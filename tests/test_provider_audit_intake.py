import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import pytest
from radar_salud.pending_queue import PendingQueue

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('provider_reconcile',ROOT/'scripts/reconcile_providers.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_audited_recovery_is_idempotent_backfill_without_publication(tmp_path):
    audit={'slug':'indisa','as_of':'2026-10-11','audit_path':'data/audits/indisa.json',
           'surfaces':[{'url':'https://www.indisa.cl/categoria-blog/novedades-indisa'}],
           'source_quality_gate':'pending_90_day_audit',
           'original_items':[{'title':'Convenio verificado de INDISA e Isapre Esencial',
           'url':'https://www.indisa.cl/blog/convenio-verificado','publication_date':'2026-09-11',
           'date_evidence':'verified_article_header','recover':True}]}
    cfg={'name':'Clínica INDISA','source_type':'corporate'}
    queue=PendingQueue(tmp_path/'queue.json');now=datetime(2026,10,11,tzinfo=timezone.utc)
    assert len(module.admit(queue,audit,cfg,now))==1
    assert module.admit(queue,audit,cfg,now)==[]
    item=next(iter(queue.items.values()))
    assert item['status']=='pending' and item['lane']=='BACKFILL'
    assert item['raw']['metadata']['source_quality_gate']=='pending_90_day_audit'
    assert item['raw']['raw_text']==''
    assert module.in_window('2026-09-11','2026-10-11',30) is True
    assert module.in_window(None,'2026-10-11',90) is None
    audit['original_items'][0]['url']='https://evil.example/convenio'
    with pytest.raises(ValueError,match='Untrusted'):module.admit(queue,audit,cfg,now)


def test_provider_title_correction_does_not_duplicate_same_original_url(tmp_path):
    from radar_salud.models import RawItem
    queue=PendingQueue(tmp_path/'queue.json')
    raw=RawItem('bupa_chile','Título inicial abreviado','https://www.bupa.cl/genomas','Bupa Chile','corporate')
    assert queue.discover('bupa_chile',[raw])==1
    raw.title='Título original completo con comillas y proyecto genómico'
    assert queue.discover('bupa_chile',[raw])==0
    assert len(queue.items)==1


def test_reviewed_false_negative_reopens_once_without_resetting_identity(tmp_path):
    from radar_salud.models import RawItem
    now=datetime(2026,10,11,tzinfo=timezone.utc)
    queue=PendingQueue(tmp_path/'queue.json')
    url='https://www.davila.cl/novedades/operativo-medico-sotero'
    raw=RawItem('red_davila','Programa Enlace: primer operativo',url,'Red Dávila','corporate','2026-08-24',metadata={'recovery_audit':'audit.json','source_quality_gate':'passed'})
    queue.discover('red_davila',[raw],now=now);key=next(iter(queue.items));queue.finish(key,'rejected','processor_rejected',now=now)
    evidence={'title':raw.title,'url':url,'publication_date':raw.event_date,'date_evidence':'verified_article_header','recover':True,
        'review_false_negative':True,'review_revision':'official_chain_v1',
        'supporting_official_sources':[{'url':'https://www.davila.cl/novedades/firma','publication_date':'2026-08-20'}]}
    audit={'slug':'red_davila','as_of':'2026-10-11','audit_path':'audit.json','surfaces':[{'url':'https://www.davila.cl/novedades'}],'original_items':[evidence]}
    cfg={'name':'Red Dávila','source_type':'corporate'}
    assert len(module.admit(queue,audit,cfg,now))==1
    assert next(iter(queue.items))==key and queue.items[key]['status']=='pending'
    assert queue.items[key]['review_history'][0]['prior_status']=='rejected'
    queue.finish(key,'rejected','relevance_below_source_gate',now=now)
    assert module.admit(queue,audit,cfg,now)==[]
    assert queue.items[key]['status']=='rejected' and len(queue.items[key]['review_history'])==1


def test_bounded_repair_evaluates_only_selected_deferred_url_and_keeps_other_assessment(tmp_path, monkeypatch):
    import json
    from radar_salud.models import RawItem
    from radar_salud import ai_budget, public_source_pipeline
    from radar_salud.pending_queue import atomic_json
    cfgs=[{'slug':slug,'name':slug,'source_type':'corporate'} for slug in ('bupa_chile','andes_salud')]
    atomic_json(tmp_path/'config/sources.json',cfgs)
    prior={'outcome':'published','evaluated':3,'published':3}
    atomic_json(tmp_path/'data/source_health.json',{'sources':{'andes_salud':{'audited_assessment':prior,'editorial_outcome':'published'}}})
    atomic_json(tmp_path/'web/data/radar_today.json',{'signals':[]})
    queue=PendingQueue(tmp_path/'data/state/pending_queue.json')
    for cfg in cfgs:
        audit_path=f"data/audits/providers_2026_10_11/{cfg['slug']}.json"
        atomic_json(tmp_path/audit_path,{'slug':cfg['slug'],'audit_path':audit_path,'as_of':'2026-10-11','surfaces':[{'url':'https://www.bupa.cl'}],'original_items':[],'blockers':[]})
        for suffix in ('selected','other'):
            raw=RawItem(cfg['slug'],suffix,f"https://www.bupa.cl/{cfg['slug']}-{suffix}",cfg['name'],'corporate','2026-10-02',metadata={'recovery_audit':audit_path})
            queue.discover(cfg['slug'],[raw])
    queue.save()
    evaluated=[]
    monkeypatch.setattr(ai_budget,'has_capacity',lambda kind:True)
    monkeypatch.setattr(public_source_pipeline,'process_corporate_news',lambda raw,cfg:evaluated.append(raw.url))
    selected='https://www.bupa.cl/bupa_chile-selected'
    module.run(tmp_path,apply=True,live=True,limit=2,urls=[selected])
    assert evaluated==[selected]
    health=json.loads((tmp_path/'data/source_health.json').read_text())
    assert health['sources']['andes_salud']['audited_assessment']==prior
    assert health['sources']['andes_salud']['editorial_outcome']=='published'
    queue=PendingQueue(queue.path)
    assert sum(v['status']=='rejected' for v in queue.items.values())==1
    assert sum(v['status']=='pending' for v in queue.items.values())==3
