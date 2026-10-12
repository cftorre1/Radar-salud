"""Bind the full independent actual final-two diagnosis to its paid producer."""
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data/audits/pulso_actual_final2_primary_model_independent_diagnosis_2026_10_11.json"


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()


def test_all_actual_models_bodies_and_ids_match_immutable_paid_producer():
    review = json.loads(REVIEW.read_bytes())
    producer = review["producer_commit"]
    originals = {}
    for path, expected in review["producer_files"].items():
        raw = subprocess.check_output(["git", "show", producer + ":" + path], cwd=ROOT)
        assert digest(raw) == expected
        if path.endswith(".jsonl"):
            originals[path] = [json.loads(line) for line in raw.splitlines() if line.strip()]
        else:
            originals[path] = json.loads(raw)
    queue = originals["data/state/pending_queue.json"]
    events = originals["data/ai_usage/responses.jsonl"]
    responses = []
    assert len(review["rows"]) == 2
    for row in review["rows"]:
        item = queue[row["queue_fingerprint"]]
        metadata = item["raw"]["metadata"]
        assert row["original_full_primary_body"] == metadata["page_text"]
        assert row["original_body_sha256"] == digest(metadata["page_text"].encode())
        assert row["original_full_model_output"] == metadata["analysis_model_output"]
        assert row["original_model_output_sha256"] == digest(metadata["analysis_model_output"])
        assert row["actual_pulso_validation"] == metadata["pulso_editorial_proof_validation"]
        assert row["actual_attempts"] == item["attempts"] == 5
        assert item["status"] == "retry"  # The diagnosis never invents publication.
        response = metadata["analysis_model_output"]["_pulso_analysis_meta"]["response_id"]
        responses.append(response)
        assert row["original_response_id"] == response
        assert len([event for event in events if event.get("response_id") == response and event.get("success") is True]) == 1
        assert all(quote in metadata["page_text"] for quote in row["primary_evidence_quotes"])
        assert row["publication_approved"] is False
    assert len(set(responses)) == 2
    assert review["actual_budget_delta"] == {
        "fast": {"attempted": 2, "successful": 2, "failed": 0},
        "deep": {"attempted": 0, "successful": 0, "failed": 0},
    }
    assert review["current_processing_qa"] == "FAIL"
    assert review["overall_acceptance"] == "WITHHELD"


def test_context_and_full_discovery_companions_preserve_actual_evidence():
    review = json.loads(REVIEW.read_bytes())
    for key in ("technical_companion", "discovery_companion"):
        proof = review[key]
        raw = (ROOT / proof["path"]).read_bytes()
        assert digest(raw) == proof["sha256"]
    discovery = json.loads((ROOT / review["discovery_companion"]["path"]).read_bytes())
    assert discovery["discovery_verdict"] == "PASS"
    assert discovery["checks"]["controls_originals_verified"] == 79
    assert discovery["checks"]["public_feeds"]["feeds_checked"] == 20
    assert discovery["checks"]["public_feeds"]["original_pages_verified"] == 75
    assert not discovery["findings"]
    hanta = next(row for row in review["rows"] if row["comparative_published_context"])
    context = hanta["comparative_published_context"]
    assert context["event_date"] == "2026-08-08"
    assert context["body_sha256"] == digest(context["full_original_primary_body"].encode())
    assert context["signal_sha256"] == digest(context["full_signal"])
    assert context["queue_entry_sha256"] == digest(context["full_queue_entry"])
    assert context["full_queue_entry"]["status"] == "published"
    assert "Previamente, el Minsal había decretado alerta sanitaria por hantavirus" in context["full_original_primary_body"]
