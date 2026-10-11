import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('provider_pieces',Path(__file__).parents[1]/'scripts/provider_piece_reconciliation.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_related_media_publication_does_not_date_or_publish_official_piece():
    item={'url':'https://www.bupa.cl/official-investment','title':'Investment','institution':'bupa_chile','publication_date':None}
    decision={'materiality':'candidate','reason':'Date unavailable; same investment already covered','related_to':['https://www.df.cl/investment']}
    history=[{'title':'Covered investment','source_url':'https://www.df.cl/investment','event_date':'2026-09-21'}]
    row=module.reconcile_piece(item,decision,{},set(),history,history)
    assert row['related_published_signals'][0]['publication_date']=='2026-09-21'
    assert row['history_count']==0 and row['feed_count']==0 and not row['omitted']
    assert item['publication_date'] is None

def test_rejection_and_seen_are_evidence_of_detection_not_publication():
    item={'url':'https://www.davila.cl/novedades/x','title':'Capacity','institution':'red_davila'}
    queue={'key':{'source':'red_davila','status':'rejected','reason':'relevance_below_source_gate','lane':'BACKFILL','raw':{'url':item['url'],'metadata':{'editorial_assessment':{'relevance_score':74,'minimum_relevance':75}}}}}
    row=module.reconcile_piece(item,{'materiality':'candidate','reason':'74<75'},queue,{'key'},[],[])
    assert row['detected'] and row['seen_ledger_match'] and not row['omitted']
    assert row['alicanto_status']=='rejected' and row['feed_count']==0
