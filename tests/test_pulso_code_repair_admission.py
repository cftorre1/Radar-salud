"""A code repair admits only pinned actual failures to another normal FAST call."""
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.models import RawItem
from radar_salud.pulso_editorial_proof import VERSION, verified_code_repair_admission

ROOT = Path(__file__).resolve().parents[1]
INPUTS = json.loads(gzip.decompress((ROOT / "tests/fixtures/pulso_focus_all69_actual_models.json.gz").read_bytes()))["rows"]
METADATA = json.loads(gzip.decompress((ROOT / "tests/fixtures/pulso_code_repair_actual_previous_metadata.json.gz").read_bytes()))["rows"]
BY_URL = {r["url"]: r for r in INPUTS}


def previous_raw(row):
    previous = {k: copy.deepcopy(v) for k, v in row.items() if k not in ("actual_queue_status", "actual_queue_reason")}
    capture = BY_URL[row["url"]]
    previous["metadata"].update(page_text=capture["body"], analysis_model_output=copy.deepcopy(capture["ai"]))
    previous["raw_text"] = capture["body"][:1800]
    return previous


def test_all69_real_v4_failures_receive_a_stable_new_assessment_admission_only():
    assert len(METADATA) == len(BY_URL) == 69
    for row in METADATA:
        previous = previous_raw(row)
        before = copy.deepcopy(previous)
        fresh = RawItem(**copy.deepcopy(previous))
        evidence = verified_code_repair_admission(fresh, previous, row["actual_queue_reason"])
        assert evidence and evidence["repair_version"] == VERSION
        assert evidence["old_response_reuse"] is False and evidence["new_assessment_required"] is True
        assert evidence["publication_approved"] is False and evidence["other_editorial_and_budget_gates_still_apply"] is True
        assert evidence["previous_response_id"] == previous["metadata"]["analysis_model_output"]["_pulso_analysis_meta"]["response_id"]
        assert previous == before and fresh.metadata == before["metadata"]
        assert verified_code_repair_admission(fresh, previous, row["actual_queue_reason"]) == evidence


@pytest.mark.parametrize("change", ["url", "day", "source", "title", "body", "body_hash", "html_hash", "flags_false", "flags_missing", "body_incomplete", "hold", "reason", "response_id", "output", "request_hash", "v5_response", "validation", "primary_binding", "validation_response", "input_incomplete", "unknown_url"])
def test_cross_primary_unverified_or_mutated_previous_responses_cannot_be_released(change):
    row = METADATA[0]
    old = previous_raw(row)
    fresh = RawItem(**copy.deepcopy(old))
    reason = row["actual_queue_reason"]
    if change == "url": fresh.url = METADATA[1]["url"]
    elif change == "day": fresh.event_date = "2026-10-11"
    elif change == "source": fresh.source_slug = "df"
    elif change == "title": fresh.title += " changed"
    elif change == "body": fresh.metadata["page_text"] += " extra original text"
    elif change == "body_hash": fresh.metadata["article_body_sha256"] = "0" * 64
    elif change == "html_hash": fresh.metadata["html_sha256"] = "0" * 64
    elif change == "flags_false": fresh.metadata["publication_date_verified"] = False
    elif change == "flags_missing": fresh.metadata.pop("primary_identity_verified")
    elif change == "body_incomplete": fresh.metadata["article_body_complete"] = False
    elif change == "hold": fresh.metadata["editorial_hold"] = "publisher_video_text_unavailable"
    elif change == "reason": reason = "analysis_unavailable"
    elif change == "response_id": old["metadata"]["analysis_model_output"]["_pulso_analysis_meta"]["response_id"] = "another-response"
    elif change == "output": old["metadata"]["analysis_model_output"]["relevance_score"] = 100
    elif change == "request_hash": old["metadata"]["analysis_request_input_sha256"] = "0" * 64
    elif change == "v5_response": old["metadata"]["analysis_model_output"]["_pulso_analysis_meta"]["schema_version"] = VERSION
    elif change == "validation": old["metadata"]["pulso_editorial_proof_validation"]["decision"] = "ready"
    elif change == "primary_binding": old["metadata"]["primary_item_binding"]["verified"] = False
    elif change == "validation_response": old["metadata"]["pulso_editorial_proof_validation"]["model_response"]["response_id"] = "different-bound-response"
    elif change == "input_incomplete": old["metadata"]["analysis_input_complete"] = False
    elif change == "unknown_url": fresh.url = old["url"] = "https://www.latercera.com/nacional/noticia/unknown-unpinned/"
    assert verified_code_repair_admission(fresh, old, reason) is None
