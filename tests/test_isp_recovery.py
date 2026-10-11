"""Regression HTML is synthetic; observed official row values are documented in the audit.

No raw live HTML was obtainable through this environment's egress policy.
"""
import pytest

from radar_salud.isp_sources import IspAnamedAlertScout, IspSurveillanceScout, publication_date


def _anamed_row(label="Alerta", href="/wp-content/uploads/alerta.pdf", published="29-09-2026"):
    return f'''<table><tr><th>Fecha Publicación</th><th>Materia</th><th>Tipo de Producto</th><th>Producto</th><th>Archivo Adjunto</th></tr>
    <tr><td>{published}</td><td>Retiro del Mercado</td><td>Farmacéutico</td>
    <td>ALERTA DE RETIRO DEL MERCADO N° 31/26 DEL PRODUCTO FARMACÉUTICO METOCLOPRAMIDA</td>
    <td><a href="{href}">{label}</a></td></tr></table>'''


@pytest.mark.parametrize("label", ["Alerta", "Nota informativa", "Publicación ISP"])
def test_anamed_accepts_current_official_attachment_labels(label):
    item = IspAnamedAlertScout().discover_from_html(_anamed_row(label))[0]
    assert item.url == "https://www.ispch.cl/wp-content/uploads/alerta.pdf"
    assert item.event_date == "2026-09-29"
    assert item.metadata["publication_date_evidence"] == {
        "kind": "listing:fecha_publicacion", "value": "29-09-2026",
        "date": "2026-09-29", "url": IspAnamedAlertScout.PAGE}


def test_anamed_preserves_two_independently_readable_official_attachments():
    html = _anamed_row().replace('</td></tr>', '<a href="/wp-content/uploads/nota.pdf">Nota informativa</a></td></tr>')
    assert len(IspAnamedAlertScout().discover_from_html(html)) == 2


@pytest.mark.parametrize("href", ["http://www.ispch.cl/test.pdf", "https://ispch.cl.evil.test/test.pdf",
                                 "https://www.ispch.gob.cl/test.pdf", "https://u@ispch.cl/test.pdf",
                                 "https://ispch.cl:8443/test.pdf", "https://example.org/test.pdf"])
def test_anamed_rejects_unverified_attachment_host(href):
    with pytest.raises(RuntimeError, match="verified publication rows"):
        IspAnamedAlertScout().discover_from_html(_anamed_row(href=href))


@pytest.mark.parametrize("published", ["31-02-2026", "29-09-2099", "Periodo 29-09-2026", ""])
def test_anamed_never_uses_title_upload_or_another_row_date(published):
    html = _anamed_row(href="/wp-content/uploads/2026/09/29-09-2026.pdf", published=published)
    html = '<p>Fecha Publicación 29-09-2026</p><tr><td>29-09-2026</td></tr>' + html
    with pytest.raises(RuntimeError, match="verified publication rows"):
        IspAnamedAlertScout().discover_from_html(html)


def test_anamed_fallback_is_recorded_and_not_silently_healthy(monkeypatch):
    def fetch(url, source_slug=None):
        if url == IspAnamedAlertScout.PAGE:
            raise OSError("CONNECT tunnel failed: 403 Forbidden")
        return _anamed_row()
    monkeypatch.setattr("radar_salud.isp_sources.fetch_html", fetch)
    scout = IspAnamedAlertScout()
    assert scout.discover()[0].metadata["discovered_from"] == scout.PAGES[1]
    assert scout.diagnostics[0]["status"] == "blocked"
    assert scout.diagnostics[1]["status"] == "discovered"


@pytest.mark.parametrize("header", ["Fecha Vencimiento", "Período de datos", "Fecha actualización"])
def test_anamed_requires_recognized_publication_column(header):
    with pytest.raises(RuntimeError, match="verified publication rows"):
        IspAnamedAlertScout().discover_from_html(_anamed_row().replace("Fecha Publicación", header))


def test_publication_date_is_calendar_checked_complete_field():
    assert publication_date("17 junio, 2026") == "2026-06-17"
    assert publication_date("2026-10-07T09:30:00-03:00") == "2026-10-07"
    assert publication_date("Informe circulación virus respiratorios SE39 06-10-2026") is None
    assert publication_date("31 febrero, 2026") is None
    assert publication_date("2026-10-07 trailing data") is None
    assert publication_date("2026-10-07T99:00:00-03:00") is None


