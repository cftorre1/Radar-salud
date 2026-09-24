from radar_salud.source_scouts import FonasaNewsScout
from radar_salud import public_source_pipeline as pipeline
from radar_salud.processing import DeferredProcessing
from radar_salud.sources import load_sources,source_index
from pathlib import Path


def test_official_discovery_rejects_external_or_listing_links():
    html='''<a href="/noticias/informe-de-cobertura-2026/">Fonasa presenta informe de cobertura 2026</a>
    <a href="https://example.com/noticias/externa/">Fonasa presenta informe externo 2026</a>
    <a href="/noticias/">Archivo de noticias institucionales</a>'''
    rows=FonasaNewsScout().discover_from_html(html)
    assert len(rows)==1
    assert rows[0].url=='https://www.fonasa.gob.cl/noticias/informe-de-cobertura-2026/'
    assert rows[0].event_date is None


def test_fonasa_rejects_undated_and_defers_unassessed(monkeypatch):
    raw=FonasaNewsScout().discover_from_html('<a href="/noticias/cobertura/">Fonasa informa nuevas coberturas verificables</a>')[0]
    monkeypatch.setattr(pipeline,'fetch_html',lambda _: '<meta name="description" content="Detalle institucional con contenido verificable y suficiente sobre cambios de cobertura, prestadores, beneficiarios y alcance de las prestaciones del sistema de salud. La publicación describe medidas y fechas que requieren evaluación antes de su publicación.">')
    cfg=source_index(load_sources(Path('config/sources.json')))['fonasa']
    assert pipeline.process_fonasa(raw,cfg) is None
    raw.event_date='2026-09-24'
    monkeypatch.setattr(pipeline,'analyze_official_news',lambda **_:None)
    try:pipeline.process_fonasa(raw,cfg)
    except DeferredProcessing:pass
    else:raise AssertionError('FONASA must defer rather than fabricate assessment')


def test_scout_dates_only_from_detail_metadata(monkeypatch):
    from radar_salud import source_scouts
    def fetch(url):
        if url.endswith('/noticias/'):
            return '<a href="/noticias/cobertura/">Fonasa anuncia cobertura relevante para beneficiarios</a>'
        return '<meta property="article:published_time" content="2026-09-24T10:00:00-03:00">'
    monkeypatch.setattr(source_scouts,'fetch_html',fetch)
    assert FonasaNewsScout().discover()[0].event_date=='2026-09-24'
    monkeypatch.setattr(source_scouts,'fetch_html',lambda url: fetch(url) if url.endswith('/noticias/') else '<title>Sin fecha verificable</title>')
    assert FonasaNewsScout().discover()[0].event_date is None


def test_detail_fetch_failure_is_not_technical_success_or_editorial_rejection(monkeypatch):
    from radar_salud import source_scouts
    monkeypatch.setattr(source_scouts,'fetch_html',lambda url: '<a href="/noticias/cobertura/">Fonasa informa nuevas coberturas verificables</a>' if url.endswith('/noticias/') else (_ for _ in ()).throw(TimeoutError()))
    try:FonasaNewsScout().discover()
    except RuntimeError:pass
    else:raise AssertionError('partial fetch cannot be healthy discovery')
    raw=FonasaNewsScout().discover_from_html('<a href="/noticias/cobertura/">Fonasa informa nuevas coberturas verificables</a>')[0]
    raw.event_date='2026-09-24'
    monkeypatch.setattr(pipeline,'fetch_html',lambda _: (_ for _ in ()).throw(TimeoutError()))
    cfg=source_index(load_sources(Path('config/sources.json')))['fonasa']
    try:pipeline.process_fonasa(raw,cfg)
    except DeferredProcessing:pass
    else:raise AssertionError('transient fetch must retry')
