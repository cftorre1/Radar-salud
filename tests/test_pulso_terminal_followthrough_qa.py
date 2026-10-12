"""Replay immutable producers; synthetic zero-core shapes never claim a run."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("terminal_actual_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec); spec.loader.exec_module(qa)


@pytest.fixture(scope="module")
def actual():
    return qa.terminal_followthrough_origin(ROOT)


def test_actual_archive_separates_paid_two_real_final_revalidation_and_live9(actual):
    settled = actual["settlement"]
    assert actual["processing_qa"]["verdict"] == "FAIL"
    assert len(actual["processing_qa"]["findings"]) == 24
    assert actual["evaluation"]["paid_model_lineage"]["original_budget_delta"]["fast"]["successful"] == 2
    assert settled["budget_delta"] == {"fast":dict(attempted=4,successful=4,failed=0),"deep":dict(attempted=0,successful=0,failed=0)}
    assert settled["processing_qa"]["verdict"] == "FAIL"
    assert len(settled["processing_qa"]["findings"]) == 1477
    assert len(settled["rows"]) == 9
    assert sum(row["model_response_id"] is not None for row in settled["rows"].values()) == 4
    assert all(row["status"] == "rejected" and row["attempts"] == 1 for row in settled["rows"].values())
    assert {row["assessment"].get("relevance_score") for row in settled["rows"].values()} == {None,58,35,68,5}
    changed = [row for row in settled["rows"].values() if row["primary_updated"]]
    assert len(changed) == 1
    assert changed[0]["body_characters"] == 3449
    assert changed[0]["body_sha256"] == "d5314e898c41422ecea913473d3cac6f7514a20705d10a684a7c91bc38862cd3"
    assert settled["telemetry_prefix"]["settled_events"] == settled["telemetry_prefix"]["events"] + 4


@pytest.mark.parametrize("mutation", ["promote_qa", "telemetry_missing", "old113", "native", "model_id", "primary_date", "validation"])
def test_original_settlement_cannot_be_replaced_by_consistent_mutable_claims(actual, monkeypatch, mutation):
    data = actual["settlement"]
    queue = dict(data["queue"])
    mapping = {
        "data/audits/pulso_runtime_2026_10_11.json": data["report"],
        "data/audits/pulso_directed_processing_qa_2026_10_11.json": data["processing_qa"],
        "data/state/pending_queue.json": queue,
        "data/history/superintendencia_signals.json": {"signals":data["history"]},
        "web/data/radar_today.json": data["snapshot"],
        "data/ai_usage/responses.jsonl": data["telemetry"],
        "data/ai_usage/2026-10.json": data["month"],
        "data/state/discovery_run.json": {},
    }
    url = next(url for url,row in data["rows"].items() if row["model_response_id"])
    key = data["rows"][url]["queue_fingerprint"]
    item = copy.deepcopy(queue[key]); queue[key] = item
    if mutation == "promote_qa": mapping["data/audits/pulso_directed_processing_qa_2026_10_11.json"] = dict(data["processing_qa"], verdict="PASS", findings=[])
    elif mutation == "telemetry_missing": mapping["data/ai_usage/responses.jsonl"] = data["telemetry"][:-1]
    elif mutation == "old113":
        frozen = json.loads((ROOT / qa.PROCESSING_COHORT_PATH).read_bytes())
        k = next(k for k,v in queue.items() if v.get("raw",{}).get("url") in frozen["urls"])
        queue[k] = dict(queue[k], attempts=999)
    elif mutation == "native":
        k = next(k for k,v in queue.items() if v.get("source") != qa.SOURCE)
        queue[k] = dict(queue[k], attempts=queue[k].get("attempts",0) + 1)
    elif mutation == "model_id": item["raw"]["metadata"]["analysis_model_output"]["_pulso_analysis_meta"]["response_id"] = "invented-response"
    elif mutation == "primary_date": item["raw"]["event_date"] = "2026-10-10"
    elif mutation == "validation": item["raw"]["metadata"]["pulso_editorial_proof_validation"]["reason"] = "invented editorial exclusion"
    original = qa.archived_editorial_input
    def claimed(root, specification, required_path):
        return mapping[required_path] if specification["commit"] == qa.LIVE9_PRODUCER else original(root,specification,required_path)
    monkeypatch.setattr(qa,"archived_editorial_input",claimed)
    with pytest.raises(ValueError,match="terminal_live9"):
        qa.terminal_live9_settlement(ROOT, actual)


@pytest.fixture
def zero_shape(actual, monkeypatch):
    """Only the new checkout's Git lookup is simulated, not archived producers."""
    settled = actual["settlement"]
    execution = copy.deepcopy(settled["execution"])
    urls = json.loads((ROOT / qa.PROCESSING_COHORT_PATH).read_bytes())["urls"]
    code = "f" * 40
    files = {path:qa.digest((ROOT/path).read_bytes()) for path in execution["runtime_fingerprint"]["files"]}
    execution.update(code_sha=code,started_at="2026-10-12T00:10:00+00:00",finished_at="2026-10-12T00:20:00+00:00",
        processing_attempts_increased=0,budget_before=copy.deepcopy(settled["execution"]["budget_after"]),budget_after=copy.deepcopy(settled["execution"]["budget_after"]),
        runtime_fingerprint=dict(files=files,sha256=qa.object_digest(files),git_or_marker_sha_used=False))
    execution["processing_selection"] = dict(execution["processing_selection"],sha256=qa.PROCESSING_COHORT_SHA256,
        selected_urls=urls,ready_selected_urls=[],skipped_terminal_urls=urls,skipped_not_due_urls=[],skipped_in_progress_urls=[])
    run = qa.subprocess.run
    def exact_new_bytes(args, **kwargs):
        if len(args) == 3 and args[:2] == ["git","show"] and args[2].startswith(code + ":"):
            return SimpleNamespace(returncode=0,stdout=(ROOT/args[2].split(":",1)[1]).read_bytes())
        return run(args,**kwargs)
    monkeypatch.setattr(qa.subprocess,"run",exact_new_bytes)
    return dict(root=ROOT,report={"last_core_execution":execution},queue=settled["queue"],history=settled["history"],
        snapshot=settled["snapshot"],telemetry=settled["telemetry"],execution=execution,origin=actual)


