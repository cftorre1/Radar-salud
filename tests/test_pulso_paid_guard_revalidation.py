"""Actual 49 paid failures; temporary queues and spies never invoke a model."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from radar_salud import beta_sources, llm_analysis, pulso_paid_revalidation as paid
from radar_salud import pulso_followup_paid_revalidation as followup
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue
from radar_salud.processing import DeferredProcessing

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 11, 19, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def original():
    document, entries = paid.load_manifest()
    return document, entries


def fresh_primary(entry):
    raw = deepcopy(entry["raw"])
    for field in list(raw["metadata"]):
        if field.startswith("analysis_") or field in (
                "article_body_complete", "editorial_assessment", "pulso_editorial_proof_validation",
                "primary_item_binding", "evidence_revisions", "queue_identity_fingerprint",
                "editorial_code_repair_admission", paid.STAMP, paid.RECEIPT):
            raw["metadata"].pop(field)
    return RawItem(**raw)


def admitted_queue(tmp_path, original):
    document, entries = original
    queue = PendingQueue(tmp_path / "queue.json")
    queue.items = deepcopy(entries)
    raws = [fresh_primary(entry) for entry in entries.values()]
    before_raws = [asdict(raw) for raw in raws]
    assert queue.discover("pulso_latercera", raws, now=NOW) == 0
    assert [asdict(raw) for raw in raws] == before_raws
    queue.save()
    return queue


def test_all49_originals_have_two_review_references_and_18_6_25_partition(original):
    document, entries = original
    assert len(document["rows"]) == len(entries) == 49
    assert Counter(row["disposition"] for row in document["rows"]) == {
        "reuse_code_fn":18, "reuse_below_gate_reject":6, "assess_contract_or_semantic_defect":25}
    assert len(document["semantic_references"]) == 2
    assert paid.digest((ROOT / paid.MANIFEST_REF).read_bytes()) == paid.MANIFEST_SHA256
    for reference in document["semantic_references"]:
        assert paid.digest((ROOT / reference["path"]).read_bytes()) == reference["sha256"]


def test_all49_admit_once_preserving_bookkeeping_and_entire_v4_v5_paid_archive(tmp_path, original):
    _, entries = original
    queue = admitted_queue(tmp_path, original)
    for key, previous in entries.items():
        current = queue.items[key]
        assert {field:value for field,value in current.items() if field not in {"raw", "retry_at"}} == {
            field:value for field,value in previous.items() if field not in {"raw", "retry_at"}}
        assert current["retry_at"] is None
        metadata, old = current["raw"]["metadata"], previous["raw"]["metadata"]
        for field in old:
            if field.startswith("analysis_") or field in (
                    "pulso_editorial_proof_validation", "primary_item_binding", "editorial_assessment",
                    "editorial_code_repair_admission"):
                assert metadata[field] == old[field]
        revision = metadata["evidence_revisions"][-1]
        assert revision["reason"] == "verified_paid_guard_revalidation_admission"
        assert revision["previous_processing_raw"] == paid.paid_raw(previous["raw"])
        assert revision["previous_retry_at"] == previous["retry_at"]
        assert metadata["evidence_revisions"][:-1] == old["evidence_revisions"]
        admission, producer = paid.verified_paid_processing_mode(RawItem(**deepcopy(current["raw"])))
        assert admission == metadata[paid.STAMP] == revision[paid.STAMP]
        assert producer == previous
        assert admission["producer_core_checkout"] == paid.PRODUCER_CODE
        assert admission["producer_runtime_fingerprint_sha256"] == paid.PRODUCER_FINGERPRINT
        assert admission["publication_approved"] is False
    assert PendingQueue(queue.path).items == queue.items
    before = deepcopy(queue.items)
    queue.discover("pulso_latercera", [fresh_primary(entry) for entry in entries.values()], now=NOW)
    assert queue.items == before
    # A later retry is never cleared again by a changed inventory annotation.
    key = next(iter(queue.items))
    queue.items[key]["retry_at"] = "2026-10-12T23:00:00+00:00"
    fresh = fresh_primary(entries[key])
    fresh.metadata["publisher_lastmod"] = "unit changed inventory token"
    queue.discover("pulso_latercera", [fresh], now=NOW)
    assert queue.items[key]["retry_at"] == "2026-10-12T23:00:00+00:00"
    assert queue.items[key]["attempts"] == entries[key]["attempts"]


def test_real_all113_terminals_and_unrelated_sources_never_reopen(tmp_path, original):
    queue = PendingQueue(tmp_path / "queue.json")
    queue.items = json.loads(subprocess.run(["git", "show", paid.PRODUCER_STATE + ":data/state/pending_queue.json"],
        cwd=ROOT, capture_output=True, check=True).stdout)
    before = deepcopy(queue.items)
    source_items = [fresh_primary(entry) for key,entry in queue.items.items()
                    if entry.get("source") == "pulso_latercera"
                    and (key in original[1] or entry.get("status") in {"published", "rejected", "archived"})]
    queue.discover("pulso_latercera", source_items, now=NOW)
    changed = {key for key in before if queue.items[key] != before[key]}
    assert changed == set(original[1])
    assert all(queue.items[key] == value for key,value in before.items() if key not in changed)


def test_real18_reuse_same_paid_answer_in_normal_processor_with_zero_model_calls(tmp_path, original, monkeypatch):
    queue = admitted_queue(tmp_path, original)
    def forbidden(*args, **kwargs):
        raise AssertionError("A same-paid-output revalidation cannot request a model or refetch HTML in this replay")
    monkeypatch.setattr(llm_analysis, "analyze_news", forbidden)
    monkeypatch.setattr(beta_sources, "fetch_html", forbidden)
    selected = [row for row in original[0]["rows"] if row["disposition"] == "reuse_code_fn"]
    assert len(selected) == 18
    for pin in selected:
        raw = RawItem(**deepcopy(queue.items[pin["queue_fingerprint"]]["raw"]))
        original_ai = deepcopy(raw.metadata["analysis_model_output"])
        row = beta_sources.process_curated_beta_source(raw, {})
        if row is None:
            # Dirección 27-oct-2026: a later feed-relevance rule (health must be the title's subject)
            # may withdraw a replayed card; the paid answer is still reused without a new model call.
            from radar_salud.editorial_gate import title_has_health_nexus
            assert not title_has_health_nexus(raw.title)
            assert raw.metadata["analysis_model_output"] == original_ai
            continue
        assert row["source_url"] == raw.url and row["event_date"] == raw.event_date
        assert row["evidence_maturity"] == "media_reported" and row["editorial_relevance"] == original_ai["relevance_score"] >= 72
        assert raw.metadata["analysis_model_output"] == original_ai
        receipt = raw.metadata[paid.RECEIPT]
        assert receipt["new_model_request"] is False and receipt["original_model_output_unchanged"] is True
        assert receipt["producer_core_checkout"] == paid.PRODUCER_CODE
        assert receipt["producer_runtime_fingerprint_sha256"] == paid.PRODUCER_FINGERPRINT
        assert receipt["validator_guard_sha256"] == hashlib.sha256((ROOT / "src/radar_salud/pulso_editorial_proof.py").read_bytes()).hexdigest()
        assert receipt["original_response_id"] == original_ai["_pulso_analysis_meta"]["response_id"]
        assert receipt["new_validation"]["decision"] == "ready" and receipt["previous_validation"]["decision"] == "deferred"
        assert receipt["publication_approved"] is False


def test_real6_below_gate_reuse_rejects_original_score_without_new_model(tmp_path, original, monkeypatch):
    queue = admitted_queue(tmp_path, original)
    monkeypatch.setattr(llm_analysis, "analyze_news", lambda **kwargs: pytest.fail("Below gate must not spend another model call"))
    selected = [row for row in original[0]["rows"] if row["disposition"] == "reuse_below_gate_reject"]
    assert len(selected) == 6
    for pin in selected:
        raw = RawItem(**deepcopy(queue.items[pin["queue_fingerprint"]]["raw"]))
        before = deepcopy(raw.metadata["analysis_model_output"])
        assert beta_sources.process_curated_beta_source(raw, {}) is None
        assert raw.metadata["editorial_assessment"]["decision"] == "rejected"
        assert raw.metadata["editorial_assessment"]["relevance_score"] == before["relevance_score"] < 72
        assert raw.metadata["pulso_editorial_proof_validation"]["decision"] == "rejected"
        assert raw.metadata["pulso_editorial_proof_validation"]["reason"] == "editorial_relevance_below_threshold"
        assert raw.metadata["analysis_model_output"] == before
        assert raw.metadata[paid.RECEIPT]["new_model_request"] is False


def test_real25_contract_defects_reach_new_full_input_fast_branch_only(tmp_path, original, monkeypatch):
    queue = admitted_queue(tmp_path, original)
    class ObservedNewFastBranch(Exception):
        pass
    calls = []
    def spy(**request):
        calls.append(request)
        raise ObservedNewFastBranch()
    monkeypatch.setattr(llm_analysis, "analyze_news", spy)
    selected = [row for row in original[0]["rows"] if row["disposition"] == "assess_contract_or_semantic_defect"]
    assert len(selected) == 25
    for pin in selected:
        raw = RawItem(**deepcopy(queue.items[pin["queue_fingerprint"]]["raw"]))
        original_ai = deepcopy(raw.metadata["analysis_model_output"])
        if followup.known_original_candidate(raw):
            before_calls = len(calls)
            with pytest.raises(DeferredProcessing, match="evidence_unverified"):
                beta_sources.process_curated_beta_source(raw, {})
            assert len(calls) == before_calls
            assert raw.metadata["analysis_model_output"] == original_ai
            continue
        with pytest.raises(ObservedNewFastBranch):
            beta_sources.process_curated_beta_source(raw, {})
        assert raw.metadata["analysis_model_output"] == original_ai
        assert paid.RECEIPT not in raw.metadata
        assert calls[-1]["full_text"] is True and calls[-1]["pulso_editorial_proof"] is True
        assert paid.digest(calls[-1]["text"].encode()) == pin["body_sha256"]
    assert len(calls) == 20


def test_bound_fonasa_comparison_enters_kind_without_changing_complete_primary_request(tmp_path, original, monkeypatch):
    queue = admitted_queue(tmp_path, original)
    pin = next(row for row in original[0]["rows"] if row.get("reassessment_context"))
    raw = RawItem(**deepcopy(queue.items[pin["queue_fingerprint"]]["raw"]))
    class RequestObserved(Exception):
        pass
    requests = []
    def spy(**request):
        requests.append(request)
        raise RequestObserved()
    monkeypatch.setattr(llm_analysis,"analyze_news",spy)
    with pytest.raises(RequestObserved):
        beta_sources.process_curated_beta_source(raw,{})
    assert len(requests) == 1
    assert pin["reassessment_context"]["context_text"] in requests[0]["kind"]
    assert "17 personas" in requests[0]["kind"] and "$26 mil millones" in requests[0]["kind"]
    assert requests[0]["text"] == raw.metadata["page_text"]
    request = llm_analysis.news_analysis_input(title=raw.title,text=requests[0]["text"],source_name=raw.source_name,full_text=True)
    assert paid.digest(request.encode()) == pin["request_input_sha256"]


def test_new_fast_deferred_output_is_retained_and_later_due_retry_is_not_poisoned(tmp_path, original, monkeypatch):
    """Actual source/model fixture, explicitly synthetic API IDs in a unit replay."""
    queue = admitted_queue(tmp_path,original)
    pin = next(row for row in original[0]["rows"] if row["disposition"]=="assess_contract_or_semantic_defect")
    key = pin["queue_fingerprint"]
    source = fresh_primary(original[1][key])
    before_attempts = queue.items[key]["attempts"]
    original_model = deepcopy(queue.items[key]["raw"]["metadata"]["analysis_model_output"])
    calls = []
    def unit_model(**request):
        calls.append(request)
        model = deepcopy(original_model)
        model["pulso_editorial_proof"]["actor"] = "unit actor absent from actual source quote"
        model["_pulso_analysis_meta"]["response_id"] = "explicit-unit-new-response-"+str(len(calls))
        model["_pulso_analysis_meta"]["raw_model_output_sha256"] = paid.digest({
            field:value for field,value in model.items() if field!="_pulso_analysis_meta"})
        return model
    monkeypatch.setattr(llm_analysis,"analyze_news",unit_model)
    for attempt in range(2):
        queue.start(key)
        raw = RawItem(**deepcopy(queue.items[key]["raw"]))
        with pytest.raises(DeferredProcessing,match="pulso_editorial_actor_not_grounded"):
            beta_sources.process_curated_beta_source(raw,{})
        queue.items[key]["raw"] = asdict(raw)
        queue.finish(key,"retry","pulso_editorial_actor_not_grounded",now=NOW)
        meta = queue.items[key]["raw"]["metadata"]
        assert len(meta[paid.NEW_FAST_RECEIPTS]) == attempt+1
        assert meta[paid.NEW_FAST_RECEIPTS][-1]["full_model_output"] == meta["analysis_model_output"]
        assert paid.RECEIPT not in meta
        retry_at = queue.items[key]["retry_at"]
        queue.discover("pulso_latercera",[source],now=NOW)
        assert queue.items[key]["retry_at"] == retry_at
        assert len([r for r in queue.items[key]["raw"]["metadata"]["evidence_revisions"]
                    if r["reason"]=="verified_paid_guard_revalidation_admission"]) == 1
    assert len(calls) == 2 and queue.items[key]["attempts"] == before_attempts+2
    assert queue.items[key]["raw"]["metadata"]["evidence_revisions"][-1]["previous_processing_raw"]["metadata"]["analysis_model_output"] == original_model


@pytest.mark.parametrize("mutation", [
    lambda old,fresh: old.update(status="published"),
    lambda old,fresh: old.update(status="rejected"),
    lambda old,fresh: old.update(status="processing"),
    lambda old,fresh: old.update(attempts=0),
    lambda old,fresh: old.update(attempts=False),
    lambda old,fresh: old.update(attempts="3"),
    lambda old,fresh: old.update(reason="analysis_unavailable"),
    lambda old,fresh: old["raw"]["metadata"]["editorial_assessment"].update(decision="published"),
    lambda old,fresh: old["raw"]["metadata"]["editorial_assessment"].update(threshold=70),
    lambda old,fresh: old["raw"]["metadata"]["analysis_model_output"].update(relevance_score=100),
    lambda old,fresh: old["raw"]["metadata"]["analysis_model_output"]["_pulso_analysis_meta"].update(response_id="unobserved-response"),
    lambda old,fresh: old["raw"]["metadata"]["pulso_editorial_proof_validation"].update(decision="ready"),
    lambda old,fresh: old["raw"]["metadata"].update(analysis_request_input_sha256="0"*64),
    lambda old,fresh: fresh.metadata.update(primary_identity_verified=False),
    lambda old,fresh: fresh.metadata.update(publication_date_verified=False),
    lambda old,fresh: fresh.metadata.update(article_body_complete=False),
    lambda old,fresh: fresh.metadata.update(analysis_input_complete=False),
    lambda old,fresh: fresh.metadata.update(primary_item_binding={"verified":False}),
    lambda old,fresh: fresh.metadata.update(html_sha256="0"*64),
    lambda old,fresh: fresh.metadata.update(editorial_hold="genuine_semantic_uncertainty"),
    lambda old,fresh: fresh.metadata.update(market_role="provider"),
    lambda old,fresh: setattr(fresh,"source_type","official"),
    lambda old,fresh: setattr(fresh,"title",fresh.title+" changed"),
    lambda old,fresh: setattr(fresh,"event_date","2026-10-11"),
])
def test_unbound_or_contradictory_previous_or_current_evidence_cannot_admit(original, mutation):
    old = deepcopy(next(iter(original[1].values())))
    fresh = fresh_primary(old)
    mutation(old,fresh)
    assert paid.verified_paid_revalidation_admission(fresh,old) is None


def test_manifest_hash_and_independent_review_bytes_are_not_replaceable(tmp_path, monkeypatch):
    source = json.loads((ROOT / paid.MANIFEST_REF).read_bytes())
    target = tmp_path / paid.MANIFEST_REF
    target.parent.mkdir(parents=True)
    altered = deepcopy(source)
    altered["rows"][0]["disposition"] = "assess_contract_or_semantic_defect"
    target.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="manifest_unpinned"):
        paid.load_manifest(tmp_path)
    target.write_bytes((ROOT / paid.MANIFEST_REF).read_bytes())
    for reference in source["semantic_references"]:
        path = tmp_path / reference["path"]
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((ROOT / reference["path"]).read_bytes())
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError, match="semantic_review_changed"):
        paid.load_manifest(tmp_path)


def test_reuse_cannot_forge_receipt_or_rewrite_old_response(tmp_path, original):
    queue = admitted_queue(tmp_path,original)
    key = next(row["queue_fingerprint"] for row in original[0]["rows"] if row["disposition"]=="reuse_code_fn")
    raw = RawItem(**deepcopy(queue.items[key]["raw"]))
    raw.metadata["analysis_model_output"]["why_it_matters"] += " altered model copy"
    with pytest.raises(ValueError, match="current_answer_or_validation_changed"):
        paid.unchanged_paid_output(raw)
    raw = RawItem(**deepcopy(queue.items[key]["raw"]))
    model = paid.unchanged_paid_output(raw)
    from radar_salud.pulso_editorial_proof import validate_pulso_editorial_proof
    verdict = validate_pulso_editorial_proof(model,raw.metadata["page_text"])
    verdict.update(primary_article_body_sha256=raw.metadata["article_body_sha256"],
        request_input_sha256=raw.metadata["analysis_request_input_sha256"],model_response=model["_pulso_analysis_meta"])
    verdict["reason"] = "invented validator verdict"
    with pytest.raises(ValueError, match="not_actual_guard_result"):
        paid.revalidation_receipt(raw,model,verdict)
