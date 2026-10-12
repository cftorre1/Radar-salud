"""Cross-source grouping is justified by full event facts, not shared labels."""
from pathlib import Path
import hashlib
import json

from radar_salud.pulso_editorial_review import canonical_sha

AUDIT = Path(__file__).resolve().parents[1] / 'data/audits/pulso_cross_source_two_events_independent_second_peer_2026_10_11.json'


def test_both_event_pairs_pin_exact_primary_content_and_effective_signals():
    audit = json.loads(AUDIT.read_text())
    assert len(audit['all_signals']) == 2
    assert set(audit['inputs']) == {'history', 'queue', 'runtime_report', 'telemetry'}
    for row in audit['all_signals']:
        assert canonical_sha(row['immutable_cross_source_event_pair_pin']) == row['immutable_cross_source_event_pair_pin_sha256']
        for role in ('target', 'survivor'):
            source = row[role]
            assert hashlib.sha256(source['full_primary_retained_content'].encode()).hexdigest() == source['retained_content_sha256']
            assert canonical_sha(source['full_effective_signal']) == source['effective_signal_sha256']
            assert source['full_effective_signal']['event_date'] == source['publication_date']
            assert source['full_primary_retained_content_read'] and source['full_effective_signal_read']
            if source['full_retained_model_output'] is not None:
                assert canonical_sha(source['full_retained_model_output']) == source['retained_model_output_sha256']
                assert source['full_retained_model_output']['_pulso_analysis_meta']['response_id'] == source['retained_response_id']
            else:
                assert source['retained_response_id'] is None and source['raw_model_limit']
        assert row['target']['source_slug'] == 'pulso_latercera'
        assert row['target']['full_effective_signal']['evidence_maturity'] == 'media_reported'
        for quote in row['literal_primary_event_comparison_quotes']:
            role = 'target' if quote['source'] == 'Pulso' else 'survivor'
            assert quote['quote'] in row[role]['full_primary_retained_content']
        assert row['decision'] == 'group'
        assert row['native_survivor_mutation_authorized'] is False
    assert audit['state_mutated'] is False and audit['reviewer_AI_calls'] == 0


def test_same_suseso_url_is_bound_to_published_news_not_rejected_fiscalization():
    row = next(r for r in json.loads(AUDIT.read_text())['all_signals']
               if r['survivor']['source_slug'] == 'suseso_news')
    assert row['survivor']['publication_date'] == '2026-09-23'
    assert '23 de septiembre de 2026' in row['survivor']['full_primary_retained_content']
    candidates = row['survivor_same_url_date_queue_candidates']
    assert len(candidates) == 2
    actual = next(v for v in candidates if v['queue_fingerprint'] == row['survivor']['queue_fingerprint'])
    assert actual['status'] == 'published' and actual['source_slug'] == 'suseso_news'
    other = next(v for v in candidates if v is not actual)
    assert other['status'] == 'rejected' and other['source_slug'] == 'suseso_fiscalizacion'
    assert 'no hay HTML original' in row['survivor']['body_capture_limits'][0]


def test_october_tenth_duplicate_is_a_followup_balance_not_initial_eighth_flood():
    audit = json.loads(AUDIT.read_text())
    row = next(r for r in audit['all_signals'] if r['survivor']['source_slug'] == 'diario_financiero')
    assert row['target']['publication_date'] == row['survivor']['publication_date'] == '2026-10-10'
    for role in ('target', 'survivor'):
        body = row[role]['full_primary_retained_content']
        assert 'jueves 8 de octubre' in body and 'todos los pacientes' in body
        assert 'algunas semanas' in body and 'Centro Médico El Alba' in body
    assert audit['summary']['keep_distinct_caja_los_andes_aug14'] is True
