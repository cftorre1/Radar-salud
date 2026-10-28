"""Rediscovery conserves actual paid output; unit queue never calls a model."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from radar_salud.models import RawItem
from radar_salud.pending_queue import persisted_items, PendingQueue, fingerprint
from radar_salud.pulso_source import _verified_detail, complete_article_body

ROOT = Path(__file__).resolve().parents[1]
MODEL_FIXTURES = ROOT / "tests/fixtures/pulso_model_proof_real"
NOW = datetime(2026, 10, 11, 16, tzinfo=timezone.utc)


def observed_case():
    # This is an actual retained Focus response, not a mocked model answer.
    model_manifest = json.loads((MODEL_FIXTURES / "manifest.json").read_bytes())
    record = model_manifest["fixtures"][0]
    snapshot_bytes = (MODEL_FIXTURES / record["path"]).read_bytes()
    assert hashlib.sha256(snapshot_bytes).hexdigest() == record["sha256"]
    snapshot = json.loads(snapshot_bytes)
    observed = snapshot["queue_entry"]
    assert observed["source"] == "pulso_latercera" and observed["status"] == "retry"
    assert observed["reason"] == "pulso_editorial_action_not_grounded"
    assert observed["raw"]["url"] == record["url"]
    old = deepcopy(observed["raw"])
    sha = old["metadata"]["html_sha256"]
    manifest = json.loads((ROOT / "tests/fixtures/pulso_runtime_real/manifest.json").read_bytes())
    witness = next(row for row in manifest["requests"]
                   if row["url"] == old["url"] and row["sha256"] == sha)
    path = Path(witness["gzip_file"])
    if not path.is_absolute() and not (ROOT / path).is_file():
        path = ROOT / "tests/fixtures/pulso_runtime_real" / path
    elif not path.is_absolute():
        path = ROOT / path
    packed = path.read_bytes()
    assert hashlib.sha256(packed).hexdigest() == witness["gzip_sha256"]
    original = gzip.decompress(packed)
    assert hashlib.sha256(original).hexdigest() == witness["sha256"]
    detail = _verified_detail({"url": old["url"], "listing": "retained-original-fixture"},
                              lambda _: original.decode(witness["charset"]), None)
    fresh = RawItem(old["source_slug"], detail["title"], old["url"], old["source_name"], old["source_type"],
                    detail["metadata"]["publication_date"], detail["body"][:1800], deepcopy(detail["metadata"]))
    # Match publisher inventory provenance; the original parser/body/date/hash
    # above are independently reproduced from exact retained response bytes.
    for field in ("publisher_lastmod", "captured_at", "discovered_from"):
        fresh.metadata[field] = old["metadata"].get(field)
    assert fresh.title == old["title"] and fresh.event_date == old["event_date"]
    assert fresh.metadata["page_text"] == old["metadata"]["page_text"]
    assert complete_article_body(fresh.metadata)
    # Reproduce the legacy Source omission explicitly even after its parser
    # learns to annotate completeness. Primary bytes/body/date remain exact.
    fresh.metadata.pop("article_body_complete", None)
    assert "article_body_complete" not in fresh.metadata
    assert old["metadata"]["article_body_complete"] is True
    ai = old["metadata"]["analysis_model_output"]
    response_id = ai["_pulso_analysis_meta"]["response_id"]
    assert response_id == record["response_id"] == snapshot["response_event"]["response_id"]
    assert snapshot["response_event"]["success"] is True
    events = [json.loads(line) for line in (ROOT / "data/ai_usage/responses.jsonl").read_bytes().splitlines() if line]
    assert any(event.get("response_id") == response_id and event.get("success") is True for event in events)
    return observed, fresh


def unit_queue(tmp_path):
    observed, fresh = observed_case()
    queue = PendingQueue(tmp_path / "queue.json")
    key = fingerprint(RawItem(**observed["raw"]))
    queue.items[key] = deepcopy(observed)
    # Exercise evidence refresh while an item is actively processing. A code
    # repair admission is separately tested for pending/retry; this unit status
    # change never changes the retained observed response fixture or calls AI.
    queue.items[key]["status"] = "processing"
    queue.save()
    return queue, key, fresh


def test_exact_original_rediscovery_cannot_drop_real_paid_model_proof_for_missing_annotation(tmp_path):
    queue, key, fresh = unit_queue(tmp_path)
    before = deepcopy(queue.items[key])
    source_input = deepcopy(asdict(fresh))
    assert queue.discover("pulso_latercera", [fresh], now=NOW) == 0
    current = queue.items[key]
    assert {field:value for field,value in current.items() if field != "raw"} == {
        field:value for field,value in before.items() if field != "raw"}
    old_metadata = before["raw"]["metadata"]
    metadata = current["raw"]["metadata"]
    for field in old_metadata:
        if field.startswith("analysis_") or field in ("pulso_editorial_proof_validation", "primary_item_binding", "editorial_assessment"):
            assert metadata[field] == old_metadata[field]
    assert metadata["article_body_complete"] is True
    assert metadata["article_body_characters"] == len(metadata["page_text"])
    assert metadata["publisher_taxonomy"] == fresh.metadata["publisher_taxonomy"]
    assert metadata["evidence_revisions"][-1]["retained_processing_input_unchanged"] is True
    assert asdict(fresh) == source_input
    # Persisted premium captures keep only lead + receipts (Dirección 28-oct-2026).
    assert PendingQueue(queue.path).items == persisted_items(queue.items)
    saved = deepcopy(current)
    queue.discover("pulso_latercera", [fresh], now=NOW)
    assert queue.items[key] == saved


def test_changed_primary_retains_entire_old_request_response_and_decision_in_revision(tmp_path):
    queue, key, fresh = unit_queue(tmp_path)
    before = deepcopy(queue.items[key])
    # Explicit synthetic primary revision for the migration test; no claim
    # that the publisher changed this title, and no original byte mutation.
    fresh.title += " (unit revised title)"
    queue.discover("pulso_latercera", [fresh], now=NOW)
    current = queue.items[key]
    assert {field:value for field,value in current.items() if field != "raw"} == {
        field:value for field,value in before.items() if field != "raw"}
    revision = current["raw"]["metadata"]["evidence_revisions"][-1]
    expected = deepcopy(before["raw"])
    expected["metadata"].pop("evidence_revisions", None)
    assert revision["previous_processing_raw"] == expected
    assert not current["raw"]["metadata"].get("analysis_model_output")
    assert not current["raw"]["metadata"].get("pulso_editorial_proof_validation")


def test_explicit_incomplete_source_flag_is_never_promoted_or_allowed_to_erase_paid_evidence(tmp_path):
    queue, key, fresh = unit_queue(tmp_path)
    fresh.metadata["article_body_complete"] = False
    before = deepcopy(queue.items[key])
    queue.discover("pulso_latercera", [fresh], now=NOW)
    assert queue.items[key] == before
    assert fresh.metadata["article_body_complete"] is False
