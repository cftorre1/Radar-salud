"""Adversarial compact-proof tests; unit response IDs are explicitly synthetic.

Temporary snapshots retain the real frozen 113 body-reviewed identities. They
exercise the independent reader without executing an engine or provider call.
"""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
qa = module("idempotence_independent_qa", ROOT / "scripts/qa_pulso_recovery.py")
helper = module("idempotence_helper_for_unit_shapes", ROOT / "scripts/pulso_idempotence.py")
unit = module("unit_idempotence_shapes", ROOT / "tests/test_pulso_idempotence.py")
NOW = datetime(2026, 10, 11, 14, 5, tzinfo=timezone.utc)


def write_context(root, context):
    contents = {helper.DEFAULT_REPORT: context["report"], "data/state/discovery_run.json": context["discovery"],
        "data/state/pending_queue.json": context["queue"], "data/history/superintendencia_signals.json": context["history"],
        "web/data/radar_today.json": context["feed"], helper.DEFAULT_SELECTION: context["selection"]}
    for path, value in contents.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if path != helper.DEFAULT_SELECTION:
            target.write_text(json.dumps(value, ensure_ascii=False) + "\n")
        context["observed_files"][path] = qa.digest(target.read_bytes())
    for name, value in context["ledgers"].items():
        path = "data/ai_usage/" + name
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value) + "\n")
        context["observed_files"][path] = qa.digest(target.read_bytes())
    target = root / "data/ai_usage/responses.jsonl"
    target.write_text("".join(json.dumps(row) + "\n" for row in context["events"]))
    context["observed_files"]["data/ai_usage/responses.jsonl"] = qa.digest(target.read_bytes())


@pytest.fixture
def replay(tmp_path):
    fingerprint = helper.runtime_fingerprint(ROOT)
    cohort_raw = (ROOT / qa.PROCESSING_COHORT_PATH).read_bytes()
    cohort = json.loads(cohort_raw)
    paths = set(fingerprint["files"]) | {qa.PROCESSING_COHORT_PATH}
    paths.update(cohort["inputs"][key]["path"] for key in
                 ("frozen_control", "independent_primary_review", "expanded_negative_review"))
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    context = unit.unit_context()
    context["selection"] = cohort
    context["observed_files"][helper.DEFAULT_SELECTION] = qa.PROCESSING_COHORT_SHA256
    context["runtime_fingerprint"] = context["recorded_core_runtime_fingerprint"] = helper.runtime_fingerprint(tmp_path)
    selected = context["report"]["last_core_execution"]["processing_selection"]
    selected.update(sha256=qa.PROCESSING_COHORT_SHA256, file_sha256=qa.PROCESSING_COHORT_SHA256,
                    selected_urls=cohort["urls"], ready_selected_urls=cohort["urls"])
    execution = context["report"]["last_core_execution"]
    execution.update(code_sha="a" * 40, runtime_fingerprint=deepcopy(context["runtime_fingerprint"]))
    current = json.loads((ROOT / "data/state/pending_queue.json").read_bytes())
    context["queue"] = {}
    context["report"]["matrix"] = []
    for original in cohort["items"]:
        key = original["queue_fingerprint"]
        item = deepcopy(current[key])
        item.update(status="rejected", attempts=1)
        item["raw"]["metadata"].pop("editorial_review", None)
        item["raw"]["metadata"]["editorial_assessment"] = dict(decision="rejected", reason="synthetic_unit_rejection")
        context["queue"][key] = item
        context["report"]["matrix"].append(dict(url=original["url"], current_core_detected=True,
            current_core_verified_health=True, publication_date_verified=True, publication_date=original["publication_date"],
            current_discovery_trace=[dict(article_body_sha256=original["body_sha256"])]))
    context["history"] = {"signals": []}
    context["feed"]["signals"] = []
    context["processing_qa"]["checks"]["processing_selection"].update(sha256=qa.PROCESSING_COHORT_SHA256)
    context["referenced_proof_files"] = {cohort["inputs"][key]["path"]: cohort["inputs"][key]["sha256"]
        for key in ("frozen_control", "independent_primary_review", "expanded_negative_review")}
    write_context(tmp_path, context)
    baseline = helper.capture_baseline(context, now=NOW.replace(minute=2))
    after = unit.unit_second_core(context)
    after["report"]["last_core_execution"]["processing_selection"].update(
        skipped_terminal_urls=cohort["urls"], skipped_not_due_urls=[])
    write_context(tmp_path, after)
    proof = helper.compare(baseline, after, now=NOW)
    assert proof["verdict"] == "PASS", proof["findings"]
    return dict(baseline=baseline, proof=proof, root=tmp_path, report=after["report"], discovery=after["discovery"],
        queue=after["queue"], history=[], snapshot=after["feed"], telemetry=after["events"])


