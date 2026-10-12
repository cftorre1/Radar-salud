"""ALL49 recovery instructions stay bound to actual paid originals, not samples."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).parents[1]
PATH = ROOT / 'data/audits/pulso_v5_paid_guard_revalidation_manifest_2026_10_11.json'
PRODUCER = '981b0ff25c226d47785b77944aa53c459053aa21'

def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()

def test_all_49_routes_preserve_actual_model_primary_and_bookkeeping_pins():
    audit = json.loads(PATH.read_bytes())
    assert audit['producer_state_commit'] == PRODUCER
    assert audit['producer_core_checkout'] == '03bf998a4bb5840c84da6473666e932fbc5cedd9'
    queue = json.loads(subprocess.check_output(['git', 'show', PRODUCER + ':data/state/pending_queue.json'], cwd=ROOT))
    selected = {key: row for key, row in queue.items() if row.get('source') == 'pulso_latercera'
                and row.get('status') == 'retry' and row.get('raw', {}).get('metadata', {}).get(
                    'analysis_model_output', {}).get('_pulso_analysis_meta', {}).get('schema_version') == 'pulso_editorial_proof_v5'}
    assert len(selected) == audit['total'] == len(audit['rows']) == 49
    assert {row['queue_fingerprint'] for row in audit['rows']} == set(selected)
    assert Counter(row['runtime_route'] for row in audit['rows']) == audit['runtime_route_counts'] == {
        'reuse_code_fn': 18, 'reuse_below_gate_reject': 6, 'assess_contract_or_semantic_defect': 25}
    for row in audit['rows']:
        entry = selected[row['queue_fingerprint']]
        raw = entry['raw']; meta = raw['metadata']; ai = meta['analysis_model_output']; response = ai['_pulso_analysis_meta']
        assert entry['attempts'] == row['original_attempts'] >= 1
        assert raw['url'] == row['url'] and raw['event_date'] == row['original_publication_date']
        assert row['actual_queue_entry_sha256'] == digest(entry)
        assert row['original_raw_sha256'] == digest(raw) and row['original_metadata_sha256'] == digest(meta)
        assert row['original_model_output_sha256'] == digest(ai) and row['original_full_model_output'] == ai
        assert row['original_body_sha256'] == digest(meta['page_text'].encode())
        assert row['original_full_primary_body'] == meta['page_text']
        assert row['original_html_sha256'] == meta['html_sha256']
        assert row['original_validation_sha256'] == digest(meta['pulso_editorial_proof_validation'])
        assert row['original_response_id'] == response['response_id']
        assert row['original_raw_model_output_sha256'] == response['raw_model_output_sha256']
        assert row['original_analysis_input_sha256'] == response['analysis_text_sha256']
        assert row['original_request_input_sha256'] == response['request_input_sha256']
        assert row['actual_score'] == ai['relevance_score'] and row['editorial_gate'] == 72
        assert row['publication_approved'] is row['runtime_route_is_publication_approval'] is False
        assert row['new_genuine_model_request_required'] == (row['runtime_route'] == 'assess_contract_or_semantic_defect')
        if row['runtime_route'] == 'reuse_below_gate_reject':
            assert row['actual_score'] < 72
        if row['original_semantic_classification'] in {'specific_editorial_deferred', 'independent_scope_rejection_proposed'}:
            assert row['runtime_route'] == 'assess_contract_or_semantic_defect'


def test_two_full_semantic_readers_partition_all49_and_disclose_missing_exact_originals():
    audit = json.loads(PATH.read_bytes()); references = audit['semantic_references']
    assert len(references) == 2 and sum(ref['scope_count'] for ref in references) == 49
    seen = set()
    for ref in references:
        data = (ROOT / ref['path']).read_bytes()
        assert digest(data) == ref['sha256']
        reader = json.loads(data)
        assert reader['producer_commit'] == PRODUCER
        assert len(reader['rows']) == ref['scope_count']
        for record in reader['rows']:
            assert record['url'] not in seen
            seen.add(record['url'])
        assert reader.get('publication_approved', reader.get('summary', {}).get('publication_approved')) is False
    assert seen == {row['url'] for row in audit['rows']}
    missing = [row['url'] for row in audit['rows'] if row['original_raw_byte_proof']['status'] != 'verified']
    assert missing == audit['missing_exact_raw_originals']
    assert audit['raw_originals_verified_at_review'] + len(missing) == 49
    assert audit['verdict'] == 'NOT_ACCEPTED_RUNTIME_RECOVERY_REQUIRED'


def test_one_novelty_route_revision_binds_real_already_published_source_and_preserves_old_audit():
    audit = json.loads(PATH.read_bytes())
    prior = audit['route_revision']['previous_manifest']
    old_bytes = subprocess.check_output(['git', 'show', prior['commit'] + ':' + prior['path']], cwd=ROOT)
    assert digest(old_bytes) == prior['sha256']
    old = {row['url']: row for row in json.loads(old_bytes)['rows']}
    changed = [row for row in audit['rows'] if row['runtime_route'] != old[row['url']]['runtime_route']]
    assert len(changed) == 1 and changed[0]['cohort_index'] == 16
    row = changed[0]; context = row['reassessment_context']
    assert row['original_semantic_classification'] == old[row['url']]['original_semantic_classification']
    assert row['runtime_route'] == 'assess_contract_or_semantic_defect'
    queue = json.loads(subprocess.check_output(['git', 'show', PRODUCER + ':data/state/pending_queue.json'], cwd=ROOT))
    history = json.loads(subprocess.check_output(['git', 'show', PRODUCER + ':data/history/superintendencia_signals.json'], cwd=ROOT))['signals']
    target = queue[context['target_queue_fingerprint']]
    signal = next(signal for signal in history if signal.get('source_url') == context['target_url'])
    assert target['status'] == 'published' and target['raw']['event_date'] == context['target_publication_date'] == '2026-09-01'
    assert digest(target) == context['target_queue_entry_sha256'] and digest(target['raw']) == context['target_raw_sha256']
    assert digest(signal) == context['target_full_original_signal_sha256']
    assert context['target_full_original_signal'] == signal and signal['evidence_maturity'] == 'media_reported'
    metadata = target['raw']['metadata']
    assert context['target_full_primary_body'] == metadata['page_text']
    assert digest(metadata['page_text'].encode()) == context['target_body_sha256']
    assert context['target_original_model_output'] == metadata['analysis_model_output']
    assert context['target_response_id'] == metadata['analysis_model_output']['_pulso_analysis_meta']['response_id']
    assert all(quote in row['original_full_primary_body'] for quote in context['source_repetition_quotes'])
    assert all(quote in metadata['page_text'] for quote in context['target_repetition_quotes'])
    assert context['publication_approved'] is context['rejection_approved'] is False
