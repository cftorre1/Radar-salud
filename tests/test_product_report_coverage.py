import importlib.util
import json
from pathlib import Path
from datetime import datetime, timezone

from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue


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
    snapshot.write_text(json.dumps({"signals": [
        {"source_url": "https://example.org/visible", "ingestion_mode": "LIVE"},
        {"source_url": "https://example.org/historical", "ingestion_mode": "BACKFILL"},
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
    snapshot.write_text(json.dumps({"signals":[{"source_url":"https://example.org/a","ingestion_mode":"LIVE","sanction_count":2,"source_alternatives":[{"url":"https://example.org/b"}]}]}))
    assert module.build(tmp_path,tmp_path/"web/data")["coverage_live"]["selected"]==2