def test_reader_recomputes_all113_queue_ledger_and_response_observations(replay):
    checked, failures = qa.verify_genuine_idempotence(**replay)
    assert failures == []
    assert checked["selected_urls"] == 113
    assert checked["paid_successful_response_ids"] == 1
    assert checked["actual_ai_calls"] == checked["actual_attempts"] == 0


@pytest.mark.parametrize("attack", ["missing_baseline", "payload", "failed_paid_qa", "wrong_paid_cohort",
    "paid_id", "new_response", "attempt_reset", "primary_day", "code_bytes", "proof_label", "current_file",
    "omitted_policy", "independent_review_bytes"])
def test_zero_ai_or_mutable_pass_label_never_replaces_genuine_bound_paid_baseline(replay, attack):
    if attack == "missing_baseline":
        replay["baseline"] = None
    elif attack == "payload":
        replay["baseline"]["semantic"]["history"]["forged"] = "0" * 64
    elif attack in {"failed_paid_qa", "wrong_paid_cohort", "paid_id"}:
        baseline = replay["baseline"]
        if attack == "failed_paid_qa":
            baseline["processing_qa"]["processing_qa"] = "FAIL"
        elif attack == "wrong_paid_cohort":
            baseline["baseline_execution"]["processing_selection"]["sha256"] = "0" * 64
        else:
            baseline["paid_successful_response_ids"] = ["forged-unit-response-id"]
        baseline["payload_sha256"] = qa.object_digest({k: v for k, v in baseline.items() if k != "payload_sha256"})
        replay["proof"]["baseline_sha256"] = baseline["payload_sha256"]
    elif attack == "new_response":
        replay["telemetry"].append(dict(at="2026-10-11T14:03:30Z", kind="fast", success=True,
                                       response_id="new-synthetic-unit-response"))
    elif attack == "attempt_reset":
        next(iter(replay["queue"].values()))["attempts"] = 0
    elif attack == "primary_day":
        replay["report"]["matrix"][0]["publication_date"] = "2026-10-10"
    elif attack == "code_bytes":
        path = replay["root"] / "src/radar_salud/pulso_source.py"
        path.write_bytes(path.read_bytes() + b"\n# unit implementation changed\n")
    elif attack == "proof_label":
        replay["proof"]["findings"] = [dict(code="changed_history")]
    elif attack == "current_file":
        path = replay["root"] / "web/data/radar_today.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif attack == "omitted_policy":
        fingerprint = replay["baseline"]["runtime_fingerprint"]
        fingerprint["files"].pop("config/source_quality_gate.json")
        fingerprint["sha256"] = qa.object_digest(fingerprint["files"])
        replay["baseline"]["baseline_execution"]["runtime_fingerprint"] = deepcopy(fingerprint)
        replay["report"]["last_core_execution"]["runtime_fingerprint"] = deepcopy(fingerprint)
        replay["proof"]["runtime_fingerprint"] = deepcopy(fingerprint)
        replay["baseline"]["payload_sha256"] = qa.object_digest({k: v for k, v in replay["baseline"].items() if k != "payload_sha256"})
        replay["proof"]["baseline_sha256"] = replay["baseline"]["payload_sha256"]
    elif attack == "independent_review_bytes":
        cohort = json.loads((replay["root"] / qa.PROCESSING_COHORT_PATH).read_bytes())
        path = replay["root"] / cohort["inputs"]["independent_primary_review"]["path"]
        path.write_bytes(path.read_bytes() + b" ")
    checked, failures = qa.verify_genuine_idempotence(**replay)
    assert checked == {}
    assert failures[0]["code"] == "genuine_idempotent_replay_not_verified"
