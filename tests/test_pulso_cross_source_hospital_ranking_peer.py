"""Additional ranking bins preserve detail without creating another evaluation."""
from pathlib import Path
import hashlib
import json

from radar_salud.pulso_editorial_review import canonical_sha

PATH = Path(__file__).resolve().parents[1] / 'data/audits/pulso_cross_source_hospital_ranking_independent_second_peer_2026_10_11.json'


def test_ranking_primary_and_effective_model_pins_are_complete_and_immutable():
    audit = json.loads(PATH.read_text())
    assert len(audit['all_signals']) == 1
    row = audit['all_signals'][0]
    assert row['decision'] == 'group' and row['application_performed'] is False
    assert canonical_sha(row['immutable_cross_source_event_pair_pin']) == row['immutable_cross_source_event_pair_pin_sha256']
    for role in ('target', 'survivor'):
        side = row[role]
        assert hashlib.sha256(side['full_primary_retained_content'].encode()).hexdigest() == side['retained_content_sha256']
        assert canonical_sha(side['full_effective_signal']) == side['effective_signal_sha256']
        assert side['full_primary_retained_content_read'] and side['full_effective_signal_read']
        assert side['full_effective_signal']['evidence_maturity'] == 'media_reported'
        assert '2025' in side['full_primary_retained_content']
        assert '2025' in side['full_effective_signal']['what_happened']
    ai = row['target']['full_retained_model_output']
    assert canonical_sha(ai) == row['target']['retained_model_output_sha256']
    assert ai['_pulso_analysis_meta']['analysis_text_sha256'] == row['target']['retained_content_sha256']
    assert row['target']['previous_editorial_review']['decision'] == 'accept'
    assert row['native_survivor_mutation_authorized'] is False
    assert audit['state_mutated'] is False and audit['reviewer_AI_calls'] == 0


def test_published_minor_bins_are_acknowledged_and_preserved_not_silently_omitted():
    audit = json.loads(PATH.read_text())
    row = audit['all_signals'][0]
    target, survivor = row['target'], row['survivor']
    assert target['publication_date'] == '2026-08-04'
    assert survivor['publication_date'] == '2026-08-05'
    what = target['full_effective_signal']['what_happened']
    assert '21 quedaron bajo 69%' in what and '15 entre 70% y 74,9%' in what
    assert '91,1%' in what
    assert '91,1%' in survivor['full_primary_retained_content']
    assert '26' in survivor['full_effective_signal']['what_happened']
    assert '36' in survivor['full_effective_signal']['what_happened']
    assert audit['summary']['minor_disaggregation_present_in_target_effective_copy'] is True
    assert audit['summary']['original_metrics_preserved_in_grouped_history'] is True
    assert 'no independent strategic action' in row['exact_reason']
    for quote in row['literal_primary_event_comparison_quotes']:
        side = target if quote['source'] == 'Pulso' else survivor
        assert quote['quote'] in side['full_primary_retained_content']
