"""Retained fresh paid answers, not manufactured evidence or publication quota."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_editorial_proof import (
    future_copy_qualified, unqualified_achieved_copy,
    validate_pulso_editorial_proof,
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
    expected = "deferred" if index in {3, 7, 12, 17, 21} else "ready"
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
    "Al 18 de julio de 2026, el contenido no acredita que el hospital modular haya sido instalado.",
])
def test_demonstrated_conditional_and_dated_nonachievement_phrases(text):
    assert future_copy_qualified(text)


@pytest.mark.parametrize("text", [
    "La secretaría mantuvo el registro de enfermería y minería.",
    "La capacidad fue agregada y el hospital se encuentra operativo.",
    "El efecto esperado era ampliar la capacidad.",  # no observation-day context
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


def test_actual_model_numeric_finding_remains_explicitly_unapproved_by_technical_ready():
    row = ROWS[5]
    assert "equivalente al 2,83%" in row["analysis"]["what_happened"]
    assert row["independent_assessment"]["classification"] == "validator_false_negative_with_independent_numeric_finding"
    verdict = validate_pulso_editorial_proof(row["analysis"], row["full_primary_body"])
    assert verdict["publication_approved"] is False
    assert verdict["quote_validation_is_semantic_approval"] is False
