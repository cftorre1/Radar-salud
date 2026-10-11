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


def test_changed_input_readonly_reports_reassessment_without_mutation(tmp_path):
    setup(tmp_path,raw('old advice'));path=tmp_path/'data/state/pending_queue.json';before=path.read_bytes()
    reports=report(raw());reconcile(tmp_path,reports,Loader(),apply=False)
    assert path.read_bytes()==before
    assert reports['ist']['rows'][0]['alicanto_status']=='pending_reassessment'
    assert reports['ist']['rows'][0]['editorial_score'] is None
