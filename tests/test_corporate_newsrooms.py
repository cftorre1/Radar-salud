from pathlib import Path

from radar_salud.source_scouts import CorporateNewsroomScout
from radar_salud.public_source_pipeline import process_corporate_news
from radar_salud.sources import load_sources, source_index
from radar_salud.processing import DeferredProcessing


def test_only_verified_newsroom_detail_links_are_discovered():
    scout=CorporateNewsroomScout("redsalud")
    html='''<a href="/noticias/redsalud-y-nueva-masvida-convenio">RedSalud y Nueva Masvida activan convenio nacional</a>
      <a href="https://www.redsalud.cl/noticias?page=4">Todas las noticias</a>
      <a href="https://evil.example/noticias/noticia">Comunicado de otra empresa y dominio</a>'''
    rows=scout.discover_from_html(html)
    assert len(rows)==1
    assert rows[0].url=="https://www.redsalud.cl/noticias/redsalud-y-nueva-masvida-convenio"
    bupa=CorporateNewsroomScout("bupa_chile")
    assert len(bupa.discover_from_html('<a href="/sala-de-prensa/clinica-bupa-santiago-incorpora-cirugia-robotica">Clínica Bupa Santiago incorpora cirugía robótica</a>'))==1
    try:scout.discover_from_html('<a href="/noticias">Notas</a>')
    except RuntimeError:pass
    else:raise AssertionError("Unexpected markup must be a technical failure")


def test_undated_or_unassessed_press_never_reaches_feed(monkeypatch):
    raw=CorporateNewsroomScout("redsalud").discover_from_html(
        '<a href="/noticias/redsalud-y-nueva-masvida-convenio">RedSalud y Nueva Masvida activan convenio nacional</a>')[0]
    cfg=source_index(load_sources(Path("config/sources.json")))["redsalud"]
    html='<meta name="description" content="Convenio de prestaciones entre las redes">' + '<p>Texto oficial del comunicado.</p>'*40
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html",lambda _:html)
    assert process_corporate_news(raw,cfg) is None  # No date from a verified publication field.
    raw.event_date="2026-02-31"
    assert process_corporate_news(raw,cfg) is None
    raw.event_date=None
    html='<meta property="article:published_time" content="2026-09-21T10:00:00-03:00">'+html
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html",lambda _:html)
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news",lambda **kw:None)
    try:process_corporate_news(raw,cfg)
    except DeferredProcessing:pass
    else:raise AssertionError("An unassessed company claim is not a signal")
