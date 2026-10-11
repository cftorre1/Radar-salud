"""Replay every held response from the real first focused FAST execution."""
import copy
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from radar_salud.llm_analysis import news_analysis_input
from radar_salud.pulso_editorial_proof import (
    VERSION, PROOF_SCHEMA, FUTURE_SOURCE, human_health_scope_anchor, literal_quote_matches,
    model_binding_matches, validate_pulso_editorial_proof,
)

FIXTURE = Path(__file__).parent / "fixtures/pulso_focus_all69_actual_models.json.gz"
CAPTURE = gzip.decompress(FIXTURE.read_bytes())
assert hashlib.sha256(CAPTURE).hexdigest() == "de2d7642695b2cd2f2875d985ea340919efdec7542b8f1413ff8cb17e80c2fb7"
ROWS = json.loads(CAPTURE)["rows"]


def test_all69_actual_complete_inputs_and_outputs_remain_bound_and_unmodified():
    assert len(ROWS) == len({r["url"] for r in ROWS}) == 69
    before = hashlib.sha256(CAPTURE).hexdigest()
    counts = Counter()
    for row in ROWS:
        body, ai = row["body"], row["ai"]
        meta = ai["_pulso_analysis_meta"]
        assert hashlib.sha256(body.encode()).hexdigest() == row["body_sha256"] == row["analysis_input_sha256"] == meta["analysis_text_sha256"]
        assert row["input_complete"] is True and row["analysis_input_format"] == "full_primary_article_body"
        request = news_analysis_input(title=row["title"], text=body, source_name="Pulso / La Tercera", full_text=True)
        request_sha = hashlib.sha256(request.encode()).hexdigest()
        assert request_sha == meta["request_input_sha256"]
        assert meta["schema_version"] == "pulso_editorial_proof_v4" and meta["response_id"]
        # Old output is diagnostic evidence, never an eligible fresh v5 answer.
        assert not model_binding_matches(ai, source_name="Pulso / La Tercera", input_text_sha256=row["body_sha256"], request_input_sha256=request_sha)
        verdict = validate_pulso_editorial_proof(ai, body)
        assert verdict["publication_approved"] is False
        assert verdict["quote_validation_is_semantic_approval"] is False
        counts[(verdict["decision"], verdict["reason"])] += 1
    assert counts == {
        ("deferred", "pulso_editorial_actor_not_grounded"): 23,
        ("deferred", "pulso_editorial_action_not_grounded"): 23,
        ("deferred", "pulso_editorial_scope_not_grounded"): 7,
        ("deferred", "pulso_editorial_status_or_novelty_not_grounded"): 4,
        ("deferred", "pulso_editorial_consequence_not_grounded"): 4,
        ("deferred", "pulso_editorial_scope_quote_not_in_input"): 3,
        ("ready", "pulso_editorial_grounded_assessment"): 3,
        ("deferred", "pulso_editorial_future_copy_not_grounded"): 1,
        ("deferred", "pulso_editorial_incremental_value_uncertain"): 1,
    }
    assert hashlib.sha256(gzip.decompress(FIXTURE.read_bytes())).hexdigest() == before


@pytest.mark.parametrize("row", [r for r in ROWS if r["reason"] == "pulso_editorial_future_copy_not_grounded"], ids=lambda r: r["title"])
def test_three_actual_conditional_copies_are_grounded_without_approval_or_score_changes(row):
    ai = copy.deepcopy(row["ai"])
    verdict = validate_pulso_editorial_proof(ai, row["body"])
    assert verdict["decision"] == "ready" and verdict["prospective_evidence"] is True
    assert verdict["publication_approved"] is False
    assert ai == row["ai"]
    if "San Antonio" in row["title"]:
        assert ai["relevance_score"] == 70 < 72
    for claim in ai["pulso_editorial_proof"]["future_claims"]:
        assert claim["summary_quote"] == ai[claim["summary_field"]]
    ai["what_happened"] = "La medida ya aumentó la capacidad disponible. La ampliación podría seguir."
    for claim in ai["pulso_editorial_proof"]["future_claims"]:
        if claim["summary_field"] == "what_happened":
            claim["summary_quote"] = ai["what_happened"]
    assert validate_pulso_editorial_proof(ai, row["body"])["reason"] == "pulso_editorial_future_copy_not_grounded"


def test_actual_ovalle_coordination_does_not_prove_installed_or_available_capacity():
    row = next(r for r in ROWS if "instalacion-de-hospital-modular" in r["url"])
    assert row["body_sha256"] == "1b38b507061816c3a60f47bd77db1baad718cf7314a5de2d4a716bc690fddc1f"
    correct = validate_pulso_editorial_proof(row["ai"], row["body"])
    assert correct["decision"] == "ready" and correct["prospective_evidence"] is True
    bad = copy.deepcopy(row["ai"])
    bad["what_happened"] = "Según La Tercera, el Minsal ya instaló el hospital modular de Ovalle."
    bad["why_it_matters"] = "El hospital ya amplió la capacidad disponible para atender pacientes."
    bad["pulso_editorial_proof"].update(event_status="actual", future_claims=[])
    verdict = validate_pulso_editorial_proof(bad, row["body"])
    assert verdict["decision"] == "deferred" and verdict["reason"] == "pulso_editorial_future_status_mismatch"


