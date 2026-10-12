"""Independent QA of ALL32 genuine outputs under the exact approved review.

Application here creates temporary test data only. No runtime state, model,
feed or queue file is written by these tests or the independent QA reader.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from radar_salud.pulso_editorial_review import apply_review

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("pulso_editorial_bound_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


@pytest.fixture
def reviewed(tmp_path):
    for path in (qa.EDITORIAL_REVIEW_PATH, qa.INDEPENDENT_EDITORIAL_PATH):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    audit = json.loads((tmp_path / qa.EDITORIAL_REVIEW_PATH).read_bytes())
    current = json.loads((ROOT / "data/state/pending_queue.json").read_bytes())
    queue, history = {}, []
    for record in audit["records"]:
        history.append(deepcopy(record["original_signal"]))
        matches = [(key, item) for key, item in current.items()
                   if item.get("source") == qa.SOURCE and item.get("raw", {}).get("url") == record["url"]
                   and item["raw"].get("event_date") == record["publication_date"]]
        assert len(matches) == 1
        key, item = matches[0]
        item = deepcopy(item)
        item.update(status="published", attempts=max(1, item["attempts"]))
        metadata = item["raw"]["metadata"]
        metadata.pop("editorial_review", None)
        metadata.update(editorial_assessment=deepcopy(record["original_model_assessment"]),
                        what_happened=record["original_signal"]["what_happened"],
                        why_it_matters=record["original_signal"]["why_it_matters"])
        queue[key] = item
    history, queue, _ = apply_review(history, queue, audit, audit_sha256=qa.EDITORIAL_REVIEW_SHA256,
                                    audit_path=qa.EDITORIAL_REVIEW_PATH)
    feed = [deepcopy(row) for row in history if row["feed_visibility"]]
    return dict(queue=queue, history=history, snapshot=dict(signals=feed), root=tmp_path)


def findings(value):
    return {row["code"] for row in qa.verify_bound_editorial_review(**value)[1]}


def test_exact_all32_preserves_paid_model_origins_gate_and_twelve_surviving_signals(reviewed):
    proofs, errors = qa.verify_bound_editorial_review(**reviewed)
    assert errors == []
    assert len(proofs) == 32
    assert sum(row["decision"] in {"reject", "group"} for row in proofs.values()) == 20
    assert len(reviewed["snapshot"]["signals"]) == 12


@pytest.mark.parametrize("attack,code", [
    ("both_provenance", "editorial_review_effective_state_or_provenance_changed"),
    ("effective_prose", "editorial_review_effective_state_or_provenance_changed"),
    ("assessment", "editorial_review_effective_state_or_provenance_changed"),
    ("body", "editorial_review_original_output_body_or_date_unverified"),
    ("day", "editorial_review_original_output_body_or_date_unverified"),
    ("partial_ack", "editorial_review_effective_state_or_provenance_changed"),
    ("withdrawn_feed", "withdrawn_editorial_publication_still_in_serialized_feed"),
    ("lost_retained", "reviewed_retained_publication_missing_or_duplicated_in_serialized_feed"),
    ("feed_text", "editorial_review_serialized_feed_changed"),
    ("other_record", "unbound_editorial_review_record"),
])
def test_flags_hash_fields_or_partial_write_never_grant_an_exemption(reviewed, attack, code):
    withdrawn = next(row for row in reviewed["history"] if row["editorial_decision"] == "reject")
    item = next(item for item in reviewed["queue"].values() if item["raw"]["url"] == withdrawn["source_url"])
    metadata = item["raw"]["metadata"]
    if attack == "both_provenance":
        withdrawn["editorial_review"]["decision"] = "accept"
        metadata["editorial_review"]["decision"] = "accept"
    elif attack == "effective_prose":
        withdrawn["what_happened"] += " Nuevo hecho inventado."
        metadata["what_happened"] = withdrawn["what_happened"]
    elif attack == "assessment":
        metadata["editorial_assessment"]["original_model_assessment"]["relevance_score"] = 71
    elif attack == "body":
        metadata["page_text"] += " Contenido inventado."
    elif attack == "day":
        metadata["publication_date"] = "2026-10-09"
    elif attack == "partial_ack":
        metadata.pop("editorial_review")
    elif attack == "withdrawn_feed":
        reviewed["snapshot"]["signals"].append(deepcopy(withdrawn))
    elif attack == "lost_retained":
        reviewed["snapshot"]["signals"].pop()
    elif attack == "feed_text":
        reviewed["snapshot"]["signals"][0]["what_happened"] += " Inventado."
    elif attack == "other_record":
        row = deepcopy(item)
        row["raw"]["url"] = "https://www.latercera.com/nacional/noticia/unbound-test/"
        reviewed["queue"]["forged"] = row
    proofs, errors = qa.verify_bound_editorial_review(**reviewed)
    assert proofs == {}
    assert code in {row["code"] for row in errors}


@pytest.mark.parametrize("path", [qa.EDITORIAL_REVIEW_PATH, qa.INDEPENDENT_EDITORIAL_PATH])
def test_complete_identity_preserving_audit_replacement_fails_frozen_file_sha(reviewed, path):
    target = reviewed["root"] / path
    target.write_bytes(target.read_bytes() + b" ")
    assert "independent_editorial_review_unverified" in findings(reviewed)
