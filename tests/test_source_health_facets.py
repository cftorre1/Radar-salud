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
