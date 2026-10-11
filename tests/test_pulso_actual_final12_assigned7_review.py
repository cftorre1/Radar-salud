"""Reconcile all seven actual outcomes and validate four paid reviews offline."""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from radar_salud.pulso_editorial_review import apply_review, canonical_sha, validate_independent_binding
from radar_salud.pulso_source import extract_article

ROOT = Path(__file__).parents[1]
PRODUCER = "66f37ca044b4cf233bc9f649b7140ff8a69855d3"
READER = "data/audits/pulso_actual_final12_assigned7_independent_semantic_review_2026_10_11.json"
REVIEW = "data/audits/pulso_actual_final12_assigned7_editorial_corrections_2026_10_11.json"
READER_SHA = "128ddb2296591847f30576c1613fab2984995ada459c2f7b3f7b94e164a64b4a"
REVIEW_SHA = "1a08eeb947162a921756546f82a704db18371c066a2065b31042222ac69a544c"
spec = importlib.util.spec_from_file_location("final12_assigned7_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


@pytest.fixture(scope="module")
def original():
    reader_raw, review_raw = (ROOT / READER).read_bytes(), (ROOT / REVIEW).read_bytes()
    assert qa.digest(reader_raw) == READER_SHA
    assert qa.digest(review_raw) == REVIEW_SHA
    reader, audit = json.loads(reader_raw), json.loads(review_raw)
    validate_independent_binding(audit, reader, independent_sha256=READER_SHA)
    archived = {}
    assert set(reader["inputs"]) == {"queue", "history", "runtime_report", "telemetry"}
    for kind, reference in reader["inputs"].items():
        assert reference["commit"] == PRODUCER
        raw = subprocess.check_output(["git", "show", PRODUCER + ":" + reference["path"]], cwd=ROOT)
        assert qa.digest(raw) == reference["file_sha256"]
        if kind in {"queue", "history"}:
            archived[kind] = json.loads(raw)
    urls = {row["url"] for row in reader["rows"]}
    queue = {key: row for key, row in archived["queue"].items() if row["raw"].get("url") in urls}
    history = [row for row in archived["history"]["signals"] if row.get("source_url") in urls]
    return reader, audit, queue, history


def test_all_seven_are_actual_primary_bodies_and_outcomes_not_fabricated_publications(original):
    reader, audit, queue, history = original
    assert {row["cohort_index"]: (row["actual_status"], row["actual_score"]) for row in reader["rows"]} == {
        38: ("published", 86), 64: ("published", 92), 89: ("published", 88),
        28: ("retry", 90), 73: ("rejected", 68), 70: ("retry", 84), 14: ("published", 84),
    }
    assert len(history) == len(audit["records"]) == 4
    assert {row["row_index"] for row in reader["all_signals"]} == {38, 64, 89, 14}
    for row in reader["rows"]:
        entry = queue[row["queue_fingerprint"]]
        metadata = entry["raw"]["metadata"]
        assert row["original_full_primary_body"] == metadata["page_text"]
        assert row["actual_full_model_output"] == metadata["analysis_model_output"]
        assert canonical_sha(row["actual_full_model_output"]) == row["actual_model_output_semantic_sha256"]
        fixture = row["raw_fixture_verification"]
        raw = subprocess.check_output(["git", "show", PRODUCER + ":" + fixture["path"]], cwd=ROOT)
        assert qa.digest(raw) == fixture["gzip_sha256"]
        html = gzip.decompress(raw)
        assert qa.digest(html) == row["original_html_sha256"]
        _, body, parsed = extract_article(html.decode(), row["url"])
        assert body == row["original_full_primary_body"]
        assert parsed["publication_date"] == row["publication_date"]
        assert entry["lane"] == "BACKFILL" and entry["attempts"] == 4


@pytest.fixture(scope="module")
def reviewed(original, tmp_path_factory):
    reader, audit, queue, history = original
    before = deepcopy((history, queue))
    after, updated, report = apply_review(history, queue, audit, audit_sha256=REVIEW_SHA, audit_path=REVIEW)
    assert (history, queue) == before
    assert report["decisions"] == dict(accept=1, correct=3, reject=0, group=0)
    assert report["ai_calls"] == 0 and report["applied_count"] == 4
    root = tmp_path_factory.mktemp("final12_review")
    (root / ".git").symlink_to(subprocess.check_output(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True).strip(), target_is_directory=True)
    files = {
        READER, REVIEW, qa.CODE_REPAIR_PINS_PATH,
        qa.INCREMENTAL_REVIEW_PATH, qa.INCREMENTAL_ADDENDUM_PATH,
        *qa.paid_revalidation_proof_files(ROOT), *qa.current_paid_proof_files(ROOT),
    }
    for path in files:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    (root / qa.EDITORIAL_REGISTRY_PATH).write_text(json.dumps(dict(
        schema_version="pulso_paid_editorial_review_registry_v1", source_id="pulso_latercera",
        reviews=[dict(review_file=REVIEW, review_sha256=REVIEW_SHA,
                      independent_review_file=READER, independent_review_sha256=READER_SHA)])))
    proofs, findings = qa.verify_additional_editorial_reviews(updated, after, dict(signals=after), root)
    assert len(proofs) == 4 and findings == []
    return after, updated, proofs


def test_categories_copy_and_all_original_paid_models_scores_prospective_flags_preserved(original, reviewed):
    reader, _, queue, _ = original
    history, updated, proofs = reviewed
    assert len(proofs) == 4
    for row in reader["all_signals"]:
        signal = next(s for s in history if s["source_url"] == row["url"])
        old, new = queue[row["queue_fingerprint"]], updated[row["queue_fingerprint"]]
        assert new["raw"]["metadata"]["analysis_model_output"] == old["raw"]["metadata"]["analysis_model_output"]
        assert new["raw"]["metadata"]["page_text"] == old["raw"]["metadata"]["page_text"]
        assert new["status"] == old["status"] == "published" and new["attempts"] == old["attempts"]
        assert signal["editorial_relevance"] == row["actual_score"]
        assert signal["prospective_evidence"] == new["raw"]["metadata"]["prospective_evidence"] is True
        assert signal["evidence_maturity"] == "media_reported"
        assert signal["what_happened"] == row.get("proposed_what_happened", row["original_published_what_happened"])
        assert signal["why_it_matters"] == row.get("proposed_why_it_matters", row["original_published_why_it_matters"])
        if row["row_index"] == 64:
            assert signal["category"] == "Prestadores"
            assert signal["what_happened"].startswith("Según Pulso / La Tercera,")
            assert "BACKFILL" not in signal["what_happened"] + signal["why_it_matters"]
        elif row["row_index"] == 14:
            assert signal["category"] == "Regulación & Legal"
        elif row["row_index"] == 89:
            assert signal["what_happened"] == row["original_published_what_happened"]
            assert "distinto de la alianza con Caja Los Andes" in signal["why_it_matters"]
    for row in reader["rows"]:
        if row["actual_status"] != "published":
            assert updated[row["queue_fingerprint"]] == queue[row["queue_fingerprint"]]


def test_exact_repeat_is_inert(original, reviewed):
    _, audit, _, _ = original
    history, queue, _ = reviewed
    after, updated, report = apply_review(history, queue, audit, audit_sha256=REVIEW_SHA, audit_path=REVIEW)
    assert report["applied_count"] == 0 and report["unchanged_on_replay"] == 4
    assert (after, updated) == (history, queue)


def test_hanta_guard_diagnosis_does_not_approve_novelty_against_already_published_august8(original):
    reader, _, _, _ = original
    row = next(row for row in reader["rows"] if row["cohort_index"] == 28)
    context = row["contextual_novelty_diagnosis"]
    later = next(record for record in reader["related_primary_fullbody_context"]
                 if record["url"] == context["existing_published_url"])
    assert later["publication_date"] == "2026-08-08" and context["human_publication_approval"] is False
    assert qa.digest(later["original_full_primary_body"].encode()) == context["existing_body_sha256"]
    assert all(quote in later["original_full_primary_body"] for quote in context["body_quotes_later_original"])
    assert context["recommended_route"] == "new_FAST_with_contextual_novelty_comparison"
    assert row["pending_not_human_approved"] is True
    assert all(record["row_index"] != 28 for record in reader["all_signals"])


@pytest.mark.parametrize("attack", ["category", "unreviewed_copy", "altered_primary"])
def test_a_review_cannot_introduce_unreviewed_changes_or_another_primary(original, attack):
    reader, audit, queue, history = deepcopy(original)
    record = next(record for record in audit["records"] if "aps-universal" in record["url"])
    if attack == "altered_primary":
        parent = next(row for row in reader["all_signals"] if row["url"] == record["url"])
        queue[parent["queue_fingerprint"]]["raw"]["metadata"]["page_text"] += " invented data"
        with pytest.raises(ValueError, match="primary_body_or_date"):
            apply_review(history, queue, audit, audit_sha256=REVIEW_SHA, audit_path=REVIEW)
    else:
        record["proposed"]["category" if attack == "category" else "what_happened"] = "unreviewed alteration"
        with pytest.raises(ValueError, match="not_independently_reviewed"):
            validate_independent_binding(audit, reader, independent_sha256=READER_SHA)
