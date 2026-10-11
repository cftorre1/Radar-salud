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
