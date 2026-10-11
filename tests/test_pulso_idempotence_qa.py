"""Adversarial compact-proof tests; unit response IDs are explicitly synthetic.

Temporary snapshots retain the real frozen 113 body-reviewed identities. They
exercise the independent reader without executing an engine or provider call.
"""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
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
PRE_FOCUS_FIXTURE = ROOT / "tests/fixtures/pulso_idempotence_pre_focus_real.json.gz"
PRE_FOCUS_GZIP_SHA256 = "55e47cabf0f7f40005f922b0a18912c0ad758e3df721f249a960825f4e756ef9"
PRE_FOCUS_RAW_SHA256 = "39a53d61e02320779cb92f34c3c5bcad1c0c5a528a5a5219a29b2530b9237c2e"


def immutable_pre_focus_queue(cohort):
    """Real primary input stays fixed as live editorial outcomes evolve.

    These 113 complete rows were copied from the committed checkout before
    the genuine focused run. The statuses below are explicitly synthetic unit
    outcomes; current deferred/published/rejected records remain untouched.
    """
    encoded = PRE_FOCUS_FIXTURE.read_bytes()
    assert qa.digest(encoded) == PRE_FOCUS_GZIP_SHA256
    raw = gzip.decompress(encoded)
    assert qa.digest(raw) == PRE_FOCUS_RAW_SHA256
    document = json.loads(raw)
    assert document["original_commit"] == "81b844a654533891ad0923a40dfedfda03c17fa3"
    assert document["cohort_sha256"] == qa.PROCESSING_COHORT_SHA256
    queue = document["queue"]
    assert document["count"] == len(queue) == 113
    assert set(queue) == {row["queue_fingerprint"] for row in cohort["items"]}
    for row in cohort["items"]:
        item = queue[row["queue_fingerprint"]]
        primary = item["raw"]
        body = primary["metadata"]["page_text"]
        assert primary["url"] == row["url"]
        assert primary["event_date"] == row["publication_date"]
        assert qa.digest(body.encode()) == row["body_sha256"]
        assert len(body) == row["body_characters"]
    return queue


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
    paths = set(fingerprint["files"]) | {qa.PROCESSING_COHORT_PATH, qa.INCREMENTAL_REVIEW_PATH,
                                       qa.INCREMENTAL_ADDENDUM_PATH}
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
    current = immutable_pre_focus_queue(cohort)
    context["queue"] = {}
    context["report"]["matrix"] = []
    for original in cohort["items"]:
        key = original["queue_fingerprint"]
        item = deepcopy(current[key])
        item.update(status="rejected", attempts=1)
        if "chomali-destaca-alza-de-47" in original["url"]:
            from radar_salud.models import RawItem
            from radar_salud.pulso_incremental_review import apply_incremental_review
            candidate = RawItem(**deepcopy(item["raw"]))
            candidate.metadata["article_body_complete"] = True
            assert apply_incremental_review(candidate)
            item["raw"] = deepcopy(candidate.__dict__)
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
    if any(item["raw"]["metadata"].get("incremental_review") for item in context["queue"].values()):
        context["referenced_proof_files"][qa.INCREMENTAL_REVIEW_PATH] = qa.INCREMENTAL_REVIEW_SHA256
    if any(item["raw"]["metadata"].get("incremental_review_addendum") for item in context["queue"].values()):
        context["referenced_proof_files"][qa.INCREMENTAL_ADDENDUM_PATH] = qa.INCREMENTAL_ADDENDUM_SHA256
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


def test_synthetic_replay_does_not_read_live_editorial_queue(monkeypatch, tmp_path):
    original_read = Path.read_bytes
    live_queue = ROOT / "data/state/pending_queue.json"
    def reject_live_queue_read(path):
        if path == live_queue:
            raise AssertionError("A new real model outcome cannot redefine this unit fixture")
        return original_read(path)
    monkeypatch.setattr(Path, "read_bytes", reject_live_queue_read)
    evidence = replay.__wrapped__(tmp_path)
    checked, failures = qa.verify_genuine_idempotence(**evidence)
    assert failures == []
    assert checked["selected_urls"] == 113


def test_reader_recomputes_all113_queue_ledger_and_response_observations(replay):
    checked, failures = qa.verify_genuine_idempotence(**replay)
    assert failures == []
    assert checked["selected_urls"] == 113
    assert checked["paid_successful_response_ids"] == 1
    assert checked["actual_ai_calls"] == checked["actual_attempts"] == 0


@pytest.mark.parametrize("field,value", [
    ("pulso_editorial_proof_validation", {"decision": "deferred", "reason": "renamed_editorial_retry"}),
    ("primary_item_binding", {"verified": False}),
    ("analysis_input_complete", False), ("article_body_complete", False),
])
def test_identical_invalid_proof_in_paid_baseline_and_replay_is_not_accepted(replay, field, value):
    item = next(iter(replay["queue"].values()))
    item["raw"]["metadata"][field] = value
    baseline = replay["baseline"]
    # Even a self-consistent compact snapshot and a claimed earlier QA PASS
    # cannot make explicit failed processing evidence valid. The helper below
    # constructs the test snapshot only; the QA reader must judge it itself.
    baseline["semantic"]["source_queue"] = helper.source_queue(replay["queue"])
    baseline["payload_sha256"] = qa.object_digest({k: v for k, v in baseline.items() if k != "payload_sha256"})
    replay["proof"]["baseline_sha256"] = baseline["payload_sha256"]
    checked, failures = qa.verify_genuine_idempotence(**replay)
    assert checked == {}
    assert failures[0]["reason"] == "replay_selected_processing_evidence_unresolved"


def test_unverified_duplicate_hold_map_cannot_grant_replay_acceptance(replay):
    baseline = replay["baseline"]
    baseline["semantic"]["reviewed_hold_bindings"] = {"synthetic-held-url": {"target_url": "synthetic-target"}}
    baseline["payload_sha256"] = qa.object_digest({k: v for k, v in baseline.items() if k != "payload_sha256"})
    replay["proof"]["baseline_sha256"] = baseline["payload_sha256"]
    checked, failures = qa.verify_genuine_idempotence(**replay)
    assert checked == {}
    assert failures[0]["reason"] == "reviewed_duplicate_hold_requires_independent_target_validation"


@pytest.mark.parametrize("relative", [qa.INCREMENTAL_REVIEW_PATH, qa.INCREMENTAL_ADDENDUM_PATH])
def test_incremental_review_original_file_is_immutable_in_replay(replay, relative):
    path = replay["root"] / relative
    path.write_bytes(path.read_bytes() + b" ")
    checked, failures = qa.verify_genuine_idempotence(**replay)
    assert checked == {}
    assert failures[0]["reason"] == "incremental_addendum_immutable_review_changed"


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
