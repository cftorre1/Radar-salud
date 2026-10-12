"""Exercise real duplicate grouping with exact, unchanged native survivors."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from radar_salud.pulso_editorial_review import apply_review, canonical_sha, validate_independent_binding

ROOT = Path(__file__).parents[1]
READER = "data/audits/pulso_cross_source_three_duplicate_publications_independent_review_2026_10_11.json"
REVIEW = "data/audits/pulso_cross_source_three_duplicate_publications_editorial_group_2026_10_11.json"
READER_SHA = "361fea64fddce6689795d174371443ce306884e501276085f38894c27c7cfbdd"
REVIEW_SHA = "a148a3e9bbbb71ae9430f05f6212a468760df298e3765d6549f5d141408befac"


@pytest.fixture(scope="module")
def evidence():
    reader_raw, review_raw = (ROOT / READER).read_bytes(), (ROOT / REVIEW).read_bytes()
    spec = importlib.util.spec_from_file_location("cross_groups_review_qa", ROOT / "scripts/qa_pulso_recovery.py")
    qa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qa)
    assert qa.digest(reader_raw) == READER_SHA and qa.digest(review_raw) == REVIEW_SHA
    reader, audit = json.loads(reader_raw), json.loads(review_raw)
    validate_independent_binding(audit, reader, independent_sha256=READER_SHA)
    archived = {}
    for name in ("queue", "history"):
        reference = reader["inputs"][name]
        original = subprocess.check_output(["git", "show", reference["commit"] + ":" + reference["path"]], cwd=ROOT)
        assert qa.digest(original) == reference["file_sha256"]
        archived[name] = json.loads(original)
    urls = {r["url"] for r in audit["records"]} | {r["duplicate_of"]["url"] for r in audit["records"]}
    queue = {key: entry for key, entry in archived["queue"].items() if entry["raw"].get("url") in urls}
    history = [s for s in archived["history"]["signals"] if s.get("source_url") in urls]
    return reader, audit, queue, history


def test_all_three_compare_full_primary_and_existing_publications_with_unchanged_paid_evidence(evidence):
    reader, audit, queue, history = evidence
    assert len(reader["all_signals"]) == len(audit["records"]) == 3
    for row in reader["all_signals"]:
        source = queue[row["queue_fingerprint"]]
        survivor = queue[row["duplicate_survivor_binding"]["queue_fingerprint"]]
        assert source["status"] == survivor["status"] == "published"
        assert row["original_full_primary_body"] == source["raw"]["metadata"]["page_text"]
        assert row["target_full_primary_content"] == survivor["raw"]["metadata"]["page_text"]
        assert row["original_full_signal"] in history and row["target_full_signal"] in history
        assert row["original_full_model_output"] == source["raw"]["metadata"].get("analysis_model_output")
        assert canonical_sha(row["immutable_cross_source_group_pin"]) == row["immutable_cross_source_group_pin_sha256"]
        assert all(q["text"] in row["original_full_primary_body"] for q in row["supporting_verbatim_quotes"])
        assert all(q["text"] in row["target_full_primary_content"] for q in row["target_supporting_verbatim_quotes"])
    legacy = next(r for r in reader["all_signals"] if "termina-traslado" in r["url"])
    assert legacy["original_model_output_missing"] is True
    assert legacy["original_model_response_binding"] is None and legacy["original_full_model_output"] is None


def test_group_changes_only_pulso_disposition_preserves_all_native_entries_and_prior_reviews(evidence):
    reader, audit, queue, history = evidence
    before = deepcopy((history, queue))
    after, updated, result = apply_review(history, queue, audit, audit_sha256=REVIEW_SHA, audit_path=REVIEW)
    assert (history, queue) == before and result["applied_count"] == 3 and result["ai_calls"] == 0
    assert result["decisions"] == dict(accept=0, correct=0, reject=0, group=3)
    for key, entry in queue.items():
        if entry["source"] != "pulso_latercera":
            assert updated[key] == entry
    for signal in history:
        if signal["source_name"] != "Pulso / La Tercera":
            assert signal in after
    for row in reader["all_signals"]:
        old, new = queue[row["queue_fingerprint"]], updated[row["queue_fingerprint"]]
        grouped = next(s for s in after if s["source_url"] == row["url"])
        assert new["status"] == "rejected" and grouped["feed_visibility"] is False
        assert grouped["editorial_decision"] == "group"
        assert grouped["editorial_review"]["previous_editorial_review"] == row["previous_editorial_review"]
        assert grouped["what_happened"] == row["original_published_what_happened"]
        assert grouped["why_it_matters"] == row["original_published_why_it_matters"]
        assert grouped["editorial_relevance"] == row["original_full_signal"]["editorial_relevance"]
        assert new["attempts"] == old["attempts"] and new["lane"] == old["lane"]
        assert new["raw"]["event_date"] == old["raw"]["event_date"]
        for field in ("analysis_model_output", "page_text", "html_sha256", "article_body_sha256"):
            assert new["raw"]["metadata"].get(field) == old["raw"]["metadata"].get(field)
    same_url = [e for e in queue.values() if e["raw"]["url"] == "https://www.suseso.gob.cl/605/w3-article-790601.html"]
    assert len(same_url) == 2 and {e["status"] for e in same_url} == {"rejected", "published"}
    again, repeated, replay = apply_review(after, updated, audit, audit_sha256=REVIEW_SHA, audit_path=REVIEW)
    assert (again, repeated) == (after, updated) and replay["applied_count"] == 0
    assert replay["unchanged_on_replay"] == 3


@pytest.mark.parametrize("attack", ["rejected_same_url", "source_id", "survivor_signal", "predecessor", "primary"])
def test_wrong_survivor_or_changed_primary_and_predecessor_cannot_authorize_group(evidence, attack):
    reader, audit, queue, history = deepcopy(evidence)
    record = next(r for r in audit["records"] if "chomali-por-listas" in r["url"])
    if attack == "rejected_same_url":
        sibling = next(key for key, entry in queue.items()
                       if entry["source"] == "suseso_fiscalizacion" and entry["raw"]["url"] == record["duplicate_of"]["url"])
        record["duplicate_of"]["queue_fingerprint"] = sibling
    elif attack == "source_id":
        record["duplicate_of"]["source_id"] = "suseso_fiscalizacion"
    elif attack == "survivor_signal":
        record["duplicate_of"]["survivor_signal_sha256"] = "f" * 64
    elif attack == "predecessor":
        record["previous_editorial_review"]["reason"] += " unreviewed change"
    else:
        parent = next(r for r in reader["all_signals"] if r["url"] == record["url"])
        queue[parent["queue_fingerprint"]]["raw"]["metadata"]["page_text"] += " invented data"
    with pytest.raises(ValueError):
        apply_review(history, queue, audit, audit_sha256=REVIEW_SHA, audit_path=REVIEW)
