"""Captured primary quotes cannot be mislabeled as direct human care."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_editorial_proof import human_health_scope_anchor, literal_quote_matches, validate_pulso_editorial_proof

RAW = gzip.decompress((Path(__file__).parent / "fixtures/pulso_real_primary_scope_counterexamples.json.gz").read_bytes())
assert hashlib.sha256(RAW).hexdigest() == "a789c94bb02c4106a24aa2c70cfd9e366513eadeac587ee2d6116525961a2baa"
CAPTURE = json.loads(RAW)


@pytest.mark.parametrize("case", CAPTURE["rows"], ids=lambda row: row["case"])
def test_real_animal_or_property_only_quote_does_not_prove_human_health(case):
    assert hashlib.sha256(case["body"].encode()).hexdigest() == case["body_sha256"]
    proof = case["analysis"]["pulso_editorial_proof"]
    assert literal_quote_matches(proof["human_health_scope_quote"], case["body"])
    verdict = validate_pulso_editorial_proof(case["analysis"], case["body"])
    assert verdict["decision"] == "deferred"
    assert verdict["reason"] in {"pulso_editorial_human_scope_conflicts_with_non_human_quote", "pulso_editorial_scope_not_grounded"}
    assert verdict["publication_approved"] is False
    assert CAPTURE["assessments_are_explicit_synthetic_adversarial_cases"] is True


def test_residence_quote_with_explicit_medical_care_remains_eligible_for_analysis():
    assert human_health_scope_anchor("Las residencias de adultos mayores prestan atención médica a los pacientes.")
    assert not human_health_scope_anchor("El negocio de senior housing crece con el envejecimiento de la población.")
