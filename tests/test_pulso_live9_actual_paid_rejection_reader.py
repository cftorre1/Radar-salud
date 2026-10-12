"""Preserve actual low-score decisions and the one genuinely updated primary."""
from pathlib import Path
import hashlib
import json

from radar_salud.pulso_editorial_proof import model_binding_matches, validate_pulso_editorial_proof
from radar_salud.pulso_editorial_review import canonical_sha

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'data/audits/pulso_live9_actual_four_paid_rejections_independent_review_2026_10_11.json'


def test_all_four_actual_paid_rejections_have_exact_model_primary_response_bindings():
    audit = json.loads(PATH.read_text())
    rows = audit['all_four_actual_paid_models']
    assert [(r['live9_index'], r['actual_score']) for r in rows] == [(2, 58), (3, 35), (6, 68), (9, 5)]
    assert len({r['model_response_id'] for r in rows}) == 4
    assert set(audit['inputs']) == {'history', 'queue', 'runtime_report', 'telemetry'}
    for row in rows:
        body, ai = row['original_full_primary_body'], row['original_full_model_output']
        assert hashlib.sha256(body.encode()).hexdigest() == row['body_sha256']
        assert canonical_sha(ai) == row['model_output_sha256']
        assert canonical_sha(row['immutable_actual_model_primary_pin']) == row['immutable_actual_model_primary_pin_sha256']
        assert model_binding_matches(ai, source_name='Pulso / La Tercera',
                                     input_text_sha256=row['body_sha256'],
                                     request_input_sha256=row['request_input_sha256'])
        assert row['genuine_paid_telemetry_event']['response_id'] == row['model_response_id']
        verdict = validate_pulso_editorial_proof(ai, body)
        assert verdict['decision'] == 'rejected' and verdict['reason'] == 'editorial_relevance_below_threshold'
        assert row['actual_editorial_assessment']['threshold'] == row['unchanged_threshold'] == 72
        assert row['actual_status'] == 'rejected' and row['publication_approved'] is False
    assert audit['summary']['actual_rejected'] == 9
    assert audit['summary']['actual_published'] == audit['summary']['actual_pending'] == 0
    assert all(r['history_matches'] == r['feed_matches'] == 0 for r in audit['all_nine_actual_outcomes'])
    assert audit['global_acceptance'].startswith('NOT_ACCEPTED')


def test_vaccination_units_and_unstarted_civil_projects_are_preserved_without_publishing_quota():
    audit = json.loads(PATH.read_text())
    row = next(r for r in audit['all_four_actual_paid_models'] if r['live9_index'] == 6)
    metrics = row['metric_and_period_review']
    assert metrics['persons_saturday_oct10'] == 883
    assert metrics['attendances_accumulated_since_oct9'] == 933
    assert metrics['doses_delivered_approximately'] == 1000
    assert metrics['civil_contract_oct5_million_CLP'] == 776.7
    assert metrics['construction_started_at_flood'] is False
    assert metrics['secondary_project_status'] == 'adjudication'
    assert '933 atenciones acumuladas' in row['original_full_model_output']['what_happened']
    assert 'dosis entregadas' in row['original_full_model_output']['what_happened']
    assert row['actual_score'] == 68 and row['semantic_decision'] == 'retain_rejection'
    assert row['original_full_model_output']['pulso_editorial_proof']['scope_decision'] == 'human_health_specific'


def test_prieto_updated_primary_is_a_real_new_observation_not_an_old_triage_relabel():
    audit = json.loads(PATH.read_text())
    row = next(r for r in audit['all_four_actual_paid_models'] if r['live9_index'] == 9)
    change = row['updated_body_lineage']
    assert change['original_triage_characters'] == 2645 and change['actual_model_input_characters'] == 3449
    assert len(row['original_full_primary_body']) == 3449
    assert change['original_triage_sha256'] != change['actual_primary_sha256']
    assert change['old_triage_replaced_or_rewritten'] is False
    assert change['prior_covid_episode'] == '2022-09' and change['discharge_year'] == 2023
    assert 'septiembre de 2022' in row['original_full_model_output']['what_happened']
    assert row['actual_score'] == 5
    assert row['original_full_model_output']['pulso_editorial_proof']['scope_decision'] == 'incidental_health'
    assert audit['summary']['genuine_new_FAST_calls'] == 4
    assert audit['Source_state_registry_mutations'] == 0
