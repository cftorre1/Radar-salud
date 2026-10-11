import copy
import json
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from scripts.occupational_inventory import reconcile, refresh_item
from radar_salud.models import RawItem
from radar_salud.pending_queue import fingerprint

URL='https://ist.cl/verified-change/'

def raw(body='new capacity'):
    return RawItem('ist','Capacity',URL,'IST','news','2026-10-10',body,
                   {'page_text':body,'market_role':'mutuality','materiality_accepted':True})

class Loader:
    records={}

def setup(tmp_path, old, status='rejected'):
    state=tmp_path/'data/state';state.mkdir(parents=True)
    item={'raw':asdict(old),'source':'ist','status':status,'reason':'old assessment',
          'editorial_assessment':{'score':65},'attempts':1,'lane':'BACKFILL','detected_at':'2026-10-01T00:00:00+00:00'}
    (state/'pending_queue.json').write_text(json.dumps({fingerprint(old):item}))
    (tmp_path/'config').mkdir();(tmp_path/'config/sources.json').write_text('[{"slug":"ist"}]')
    history=tmp_path/'data/history';history.mkdir();(history/'superintendencia_signals.json').write_text('[]')
    return item

def report(item=None):
    return {'ist':{'raw_items':[item] if item else [],'rows':[{'url':URL,'within_90_days':True,
        'status':'candidate' if item else 'pending','reason':'detail_timeout'}]}}

def test_changed_material_input_reassessed_and_fresh_raw_persisted(tmp_path,monkeypatch):
    setup(tmp_path,raw('old advice'))
    calls=[]
    def process(item,cfg):
        calls.append(item.raw_text);item.metadata['editorial_assessment']={'score':72}
        item.metadata['publication_rejection_reason']='below threshold';return None
    monkeypatch.setattr('scripts.occupational_inventory.process_curated_beta_source',process)
    reports=report(raw())
    reconcile(tmp_path,reports,Loader(),apply=True)
    saved=json.loads((tmp_path/'data/state/pending_queue.json').read_text())[fingerprint(raw())]
    assert calls==['new capacity'] and saved['raw']['raw_text']=='new capacity'
    assert saved['editorial_assessment']['score']==72
    assert saved['revisions'][0]['editorial_assessment']['score']==65
    assert reports['ist']['rows'][0]['editorial_input_changed']


def test_capture_refresh_preserves_rejection_without_repeat_analysis(tmp_path,monkeypatch):
    old=raw();setup(tmp_path,old)
    new=raw();new.metadata['capture_evidence']={'sha256':'fresh'}
    monkeypatch.setattr('scripts.occupational_inventory.process_curated_beta_source',lambda *a: (_ for _ in ()).throw(AssertionError('repeat AI')))
    reports=report(new);reconcile(tmp_path,reports,Loader(),apply=True)
    saved=json.loads((tmp_path/'data/state/pending_queue.json').read_text())[fingerprint(new)]
    assert saved['raw']['metadata']['capture_evidence']['sha256']=='fresh'
    assert reports['ist']['rows'][0]['editorial_score']==65


def test_missing_current_capture_preserves_previous_publication(tmp_path):
    setup(tmp_path,raw(),status='published')
    reports=report();reconcile(tmp_path,reports,Loader(),apply=True)
    row=reports['ist']['rows'][0]
    assert row['alicanto_status']=='published' and row['current_capture_gap']=='detail_timeout'
    assert reports['ist']['reconciliation']['states']['published']==1


def test_shared_newsroom_foreign_role_never_counts_as_published(tmp_path):
    setup(tmp_path,raw(),status='published')
    reports=report()
    reports['ist']['rows'][0].update(status='excluded_role',reason='other publisher lane')
    reconcile(tmp_path,reports,Loader(),apply=True)
    assert reports['ist']['rows'][0]['alicanto_status']=='excluded'
    assert reports['ist']['reconciliation']['states'].get('published',0)==0


