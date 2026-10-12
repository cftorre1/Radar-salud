"""Verify the complete held cohort against its immutable paid producer."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from radar_salud.pulso_editorial_review import canonical_sha
from radar_salud.pulso_source import extract_article

ROOT = Path(__file__).parents[1]
AUDIT = ROOT / "data/audits/pulso_actual_mixed12_full_primary_model_diagnosis_2026_10_11.json"


def test_all_twelve_diagnoses_preserve_actual_paid_response_and_original_primary():
    audit = json.loads(AUDIT.read_bytes())
    producer = audit["producer_commit"]
    frozen = {}
    for key, ref in audit["inputs"].items():
        raw = subprocess.check_output(["git", "show", producer + ":" + ref["path"]], cwd=ROOT)
        assert hashlib.sha256(raw).hexdigest() == ref["file_sha256"]
        frozen[key] = [json.loads(line) for line in raw.splitlines() if line] if key == "telemetry" else json.loads(raw)
    execution = frozen["runtime_report"]["last_core_execution"]
    assert execution["code_sha"] == audit["actual_code_sha"]
    assert len(audit["rows"]) == 12
    responses = set()
    for row in audit["rows"]:
        item = frozen["queue"][row["queue_fingerprint"]]
        metadata = item["raw"]["metadata"]
        assert item["status"] == row["actual_status"] == "retry"
        assert item["reason"] == row["actual_reason"]
        assert item["attempts"] == row["actual_attempts"] == 3
        assert metadata["page_text"] == row["original_full_primary_body"]
        assert metadata["analysis_model_output"] == row["original_full_model_output"]
        assert canonical_sha(metadata["analysis_model_output"]) == row["original_model_output_semantic_sha256"]
        assert metadata["analysis_model_output"]["relevance_score"] == row["score"] >= 72
        assert metadata["pulso_editorial_proof_validation"]["reason"] == row["actual_reason"]
        primary = gzip.decompress((ROOT / row["raw_fixture_path"]).read_bytes())
        assert hashlib.sha256(primary).hexdigest() == row["original_html_sha256"]
        _, body, original = extract_article(primary.decode("utf-8"), row["url"])
        assert body == row["original_full_primary_body"]
        assert hashlib.sha256(body.encode()).hexdigest() == row["original_body_sha256"]
        assert original["publication_date"] == row["publication_date"] == item["raw"]["event_date"]
        assert all(quote in body for quote in row["supporting_verbatim_quotes"])
        response = row["original_model_response"]["response_id"]
        paid = [event for event in frozen["telemetry"] if event.get("response_id") == response
                and execution["started_at"] <= event["at"] <= execution["finished_at"]]
        assert len(paid) == 1 and paid[0]["success"] is True and paid[0]["kind"] == "fast"
        responses.add(response)
        assert row["route_is_publication_approval"] is False
    assert len(responses) == 12


def test_diagnosis_does_not_reuse_nonliteral_or_semantically_defective_assessments():
    audit = json.loads(AUDIT.read_bytes())
    reuse = [row for row in audit["rows"] if row["proposed_runtime_route"] == "reuse_code_fn"]
    assert len(reuse) == 2
    assert {row["publication_date"] for row in reuse} == {"2026-07-15", "2026-09-19"}
    for row in reuse:
        checks = row["read_only_contract_diagnostic"]
        assert all(checks["all_required_quotes_literal"].values())
        assert all(claim["source_literal"] and claim["exact"] for claim in checks["future_checks"])
        assert row["independent_semantic_peer_required"] is True
    assert sum(row["proposed_runtime_route"] == "assess_contract_or_semantic_defect"
               for row in audit["rows"]) == 10
    assert audit["publication_approved"] is False and audit["gate_threshold"] == 72
