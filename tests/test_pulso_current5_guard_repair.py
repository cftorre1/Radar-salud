"""Bounded validator repairs replay intact, dated, real paid responses."""
from copy import deepcopy
from pathlib import Path
import gzip
import hashlib
import json

import pytest

from radar_salud.pulso_editorial_proof import (
    future_copy_qualified, human_health_scope_anchor, literal_quote_matches,
    unqualified_achieved_copy, validate_pulso_editorial_proof,
)
from radar_salud.pulso_source import extract_article
from radar_salud.pulso_editorial_review import canonical_sha

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/pulso_actual_current12_remaining5_paid_models.json.gz'
DATA = json.loads(gzip.decompress(FIXTURE.read_bytes()))
ROWS = DATA['rows']


@pytest.mark.parametrize('row', ROWS, ids=[str(r['row']) for r in ROWS])
def test_intact_paid_responses_remove_only_technical_blocks_without_semantic_approval(row):
    before = deepcopy(row['actual_full_model_output'])
    result = validate_pulso_editorial_proof(before, row['original_full_primary_body'])
    assert result['decision'] == 'ready'
    assert result['prospective_evidence'] is True
    assert result['quote_validation_is_semantic_approval'] is False
    assert result['publication_approved'] is False
    assert row['actual_full_model_output'] == before
    assert row['actual_status'] == 'retry'  # fixture is the real producer, never rewritten
    assert row['actual_full_queue_entry']['raw']['metadata']['pulso_editorial_proof_validation']['decision'] == 'deferred'
    if row['row'] in {2, 9}:
        # Mama's period/growth error and Hanta's prior-alert comparison require
        # fresh assessments even though the lexical guard block is repaired.
        assert row['independent_semantic_decision'] == 'assess_contract_or_semantic_defect'
    else:
        assert row['row'] in {5, 6, 11}
        assert row['independent_semantic_decision'] == 'reuse_code_fn'


@pytest.mark.parametrize('row', ROWS, ids=[str(r['row']) for r in ROWS])
def test_every_original_raw_html_reparses_to_the_same_complete_body_and_publication_day(row):
    html = gzip.decompress((ROOT / row['original_primary_raw_fixture_path']).read_bytes())
    assert hashlib.sha256(html).hexdigest() == row['source_pin']['html_sha256']
    _, body, metadata = extract_article(html.decode(), row['url'])
    assert body == row['original_full_primary_body']
    assert metadata['publication_date'] == row['publication_date']
    assert hashlib.sha256(body.encode()).hexdigest() == row['body_sha256']


@pytest.mark.parametrize('row', ROWS, ids=[str(r['row']) for r in ROWS])
def test_source_quotes_and_entire_model_field_bindings_remain_exact(row):
    ai, body = row['actual_full_model_output'], row['original_full_primary_body']
    proof = ai['pulso_editorial_proof']
    for field in ('human_health_scope_quote', 'actor_quote', 'action_quote', 'consequence_quote',
                  'event_status_quote', 'novelty_quote'):
        assert literal_quote_matches(proof[field], body, 8 if field == 'actor_quote' else 12 if field == 'event_status_quote' else 20)
    for claim in proof['future_claims']:
        assert claim['summary_quote'] == ai[claim['summary_field']]
        assert literal_quote_matches(claim['source_quote'], body)


@pytest.mark.parametrize('row', ROWS, ids=[str(r['row']) for r in ROWS])
def test_new_patterns_never_cancel_a_separate_completed_capacity_assertion(row):
    ai = deepcopy(row['actual_full_model_output'])
    ai['why_it_matters'] += ' El hospital ya fue inaugurado.'
    next(c for c in ai['pulso_editorial_proof']['future_claims']
         if c['summary_field'] == 'why_it_matters')['summary_quote'] = ai['why_it_matters']
    result = validate_pulso_editorial_proof(ai, row['original_full_primary_body'])
    assert result['decision'] == 'deferred'
    assert result['reason'] == 'pulso_editorial_future_copy_not_grounded'


@pytest.mark.parametrize('text', [
    'no de inversiones ya ejecutadas',
    'la nota no acredita una reasignación ya ejecutada',
    'el contenido no acredita resultados ya alcanzados',
])
def test_three_actual_local_denials_are_not_positive_achievement_assertions(text):
    assert not unqualified_achieved_copy(text)
    assert unqualified_achieved_copy(text + '. Luego ya ejecutó la ampliación.')
    assert unqualified_achieved_copy(text + ', pero ya implementó la capacidad.')


@pytest.mark.parametrize('text', [
    'La extensión se anunciaba para ese período.',
    'La nota también reportó recomendaciones de revisión focalizada y de refuerzo de incentivos, sin acreditar su implementación.',
    'La extensión territorial y la vigencia hasta julio de 2027 eran condiciones anunciadas en esa fecha.',
])
def test_historical_future_wording_still_requires_explicit_observation_date(text):
    assert not future_copy_qualified(text)
    assert future_copy_qualified('Según la nota del 1 de septiembre de 2026, ' + text)


@pytest.mark.parametrize('quote', [
    'prestaciones financieras en el semestre',
    'La incorporación del Sanatorio Alemán aportó utilidades',
    'La mayor complejidad de sus prestaciones generó utilidades',
    'la incorporación del sanatorio veterinario generó prestaciones',
    'mayor complejidad de sus prestaciones, sumado a la incorporación del Sanatorio Alemán veterinario',
])
def test_bare_accounting_prestaciones_or_sanatorio_does_not_gain_human_scope(quote):
    assert not human_health_scope_anchor(quote)


@pytest.mark.parametrize('prefix', ['medicina veterinaria', 'Hospital Clínico Veterinario'])
def test_new_named_provider_pattern_does_not_override_explicit_veterinary_context(prefix):
    row = next(r for r in ROWS if r['row'] == 5)
    ai = deepcopy(row['actual_full_model_output'])
    quote = prefix + ': ' + ai['pulso_editorial_proof']['human_health_scope_quote']
    ai['pulso_editorial_proof']['human_health_scope_quote'] = quote
    # Deliberately synthetic append, not a claimed publisher capture.
    result = validate_pulso_editorial_proof(ai, row['original_full_primary_body'] + '\n' + quote)
    assert result['decision'] == 'deferred'
    assert result['reason'] == 'pulso_editorial_human_scope_conflicts_with_non_human_quote'


def test_ilc_scope_is_the_complete_literal_specific_clinical_relation():
    row = next(r for r in ROWS if r['row'] == 5)
    quote = row['actual_full_model_output']['pulso_editorial_proof']['human_health_scope_quote']
    assert 'complejidad de sus prestaciones' in quote and 'incorporación del Sanatorio Alemán' in quote
    assert quote in row['original_full_primary_body'] and human_health_scope_anchor(quote)


def test_veterinary_modifier_cannot_relabel_the_named_clinical_provider_as_human():
    row = next(r for r in ROWS if r['row'] == 5)
    ai = deepcopy(row['actual_full_model_output'])
    quote = ai['pulso_editorial_proof']['human_health_scope_quote'].replace(
        'Sanatorio Alemán', 'Sanatorio Alemán veterinario')
    ai['pulso_editorial_proof']['human_health_scope_quote'] = quote
    result = validate_pulso_editorial_proof(ai, row['original_full_primary_body'] + '\n' + quote)
    assert result['decision'] == 'deferred'
    assert result['reason'] == 'pulso_editorial_human_scope_conflicts_with_non_human_quote'
