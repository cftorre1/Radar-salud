import importlib.util
import json
from pathlib import Path
spec=importlib.util.spec_from_file_location("reviewer",Path("scripts/review_candidate.py"))
reviewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviewer)

def test_missing_snapshot_is_critical(tmp_path):
    r=reviewer.review(tmp_path,"abc")
    assert not r["checks"]["data"]
    assert any(x["code"]=="invalid_snapshot" for x in r["findings"])

def test_current_snapshot_passes_existing_editorial_gate():
    r=reviewer.review(Path("web"),"abc")
    assert r["checks"]["editorial"]
    assert not [f for f in r["findings"] if f["category"]=="data" and f["code"]!="stale_snapshot"]
