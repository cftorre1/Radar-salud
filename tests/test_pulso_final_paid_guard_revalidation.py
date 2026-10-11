"""Two actual c2db paid models, no publisher access or model requests in tests."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud import pulso_final_paid_revalidation as final
from radar_salud import pulso_followup_paid_revalidation as followup
from radar_salud import pulso_current_paid_revalidation as current
from radar_salud import pulso_paid_revalidation as legacy
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue
from radar_salud.processing import DeferredProcessing

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 11, 23, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def actual():
    return final.load_manifest()


def fresh(entry):
    raw = deepcopy(entry["raw"])
    claims = [final.STAMP, final.RECEIPT, "editorial_code_repair_admission"]
    for module in (followup, current, legacy):
        claims.extend([module.STAMP, module.RECEIPT, module.NEW_FAST_RECEIPTS])
    for field in list(raw["metadata"]):
        if field.startswith("analysis_") or field in claims + [
                "article_body_complete", "editorial_assessment", "pulso_editorial_proof_validation",
                "primary_item_binding", "evidence_revisions", "queue_identity_fingerprint"]:
            raw["metadata"].pop(field)
    return RawItem(**raw)


def admitted(tmp_path, actual):
    queue = PendingQueue(tmp_path / "queue.json")
    queue.items = deepcopy(actual[1]["held"])
    source = [fresh(entry) for entry in queue.items.values()]
    before = [asdict(raw) for raw in source]
    assert queue.discover("pulso_latercera", source, now=NOW) == 0
    assert [asdict(raw) for raw in source] == before
    return queue


def test_original_actual_two_paid_events_and_all_prior_generations_replayed(actual):
    document, origin = actual
    assert len(origin["events"]) == len(origin["held"]) == len(document["rows"]) == 2
    assert all(event["kind"] == "fast" and event["success"] is True for event in origin["events"])
    assert origin["execution"]["code_sha"] == final.PRODUCER_CODE
    assert origin["execution"]["runtime_fingerprint"]["sha256"] == final.PRODUCER_FINGERPRINT
    assert all(entry["attempts"] == 5 for entry in origin["held"].values())
    assert all(row["disposition"] == "reuse_code_fn" and row["new_model_request"] is False for row in document["rows"])
    assert len(document["semantic_references"]) == 2
    assert final.digest((ROOT / final.MANIFEST_REF).read_bytes()) == final.MANIFEST_SHA256
    for ref in document["semantic_references"]:
        assert final.digest((ROOT / ref["path"]).read_bytes()) == ref["sha256"]
    for entry in origin["held"].values():
        raw = RawItem(**deepcopy(entry["raw"]))
        followup.verified_processing_mode(raw)
        current.verified_processing_mode(raw)
        legacy.verified_paid_processing_mode(raw)


def test_once_exact_admission_preserves_response_archive_and_all_queue_bookkeeping(tmp_path, actual):
    queue = admitted(tmp_path, actual)
    for key, old in actual[1]["held"].items():
        entry = queue.items[key]
        assert {k:v for k,v in entry.items() if k not in {"raw", "retry_at"}} == {
            k:v for k,v in old.items() if k not in {"raw", "retry_at"}}
        assert entry["retry_at"] is None
        meta, original = entry["raw"]["metadata"], old["raw"]["metadata"]
        for field in final.PRIOR_FIELDS + ("analysis_model_output", "pulso_editorial_proof_validation", "editorial_assessment"):
            assert meta.get(field) == original.get(field)
        assert meta["evidence_revisions"][:-1] == original["evidence_revisions"]
        revision = meta["evidence_revisions"][-1]
        assert revision["reason"] == final.REVISION and revision[final.STAMP] == meta[final.STAMP]
        assert revision["previous_processing_raw"] == final.paid_raw(old["raw"])
        assert revision["previous_retry_at"] == old["retry_at"]
        assert final.verified_processing_mode(RawItem(**deepcopy(entry["raw"])))[0] == meta[final.STAMP]
    before = deepcopy(queue.items)
    queue.discover("pulso_latercera", [fresh(entry) for entry in actual[1]["held"].values()], now=NOW)
    assert queue.items == before
    key = next(iter(queue.items))
    queue.items[key]["retry_at"] = "2026-10-12T23:00:00+00:00"
    changed = fresh(actual[1]["held"][key])
    changed.metadata["publisher_lastmod"] = "explicit unit inventory annotation"
    queue.discover("pulso_latercera", [changed], now=NOW)
    assert queue.items[key]["retry_at"] == "2026-10-12T23:00:00+00:00"
    assert queue.items[key]["raw"]["metadata"][final.STAMP] == before[key]["raw"]["metadata"][final.STAMP]


def test_whole_original_queue_only_two_admissions_no_terminal_reopens(tmp_path, actual):
    queue = PendingQueue(tmp_path / "queue.json")
    queue.items = deepcopy(actual[1]["queue"])
    before = deepcopy(queue.items)
    source = [fresh(entry) for key,entry in queue.items.items() if key in actual[1]["held"]
              or entry.get("source") == "pulso_latercera" and entry.get("status") in {"published", "rejected", "archived"}]
    queue.discover("pulso_latercera", source, now=NOW)
    changed = {key for key in before if queue.items[key] != before[key]}
    assert changed == set(actual[1]["held"])
    assert all(queue.items[key] == before[key] for key in before if key not in changed)


@pytest.mark.parametrize("attack", ["body", "html", "day", "type", "role", "incomplete", "identity", "hold",
    "model", "response", "reason", "validation", "assessment", "attempts0", "attempts_bool", "attempts6", "published", "rejected"])
def test_changed_primary_or_paid_entry_never_obtains_final_admission(actual, attack):
    for old in actual[1]["held"].values():
        entry = deepcopy(old)
        raw = fresh(entry)
        raw.metadata["article_body_complete"] = True
        if attack == "body": raw.metadata["page_text"] += " unit changed"
        elif attack == "html": raw.metadata["html_sha256"] = "0" * 64
        elif attack == "day": raw.event_date = "2026-10-10"
        elif attack == "type": raw.source_type = "official"
        elif attack == "role": raw.metadata["market_role"] = "provider"
        elif attack == "incomplete": raw.metadata["article_body_complete"] = False
        elif attack == "identity": raw.metadata["primary_identity_verified"] = False
        elif attack == "hold": raw.metadata["editorial_hold"] = "explicit unit unresolved hold"
        elif attack == "model": entry["raw"]["metadata"]["analysis_model_output"]["why_it_matters"] += " unit changed"
        elif attack == "response": entry["raw"]["metadata"]["analysis_model_output"]["_pulso_analysis_meta"]["response_id"] = "explicit unit forged ID"
        elif attack == "reason": entry["reason"] = "retry_not_due"
        elif attack == "validation": entry["raw"]["metadata"]["pulso_editorial_proof_validation"]["decision"] = "ready"
        elif attack == "assessment": entry["raw"]["metadata"]["editorial_assessment"]["decision"] = "published"
        elif attack == "attempts0": entry["attempts"] = 0
        elif attack == "attempts_bool": entry["attempts"] = True
        elif attack == "attempts6": entry["attempts"] = 6
        else: entry["status"] = attack
        assert final.verified_admission(raw, entry) is None


def test_exact_two_current_paid_models_normal_media_pipeline_no_http_or_ai(tmp_path, actual, monkeypatch):
    queue = admitted(tmp_path, actual)
    def forbidden(**kwargs):
        pytest.fail("The two exact paid revalidations require zero model and publisher calls")
    monkeypatch.setattr(llm_analysis, "analyze_news", forbidden)
    monkeypatch.setattr(beta_sources, "fetch_html", forbidden)
    for entry in queue.items.values():
        raw = RawItem(**deepcopy(entry["raw"]))
        original = deepcopy(raw.metadata)
        signal = beta_sources.process_curated_beta_source(raw, {})
        assert signal is not None and signal["evidence_maturity"] == "media_reported"
        assert signal["source_type"] == "press_high_trust"
        assert signal["editorial_relevance"] == original["analysis_model_output"]["relevance_score"] >= 72
        original_what = original["analysis_model_output"]["what_happened"]
        assert original_what.startswith("Según la nota del ")
        assert signal["what_happened"] == "Según Pulso / La Tercera, " + original_what
        assert raw.metadata["analysis_model_output"] == original["analysis_model_output"]
        for field in final.PRIOR_FIELDS:
            assert raw.metadata.get(field) == original.get(field)
        receipt = raw.metadata[final.RECEIPT]
        assert receipt["producer_core_checkout"] == final.PRODUCER_CODE
        assert receipt["producer_runtime_fingerprint_sha256"] == final.PRODUCER_FINGERPRINT
        assert receipt["original_response_id"] == original["analysis_model_output"]["_pulso_analysis_meta"]["response_id"]
        assert receipt["new_model_request"] is False and receipt["original_model_output_unchanged"] is True
        assert receipt["previous_validation"]["decision"] == "deferred"
        assert receipt["new_validation"]["decision"] == "ready" and receipt["publication_approved"] is False
        final.verified_processing_mode(raw)


@pytest.mark.parametrize("what", [
    "Según Pulso / La Tercera, la nota informó una medida sanitaria.",
    "Según la nota de La Tercera del 5 de octubre, el Ministerio informó una medida sanitaria.",
    "Según la nota de Pulso, el Ministerio informó una medida sanitaria.",
    "La Tercera reportó una medida sanitaria atribuida a su fuente.",
])
def test_explicit_publisher_intro_never_receives_duplicate_attribution(what):
    assert beta_sources._attribute_pulso_what(what) == what


def test_rehashed_forged_validation_cannot_become_a_receipt(tmp_path, actual):
    queue = admitted(tmp_path, actual)
    for entry in queue.items.values():
        raw = RawItem(**deepcopy(entry["raw"]))
        model = final.unchanged_output(raw)
        validation, _, _ = final._validation(raw, model)
        validation.update(decision="rejected", reason="unit fabricated conservative rejection")
        with pytest.raises(ValueError, match="actual_guard_result_unverified"):
            final.revalidation_receipt(raw, model, validation)


@pytest.mark.parametrize("attack", ["type", "role", "old49_archive", "old12_archive", "old5_archive",
                                   "old49_receipts", "old12_receipts", "old5_receipts", "own_stamp", "own_revision"])
def test_every_prior_paid_archive_and_current_binding_mandatory(tmp_path, actual, attack):
    queue = admitted(tmp_path, actual)
    for entry in queue.items.values():
        raw = RawItem(**deepcopy(entry["raw"]))
        if attack == "type": raw.source_type = "official"
        elif attack == "role": raw.metadata["market_role"] = "provider"
        elif attack == "old49_archive": raw.metadata[legacy.STAMP]["original_response_id"] = "unit changed ancestor"
        elif attack == "old12_archive": raw.metadata[current.STAMP]["original_response_id"] = "unit changed ancestor"
        elif attack == "old5_archive": raw.metadata[followup.STAMP]["original_response_id"] = "unit changed ancestor"
        elif attack == "old49_receipts": raw.metadata[legacy.NEW_FAST_RECEIPTS][0]["new_response_id"] = "unit changed ancestor"
        elif attack == "old12_receipts": raw.metadata[current.NEW_FAST_RECEIPTS][0]["new_response_id"] = "unit changed ancestor"
        elif attack == "old5_receipts": raw.metadata[followup.NEW_FAST_RECEIPTS][0]["new_response_id"] = "unit changed ancestor"
        elif attack == "own_revision": raw.metadata["evidence_revisions"][-1]["previous_processing_raw"]["title"] += " unit changed"
        else: raw.metadata[final.STAMP]["publication_approved"] = True
        with pytest.raises(ValueError, match="unverified"):
            final.verified_processing_mode(raw)


@pytest.mark.parametrize("generation", ["original981", "original908", "original66", "original323", "revalidated_once"])
def test_membership_authority_cannot_be_erased_to_dispatch_any_older_context(tmp_path, actual, monkeypatch, generation):
    queue = admitted(tmp_path, actual)
    def forbidden(**kwargs):
        pytest.fail("Removing every final claim must fail before publisher or model access")
    monkeypatch.setattr(llm_analysis, "analyze_news", forbidden)
    monkeypatch.setattr(beta_sources, "fetch_html", forbidden)
    for key, original in actual[1]["held"].items():
        if generation == "original981": raw = RawItem(**deepcopy(legacy._producer(str(ROOT))[key]["raw"]))
        elif generation == "original908": raw = RawItem(**deepcopy(current.producer(str(ROOT))["held"][key]["raw"]))
        elif generation == "original66": raw = RawItem(**deepcopy(followup.producer(str(ROOT))["held"][key]["raw"]))
        elif generation == "original323":
            raw = RawItem(**deepcopy(original["raw"]))
            assert followup.verified_processing_mode(raw)[0]["new_model_request"] is True
            assert current.verified_processing_mode(raw)[0]["new_model_request"] is True
            assert legacy.verified_paid_processing_mode(raw)[0]["new_model_request"] is True
        else:
            raw = RawItem(**deepcopy(queue.items[key]["raw"]))
            beta_sources.process_curated_beta_source(raw, {})
        raw.metadata.pop(final.STAMP, None)
        raw.metadata.pop(final.RECEIPT, None)
        raw.metadata["evidence_revisions"] = [r for r in raw.metadata.get("evidence_revisions", []) if r.get("reason") != final.REVISION]
        assert not final.has_claim(raw.metadata) and final.known_original_candidate(raw)
        with pytest.raises(DeferredProcessing, match="evidence_unverified"):
            beta_sources.process_curated_beta_source(raw, {})
