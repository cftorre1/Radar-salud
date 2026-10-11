import json
from pathlib import Path
from zipfile import ZipFile
from datetime import date
import pytest
from radar_salud.cmf_sources import parse_actor, parse_essential_index, financial_documents, financial_results, essential_query, classify_primary

ROOT=Path(__file__).resolve().parents[1]


def test_native_cmf_inventory_keeps_inactive_parent_separate():
    with ZipFile(ROOT/'data/audits/source_expansion/native_initial.zip') as z:
        rs=json.loads(z.read('receipts.json'))['receipts'];actors=[]
        for r in rs:
            if r['package']=='cmf' and r['kind']=='1':
                actors.append(parse_actor(z.read(r['body_file']).decode(),source_url=r['url'],sha256=r['sha256'],fetched_at=r['completed_at']))
    assert len(actors)==5
    assert [a['rut'] for a in actors if a['issuer_registration_status']!='Vigente']==['96528990-9']
    assert all(a['subsidiary_entity_ids']==[] for a in actors)


def test_real_essential_form_results_and_stable_dedupe():
    actors=json.loads((ROOT/'data/entities/cmf_reporting_actors.json').read_text())['actors']
    documents=[]
    with ZipFile(ROOT/'data/audits/source_expansion/native_forms.zip') as z:
        for r in json.loads(z.read('receipts.json'))['receipts']:
            if r['kind']!='essential_90d':continue
            a=next(a for a in actors if 'rut='+a['rut'].split('-')[0]+'&' in r['url'])
            html=z.read(r['body_file']).decode()
            parsed=parse_essential_index(html,actor=a,source_url=r['url'],query_start='2026-07-14',query_end='2026-10-11')
            assert parsed['coverage_complete']
            assert parsed==parse_essential_index(html,actor=a,source_url=r['url'],query_start='2026-07-14',query_end='2026-10-11')
            documents+=parsed['documents']
    assert len(documents)==9 and len({d['record_id'] for d in documents})==9
    assert sum(d['published_at']>='2026-09-12' for d in documents)==3
    assert all(d['event_date'] is None and not d['subsidiary_attribution'] for d in documents)


def test_calendar_and_empty_menu_are_not_coverage():
    actor={'rut':'93930000-7','entity_id':'cl:rut:93930000-7','legal_name':'CLINICA LAS CONDES S.A.'}
    assert not parse_essential_index('<p>Hechos Esenciales</p><form>Fecha desde</form>',actor=actor,source_url='https://www.cmfchile.cl/',query_start='2026-07-14',query_end='2026-10-11')['coverage_complete']
    with pytest.raises(ValueError,match='calendar'):
        financial_documents('<table><tr><td>27/11/2026</td></tr></table>',actor=actor,source_url='https://www.cmfchile.cl/?pestania=101',reporting_period='2026-09',sha256='a'*64)


def test_native_ifrs_results_preserve_actual_columns_and_unit():
    actors=json.loads((ROOT/'data/entities/cmf_reporting_actors.json').read_text())['actors']
    with ZipFile(ROOT/'data/audits/source_expansion/native_forms.zip') as z:
        rs=json.loads(z.read('receipts.json'))['receipts'];r=next(r for r in rs if r['kind']=='financial_period' and 'rut=93930000' in r['url'] and 'mm=06' in r['url'])
        a=next(a for a in actors if a['rut']=='93930000-7')
        obs=financial_results(z.read(r['body_file']).decode(),actor=a,source_url=r['url'],sha256=r['sha256'],reporting_period='2026-06')
    ytd=next(o for o in obs if o['metric_id']=='revenue' and o['period_start']=='2026-01-01')
    assert ytd['value']==98469698 and ytd['unit']=='thousand_CLP'
    assert ytd['period_end']=='2026-06-30' and ytd['published_at'] is None
    assert all(o['entity_id']=='cl:rut:93930000-7' for o in obs)


def test_materiality_never_publishes_parent_fact_to_insurer():
    assert classify_primary('ILC aumento de capital para financiar adquisiciones')['material'] is True
    assert classify_primary('Citación a junta ordinaria de accionistas')['disposition']=='rejected'
    assert classify_primary('Otros')['disposition']=='deferred'
    url,body=essential_query('94139000','ILC',date(2026,7,14),date(2026,10,11))
    assert 'pestania=25' in url and 'aa=2026' in body


def test_review_cannot_reuse_changed_document_or_cross_issuer():
    from radar_salud.cmf_sources import apply_verified_primary
    review=json.loads((ROOT/'config/cmf_verified_events_2026_10_11.json').read_text())['records'][0]
    doc={key:review[key] for key in ['official_document_number','issuer_entity_id','published_at']}
    doc['primary_sha256']='0'*64
    assert not apply_verified_primary(doc,review) and 'verified_event' not in doc
    doc['primary_sha256']=review['primary_sha256'];doc['issuer_entity_id']='cl:rut:94139000-5'
    with pytest.raises(ValueError,match='identity'):apply_verified_primary(doc,review)
    doc['issuer_entity_id']=review['issuer_entity_id']
    assert apply_verified_primary(doc,review) and doc['disposition']=='deferred'
    assert doc['verified_event']['amount']['value']==80119759016
