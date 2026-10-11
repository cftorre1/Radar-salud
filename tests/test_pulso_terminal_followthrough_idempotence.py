"""Bounded followthrough helper contracts; future observations are synthetic.

Actual paid323 and final123 executions/failed QA remain immutable premises.
The independent-reader boundary below is fixed explicitly; these snapshots
never stand for a real core run, successful model call or acceptance artifact.
"""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


prior = module("terminal_followthrough_prior_unit_shapes", "tests/test_pulso_revalidated_idempotence.py")
helper = prior.helper
NOW = datetime(2026, 10, 11, 23, 2, tzinfo=timezone.utc)


@lru_cache(maxsize=1)
def actual_final_failure():
    values = {}
    for name, path in (("report", helper.DEFAULT_REPORT), ("quality", helper.DEFAULT_QA)):
        payload = subprocess.check_output(["git", "show", helper.ARCHIVED_FINAL_PRODUCER + ":" + path], cwd=ROOT)
        assert helper.digest(payload) == helper.ARCHIVED_FINAL_FILES[path]
        values[name] = json.loads(payload)
    assert values["quality"]["processing_qa"] == "FAIL"
    assert len(values["quality"]["findings"]) == 24
    return values


@lru_cache(maxsize=1)
def actual_settlement_failure():
    values = {}
    for name, path in (("report", helper.DEFAULT_REPORT), ("quality", helper.DEFAULT_QA),
                       ("telemetry", "data/ai_usage/responses.jsonl")):
        payload = subprocess.check_output(["git", "show", helper.SETTLEMENT_PRODUCER + ":" + path], cwd=ROOT)
        assert helper.digest(payload) == helper.SETTLEMENT_FILES[path]
        values[name] = ([json.loads(line) for line in payload.splitlines() if line.strip()]
                        if path.endswith("jsonl") else json.loads(payload))
    assert len(values["quality"]["findings"]) == 1477
    return values


def unit_context_and_proof():
    context, lineage, stock, receipts = prior.unit_revalidated_context()
    archive = deepcopy(actual_final_failure())
    old = archive["report"]["last_core_execution"]
    settlement = deepcopy(actual_settlement_failure())
    settled_execution = settlement["report"]["last_core_execution"]
    execution = context["report"]["last_core_execution"]
    execution.update(code_sha="f" * 40, processing_attempts_increased=0,
        started_at="2026-10-11T23:40:00Z", finished_at="2026-10-11T23:41:00Z",
        budget_before={"run": prior.unit.counters(), "month": deepcopy(settled_execution["budget_after"]["month"])},
        budget_after={"run": prior.unit.counters(), "month": deepcopy(settled_execution["budget_after"]["month"])})
    context["discovery"]["at"] = "2026-10-11T23:40:30Z"
    context["events"] = settlement["telemetry"]
    context["ledgers"] = {"2026-10.json": deepcopy(settled_execution["budget_after"]["month"])}
    live9 = {}
    for index in range(9):
        url = f"https://www.latercera.com/nacional/noticia/explicit-unit-live-settlement-{index}/"
        item = deepcopy(context["queue"]["unit-fingerprint-0"])
        item.update(status="rejected", attempts=1)
        item["raw"]["url"] = url
        context["queue"][f"explicit-unit-live-settlement-fingerprint-{index}"] = item
        live9[url] = dict(unit_only=True, status="rejected", attempts=1)
    execution["processing_selection"].update(ready_selected_urls=[], skipped_terminal_urls=context["selection"]["urls"])
    context["discovery"]["processing_attempts"] = 0
    files = deepcopy(old["runtime_fingerprint"]["files"])
    files["scripts/pulso_idempotence.py"] = helper.digest(b"explicit synthetic future helper bytes")
    files["scripts/qa_pulso_recovery.py"] = helper.digest(b"explicit synthetic future consumer bytes")
    fingerprint = dict(files=files, sha256=helper.digest(files), git_or_marker_sha_used=False)
    context["runtime_fingerprint"] = deepcopy(fingerprint)
    context["recorded_core_runtime_fingerprint"] = deepcopy(fingerprint)
    execution["runtime_fingerprint"] = deepcopy(fingerprint)
    archived = dict(evaluation_execution=old, paid_model_lineage=deepcopy(lineage),
        current_revalidation_receipts=deepcopy(receipts), actual_budget_delta=helper.budget_delta(old),
        publication_approved=False)
    proof = dict(schema_version="pulso_terminal_followthrough_provenance_v1",
        archived_producer=dict(commit=helper.ARCHIVED_FINAL_PRODUCER, code_sha=helper.ARCHIVED_FINAL_CODE,
            runtime_fingerprint_sha256=helper.ARCHIVED_FINAL_FINGERPRINT, files=dict(helper.ARCHIVED_FINAL_FILES), original_qa_promoted=False),
        settlement_producer=dict(commit=helper.SETTLEMENT_PRODUCER, code_sha=helper.SETTLEMENT_CODE,
            runtime_fingerprint_sha256=helper.SETTLEMENT_FINGERPRINT, files=dict(helper.SETTLEMENT_FILES), original_qa_promoted=False),
        archived_final_evaluation=archived, current_followthrough_execution=deepcopy(execution),
        archived_processing_qa=archive["quality"], paid_model_lineage=deepcopy(lineage),
        launch_stock=dict(stock, commit=helper.SETTLEMENT_PRODUCER, file_sha256=helper.SETTLEMENT_FILES),
        preserved_final_receipts=deepcopy(receipts), actual_budget_delta=helper.budget_delta(execution),
        settlement_execution=settled_execution, settlement_processing_qa=settlement["quality"],
        settlement_live9=live9,
        settlement_response_events=[event for event in settlement["telemetry"]
            if helper.stamp(settled_execution["started_at"]) <= helper.stamp(event["at"]) <= helper.stamp(settled_execution["finished_at"])],
        settlement_budget_delta=helper.budget_delta(settled_execution),
        settlement_telemetry_prefix={"explicit_unit_boundary": True},
        publication_approved=False)
    proof["launch_stock"]["source_queue_semantic_sha256s"] = {
        url: row["semantic_sha256"] for url, row in helper.source_queue(context["queue"]).items()}
    return context, proof


