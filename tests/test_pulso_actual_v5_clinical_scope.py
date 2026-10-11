"""The fresh v5 cohort demonstrates clinical scope omissions, not approval."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_editorial_proof import (
    human_health_scope_anchor, validate_pulso_editorial_proof,
)


FIXTURE = Path(__file__).parent / "fixtures/pulso_actual_v5_nonfuture_holds.json.gz"
RAW = gzip.decompress(FIXTURE.read_bytes())
OBSERVED = json.loads(RAW)
SCOPE = [r for r in OBSERVED["rows"] if r["reason"] == "pulso_editorial_scope_not_grounded"]
EXPECTED_SCOPE = [True, False, False, True, True, True, False, True, False, True, True]


def test_all24_actual_responses_and_complete_primary_bodies_stay_immutable():
    assert hashlib.sha256(RAW).hexdigest() == "91288ad1c62380820efe80b445ddf0f55d87b46ed54edf5c7ed549a796ebc796"
    assert OBSERVED["producer_commit"] == "981b0ff25c226d47785b77944aa53c459053aa21"
    assert set(OBSERVED["inputs"]) == {"history", "queue", "runtime_report", "telemetry"}
    assert len(OBSERVED["rows"]) == 24
    assert len({r["ai"]["_pulso_analysis_meta"]["response_id"] for r in OBSERVED["rows"]}) == 24
    for row in OBSERVED["rows"]:
        body_sha = hashlib.sha256(row["body"].encode()).hexdigest()
        assert body_sha == row["body_sha256"] == row["ai"]["_pulso_analysis_meta"]["analysis_text_sha256"]
        request = "Fuente: Pulso / La Tercera\nTítulo: " + row["title"] + "\nContenido:\n" + row["body"]
        assert hashlib.sha256(request.encode()).hexdigest() == row["ai"]["_pulso_analysis_meta"]["request_input_sha256"]


@pytest.mark.parametrize("row,expected", list(zip(SCOPE, EXPECTED_SCOPE)), ids=[r["url"].split("/")[-2] for r in SCOPE])
def test_all11_observed_scope_quotes_seven_clinical_four_generic(row, expected):
    quote = row["ai"]["pulso_editorial_proof"]["human_health_scope_quote"]
    assert quote in row["body"]
    assert human_health_scope_anchor(quote) is expected
    verdict = validate_pulso_editorial_proof(row["ai"], row["body"])
    assert verdict["publication_approved"] is False
    if not expected:
        assert verdict["reason"] == "pulso_editorial_scope_not_grounded"


def test_fixed_scope_does_not_clear_other_actual_contract_or_novelty_findings():
    # The two budget stories still need literal action/future proof. The virus
    # report explicitly labelled historical_context by its model stays rejected.
    expected = {
        "chomali-destaca-alza-de-47-en-presupuesto-de-salud-y-apunta-como-prioridad-reducir-listas-de-espera-oncologia-y-aps": "pulso_editorial_future_copy_not_grounded",
        "presupuesto-2027-ministra-chomali-destaca-aumento-de-recursos-de-47-en-salud": "pulso_editorial_action_not_grounded",
        "virus-respiratorios-positividad-asciende-al-579-la-mas-alta-en-los-ultimos-tres-anos": "pulso_editorial_repetition_or_context",
    }
    for row in SCOPE:
        slug = row["url"].split("/")[-2]
        if slug in expected:
            assert validate_pulso_editorial_proof(row["ai"], row["body"])["reason"] == expected[slug]


@pytest.mark.parametrize("scope", [
    "El programa ofrece atención médica a animales y mascotas de la región.",
    "El programa ofrece atención de los pacientes animales en la región.",
    "El programa ofrece procedimientos clínicos veterinarios en la región.",
    "El programa ofrece exámenes de diagnóstico veterinarios en la región.",
])
def test_new_clinical_terms_do_not_support_explicit_animal_care(scope):
    row = next(r for r in SCOPE if "agencia-de-ciberseguridad" in r["url"])
    ai = deepcopy(row["ai"])
    ai["pulso_editorial_proof"]["human_health_scope_quote"] = scope
    verdict = validate_pulso_editorial_proof(ai, row["body"] + " " + scope)
    assert verdict["decision"] == "deferred"
    assert verdict["reason"] == "pulso_editorial_human_scope_conflicts_with_non_human_quote"


def test_scope_fix_does_not_waive_fabricated_or_joined_quote():
    row = next(r for r in SCOPE if "agencia-de-ciberseguridad" in r["url"])
    ai = deepcopy(row["ai"])
    ai["pulso_editorial_proof"]["human_health_scope_quote"] += " ... ya todos los pacientes fueron atendidos"
    assert validate_pulso_editorial_proof(ai, row["body"])["reason"] == "pulso_editorial_scope_quote_not_in_input"
