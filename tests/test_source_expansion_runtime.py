import importlib.util
import json
from datetime import date
from pathlib import Path
from zipfile import ZipFile
import pytest
from radar_salud.market_sources import Captures, collect_cmf
from radar_salud.market_sources import collect_dipres
from radar_salud.market_intelligence import export_views
from radar_salud.cmf_sources import parse_shareholders

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def captures(tmp_path_factory):
    path=tmp_path_factory.mktemp('native')
    with ZipFile(ROOT/'data/audits/source_expansion/native_validated.zip') as archive:
        archive.extractall(path)
    return Captures(path)


def test_primary_hash_bound_review_groups_updates_without_false_close(captures,tmp_path,monkeypatch):
    monkeypatch.setattr('radar_salud.primary_documents.extract_primary_pdf',lambda content:('aumento de capital '+('x'*100),'fixture'))
    health=collect_cmf(captures,tmp_path)
    docs=json.loads((tmp_path/'data/market/cmf_disclosures.json').read_text())['documents']
    events=json.loads((tmp_path/'data/market/cmf_events.json').read_text())['events']
    assert health['unique_items']==9 and health['items_material']==7
    assert health['rejected']==2 and health['deferred']==7 and health['published']==0
    assert len(events)==5
    red=next(e for e in events if 'vida_camara' in e['event_id'])
    assert len(red['primary_disclosures'])==4 and red['stage']=='shareholders_meeting_called'
    assert red['scheduled_meeting_date']=='2026-10-13' and red['effective_date'] is None
    assert red['amount']['kind']=='proposed_non_cash_capital_increase'
    bionet=next(e for e in events if 'bionet' in e['event_id'])
    assert bionet['stage']=='non_binding_offer_accepted_subject_to_conditions'
    assert bionet['amount']['currency']=='UF' and not any(d['subsidiary_attribution'] for d in docs)
    assert all(d.get('verified_event') for d in docs)
    # A later partial native query must preserve the stock and its first detection.
    before={d['record_id']:d['detected_at'] for d in docs}
    partial=Captures(captures.path)
    partial.receipts=[r for r in captures.receipts if 'rut=93930000' in r['url'] and r['kind']=='1']
    collect_cmf(partial,tmp_path)
    remaining=json.loads((tmp_path/'data/market/cmf_disclosures.json').read_text())['documents']
    assert before=={d['record_id']:d['detected_at'] for d in remaining}


def test_shareholder_control_keeps_original_reporting_period(captures):
    r=next(r for r in captures.receipts if r['kind']=='reporting_5' and 'rut=76020458' in r['url'])
    owners=parse_shareholders(captures.html(r),source_url=r['url'],sha256=r['sha256'])
    ilc=next(o for o in owners if 'CONSTRU' in o['name'])
    assert ilc['ownership_pct']==100 and ilc['reported_period']=='2025-12'


def test_partial_budget_poll_retains_valid_stock_and_does_not_claim_absence(captures,tmp_path):
    path=tmp_path/'data/market';path.mkdir(parents=True)
    original=json.loads((ROOT/'data/market/dipres_health_budget.json').read_text())
    (path/'dipres_health_budget.json').write_text(json.dumps(original))
    partial=Captures(captures.path)
    partial.receipts=[r for r in captures.receipts if r['package']=='dipres' and r['kind']=='budget_index']
    health=collect_dipres(partial,tmp_path)
    retained=json.loads((path/'dipres_health_budget.json').read_text())
    assert retained['records']==original['records']
    assert retained['material_variations']==original['material_variations']
    assert retained['document_ledger']==original['document_ledger']
    assert health['items_recent'] is None and not health['coverage_complete']


def test_periodic_queries_cross_year_without_freezing_2026():
    spec=importlib.util.spec_from_file_location('probe',ROOT/'scripts/probe_source_expansion.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    seeds=json.loads((ROOT/'config/source_expansion_runtime.json').read_text())['seeds']
    changed=module.period_seeds(seeds,date(2027,1,20))
    body=next(s['post'] for s in changed if s['kind']=='essential_90d')
    assert 'dd2=20' in body and 'aa2=2027' in body and 'aa=2026' in body
    assert all('aa=2026' in s['url'] for s in changed if s['kind']=='financial_period')


def test_consumers_do_not_compare_parent_results_or_calendar_years(tmp_path):
    path=tmp_path/'data/market';path.mkdir(parents=True)
    common=dict(entity_id='cl:rut:93930000-7',metric_id='revenue',unit='thousand_CLP',reporting_perimeter='consolidated',source_url='https://www.cmfchile.cl/statement')
    observations=[dict(common,value=120,period_start='2028-01-01',period_end='2028-06-30'),
                  dict(common,value=100,period_start='2027-01-01',period_end='2027-06-30'),
                  dict(common,entity_id='cl:rut:94139000-5',value=999,period_start='2027-01-01',period_end='2027-06-30')]
    (path/'cmf_financials.json').write_text(json.dumps({'observations':observations}))
    # Empty portfolio must produce an explicit empty data view, not invented denominators.
    view=export_views(tmp_path)
    assert len(view['trend']['cmf_same_issuer_results'])==1
    assert view['trend']['cmf_same_issuer_results'][0]['pct_change']==20
    assert view['benchmark']['cmf']['cross_entity_ranking'] is False
    assert json.loads((path/'signal_candidates.json').read_text())['candidates']==[]


def test_parser_failure_replaces_canonical_health_without_claiming_zero_content(captures,tmp_path,monkeypatch):
    import sys
    from radar_salud.market_sources import main
    capture=tmp_path/'capture';capture.mkdir()
    r=next(r for r in captures.receipts if r['kind']=='registry')
    body=capture/r['body_file'];body.parent.mkdir(parents=True);body.write_bytes(captures.body(r))
    (capture/'receipts.json').write_text(json.dumps({'receipts':[r]}))
    root=tmp_path/'stock';(root/'data').mkdir(parents=True)
    (root/'data/source_health.json').write_text(json.dumps({'sources':{'sis_isapre_universe':{'status':'ok'}}}))
    monkeypatch.setattr(sys,'argv',['market_sources','--capture-dir',str(capture),'--output-root',str(root),'--only','isapres'])
    with pytest.raises(SystemExit) as exc:main()
    assert exc.value.code==1
    sources=json.loads((root/'data/source_health.json').read_text())['sources']
    assert 'market_isapres' not in sources
    evidence=sources['sis_isapre_universe']
    assert evidence['status']=='error' and evidence['technical_status']=='error'
    assert evidence['parse_errors']==1 and evidence['items_discovered'] is None
    assert evidence['items_recent'] is None and not evidence['coverage_complete']
