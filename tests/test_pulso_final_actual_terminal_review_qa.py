"""Regression for the complete real123 editorial stock, not mutable fixtures."""
from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).parents[1]
PRODUCER = "123bf2550536030a077c03ad4d56572df24ab418"
spec = importlib.util.spec_from_file_location("terminal_actual_review_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
AUDIT = "data/audits/pulso_actual323_ilc_mask_editorial_review_2026_10_11.json"
PEER = "data/audits/pulso_actual323_ilc_mask_independent_second_peer_2026_10_11.json"


def archived(commit, path):
    return json.loads(subprocess.check_output(["git", "show", commit + ":" + path], cwd=ROOT))


@pytest.fixture(scope="module")
def actual():
    return dict(queue=archived(PRODUCER, "data/state/pending_queue.json"),
        history=archived(PRODUCER, "data/history/superintendencia_signals.json")["signals"],
        snapshot=archived(PRODUCER, "web/data/radar_today.json"),
        recorded_qa=archived(PRODUCER, "data/audits/pulso_directed_processing_qa_2026_10_11.json"))


def test_all_actual24_consumer_findings_recover_exact_reviews_and_gate_trace(actual):
    recorded = actual["recorded_qa"]
    assert recorded["processing_qa"] == "FAIL" and len(recorded["findings"]) == 24
    assert Counter(row["code"] for row in recorded["findings"])["published_without_unchanged_editorial_gate_trace"] == 18
    proofs, findings = qa.verify_bound_editorial_review(actual["queue"], actual["history"], actual["snapshot"], ROOT)
    assert findings == []
    urls = {row["url"] for row in recorded["findings"] if row.get("url")}
    assert urls <= set(proofs)
    for item in actual["queue"].values():
        if item.get("source") != qa.SOURCE or item.get("status") != "published":
            continue
        assessment = item["raw"]["metadata"]["editorial_assessment"]
        url = item["raw"]["url"]
        reason = (proofs[url]["original_model_assessment"] if url in proofs else assessment).get("analysis_reason")
        assert assessment["decision"] == "published" and assessment["threshold"] == 72
        assert type(assessment["relevance_score"]) is int and assessment["relevance_score"] >= 72 and reason
    uc = next(row for row in actual["history"] if "clinica-uc-christus-de-san-carlos" in row.get("source_url", ""))
    assert proofs[uc["source_url"]]["decision"] == "group" and uc["feed_visibility"] is False
    assert all(row["source_url"] != uc["source_url"] for row in actual["snapshot"]["signals"])


@pytest.fixture(scope="module")
def exact_missing_binding():
    audit = json.loads((ROOT / AUDIT).read_bytes())
    parent = json.loads((ROOT / audit["independent_review"]["path"]).read_bytes())
    reader = parent["all_signals"][0]
    source = archived(qa.FINAL_PAID_PRODUCER, "data/state/pending_queue.json")
    paid = next(row for row in source.values() if row.get("raw", {}).get("url") == reader["url"])
    report = archived(qa.FINAL_PAID_PRODUCER, "data/audits/pulso_runtime_2026_10_11.json")
    execution = report["last_core_execution"]
    origin = qa.followup_paid_origin(ROOT)
    receipt = qa.verify_followup_paid_revalidation(paid, ROOT, execution=execution,
        telemetry=origin["telemetry"], origin=origin, archived_execution=True)
    dual = dict(original_producer=qa.FOLLOWUP_PAID_PRODUCER, original_core_code=qa.FOLLOWUP_PAID_CODE,
        publication_execution_code=execution["code_sha"], manifest_ref=qa.FOLLOWUP_PAID_PATH,
        manifest_sha256=qa.FOLLOWUP_PAID_SHA256,
        actual_receipt_sha256=qa.object_digest(paid["raw"]["metadata"][qa.FOLLOWUP_PAID_RECEIPT]), proof=receipt)
    return reader, paid, dual


def test_only_frozen_missing_field_is_reconstructed_from_second_independent_receipt(exact_missing_binding):
    reader, paid, dual = exact_missing_binding
    assert "revalidated_followup_paid_response" not in reader["original_output_binding"]
    assert qa.frozen323_followup_review_binding(ROOT, AUDIT,
        "8ff73f3d5abba75148238f609d39f96957bf9e51e9b3f16add04c60806c8760c", reader, paid, dual)


@pytest.mark.parametrize("attack", ["declared_false", "different_review", "changed_audit", "primary", "model", "receipt", "producer", "peer_bytes"])
def test_frozen_missing_field_does_not_authorize_changed_or_unrelated_claims(exact_missing_binding, attack, tmp_path, monkeypatch):
    reader, paid, dual = deepcopy(exact_missing_binding)
    path, audit_sha = AUDIT, "8ff73f3d5abba75148238f609d39f96957bf9e51e9b3f16add04c60806c8760c"
    if attack == "declared_false": reader["original_output_binding"]["revalidated_followup_paid_response"] = None
    elif attack == "different_review": path = "data/audits/pulso_unrelated_review.json"
    elif attack == "changed_audit": audit_sha = "0" * 64
    elif attack == "primary": paid["raw"]["metadata"]["page_text"] += " changed"
    elif attack == "model": paid["raw"]["metadata"]["analysis_model_output"]["what_happened"] += " changed"
    elif attack == "receipt": paid["raw"]["metadata"][qa.FOLLOWUP_PAID_RECEIPT]["new_validation_sha256"] = "0" * 64
    elif attack == "producer": dual["publication_execution_code"] = "0" * 40
    elif attack == "peer_bytes":
        fake = tmp_path / "peer.json"
        fake.write_bytes((ROOT / PEER).read_bytes() + b" ")
        original = qa.local_capture_path
        monkeypatch.setattr(qa, "local_capture_path", lambda root, p: fake if p == PEER else original(root, p))
    try:
        accepted = qa.frozen323_followup_review_binding(ROOT, path, audit_sha, reader, paid, dual)
    except (ValueError, KeyError):
        accepted = False
    assert not accepted
