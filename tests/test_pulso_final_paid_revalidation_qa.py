"""Independent final-two QA; processor envelopes are units, not actual-core proof.

Both model outputs and their failed paid producer are real immutable inputs.
The tests forbid publisher/model access and only synthesize the later local
evaluation window. They never invent a paid Response or promote the old FAIL.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "final_paid_independent_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
URLS = [row["url"] for row in json.loads((ROOT / qa.FINAL_PAID_PATH).read_text())["rows"]]
GUARD_PATH = "src/radar_salud/pulso_editorial_proof.py"


@pytest.fixture(scope="module")
def actual_origin():
    return qa.final_paid_origin(ROOT)


def fresh(entry):
    raw = deepcopy(entry["raw"])
    claims = (
        "editorial_code_repair_admission", "paid_guard_revalidation_admission",
        "paid_guard_revalidation_receipt", "paid_guard_new_fast_attempt_receipts",
        qa.CURRENT_PAID_STAMP, qa.CURRENT_PAID_RECEIPT, qa.CURRENT_PAID_ATTEMPTS,
        qa.FOLLOWUP_PAID_STAMP, qa.FOLLOWUP_PAID_RECEIPT, qa.FOLLOWUP_PAID_ATTEMPTS,
        qa.FINAL_PAID_STAMP, qa.FINAL_PAID_RECEIPT,
    )
    for field in list(raw["metadata"]):
        if field.startswith("analysis_") or field in claims + (
            "article_body_complete", "editorial_assessment", "pulso_editorial_proof_validation",
            "primary_item_binding", "evidence_revisions", "queue_identity_fingerprint",
        ):
            raw["metadata"].pop(field)
    return RawItem(**raw)


@pytest.fixture(params=URLS, ids=[url.split("/")[-2][:35] for url in URLS])
def case(request, tmp_path, actual_origin, monkeypatch):
    row = actual_origin["rows"][request.param]
    key = row["queue_fingerprint"]
    original = actual_origin["originals"][key]
    queue = PendingQueue(tmp_path / "queue.json")
    queue.items = {key: deepcopy(original)}
    start = datetime.now(timezone.utc) - timedelta(seconds=1)
    queue.discover(qa.SOURCE, [fresh(original)], now=start)
    item = queue.items[key]
    raw = RawItem(**deepcopy(item["raw"]))
    assert qa.FINAL_PAID_STAMP in raw.metadata

    def forbidden(*args, **kwargs):
        pytest.fail("Final-two units require zero publisher access and zero model requests")

    monkeypatch.setattr(beta_sources, "fetch_html", forbidden)
    monkeypatch.setattr(llm_analysis, "analyze_news", forbidden)
    signal = beta_sources.process_curated_beta_source(raw, {})
    assert signal is not None and signal["evidence_maturity"] == "media_reported"
    item["raw"] = asdict(raw)
    item["attempts"] += 1
    item["status"] = "published"
    execution = dict(
        started_at=start.isoformat(),
        finished_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        runtime_fingerprint=dict(files={GUARD_PATH: qa.digest((ROOT / GUARD_PATH).read_bytes())}),
    )
    return dict(item=item, execution=execution, telemetry=actual_origin["telemetry"], origin=actual_origin)


def inspect(case):
    return qa.verify_final_paid_revalidation(root=ROOT, **case)


def copy_case(case):
    """Copy attacked fields without repeatedly copying the whole native stock."""
    origin = dict(case["origin"], successful_response_ids=set(case["origin"]["successful_response_ids"]))
    return dict(case, item=deepcopy(case["item"]), execution=deepcopy(case["execution"]),
                telemetry=deepcopy(case["telemetry"]), origin=origin)


def test_original_two_are_genuine_deferred_premise_and_keep_their_failed_qa(actual_origin):
    assert len(actual_origin["originals"]) == len(actual_origin["successful_response_ids"]) == 2
    assert len(actual_origin["proof_files"]) == 3
    assert actual_origin["execution"]["code_sha"] == qa.FINAL_PAID_CODE
    assert actual_origin["processing_qa"]["discovery_qa"] == "PASS"
    assert actual_origin["processing_qa"]["processing_qa"] == "FAIL"
    assert actual_origin["budget_delta"]["fast"] == dict(attempted=2, successful=2, failed=0)
    for item in actual_origin["originals"].values():
        assert item["status"] == "retry" and item["attempts"] == 5
        assert item["raw"]["metadata"]["pulso_editorial_proof_validation"]["decision"] == "deferred"
        assert not qa.requires_final_paid_authority(item, actual_origin)
        assert qa.verify_final_paid_revalidation(
            item, ROOT, execution=actual_origin["execution"], telemetry=actual_origin["telemetry"],
            origin=actual_origin, archived_execution=True) is None


def test_both_unchanged_paid_answers_have_independent_current_guard_proof(case):
    proof = inspect(case)
    assert proof["prior981_and908_and66_and323_paid_provenances_preserved"]
    assert proof["publication_approved"] is False and proof["old_paid_output_reused"] is True
    assert proof["current_response_id"] == proof["original_response_id"]
    assert proof["current_guard_sha256"] == case["origin"]["document"]["validator_guard_sha256"]
    meta = case["item"]["raw"]["metadata"]
    original = case["origin"]["originals"][meta[qa.FINAL_PAID_STAMP]["queue_fingerprint"]]
    assert meta["analysis_model_output"] == original["raw"]["metadata"]["analysis_model_output"]
    assert meta[qa.FINAL_PAID_RECEIPT]["previous_validation"]["decision"] == "deferred"
    assert meta[qa.FINAL_PAID_RECEIPT]["new_validation"]["decision"] == "ready"
    assert meta[qa.FINAL_PAID_RECEIPT]["new_model_request"] is False


@pytest.mark.parametrize("reset_attempts", [False, True])
def test_erasing_every_final_claim_cannot_fall_back_to_a_lower_paid_authority(case, reset_attempts):
    value = copy_case(case)
    metadata = value["item"]["raw"]["metadata"]
    for field in (qa.FINAL_PAID_STAMP, qa.FINAL_PAID_RECEIPT):
        metadata.pop(field, None)
    metadata["evidence_revisions"] = [
        row for row in metadata["evidence_revisions"] if row.get("reason") != qa.FINAL_PAID_REVISION]
    if reset_attempts:
        value["item"]["attempts"] = 5
    assert not qa.has_final_paid_claim(metadata)
    assert qa.has_followup_paid_claim(metadata) and qa.has_current_paid_claim(metadata)
    assert qa.has_paid_revalidation_claim(metadata)
    assert qa.requires_final_paid_authority(value["item"], value["origin"])
    with pytest.raises(ValueError, match="final_paid_required_authority_missing"):
        inspect(value)


@pytest.mark.parametrize("survivor", ["receipt", "archive", "stamp"])
def test_a_surviving_receipt_revision_or_null_stamp_still_requires_final_proof(case, survivor):
    value = copy_case(case)
    metadata = value["item"]["raw"]["metadata"]
    stamp, receipt = metadata.pop(qa.FINAL_PAID_STAMP), metadata.pop(qa.FINAL_PAID_RECEIPT)
    revision = next(row for row in metadata["evidence_revisions"] if row["reason"] == qa.FINAL_PAID_REVISION)
    metadata["evidence_revisions"] = [
        row for row in metadata["evidence_revisions"] if row["reason"] != qa.FINAL_PAID_REVISION]
    if survivor == "receipt":
        metadata[qa.FINAL_PAID_RECEIPT] = receipt
    elif survivor == "archive":
        metadata["evidence_revisions"].append(revision)
    else:
        metadata[qa.FINAL_PAID_STAMP] = None
    assert stamp and qa.has_final_paid_claim(metadata)
    assert qa.requires_final_paid_authority(value["item"], value["origin"])
    with pytest.raises(ValueError, match="final_paid_admission_archive_or_historical_chain_changed"):
        inspect(value)


@pytest.mark.parametrize("mutation", [
    "body", "day", "role", "type", "attempts", "archive", "verdict",
    "window", "guard", "telemetry", "prior49", "prior12", "prior5",
])
def test_primary_archive_guard_and_genuine_paid_authority_cannot_be_forged(case, mutation):
    value = copy_case(case)
    item = value["item"]
    metadata = item["raw"]["metadata"]
    if mutation == "body":
        metadata["page_text"] += " unit invented body"
    elif mutation == "day":
        item["raw"]["event_date"] = "2026-10-10"
    elif mutation == "role":
        metadata["market_role"] = "official"
    elif mutation == "type":
        item["raw"]["source_type"] = "official"
    elif mutation == "attempts":
        item["attempts"] = 5
    elif mutation == "archive":
        next(row for row in metadata["evidence_revisions"] if row["reason"] == qa.FINAL_PAID_REVISION)[
            "previous_processing_raw"]["title"] += " unit invented archive"
    elif mutation == "verdict":
        validation = metadata["pulso_editorial_proof_validation"]
        validation.update(decision="rejected", reason="unit invented rehashed conservative rejection")
        receipt = metadata[qa.FINAL_PAID_RECEIPT]
        receipt["new_validation"] = deepcopy(validation)
        receipt["new_validation_sha256"] = qa.object_digest(validation)
    elif mutation == "window":
        value["execution"]["finished_at"] = value["execution"]["started_at"]
    elif mutation == "guard":
        value["execution"]["runtime_fingerprint"]["files"][GUARD_PATH] = "0" * 64
    elif mutation == "telemetry":
        response = metadata["analysis_model_output"]["_pulso_analysis_meta"]["response_id"]
        value["origin"]["successful_response_ids"].discard(response)
        value["telemetry"] = [event for event in value["telemetry"] if event.get("response_id") != response]
    else:
        field = {"prior49": "paid_guard_new_fast_attempt_receipts", "prior12": qa.CURRENT_PAID_ATTEMPTS,
                 "prior5": qa.FOLLOWUP_PAID_ATTEMPTS}[mutation]
        metadata[field][-1]["new_response_id"] = "resp_unit_forged_prior_paid_response"
    expected = ("final_paid_recorded_verdict_not_execution_bound_guard_result"
                if mutation == "verdict" else None)
    with pytest.raises(ValueError, match=expected):
        inspect(value)


@pytest.mark.parametrize("hide_paid_calls", [False, True])
def test_original_two_fast_producer_cannot_be_promoted_to_a_zero_api_evaluation(actual_origin, hide_paid_calls):
    execution = deepcopy(actual_origin["execution"])
    events = actual_origin["telemetry"]
    if hide_paid_calls:
        execution["budget_after"] = deepcopy(execution["budget_before"])
        events = [event for event in events if event.get("response_id") not in actual_origin["successful_response_ids"]]
    # Even forged counters cannot turn the original paid window into a later
    # zero-API execution. The immutable producer's processing QA remains FAIL.
    with pytest.raises(ValueError, match="final_revalidated_execution_not_real_zero_api_exact2"):
        qa.verify_final_revalidated_execution(
            ROOT, report={"last_core_execution": execution}, queue=actual_origin["queue"],
            history=actual_origin["history"], telemetry=events, execution=execution, origin=actual_origin)
    assert actual_origin["processing_qa"]["processing_qa"] == "FAIL"


def test_three_followup_seven_current_and_all37_older_terminal_receipts_keep_their_actual_guards(actual_origin):
    followup = qa.followup_paid_origin(ROOT)
    current = qa.current_paid_origin(ROOT)
    older = qa.paid_revalidation_origin(ROOT)
    counts = dict(followup=0, current=0, older=0)
    for item in actual_origin["queue"].values():
        if item.get("source") != qa.SOURCE or item.get("status") not in {"published", "rejected"}:
            continue
        metadata = item["raw"]["metadata"]
        if qa.has_followup_paid_claim(metadata):
            execution = qa.unchanged_followup_paid_execution(item, actual_origin)
            assert execution is actual_origin["execution"]
            verify, origin, tier = qa.verify_followup_paid_revalidation, followup, "followup"
        elif qa.has_current_paid_claim(metadata):
            execution = qa.unchanged_current_paid_execution(item, followup)
            assert execution is followup["execution"]
            verify, origin, tier = qa.verify_current_paid_revalidation, current, "current"
        elif qa.has_paid_revalidation_claim(metadata):
            execution = qa.unchanged_previous_paid_execution(item, current)
            assert execution is current["execution"]
            verify, origin, tier = qa.verify_paid_guard_revalidation, older, "older"
        else:
            continue
        assert verify(item, ROOT, execution=execution, telemetry=actual_origin["telemetry"],
                      origin=origin, archived_execution=True)
        if counts[tier] == 0:
            changed = deepcopy(execution)
            changed["runtime_fingerprint"]["files"][GUARD_PATH] = actual_origin["document"]["validator_guard_sha256"]
            assert changed["runtime_fingerprint"]["files"][GUARD_PATH] != execution["runtime_fingerprint"]["files"][GUARD_PATH]
            with pytest.raises(ValueError):
                verify(item, ROOT, execution=changed, telemetry=actual_origin["telemetry"],
                       origin=origin, archived_execution=True)
        counts[tier] += 1
    assert counts == dict(followup=3, current=7, older=37)
