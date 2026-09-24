import json
from datetime import datetime
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def test_validated_trigger_has_observed_wakeup_and_honest_limitation():
    queue = load("config/orchestrator_queue.json")
    task = next(item for item in queue["tasks"] if item["id"] == "orchestrator_event_trigger")
    proof = task["trigger_evidence"]

    assert task["status"] == "validated"
    assert proof["kind"] == "condition_watch_polling"
    assert proof["enabled"] is True
    assert len(proof["automation_id"]) == 32
    assert datetime.fromisoformat(proof["observed_run_at"].replace("Z", "+00:00"))
    assert "sin retransmisión humana" in proof["observed_behavior"]
    assert "no es un webhook instantáneo" in proof["limitation"]


def test_pmo_records_same_operational_evidence_without_production_scope():
    queue = load("config/orchestrator_queue.json")
    baseline = load("config/pmo_baseline.json")
    task = next(item for item in queue["tasks"] if item["id"] == "orchestrator_event_trigger")
    debt = next(item for item in baseline["infrastructure_debt"] if item["id"] == task["id"])
    proof = baseline["evidence_catalog"][debt["evidence"]]

    assert debt["status"] == "Validado"
    assert proof["automation_id"] == task["trigger_evidence"]["automation_id"]
    assert proof["observed_run_at"] == task["trigger_evidence"]["observed_run_at"]
    assert proof["result"] == "success"
    assert "sin secretos" in proof["scope"]
    assert "main" in proof["scope"]
    assert "producción" in proof["scope"]