def test_new_zero_core_shape_retains_both_historical_failures_and_actual_settled_four(zero_shape):
    proof = qa.verify_terminal_followthrough_execution(**zero_shape)
    assert proof["archived_processing_qa"]["verdict"] == "FAIL"
    assert proof["settlement_processing_qa"]["verdict"] == "FAIL"
    assert proof["launch_stock"]["commit"] == qa.LIVE9_PRODUCER
    assert len(proof["launch_stock"]["preserved_terminal_urls"]) == 113
    assert proof["settlement_budget_delta"]["fast"]["successful"] == 4
    assert proof["actual_budget_delta"]["fast"]["attempted"] == 0
    assert len(proof["preserved_final_receipts"]) == 2


def rollover_snapshot(actual):
    audit = json.loads((ROOT / "data/audits/pulso_inherited_native_feed_clock_rollover_2026_10_12.json").read_bytes())
    rows = {row["source_url"]: row for row in actual["settlement"]["snapshot"]["signals"]}
    rows.update({row["url"]: row["after"] for row in audit["changes"]})
    return dict(date=audit["current_date"], signals=[rows[url] for url in audit["current_signal_order"]])


def test_only_exact_inherited_native_rollover_keeps_all70_source_signals(zero_shape):
    current = dict(zero_shape, snapshot=rollover_snapshot(zero_shape["origin"]))
    proof = qa.verify_terminal_followthrough_execution(**current)
    rollover = proof["inherited_native_feed_clock_rollover"]
    assert rollover["pulso_70_signals_unchanged"] is True
    assert rollover["global_feed_unchanged"] is False
    assert rollover["exact_native_changes"] == 5
    assert proof["launch_stock"]["feed_signal_count"] == 165
    assert proof["launch_stock"]["history_signal_count"] == 992


