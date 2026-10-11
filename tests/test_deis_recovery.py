from datetime import date
from pathlib import Path
from urllib.error import URLError

import pytest

from radar_salud.deis_sources import DeisDocumentScout, official_deis_url
from radar_salud.processing import DeferredProcessing
from radar_salud.public_source_pipeline import process_deis
from radar_salud.sources import load_sources, source_index


HEADER = """<h1>Departamento de Estadísticas e Información de Salud</h1>
<h2>Centro Nacional de Referencia de la Familia Internacional de las Clasificaciones</h2>
<h3>Documentación y Normativa</h3>"""
PDF = ("https://repositoriodeis.minsal.cl/ContenidoSitioWeb2020/uploads/2021/03/"
       "Orientaciones%20de%20codificaci%C3%B3n%20para%20el%20Cap%C3%ADtulo%20XXI%20junio2026.pdf")
TODAY = date(2026, 10, 11)


def listing(*blocks):
    return HEADER + "<ul>" + "".join(f"<li>{block}</li>" for block in blocks) + "</ul>"


def document(notice, *, href=PDF, title="Orientaciones de codificación para el Capítulo XXI de la CIE-10 – Actualización"):
    return f'<a href="{href}">{title}</a> {notice}'


def test_verified_listing_date_wins_over_upload_path_and_pdf_edition_period():
    # Reconstructed from the live Centro FIC listing. HTML could not be captured
    # from this runner; the durable browser observation records that limitation.
    html = listing(document("¡Publicado 25/06/2026!. Nota: El documento fue actualizado en junio de 2026 "
                            "para corregir la orientación de codificación de la categoría Z54.- Convalecencia."))
    scout = DeisDocumentScout(today=TODAY)
    item, = scout.discover_from_html(html)
    assert item.event_date == "2026-06-25"
    assert item.url == PDF
    assert item.metadata["publication_date_evidence"] == {
        "kind": "official_document_listing:published", "value": "Publicado 25/06/2026",
        "date": "2026-06-25", "url": DeisDocumentScout.PAGE,
    }
    assert item.metadata["publication_date_source"] == "official_document_listing:published"
    assert item.metadata["document_verification"] == "pending_pipeline"
    assert len(item.metadata["listing_sha256"]) == 64
    assert scout.diagnostics["coverage_status"] == "dated_documents_found"


@pytest.mark.parametrize("text", [
    "Serie 2018 - 2024; mortalidad hasta 25/06/2026",
    "Mayo 2026. Edición actual. Datos al 25/06/2026",
    "¡Actualizado agosto/2026!",
    "¡Agregado 26/03/2015!",
    "Resolución de fecha 25/06/2026",
    "Publicado 31/02/2026",
    "Publicado 12/10/2026",
    "Publicado 25/06/2026 y Publicado 26/06/2026",
    "Actualizada 23-07-2026",  # No substantive change explained.
])
def test_does_not_invent_publication_from_coverage_or_partial_invalid_future_or_ambiguous_dates(text):
    assert DeisDocumentScout(today=TODAY).discover_from_html(listing(document(text))) == []


def test_publication_notice_cannot_leak_into_a_neighbor_or_nested_list_item():
    html = listing(
        document("¡Publicado 25/06/2026!"),
        document("Datos 2002 - 2023", href="https://repositoriodeis.minsal.cl/undated.pdf"),
        "Publicado 24/06/2026<ul><li>" + document("sin fecha", href="https://repositoriodeis.minsal.cl/nested.pdf") + "</li></ul>",
    )
    rows = DeisDocumentScout(today=TODAY).discover_from_html(html)
    assert [row.url for row in rows] == [PDF]


def test_ambiguous_multiple_document_links_do_not_share_one_date():
    html = listing(document("¡Publicado 25/06/2026!") + document("", href="https://repositoriodeis.minsal.cl/other.pdf"))
    assert DeisDocumentScout(today=TODAY).discover_from_html(html) == []


@pytest.mark.parametrize("notice", [
    "¡Actualización 31/08/2026! Actualización editorial: ajuste en la presentación de los códigos CIE-10, sin cambios en el contenido de la lista.",
    "¡Publicado 31/08/2026! Actualización editorial: revisión de redacción y ortografía.",
])
def test_editorial_only_updates_do_not_become_material_releases(notice):
    scout = DeisDocumentScout(today=TODAY)
    assert scout.discover_from_html(listing(document(notice))) == []
    assert scout.diagnostics["rejected_editorial_only"] == 1


def test_updated_notice_requires_explicit_substantive_change_and_keeps_date_kind():
    rows = DeisDocumentScout(today=TODAY).discover_from_html(listing(document(
        "¡Actualizado 25/06/2026! Corrección de la orientación de codificación de Z54.")))
    assert len(rows) == 1
    assert rows[0].metadata["publication_date_source"] == "official_document_listing:updated"


