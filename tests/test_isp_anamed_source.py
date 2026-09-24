from radar_salud.source_scouts import IspAnamedAlertScout
from radar_salud.public_source_pipeline import process_isp_anamed
from radar_salud.processing import DeferredProcessing
from radar_salud.sources import load_sources, source_index
from pathlib import Path
import pytest


LISTING = """
<table>
 <tr><td>20-08-2026</td><td>Retiro del Mercado</td><td>Farmacéutico</td>
 <td>ALERTA DE RETIRO DEL MERCADO N° 25/26 DEL PRODUCTO FARMACÉUTICO KETOROLACO</td>
 <td><a href="https://www.ispch.gob.cl/wp-content/uploads/2026/08/alerta-25.pdf">Publicación ISP</a></td></tr>
 <tr><td>Nota Informativa Farmacovigilancia</td><td>Advertencia de seguridad para tratamiento prolongado</td>
 <td><a href="https://www.ispch.gob.cl/wp-content/uploads/nota.pdf">Publicación ISP</a></td></tr>
 <tr><td>21-08-2026</td><td>Retiro del Mercado</td><td>ALERTA DE RETIRO DEL MERCADO</td>
 <td><a href="https://example.org/foreign.pdf">Publicación ISP</a></td></tr>
</table>"""


def test_anamed_requires_date_same_row_and_official_pdf():
    rows = IspAnamedAlertScout().discover_from_html(LISTING)
    assert len(rows) == 1
    row = rows[0]
    assert row.event_date == "2026-08-20"
    assert "KETOROLACO" in row.title
    assert row.url == "https://www.ispch.gob.cl/wp-content/uploads/2026/08/alerta-25.pdf"
    with pytest.raises(RuntimeError, match="verified publication rows"):
        IspAnamedAlertScout().discover_from_html("<tr><td>20-08-2026</td></tr>" + LISTING.replace("20-08-2026", ""))


def test_anamed_rejects_title_date_impossible_calendar_and_wrong_pdf():
    scout=IspAnamedAlertScout()
    with pytest.raises(RuntimeError, match="verified publication rows"):
        scout.discover_from_html('<tr><td>Sin fecha</td><td>Nota informativa estudio realizado el 20-08-2026</td>'
                                 '<td><a href="/wp-content/uploads/note.pdf">Publicación ISP</a></td></tr>')
    with pytest.raises(RuntimeError, match="verified publication rows"):
        scout.discover_from_html(LISTING.replace("20-08-2026","31-02-2026").replace("21-08-2026","31-02-2026"))
    with pytest.raises(RuntimeError, match="verified publication rows"):
        scout.discover_from_html("<html>Unexpected empty template</html>")
    with pytest.raises(RuntimeError, match="verified publication rows"):
        scout.discover_from_html("<table><tr><td>20-08-2026</td><td>Mantenimiento del sitio</td></tr></table>")
    listing=LISTING.replace('<td><a href="https://www.ispch.gob.cl/wp-content/uploads/2026/08/alerta-25.pdf">',
      '<td><a href="https://www.ispch.gob.cl/wp-content/uploads/antecedente.pdf">Antecedente</a>'
      '<a href="https://www.ispch.gob.cl/wp-content/uploads/2026/08/alerta-25.pdf">')
    assert scout.discover_from_html(listing)[0].url.endswith("alerta-25.pdf")


def test_anamed_pdf_and_assessment_fail_closed(monkeypatch):
    cfg = source_index(load_sources(Path("config/sources.json")))["isp_anamed"]
    row = IspAnamedAlertScout().discover_from_html(LISTING)[0]
    monkeypatch.setattr("radar_salud.public_source_pipeline.extract_pdf_text", lambda *a, **kw: "")
    try:
        process_isp_anamed(row, cfg)
    except DeferredProcessing:
        pass
    else:
        raise AssertionError("Unreadable official PDF cannot become a signal")
    monkeypatch.setattr("radar_salud.public_source_pipeline.extract_pdf_text", lambda *a, **kw: "Official detail " * 40)
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_official_news", lambda **kw: None)
    try:
        process_isp_anamed(row, cfg)
    except DeferredProcessing:
        pass
    else:
        raise AssertionError("Unevaluated document cannot become a signal")
