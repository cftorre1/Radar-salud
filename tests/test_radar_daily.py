from radar_salud.models import Signal
from radar_salud.personalization import DEFAULT_PROFILES
from radar_salud.radar_daily import select_daily, build_whatsapp_daily


def mk(title, category, domain, score=80, conf=95):
    return Signal(title=title, source_name='X', source_type='official', source_url='u'+title, category=category, subcategory='x', system_domain=domain, what_happened=title, radar_score=score, confidence_score=conf, why_it_matters='Importa.')

def test_limits_world_and_local():
    sigs=[mk(f'L{i}','Mercado','HEALTH_INSURANCE',90-i) for i in range(8)] + [mk(f'W{i}','Radar Mundo','GLOBAL_HEALTH',90-i) for i in range(4)]
    selected=select_daily(sigs, DEFAULT_PROFILES['isapre'])
    assert len([x for x in selected if x.signal.category=='Radar Mundo']) == 2
    assert len([x for x in selected if x.signal.category!='Radar Mundo']) == 5

def test_whatsapp_mentions_watch_exception():
    out=build_whatsapp_daily([mk('L','Aseguramiento','HEALTH_INSURANCE',95)], DEFAULT_PROFILES['isapre'], '2026-09-21')
    assert 'Watch específicos' in out
    assert 'Fuente:' in out
