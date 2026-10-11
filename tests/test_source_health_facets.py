import json
from radar_salud.source_health import record


def test_source_health_distinguishes_poll_freshness_and_editorial_result(tmp_path):
    record(tmp_path,"source",name="Fuente",discovered=2,new=2,published=0,
           pending=2,rows=[],error=None,live_pending=1,backfill_pending=1)
    row=json.loads((tmp_path/"data/source_health.json").read_text())["sources"]["source"]
    assert (row["technical_status"],row["content_freshness"],row["editorial_outcome"])==("ok","unknown","pending")
    record(tmp_path,"source",name="Fuente",discovered=0,new=0,published=0,
           pending=2,rows=[],error="TimeoutError")
    row=json.loads((tmp_path/"data/source_health.json").read_text())["sources"]["source"]
    assert row["technical_status"]=="error" and row["editorial_outcome"]=="not_evaluated"


def test_source_health_marks_zero_discovery_unknown_freshness_as_coverage_gap(tmp_path):
    record(tmp_path,"deis",name="DEIS",discovered=0,new=0,published=0,
           pending=0,rows=[],error=None,live_pending=0,backfill_pending=0)
    row=json.loads((tmp_path/"data/source_health.json").read_text())["sources"]["deis"]
    assert row["technical_status"]=="ok"
    assert row["status"]=="warning"
    assert row["coverage_status"]=="gap"
    assert row["content_freshness"]=="unknown"


def test_df_all_undated_is_partial_not_healthy_or_fresh(tmp_path):
    record(tmp_path,"diario_financiero",name="Diario Financiero",discovered=73,new=0,published=0,pending=44,rejected=170,
           discovery_evidence={"dated":0,"undated":73,"detail_errors":0,"newest_event_date":None,"last_published_event_at":"2026-09-22"})
    row=json.loads((tmp_path/"data/source_health.json").read_text())["sources"]["diario_financiero"]
    assert row["status"]=="warning" and row["technical_status"]=="partial"
    assert row["coverage_status"]=="date_or_detail_gap"
    assert row["content_freshness"]=="older"
    assert row["counts_scope"]["published"]=="this_run"
    assert row["counts_scope"]["rejected"]=="cumulative_queue"


def test_fiscalization_counts_do_not_certify_coverage_and_history_repairs_last_signal(tmp_path):
    record(tmp_path,'superintendencia_fiscalizacion',name='SIS',discovered=2696,new=0,published=0,
        rows=[],published_history=[{'event_date':'2026-09-08'}],archived=2516)
    row=json.loads((tmp_path/'data/source_health.json').read_text())['sources']['superintendencia_fiscalizacion']
    assert row['status']=='warning' and row['coverage_status']=='unverified'
    assert row['last_signal_at']=='2026-09-08' and row['published_total']==1
    assert row['editorial_outcome']=='no_new_publications_existing_history'
    assert row['published']==0 and row['archived']==2516


def test_fiscalization_windows_use_office_identity_and_never_suspension_dates(tmp_path):
    from datetime import date, timedelta
    today=date.today()
    current=(today-timedelta(days=2)).isoformat()
    old=(today-timedelta(days=150)).isoformat()
    observed=[dict(url='https://www.suseso.gob.cl/609/register',event_date=day,
        metadata={'source_record_id':identity,'emission_date':day,'publication_date':None,
                  'suspension_start':current,'document_class':'enforcement_sanction'})
        for identity,day in [('A',current),('B',current),('C',old)]]
    published=[{'source_url':row['url'],'source_record_id':row['metadata']['source_record_id'],
        'event_date':row['event_date']} for row in observed]
    record(tmp_path,'suseso_fiscalizacion',name='SUSESO',discovered=3,new=0,published=0,
        observed_rows=observed,published_history=published,surfaces=[{'status':'parsed','documents':3}])
    row=json.loads((tmp_path/'data/source_health.json').read_text())['sources']['suseso_fiscalizacion']
    assert row['pages_checked']==1 and row['unique_items']==3
    assert row['items_recent']==row['items_material']==2
    assert row['windows']['30']['published']==2
    assert row['parse_errors']==0 and row['coverage_complete'] is False
    assert row['zero_published_reason']=='evaluated_rejections_or_existing_published_history'


