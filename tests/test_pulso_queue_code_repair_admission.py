"""Pinned ALL69 genuine failed FAST responses; temporary queue never calls AI."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.models import RawItem
from radar_salud.pending_queue import persisted_items, PendingQueue
from radar_salud.pulso_editorial_proof import VERSION, REPAIR_ADMISSION_PIN_SHA256

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/pulso_model_proof_real"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_bytes())
RECORD = next(record for record in MANIFEST["fixtures"] if record.get("kind") == "actual_full_failed_processing_queue")
PACKED = (FIXTURES / RECORD["path"]).read_bytes()
assert hashlib.sha256(PACKED).hexdigest() == RECORD["gzip_sha256"]
ORIGINAL = gzip.decompress(PACKED)
assert hashlib.sha256(ORIGINAL).hexdigest() == RECORD["uncompressed_sha256"]
OBSERVED = json.loads(ORIGINAL)
NOW = datetime(2026, 10, 11, 17, tzinfo=timezone.utc)


def fresh_primary(entry):
    # Only primary fields persisted by the genuine Source are replayed here;
    # processing annotations are removed to reproduce a fresh Source item.
    # Raw publisher bytes are independently tested by Source fixtures, and no
    # synthetic HTML, new inventory item or model answer is produced here.
    raw = deepcopy(entry["raw"])
    metadata = raw["metadata"]
    for field in list(metadata):
        if field.startswith("analysis_") or field in (
            "article_body_complete", "editorial_assessment", "pulso_editorial_proof_validation",
            "primary_item_binding", "evidence_revisions", "queue_identity_fingerprint",
            "editorial_code_repair_admission"):
            metadata.pop(field)
    return RawItem(**raw)


def unit_queue(tmp_path, entries=None):
    queue = PendingQueue(tmp_path / "queue.json")
    queue.items = deepcopy(entries or OBSERVED)
    queue.save()
    return queue


def assert_no_bookkeeping_reset(current, previous):
    assert {k:v for k,v in current.items() if k not in {"raw", "retry_at"}} == {
        k:v for k,v in previous.items() if k not in {"raw", "retry_at"}}


def test_all69_pinned_real_failures_admit_one_new_assessment_without_rewriting_prior_model(tmp_path):
    assert len(OBSERVED) == len({entry["raw"]["url"] for entry in OBSERVED.values()}) == 69
    queue = unit_queue(tmp_path)
    before = deepcopy(queue.items)
    inputs = [fresh_primary(entry) for entry in before.values()]
    source_inputs = [asdict(raw) for raw in inputs]
    assert queue.ready(now=NOW) == []
    assert queue.discover("pulso_latercera", inputs, now=NOW) == 0
    assert len(queue.ready(now=NOW)) == 69
    for key, previous in before.items():
        current = queue.items[key]
        assert_no_bookkeeping_reset(current, previous)
        assert current["retry_at"] is None
        metadata, old = current["raw"]["metadata"], previous["raw"]["metadata"]
        for field in old:
            if field.startswith("analysis_") or field in (
                    "editorial_assessment", "pulso_editorial_proof_validation", "primary_item_binding"):
                assert metadata[field] == old[field]
        evidence = metadata["editorial_code_repair_admission"]
        assert evidence["repair_version"] == VERSION == "pulso_editorial_proof_v5"
        assert evidence["pins_sha256"] == REPAIR_ADMISSION_PIN_SHA256
        assert evidence["previous_response_id"] == old["analysis_model_output"]["_pulso_analysis_meta"]["response_id"]
        assert evidence["previous_reason"] == previous["reason"]
        assert evidence["new_assessment_required"] is True and evidence["old_response_reuse"] is False
        assert evidence["publication_approved"] is False
        assert metadata["analysis_model_output"]["_pulso_analysis_meta"]["schema_version"] == "pulso_editorial_proof_v4"
        revision = metadata["evidence_revisions"][-1]
        assert revision["reason"] == "verified_editorial_code_repair_analysis_admission"
        archived = deepcopy(previous["raw"])
        archived["metadata"].pop("evidence_revisions", None)
        assert revision["previous_processing_raw"] == archived
        assert revision["previous_retry_at"] == previous["retry_at"]
        assert revision["fingerprint_preserved"] == key
        assert revision["code_repair_admission"] == evidence
        assert revision["body_completeness_derived_from_verified_hash"] is True
    assert [asdict(raw) for raw in inputs] == source_inputs
    # Persisted premium captures keep only lead + receipts (Dirección 28-oct-2026).
    assert PendingQueue(queue.path).items == persisted_items(queue.items)
    saved = deepcopy(queue.items)
    queue.discover("pulso_latercera", inputs, now=NOW)
    assert queue.items == saved
    assert hashlib.sha256(gzip.decompress((FIXTURES / RECORD["path"]).read_bytes())).hexdigest() == RECORD["uncompressed_sha256"]


@pytest.mark.parametrize("status", ["published", "rejected", "archived", "processing"])
def test_repair_never_reopens_terminal_or_active_processing_rows(tmp_path, status):
    key = next(iter(OBSERVED))
    entry = deepcopy(OBSERVED[key])
    entry["status"] = status
    queue = unit_queue(tmp_path, {key:entry})
    before = deepcopy(queue.items)
    queue.discover("pulso_latercera", [fresh_primary(entry)], now=NOW)
    assert queue.items[key]["retry_at"] == before[key]["retry_at"]
    assert_no_bookkeeping_reset(queue.items[key], before[key])
    assert not queue.items[key]["raw"]["metadata"].get("editorial_code_repair_admission")
    if status != "processing":
        assert queue.items == before


@pytest.mark.parametrize("mutation", [
    lambda entry, fresh: entry.update(reason="analysis_unavailable"),
    lambda entry, fresh: entry.update(attempts=0),
    lambda entry, fresh: entry.update(attempts=-1),
    lambda entry, fresh: entry.update(attempts=False),
    lambda entry, fresh: entry.update(attempts="1"),
    lambda entry, fresh: entry["raw"]["metadata"]["editorial_assessment"].update(decision="published"),
    lambda entry, fresh: entry["raw"]["metadata"]["editorial_assessment"].update(reason="unrelated_hold"),
    lambda entry, fresh: entry["raw"]["metadata"]["editorial_assessment"].update(threshold=70),
    lambda entry, fresh: entry["raw"]["metadata"]["pulso_editorial_proof_validation"].update(decision="ready"),
    lambda entry, fresh: entry["raw"]["metadata"]["pulso_editorial_proof_validation"].update(reason="unrelated_hold"),
    lambda entry, fresh: entry["raw"]["metadata"]["pulso_editorial_proof_validation"]["model_response"].update(response_id="unobserved"),
    lambda entry, fresh: entry["raw"]["metadata"]["primary_item_binding"].update(verified=False),
    lambda entry, fresh: entry["raw"]["metadata"]["primary_item_binding"].update(primary_canonical_url="https://www.latercera.com/unrelated/"),
    lambda entry, fresh: entry["raw"]["metadata"].update(primary_item_binding=None),
    lambda entry, fresh: entry["raw"]["metadata"]["pulso_editorial_proof_validation"].update(request_input_sha256="0" * 64),
    lambda entry, fresh: entry["raw"]["metadata"]["analysis_model_output"].update(what_happened="unit changed model copy"),
    lambda entry, fresh: entry["raw"]["metadata"].update(editorial_code_repair_admission={}),
    lambda entry, fresh: fresh.metadata.update(primary_item_binding={"verified":False}),
    lambda entry, fresh: fresh.metadata.update(primary_item_binding=None),
    lambda entry, fresh: fresh.metadata.update(article_body_complete=False),
    lambda entry, fresh: fresh.metadata.update(publication_date_verified=False),
    lambda entry, fresh: fresh.metadata.update(analysis_input_complete=False),
    lambda entry, fresh: fresh.metadata.update(html_sha256="0" * 64),
    lambda entry, fresh: setattr(fresh, "title", fresh.title + " unit changed title"),
    lambda entry, fresh: setattr(fresh, "event_date", "2026-10-10"),
])
def test_unpinned_inconsistent_or_explicitly_false_evidence_never_clears_retry(tmp_path, mutation):
    key = next(iter(OBSERVED))
    entry = deepcopy(OBSERVED[key])
    fresh = fresh_primary(entry)
    mutation(entry, fresh)
    queue = unit_queue(tmp_path, {key:entry})
    before = deepcopy(queue.items)
    queue.discover("pulso_latercera", [fresh], now=NOW)
    current = queue.items[key]
    assert current["retry_at"] == before[key]["retry_at"]
    assert_no_bookkeeping_reset(current, before[key])
    assert not any(revision.get("reason") == "verified_editorial_code_repair_analysis_admission"
                   for revision in current["raw"]["metadata"].get("evidence_revisions", []))


def test_already_admitted_old_failure_cannot_reclear_future_retry_on_annotation_change(tmp_path):
    key = next(iter(OBSERVED))
    entry = deepcopy(OBSERVED[key])
    queue = unit_queue(tmp_path, {key:entry})
    fresh = fresh_primary(entry)
    queue.discover("pulso_latercera", [fresh], now=NOW)
    evidence = deepcopy(queue.items[key]["raw"]["metadata"]["editorial_code_repair_admission"])
    # A simulated later processor defer leaves the observed v4 response in
    # place. Rediscovery must retain the previous stamp and cannot clear again.
    queue.items[key]["retry_at"] = "2026-10-11T23:00:00+00:00"
    fresh.metadata["publisher_lastmod"] = "unit revised inventory metadata"
    before = deepcopy(queue.items[key])
    queue.discover("pulso_latercera", [fresh], now=NOW)
    current = queue.items[key]
    assert_no_bookkeeping_reset(current, before)
    assert current["retry_at"] == before["retry_at"]
    assert current["raw"]["metadata"]["editorial_code_repair_admission"] == evidence
    assert current["raw"]["metadata"]["evidence_revisions"][-1]["reason"] == "verified_article_rediscovery"
