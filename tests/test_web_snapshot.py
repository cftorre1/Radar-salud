import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('export_web_snapshot', Path('scripts/export_web_snapshot.py'))
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def sig(title, score=65, event='2026-09-07', facts=None):
    return {
      'title':title,'source_name':'Superintendencia de Salud','source_url':'https://example.com',
      'category':'Aseguramiento','event_date':event,'radar_score':score,'confidence_score':100,
      'validation_status':'automatic','key_facts':facts or ['Información actualizada a julio 2026.'],
      'what_happened':'x','why_it_matters':'y'
    }


def test_monthly_isapre_releases_are_grouped():
    items=[
      sig('Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE – año 2026'),
      sig('Estadística Mensual de Movilidad de Cartera de Cotizantes del Sistema ISAPRE a Nivel Regional – Año 2026',68),
      sig('Estadística Mensual de Suscripciones y Desahucios del Sistema ISAPRE – año 2026',65),
    ]
    out=mod.curate(items)
    assert len(out)==1
    assert out[0]['grouped_count']==3
    assert 'Actualización mensual del sistema Isapre' in out[0]['title']


def test_old_items_are_hidden_from_frontpage():
    items=[sig('Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE – año 2026', event='2026-09-07'),
           sig('Estadísticas Financieras del Sistema ISAPRE a marzo 2026', event='2026-07-07')]
    out=mod.curate(items)
    assert all(x['event_date']!='2026-07-07' for x in out)
