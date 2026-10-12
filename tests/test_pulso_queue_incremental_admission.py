"""Actual retained Oct5 primary bytes bind admission; temporary queue is unit state."""
import gzip
import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_salud import pulso_incremental_review as review
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, fingerprint
from radar_salud.pulso_source import _verified_detail

ROOT = Path(__file__).resolve().parents[1]
ADDENDUM = json.loads(review.ADDENDUM_PATH.read_bytes())
OLD_REVIEW = json.loads(review.REVIEW_PATH.read_bytes())
NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


def primary():
    article = ADDENDUM["article"]
    packed = (ROOT / article["gzip_file"]).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == article["gzip_sha256"]
    original = gzip.decompress(packed)
    assert hashlib.sha256(original).hexdigest() == article["html_sha256"]
    detail = _verified_detail({"url": article["source_url"], "listing": "retained-original-fixture"},
                              lambda _: original.decode("utf-8"), None)
    metadata = deepcopy(detail["metadata"])
    assert len(metadata["page_text"]) == article["body_characters"]
    assert metadata["article_body_sha256"] == article["body_sha256"]
    metadata["captured_at"] = article["source_capture_at"]
    return RawItem("pulso_latercera", detail["title"], article["source_url"], "Pulso / La Tercera",
                   "press_high_trust", article["publication_date"], detail["body"][:1800], metadata)


def held_queue(tmp_path, status="retry"):
    raw = primary()
    article = ADDENDUM["article"]
    raw.metadata.update(
        editorial_hold=ADDENDUM["prior_review"]["reason"],
        editorial_assessment={"decision": "pending", "reason": ADDENDUM["prior_review"]["reason"]},
        event_equivalence_review=[OLD_REVIEW["reviews"][0]["compared_signal"]],
        editorial_review_context={"compared_signal": OLD_REVIEW["reviews"][0]["compared_signal"]},
        incremental_review={"review_ref": review.REVIEW_REF, "review_sha256": review.REVIEW_SHA256,
            "decision": "keep_hold", "reason": ADDENDUM["prior_review"]["reason"],
            "publication_approved": False, "verified_publication_date": article["publication_date"],
            "verified_body_sha256": article["body_sha256"], "verified_html_sha256": article["html_sha256"],
            "verified_captured_at": article["source_capture_at"]})
    queue = PendingQueue(tmp_path / "queue.json")
    queue.discover("pulso_latercera", [raw], now=NOW)
    key = fingerprint(raw)
    queue.start(key)
    queue.finish(key, "retry", ADDENDUM["prior_review"]["reason"], now=NOW)
    queue.items[key]["status"] = status
    queue.save()
    return queue, key


@pytest.mark.parametrize("status", ["pending", "retry"])
@pytest.mark.parametrize("already_applied", [False, True])
def test_only_bound_review_clears_future_retry_without_consuming_analysis(tmp_path, status, already_applied):
    queue, key = held_queue(tmp_path, status)
    before = deepcopy(queue.items[key])
    fresh = primary()
    if already_applied:
        for field in ("incremental_review", "event_equivalence_review", "editorial_review_context", "editorial_hold"):
            fresh.metadata[field] = deepcopy(before["raw"]["metadata"][field])
        from radar_salud.pulso_source import complete_article_body
        fresh.metadata["article_body_complete"] = complete_article_body(fresh.metadata)
        assert review.apply_incremental_review(fresh)
    source_input = deepcopy(asdict(fresh))
    assert queue.ready(now=NOW) == []
    assert queue.discover("pulso_latercera", [fresh], now=NOW) == 0
    current = queue.items[key]
    assert {k:v for k,v in current.items() if k not in {"raw", "retry_at"}} == {
        k:v for k,v in before.items() if k not in {"raw", "retry_at"}}
    assert current["retry_at"] is None
    assert [ready_key for ready_key, _ in queue.ready(now=NOW)] == [key]
    metadata = current["raw"]["metadata"]
    assert "editorial_hold" not in metadata
    assert metadata["incremental_review"] == before["raw"]["metadata"]["incremental_review"]
    assert metadata["event_equivalence_review"] == before["raw"]["metadata"]["event_equivalence_review"]
    evidence = metadata["incremental_review_addendum"]
    assert evidence["review_sha256"] == review.ADDENDUM_SHA256 and evidence["publication_approved"] is False
    assert metadata["editorial_review_context"]["media_materiality_threshold"] == 72
    revision = metadata["evidence_revisions"][-1]
    assert revision["reason"] == "approved_incremental_review_discovery_admission"
    assert revision["previous_retry_at"] == before["retry_at"]
    assert revision["fingerprint_preserved"] == key
    assert revision["attempts_preserved"] == before["attempts"] == 1
    assert revision["body_completeness_derived_from_verified_hash"] is (not already_applied)
    assert review.verified_incremental_release(RawItem(**current["raw"])) == evidence
    assert asdict(fresh) == source_input
    assert PendingQueue(queue.path).items == queue.items
    saved = deepcopy(current)
    queue.discover("pulso_latercera", [primary()], now=NOW)
    assert queue.items[key] == saved


