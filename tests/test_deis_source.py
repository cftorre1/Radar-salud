from pathlib import Path

import pytest

from radar_salud.processing import DeferredProcessing
from radar_salud.public_source_pipeline import process_deis
from radar_salud.source_scouts import DeisResourceScout
from radar_salud.sources import load_sources, source_index


HEADER = """<h1>Departamento de Estadísticas e Información de Salud</h1>
<nav><a href='/datos-abiertos/'>Datos Abiertos</a><a href='/tableros-deis/'>Tableros DEIS</a></nav>"""


def test_deis_recognizes_real_hub_shape_without_inventing_a_release():
    html = HEADER.replace("Estadísticas","Estadisticas") + """<a href='/'>Campaña inmunización VRS 2026</a>
      <a href='/datos-abiertos/'>Datos Abiertos</a>
      <a href='/noticia-general/'>Ministerio informa nueva autoridad 23 de septiembre de 2026</a>"""
    assert DeisResourceScout().discover_from_html(html) == []
    with pytest.raises(RuntimeError, match="structure unrecognized"):
        DeisResourceScout().discover_from_html("<html>maintenance</html>")


def test_deis_does_not_confuse_data_period_with_publication_date(monkeypatch):
    html = HEADER + """<a href='/publicaciones/egresos-hospitalarios-2025'>
      Publicación estadística de egresos hospitalarios — 23 de septiembre de 2026</a>
      <a href='https://evil.example/datos'>Datos abiertos — 23 de septiembre de 2026</a>
      <a href='/publicaciones/futura'>Estadísticas de mortalidad — 23 de septiembre de 2099</a>"""
    rows=DeisResourceScout().discover_from_html(html)
    assert len(rows)==1
    assert rows[0].event_date is None
    assert rows[0].url=="https://deis.minsal.cl/publicaciones/egresos-hospitalarios-2025"
    assert rows[0].metadata["resource_kind"]=="candidate_data_release"
    for title in ("Publicación de estadísticas de mortalidad al 23 de septiembre de 2026",
                  "Actualización de estadísticas de mortalidad: registros del 01-01-2025 al 31-12-2025"):
        candidate=DeisResourceScout().discover_from_html(HEADER+f"<a href='/publicaciones/mortalidad'>{title}</a>")[0]
        assert candidate.event_date is None
    period_only=HEADER+"""<a href='/estadisticas/mortalidad-2025'>
      Estadísticas de mortalidad al 23 de septiembre de 2026</a>"""
    assert DeisResourceScout().discover_from_html(period_only)==[]
    monkeypatch.setattr("radar_salud.source_scouts.fetch_html",lambda url:html if url==DeisResourceScout.PAGE else
                        '<meta property="article:published_time" content="2026-09-24T09:00:00-03:00">')
    verified=DeisResourceScout().discover()
    assert len(verified)==1
    assert verified[0].event_date=="2026-09-24"
    assert verified[0].metadata["publication_date_source"]=="article:published_time"
    monkeypatch.setattr("radar_salud.source_scouts.fetch_html",lambda url:html if url==DeisResourceScout.PAGE else
                        '<p>Datos de enero a julio de 2026, sin fecha de publicación.</p>')
    assert DeisResourceScout().discover()==[]
    monkeypatch.setattr("radar_salud.source_scouts.fetch_html",lambda url:html if url==DeisResourceScout.PAGE else
                        '<meta name="date" content="2026-09-23"><p>El conjunto cubre la serie hasta esa fecha.</p>')
    assert DeisResourceScout().discover()==[]


def test_deis_detail_and_editorial_assessment_fail_closed(monkeypatch):
    raw=DeisResourceScout().discover_from_html(HEADER+"""<a href='/publicaciones/egresos-hospitalarios-2025'>
      Publicación estadística de egresos hospitalarios — 23 de septiembre de 2026</a>""")[0]
    cfg=source_index(load_sources(Path("config/sources.json")))["deis"]
    assert process_deis(raw,cfg) is None
    raw.event_date="2026-09-24"
    raw.metadata.update(resource_kind="dated_data_release",publication_date_source="article:published_time")
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html",lambda _:"<p>Detalle oficial de la serie.</p>"*35)
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_official_news",lambda **kw:None)
    with pytest.raises(DeferredProcessing,match="pending assessment"):
        process_deis(raw,cfg)
    raw.url="https://example.org/release"
    assert process_deis(raw,cfg) is None
    raw.url="https://deis.minsal.cl/publicaciones/egresos-hospitalarios-2025"
    raw.source_name="Fuente inventada"
    assert process_deis(raw,cfg) is None
    raw.source_name="DEIS";raw.source_type="press_high_trust"
    assert process_deis(raw,cfg) is None
    raw.source_type="official"
    assert process_deis(raw,{**cfg,"slug":"minsal"}) is None