@pytest.mark.parametrize("url", [
    "http://repositoriodeis.minsal.cl/guide.pdf",
    "https://deis.minsal.cl.evil.example/guide.pdf",
    "https://repositoriodeis.minsal.cl@evil.example/guide.pdf",
    "https://evil.example@repositoriodeis.minsal.cl/guide.pdf",
    "https://repositoriodeis.minsal.cl:444/guide.pdf",
    "https://deis.minsal.cl/noticias/",
])
def test_document_discovery_rejects_unverified_authorities_and_non_documents(url):
    assert not official_deis_url(url, pdf=True)
    assert DeisDocumentScout(today=TODAY).discover_from_html(listing(document("Publicado 25/06/2026", href=url))) == []


def test_parser_is_fail_closed_for_layout_changes_and_unverified_listing():
    scout = DeisDocumentScout(today=TODAY)
    with pytest.raises(RuntimeError, match="structure unrecognized"):
        scout.discover_from_html("<h1>Maintenance</h1>" + listing(document("Publicado 25/06/2026")).replace(HEADER, ""))
    with pytest.raises(ValueError, match="verified Centro FIC"):
        scout.discover_from_html(listing(document("Publicado 25/06/2026")), "https://example.org/listing")


def test_no_documents_is_explicit_coverage_gap_not_healthy():
    scout = DeisDocumentScout(today=TODAY)
    assert scout.discover_from_html(HEADER) == []
    assert scout.diagnostics["coverage_status"] == "no_verifiable_documents"
    assert "healthy" not in scout.diagnostics


def test_transport_failure_is_not_silently_converted_to_zero_discoveries():
    def blocked(_):
        raise URLError("Tunnel connection failed: 403 Forbidden")
    scout = DeisDocumentScout(fetcher=blocked, today=TODAY)
    with pytest.raises(URLError, match="Tunnel connection"):
        scout.discover()
    assert scout.diagnostics["listing_recognized"] is False
    assert scout.diagnostics["fetch_error"] == "URLError"


def test_fetcher_is_injectable_and_fetches_the_verified_listing():
    calls = []
    def fetcher(url):
        calls.append(url)
        return listing(document("Publicado 25/06/2026"))
    assert len(DeisDocumentScout(fetcher=fetcher, today=TODAY).discover()) == 1
    assert calls == [DeisDocumentScout.PAGE]


def test_document_processing_requires_live_pdf_even_when_raw_text_was_supplied(monkeypatch):
    item, = DeisDocumentScout(today=TODAY).discover_from_html(listing(document("Publicado 25/06/2026")))
    item.raw_text = "Preexisting text must not count as a fresh PDF capture. " * 30
    cfg = source_index(load_sources(Path("config/sources.json")))["deis"]
    calls = []
    monkeypatch.setattr("radar_salud.public_source_pipeline.extract_public_source_pdf",
                        lambda url, slug, **kwargs: calls.append(url) or "")
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_official_news",
                        lambda **kwargs: pytest.fail("An unreadable PDF must not reach assessment"))
    with pytest.raises(DeferredProcessing, match="official PDF unreadable"):
        process_deis(item, cfg)
    assert calls == [PDF]
    assert item.metadata["document_verification"] == "pending_pipeline"


def test_captured_document_keeps_publication_provenance_while_assessment_pending(monkeypatch):
    item, = DeisDocumentScout(today=TODAY).discover_from_html(listing(document("Publicado 25/06/2026")))
    cfg = source_index(load_sources(Path("config/sources.json")))["deis"]
    body = "Manual de Orientaciones CIE-10. Corrección de la categoría Z54, convalecencia. " * 15
    monkeypatch.setattr("radar_salud.public_source_pipeline.extract_public_source_pdf", lambda url, slug, **kwargs: body)
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_official_news", lambda **kwargs: None)
    with pytest.raises(DeferredProcessing, match="pending assessment"):
        process_deis(item, cfg)
    assert item.metadata["document_verification"] == "readable_pdf"
    assert item.event_date == "2026-06-25"
    assert item.metadata["publication_date_evidence"]["url"] == DeisDocumentScout.PAGE


@pytest.mark.parametrize("mutation", ["date", "notice", "authority"])
def test_document_provenance_tampering_is_rejected_before_capture(monkeypatch, mutation):
    item, = DeisDocumentScout(today=TODAY).discover_from_html(listing(document("Publicado 25/06/2026")))
    cfg = source_index(load_sources(Path("config/sources.json")))["deis"]
    evidence = item.metadata["publication_date_evidence"]
    if mutation == "date":
        evidence["date"] = "2026-06-26"
    elif mutation == "notice":
        evidence["value"] = "Publicado 26/06/2026"
    else:
        evidence["url"] = "https://example.org/centrofic/"
    monkeypatch.setattr("radar_salud.public_source_pipeline.extract_public_source_pdf",
                        lambda **kwargs: pytest.fail("Unverified provenance must not reach capture"))
    assert process_deis(item, cfg) is None