def test_previous_published_decision_keeps_score_without_a_new_assessment(tmp_path,monkeypatch):
    setup(tmp_path,raw(),status='published')
    monkeypatch.setattr('scripts.occupational_inventory.process_curated_beta_source',lambda *a: (_ for _ in ()).throw(AssertionError('repeat analysis')))
    reports=report(raw());reconcile(tmp_path,reports,Loader(),apply=True)
    assert reports['ist']['rows'][0]['alicanto_status']=='published'
    assert reports['ist']['rows'][0]['editorial_score']==65


def test_changed_input_readonly_reports_reassessment_without_mutation(tmp_path):
    setup(tmp_path,raw('old advice'));path=tmp_path/'data/state/pending_queue.json';before=path.read_bytes()
    reports=report(raw());reconcile(tmp_path,reports,Loader(),apply=False)
    assert path.read_bytes()==before
    assert reports['ist']['rows'][0]['alicanto_status']=='pending_reassessment'
    assert reports['ist']['rows'][0]['editorial_score'] is None


def test_checkpoint_accepts_workflow_relative_output_and_only_isolated_branch(tmp_path,monkeypatch):
    from pathlib import Path
    from scripts.occupational_inventory import commit_source_checkpoint
    output=tmp_path/'data/audits/source_e_recovery/actions/123/inventory';output.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GITHUB_REF','refs/heads/codex/e-salud-laboral-20261011')
    calls=[]
    monkeypatch.setattr('scripts.occupational_inventory.subprocess.check_output',lambda *a,**k:'candidate')
    from types import SimpleNamespace
    def run(args,**kwargs):
        calls.append(args);return SimpleNamespace(returncode=0)
    monkeypatch.setattr('scripts.occupational_inventory.subprocess.run',run)
    commit_source_checkpoint(tmp_path,Path('data/audits/source_e_recovery/actions/123/inventory'),'ist')
    assert calls[0]==['git','add','--','data/audits/source_e_recovery/actions/123/inventory']
    assert calls[-2][-1]=='HEAD:codex/e-salud-laboral-20261011'


def test_same_assessment_failure_limit_survives_separate_source_checkpoints(tmp_path,monkeypatch):
    from radar_salud.processing import DeferredProcessing
    setup(tmp_path,raw(),status='pending');calls=[]
    def unavailable(*args):
        calls.append(True);raise DeferredProcessing('curated beta source pending assessment')
    monkeypatch.setattr('scripts.occupational_inventory.process_curated_beta_source',unavailable)
    shared={'failures':3}
    reports=report(raw());reconcile(tmp_path,reports,Loader(),apply=True,assessment_state=shared)
    assert not calls and shared['failures']==3
    assert reports['ist']['rows'][0]['processing_reason']=='analysis_failure_limit_reached_after_three_attempts'


def test_health_and_product_sync_preserve_unrelated_sources_and_capture_time(tmp_path):
    from scripts.occupational_inventory import save_health
    for name in ('data/source_health.json','web/data/source_health.json','web/data/product.json'):
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps({'sources':{'other':{'name':'Unrelated','count':8}},'untouched':42}))
    reports={'ist':{'metrics':{'90':{'expected_role':1},'30':{'expected_role':1}},
        'reconciliation':{'states':{'published':1,'pending':1}},'coverage_complete':False,
        'errors':[{'code':'publisher_date_conflict'}],'window':{'as_of':'2026-10-11'},
        'pages':[{'url':'https://ist.cl/noticias/'}], 'capture_checked_at':'2026-10-11T05:00:00+00:00',
        'oldest_capture_at':'2026-10-11T04:00:00+00:00','rows':[{'url':URL,'status':'candidate',
        'publication_date':'2026-10-10','alicanto_status':'published'}],'raw_items':[]}}
    save_health(tmp_path,reports)
    for name in ('data/source_health.json','web/data/source_health.json','web/data/product.json'):
        saved=json.loads((tmp_path/name).read_text())
        assert saved['sources']['other']=={'name':'Unrelated','count':8} and saved['untouched']==42
        row=saved['sources']['ist']
        assert row['recovery_outcome']=='OPERATIVE_DEGRADED' and row['status']!='ok'
        assert row['checked_at']=='2026-10-11T05:00:00+00:00'
        assert row['oldest_capture_at']=='2026-10-11T04:00:00+00:00'
        assert row['published']==1 and row['pending']==1
