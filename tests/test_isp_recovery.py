"""Regression HTML is synthetic; observed official row values are documented in the audit.

No raw live HTML was obtainable through this environment's egress policy.
"""
import pytest

from radar_salud.isp_sources import IspAnamedAlertScout, official_isp_url, publication_date


def _anamed_row(label="Alerta", href="/wp-content/uploads/alerta.pdf", published="29-09-2026"):
    return f'''<table><tr><td>{published}</td><td>Retiro del Mercado</td><td>Farmacéutico</td>
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
    def fetch(url):
        if url == IspAnamedAlertScout.PAGE:
            raise OSError("CONNECT tunnel failed: 403 Forbidden")
        return _anamed_row()
    monkeypatch.setattr("radar_salud.isp_sources.fetch_html", fetch)
    scout = IspAnamedAlertScout()
    assert scout.discover()[0].metadata["discovered_from"] == scout.PAGES[1]
    assert scout.diagnostics[0]["status"] == "blocked"
    assert scout.diagnostics[1]["status"] == "discovered"


def test_publication_date_is_calendar_checked_complete_field():
    assert publication_date("17 junio, 2026") == "2026-06-17"
    assert publication_date("2026-10-07T09:30:00-03:00") == "2026-10-07"
    assert publication_date("Informe circulación virus respiratorios SE39 06-10-2026") is None
    assert publication_date("31 febrero, 2026") is None
    assert publication_date("2026-10-07 trailing data") is None


