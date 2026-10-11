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


def test_fiscalization_counts_do_not_certify_coverage_and_history_repairs_last_signal(tmp_path):
    record(tmp_path,'superintendencia_fiscalizacion',name='SIS',discovered=2696,new=0,published=0,
        rows=[],published_history=[{'event_date':'2026-09-08'}],archived=2516)
    row=json.loads((tmp_path/'data/source_health.json').read_text())['sources']['superintendencia_fiscalizacion']
    assert row['status']=='warning' and row['coverage_status']=='unverified'
    assert row['last_signal_at']=='2026-09-08' and row['published_total']==1
    assert row['editorial_outcome']=='no_new_publications_existing_history'
    assert row['published']==0 and row['archived']==2516


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
