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
