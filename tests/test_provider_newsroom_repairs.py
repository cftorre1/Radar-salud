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


def test_provider_jsonld_requires_own_url_and_ignores_modified():
    from radar_salud.beta_sources import _ProviderPublication
    import json
    url='https://www.davila.cl/novedades/current'
    schema={'@type':'NewsArticle','url':url,'datePublished':'2026-10-05','dateModified':'2026-10-11'}
    def parser(value):
        p=_ProviderPublication(url);p.feed('<h1>Current article</h1><script type="application/ld+json">'+json.dumps(value)+'</script>');return p
    assert parser(schema).publication()==('2026-10-05','url_associated_jsonld_datePublished')
    schema['url']=url+'/other'
    assert parser(schema).publication()[0] is None
    schema.pop('datePublished');schema['url']=url
    assert parser(schema).publication()[0] is None


def test_redsalud_capacity_lists_are_read_without_related_cards():
    from radar_salud.public_source_pipeline import _RedSaludArticle
    p=_RedSaludArticle();p.feed('<h1>New urgency unit</h1><p>Operational change.</p><ul><li>26 boxes</li><li>874 m²</li></ul><h2>Conoce otras de nuestras noticias</h2><p>Unrelated investment.</p>');p.finish()
    assert '26 boxes' in p.body and '874 m²' in p.body
    assert 'Unrelated investment' not in p.body


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


@pytest.mark.parametrize('actor',['Roche','Sanofi','Merck','Biomed'])
def test_provider_agreement_with_named_laboratory_keeps_pharma_scope(monkeypatch,actor):
    from radar_salud import beta_sources, llm_analysis
    title=f'Andes Salud firma convenio con Laboratorio {actor}'
    raw=RawItem('andes_salud',title,'https://www.andessalud.cl/novedades/convenio/','Andes Salud','corporate','2026-10-02',
        metadata={'market_role':'provider','publication_date_source':'verified_article_header','source_quality_gate':'passed'})
    html=f'<h1>{title}</h1><div>octubre 2, 2026</div><p>'+f'El convenio de inversión con Laboratorio {actor} amplía la red de prestaciones y capacidad. '*8+'</p>'
    monkeypatch.setattr(beta_sources,'fetch_html',lambda _:html)
    monkeypatch.setattr(llm_analysis,'analyze_news',lambda **kw:{'relevance_score':86,
        'what_happened':f'Andes Salud suscribió un convenio de inversión con Laboratorio {actor} para ampliar prestaciones.',
        'why_it_matters':'El acuerdo conecta una red de prestadores y un actor farmacéutico en un nuevo proyecto.'})
    row=beta_sources.process_curated_beta_source(raw,{'base_confidence':80})
    assert row['scopes']==['Prestadores','Farma / medicamentos']
def test_redsalud_canonical_header_resolves_old_teaser_without_using_update(monkeypatch):
    from radar_salud.models import RawItem
    from radar_salud import public_source_pipeline as pipeline
    from radar_salud.sources import load_sources,source_index
    from pathlib import Path
    title='Nueva unidad clínica de alta complejidad'
    raw=RawItem('redsalud',title,'https://www.redsalud.cl/noticias/old-teaser','RedSalud','corporate','2026-08-27',metadata={'listing_date':'2026-08-27'})
    canonical='https://www.redsalud.cl/observatorio/noticias/nueva-unidad'
    html=f'<link rel="canonical" href="{canonical}"><script type="application/ld+json">'+__import__('json').dumps({'@type':'NewsArticle','url':canonical,'headline':title,'datePublished':'2026-09-04','dateModified':'2026-10-07'})+f'</script><span class="coh-inline-element coh-ce-9ca7c0c5">4 Sep 2026</span><span>Comparte</span><h1>{title}</h1><p>'+('Nueva capacidad de atención documentada. '*40)+'</p>'
    monkeypatch.setattr(pipeline,'fetch_html',lambda _:html)
    monkeypatch.setattr(pipeline,'analyze_news',lambda **kw:{'relevance_score':86,'reason':'Nueva capacidad hospitalaria documentada.',
        'what_happened':'El prestador abrió una nueva unidad hospitalaria de alta complejidad con capacidad adicional.',
        'why_it_matters':'Amplía la oferta para pacientes del sistema público y privado con necesidades especializadas.'})
    cfg=source_index(load_sources(Path('config/sources.json')))['redsalud']
    assert pipeline.process_corporate_news(raw,cfg)['event_date']=='2026-09-04'
    assert raw.metadata['listing_date_before_canonical_verification']=='2026-08-27'
    assert raw.metadata['publication_date_source']=='canonical_article_publication'
    monkeypatch.setattr(pipeline,'fetch_html',lambda _:html.replace('4 Sep 2026','7 Oct 2026'))
    import pytest
    from radar_salud.processing import DeferredProcessing
    with pytest.raises(DeferredProcessing,match='dates disagree'):pipeline.process_corporate_news(raw,cfg)


def test_davila_official_chain_preserves_threshold_and_rejects_unverified_support(monkeypatch):
    from radar_salud import beta_sources,llm_analysis
    title='Programa Enlace: treinta cirugías ejecutadas'
    support_title='Programa Enlace: compromiso de quinientos pacientes'
    url='https://www.davila.cl/novedades/operativo'
    support_url='https://www.davila.cl/novedades/firma'
    evidence={'url':support_url,'title':support_title,'publication_date':'2026-08-20','relationship':'programme_announcement_before_execution'}
    raw=RawItem('red_davila',title,url,'Red Dávila','corporate','2026-08-24',metadata={'market_role':'provider','source_quality_gate':'passed','publication_date_source':'verified_article_header','supporting_official_sources':[evidence]})
    def fetch(target):
        primary=target==url
        return f'<span>Novedades {"24" if primary else "20"}/08/2026</span><h1>{title if primary else support_title}</h1><p>'+('Programa Enlace: se ejecutaron treinta cirugías con cinco pabellones. '*4 if primary else 'El Programa Enlace compromete quinientos pacientes en diez jornadas y diez meses. '*4)+'</p>'
    monkeypatch.setattr(beta_sources,'fetch_html',fetch)
    inputs=[]
    monkeypatch.setattr(llm_analysis,'analyze_news',lambda **kw:inputs.append(kw['text']) or {'relevance_score':74,'reason':'Convenio cuantificado, impacto acotado territorialmente.', 'what_happened':'El prestador ejecutó treinta cirugías bajo un convenio de diez meses con la red pública.', 'why_it_matters':'Aporta capacidad privada para resolver espera odontológica en un hospital de referencia.'})
    assert beta_sources.process_curated_beta_source(raw,{}) is None
    assert 'quinientos' in inputs[0] and 'treinta' in inputs[0]
    assert raw.metadata['editorial_assessment']['minimum_relevance']==75
    evidence['publication_date']='2026-08-21'
    with pytest.raises(DeferredProcessing,match='publication/programme mismatch'):beta_sources.process_curated_beta_source(raw,{})
    assert len(inputs)==1

