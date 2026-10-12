"""Replay the two genuine final responses without editing model or input."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_editorial_proof import (
    future_copy_qualified, human_health_scope_anchor, literal_quote_matches,
    validate_pulso_editorial_proof,
)

FIXTURE = Path(__file__).parent / 'fixtures/pulso_actual_final2_paid_models.json.gz'
PAYLOAD = FIXTURE.read_bytes()
assert hashlib.sha256(PAYLOAD).hexdigest() == 'b57c36b685996cfb10c9964c70c3d17786597e0a4f7530bc90c3f47efd2f41f8'
DATA = json.loads(gzip.decompress(PAYLOAD))
ROWS = DATA['rows']


@pytest.mark.parametrize('row', ROWS, ids=['mama', 'hanta'])
def test_intact_actual_paid_models_are_grounded_without_semantic_or_publication_approval(row):
    before = deepcopy(row['model'])
    assert hashlib.sha256(row['body'].encode()).hexdigest() == row['body_sha256']
    assert row['model']['_pulso_analysis_meta']['response_id'] == row['response_id']
    result = validate_pulso_editorial_proof(row['model'], row['body'])
    assert result['decision'] == 'ready' and result['prospective_evidence'] is True
    assert result['quote_validation_is_semantic_approval'] is False
    assert result['publication_approved'] is False
    assert row['model'] == before
    assert row['original_status'] == 'retry' and row['original_attempts'] == 5
    assert row['original_validation']['decision'] == 'deferred'
    assert DATA['producer'] == '323b73ef5fb0ec39410024c21d70e6fd99b065e2'
    assert DATA['run_id'] == 38177423421


@pytest.mark.parametrize('row', ROWS, ids=['mama', 'hanta'])
def test_original_eight_quotes_and_whole_field_bindings_remain_literal(row):
    proof = row['model']['pulso_editorial_proof']
    for field in ('human_health_scope_quote', 'actor_quote', 'action_quote',
                  'consequence_quote', 'event_status_quote', 'novelty_quote'):
        minimum = 8 if field == 'actor_quote' else 12 if field == 'event_status_quote' else 20
        assert literal_quote_matches(proof[field], row['body'], minimum)
    for claim in proof['future_claims']:
        assert claim['summary_quote'] == row['model'][claim['summary_field']]
        assert literal_quote_matches(claim['source_quote'], row['body'])


@pytest.mark.parametrize('row', ROWS, ids=['mama', 'hanta'])
@pytest.mark.parametrize('field', ['what_happened', 'why_it_matters'])
@pytest.mark.parametrize('unsupported', [
    ' Luego ya ejecutó la ampliación.',
    ' El hospital ya fue inaugurado.',
    ' La clínica ya dispone de capacidad clínica instalada.',
])
def test_dated_intention_or_denial_cannot_hide_another_completed_capacity_assertion(row, field, unsupported):
    model = deepcopy(row['model'])
    model[field] += unsupported
    next(c for c in model['pulso_editorial_proof']['future_claims']
         if c['summary_field'] == field)['summary_quote'] = model[field]
    result = validate_pulso_editorial_proof(model, row['body'])
    assert result['decision'] == 'deferred'
    assert result['reason'] == 'pulso_editorial_future_copy_not_grounded'


def test_municipal_estimate_requires_an_explicit_publication_date():
    estimate = 'El alcalde estimó cerrar el año con más de 10.000 mamografías.'
    assert not future_copy_qualified(estimate)
    assert future_copy_qualified('Según la nota del 5 de octubre de 2026, ' + estimate)


def test_expired_or_unverified_alert_is_a_dated_denial_not_a_current_effect_claim():
    assert future_copy_qualified('La nota no acredita que la alerta ni sus efectos siguieran vigentes al 11 de octubre de 2026.')
    assert not future_copy_qualified('La alerta y sus efectos siguen vigentes al 11 de octubre de 2026.')
    assert not future_copy_qualified('No acredita que la alerta ni sus efectos siguieran vigentes.')


@pytest.mark.parametrize('quote', [
    'El hanta está presente en ratones de la zona rural.',
    'El hanta afecta el balance del sector y su equipo.',
    'Los síntomas son parecidos a un estado gripal.',
])
def test_generic_hanta_or_symptom_references_do_not_establish_clinical_scope(quote):
    assert not human_health_scope_anchor(quote)


@pytest.mark.parametrize('animal_context', ['pacientes veterinarios', 'hospital clínico veterinario'])
def test_the_symptom_alias_cannot_override_a_veterinary_primary_quote(animal_context):
    row = ROWS[1]
    model = deepcopy(row['model'])
    quote = model['pulso_editorial_proof']['human_health_scope_quote'] + ' ' + animal_context
    model['pulso_editorial_proof']['human_health_scope_quote'] = quote
    # Deliberate adversarial append, never a claimed publisher capture.
    result = validate_pulso_editorial_proof(model, row['body'] + '\n' + quote)
    assert result['decision'] == 'deferred'
    assert result['reason'] == 'pulso_editorial_human_scope_conflicts_with_non_human_quote'


@pytest.mark.parametrize('row', ROWS, ids=['mama', 'hanta'])
def test_repair_never_overrides_gate72(row):
    model = deepcopy(row['model'])
    model['relevance_score'] = 71
    result = validate_pulso_editorial_proof(model, row['body'])
    assert result['decision'] == 'rejected'
    assert result['reason'] == 'editorial_relevance_below_threshold'
