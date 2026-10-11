"""Independent QA consumes actual Oct5 bytes, never approves publication."""
from copy import deepcopy
from dataclasses import asdict
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("addendum_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
spec = importlib.util.spec_from_file_location("original_oct5", ROOT / "tests/test_pulso_oct5_incremental_addendum.py")
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)


@pytest.fixture
def evidence(tmp_path):
    for relative in (qa.INCREMENTAL_REVIEW_PATH, qa.INCREMENTAL_ADDENDUM_PATH):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    raw = original.held_original()
    assert original.review.apply_incremental_review(raw)
    return asdict(raw), tmp_path


def test_literal_analysis_release_keeps_prior_review_without_publication_approval(evidence):
    raw, root = evidence
    before = deepcopy(raw)
    assert qa.verify_incremental_addendum_reference(raw, root) == dict(
        review_ref=qa.INCREMENTAL_ADDENDUM_PATH, review_sha256=qa.INCREMENTAL_ADDENDUM_SHA256,
        analysis_release_only=True, publication_approved=False)
    assert raw == before


@pytest.mark.parametrize("decision", ["published", "rejected"])
def test_completed_editorial_decision_retains_analysis_release_provenance(evidence, decision):
    raw, root = evidence
    raw["metadata"]["editorial_assessment"] = dict(decision=decision, reason="unit_actual_decision")
    assert qa.verify_incremental_addendum_reference(raw, root)["publication_approved"] is False


@pytest.mark.parametrize("field,value", [
    ("review_sha256", "0" * 64), ("prior_review_sha256", "0" * 64),
    ("publication_approved", True), ("decision", "publish"),
    ("verified_publication_date", "2026-10-04"), ("verified_body_sha256", "0" * 64),
    ("verified_html_sha256", "0" * 64), ("verified_captured_at", "2026-10-11T11:11:11Z"),
])
def test_analysis_release_flag_cannot_override_exact_bound_provenance(evidence, field, value):
    raw, root = evidence
    raw["metadata"]["incremental_review_addendum"][field] = value
    with pytest.raises(ValueError, match="applied_original_or_provenance_mismatch"):
        qa.verify_incremental_addendum_reference(raw, root)


@pytest.mark.parametrize("field,value", [
    ("page_text", "Un resumen no sustituye el cuerpo primario completo."),
    ("publication_date", "2026-10-04"), ("primary_identity_verified", False),
    ("publication_date_verified", False), ("article_body_complete", False),
    ("html_sha256", "0" * 64), ("incremental_review", {}),
])
def test_changed_original_or_discarded_prior_review_cannot_validate(evidence, field, value):
    raw, root = evidence
    raw["metadata"][field] = value
    with pytest.raises(ValueError, match="applied_original_or_provenance_mismatch"):
        qa.verify_incremental_addendum_reference(raw, root)


@pytest.mark.parametrize("relative", [qa.INCREMENTAL_REVIEW_PATH, qa.INCREMENTAL_ADDENDUM_PATH])
def test_either_immutable_review_changed_blocks_reading(evidence, relative):
    raw, root = evidence
    path = root / relative
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="immutable_review_changed"):
        qa.verify_incremental_addendum_reference(raw, root)
