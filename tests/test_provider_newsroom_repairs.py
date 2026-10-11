import pytest

from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing
from radar_salud.public_source_pipeline import _IndisaArticle, process_corporate_news
from radar_salud.source_scouts import CorporateNewsroomScout


def test_bupa_root_article_requires_newsroom_card_and_date(monkeypatch):
    title = "Bupa acelera su crecimiento con inversión y adquisición de clínicas"
    url = "https://www.bupa.cl/bupa-acelera-su-crecimiento-en-el-sector-oriente"
    listing = f'<article class="card"><h3 class="card__title">{title}</h3><a href="{url}">Ver más</a></article>'
    raw = CorporateNewsroomScout("bupa_chile").discover_from_html(listing)[0]
    cfg = {"slug": "bupa_chile", "source_type": "corporate", "base_confidence": 75}
    html = f'<h1 class="enc-main__title">{title}</h1><div class="CUERPO"><p>' + "Capacidad ambulatoria y nueva infraestructura clínica. " * 20 + '</p></div>'
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html", lambda _: html)
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news", lambda **kw: None)
    with pytest.raises(DeferredProcessing, match="publication date unavailable"):
        process_corporate_news(raw, cfg)
    html = '<meta property="article:published_time" content="2026-09-21">' + html
    with pytest.raises(DeferredProcessing, match="pending assessment"):
        process_corporate_news(raw, cfg)
    raw.metadata.clear()
    assert process_corporate_news(raw, cfg) is None


def test_indisa_visible_header_stamp_excludes_dates_from_article_and_footer():
    article = _IndisaArticle()
    article.feed('<p>Menú</p><div>Novedades INDISA • 11/09/2026 • 4 min lectura</div>'
                 '<h1>Convenio INDISA con Isapre Esencial</h1><p>Objetivo para 31/12/2027.</p>'
                 '<footer>Actualizado 10/10/2026</footer>')
    article.finish()
    assert article.event_date() == "2026-09-11"
    undated = _IndisaArticle()
    undated.feed('<h1>Convenio sin fecha</h1><p>Objetivo para 31/12/2027.</p>')
    undated.finish()
    assert undated.event_date() is None


def test_redsalud_discovers_beyond_first_page_without_duplicate_pinned_card(monkeypatch):
    def card(slug, day):
        return f'<article><a href="/noticias/{slug}"></a><h3>Nueva capacidad clínica y convenio {slug}</h3><p>{day}</p></article>'
    pinned = card("trasplante", "27 Ago 2026")
    pages = {"https://www.redsalud.cl/noticias": pinned}
    for page in range(1, 5): pages[f"https://www.redsalud.cl/noticias?page={page}"] = pinned + card(f"inversion-{page}", "23 Jul 2026")
    monkeypatch.setattr("radar_salud.source_scouts.fetch_html", pages.__getitem__)
    items = CorporateNewsroomScout("redsalud").discover()
    assert len(items) == 5 and len({raw.url for raw in items}) == 5
