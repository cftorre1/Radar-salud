"""Both genuine paid holds retain complete evidence and remain unpublished."""
from pathlib import Path
import gzip
import hashlib
import json

from radar_salud.pulso_editorial_proof import literal_quote_matches
from radar_salud.pulso_editorial_review import canonical_sha

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'data/audits/pulso_actual323_two_pending_complete_guard_diagnosis_2026_10_11.json'


def test_both_genuine_models_and_all_eight_quotes_are_preserved_with_actual_pending_status():
    audit = json.loads(PATH.read_text())
    raw = (ROOT / audit['actual_paid_fixture']['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == audit['actual_paid_fixture']['sha256']
    fixture = json.loads(gzip.decompress(raw))
    assert fixture['producer_commit'] == audit['producer_commit'] == '323b73ef5fb0ec39410024c21d70e6fd99b065e2'
    assert fixture['producer_code_sha'] == audit['producer_code_sha'] == 'c2db17141fd55cbacbcda5b53805341aa4dfa86f'
    assert {row['score'] for row in audit['rows']} == {80, 78}
    assert audit['required_media_gate_threshold'] == 72
    assert len(audit['rows']) == len(fixture['rows']) == 2
    for row, original in zip(audit['rows'], fixture['rows']):
        assert row['original_full_primary_body'] == original['body']
        assert row['original_full_model_output'] == original['actual_ai']
        assert canonical_sha(row['original_full_model_output']) == row['model_sha256']
        assert hashlib.sha256(row['original_full_primary_body'].encode()).hexdigest() == row['body_sha256']
        assert canonical_sha(row['immutable_actual_model_primary_pin']) == row['immutable_actual_model_primary_pin_sha256']
        assert row['actual_status'] == 'retry' and row['publication_approved'] is False
        assert row['actual_guard_replay_matches_producer'] is True
        assert len(row['six_proof_quote_checks']) == 6 and len(row['two_future_claim_checks']) == 2
        for quote in row['six_proof_quote_checks']:
            assert literal_quote_matches(quote['quote'], original['body'],
                8 if quote['field'] == 'actor_quote' else 12 if quote['field'] == 'event_status_quote' else 20)
        for claim in row['two_future_claim_checks']:
            assert claim['whole_field_exact'] and claim['source_quote_literal']
            assert literal_quote_matches(claim['source_quote'], original['body'])
            assert not claim['unqualified_achieved_copy'] and not claim['unsupported_clinical_completion']


def test_mama_period_fix_and_hanta_prior_alert_comparison_are_independent_of_lexical_qualification():
    audit = json.loads(PATH.read_text())
    mama, hanta = audit['rows']
    assert mama['row'] == 1 and hanta['row'] == 4
    fields = {v['field']: v['future_copy_qualified'] for v in mama['two_future_claim_checks']}
    assert fields == dict(what_happened=False, why_it_matters=True)
    assert 'Hasta el 5 de octubre' in mama['original_full_model_output']['what_happened']
    assert 'no deben extenderse al período enero-julio' in mama['original_full_model_output']['why_it_matters']
    fields = {v['field']: v['future_copy_qualified'] for v in hanta['two_future_claim_checks']}
    assert fields == dict(what_happened=True, why_it_matters=False)
    assert hanta['secondary_failure_reproduction']['next_guard_reason'] == 'pulso_editorial_future_copy_not_grounded'
    comparator = hanta['comparison_with_published_aug8']
    assert comparator['publication_date'] == '2026-08-08'
    assert hashlib.sha256(comparator['full_original_primary_body'].encode()).hexdigest() == comparator['body_sha256']
    assert canonical_sha(comparator['full_actual_effective_signal']) == comparator['signal_sha256']
    assert comparator['prior_alert_literal_quote'] in comparator['full_original_primary_body']
    assert '39%' not in comparator['full_original_primary_body']
    assert audit['publication_approved'] is False and audit['AI_calls'] == 0 and audit['state_mutated'] is False


def test_hanta_dipres_second_peer_matches_frozen_writer_and_both_pending_findings():
    path = ROOT / 'data/audits/pulso_actual323_hanta_dipres_independent_second_peer_2026_10_11.json'
    peer = json.loads(path.read_text())
    for field in ('first_reader', 'publication_template', 'pending_diagnosis'):
        ref = peer[field]
        assert hashlib.sha256((ROOT / ref['path']).read_bytes()).hexdigest() == ref['sha256']
    publication, pending = peer['rows']
    assert publication['actual_status'] == 'published' and publication['decision'] == 'correct'
    assert publication['actual_score'] == 84
    assert pending['actual_status'] == 'retry' and pending['actual_score'] == 78
    assert pending['publication_approved'] is False
    diag = json.loads(PATH.read_text())
    assert pending['immutable_actual_model_primary_pin_sha256'] == next(r for r in diag['rows'] if r['row'] == 4)['immutable_actual_model_primary_pin_sha256']
    template = json.loads((ROOT / peer['publication_template']['path']).read_text())
    assert publication['proposed_what_happened'] == template['records'][0]['proposed']['what_happened']
    assert publication['proposed_why_it_matters'] == template['records'][0]['proposed']['why_it_matters']
    assert peer['pending_publication_approved'] is False and peer['AI_calls'] == 0
