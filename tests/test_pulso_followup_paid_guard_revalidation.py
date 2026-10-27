"""Actual de514 articles/responses; unit spies never call a publisher or model."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud import pulso_followup_paid_revalidation as current
from radar_salud import pulso_current_paid_revalidation as prior_current
from radar_salud import pulso_paid_revalidation as previous
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue
from radar_salud.processing import DeferredProcessing

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 11, 21, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def actual():
    return current.load_manifest()


def fresh(entry):
    raw = deepcopy(entry["raw"])
    for field in list(raw["metadata"]):
        if field.startswith("analysis_") or field in (
                "article_body_complete", "editorial_assessment", "pulso_editorial_proof_validation",
                "primary_item_binding", "evidence_revisions", "queue_identity_fingerprint",
                "editorial_code_repair_admission", previous.STAMP, previous.RECEIPT, previous.NEW_FAST_RECEIPTS,
                current.STAMP, current.RECEIPT, current.NEW_FAST_RECEIPTS,
                prior_current.STAMP, prior_current.RECEIPT, prior_current.NEW_FAST_RECEIPTS):
            raw["metadata"].pop(field)
    return RawItem(**raw)


def admitted(tmp_path, actual):
    queue = PendingQueue(tmp_path / "queue.json")
    queue.items = deepcopy(actual[1]["held"])
    source = [fresh(entry) for entry in queue.items.values()]
    before = [asdict(raw) for raw in source]
    assert queue.discover("pulso_latercera", source, now=NOW) == 0
    assert [asdict(raw) for raw in source] == before
    queue.save()
    return queue


def test_actual_original_10_paid_events_and_5_deferrals_replay_original_guard():
    origin = current.producer(str(ROOT))
    assert len(origin["events"]) == 10 and len(origin["held"]) == 5
    assert all(event["kind"] == "fast" and event["success"] is True for event in origin["events"])
    assert origin["execution"]["code_sha"] == current.PRODUCER_CODE
    assert origin["execution"]["runtime_fingerprint"]["sha256"] == current.PRODUCER_FINGERPRINT
    assert all(entry["attempts"] == 4 for entry in origin["held"].values())


def test_manifest_exact5_two_semantic_reviews_and3_2_partition(actual):
    document, origin = actual
    assert Counter(row["disposition"] for row in document["rows"]) == {"reuse_code_fn": 3, "assess_contract_or_semantic_defect": 2}
    assert len(origin["held"]) == len(document["rows"]) == 5
    assert len(document["semantic_references"]) == 2
    assert current.digest((ROOT / current.MANIFEST_REF).read_bytes()) == current.MANIFEST_SHA256
    for ref in document["semantic_references"]:
        assert current.digest((ROOT / ref["path"]).read_bytes()) == ref["sha256"]


def test_once_admission_keeps_full_original981_and_new29731_proofs(tmp_path, actual):
    queue = admitted(tmp_path, actual)
    for key, old in actual[1]["held"].items():
        entry = queue.items[key]
        assert {field:value for field,value in entry.items() if field not in ("raw", "retry_at")} == {
            field:value for field,value in old.items() if field not in ("raw", "retry_at")}
        assert entry["retry_at"] is None
        meta, original = entry["raw"]["metadata"], old["raw"]["metadata"]
        for field in ("analysis_model_output", "pulso_editorial_proof_validation", "editorial_assessment",
                      previous.STAMP, previous.NEW_FAST_RECEIPTS, prior_current.STAMP,
                      prior_current.NEW_FAST_RECEIPTS, "editorial_code_repair_admission"):
            assert meta[field] == original[field]
        assert meta["evidence_revisions"][:-1] == original["evidence_revisions"]
        revision = meta["evidence_revisions"][-1]
        assert revision["previous_processing_raw"] == current.paid_raw(old["raw"])
        assert revision["reason"] == current.REVISION and revision[current.STAMP] == meta[current.STAMP]
        assert revision["previous_retry_at"] == old["retry_at"]
        assert current.verified_processing_mode(RawItem(**deepcopy(entry["raw"])))[0] == meta[current.STAMP]
    before = deepcopy(queue.items)
    queue.discover("pulso_latercera", [fresh(entry) for entry in actual[1]["held"].values()], now=NOW)
    assert queue.items == before
    key = next(iter(queue.items))
    queue.items[key]["retry_at"] = "2026-10-12T23:00:00+00:00"
    changed = fresh(actual[1]["held"][key])
    changed.metadata["publisher_lastmod"] = "unit-only changed inventory annotation"
    queue.discover("pulso_latercera", [changed], now=NOW)
    assert queue.items[key]["retry_at"] == "2026-10-12T23:00:00+00:00"
    assert queue.items[key]["raw"]["metadata"][current.STAMP] == before[key]["raw"]["metadata"][current.STAMP]


def test_actual113_terminal_and_other_source_entries_never_reopen(tmp_path, actual):
    queue = PendingQueue(tmp_path / "queue.json")
    queue.items = deepcopy(actual[1]["queue"])
    before = deepcopy(queue.items)
    selected = [fresh(entry) for key,entry in queue.items.items() if entry.get("source") == "pulso_latercera"
                and (key in actual[1]["held"] or entry.get("status") in {"published", "rejected", "archived"})]
    queue.discover("pulso_latercera", selected, now=NOW)
    changed = {key for key in before if queue.items[key] != before[key]}
    assert changed == set(actual[1]["held"])
    assert all(queue.items[key] == before[key] for key in before if key not in changed)


@pytest.mark.parametrize("attack", ["body", "html", "day", "source_type", "role", "incomplete", "identity", "hold",
    "model", "response", "reason", "validation", "assessment", "attempts0", "attempts_bool", "attempts5", "published", "rejected"])
def test_changed_primary_or_paid_entry_cannot_obtain_current_admission(actual, attack):
    entry = deepcopy(next(iter(actual[1]["held"].values())))
    raw = fresh(entry)
    raw.metadata["article_body_complete"] = True
    if attack == "body": raw.metadata["page_text"] += " changed"
    elif attack == "html": raw.metadata["html_sha256"] = "0" * 64
    elif attack == "day": raw.event_date = "2026-10-10"
    elif attack == "source_type": raw.source_type = "official"
    elif attack == "role": raw.metadata["market_role"] = "provider"
    elif attack == "incomplete": raw.metadata["article_body_complete"] = False
    elif attack == "identity": raw.metadata["primary_identity_verified"] = False
    elif attack == "hold": raw.metadata["editorial_hold"] = "unit unresolved hold"
    elif attack == "model": entry["raw"]["metadata"]["analysis_model_output"]["why_it_matters"] += " altered"
    elif attack == "response": entry["raw"]["metadata"]["analysis_model_output"]["_pulso_analysis_meta"]["response_id"] = "unit forged id"
    elif attack == "reason": entry["reason"] = "retry_not_due"
    elif attack == "validation": entry["raw"]["metadata"]["pulso_editorial_proof_validation"]["decision"] = "ready"
    elif attack == "assessment": entry["raw"]["metadata"]["editorial_assessment"]["decision"] = "published"
    elif attack == "attempts0": entry["attempts"] = 0
    elif attack == "attempts_bool": entry["attempts"] = True
    elif attack == "attempts5": entry["attempts"] = 5
    else: entry["status"] = attack
    assert current.verified_admission(raw, entry) is None


def test_real3_reuse_same_followup_paid_answer_and_normal_media_pipeline_zero_calls(tmp_path, actual, monkeypatch):
    queue = admitted(tmp_path, actual)
    def forbidden(**kwargs):
        pytest.fail("Current paid reuse must not request another model or fetch original HTML")
    monkeypatch.setattr(llm_analysis, "analyze_news", forbidden)
    monkeypatch.setattr(beta_sources, "fetch_html", forbidden)
    rows = [row for row in actual[0]["rows"] if row["disposition"] == "reuse_code_fn"]
    assert len(rows) == 3
    for pin in rows:
        raw = RawItem(**deepcopy(queue.items[pin["queue_fingerprint"]]["raw"]))
        old = deepcopy(raw.metadata["analysis_model_output"])
        old_receipts = deepcopy(raw.metadata[previous.NEW_FAST_RECEIPTS])
        current_receipts = deepcopy(raw.metadata[prior_current.NEW_FAST_RECEIPTS])
        signal = beta_sources.process_curated_beta_source(raw, {})
        if signal is None:
            # Dirección 27-oct-2026: a later feed-relevance rule (health must be the title's subject)
            # may withdraw a replayed card; the paid answer is still reused without a new model call.
            from radar_salud.editorial_gate import title_has_health_nexus
            assert not title_has_health_nexus(raw.title)
            assert raw.metadata["analysis_model_output"] == old
            continue
        assert signal["evidence_maturity"] == "media_reported"
        assert signal["source_type"] == "press_high_trust" and signal["editorial_relevance"] == old["relevance_score"] >= 72
        assert raw.metadata["analysis_model_output"] == old
        assert raw.metadata[previous.NEW_FAST_RECEIPTS] == old_receipts
        assert raw.metadata[prior_current.NEW_FAST_RECEIPTS] == current_receipts
        receipt = raw.metadata[current.RECEIPT]
        assert receipt["producer_core_checkout"] == current.PRODUCER_CODE
        assert receipt["producer_runtime_fingerprint_sha256"] == current.PRODUCER_FINGERPRINT
        assert receipt["original_response_id"] == old["_pulso_analysis_meta"]["response_id"]
        assert receipt["new_model_request"] is False and receipt["original_model_output_unchanged"] is True
        assert receipt["previous_validation"]["decision"] == "deferred"
        assert receipt["new_validation"]["decision"] == "ready" and receipt["publication_approved"] is False


def test_historical2_contract_context_survives_but_final_authority_blocks_new_api(tmp_path, actual, monkeypatch):
    """Earlier context remains historical; exact two URLs now require final authority."""
    queue = admitted(tmp_path, actual)
    def forbidden(**kwargs):
        pytest.fail("Superseded followup permission must never dispatch another FAST")
    monkeypatch.setattr(llm_analysis, "analyze_news", forbidden)
    rows = [row for row in actual[0]["rows"] if row["disposition"] == "assess_contract_or_semantic_defect"]
    assert len(rows) == 2
    for pin in rows:
        raw = RawItem(**deepcopy(queue.items[pin["queue_fingerprint"]]["raw"]))
        before = deepcopy(raw.metadata)
        assert current.verified_processing_mode(raw)[0]["new_model_request"] is True
        assert current.reassessment_context(raw) == pin["reassessment_context"]
        with pytest.raises(DeferredProcessing, match="evidence_unverified"):
            beta_sources.process_curated_beta_source(raw, {})
        assert raw.metadata["analysis_model_output"] == before["analysis_model_output"]
        for field in (current.NEW_FAST_RECEIPTS, previous.NEW_FAST_RECEIPTS, prior_current.NEW_FAST_RECEIPTS):
            assert raw.metadata.get(field) == before.get(field)
        assert current.digest(raw.metadata["page_text"].encode()) == pin["body_sha256"]


def test_false_ready_result_cannot_become_a_current_validator_receipt(tmp_path, actual):
    queue = admitted(tmp_path, actual)
    pin = next(row for row in actual[0]["rows"] if row["disposition"] == "reuse_code_fn")
    raw = RawItem(**deepcopy(queue.items[pin["queue_fingerprint"]]["raw"]))
    model = current.unchanged_output(raw)
    validation, _, _ = current._validation(raw, model)
    validation.update(decision="rejected", reason="unit fabricated result")
    with pytest.raises(ValueError, match="actual_guard_result_unverified"):
        current.revalidation_receipt(raw, model, validation)


def test_removing_every_followup_claim_cannot_bypass_original66_authority(actual, monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("A known original66 paid answer without admission must fail before any API request")
    monkeypatch.setattr(llm_analysis, "analyze_news", forbidden)
    for entry in actual[1]["held"].values():
        raw = RawItem(**deepcopy(entry["raw"]))
        assert not current.has_claim(raw.metadata)
        with pytest.raises(DeferredProcessing, match="evidence_unverified"):
            beta_sources.process_curated_beta_source(raw, {})


@pytest.mark.parametrize("attack", ["type", "role", "old49_archive", "old12_archive", "old49_receipts", "old12_receipts", "own_stamp"])
def test_current_binding_and_each_paid_generation_are_mandatory_after_admission(tmp_path, actual, attack):
    queue = admitted(tmp_path, actual)
    for entry in queue.items.values():
        raw = RawItem(**deepcopy(entry["raw"]))
        if attack == "type": raw.source_type = "official"
        elif attack == "role": raw.metadata["market_role"] = "provider"
        elif attack == "old49_archive": raw.metadata[previous.STAMP]["original_response_id"] = "unit forged ancestor"
        elif attack == "old12_archive": raw.metadata[prior_current.STAMP]["original_response_id"] = "unit forged ancestor"
        elif attack == "old49_receipts": raw.metadata[previous.NEW_FAST_RECEIPTS][0]["new_response_id"] = "unit forged ancestor"
        elif attack == "old12_receipts": raw.metadata[prior_current.NEW_FAST_RECEIPTS][0]["new_response_id"] = "unit forged ancestor"
        else: raw.metadata[current.STAMP]["publication_approved"] = True
        with pytest.raises(ValueError, match="unverified"):
            current.verified_processing_mode(raw)


def test_hanta_context_is_full_published_august8_proof_and_never_an_editorial_decision(actual):
    document, origin = actual
    hanta = next(row for row in document["rows"] if "hanta" in row["url"])
    context = hanta["reassessment_context"]
    target = context["published_comparison_targets"][0]
    original = origin["queue"][target["target_queue_fingerprint"]]
    assert target["target_full_primary_raw"] == original["raw"]
    assert target["target_full_primary_raw"]["event_date"] == "2026-08-08"
    assert target["target_full_signal"]["editorial_relevance"] == 86
    assert target["target_full_signal"]["evidence_maturity"] == "media_reported"
    assert context["publication_approved"] is context["rejection_approved"] is False
    assert target["target_queue_entry_sha256"] == current.digest(original)
    changed = deepcopy(context)
    changed["published_comparison_targets"][0]["target_full_primary_raw"]["metadata"]["page_text"] += " unit altered context"
    with pytest.raises(ValueError, match="not_published_and_bound"):
        current._verify_context(changed, origin["held"][hanta["queue_fingerprint"]]["raw"], origin)


@pytest.mark.parametrize("cohort", [0, 1])
@pytest.mark.parametrize("generation", ["original981", "original908", "original66", "original323"])
def test_all_four_paid_generations_require_latest_authority_even_after_response_changes(
        tmp_path, actual, monkeypatch, cohort, generation):
    """All models are genuine immutable paid answers; no new response is made."""
    from radar_salud import pulso_final_paid_revalidation as final
    pin = [row for row in actual[0]["rows"] if row["disposition"] == "assess_contract_or_semantic_defect"][cohort]
    key = pin["queue_fingerprint"]
    if generation == "original981":
        raw = RawItem(**deepcopy(previous._producer(str(ROOT))[key]["raw"]))
    elif generation == "original908":
        raw = RawItem(**deepcopy(prior_current.producer(str(ROOT))["held"][key]["raw"]))
    elif generation == "original66":
        raw = RawItem(**deepcopy(actual[1]["held"][key]["raw"]))
    else:
        raw = RawItem(**deepcopy(final.producer(str(ROOT))["held"][key]["raw"]))
        for field in (current.STAMP, current.RECEIPT, current.NEW_FAST_RECEIPTS):
            raw.metadata.pop(field, None)
        raw.metadata["evidence_revisions"] = [revision for revision in raw.metadata["evidence_revisions"]
                                             if revision.get("reason") != current.REVISION]
        assert previous.verified_paid_processing_mode(raw)[0]["new_model_request"] is True
        assert prior_current.verified_processing_mode(raw)[0]["new_model_request"] is True
    assert not current.has_claim(raw.metadata)
    assert current.known_original_candidate(raw) and final.known_original_candidate(raw)
    old_model = deepcopy(raw.metadata["analysis_model_output"])
    def forbidden(**kwargs):
        pytest.fail("Erased authority must defer before another API request or legacy context fallback")
    monkeypatch.setattr(llm_analysis, "analyze_news", forbidden)
    with pytest.raises(DeferredProcessing, match="evidence_unverified"):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.metadata["analysis_model_output"] == old_model
