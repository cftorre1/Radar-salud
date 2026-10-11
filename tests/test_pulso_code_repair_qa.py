"""Independent lineage reader: real old responses; no calls or runtime mutation."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("code_repair_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
FIXTURES = ROOT / "tests/fixtures/pulso_model_proof_real"
manifest = json.loads((FIXTURES / "manifest.json").read_bytes())
record = next(row for row in manifest["fixtures"] if row.get("kind") == "actual_full_failed_processing_queue")
packed = (FIXTURES / record["path"]).read_bytes()
assert hashlib.sha256(packed).hexdigest() == record["gzip_sha256"]
original = gzip.decompress(packed)
assert hashlib.sha256(original).hexdigest() == record["uncompressed_sha256"]
OBSERVED = json.loads(original)
NOW = datetime(2026, 10, 11, 17, tzinfo=timezone.utc)


def fresh(entry):
    raw = deepcopy(entry["raw"])
    for field in list(raw["metadata"]):
        if field.startswith("analysis_") or field in {
            "article_body_complete", "editorial_assessment", "pulso_editorial_proof_validation",
            "primary_item_binding", "evidence_revisions", "queue_identity_fingerprint", "editorial_code_repair_admission"}:
            raw["metadata"].pop(field)
    return RawItem(**raw)


@pytest.fixture
def admitted(tmp_path):
    path = tmp_path / qa.CODE_REPAIR_PINS_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes((ROOT / qa.CODE_REPAIR_PINS_PATH).read_bytes())
    queue = PendingQueue(tmp_path / "queue.json")
    queue.items = deepcopy(OBSERVED)
    queue.discover("pulso_latercera", [fresh(row) for row in OBSERVED.values()], now=NOW)
    assert len(queue.items) == 69
    return queue, tmp_path


def test_all69_admissions_bind_unchanged_archived_real_v4_answers_without_approving_them(admitted):
    queue, root = admitted
    before = deepcopy(queue.items)
    for row in queue.items.values():
        proof = qa.verify_code_repair_reference(row["raw"], root)
        assert proof["analysis_release_only"] is True and proof["publication_approved"] is False
        assert proof["current_response_id"] is None
        with pytest.raises(ValueError, match="new_genuine_v5_assessment_missing"):
            qa.verify_code_repair_reference(row["raw"], root, successful_response_ids=set(), require_new_assessment=True)
    assert queue.items == before


@pytest.mark.parametrize("change", ["stamp", "duplicate_revision", "remove_archive", "old_response", "old_version",
    "old_score", "old_assessment", "old_validation", "old_primary", "old_request", "retry_evidence", "attempts",
    "fingerprint", "current_primary", "current_day", "current_false", "current_body"])
def test_pinned_permission_does_not_accept_mutated_history_or_primary(admitted, change):
    queue, root = admitted
    raw = deepcopy(next(iter(queue.items.values()))["raw"])
    meta = raw["metadata"]
    revision = next(row for row in meta["evidence_revisions"] if row["reason"] == "verified_editorial_code_repair_analysis_admission")
    old = revision["previous_processing_raw"]["metadata"]
    if change == "stamp": meta["editorial_code_repair_admission"]["publication_approved"] = True
    elif change == "duplicate_revision": meta["evidence_revisions"].append(deepcopy(revision))
    elif change == "remove_archive": revision.pop("previous_processing_raw")
    elif change == "old_response": old["analysis_model_output"]["_pulso_analysis_meta"]["response_id"] = "foreign"
    elif change == "old_version": old["analysis_model_output"]["_pulso_analysis_meta"]["schema_version"] = qa.CODE_REPAIR_VERSION
    elif change == "old_score": old["analysis_model_output"]["relevance_score"] = 100
    elif change == "old_assessment": old["editorial_assessment"]["decision"] = "published"
    elif change == "old_validation": old["pulso_editorial_proof_validation"]["decision"] = "ready"
    elif change == "old_primary": old["html_sha256"] = "0" * 64
    elif change == "old_request": old["analysis_request_input_sha256"] = "0" * 64
    elif change == "retry_evidence": revision.pop("previous_retry_at")
    elif change == "attempts": revision["attempts_preserved"] = 0
    elif change == "fingerprint": revision["fingerprint_preserved"] = "0" * 64
    elif change == "current_primary": meta["html_sha256"] = "0" * 64
    elif change == "current_day": raw["event_date"] = "2026-10-11"
    elif change == "current_false": meta["article_body_complete"] = False
    elif change == "current_body": meta["page_text"] += " changed primary"
    with pytest.raises(ValueError):
        qa.verify_code_repair_reference(raw, root)


def unit_new_v5_transport(raw):
    # Synthetic transport annotations ONLY: no actual new model or semantic
    # approval is claimed. This tests the reader's ID/hash/version boundaries.
    meta = raw["metadata"]
    model = meta["analysis_model_output"]
    model["_pulso_analysis_meta"].update(schema_version=qa.CODE_REPAIR_VERSION, response_id="unit_distinct_v5_response")
    validation = meta["pulso_editorial_proof_validation"]
    validation.update(version=qa.CODE_REPAIR_VERSION, decision="ready", reason="unit_transport_binding_only",
                      model_response=deepcopy(model["_pulso_analysis_meta"]), model_output_sha256=qa.object_digest(model))
    return "unit_distinct_v5_response"


def test_completed_transport_requires_distinct_v5_response_known_to_real_telemetry_reader(admitted):
    queue, root = admitted
    raw = deepcopy(next(iter(queue.items.values()))["raw"])
    old_id = raw["metadata"]["editorial_code_repair_admission"]["previous_response_id"]
    new_id = unit_new_v5_transport(raw)
    proof = qa.verify_code_repair_reference(raw, root, successful_response_ids={old_id, new_id}, require_new_assessment=True)
    assert proof["previous_response_id"] == old_id and proof["current_response_id"] == new_id != old_id
    assert raw["metadata"]["evidence_revisions"][-1]["previous_processing_raw"]["metadata"]["analysis_model_output"]["_pulso_analysis_meta"]["schema_version"] == "pulso_editorial_proof_v4"
    with pytest.raises(ValueError, match="new_genuine_v5_assessment_missing"):
        qa.verify_code_repair_reference(raw, root, successful_response_ids={old_id}, require_new_assessment=True)


@pytest.mark.parametrize("change", ["reuse", "v4", "deferred", "foreign_input", "foreign_request", "output_tamper", "response_binding"])
def test_new_paid_output_must_match_same_primary_and_current_guard_version(admitted, change):
    queue, root = admitted
    raw = deepcopy(next(iter(queue.items.values()))["raw"])
    new_id = unit_new_v5_transport(raw)
    meta = raw["metadata"]
    model = meta["analysis_model_output"]
    validation = meta["pulso_editorial_proof_validation"]
    if change == "reuse": model["_pulso_analysis_meta"]["response_id"] = meta["editorial_code_repair_admission"]["previous_response_id"]
    elif change == "v4": model["_pulso_analysis_meta"]["schema_version"] = "pulso_editorial_proof_v4"
    elif change == "deferred": validation["decision"] = "deferred"
    elif change == "foreign_input": model["_pulso_analysis_meta"]["analysis_text_sha256"] = "0" * 64
    elif change == "foreign_request": model["_pulso_analysis_meta"]["request_input_sha256"] = "0" * 64
    elif change == "output_tamper": model["what_happened"] = "unobserved modified answer"
    elif change == "response_binding": validation["model_response"]["response_id"] = "foreign"
    with pytest.raises(ValueError, match="new_genuine_v5_assessment_missing"):
        qa.verify_code_repair_reference(raw, root, successful_response_ids={new_id}, require_new_assessment=True)


def test_mutable_config_cannot_replace_fixed69_pin_set(admitted):
    queue, root = admitted
    path = root / qa.CODE_REPAIR_PINS_PATH
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="immutable_pins_changed"):
        qa.verify_code_repair_reference(next(iter(queue.items.values()))["raw"], root)


def test_unrelated_primary_without_repair_claim_has_no_exemption():
    assert qa.verify_code_repair_reference({"metadata": {}}, ROOT) is None
