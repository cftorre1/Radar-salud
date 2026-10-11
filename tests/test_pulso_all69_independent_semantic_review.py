"""Durable complete review binds every actual failed answer, never a sample."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'data/audits/pulso_focus_all69_independent_semantic_review_2026_10_11.json'
FIXTURE = ROOT / 'tests/fixtures/pulso_focus_all69_actual_models.json.gz'
FIXTURE_SHA = 'de2d7642695b2cd2f2875d985ea340919efdec7542b8f1413ff8cb17e80c2fb7'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def test_all69_independent_reviews_bind_frozen_complete_inputs_and_models():
    packed = FIXTURE.read_bytes()
    original = gzip.decompress(packed)
    assert digest(original) == FIXTURE_SHA
    captures = {row['url']: row for row in json.loads(original)['rows']}
    audit = json.loads(AUDIT.read_bytes())
    assert audit['producer_run_id'] == 38149773071
    assert audit['original_execution_code_sha'] == '81b844a654533891ad0923a40dfedfda03c17fa3'
    assert audit['input_fixture'] == dict(path=str(FIXTURE.relative_to(ROOT)), gzip_sha256=digest(packed), uncompressed_sha256=FIXTURE_SHA)
    assert len(audit['rows']) == len(captures) == len({row['url'] for row in audit['rows']}) == 69
    assert {row['url'] for row in audit['rows']} == set(captures)
    assert len({row['response_id'] for row in audit['rows']}) == 69
    for row in audit['rows']:
        original = captures[row['url']]
        assert row['primary_body_sha256'] == original['body_sha256'] == digest(original['body'].encode())
        assert row['primary_body_characters'] == len(original['body'])
        assert row['source_html_sha256'] == original['source_html_sha256']
        assert row['model_output_sha256'] == canonical(original['ai'])
        assert row['response_id'] == original['ai']['_pulso_analysis_meta']['response_id']
        assert row['request_input_sha256'] == original['ai']['_pulso_analysis_meta']['request_input_sha256']
        assert row['publication_date'] == original['publication_date']
        assert row['first_reason'] == original['reason'] and row['relevance_score'] == original['score']
        assert row['primary_read_complete'] is True and row['model_read_complete'] is True
        assert row['publication_approved'] is False
        review = row['semantic_review']
        if 'source_verbatim_citations' in review:
            for quote in review['source_verbatim_citations']:
                assert ' '.join(quote['text'].split()) in ' '.join(original['body'].split())
            # The original child snapshot used spaced JSON serialization.
            assert review['model_output_sha256'] == digest(json.dumps(original['ai'], ensure_ascii=False, sort_keys=True).encode())
    assert audit['original_focus_findings'] == dict(qa_rows=129, unique_failed_articles=69,
        selected_processing_proof_failures=69, important_control_terminal_gaps=60, duplicate_identical_url_and_code_rows=0)
    assert audit['editorial_policy']['materiality_threshold'] == 72
    assert audit['editorial_policy']['old_model_outputs_approved'] is False
    assert audit['editorial_policy']['new_paid_assessment_required'] is True
    assert audit['runtime_state_mutated'] is False and audit['no_ai_calls'] is True
    assert audit['verdict'].startswith('NOT_ACCEPTED_')
