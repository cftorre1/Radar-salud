"""Read-only composite-baseline contracts, never actual processing evidence.

The synthetic current snapshots exercise admission and tamper denial. Their
independent-reader boundary is explicit; no engine/provider run is mocked or
represented as a genuine success. Immutable paid323's actual FAIL is separately
retained and checked, including its real execution and response identifiers.
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

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


helper = module("revalidated_idempotence_unit_helper", "scripts/pulso_idempotence.py")
unit = module("revalidated_idempotence_unit_shapes", "tests/test_pulso_idempotence.py")
NOW = datetime(2026, 10, 11, 23, 2, tzinfo=timezone.utc)


@lru_cache(maxsize=1)
def immutable_paid_failure():
    def read(path):
        payload = subprocess.check_output(["git", "show", helper.FINAL_PAID_PRODUCER + ":" + path], cwd=ROOT)
        value = ([json.loads(line) for line in payload.splitlines() if line.strip()]
                 if path.endswith("jsonl") else json.loads(payload))
        return value, helper.digest(payload)
    report, report_sha = read(helper.DEFAULT_REPORT)
    quality, qa_sha = read(helper.DEFAULT_QA)
    telemetry, telemetry_sha = read("data/ai_usage/responses.jsonl")
    execution = report["last_core_execution"]
    start, end = helper.stamp(execution["started_at"]), helper.stamp(execution["finished_at"])
    ids = [event["response_id"] for event in telemetry
           if start <= helper.stamp(event["at"]) <= end and event.get("success") is True]
    assert quality["verdict"] == quality["processing_qa"] == "FAIL"
    assert quality["findings"] and len(ids) == 2
    return dict(execution=execution, quality=quality, telemetry=telemetry, ids=ids,
        hashes={helper.DEFAULT_REPORT: report_sha, helper.DEFAULT_QA: qa_sha,
                "data/ai_usage/responses.jsonl": telemetry_sha})


def unit_revalidated_context():
    context = unit.unit_context()
    original = deepcopy(immutable_paid_failure())
    execution = context["report"]["last_core_execution"]
    month = original["execution"]["budget_after"]["month"]
    execution.update(started_at="2026-10-11T23:00:00Z", finished_at="2026-10-11T23:01:00Z",
        budget_before={"run": unit.counters(), "month": deepcopy(month)},
        budget_after={"run": unit.counters(), "month": deepcopy(month)}, processing_attempts_increased=2)
    selected = execution["processing_selection"]
    urls = context["selection"]["urls"]
    selected.update(ready_selected_urls=urls[:2], skipped_terminal_urls=urls[2:], skipped_not_due_urls=[])
    context["discovery"].update(at="2026-10-11T23:00:30Z", processing_attempts=2)
    held = context["queue"]["unit-fingerprint-112"]
    held.update(status="published", reason="gate_passed", retry_at=None)
    held["raw"]["metadata"]["editorial_assessment"] = {"decision": "published", "reason": "gate_passed"}
    for index in range(2):
        context["queue"][f"unit-fingerprint-{index}"]["attempts"] = 2
    for index in range(5292):
        context["queue"][f"unit-native-{index}"] = {"source": "unit_native_contract", "status": "archived",
                                                      "attempts": 0, "raw": {"unit_index": index}}
    context["ledgers"] = {"2026-10.json": deepcopy(month)}
    context["events"] = deepcopy(original["telemetry"])
    quality = context["processing_qa"]
    quality["checks"].update(actual_ai_budget_delta=helper.budget_delta(execution), actual_fast_response_events=0)
    models = {}
    receipts = {}
    for index, url in enumerate(urls[:2]):
        # These are plainly unit contract fields, never a saved real receipt.
        admission = dict(original_attempts=1, unit_contract_authority=True, actual_processing_evidence=False)
        receipt = dict(original_response_id=original["ids"][index], original_model_output_sha256="unit-unchanged-model",
                       original_model_output_unchanged=True, new_model_request=False,
                       publication_approved=False, unit_contract_receipt=True, actual_processing_evidence=False)
        models[url] = dict(queue_fingerprint=f"unit-fingerprint-{index}",
            original_response_id=original["ids"][index], original_model_output_sha256="unit-unchanged-model",
            admission=admission, receipt=receipt)
        receipts[url] = dict(original_response_id=original["ids"][index], current_response_id=original["ids"][index],
            old_paid_output_reused=True, publication_approved=False, current_evaluation_code=execution["code_sha"],
            current_receipt_sha256=helper.digest(receipt), unit_contract_proof=True, actual_processing_evidence=False)
    lineage = dict(schema_version="pulso_genuine_paid_model_lineage_v1", producer_state_commit=helper.FINAL_PAID_PRODUCER,
        producer_core_checkout=helper.FINAL_PAID_CODE, original_execution=deepcopy(original["execution"]),
        original_runtime_fingerprint=deepcopy(original["execution"]["runtime_fingerprint"]),
        original_budget_delta=helper.budget_delta(original["execution"]), original_successful_response_ids=original["ids"],
        original_processing_qa=original["quality"], original_observed_files=original["hashes"],
        original_paid_qa_promoted=False, same_runtime_fingerprint_as_baseline=False,
        authority={"unit_contract_authority": True, "actual_processing_evidence": False}, models=models)
    stock = dict(commit=execution["code_sha"], file_sha256={"unit_stock": "unit-stock-sha"},
        preserved_terminal_urls={url: dict(queue_fingerprint=f"unit-fingerprint-{index}",
            queue_entry_sha256=helper.digest(context["queue"][f"unit-fingerprint-{index}"]))
            for index, url in enumerate(urls[2:], 2)},
        native_queue_count=5293, native_history_count=897,
        native_queue_sha256=helper.digest({key: item for key, item in context["queue"].items() if item.get("source") != helper.SOURCE}),
        native_history_sha256=helper.digest("unit-native-history-stock"))
    return context, lineage, stock, receipts


@pytest.fixture
def shape(monkeypatch):
    context, lineage, stock, receipts = unit_revalidated_context()
    def independent_boundary(root, *, report, queue, history, telemetry, execution):
        return dict(paid_model_lineage=deepcopy(lineage), launch_stock=deepcopy(stock),
            current_revalidation_receipts=deepcopy(receipts), evaluation_execution=deepcopy(execution),
            actual_budget_delta=helper.budget_delta(execution), publication_approved=False)
    reader = SimpleNamespace(final_paid_origin=lambda root: None,
        verify_final_paid_revalidation=lambda *args, **kwargs: None,
        verify_final_revalidated_execution=independent_boundary)
    monkeypatch.setattr(helper, "final_paid_reader", lambda root: reader)
    baseline = helper.capture_revalidated_baseline(context, now=NOW)
    return context, baseline, reader


def seal(bundle):
    bundle["payload_sha256"] = helper.digest({key: value for key, value in bundle.items() if key != "payload_sha256"})


def second_core(context):
    after = deepcopy(context)
    execution = after["report"]["last_core_execution"]
    execution.update(started_at="2026-10-11T23:03:00Z", finished_at="2026-10-11T23:04:00Z",
                     processing_attempts_increased=0)
    execution["processing_selection"].update(ready_selected_urls=[],
        skipped_terminal_urls=after["selection"]["urls"], skipped_not_due_urls=[])
    after["discovery"].update(at="2026-10-11T23:03:30Z", processing_attempts=0)
    return after


def test_explicit_composite_retains_actual_original_failure_and_separate_runtime(shape):
    context, baseline, _ = shape
    assert baseline["mode"] == helper.REVALIDATED_MODE
    assert baseline["paid_model_lineage"]["original_processing_qa"] == immutable_paid_failure()["quality"]
    assert baseline["paid_model_lineage"]["original_execution"] == immutable_paid_failure()["execution"]
    assert baseline["paid_model_lineage"]["original_runtime_fingerprint"] != baseline["runtime_fingerprint"]
    assert not any(baseline["revalidated_budget_delta"][tier][metric]
                   for tier in ("fast", "deep") for metric in ("attempted", "successful", "failed"))
    assert "paid_budget_delta" not in baseline and "paid_successful_response_ids" not in baseline
    assert len(baseline["selection"]["current_partition"]["terminal_urls"]) == 113
    assert len(baseline["semantic"]["native_queue"]) == 5293
    helper.validate_baseline(baseline)
    assert helper.preflight(baseline, context, now=NOW)["verdict"] == "PASS"


def test_old_mode_still_refuses_zero_ai_current_processing(shape):
    context, _, _ = shape
    with pytest.raises(ValueError, match="positive_genuine_paid_processing_required"):
        helper.capture_baseline(context, now=NOW)


def test_actual_323_failed_qa_never_becomes_revalidated_baseline(shape):
    context, _, _ = shape
    context["processing_qa"] = deepcopy(immutable_paid_failure()["quality"])
    with pytest.raises(ValueError, match="revalidated_processing_qa_pass_required"):
        helper.capture_revalidated_baseline(context, now=NOW)


def test_new_paid_call_cannot_be_hidden_as_zero_ai_revalidation(shape):
    context, _, _ = shape
    execution = context["report"]["last_core_execution"]
    for metric in ("attempted", "successful"):
        execution["budget_after"]["run"]["fast"][metric] += 1
        execution["budget_after"]["month"]["fast"][metric] += 1
    context["ledgers"]["2026-10.json"] = deepcopy(execution["budget_after"]["month"])
    context["events"].append(dict(at="2026-10-11T23:00:45Z", kind="fast", success=True,
                                  response_id="unit-contract-new-response-never-real-evidence"))
    with pytest.raises(ValueError, match="revalidated_baseline_must_use_zero_new_ai"):
        helper.capture_revalidated_baseline(context, now=NOW)


@pytest.mark.parametrize("attack,reason", [
    (lambda c: c["processing_qa"].update(findings=[{"unit_failure": True}]), "qa_pass_required"),
    (lambda c: c["report"]["last_core_execution"].update(processing_attempts_increased=0), "two_revalidation"),
    (lambda c: c["discovery"].update(processing_attempts=3), "two_revalidation"),
    (lambda c: c["processing_qa"]["checks"].update(actual_fast_response_events=2), "not_bound_to_actual"),
    (lambda c: c["report"]["last_core_execution"]["processing_selection"].update(ready_selected_urls=[]), "two_reuse"),
    (lambda c: c["queue"]["unit-fingerprint-2"].update(status="retry", reason="analysis_unavailable"), "non_editorial"),
    (lambda c: c["queue"]["unit-fingerprint-2"].update(status="archived"), "all113_terminal"),
])
def test_capture_denies_missing_genuine_final_observations(shape, attack, reason):
    context, _, _ = shape
    attack(context)
    with pytest.raises(ValueError, match=reason):
        helper.capture_revalidated_baseline(context, now=NOW)


@pytest.mark.parametrize("attack,reason", [
    (lambda b: b["paid_model_lineage"].update(original_paid_qa_promoted=True), "failure_erased_or_promoted"),
    (lambda b: b["paid_model_lineage"]["original_processing_qa"].update(processing_qa="PASS"), "failure_erased_or_promoted"),
    (lambda b: b["paid_model_lineage"].update(same_runtime_fingerprint_as_baseline=True), "failure_erased_or_promoted"),
    (lambda b: b.update(paid_successful_response_ids=["retagged-unit-response"]), "failure_erased_or_promoted"),
    (lambda b: b["paid_model_lineage"].update(original_successful_response_ids=["forged-unit-1", "forged-unit-2"]), "lineage_invalid"),
    (lambda b: b["paid_model_lineage"]["original_runtime_fingerprint"]["files"].update(unit_changed_original="unit-forgery"), "lineage_invalid"),
    (lambda b: next(iter(b["paid_model_lineage"]["models"].values()))["receipt"].update(original_model_output_sha256="changed-model"), "lineage_invalid"),
    (lambda b: b["baseline_execution"].update(engine_completed=False), "execution_not_genuine"),
    (lambda b: b["launch_stock"].update(commit="f" * 40), "execution_binding_invalid"),
    (lambda b: b["launch_stock"].update(native_queue_count=0), "native_stock_proof_missing"),
    (lambda b: b["selection"]["current_partition"].update(held_not_due_urls=["unit-hold"]), "native_stock_proof_missing"),
    (lambda b: b["current_revalidation_receipts"].clear(), "two_current_receipts_missing"),
])
def test_resealed_baseline_cannot_relabel_paid_failure_or_erase_scope(shape, attack, reason):
    _, baseline, _ = shape
    attack(baseline)
    seal(baseline)
    with pytest.raises(ValueError, match=reason):
        helper.validate_baseline(baseline)


def test_independent_composite_api_is_required_before_a_baseline(shape):
    context, _, reader = shape
    del reader.verify_final_revalidated_execution
    with pytest.raises(ValueError, match="independent_final_revalidated_execution_reader_unavailable"):
        helper.capture_revalidated_baseline(context, now=NOW)


@pytest.mark.parametrize("field", ["paid_model_lineage", "launch_stock", "current_revalidation_receipts"])
def test_preflight_rereads_immutable_origin_and_exact_current_receipts(shape, field):
    context, baseline, _ = shape
    target = (next(iter(baseline[field].values())) if field == "current_revalidation_receipts"
              else baseline[field])
    target["unit_tamper"] = "recomputed-payload-cannot-authorize-this"
    seal(baseline)
    with pytest.raises(ValueError, match="lineage_changed"):
        helper.preflight(baseline, context, now=NOW)


def test_replay_contract_checks_all_native_queue_objects_and_zero_attempts(shape):
    context, baseline, _ = shape
    after = second_core(context)
    result = helper.compare(baseline, after, now=NOW.replace(minute=5))
    assert result["verdict"] == "PASS", result["findings"]
    after["queue"]["unit-native-0"]["raw"]["unit_index"] = "changed-native-record"
    result = helper.compare(baseline, after, now=NOW.replace(minute=5))
    assert "changed_native_queue" in {row["code"] for row in result["findings"]}
    after = second_core(context)
    after["report"]["last_core_execution"]["processing_attempts_increased"] = 2
    result = helper.compare(baseline, after, now=NOW.replace(minute=5))
    assert "second_core_processing_attempts_nonzero" in {row["code"] for row in result["findings"]}


def test_changed_independent_lineage_denies_replay_even_if_current_state_is_identical(shape):
    context, baseline, reader = shape
    original = reader.verify_final_revalidated_execution
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        result["paid_model_lineage"]["original_processing_qa"]["findings"] = []
        return result
    reader.verify_final_revalidated_execution = changed
    result = helper.compare(baseline, second_core(context), now=NOW.replace(minute=5))
    assert "original_paid_or_revalidated_execution_lineage_invalid" in {row["code"] for row in result["findings"]}
