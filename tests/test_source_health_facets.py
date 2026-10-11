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
