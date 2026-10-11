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
independent_qa = module("revalidated_idempotence_independent_qa", "scripts/qa_pulso_recovery.py")
qa_units = module("revalidated_idempotence_prior_qa_shapes", "tests/test_pulso_idempotence_qa.py")
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


@pytest.fixture
def independent_replay(tmp_path, monkeypatch):
    """Full reader integration; only the already-tested composite API is fixed.

    Publisher bodies, the frozen113 cohort, implementation bytes and review
    files are real. Future outcomes/native rows are openly synthetic. The
    original paid323 execution, failed QA and telemetry remain immutable real
    inputs. Nothing here is saved as actual runtime acceptance evidence.
    """
    previous = qa_units.replay.__wrapped__(tmp_path)
    cohort = json.loads((tmp_path / independent_qa.PROCESSING_COHORT_PATH).read_bytes())
    context, lineage, stock, receipts = unit_revalidated_context()
    context["selection"] = cohort
    context["queue"] = deepcopy(previous["queue"])
    context["report"]["matrix"] = deepcopy(previous["report"]["matrix"])
    for index in range(5293):
        context["queue"][f"integration-unit-native-{index}"] = dict(
            source="integration_unit_native", status="archived", attempts=0,
            raw=dict(unit_only=True, url=f"https://unit-native.invalid/record/{index}/"))
    signals = [dict(source_url=f"https://unit-native.invalid/record/{index}/", event_date="2026-10-01",
                    source_type="official", source_name="Explicit synthetic native unit",
                    source_record_id=f"unit-native-record-{index}", what_happened="Synthetic contract copy only.")
               for index in range(897)]
    context["history"] = {"signals": signals}
    context["feed"] = {"signals": deepcopy(signals)}
    execution = context["report"]["last_core_execution"]
    execution["code_sha"] = "a" * 40
    selection = execution["processing_selection"]
    selection.update(sha256=independent_qa.PROCESSING_COHORT_SHA256,
        file_sha256=independent_qa.PROCESSING_COHORT_SHA256, selected_urls=cohort["urls"],
        ready_selected_urls=cohort["urls"][:2], skipped_terminal_urls=cohort["urls"][2:])
    context["observed_files"][helper.DEFAULT_SELECTION] = independent_qa.PROCESSING_COHORT_SHA256
    context["runtime_fingerprint"] = helper.runtime_fingerprint(tmp_path)
    context["recorded_core_runtime_fingerprint"] = deepcopy(context["runtime_fingerprint"])
    execution["runtime_fingerprint"] = deepcopy(context["runtime_fingerprint"])
    old_models, old_receipts = list(lineage["models"].values()), list(receipts.values())
    lineage["models"], receipts = {}, {}
    cohort_items = {row["url"]: row for row in cohort["items"]}
    for index, url in enumerate(cohort["urls"][:2]):
        key = cohort_items[url]["queue_fingerprint"]
        context["queue"][key]["attempts"] = 2
        row = deepcopy(old_models[index])
        row["queue_fingerprint"] = key
        lineage["models"][url] = row
        receipts[url] = dict(old_receipts[index], current_evaluation_code=execution["code_sha"])
    references = {cohort["inputs"][key]["path"]: cohort["inputs"][key]["sha256"]
                  for key in helper.IMMUTABLE_COHORT_INPUTS}
    for read_proofs in (independent_qa.paid_revalidation_proof_files, independent_qa.current_paid_proof_files,
                        independent_qa.followup_paid_proof_files, independent_qa.final_paid_proof_files):
        references.update(read_proofs(ROOT))
    for relative in references:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    documents = helper.incremental_proof_files(tmp_path, context["queue"])
    references.update({relative: helper.digest((tmp_path / relative).read_bytes()) for relative in documents})
    context["referenced_proof_files"] = references
    context["incremental_review_files"] = documents
    context["processing_qa"]["checks"]["processing_selection"].update(sha256=independent_qa.PROCESSING_COHORT_SHA256)
    current_rows = helper.source_queue(context["queue"])
    stock.update(commit=execution["code_sha"], preserved_terminal_urls={
        url: dict(queue_fingerprint=current_rows[url]["fingerprint"],
                  queue_entry_sha256=helper.digest(context["queue"][current_rows[url]["fingerprint"]]))
        for url in cohort["urls"][2:]},
        native_queue_sha256=helper.digest({key: item for key, item in context["queue"].items() if item.get("source") != helper.SOURCE}),
        native_history_sha256=helper.digest(signals))
    lineage["authority"] = independent_qa.final_paid_proof_files(tmp_path)
    qa_units.write_context(tmp_path, context)
    observed_composite = dict(paid_model_lineage=deepcopy(lineage), launch_stock=deepcopy(stock),
        current_revalidation_receipts=deepcopy(receipts), evaluation_execution=deepcopy(execution),
        actual_budget_delta=helper.budget_delta(execution), publication_approved=False)
    def fixed_composite(*args, **kwargs):
        assert kwargs["execution"] == observed_composite["evaluation_execution"]
        return deepcopy(observed_composite)
    monkeypatch.setattr(independent_qa, "verify_final_revalidated_execution", fixed_composite)
    partition = dict(terminal_urls=sorted(cohort["urls"]), held_not_due_urls=[])
    baseline = dict(schema_version=helper.SCHEMA, mode=helper.REVALIDATED_MODE, read_only=True,
        baseline_execution=deepcopy(execution), runtime_fingerprint=deepcopy(context["runtime_fingerprint"]),
        revalidated_budget_delta=helper.budget_delta(execution), revalidated_successful_response_ids=[],
        paid_model_lineage=deepcopy(lineage), launch_stock=deepcopy(stock), current_revalidation_receipts=deepcopy(receipts),
        selection=dict(path=helper.DEFAULT_SELECTION, sha256=independent_qa.PROCESSING_COHORT_SHA256,
                       urls=cohort["urls"], count=113, current_partition=partition),
        processing_qa=deepcopy(context["processing_qa"]), semantic=helper.revalidated_snapshot(context))
    seal(baseline)
    helper.validate_baseline(baseline)
    after = second_core(context)
    qa_units.write_context(tmp_path, after)
    proof = dict(schema_version=helper.SCHEMA, mode="after_genuine_core", read_only=True, verdict="PASS", findings=[],
        baseline_sha256=baseline["payload_sha256"], runtime_fingerprint=deepcopy(context["runtime_fingerprint"]),
        actual_budget_delta=helper.budget_delta(after["report"]["last_core_execution"]), selected_partition=partition,
        observed_files=deepcopy(after["observed_files"]))
    evidence = dict(baseline=baseline, proof=proof, root=tmp_path, report=after["report"], discovery=after["discovery"],
                    queue=after["queue"], history=after["history"]["signals"], snapshot=after["feed"], telemetry=after["events"])
    return evidence