@pytest.mark.parametrize("mutation", ["source", "native", "drop", "duplicate", "date", "execution_day"])
def test_native_clock_rollover_never_waives_any_other_feed_change(zero_shape, mutation):
    current = dict(zero_shape, snapshot=copy.deepcopy(rollover_snapshot(zero_shape["origin"])))
    if mutation in {"source", "native"}:
        row = next(row for row in current["snapshot"]["signals"]
                   if bool(qa.normalized_url(row.get("source_url"))) == (mutation == "source"))
        row["what_happened"] += " altered substantive fact"
    elif mutation == "drop": current["snapshot"]["signals"].pop()
    elif mutation == "duplicate": current["snapshot"]["signals"].append(current["snapshot"]["signals"][0])
    elif mutation == "date": current["snapshot"]["date"] = "2026-10-13"
    else:
        current["execution"] = dict(current["execution"], started_at="2026-10-13T00:10:00Z", finished_at="2026-10-13T00:20:00Z")
    with pytest.raises(ValueError, match="terminal_followthrough"):
        qa.verify_terminal_followthrough_execution(**current)


@pytest.mark.parametrize("mutation",["ledger_old516","attempt","call","pending_body","terminal_receipt","source_policy","delete_unselected","delete_live9","live9_body_summary","pending_body_summary","raw_body_summary"])
def test_zero_core_never_waives_processing_or_primary_state_changes(zero_shape,mutation):
    current = dict(zero_shape); current["execution"] = copy.deepcopy(current["execution"])
    if mutation == "ledger_old516": current["execution"]["budget_after"]["month"] = current["origin"]["month"]
    elif mutation == "attempt": current["execution"]["processing_attempts_increased"] = 1
    elif mutation == "call": current["telemetry"] = current["telemetry"] + [{"at":"2026-10-12T00:15:00+00:00","kind":"fast","success":True,"response_id":"new-paid"}]
    elif mutation in {"pending_body","terminal_receipt"}:
        current["queue"] = dict(current["queue"])
        k = next(k for k,v in current["queue"].items() if v.get("source") == qa.SOURCE and
            (v.get("status") == "pending" if mutation == "pending_body" else v.get("raw",{}).get("metadata",{}).get(qa.FINAL_PAID_RECEIPT)))
        item = copy.deepcopy(current["queue"][k]);current["queue"][k] = item
        item["raw"]["metadata"]["page_text"] += " forged primary text"
    elif mutation in {"delete_unselected","delete_live9"}:
        current["queue"] = dict(current["queue"])
        k = (next(iter(current["origin"]["settlement"]["rows"].values()))["queue_fingerprint"]
             if mutation == "delete_live9" else next(k for k,v in current["queue"].items() if v.get("source") == qa.SOURCE and v.get("status") == "pending"))
        del current["queue"][k]
    elif mutation in {"live9_body_summary","pending_body_summary","raw_body_summary"}:
        current["queue"] = dict(current["queue"])
        k = (next(iter(current["origin"]["settlement"]["rows"].values()))["queue_fingerprint"]
             if mutation == "live9_body_summary" else next(k for k,v in current["queue"].items()
                if v.get("source") == qa.SOURCE and v.get("status") == "pending"
                and isinstance(v["raw"].get("raw_text") if mutation == "raw_body_summary"
                    else v["raw"].get("metadata",{}).get("page_text"),str)))
        item = copy.deepcopy(current["queue"][k]);current["queue"][k] = item
        owner = item["raw"] if mutation == "raw_body_summary" else item["raw"]["metadata"]
        field = "raw_text" if mutation == "raw_body_summary" else "page_text"
        body = owner[field]
        owner[field] = {"utf8_sha256":qa.digest(body.encode()),"characters":len(body)}
    elif mutation == "source_policy":
        fp = current["execution"]["runtime_fingerprint"];fp["files"]["config/media_early_signal_gate.json"] = qa.digest(b"threshold71")
        fp["sha256"] = qa.object_digest(fp["files"])
    with pytest.raises(ValueError,match="terminal_followthrough"):
        qa.verify_terminal_followthrough_execution(**current)
