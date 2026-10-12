"""Strict final-reader tests use actual immutable zero-observation evidence."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import pytest
from scripts import verify_pulso_completed_zero_observations as final
from scripts import retain_pulso_zero_original as original

ROOT=Path(__file__).parents[1]

@pytest.fixture(scope='module')
def actual():
    read=lambda p:json.loads(subprocess.check_output(['git','show',final.SECOND+':'+p],cwd=ROOT))
    queue=read('data/state/pending_queue.json')
    budget=next(v for v in queue.values() if v.get('raw',{}).get('url')==final.MISSING)
    report=read('data/audits/pulso_runtime_2026_10_11.json')
    row=next(r for r in report['matrix'] if r['url']==original.URL)
    data=(ROOT/'tests/fixtures/pulso_zero_observation_real'/(original.SHA+'.html.gz')).read_bytes()
    return dict(compare=read(final.helper.DEFAULT_RESULT),quality=read(final.helper.DEFAULT_QA),
        budget=budget,queue=queue,traces=row['current_discovery_trace'],captured_original=original.verify(data))

def test_exact_paid_body_original_byline_and_already_rejected_negative_are_preserved(actual):
    result=final.bounded_result(**actual)
    assert result['verdict']=='PASS'
    assert result['publication_approved'] is False
    assert result['AI_calls']==result['HTTP_calls']==result['state_changes']==0
    assert result['original_second_directed_QA_FAIL_preserved']
    assert [r['score'] for r in result['corrected_conditions']]==[76,5]
    assert all(r['disposition']=='rejected' for r in result['corrected_conditions'])

@pytest.mark.parametrize('change',['other_missing','changed_primary','additional_QA','budget_published',
    'budget_date','budget_body','budget_gate','paid_body','paid_gate','paid_date','paid_status',
    'current_body','current_date','current_HTML','captured_body'])
def test_no_other_consumer_or_editorial_change_is_accepted(actual,change):
    value=deepcopy(actual)
    if change=='other_missing':value['compare']['findings'][0]['missing'].append('https://www.latercera.com/pulso/noticia/another/')
    elif change=='changed_primary':value['compare']['findings'][0]['changed'].append(final.MISSING)
    elif change=='additional_QA':value['quality']['findings'].append(dict(domain='processing',code='new_model_call'))
    elif change=='budget_published':value['budget']['status']='published'
    elif change=='budget_date':value['budget']['raw']['event_date']='2026-10-12'
    elif change=='budget_body':value['budget']['raw']['metadata']['page_text']+=' fabricated health investment'
    elif change=='budget_gate':value['budget']['raw']['metadata']['editorial_assessment']['threshold']=71
    elif change.startswith('paid'):
        item=next(v for v in value['queue'].values() if v.get('raw',{}).get('url')==original.URL)
        if change=='paid_body':item['raw']['metadata']['page_text']='erased original'
        elif change=='paid_gate':item['raw']['metadata']['editorial_assessment']['relevance_score']=72
        elif change=='paid_date':item['raw']['metadata']['publication_date']='2026-10-12'
        else:item['status']='published'
    elif change=='current_body':value['traces'][0]['article_body_sha256']='a'*64
    elif change=='current_date':value['traces'][0]['publication_date']='2026-10-12'
    elif change=='current_HTML':value['traces'][0]['html_sha256']='b'*64
    else:value['captured_original']['body']+=' unverified material change'
    with pytest.raises(ValueError):final.bounded_result(**value)

def test_current_HTML_is_exact_original_capture_not_reconstructed_or_recaptured():
    data=(ROOT/'tests/fixtures/pulso_zero_observation_real'/(original.SHA+'.html.gz')).read_bytes()
    assert original.verify(data)['body_characters']==3449
    with pytest.raises(AssertionError):original.verify(data+b'corrupted')