@pytest.fixture
def shape(monkeypatch):
    context, immutable_proof = unit_context_and_proof()
    def fixed_reader(root, *, report, queue, history, snapshot, telemetry, execution):
        result = deepcopy(immutable_proof)
        result["current_followthrough_execution"] = deepcopy(execution)
        result["actual_budget_delta"] = helper.budget_delta(execution)
        return result
    reader = SimpleNamespace(verify_terminal_followthrough_execution=fixed_reader)
    monkeypatch.setattr(helper, "final_paid_reader", lambda root: reader)
    baseline = helper.capture_terminal_followthrough_baseline(context, now=NOW)
    return context, baseline, reader


def seal(bundle):
    bundle["payload_sha256"] = helper.digest({key: value for key, value in bundle.items() if key != "payload_sha256"})


def later_core(context):
    result = prior.second_core(context)
    result["report"]["last_core_execution"].update(started_at="2026-10-11T23:43:00Z", finished_at="2026-10-11T23:44:00Z")
    result["discovery"]["at"] = "2026-10-11T23:43:30Z"
    return result


def test_explicit_terminal_mode_preserves_both_actual_failures_and_runtime_scope(shape):
    context, baseline, _ = shape
    proof = baseline["terminal_followthrough_provenance"]
    assert baseline["mode"] == helper.TERMINAL_FOLLOWTHROUGH_MODE
    assert proof["archived_processing_qa"] == actual_final_failure()["quality"]
    assert proof["paid_model_lineage"]["original_processing_qa"] == prior.immutable_paid_failure()["quality"]
    assert proof["archived_final_evaluation"]["evaluation_execution"]["code_sha"] == helper.ARCHIVED_FINAL_CODE
    assert baseline["baseline_execution"]["processing_attempts_increased"] == 0
    assert baseline["archived_producer"]["files"] == helper.ARCHIVED_FINAL_FILES
    assert helper.preflight(baseline, context, now=NOW)["verdict"] == "PASS"
    assert proof["settlement_execution"]["processing_attempts_increased"] == 9
    assert len(proof["settlement_response_events"]) == 4
    assert proof["settlement_processing_qa"] == actual_settlement_failure()["quality"]
    assert helper.compare(baseline, later_core(context), now=NOW.replace(minute=5))["verdict"] == "PASS"


def test_old_capture_modes_cannot_silently_adopt_terminal_followthrough(shape):
    context, _, _ = shape
    with pytest.raises(ValueError, match="positive_genuine_paid_processing_required"):
        helper.capture_baseline(context, now=NOW)
    with pytest.raises(ValueError, match="two_revalidation_processing_attempts_required"):
        helper.capture_revalidated_baseline(context, now=NOW)


@pytest.mark.parametrize("attack,reason", [
    (lambda c: c["processing_qa"].update(processing_qa="FAIL"), "qa_pass_required"),
    (lambda c: c["report"]["last_core_execution"].update(processing_attempts_increased=2), "zero_actual_ai_and_attempts"),
    (lambda c: c["discovery"].update(processing_attempts=1), "zero_actual_ai_and_attempts"),
    (lambda c: c["report"]["last_core_execution"]["processing_selection"].update(ready_selected_urls=[c["selection"]["urls"][0]]), "all113_terminal_skip"),
    (lambda c: c["queue"]["unit-fingerprint-0"].update(status="archived"), "all113_terminal_skip"),
])
def test_terminal_capture_requires_current_real_zero_and_all_terminal(shape, attack, reason):
    context, _, _ = shape
    attack(context)
    with pytest.raises(ValueError, match=reason):
        helper.capture_terminal_followthrough_baseline(context, now=NOW)