def test_actual_independent_reader_routes_composite_paid_window_and_final_zero_ai(independent_replay):
    evidence = independent_replay
    baseline = evidence["baseline"]
    checked, findings = independent_qa.verify_genuine_idempotence(**evidence)
    assert findings == [], findings
    assert checked["paid_successful_response_ids"] == 2
    assert checked["actual_ai_calls"] == checked["actual_attempts"] == 0
    assert baseline["processing_qa"]["checks"]["actual_fast_response_events"] == 0
    assert baseline["paid_model_lineage"]["original_processing_qa"]["processing_qa"] == "FAIL"
    assert baseline["paid_model_lineage"]["original_runtime_fingerprint"] != baseline["runtime_fingerprint"]
    assert baseline["runtime_fingerprint"] == evidence["report"]["last_core_execution"]["runtime_fingerprint"]
    start = helper.stamp(baseline["baseline_execution"]["started_at"])
    end = helper.stamp(baseline["baseline_execution"]["finished_at"])
    assert not [event for event in evidence["telemetry"] if start <= helper.stamp(event["at"]) <= end]
    assert baseline["paid_model_lineage"]["original_successful_response_ids"] == immutable_paid_failure()["ids"]
    assert len(baseline["semantic"]["native_queue"]) == 5293
    assert len(evidence["history"]) == 897
    assert independent_qa.FINAL_PAID_PATH in baseline["semantic"]["referenced_proof_files"]


@pytest.mark.parametrize("attack,reason", [
    ("paid_fingerprint_retag", "composite_original_paid_or_real_revalidation_proof_changed"),
    ("original_paid_fail_erased", "composite_original_paid_or_real_revalidation_proof_changed"),
    ("current_quality_claims_two_ai", "paid_qa_not_bound_to_actual_ledger_and_cohort"),
    ("current_fingerprint_claims_paid_code", "genuine_paid_and_replay_implementation_or_policy_changed"),
    ("native_object_changed", "replay_changed_native_connector_queue"),
    ("final2_reader_bytes_changed", "final_paid_current_semantic_reader_changed"),
])
def test_independent_composite_reader_denies_retagged_lineage_and_changed_stocks(independent_replay, attack, reason):
    evidence = independent_replay
    baseline = evidence["baseline"]
    if attack == "paid_fingerprint_retag":
        baseline["paid_model_lineage"]["original_execution"]["runtime_fingerprint"] = deepcopy(baseline["runtime_fingerprint"])
    elif attack == "original_paid_fail_erased":
        baseline["paid_model_lineage"]["original_processing_qa"].update(processing_qa="PASS", verdict="PASS", findings=[])
    elif attack == "current_quality_claims_two_ai":
        baseline["processing_qa"]["checks"]["actual_fast_response_events"] = 2
    elif attack == "current_fingerprint_claims_paid_code":
        fingerprint = deepcopy(baseline["paid_model_lineage"]["original_runtime_fingerprint"])
        baseline["runtime_fingerprint"] = fingerprint
        evidence["proof"]["runtime_fingerprint"] = deepcopy(fingerprint)
        evidence["report"]["last_core_execution"]["runtime_fingerprint"] = deepcopy(fingerprint)
    elif attack == "native_object_changed":
        evidence["queue"]["integration-unit-native-0"]["raw"]["unit_only"] = "changed whole native object"
    else:
        manifest = json.loads((evidence["root"] / independent_qa.FINAL_PAID_PATH).read_bytes())
        path = evidence["root"] / manifest["semantic_references"][0]["path"]
        path.write_bytes(path.read_bytes() + b" ")
    seal(baseline)
    evidence["proof"]["baseline_sha256"] = baseline["payload_sha256"]
    checked, findings = independent_qa.verify_genuine_idempotence(**evidence)
    assert checked == {}
    assert findings[0]["reason"] == reason
