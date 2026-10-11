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
        'reuse_code_fn': 19, 'reuse_below_gate_reject': 6, 'assess_contract_or_semantic_defect': 24}
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
