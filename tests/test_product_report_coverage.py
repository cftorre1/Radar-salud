import importlib.util
import json
from pathlib import Path
from datetime import datetime, timezone

from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue


def load_report_module():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("product_report", root / "scripts/product_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_feature_observability_separates_monthly_accumulated_and_actual_model():
    module = load_report_module()
    rows = [
        {"at": "2026-08-20T00:00:00Z", "feature": "global_intelligence", "model": "gpt-5.6-terra",
         "requested_model": "gpt-5.6-luna", "input_tokens": 10, "output_tokens": 5, "cost_usd": None,
         "output_id": "old", "run_id": "r1"},
        {"at": "2026-09-20T00:00:00Z", "feature": "global_intelligence", "model": "gpt-5.6-terra",
         "requested_model": "gpt-5.6-luna", "input_tokens": 20, "output_tokens": 8, "cost_usd": None,
         "output_id": "new", "run_id": "r2"},
    ]
    free = {"global_teaser": {"model_trace": {"api_call": False, "output_id": "teaser"}}, "weekly_insight": None}
    result = module.feature_observability(rows, "2026-09", free)["global_intelligence"]
    assert result["periods"]["monthly"]["models"]["gpt-5.6-terra"]["calls"] == 1
    assert result["periods"]["accumulated"]["models"]["gpt-5.6-terra"]["calls"] == 2
    assert result["periods"]["accumulated"]["models"]["gpt-5.6-luna"]["calls"] is None
    assert result["periods"]["accumulated"]["cost_per_output"] is None


def test_coverage_live_funnel_excludes_backfill(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("product_report", root / "scripts/product_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    queue = PendingQueue(tmp_path / "data/state/pending_queue.json")
    (tmp_path / "data/state").mkdir(parents=True,exist_ok=True)
    (tmp_path / "data/state/discovery_run.json").write_text(json.dumps({"successful_sources":1,"failed_sources":0,"at":datetime.now(timezone.utc).isoformat()}))
    def raw(name):
        return RawItem("source", name, f"https://example.org/{name}", "Source", "official", "2026-09-23")
    queue.discover("source", [raw("visible"), raw("rejected")], last_discovered_at="2026-09-22T12:00:00+00:00")
    queue.discover("source", [raw("historical")])
    for key, item in queue.items.items():
        if item["raw"]["title"] == "visible":
            queue.finish(key, "published")
        elif item["raw"]["title"] == "rejected":
            queue.finish(key, "rejected")
    snapshot = tmp_path / "web/data/radar_today.json"
    snapshot.parent.mkdir(parents=True)
    observed={item["raw"]["title"]:item["detected_at"] for item in queue.items.values()}
    snapshot.write_text(json.dumps({"signals": [
        {"source_url": "https://example.org/visible", "ingestion_mode": "LIVE", "detected_at":observed["visible"]},
        {"source_url": "https://example.org/historical", "ingestion_mode": "BACKFILL", "detected_at":observed["historical"]},
    ]}))
    result = module.build(tmp_path, tmp_path / "web/data")
    assert result["coverage_live"] == {"detected": 2, "evaluated": 2, "selected": 1}
    assert result["queue"]["backfill_pending"] == 1

def test_coverage_counts_live_resolutions_inside_pulse(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("product_report", root / "scripts/product_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    queue = PendingQueue(tmp_path / "data/state/pending_queue.json")
    (tmp_path / "data/state").mkdir(parents=True,exist_ok=True)
    (tmp_path / "data/state/discovery_run.json").write_text(json.dumps({"successful_sources":1,"failed_sources":0,"at":datetime.now(timezone.utc).isoformat()}))
    queue.discover("s",[RawItem("s",name,f"https://example.org/{name}","Source","official","2026-09-23") for name in ("a","b")],last_discovered_at="2026-09-22T12:00:00+00:00")
    for key in queue.items:queue.finish(key,"published")
    snapshot=tmp_path/"web/data/radar_today.json";snapshot.parent.mkdir(parents=True)
    evidence={item["raw"]["title"]:item["detected_at"] for item in queue.items.values()}
    snapshot.write_text(json.dumps({"signals":[{"source_url":"https://example.org/a","ingestion_mode":"LIVE","detected_at":evidence["a"],"sanction_count":2,"source_alternatives":[{"url":"https://example.org/b","ingestion_mode":"LIVE","detected_at":evidence["b"]}]}]}))
    assert module.build(tmp_path,tmp_path/"web/data")["coverage_live"]["selected"]==2

def test_published_backfill_cannot_be_selected_by_fake_live_snapshot(tmp_path):
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location("product_report",root/"scripts/product_report.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    state=tmp_path/"data/state";state.mkdir(parents=True)
    (state/"discovery_run.json").write_text(json.dumps({"successful_sources":1,"at":datetime.now(timezone.utc).isoformat()}))
    q=PendingQueue(state/"pending_queue.json")
    q.discover("s",[RawItem("s","live","https://example.org/live","Source","official",datetime.now(timezone.utc).date().isoformat())],last_discovered_at=datetime.now(timezone.utc).isoformat())
    q.discover("s",[RawItem("s","backfill","https://example.org/backfill","Source","official",datetime.now(timezone.utc).date().isoformat())])
    for key in q.items:q.finish(key,"published")
    by_title={v["raw"]["title"]:v for v in q.items.values()}
    web=tmp_path/"web/data";web.mkdir(parents=True)
    (web/"radar_today.json").write_text(json.dumps({"signals":[
        {"source_url":"https://example.org/backfill","ingestion_mode":"LIVE","detected_at":by_title["backfill"]["detected_at"]},
        {"source_url":"https://example.org/live","ingestion_mode":"LIVE","detected_at":"forged"}]}))
    result=module.build(tmp_path,web)
    assert result["coverage_live"]=={"detected":1,"evaluated":1,"selected":0}
