from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace

from radar_salud.weekly_freshness import freshness_gate, reviewed_weekly
from radar_salud.free_value import build_free_value, rank_weekly_candidates
from radar_salud import weekly_insight_v2 as pipeline

ROOT = Path(__file__).resolve().parents[1]

def approved():
    payload=json.loads((ROOT/'data/weekly_insight/editorial_approved.json').read_text())
    payload['weekly_insight'].update(event_date='2026-10-07',freshness_anchor_date='2026-10-07',expires_on='2026-10-14')
    return payload

def test_expired_september_insight_never_revives_from_generation_date():
    old = json.loads((ROOT/'data/weekly_insight/archive/2026-09-14.json').read_text())
    old['generated_at'] = '2026-10-11T03:00:00Z'
    old['audit'] = {'verdict':'PASS','editorial_business_review_pass':True}
    assert reviewed_weekly(old, date(2026,10,11)) is None
    assert not freshness_gate(old['weekly_insight'], date(2026,10,11))['eligible']

def test_seven_calendar_dates_and_chile_expiry_boundary():
    payload = approved()
    assert reviewed_weekly(payload, date(2026,10,13))
    assert reviewed_weekly(payload, date(2026,10,14)) is None
    assert reviewed_weekly(payload, date(2026,10,6)) is None
    result=build_free_value({'signals':[payload['weekly_insight']]},{'themes':[]},today=date(2026,10,11),approved_payload=payload)
    assert result['weekly_insight']['id']==payload['weekly_insight']['id']
    expired=build_free_value({'signals':[]},{'themes':[]},today=date(2026,10,14),approved_payload=payload)
    assert expired['weekly_insight'] is None

def test_model_pass_without_business_review_and_invalid_dates_fail_closed():
    payload = approved()
    payload['audit'].pop('editorial_business_review_pass')
    assert reviewed_weekly(payload,date(2026,10,11)) is None
    for day in [None,'not-a-date','2026-10-32','2026-11-01']:
        bad=approved();bad['weekly_insight']['freshness_anchor_date']=day
        assert reviewed_weekly(bad,date(2026,10,11)) is None

def test_fresh_news_cannot_rejuvenate_old_normative_anchor():
    row={'title':'Circular y noticia','source_name':'Fuente','source_url':'https://example.org/act',
         'event_date':'2026-10-09','freshness_anchor_date':'2026-10-02',
         'publication_gate_reason':'ok','publication_ready_score':100,'source_quality_score':100,
         'what_happened':'Obligación','why_it_matters':'Proceso','radar_score':100}
    assert rank_weekly_candidates([row],[],date(2026,10,11))==[]

def test_structurally_valid_model_output_remains_a_draft(monkeypatch):
    row={'title':'Cambio material','source_name':'Fuente','source_url':'https://example.org/source',
         'event_date':'2026-10-07','publication_gate_reason':'ok','publication_ready_score':100,
         'source_quality_score':100,'radar_score':100,'regulatory_impact_score':100,
         'actionability_score':100,'what_happened':'Cambio','why_it_matters':'Proceso',
         'event_type':'REGULATION'}
    output={k:['Contenido sustentado'] for k in pipeline.REQUIRED};output['source_refs']=[row['source_url']]
    monkeypatch.setattr(pipeline,'call_json',lambda *a,**kw:SimpleNamespace(output=output,model='stub',fallback_used=False,estimated_cost_usd=0,response_id='test'))
    result=pipeline.run_weekly_pipeline({'signals':[row]},as_of=date(2026,10,11))
    assert result['status']=='editorial_review_required'
    assert result['weekly_insight'] is None
    assert result['draft_weekly_insight']
    assert reviewed_weekly(result,date(2026,10,11)) is None
