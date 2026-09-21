from src.radar_salud.models import RawItem
from src.radar_salud.minsal_pipeline import process_minsal_detail
from src.radar_salud.scouts import MinsalNewsScout

CFG={"slug":"minsal","name":"Ministerio de Salud","source_type":"official","system_domain":"PUBLIC_HEALTH","base_confidence":100,"default_category":"Mercado"}

def _raw(title,url='https://www.minsal.cl/test/'):
    return RawItem('minsal',title,url,'Ministerio de Salud','official')

def test_minsal_scout_discovers_news_and_ignores_navigation():
    html='''<a href="https://www.minsal.cl/category/noticias/page/2/">Antes</a>
    <a href="https://www.minsal.cl/nuevo-hospital-x/">Ministerio anuncia nuevo hospital de alta complejidad para Arica</a>'''
    items=MinsalNewsScout().discover_from_html(html)
    assert len(items)==1
    assert 'hospital' in items[0].title.lower()

def test_compin_fiscalization_is_regulatory_and_social_security():
    html='''<h1>Plan de fiscalización de COMPIN reduce grandes emisores de licencias médicas</h1>
    <p>Septiembre 10, 2026</p><p>COMPIN reforzó la fiscalización y sanciones sobre licencias médicas y grandes emisores.</p>'''
    s=process_minsal_detail(_raw('Plan COMPIN'),html,CFG)
    assert s.category == 'Regulación & Legal'
    assert s.system_domain == 'SOCIAL_SECURITY'
    assert s.regulatory_impact_score >= 80
    assert 'compin' in s.watch_tags

def test_hospital_investment_is_provider_infrastructure():
    html='''<h1>Ministerio de Salud firma compra de terrenos para expansión del Hospital Carlos Van Buren</h1>
    <p>Septiembre 1, 2026</p><p>La inversión supera los $7.700 millones y considera un nuevo Centro de Diagnóstico y Tratamiento de 26 mil metros cuadrados.</p>'''
    s=process_minsal_detail(_raw('Expansión Hospital Van Buren'),html,CFG)
    assert s.category == 'Prestadores'
    assert s.system_domain == 'HEALTH_PROVIDERS'
    assert s.subcategory == 'Infraestructura'
    assert s.economic_impact_score >= 65

def test_digital_transformation_gets_market_signal():
    html='''<h1>Minsal inicia nueva etapa de transformación digital con siete proyectos estratégicos</h1>
    <p>Septiembre 2, 2026</p><p>Receta Digital Nacional, interoperabilidad de datos clínicos y salud digital forman parte de las iniciativas.</p>'''
    s=process_minsal_detail(_raw('Transformación digital Minsal'),html,CFG)
    assert s.category == 'Mercado'
    assert s.subcategory == 'Transformación digital'
    assert 'salud digital' in s.watch_tags
