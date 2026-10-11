"""Narrow clinical/negation fixes use complete, unmodified paid responses."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_editorial_proof import (
    human_health_scope_anchor,
    unqualified_achieved_copy,
    unsupported_clinical_completion,
    validate_pulso_editorial_proof,
)
from radar_salud.pulso_editorial_review import canonical_sha

RAW = gzip.decompress((Path(__file__).parent / "fixtures/pulso_actual_mixed12_paid_models.json.gz").read_bytes())
assert hashlib.sha256(RAW).hexdigest() == "8d1e9e638eac27848a147607b0d0edca77e7ac47beed3d82b1047649a222c185"
ROWS = json.loads(RAW)["rows"]


def request(row):
    return "Fuente: Pulso / La Tercera\nTítulo: " + row["title"] + "\nContenido:\n" + row["body"]


def test_all_twelve_prior_models_remain_immutable_with_frozen_original_routes():
    ready = []
    for row in ROWS:
        before = deepcopy(row["ai"])
        assert hashlib.sha256(row["body"].encode()).hexdigest() == row["body_sha256"]
        assert canonical_sha(row["ai"]) == row["model_sha256"]
        result = validate_pulso_editorial_proof(row["ai"], request(row))
        assert row["ai"] == before
        assert result["publication_approved"] is False
        if result["decision"] == "ready":
            # The later real September-1 mask response demonstrated dated
            # announcement grammar. Repairing that lexical check also affects
            # the older response, without reopening its immutable fresh route.
            assert (row["proposed_route"] == "reuse_code_fn" or
                    row["url"].endswith("/minsal-extiende-hasta-el-30-de-septiembre-el-uso-obligatorio-de-mascarillas-en-urgencias-por-alta-circulacion-de-virus-respiratorios/"))
            ready.append(row["publication_date"])
        else:
            assert result["decision"] == "deferred"
            assert row["proposed_route"] == "assess_contract_or_semantic_defect"
    assert sorted(ready) == ["2026-07-15", "2026-09-01", "2026-09-19"]


@pytest.mark.parametrize("fragment", [
    "la mamografía para mujeres de entre 50 y 69 años es gratuita, no requiere orden médica",
    "Todos los pacientes contactados iniciaron su proceso de atención, que tiene diferentes etapas.",
    "uso obligatorio de mascarilla en los servicios de urgencia, unidades de diálisis y servicios de oncohematología de la red pública y privada de todo el país",
    "antes de la interrupción del embarazo por las tres causales",
])
def test_four_real_clinical_quotes_are_specific_without_generic_scope_expansion(fragment):
    assert any(fragment in row["body"] for row in ROWS)
    assert human_health_scope_anchor(fragment)


@pytest.mark.parametrize("fragment", [
    "hasta la semana pasada se registraban 46 contagios y 18 fallecidos",
    "que no se cierren los pabellones y todas esas cosas que a la gente le asustan",
    "los pacientes veterinarios contactados iniciaron su proceso de atención",
    "el estudio describió un embarazo y tres causas del envejecimiento",
    "Las mujeres de la población envejecen y visitan la exposición",
])
def test_generic_mortality_demographics_and_veterinary_patient_labels_do_not_gain_an_anchor(fragment):
    assert not human_health_scope_anchor(fragment)


@pytest.mark.parametrize("value", [
    "la eventual ampliación quedaba como una medida futura, no como capacidad ya implementada.",
    "esa proyección es futura y local, por lo que no acredita capacidad nacional ya instalada.",
])
def test_exact_local_capacity_denials_are_not_completed_achievements(value):
    assert not unqualified_achieved_copy(value)


@pytest.mark.parametrize("suffix", [
    " El hospital modular ya está instalado y operativo.",
    ", pero el hospital modular ya está instalado y operativo.",
    " y el hospital modular ya está instalado y operativo.",
])
def test_local_denial_cannot_cancel_a_separate_unsupported_positive_installation(suffix):
    row = next(row for row in ROWS if row["proposed_route"] == "reuse_code_fn"
               and row["publication_date"] == "2026-09-19")
    model = deepcopy(row["ai"])
    value = ("Al 19 de septiembre de 2026, la capacidad podría ampliarse; "
             "la nota no acredita capacidad nacional ya instalada" + suffix)
    model["why_it_matters"] = value
    claim = next(claim for claim in model["pulso_editorial_proof"]["future_claims"]
                 if claim["summary_field"] == "why_it_matters")
    claim["summary_quote"] = value
    result = validate_pulso_editorial_proof(model, request(row))
    assert result["decision"] == "deferred"
    assert result["reason"] == "pulso_editorial_future_copy_not_grounded"


def test_adding_an_ellipsis_to_a_reusable_literal_scope_remains_held():
    row = next(row for row in ROWS if row["publication_date"] == "2026-07-15")
    model = deepcopy(row["ai"])
    model["pulso_editorial_proof"]["human_health_scope_quote"] = "interrupción ... del embarazo por las tres causales"
    result = validate_pulso_editorial_proof(model, request(row))
    assert result["decision"] == "deferred" and result["reason"] == "pulso_editorial_scope_quote_not_in_input"


@pytest.mark.parametrize("prefix", ["medicina veterinaria", "Hospital Clínico Veterinario"])
@pytest.mark.parametrize("publication_date", ["2026-07-15", "2026-09-19"])
def test_explicit_veterinary_context_cannot_turn_patient_contacts_into_independent_human_scope(prefix, publication_date):
    # This is a synthetic scope-only counterexample using intact real paid
    # models; it is not a fabricated publisher capture or a paid model output.
    row = next(row for row in ROWS if row["publication_date"] == publication_date)
    model = deepcopy(row["ai"])
    quote = prefix + ": pacientes contactados iniciaron su proceso de atención"
    model["pulso_editorial_proof"]["human_health_scope_quote"] = quote
    result = validate_pulso_editorial_proof(model, request(row) + "\n" + quote)
    assert result["decision"] == "deferred"
    assert result["reason"] == "pulso_editorial_human_scope_conflicts_with_non_human_quote"


def test_explicit_independent_human_procedure_can_coexist_with_a_veterinary_reference():
    quote = "medicina veterinaria; antes de la interrupción del embarazo por las tres causales"
    assert human_health_scope_anchor(quote, allow_patient_contact=False)


@pytest.mark.parametrize("denial", [
    "la nota no acredita capacidad nacional ya instalada",
    "no como capacidad ya implementada",
])
@pytest.mark.parametrize("completed", [
    "El hospital ya fue inaugurado.",
    "El hospital ha sido inaugurado.",
    "El recinto ya fue inaugurado.",
    "La clínica ha sido inaugurada.",
])
def test_local_capacity_denial_does_not_excuse_a_separate_unsupported_inauguration(denial, completed):
    # Only the entire WHY and its exact whole-field claim are mutated. All real
    # primary input, clinical quotes, score and response provenance stay intact.
    row = next(row for row in ROWS if row["publication_date"] == "2026-09-19")
    model = deepcopy(row["ai"])
    value = "Al 19 de septiembre de 2026, la capacidad podría ampliarse; " + denial + ". " + completed
    model["why_it_matters"] = value
    claim = next(claim for claim in model["pulso_editorial_proof"]["future_claims"]
                 if claim["summary_field"] == "why_it_matters")
    claim["summary_quote"] = value
    result = validate_pulso_editorial_proof(model, request(row))
    assert result["decision"] == "deferred"
    assert result["reason"] == "pulso_editorial_future_copy_not_grounded"
    assert result["publication_approved"] is False


@pytest.mark.parametrize("statement", [
    "El hospital ya fue inaugurado",
    "El hospital ha sido inaugurado",
    "El recinto fue inaugurado",
    "La clínica ha sido inaugurada",
])
def test_completed_inauguration_requires_positive_same_input_evidence(statement):
    # Explicitly synthetic boundary assertions, not a publisher capture. The
    # captured SAR inauguration/mixed projection remains exercised separately.
    assert not unsupported_clinical_completion(statement, statement + ". Su ampliación podría continuar.")
    assert unsupported_clinical_completion(statement, "No " + statement.lower() + ". Su ampliación podría continuar.")
    assert unsupported_clinical_completion(statement, "Se planifica la apertura; podría iniciarse en 2027.")