def test_actual_sar_inauguration_does_not_prove_estimated_yearly_attentions_achieved():
    row = next(r for r in ROWS if "recinto-podra-realizar-65-mil" in r["url"])
    assert row["body_sha256"] == "b19cf891c76d50a414054e4819e3dc943134c6d5329b5cc1430e7bd4813f3b6b"
    assert validate_pulso_editorial_proof(row["ai"], row["body"])["prospective_evidence"] is True
    bad = copy.deepcopy(row["ai"])
    bad["what_happened"] = "Según La Tercera, el SAR ya realizó 65.000 atenciones anuales."
    bad["why_it_matters"] = "El SAR ya descongestionó los hospitales con esas 65.000 atenciones."
    bad["pulso_editorial_proof"].update(event_status="actual", future_claims=[],
        consequence="tendrá una capacidad para realizar 65 mil atenciones al año",
        consequence_quote="se estima que tendrá una capacidad para realizar 65 mil atenciones al año.")
    verdict = validate_pulso_editorial_proof(bad, row["body"])
    assert verdict["decision"] == "deferred" and verdict["reason"] == "pulso_editorial_future_status_mismatch"


def test_actual_scope_lexical_repairs_leave_seven_insufficient_quotes_held():
    rows = [r for r in ROWS if r["reason"] == "pulso_editorial_scope_not_grounded"]
    assert len(rows) == 20
    repaired = [r for r in rows if human_health_scope_anchor(r["ai"]["pulso_editorial_proof"]["human_health_scope_quote"])]
    assert len(repaired) == 13
    assert any("2.513.508 consultas de especialidad" in r["ai"]["pulso_editorial_proof"]["human_health_scope_quote"] for r in repaired)
    assert any("atenciones oncológicas" in r["ai"]["pulso_editorial_proof"]["human_health_scope_quote"] for r in repaired)
    assert any("cirugías estéticas" in r["ai"]["pulso_editorial_proof"]["human_health_scope_quote"] for r in repaired)
    for text in ("financiamiento del sector con una mirada de largo plazo", "un equipo de diez profesionales", "una realidad demográfica completamente distinta", "cirugías veterinarias de animales", "la sanidad vegetal de la producción"):
        assert not human_health_scope_anchor(text)


def test_equivalent_typography_remains_a_contiguous_quote_with_all_factual_tokens():
    source = "La red informó: “No hay 12 pacientes trasladados; son 21”. Luego atendió consultas."
    assert literal_quote_matches('la red informó: "No hay 12 pacientes trasladados; son 21".', source)
    assert literal_quote_matches('"No hay 12 pacientes trasladados; son 21"', source)
    for bad in ("La red informó: Hay 12 pacientes trasladados; son 21", "No hay 21 pacientes trasladados; son 12", "No hay 12 pacientes trasladados son 21", "La red informó ... Luego atendió consultas.", "La red informó y luego atendió consultas."):
        assert not literal_quote_matches(bad, source)


def test_v5_schema_instructs_exact_short_fields_and_entire_future_summaries():
    assert VERSION == "pulso_editorial_proof_v5"
    for field in ("actor", "action", "consequence"):
        assert "EXACTO" in PROOF_SCHEMA["properties"][field]["description"]
        assert "CONTIGUO" in PROOF_SCHEMA["properties"][field + "_quote"]["description"]
    assert "TODO" in PROOF_SCHEMA["properties"]["future_claims"]["items"]["properties"]["summary_quote"]["description"]


@pytest.mark.parametrize("verb", ["eliminará", "llegará", "liberará", "comprará", "aumentará", "presentarán", "citará", "ejercerá", "viajará"])
def test_regular_pending_future_grammar_is_present_in_actual_selected_evidence(verb):
    quotes = [r["ai"]["pulso_editorial_proof"][field] for r in ROWS for field in (
        "action_quote", "consequence_quote", "event_status_quote")]
    assert len(quotes) == 207
    witnesses = [quote for quote in quotes if verb in quote]
    assert witnesses and all(FUTURE_SOURCE.search(quote) for quote in witnesses)


def test_actual_legal_obligation_and_insurance_plan_are_not_mislabeled_future_proposals():
    row = next(r for r in ROWS if "historica-condena-por-megafraude" in r["url"])
    quote = row["ai"]["pulso_editorial_proof"]["action_quote"]
    assert "deberán pagar" in quote and not FUTURE_SOURCE.search(quote)
    row = next(r for r in ROWS if "planes-mas-baratos" in r["url"])
    quote = row["ai"]["pulso_editorial_proof"]["consequence_quote"]
    assert "plan" in quote and not FUTURE_SOURCE.search(quote)
    for past in ("eliminaron", "llegó", "liberaron", "compraron", "aumentó", "presentaron", "citó", "ejerció", "viajó"):
        assert not FUTURE_SOURCE.search(past)
