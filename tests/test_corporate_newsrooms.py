from pathlib import Path

from radar_salud.source_scouts import CorporateNewsroomScout
from radar_salud.public_source_pipeline import process_corporate_news
from radar_salud.sources import load_sources, source_index
from radar_salud.processing import DeferredProcessing
from radar_salud.models import RawItem


def test_only_verified_newsroom_detail_links_are_discovered():
    scout=CorporateNewsroomScout("redsalud")
    html='''<a href="/noticias/redsalud-y-nueva-masvida-convenio">RedSalud y Nueva Masvida activan convenio nacional</a>
      <a href="https://www.redsalud.cl/noticias?page=4">Todas las noticias</a>
      <a href="https://evil.example/noticias/noticia">Comunicado de otra empresa y dominio</a>'''
    rows=scout.discover_from_html(html)
    assert len(rows)==1
    assert rows[0].url=="https://www.redsalud.cl/noticias/redsalud-y-nueva-masvida-convenio"
    bupa=CorporateNewsroomScout("bupa_chile")
    real=Path("tests/fixtures/bupa_real_card.html").read_text()
    bupa_rows=bupa.discover_from_html(real)
    assert len(bupa_rows)==1
    assert bupa_rows[0].title.startswith("Bupa Chile y Teletón renuevan alianza")
    assert bupa_rows[0].url.endswith("bupa-chile-y-teleton-renuevan-alianza-para-acercar-salud-e-inclusion")
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


def test_real_bupa_article_date_and_body_are_bound_to_one_story(monkeypatch):
    raw=RawItem("bupa_chile","Clínica Bupa Santiago incorpora cirugía robótica y amplía el acceso a intervenciones de alta precisión en Chile",
                "https://www.bupa.cl/sala-de-prensa/clinica-bupa-santiago-incorpora-cirugia-robotica","Bupa Chile","corporate")
    cfg=source_index(load_sources(Path("config/sources.json")))["bupa_chile"]
    # Published layout and first passage from the same official article.
    html=Path("tests/fixtures/bupa_real_article_excerpt.html").read_text()
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html",lambda _:html)
    captured=[]
    def assess(**kw):
        captured.append(kw["text"])
        return {"relevance_score":82,"what_happened":"Bupa presentó una iniciativa clínica verificable en la red chilena.",
                "why_it_matters":"La incorporación puede afectar capacidad y oferta de prestaciones locales."}
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news",assess)
    row=process_corporate_news(raw,cfg)
    assert row["event_date"]=="2026-05-05"
    assert row["source_url"].endswith("clinica-bupa-santiago-incorpora-cirugia-robotica")
    assert len(captured)==1 and "La cirugía robótica" in captured[0]
    assert "breadcrumb" not in captured[0].lower() and "gtm" not in captured[0].lower()
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news",lambda **kw:{**assess(**kw),"relevance_score":70})
    assert process_corporate_news(raw,cfg) is None
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html",lambda _:html.replace('<h1 class="enc-main__title" id="#contenido-ppal">'+raw.title+'</h1>',""))
    try:process_corporate_news(raw,cfg)
    except DeferredProcessing:pass
    else:raise AssertionError("Missing article headline cannot inherit listing title")
    raw.event_date="2026-05-05"
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html",lambda _:html.replace("Martes 5 de mayo de 2026",""))
    try:process_corporate_news(raw,cfg)
    except DeferredProcessing:pass
    else:raise AssertionError("A carried date cannot replace missing article publication date")
