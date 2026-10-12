"""Qualification cannot modify dated identities or invent a fresh cadence anchor."""
import copy
import json
from pathlib import Path
import pytest
from scripts.discover_global_sources import coverage_contract_id
from scripts.requalify_global_coverage import assert_coverage_projection,END

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture
def qualification():
    # An immutable captured metadata inventory, not a projection made by this test.
    path=ROOT/'data/audits/global_source_recovery_2026_10_11/runs/38153425336/metadata_requalification/38155456354/inventory.json'
    before=json.loads(path.read_text());after=copy.deepcopy(before)
    after['mode']='projection_replay';after['network_requests']=0
    for route in after['routes']:
        if not route.get('date_partitions'):continue
        for index,page in enumerate(route['pages']):
            if page['items'] or not index:continue
            prior=route['pages'][index-1];pager=prior.get('numbered_native_pager',{})
            if pager.get('terminal'):
                page['clamped_empty_native_pager']={'requested_page':pager['current']+1,'clamped_current':pager['current'],'maximum':pager['maximum'],'terminal':True,'previous_page_url':prior['url']}
        for part in route['date_partitions']:
            if part['stop_reason']=='date_partition_empty_unverified':part.update(archive_complete=True,stop_reason=END)
        route.update(archive_complete=True,stop_reason='verified_date_partition_coverage')
    h=after['source_health']['paho'];h.update(coverage_status='complete',outcome='READY_FOR_INTEGRATION',coverage_completeness='complete',window_completeness={'30':'complete_on_declared_surfaces','90':'complete_on_declared_surfaces'},source_quality_disposition='pass_data',coverage_contract_id=coverage_contract_id(json.loads((ROOT/'config/global_discovery.json').read_text()),'paho'))
    h['boundary_evidence']=[{'section':r['route']['section'],'stop':r['stop_reason'],'pages':len(r['pages'])} for r in after['routes'] if r['route']['source']=='paho']
    return before,after

def test_captured_end_qualification_preserves_all_items_dates_receipts_and_counts(qualification):
    a,b=qualification
    assert len(assert_coverage_projection(a,b))==23
    assert a['items']==b['items'] and b['source_health']['paho']['counts']=={'30':185,'90':530}

@pytest.mark.parametrize('change',[
    lambda b:b['items'][0].update(published_at='2026-10-11'),
    lambda b:b['source_health']['paho']['counts'].update({'90':999}),
    lambda b:b['source_health']['paho'].update(recurrent_operation_proven=True),
    lambda b:b['source_health']['paho'].update(coverage_contract_id='invented'),
    lambda b:b['source_health']['reuters']['counts'].update({'90':999}),
    lambda b:b.update(network_requests=1),
    lambda b:b['routes'][3]['pages'][0]['capture'].update(body_sha256='invented'),
    lambda b:b['routes'][3]['date_partitions'][1].update(query_from='1900-01-01'),
    lambda b:b['routes'][3]['pages'].pop(),
])
def test_qualification_rejects_date_count_cadence_rights_transport_and_partition_drift(qualification,change):
    a,b=qualification;change(b)
    with pytest.raises(ValueError):assert_coverage_projection(a,b)
