"""Retained fresh paid answers, not manufactured evidence or publication quota."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_editorial_proof import (
    future_copy_qualified, unqualified_achieved_copy,
    unsupported_clinical_completion, validate_pulso_editorial_proof,
)


FIXTURE = Path(__file__).parent / "fixtures/pulso_actual_v5_future_holds.json.gz"
RAW = gzip.decompress(FIXTURE.read_bytes())
OBSERVED = json.loads(RAW)
ROWS = OBSERVED["rows"]


def test_all25_real_complete_primary_inputs_and_fresh_response_ids_retained():
    assert hashlib.sha256(RAW).hexdigest() == "d82468964f11e913abb441ae8a327c52aca7fd46bd363275ac9a6a5637510106"
    assert len(ROWS) == 25
    assert set(OBSERVED["inputs"]) == {"history", "queue", "runtime_report", "telemetry"}
    assert OBSERVED["producer_commit"] == "981b0ff25c226d47785b77944aa53c459053aa21"
    assert len({r["model_response"]["response_id"] for r in ROWS}) == 25
    for row in ROWS:
        assert hashlib.sha256(row["full_primary_body"].encode()).hexdigest() == row["body_sha256"] == row["model_response"]["analysis_text_sha256"]
        assert row["model_response"] == row["analysis"]["_pulso_analysis_meta"]


@pytest.mark.parametrize("index,row", list(enumerate(ROWS, 1)), ids=[r["url"].split("/")[-2] for r in ROWS])
def test_every_actual_future_hold_replayed_without_changing_its_answer(index, row):
    before = deepcopy(row["analysis"])
    verdict = validate_pulso_editorial_proof(row["analysis"], row["full_primary_body"])
    # Three nonliteral source quotes, a rewritten whole summary, and the
    # approval-scope finding remain held. No punctuation or words are deleted.
    expected = ("rejected" if index in {22, 24} else
                "deferred" if index in {3, 7, 12, 17, 21} else "ready")
    assert verdict["decision"] == expected
    assert verdict["publication_approved"] is False
    assert verdict["quote_validation_is_semantic_approval"] is False
    assert row["analysis"] == before
    assert row["analysis"]["relevance_score"] == before["relevance_score"]


@pytest.mark.parametrize("text", [
    "La estrategia se implementaría y ocurriría durante el segundo semestre.",
    "Las devoluciones deberían completarse hasta diciembre de 2037.",
    "La nota del 24 de agosto de 2026 advertía que las lluvias podían elevar la circulación.",
    "Al 19 de agosto de 2026, el efecto esperado era ampliar la resolutividad con capacidad estimada.",
    "Al 18 de julio de 2026, comenzaron coordinaciones con Defensa para instalar un hospital modular.",
])
def test_demonstrated_conditional_and_dated_nonachievement_phrases(text):
    assert future_copy_qualified(text)


@pytest.mark.parametrize("text", [
    "La secretaría mantuvo el registro de enfermería y minería.",
    "La capacidad fue agregada y el hospital se encuentra operativo.",
    "El efecto esperado era ampliar la capacidad.",  # no observation-day context
    "La inversión hospitalaria prioritaria y necesaria tiene capacidad disponible.",
    "La atención secundaria unitaria ordinaria y comunitaria fue implementada.",
    "La cafetería hospitalaria tiene capacidad disponible.",
    "La peluquería comunitaria está operativa.",
    "La droguería hospitalaria dispone de nueva capacidad.",
    "La repostería necesaria fue implementada.",
    "La joyería ordinaria tiene capacidad instalada.",
    "La subsecretaría reportó los requerimientos que requerían los equipos.",
    "Al 18 de julio de 2026, la nota no acredita otra medida. El hospital modular ya está instalado.",
    "Al 18 de julio de 2026, la nota no acredita otra medida. El Minsal ya ha ejecutado la instalación.",
    "Al 18 de julio de 2026, la nota no acredita otra medida. El hospital dispone de capacidad clínica disponible.",
    "Al 18 de julio de 2026, la capacidad fue agregada y el hospital se encuentra operativo. La nota no demuestra vigencia.",
])
def test_generic_nouns_or_unqualified_past_states_are_not_future_proof(text):
    assert not future_copy_qualified(text)


@pytest.mark.parametrize("text", [
    "Las acciones fueron anunciadas, no como resultados ya ejecutados.",
    "Esas acciones futuras no deben entenderse como ya ejecutadas.",
    "La nota no se ejecutó y el plan permanece propuesto.",
])
def test_explicit_local_denial_is_not_completed_execution(text):
    assert not unqualified_achieved_copy(text)


@pytest.mark.parametrize("text", [
    "Las acciones futuras ya se ejecutaron.",
    "La nota no confirma otra medida; el hospital ya se implementó.",
    "No hubo retrasos y ya se ejecutó el plan.",
    "Las acciones no sólo ya se ejecutaron sino que ampliaron la capacidad.",
    "La instalación ya se concretó, no como resultados ya ejecutados.",
])
def test_negation_elsewhere_cannot_hide_unqualified_achievement(text):
    assert unqualified_achieved_copy(text)


def test_actual_sar_projection_cannot_be_replaced_by_already_realized_capacity():
    row = ROWS[9]
    ai = deepcopy(row["analysis"])
    ai["why_it_matters"] = "El SAR ya realizó 65.000 atenciones y el plan ya instaló nueva capacidad."
    claim = next(c for c in ai["pulso_editorial_proof"]["future_claims"] if c["summary_field"] == "why_it_matters")
    claim["summary_quote"] = ai["why_it_matters"]
    assert validate_pulso_editorial_proof(ai, row["full_primary_body"])["reason"] == "pulso_editorial_future_copy_not_grounded"


def test_real_sar_opening_and_estimated_capacity_remain_a_valid_mixed_account():
    row = ROWS[9]
    assert "inauguraron el primer Centro de Salud de Alta Resolutividad (SAR)" in row["full_primary_body"]
    assert "se estima que tendrá una capacidad para realizar 65 mil atenciones al año" in row["full_primary_body"]
    before = deepcopy(row["analysis"])
    result = validate_pulso_editorial_proof(row["analysis"], row["full_primary_body"])
    assert result["decision"] == "ready"
    assert result["prospective_evidence"] is True and result["publication_approved"] is False
    assert row["analysis"] == before


def test_actual_model_numeric_finding_remains_explicitly_unapproved_by_technical_ready():
    row = ROWS[5]
    assert "equivalente al 2,83%" in row["analysis"]["what_happened"]
    assert row["independent_assessment"]["classification"] == "validator_false_negative_with_independent_numeric_finding"
    verdict = validate_pulso_editorial_proof(row["analysis"], row["full_primary_body"])
    assert verdict["publication_approved"] is False
    assert verdict["quote_validation_is_semantic_approval"] is False


def test_dated_disclaimer_does_not_hide_separate_available_capacity_claim():
    row = ROWS[24]
    ai = deepcopy(row["analysis"])
    ai["what_happened"] = (
        "Al 18 de julio de 2026, la nota no acredita la ejecución. "
        "La inversión hospitalaria ya tiene capacidad disponible.")
    for claim in ai["pulso_editorial_proof"]["future_claims"]:
        if claim["summary_field"] == "what_happened":
            claim["summary_quote"] = ai["what_happened"]
    assert validate_pulso_editorial_proof(ai, row["full_primary_body"])["reason"] == "pulso_editorial_future_copy_not_grounded"


@pytest.mark.parametrize("row", ROWS, ids=[r["url"].split("/")[-2] for r in ROWS])
def test_generic_dated_denial_cannot_qualify_completed_future_acts_in_any_actual_answer(row):
    ai = deepcopy(row["analysis"])
    ai["what_happened"] = (
        "Según La Tercera, al 2026-10-11 la red amplió la capacidad asistencial "
        "e incorporó las prestaciones. La nota no acredita la vigencia al 2026-10-11.")
    for claim in ai["pulso_editorial_proof"]["future_claims"]:
        if claim["summary_field"] == "what_happened":
            claim["summary_quote"] = ai["what_happened"]
    verdict = validate_pulso_editorial_proof(ai, row["full_primary_body"])
    assert verdict["decision"] != "ready"
    assert verdict["publication_approved"] is False


@pytest.mark.parametrize("claim", [
    "El hospital modular ya está instalado.",
    "El Minsal ya ha ejecutado la instalación.",
    "El hospital dispone de capacidad clínica disponible.",
    "La capacidad fue agregada y el hospital se encuentra operativo.",
])
def test_real_ovalle_future_proof_cannot_be_laundered_by_an_unrelated_dated_denial(claim):
    row = ROWS[24]
    ai = deepcopy(row["analysis"])
    ai["what_happened"] = "Al 18 de julio de 2026, la nota no acredita otra medida. " + claim
    for proof in ai["pulso_editorial_proof"]["future_claims"]:
        if proof["summary_field"] == "what_happened":
            proof["summary_quote"] = ai["what_happened"]
    assert validate_pulso_editorial_proof(ai, row["full_primary_body"])["reason"] == "pulso_editorial_future_copy_not_grounded"


@pytest.mark.parametrize("claim", [
    "El hospital modular ya está instalado y operativo.",
    "El Minsal ya ha ejecutado la instalación.",
    "El hospital dispone de capacidad clínica disponible.",
    "La capacidad fue agregada y el hospital se encuentra operativo.",
    "El hospital ya cuenta con capacidad instalada.",
    "El hospital modular ya funciona y atiende pacientes.",
])
def test_whole_field_future_clause_does_not_excuse_unsupported_clinical_completion(claim):
    row = ROWS[24]
    ai = deepcopy(row["analysis"])
    ai["what_happened"] = "El plan podría reforzar Ovalle. " + claim
    for proof in ai["pulso_editorial_proof"]["future_claims"]:
        if proof["summary_field"] == "what_happened":
            proof["summary_quote"] = ai["what_happened"]
    assert validate_pulso_editorial_proof(ai, row["full_primary_body"])["reason"] == "pulso_editorial_future_copy_not_grounded"


def test_clinical_completion_requires_positive_same_input_evidence_even_in_mixed_account():
    # A deliberately small synthetic input tests the boundary independently of
    # publisher facts: it never claims a captured source, model or publication.
    statement = "El hospital modular se encuentra operativo"
    assert not unsupported_clinical_completion(statement, statement + ". La ampliación podría continuar.")
    assert unsupported_clinical_completion(statement, "No " + statement.lower() + ". La ampliación podría continuar.")
    assert unsupported_clinical_completion(statement, "Comenzó la coordinación para instalar un hospital modular.")
