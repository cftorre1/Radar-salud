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


def test_internal_added_quote_correction_preserves_original_model_and_below_gate_uncertainty():
    import unicodedata
    from radar_salud.pulso_editorial_proof import validate_pulso_editorial_proof
    original_audit = AUDIT.read_bytes()
    addendum = json.loads((ROOT / 'data/audits/pulso_focus_all69_semantic_addendum_2026_10_11.json').read_bytes())
    assert addendum['prior_review'] == dict(path=str(AUDIT.relative_to(ROOT)), sha256=digest(original_audit))
    assert digest(original_audit) == '4aeb33e490eb7fbed45f767e1c5cf6c3c59c5d91f9d69c6b3f4332869a64c9bf'
    correction, = addendum['records']
    originals = json.loads(gzip.decompress(FIXTURE.read_bytes()))['rows']
    source = next(row for row in originals if row['url'] == correction['url'])
    previous = next(row for row in json.loads(original_audit)['rows'] if row['url'] == correction['url'])
    assert correction['previous_review_record_sha256'] == canonical(previous)
    assert correction['model_output_sha256'] == canonical(source['ai'])
    assert correction['primary_body_sha256'] == digest(source['body'].encode())
    assert correction['score'] == source['score'] == 68
    assert correction['novelty_decision'] == source['ai']['pulso_editorial_proof']['novelty_decision'] == 'uncertain'
    quote = source['ai']['pulso_editorial_proof']['human_health_scope_quote']
    assert correction['original_scope_quote'] == quote
    assert correction['original_scope_quote_sha256'] == digest(quote.encode())
    typography = lambda value: ' '.join(unicodedata.normalize('NFKC', value).translate(str.maketrans({'“':'"', '”':'"'})).split()).casefold()
    assert typography(quote) not in typography(source['body'])
    assert not (quote[0] == quote[-1] and quote[0] in '“”"')
    for cited in correction['source_verbatim_citations']:
        assert cited in source['body']
    verdict = validate_pulso_editorial_proof(source['ai'], source['body'])
    assert verdict['decision'] == 'deferred' and verdict['reason'] == 'pulso_editorial_scope_quote_not_in_input'
    assert correction['approved_model_rewrite'] is False and correction['publication_approved'] is False
    assert addendum['runtime_state_mutated'] is False and addendum['no_ai_calls'] is True
    clarification = addendum['inherited_diagnostic_field_clarification']
    assert clarification['complete_parent_reviews'] + clarification['complete_child_reviews'] == 69
    assert clarification['complete_parent_review_field'] == 'semantic_review.independent_first_trigger_review'