def test_fiscalization_partial_receipt_and_observation_are_separate_from_publication(tmp_path):
    record(tmp_path,'suseso_fiscalizacion',name='SUSESO',discovered=38,new=2,published=0,
        observed_rows=[{'event_date':'2026-09-29','metadata':{'publication_date':'2026-09-29'}}],
        surfaces=[{'url':'isapre','status':'error'},{'url':'compin','status':'parsed'}],
        published_history=[])
    row=json.loads((tmp_path/'data/source_health.json').read_text())['sources']['suseso_fiscalizacion']
    assert row['technical_status']=='partial' and row['coverage_status']=='partial' and row['status']=='warning'
    assert row['last_observed_event_at']=='2026-09-29' and row['last_signal_at'] is None
    assert row['last_observed_publication_at']=='2026-09-29'


def test_fiscalization_undated_documents_cannot_be_real_absence(tmp_path):
    record(tmp_path,'suseso_fiscalizacion',name='SUSESO',discovered=1,new=1,published=0,
        observed_rows=[{'event_date':None}],surfaces=[{'url':'compin','status':'parsed'}])
    row=json.loads((tmp_path/'data/source_health.json').read_text())['sources']['suseso_fiscalizacion']
    assert row['coverage_status']=='gap' and row['undated_observations']==1


def test_parsed_dated_historical_tables_do_not_mark_fiscalization_operational(tmp_path):
    record(tmp_path,'superintendencia_fiscalizacion',name='SIS',discovered=2696,new=0,published=0,
        observed_rows=[{'event_date':'2024-12-31','metadata':{'publication_date':'2024-12-31'}}],
        surfaces=[{'url':'reports','status':'parsed','documents':2696}],published_history=[])
    row=json.loads((tmp_path/'data/source_health.json').read_text())['sources']['superintendencia_fiscalizacion']
    assert row['technical_status']=='ok' and row['coverage_status']=='listed_surface_parsed'
    assert row['status']=='warning' and row['coverage_complete'] is False
    assert row['last_signal_at'] is None and row['last_observed_publication_at']=='2024-12-31'


def test_history_cannot_mask_current_unverified_publications(tmp_path):
    record(tmp_path,"deis",name="DEIS",discovered=1,new=1,published=1,
           rows=[{"event_date":"2026-06-25"}])
    record(tmp_path,"deis",name="DEIS",discovered=0,new=0,published=0,
           diagnostics={"coverage_status":"no_verifiable_documents","verified_publications":0})
    row=json.loads((tmp_path/"data/source_health.json").read_text())["sources"]["deis"]
    assert row["status"]=="warning" and row["coverage_status"]=="gap"
    assert row["last_signal_at"]=="2026-06-25"


def test_partial_document_capture_is_degraded_not_healthy(tmp_path):
    record(tmp_path,"isp_surveillance",name="ISP",discovered=1,new=1,published=0,pending=1,
           diagnostics={"partial_failure":True,"evidence_status":"capture_pending"})
    row=json.loads((tmp_path/"data/source_health.json").read_text())["sources"]["isp_surveillance"]
    assert (row["status"],row["technical_status"],row["coverage_status"])==("warning","degraded","partial")


def test_complete_historical_inventory_does_not_hide_current_access_degradation(tmp_path):
    from radar_salud.pending_queue import atomic_json
    coverage={'coverage_complete':True,'outcome':'OPERATIVE_DEGRADED',
              'coverage_reason':'Known chronology reconciled;191historical originals still403 in current runtime.'}
    atomic_json(tmp_path/'data/source_health.json',{'sources':{'red_davila':{'provider_coverage':coverage}}})
    record(tmp_path,'red_davila',name='Red Dávila',discovered=13,new=1,published=1,
           pending=0,rows=[{'event_date':'2026-10-11'}],error=None,
           evaluation_performed=True,live_pending=0,backfill_pending=0)
    row=json.loads((tmp_path/'data/source_health.json').read_text())['sources']['red_davila']
    assert row['technical_status']=='ok' and row['status']=='warning'
    assert row['provider_coverage']==coverage
