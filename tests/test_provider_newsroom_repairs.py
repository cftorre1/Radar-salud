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
    unrelated = _IndisaArticle()
    unrelated.feed('<nav><p>Evento seminario: 15/09/2026</p></nav><h1>Convenio sin sello</h1>')
    unrelated.finish()
    assert unrelated.event_date() is None


def test_redsalud_discovers_beyond_first_page_without_duplicate_pinned_card(monkeypatch):
    def card(slug, day):
        return f'<article><a href="/noticias/{slug}"></a><h3>Nueva capacidad clínica y convenio {slug}</h3><p>{day}</p></article>'
    pinned = card("trasplante", "27 Ago 2026")
    pages = {"https://www.redsalud.cl/noticias": pinned}
    for page in range(1, 5): pages[f"https://www.redsalud.cl/noticias?page={page}"] = pinned + card(f"inversion-{page}", "23 Jul 2026")
    monkeypatch.setattr("radar_salud.source_scouts.fetch_html", pages.__getitem__)
    items = CorporateNewsroomScout("redsalud").discover()
    assert len(items) == 5 and len({raw.url for raw in items}) == 5


def test_corporate_date_learned_in_detail_obeys_backfill_horizon(monkeypatch):
    from radar_salud.processing import OutsideBackfillHorizon
    title='Bupa acelera inversión y nueva capacidad clínica'
    raw=RawItem('bupa_chile',title,'https://www.bupa.cl/sala-de-prensa/inversion', 'Bupa Chile','corporate')
    html=f'<meta property="article:published_time" content="2025-09-01"><h1 class="enc-main__title">{title}</h1><div class="CUERPO"><p>'+'Nueva capacidad y adquisición de clínicas. '*20+'</p></div>'
    monkeypatch.setattr('radar_salud.public_source_pipeline.fetch_html',lambda _:html)
    monkeypatch.setattr('radar_salud.public_source_pipeline.analyze_news',lambda **kw:pytest.fail('Old backfill must not consume assessment'))
    with pytest.raises(OutsideBackfillHorizon,match='2025-09-01'):
        process_corporate_news(raw,{'slug':'bupa_chile','source_type':'corporate'})


def test_provider_header_date_does_not_borrow_from_body_or_related_cards():
    from radar_salud.beta_sources import _ProviderPublication
    cases=[('<div>Novedades 20/08/2026</div><h1>Plan Enlace</h1><p>Julio 2025.</p>','2026-08-20'),
           ('<div>Operativos Médicos 24/08/2026</div><h1>Plan Enlace ejecutado</h1><p>Treinta cirugías.</p>','2026-08-24'),
           ('<h1>Centro Puerto Varas</h1><ul><li>agosto 24, 2026</li></ul><p>2030.</p>','2026-08-24'),
           ('<h1>SAFED</h1><div>28/08/2026</div><p>19 agosto.</p>','2026-08-28'),
           ('<nav>19/08/2026</nav><h1>Undated</h1><p>Evento 24/08/2026</p><h2>Relacionadas</h2><div>28/09/2026</div>',None)]
    for html,expected in cases:
        p=_ProviderPublication();p.feed(html)
        assert p.publication()[0]==expected


@pytest.mark.parametrize('slug,name,processor,url',[
    ('indisa','Clínica INDISA','corporate','https://www.indisa.cl/blog/convenio'),
    ('red_davila','Red Dávila','beta','https://www.davila.cl/novedades/convenio'),
])
def test_pending_source_quality_gate_blocks_fetch_and_assessment(monkeypatch,slug,name,processor,url):
    from radar_salud import beta_sources, public_source_pipeline
    raw=RawItem(slug,'Nueva capacidad y convenio de atención',url,name,'corporate','2026-10-02',
        metadata={'source_quality_gate':'pending_90_day_audit','market_role':'provider','publication_date_source':'verified_article_header'})
    for module in (beta_sources,public_source_pipeline):
        monkeypatch.setattr(module,'fetch_html',lambda _:pytest.fail('Pending quality gate must block article fetch'))
    monkeypatch.setattr(public_source_pipeline,'analyze_news',lambda **kw:pytest.fail('Pending quality gate must block paid assessment'))
    process=public_source_pipeline.process_corporate_news if processor=='corporate' else beta_sources.process_curated_beta_source
    with pytest.raises(DeferredProcessing,match='source quality gate not passed: pending_90_day_audit'):
        process(raw,{'slug':slug,'source_type':'corporate'})


def test_hospital_pharmacy_and_lab_capacity_does_not_create_pharma_industry_scope(monkeypatch):
    from radar_salud import beta_sources, llm_analysis
    title='Clínica Andes Salud incorpora nueva capacidad hospitalaria'
    raw=RawItem('andes_salud',title,'https://www.andessalud.cl/novedades/capacidad/','Andes Salud','corporate','2026-10-02',
        metadata={'market_role':'provider','publication_date_source':'verified_article_header','source_quality_gate':'passed'})
    html=f'<h1>{title}</h1><div>octubre 2, 2026</div><p>'+'El nuevo hospital incorpora 94 camas, farmacia y laboratorio para diagnóstico clínico. '*8+'</p>'
    monkeypatch.setattr(beta_sources,'fetch_html',lambda _:html)
    monkeypatch.setattr(llm_analysis,'analyze_news',lambda **kw:{'relevance_score':86,
        'what_happened':'La nueva clínica incorpora camas, farmacia y laboratorio como parte de su capacidad hospitalaria.',
        'why_it_matters':'Amplía la oferta hospitalaria y diagnóstica para pacientes de la región.'})
    row=beta_sources.process_curated_beta_source(raw,{'base_confidence':80})
    assert row['scopes']==['Prestadores']
