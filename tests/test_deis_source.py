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


def test_deis_accepts_only_dated_material_first_party_release():
    html = HEADER + """<a href='/publicaciones/egresos-hospitalarios-2025'>
      Publicación estadística de egresos hospitalarios — 23 de septiembre de 2026</a>
      <a href='https://evil.example/datos'>Datos abiertos — 23 de septiembre de 2026</a>
      <a href='/publicaciones/futura'>Estadísticas de mortalidad — 23 de septiembre de 2099</a>"""
    rows=DeisResourceScout().discover_from_html(html)
    assert len(rows)==1
    assert rows[0].event_date=="2026-09-23"
    assert rows[0].url=="https://deis.minsal.cl/publicaciones/egresos-hospitalarios-2025"
    assert rows[0].metadata["resource_kind"]=="dated_data_release"
    period_only=HEADER+"""<a href='/estadisticas/mortalidad-2025'>
      Estadísticas de mortalidad al 23 de septiembre de 2026</a>"""
    assert DeisResourceScout().discover_from_html(period_only)==[]


def test_deis_detail_and_editorial_assessment_fail_closed(monkeypatch):
    raw=DeisResourceScout().discover_from_html(HEADER+"""<a href='/publicaciones/egresos-hospitalarios-2025'>
      Publicación estadística de egresos hospitalarios — 23 de septiembre de 2026</a>""")[0]
    cfg=source_index(load_sources(Path("config/sources.json")))["deis"]
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
