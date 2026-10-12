"""All rejected original bodies, rather than a manual sample, constrain recovery."""
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from radar_salud.beta_sources import _material


ROOT = Path(__file__).parents[1]
AUDIT = json.loads((ROOT / 'data/audits/pulso_expanded_primary_materiality_review_2026_10_11.json').read_text())
NEGATIVES = AUDIT['all_287_initial_negative_full_body_semantic_reviews']
MATRIX = AUDIT['all_1706_original_prefilter_matrix']


@pytest.mark.parametrize('row', NEGATIVES, ids=lambda row: row['url'].split('/')[-2])
def test_all_original_negative_bodies_preserve_independent_expectations_and_scope_disagreements(row):
    assert row['full_body_read'] is True
    assert hashlib.sha256(row['body'].encode()).hexdigest() == row['fullbody_sha256'] == row['metadata_body_sha256']
    assert len(row['body']) == row['body_characters']
    expected = row['engineering_adjudication']['decision'] == 'analysis_eligibility_repaired'
    assert bool(_material('media', row['title'], row['body'])) is expected
    if expected:
        assert row['independent_review_decision'] == 'concrete_false_negative_for_editorial_analysis'
        assert row['date_verified'] is True
        assert row['publication_date'] is not None
    assert row['actual_ai_result'] is None and row['actual_queue_outcome'] is None
    assert row['publication_approved'] is False


def test_expanded_review_is_complete_and_cannot_pass_with_a_small_manual_sample():
    assert len(MATRIX) == len({row['url'] for row in MATRIX}) == 1706
    assert len(NEGATIVES) == len({row['url'] for row in NEGATIVES}) == 287
    assert {row['url'] for row in NEGATIVES} == {
        row['url'] for row in MATRIX if not row['prefilter_allows_analysis_before']}
    assert sum(row['date_verified'] for row in MATRIX) == 1695
    assert sum(row['publication_date'] is not None and '2026-09-11' <= row['publication_date'] <= '2026-10-10'
               for row in MATRIX) == 536
    assert all(row['body_sha256_recomputed'] == row['fullbody_sha256'] == row['metadata_body_sha256']
               for row in MATRIX)
    assert sum(row['prefilter_allows_analysis_before'] for row in MATRIX) == 1419
    assert sum(row['prefilter_allows_analysis_after'] for row in MATRIX) == 1435
    assert sum(row['prefilter_allows_analysis_before'] != row['prefilter_allows_analysis_after']
               for row in MATRIX) == 16
    assert not any(row['prefilter_allows_analysis_before'] and not row['prefilter_allows_analysis_after']
                   for row in MATRIX)
    assert Counter(row['engineering_adjudication']['decision'] for row in NEGATIVES) == {
        'analysis_eligibility_repaired': 16, 'defensible_prefilter_rejection': 250,
        'uncertain_scope_flagged_without_automatic_widening': 17,
        'defensible_prefilter_rejection_with_documented_scope_disagreement': 4}


def test_expanded_review_cannot_adopt_conflicting_dates_or_claim_actual_runtime_publication():
    conflicts = [row for row in MATRIX if not row['date_verified']]
    assert len(conflicts) == 11
    assert all(row['publication_date'] is None and len(row['possible_publication_days']) > 1
               and row['editorial_hold'] == 'publisher_conflicting_publication_dates'
               and row['current_code_potential_analysis_after_source_holds'] is False for row in conflicts)
    assert AUDIT['unchanged_policy']['materiality_threshold'] == 72
    assert AUDIT['unchanged_policy']['media_reported'] is True
    assert AUDIT['unchanged_policy']['publication_quota'] is False
    assert AUDIT['counts']['actual_core_recall_credited_by_this_audit'] == 0
    assert all(row['actual_model_score'] is None and row['actual_runtime_outcome'] is None for row in MATRIX)
    control = ROOT / 'data/audits/pulso_external_control_2026_10_11.json'
    assert hashlib.sha256(control.read_bytes()).hexdigest() == AUDIT['frozen_control']['sha256']
    assert AUDIT['frozen_control']['recall_expected_30'] == 29
    assert AUDIT['frozen_control']['recall_expected_90'] == 79