@pytest.mark.parametrize("status", ["published", "rejected", "archived", "processing"])
def test_terminal_or_active_processing_cannot_be_readmitted(tmp_path, status):
    queue, key = held_queue(tmp_path, status)
    before = deepcopy(queue.items[key])
    queue.discover("pulso_latercera", [primary()], now=NOW)
    assert queue.items[key] == before


@pytest.mark.parametrize("mutation", [
    lambda old, fresh: old.update(editorial_hold="unrelated_editorial_review"),
    lambda old, fresh: old["incremental_review"].update(review_sha256="0" * 64),
    lambda old, fresh: old["incremental_review"].update(decision="release_hold_for_editorial_analysis"),
    lambda old, fresh: old.pop("editorial_assessment"),
    lambda old, fresh: old["editorial_assessment"].update(reason="another_decision"),
    lambda old, fresh: old["editorial_assessment"].update(decision="deferred"),
    lambda old, fresh: fresh.metadata.update(editorial_hold="another_new_hold"),
    lambda old, fresh: fresh.metadata.update(incremental_review={}),
    lambda old, fresh: fresh.metadata.update(publication_date_verified=False),
    lambda old, fresh: fresh.metadata.update(article_body_complete=False),
    lambda old, fresh: fresh.metadata.update(html_sha256="0" * 64),
    lambda old, fresh: fresh.metadata.update(page_text=fresh.metadata["page_text"] + " revised",
        article_body_sha256=hashlib.sha256((fresh.metadata["page_text"] + " revised").encode()).hexdigest(),
        article_body_characters=len(fresh.metadata["page_text"] + " revised")),
])
def test_unrelated_unverified_or_revised_evidence_cannot_clear_retry(tmp_path, mutation):
    queue, key = held_queue(tmp_path)
    fresh = primary()
    mutation(queue.items[key]["raw"]["metadata"], fresh)
    before = deepcopy(queue.items[key])
    queue.discover("pulso_latercera", [fresh], now=NOW)
    current = queue.items[key]
    assert current["retry_at"] == before["retry_at"]
    assert current["status"] == before["status"] and current["attempts"] == before["attempts"]
    assert current["raw"]["metadata"].get("editorial_hold")
    assert not current["raw"]["metadata"].get("incremental_review_addendum")
    assert not any(row["reason"] == "approved_incremental_review_discovery_admission"
                   for row in current["raw"]["metadata"].get("evidence_revisions", []))


def test_modified_addendum_bytes_never_admit_even_with_real_primary(tmp_path, monkeypatch):
    queue, key = held_queue(tmp_path)
    before = deepcopy(queue.items[key])
    path = tmp_path / "changed-review.json"
    path.write_bytes(review.ADDENDUM_PATH.read_bytes() + b"\n")
    monkeypatch.setattr(review, "ADDENDUM_PATH", path)
    queue.discover("pulso_latercera", [primary()], now=NOW)
    assert queue.items[key] == before


@pytest.mark.parametrize("decision", ["published", "rejected", "accepted", "approved"])
def test_inconsistent_mutable_status_never_erases_terminal_editorial_assessment(tmp_path, decision):
    queue, key = held_queue(tmp_path)
    queue.items[key]["raw"]["metadata"]["editorial_assessment"].update(decision=decision, score=90)
    before = deepcopy(queue.items[key])
    fresh = primary()
    # Even a changed but otherwise complete rediscovered primary cannot erase
    # a terminal editorial assessment merely because queue status says retry.
    fresh.title += " updated title"
    queue.discover("pulso_latercera", [fresh], now=NOW)
    assert queue.items[key] == before