@pytest.mark.parametrize("path", ["src/radar_salud/pulso_source.py", "src/radar_salud/engine_cli.py",
    "src/radar_salud/pulso_editorial_proof.py", "config/media_early_signal_gate.json", ".github/workflows/daily-radar.yml"])
def test_source_engine_gate_and_unlisted_workflow_bytes_cannot_change(shape, path):
    _, baseline, _ = shape
    fingerprint = baseline["runtime_fingerprint"]
    fingerprint["files"][path] = helper.digest(b"unapproved unit runtime edit")
    fingerprint["sha256"] = helper.digest(fingerprint["files"])
    baseline["baseline_execution"]["runtime_fingerprint"] = deepcopy(fingerprint)
    baseline["terminal_followthrough_provenance"]["current_followthrough_execution"] = deepcopy(baseline["baseline_execution"])
    seal(baseline)
    with pytest.raises(ValueError, match="runtime_changed_outside_bound_consumers"):
        helper.validate_baseline(baseline)


@pytest.mark.parametrize("attack,reason", [
    (lambda b: b["archived_producer"]["files"].update({helper.DEFAULT_QA: "0" * 64}), "archive_or_consumer_scope_changed"),
    (lambda b: b["allowed_consumer_changes"].append("src/radar_salud/pulso_source.py"), "archive_or_consumer_scope_changed"),
    (lambda b: b["terminal_followthrough_provenance"]["archived_processing_qa"].update(processing_qa="PASS"), "archived_real_evaluation_or_failure_changed"),
    (lambda b: b["terminal_followthrough_provenance"]["paid_model_lineage"].update(original_paid_qa_promoted=True), "original_paid_or_final_receipts_erased"),
    (lambda b: b["terminal_followthrough_provenance"]["preserved_final_receipts"].clear(), "original_paid_or_final_receipts_erased"),
    (lambda b: b.update(paid_successful_response_ids=["unit-fake-new-paid-label"]), "retagged_as_paid_or_revalidation"),
    (lambda b: b["terminal_followthrough_provenance"]["launch_stock"].update(native_queue_count=0), "full113_or_native_stock_missing"),
    (lambda b: b["terminal_followthrough_provenance"]["settlement_producer"].update(original_qa_promoted=True), "provenance_descriptor_changed"),
    (lambda b: b["terminal_followthrough_provenance"]["settlement_response_events"][0].update(response_id="unit-forged-response"), "settlement_responses_or_reviews_missing"),
    (lambda b: b["terminal_followthrough_provenance"]["settlement_processing_qa"].update(processing_qa="PASS"), "settlement_execution_or_usage_changed"),
    (lambda b: b["terminal_followthrough_provenance"]["launch_stock"]["source_queue_semantic_sha256s"].update({b["selection"]["urls"][0]: "0" * 64}), "existing_source_semantics_changed"),
])
def test_resealed_terminal_baseline_cannot_erase_archive_or_expand_scope(shape, attack, reason):
    _, baseline, _ = shape
    attack(baseline)
    seal(baseline)
    with pytest.raises(ValueError, match=reason):
        helper.validate_baseline(baseline)


def test_terminal_reader_must_exist_and_preserved_receipts_are_reread_before_replay(shape):
    context, baseline, reader = shape
    original = reader.verify_terminal_followthrough_execution
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        result["preserved_final_receipts"] = {}
        return result
    reader.verify_terminal_followthrough_execution = changed
    with pytest.raises(ValueError, match="terminal_followthrough_provenance_changed"):
        helper.preflight(baseline, context, now=NOW)
    result = helper.compare(baseline, later_core(context), now=NOW.replace(minute=5))
    assert "archived_final_or_terminal_followthrough_provenance_invalid" in {row["code"] for row in result["findings"]}
    del reader.verify_terminal_followthrough_execution
    with pytest.raises(ValueError, match="independent_terminal_followthrough_reader_unavailable"):
        helper.capture_terminal_followthrough_baseline(context, now=NOW)


def test_followthrough_replay_still_requires_same_new_fingerprint_and_native_objects(shape):
    context, baseline, _ = shape
    after = later_core(context)
    after["queue"]["unit-native-0"]["raw"]["unit_index"] = "changed whole native item"
    assert "changed_native_queue" in {row["code"] for row in helper.compare(baseline, after, now=NOW.replace(minute=5))["findings"]}
    after = later_core(context)
    after["runtime_fingerprint"]["files"]["scripts/qa_pulso_recovery.py"] = helper.digest(b"another consumer version")
    with pytest.raises(ValueError, match="runtime_implementation_or_policy_changed"):
        helper.preflight(baseline, after, now=NOW)
