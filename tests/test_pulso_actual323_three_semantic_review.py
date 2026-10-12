"""Observed publications only; the new Mama response remains a held assessment."""
from pathlib import Path
import hashlib
import json

from radar_salud.pulso_editorial_proof import literal_quote_matches
from radar_salud.pulso_editorial_review import canonical_sha, validate_independent_binding, apply_review

ROOT = Path(__file__).resolve().parents[1]
READER = 'data/audits/pulso_actual323_three_primary_semantic_review_2026_10_11.json'
TEMPLATE = 'data/audits/pulso_actual323_ilc_mask_editorial_review_2026_10_11.json'


def documents():
    raw = (ROOT / READER).read_bytes()
    return json.loads(raw), json.loads((ROOT / TEMPLATE).read_text()), hashlib.sha256(raw).hexdigest()


def test_actual_three_reader_keeps_periods_and_exact_response_primary_pins():
    reader, _, _ = documents()
    assert set(reader['inputs']) == {'history', 'queue', 'runtime_report', 'telemetry'}
    assert {x['commit'] for x in reader['inputs'].values()} == {reader['producer_commit']}
    assert len(reader['all_three_actual_assessments']) == 3
    for row in reader['all_three_actual_assessments']:
        body, ai = row['original_full_primary_body'], row['original_full_model_output']
        assert hashlib.sha256(body.encode()).hexdigest() == row['body_sha256']
        assert canonical_sha(ai) == row['original_model_output_sha256']
        assert canonical_sha(row['immutable_actual_model_primary_pin']) == row['immutable_actual_model_primary_pin_sha256']
        assert row['source_primary_flags'] == dict(article_verified=True, article_body_complete=True,
                                                 primary_identity_verified=True, publication_date_verified=True)
        assert all(v['contiguous_in_full_primary'] for v in row['six_proof_quote_checks'])
        assert len(row['two_future_claim_checks']) == 2
        assert all(v['source_quote_contiguous_in_full_primary'] and v['whole_field_equals_actual_model']
                   for v in row['two_future_claim_checks'])
        for quote in row['six_proof_quote_checks']:
            assert literal_quote_matches(quote['quote'], body,
                8 if quote['field'] == 'actor_quote' else 12 if quote['field'] == 'event_status_quote' else 20)
    mama = reader['all_three_actual_assessments'][0]
    assert mama['actual_status'] == 'retry' and mama['publication_approved'] is False
    assert mama['original_full_model_output']['relevance_score'] == 80
    assert 'Hasta el 5 de octubre' in mama['original_full_model_output']['what_happened']
    assert 'no deben extenderse al período enero-julio' in mama['original_full_model_output']['why_it_matters']
    assert {r['url'] for r in reader['all_signals']} == {r['url'] for r in reader['all_three_actual_assessments'] if r['actual_status'] == 'published'}


def test_bound_two_publication_template_does_not_change_paid_copy_scores_or_dates():
    reader, audit, digest = documents()
    validate_independent_binding(audit, reader, independent_sha256=digest)
    assert len(audit['records']) == 2
    ilc = next(r for r in audit['records'] if r['decision'] == 'accept')
    mask = next(r for r in audit['records'] if r['decision'] == 'correct')
    assert '165 mil millones' in ilc['original_signal']['what_happened']
    assert '36.783 millones' in ilc['original_signal']['what_happened']
    assert '4.380 millones' in ilc['original_signal']['what_happened']
    assert mask['proposed']['category'] == 'Regulación & Legal'
    assert mask['proposed']['what_happened'] == mask['original_signal']['what_happened']
    assert mask['proposed']['why_it_matters'] == mask['original_signal']['why_it_matters']
    assert 'no acredita que la medida siguiera vigente al 11 de octubre' in mask['proposed']['what_happened']
    assert mask['original_signal']['editorial_relevance'] == 86
    assert all(r['original_signal']['evidence_maturity'] == 'media_reported' for r in audit['records'])