LABORATORY = '''<table><tr><th colspan="2">Titulo</th><th>Fecha Publicación</th><th>Enlace</th></tr>
<tr><td><img src="rabia.jpg"></td><td>Informe de Laboratorio Biomédico Vigilancia de Rabia Animal 2025</td>
<td>17 junio, 2026</td><td><a href="/boletin/informe-de-laboratorio-biomedico-vigilancia-de-rabia-animal-2025/">Enlace</a></td></tr></table>'''
RESPIRATORY = '''<table><tr><th>Semana</th><th>Enlace</th></tr>
<tr><td>Semana 39, 2026</td><td><a href="/documento/semana-39-2026/">Enlace</a></td></tr></table>'''
DOCUMENT = '''<meta property="article:published_time" content="2026-10-07T10:00:00-03:00">
<h1>Semana 39, 2026</h1><p>7 octubre, 2026</p>
<a href="/wp-content/uploads/2026/10/Informe-circulacion-virus-respiratorios-SE39-06-10-2026.pdf">Informe circulación virus respiratorios SE39 06-10-2026</a>'''


def _respiratory_candidate():
    scout = IspSurveillanceScout()
    return scout.discover_from_html(RESPIRATORY, scout.PAGES[1][1], scout.PAGES[1][0])[0]


def test_laboratory_uses_publication_column_and_enlace_detail_not_data_year():
    scout = IspSurveillanceScout()
    item = scout.discover_from_html(LABORATORY, scout.PAGES[0][1], scout.PAGES[0][0])[0]
    assert item.event_date == "2026-06-17"
    assert item.title.endswith("2025")
    assert item.url.endswith("rabia-animal-2025/")
    assert item.metadata["publication_date_evidence"]["value"] == "17 junio, 2026"
    with pytest.raises(RuntimeError, match="verified document rows"):
        scout.discover_from_html(LABORATORY.replace("Fecha Publicación", "Período datos"), scout.PAGES[0][1], scout.PAGES[0][0])


def test_respiratory_period_and_pdf_filename_are_not_publication_dates():
    item = _respiratory_candidate()
    assert item.event_date is None
    assert "publication_date_evidence" not in item.metadata
    item = IspSurveillanceScout().document_from_html(item, DOCUMENT)
    assert item.event_date == "2026-10-07"
    assert item.url.endswith("SE39-06-10-2026.pdf")
    assert item.metadata["publication_date_evidence"]["url"].endswith("/documento/semana-39-2026/")
    assert item.metadata["publication_document_url"] == item.url
    assert item.metadata["publication_document_link_evidence"]["document_url"] == item.url


@pytest.mark.parametrize("html", [DOCUMENT.replace('property="article:published_time"', 'property="article:modified_time"'),
                                  DOCUMENT.replace("2026-10-07T10:00:00-03:00", "2099-10-07T10:00:00-03:00"),
                                  DOCUMENT + '<meta itemprop="datePublished" content="2026-10-06">'])
def test_respiratory_rejects_no_publication_field_future_or_conflicting_dates(html):
    with pytest.raises(RuntimeError, match="explicit verified publication date"):
        IspSurveillanceScout().document_from_html(_respiratory_candidate(), html)


@pytest.mark.parametrize("html", [DOCUMENT.replace("/wp-content/uploads/", "https://foreign.example/uploads/"),
                                  DOCUMENT + '<a href="/wp-content/uploads/other.pdf">Otro documento</a>'])
def test_surveillance_document_requires_unambiguous_official_pdf(html):
    with pytest.raises(RuntimeError, match="exactly one official PDF"):
        IspSurveillanceScout().document_from_html(_respiratory_candidate(), html)


def test_laboratory_detail_date_disagreement_cannot_change_listing_publication():
    scout = IspSurveillanceScout()
    item = scout.discover_from_html(LABORATORY, scout.PAGES[0][1], scout.PAGES[0][0])[0]
    with pytest.raises(RuntimeError, match="dates disagree"):
        scout.document_from_html(item, DOCUMENT)


def test_surveillance_continues_respiratory_when_laboratory_is_blocked(monkeypatch):
    def fetch(url, source_slug=None):
        if "/boletin/" in url:
            raise OSError("CONNECT tunnel failed: 403 Forbidden")
        if "/documento/" in url:
            return DOCUMENT
        return RESPIRATORY
    monkeypatch.setattr("radar_salud.isp_sources.fetch_html", fetch)
    scout = IspSurveillanceScout()
    items = scout.discover()
    assert len(items) == 1 and items[0].event_date == "2026-10-07"
    assert scout.partial_failure is True
    assert len([row for row in scout.diagnostics if row.get("error_type")]) == 2
    assert any(row["channel"] == scout.PAGES[0][0] and row["status"] == "blocked" for row in scout.diagnostics)


def test_surveillance_continues_laboratory_when_respiratory_is_blocked(monkeypatch):
    def fetch(url, source_slug=None):
        if "/boletin/" in url:
            return LABORATORY.replace('/boletin/informe-de-laboratorio-biomedico-vigilancia-de-rabia-animal-2025/', '/wp-content/uploads/rabia.pdf')
        raise OSError("CONNECT tunnel failed: 403 Forbidden")
    monkeypatch.setattr("radar_salud.isp_sources.fetch_html", fetch)
    scout = IspSurveillanceScout()
    items = scout.discover()
    assert len(items) == 1 and items[0].event_date == "2026-06-17"
    assert scout.partial_failure is True
