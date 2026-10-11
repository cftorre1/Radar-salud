"""Synthetic regression contracts; these fixtures are not live HTML captures."""
from datetime import date
from urllib.error import HTTPError

import pytest

from radar_salud.fonasa_sources import (
    FonasaDataHubScout, FonasaDiscoveryError, FonasaNewsScout, publication_evidence_from_html,
)

URL = "https://www.fonasa.gob.cl/noticias/cobertura/"
TODAY = date(2026, 10, 11)
LISTING = '<a href="/noticias/cobertura/">Fonasa presenta novedades de cobertura pública</a>'


def test_publication_metadata_is_explicit_and_durable():
    evidence = publication_evidence_from_html(
        '<meta property="article:published_time" content="2026-09-24T10:00:00-03:00">', URL, TODAY
    )
    assert evidence == {"kind": "article:published_time", "value": "2026-09-24T10:00:00-03:00",
                        "date": "2026-09-24", "url": URL}


@pytest.mark.parametrize("html", [
    '<h1>Boletín 24 de septiembre de 2026</h1>',
    '<p>Datos al 2026-09-24. Publicado por Fonasa.</p>',
    '<meta property="article:modified_time" content="2026-09-24">',
    '<meta name="date" content="2026-09-24">',
    '<meta property="article:published_time" content="2026-02-30">',
    '<meta property="article:published_time" content="2026-10-12">',
    '<meta property="article:published_time" content="2026-09-24"><meta itemprop="datePublished" content="2026-09-25">',
])
def test_period_modified_invalid_future_and_conflicting_dates_fail_closed(html):
    assert publication_evidence_from_html(html, URL, TODAY) is None


def test_jsonld_requires_article_identity_on_the_official_detail():
    html = '<script type="application/ld+json">{"@type":"NewsArticle","url":"%s","datePublished":"2026-09-24"}</script>'
    assert publication_evidence_from_html(html % URL, URL, TODAY)["date"] == "2026-09-24"
    assert publication_evidence_from_html(html % "https://example.org/elsewhere", URL, TODAY) is None
    assert publication_evidence_from_html(html % URL, "https://fonasa.gob.cl.evil.test/noticias/cobertura/", TODAY) is None


def test_empty_listing_cannot_report_technical_success():
    with pytest.raises(FonasaDiscoveryError) as error:
        FonasaNewsScout(fetcher=lambda _: "<h1>Noticias</h1>").discover()
    assert error.value.diagnostics[-1]["reason"] == "no_article_links"


def test_newsroom_detail_failure_has_exact_diagnostic():
    def fetch(url):
        if url.endswith("/noticias/"):
            return LISTING
        raise HTTPError(url, 403, "Forbidden", {}, None)
    with pytest.raises(FonasaDiscoveryError) as error:
        FonasaNewsScout(fetcher=fetch).discover()
    assert error.value.diagnostics[-1]["url"] == URL
    assert error.value.diagnostics[-1]["http_status"] == 403
    assert error.value.diagnostics[-1]["stage"] == "detail"


def test_newsroom_undated_items_do_not_infer_from_body():
    scout = FonasaNewsScout(fetcher=lambda url: LISTING if url.endswith("/noticias/") else "Datos al 2026-09-24")
    row = scout.discover()[0]
    assert row.event_date is None
    assert "publication_date_evidence" not in row.metadata


def test_newsroom_date_evidence_is_attached_to_current_detail():
    scout = FonasaNewsScout(fetcher=lambda url: LISTING if url.endswith("/noticias/") else '<meta itemprop="datePublished" content="2026-09-24">')
    row = scout.discover()[0]
    assert row.event_date == "2026-09-24"
    assert row.metadata["publication_date_evidence"]["url"] == row.url
    assert row.metadata["publication_date_source"] == "datePublished"


def test_data_hubs_all_evaluated_even_after_first_transport_failure():
    visited = []
    def fetch(url):
        visited.append(url)
        raise HTTPError(url, 403, "Forbidden", {}, None)
    scout = FonasaDataHubScout(fetcher=fetch)
    with pytest.raises(FonasaDiscoveryError) as error:
        scout.discover()
    assert visited == [url for _, url in scout.PAGES]
    assert len(error.value.diagnostics) == 4
    assert {d["channel"] for d in error.value.diagnostics} == {channel for channel, _ in scout.PAGES}


def test_data_pdf_title_upload_path_and_listing_body_are_not_publication_dates():
    scout = FonasaDataHubScout(fetcher=lambda url: (
        '<p>Actualizado el 2026-09-24</p><a href="/wp-content/uploads/2026/09/Boletin_2026-09-24.pdf">'
        'Boletín estadístico datos al 24 de septiembre de 2026</a>'
        if url.endswith("/boletines-estadisticos/") else "<h1>Biblioteca</h1>"
    ))
    item = scout.discover()[0]
    assert item.event_date is None
    assert item.metadata["date_blocker"] == "document_has_no_item_bound_publication_date"
    assert "publication_date_evidence" not in item.metadata


def test_data_detail_fetch_failure_is_not_healthy_partial_capture():
    def fetch(url):
        if url == FonasaDataHubScout.PAGES[0][1]:
            return '<a href="/noticias/cobertura/">Noticia sobre cobertura Fonasa relevante</a>'
        if url.endswith("/noticias/cobertura/"):
            raise TimeoutError("timed out")
        return "<h1>Biblioteca</h1>"
    with pytest.raises(FonasaDiscoveryError) as error:
        FonasaDataHubScout(fetcher=fetch).discover()
    assert any(d.get("exception") == "TimeoutError" and d["stage"] == "detail" for d in error.value.diagnostics)


def test_data_detail_ignores_report_period_and_uses_current_publication_metadata():
    def fetch(url):
        if url == FonasaDataHubScout.PAGES[0][1]:
            return '<a href="/noticias/cobertura/">Boletín estadístico correspondiente a 2024</a>'
        if url.endswith("/noticias/cobertura/"):
            return '<meta property="article:published_time" content="2026-09-24"><p>Datos al 2024-12-31</p>'
        return "<h1>Biblioteca</h1>"
    row = FonasaDataHubScout(fetcher=fetch).discover()[0]
    assert row.event_date == "2026-09-24"
    assert row.metadata["publication_date_evidence"]["value"] == "2026-09-24"
    assert row.metadata["fonasa_channel"] == "Noticias"


def test_data_external_and_navigation_links_are_ignored():
    scout = FonasaDataHubScout(fetcher=lambda _: (
        '<a href="https://datosabiertos.fonasa.cl.evil.test/documento.pdf">Boletín estadístico relevante</a>'
        '<a href="https://fonasacl.cloud-qa.fonasa.cl/documento.pdf">Boletín estadístico en QA</a>'
        '<a href="/boletines-estadisticos/">Boletines estadísticos Fonasa</a>'
        '<a href="/category/noticias/">Categoría noticias oficiales</a>'
    ))
    with pytest.raises(FonasaDiscoveryError, match="no verifiable publication"):
        scout.discover()
