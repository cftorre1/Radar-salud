"""Synthetic execution bookkeeping bound to all 113 real reviewed bodies.

These tests do not execute AI or claim a genuine processing run. They try to
falsify the independent reader's membership and immutable evidence checks.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("pulso_selection_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


PRE_REDACTION = "3aa26270bf6c78910b6aed24e1a91f1dfd48e75c"  # last commit with Pulso bodies in the queue


@pytest.fixture
def selection_evidence(tmp_path):
    cohort = json.loads((ROOT / qa.PROCESSING_COHORT_PATH).read_bytes())
    references = [dict(path=qa.PROCESSING_COHORT_PATH)] + [cohort["inputs"][key] for key in
        ("frozen_control", "independent_primary_review", "expanded_negative_review")]
    for reference in references:
        path = tmp_path / reference["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / reference["path"]).read_bytes())
    # The reviewed bodies predate the rights redaction (28-oct-2026): replay the queue as it was then.
    import subprocess
    current = json.loads(subprocess.run(["git", "show", PRE_REDACTION + ":data/state/pending_queue.json"],
                                        cwd=ROOT, capture_output=True, check=True).stdout)
    queue, before = {}, []
    for original in cohort["items"]:
        key = original["queue_fingerprint"]
        item = deepcopy(current[key])
        item.update(status="pending", attempts=0)
        queue[key] = item
        before.append(dict(url=original["url"], fingerprint=key, status="pending", attempts=0))
    outside = "https://www.latercera.com/nacional/noticia/synthetic-outside-cohort/"
    queue["outside"] = dict(source=qa.SOURCE, status="pending", attempts=3,
                            raw=dict(url=outside, metadata={}))
    before.append(dict(url=outside, fingerprint="outside", status="pending", attempts=3))
    selected = dict(source=qa.SOURCE, reason="explicit_queue_selection", sha256=qa.PROCESSING_COHORT_SHA256,
        file_sha256=qa.PROCESSING_COHORT_SHA256, selected_urls=cohort["urls"], selected_url_count=113,
        matched_existing_url_count=113, ready_selected_urls=cohort["urls"], skipped_terminal_urls=[],
        skipped_not_due_urls=[], skipped_in_progress_urls=[], outside_selection_pending_url_count=1,
        outside_selection_pending_reason="processing_not_attempted:explicit_queue_selection_excluded")
    report = dict(last_core_execution=dict(processing_selection=selected), baseline_queue=before,
        matrix=[dict(url=outside, exact_reason="processing_not_attempted:explicit_queue_selection_excluded",
                     processing_selection_evidence=dict(sha256=qa.PROCESSING_COHORT_SHA256,
                                                        selected=False, source=qa.SOURCE))])
    return dict(report=report, discovery=dict(processing_selection=deepcopy(selected)), queue=queue,
                root=tmp_path, enumerated=set(cohort["urls"]), cohort=cohort)


def run(value):
    return qa.verify_processing_selection(**{key: item for key, item in value.items() if key != "cohort"})


def mutate_selection(value, change):
    change(value["report"]["last_core_execution"]["processing_selection"])
    value["discovery"]["processing_selection"] = deepcopy(value["report"]["last_core_execution"]["processing_selection"])


def test_all113_body_reviewed_identities_validate_without_publication_quota(selection_evidence):
    checks, findings = run(selection_evidence)
    assert findings == []
    assert checks == dict(sha256=qa.PROCESSING_COHORT_SHA256, selected_urls=113,
        independent_primary_controls=79, independent_material_cases=20,
        independent_uncertain_cases=17, outside_pending_preserved=1, publication_quota=False)


@pytest.mark.parametrize("attack,expected", [
    ("unbound", "processing_selection_not_bound_to_actual_core"),
    ("sha", "processing_selection_recorded_manifest_mismatch"),
    ("missing_core", "processing_selection_urls_not_returned_by_current_core"),
    ("body", "processing_selection_reviewed_original_body_or_day_changed"),
    ("date", "processing_selection_reviewed_original_body_or_day_changed"),
    ("duplicate_identity", "processing_selection_durable_identity_missing_or_ambiguous"),
    ("duplicate_partition", "processing_selection_ready_partition_invalid"),
    ("null_partition", "processing_selection_ready_partition_invalid"),
    ("outside_attempt", "processing_selection_processed_outside_cohort"),
    ("outside_reason_proof", "processing_selection_excluded_reason_without_membership_proof"),
    ("outside_count", "processing_selection_outside_pending_count_or_reason_unproven"),
])
def test_false_membership_or_modified_originals_fail(selection_evidence, attack, expected):
    value = selection_evidence
    first = value["cohort"]["items"][0]
    if attack == "unbound":
        value["discovery"]["processing_selection"] = None
    elif attack == "sha":
        mutate_selection(value, lambda item: item.update(sha256="0" * 64))
    elif attack == "missing_core":
        value["enumerated"].remove(first["url"])
    elif attack == "body":
        value["queue"][first["queue_fingerprint"]]["raw"]["metadata"]["page_text"] += " Forjado."
    elif attack == "date":
        value["queue"][first["queue_fingerprint"]]["raw"]["event_date"] = "2026-10-11"
    elif attack == "duplicate_identity":
        value["queue"]["duplicate"] = deepcopy(value["queue"][first["queue_fingerprint"]])
    elif attack == "duplicate_partition":
        mutate_selection(value, lambda item: item["skipped_not_due_urls"].append(first["url"]))
    elif attack == "null_partition":
        mutate_selection(value, lambda item: item.update(skipped_terminal_urls=None))
    elif attack == "outside_attempt":
        value["queue"]["outside"]["attempts"] = 4
    elif attack == "outside_reason_proof":
        value["report"]["matrix"][0]["processing_selection_evidence"]["selected"] = True
    elif attack == "outside_count":
        mutate_selection(value, lambda item: item.update(outside_selection_pending_url_count=0))
    assert expected in {item["code"] for item in run(value)[1]}


@pytest.mark.parametrize("reset", [False, True])
def test_terminal_skip_preserves_actual_preexisting_terminal_bookkeeping(selection_evidence, reset):
    value = selection_evidence
    first = value["cohort"]["items"][0]
    value["report"]["baseline_queue"][0].update(status="rejected", attempts=2)
    value["queue"][first["queue_fingerprint"]].update(status="pending" if reset else "rejected", attempts=2)
    def skip(selected):
        selected["ready_selected_urls"].remove(first["url"])
        selected["skipped_terminal_urls"].append(first["url"])
    mutate_selection(value, skip)
    assert ("processing_selection_terminal_reset_or_skip_unproven" in {item["code"] for item in run(value)[1]}) is reset


@pytest.mark.parametrize("reference", [qa.PROCESSING_COHORT_PATH,
    "data/audits/pulso_all79_primary_independent_review_2026_10_11.json"])
def test_mutable_denominator_preserving_review_or_cohort_replacement_is_rejected(selection_evidence, reference):
    path = selection_evidence["root"] / reference
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    assert "processing_selection_immutable_cohort_unverified" in {item["code"] for item in run(selection_evidence)[1]}
