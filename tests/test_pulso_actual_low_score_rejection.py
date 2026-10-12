"""A real low score closes conservatively without bypassing response binding."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.processing import DeferredProcessing
from radar_salud.pulso_editorial_proof import validate_pulso_editorial_proof
from test_pulso_editorial_proof import bind, clinical_assessment, original_clinical_raw


FIXTURES = Path(__file__).parent / "fixtures"
CAPTURES = [json.loads(gzip.decompress((FIXTURES / name).read_bytes())) for name in (
    "pulso_actual_v5_nonfuture_holds.json.gz", "pulso_actual_v5_future_holds.json.gz")]
ROWS = [dict(row, analysis=row.get("analysis", row.get("ai")),
             full_primary_body=row.get("full_primary_body", row.get("body")))
        for capture in CAPTURES for row in capture["rows"]
        if row.get("analysis", row.get("ai"))["relevance_score"] < 72]


def test_all_six_actual_low_scores_reject_without_rewriting_paid_evidence():
    assert len(ROWS) == 6 and len({row["url"] for row in ROWS}) == 6
    for row in ROWS:
        ai, body = row["analysis"], row["full_primary_body"]
        before = deepcopy(ai)
        assert hashlib.sha256(body.encode()).hexdigest() == row["body_sha256"]
        assert ai["_pulso_analysis_meta"] == row.get("model_response", ai["_pulso_analysis_meta"])
        verdict = validate_pulso_editorial_proof(ai, body)
        assert verdict["decision"] == "rejected"
        assert verdict["reason"] == "editorial_relevance_below_threshold"
        assert verdict["publication_approved"] is False
        assert verdict["quote_validation_is_semantic_approval"] is False
        assert ai == before


@pytest.mark.parametrize("score", [None, True, -1, 101, "71", 71.0])
def test_invalid_score_cannot_become_a_conservative_editorial_rejection(score):
    body, ai = clinical_assessment()
    ai["relevance_score"] = score
    verdict = validate_pulso_editorial_proof(ai, body)
    assert verdict["decision"] == "deferred"
    assert verdict["reason"] == "pulso_editorial_proof_invalid_score"


@pytest.mark.parametrize("malformation", ["missing", "wrong_type", "future_list",
    "future_item", "future_keys", "future_field", "future_summary", "future_source"])
def test_low_score_still_requires_complete_provider_schema(malformation):
    body, ai = clinical_assessment()
    ai["relevance_score"] = 71
    proof = ai["pulso_editorial_proof"]
    if malformation == "missing":
        proof.pop("action_quote")
    elif malformation == "wrong_type":
        proof["actor"] = []
    elif malformation == "future_list":
        proof["future_claims"] = None
    else:
        claim = dict(summary_field="what_happened", summary_quote="future copy", source_quote="primary quote")
        if malformation == "future_item":
            claim = None
        elif malformation == "future_keys":
            claim.pop("source_quote")
        elif malformation == "future_field":
            claim["summary_field"] = "other"
        elif malformation == "future_summary":
            claim["summary_quote"] = []
        elif malformation == "future_source":
            claim["source_quote"] = None
        proof["future_claims"] = [claim]
    assert validate_pulso_editorial_proof(ai, body)["decision"] == "deferred"


@pytest.mark.parametrize("mismatch", ["request_input_sha256", "analysis_text_sha256", "response_id", "schema_version"])
def test_low_score_cross_request_or_missing_response_binding_defers_in_real_processor(monkeypatch, mismatch):
    raw = original_clinical_raw()
    _, ai = clinical_assessment()
    ai["relevance_score"] = 71
    def unbound(**request):
        answer = bind(ai, request)
        answer["_pulso_analysis_meta"][mismatch] = "" if mismatch == "response_id" else "wrong"
        return answer
    monkeypatch.setattr(llm_analysis, "analyze_news", unbound)
    with pytest.raises(DeferredProcessing, match="pulso_editorial_model_binding_mismatch"):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.metadata["editorial_assessment"]["decision"] == "pending"
    assert raw.metadata["analysis_model_output"]["relevance_score"] == 71


def test_unchanged_71_72_boundary_never_turns_unsupported_above_gate_copy_into_ready():
    body, ai = clinical_assessment()
    ai["pulso_editorial_proof"]["action"] = "acción inventada sin prueba"
    ai["relevance_score"] = 71
    assert validate_pulso_editorial_proof(ai, body)["reason"] == "editorial_relevance_below_threshold"
    ai["relevance_score"] = 72
    assert validate_pulso_editorial_proof(ai, body)["reason"] == "pulso_editorial_action_not_grounded"
