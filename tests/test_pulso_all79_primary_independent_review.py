"""Guard the complete frozen control review and its historical input binding."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
REPORT = ROOT / "data/audits/pulso_all79_primary_independent_review_2026_10_11.json"
CONTROL = ROOT / "data/audits/pulso_external_control_2026_10_11.json"
FROZEN_CONTROL = "b9c3ce2aea38107797fc19572581f27884d15611214fd2328d458bd35e906374"


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read_report():
    return json.loads(REPORT.read_text())


def test_complete_frozen_control_review_retains_every_original_and_semantic_read():
    value = read_report()
    assert sha(CONTROL.read_bytes()) == FROZEN_CONTROL == value["inputs"]["frozen_control_sha256"]
    controls = json.loads(CONTROL.read_text())["articles"]
    expected = {row["url"] for row in controls if row.get("recall_expected")
                and "2026-07-13" <= row["publication_date"] <= "2026-10-10"}
    rows = value["all_controls"]
    assert len(rows) == len(expected) == 79
    assert {row["url"] for row in rows} == expected
    assert {row["review_index"] for row in rows} == set(range(1, 80))
    assert value["counts"]["full_primary_body_characters_read"] == sum(len(row["primary_body_full"]) for row in rows) == 331754
    assert all(row["materiality_review"]["full_primary_body_read"] is True
               and row["materiality_review"]["reviewed_primary_body_sha256"] == sha(row["primary_body_full"].encode())
               and row["evidence_maturity_required"] == "media_reported"
               and row["gate_threshold_required"] == 72 for row in rows)


def test_every_retained_control_replays_its_original_hash_identity_day_and_complete_body():
    spec = importlib.util.spec_from_file_location("independent_pulso_qa", ROOT / "scripts/qa_pulso_recovery.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    for row in read_report()["all_controls"]:
        compressed = (ROOT / row["gzip_file"]).read_bytes()
        raw = gzip.decompress(compressed)
        assert sha(compressed) == row["gzip_sha256"]
        assert sha(raw) == row["capture_sha256"]
        assert len(raw) == row["raw_byte_length"]
        parser = reader.PrimaryDates()
        parser.feed(raw.decode("utf-8"))
        assert parser.canonical == row["url"]
        assert parser.days_for(row["url"]) == {row["publication_day_adopted"]}
        title, body = parser.primary_text(row["url"])
        assert body == row["primary_body_full"]
        assert sha(body.encode()) == row["primary_body_sha256"]
        assert " ".join(" ".join(parser.primary_paragraphs).split()) == body
        chain = row["original_capture_provenance_chain"]
        assert chain["capture_join_verified"] is True
        assert chain["local_manifest_sha256"] == chain["declared_capture_manifest_sha256"] == row["capture_manifest_sha256"]
        assert chain["capture_http_status"] == 200 and chain["capture_final_url"] == row["url"]


def test_proof_and_semantic_expectations_cannot_receive_core_gate_or_publication_credit():
    value = read_report()
    assert value["actual_core_execution_binding"]["run_id"] == 38120291133
    assert value["actual_core"]["error_type"] == "TypeError" and value["actual_core"]["discovered"] == 0
    assert value["actual_core_recall"] == {"complete30": {"detected": 0, "expected": 29},
                                            "complete90": {"detected": 0, "expected": 79}}
    assert value["acceptance_pass"] is False and value["publication_or_gate_approval_claimed"] is False
    assert value["counts"]["actual_gate_evaluations"] == value["counts"]["actual_core_credit_from_these_traces"] == 0
    assert all(row["actual_core_detected"] is False and row["actual_passed_gate"] is None
               and row["publication_or_gate_approval_claimed"] is False for row in value["all_controls"])
    observation = value["same_day_primary_timestamp_observations"]
    assert len(observation) == 1 and observation[0]["review_index"] == 35
    assert observation[0]["instant_difference_seconds"] == 244.619 and observation[0]["publication_day_conflict"] is False
