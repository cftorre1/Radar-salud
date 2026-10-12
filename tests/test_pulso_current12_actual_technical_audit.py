"""Replay the complete real twelve against immutable paid producer blobs."""
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from radar_salud.pulso_source import extract_article

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'data/audits/pulso_current12_actual_technical_evidence_2026_10_11.json'


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()


def frozen(ref, path):
    return subprocess.check_output(['git', 'show', ref + ':' + path], cwd=ROOT)


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def test_all12_models_originals_and_receipts_bind_exact_real_producer():
    audit = json.loads(AUDIT.read_bytes())
    producer, code = audit['producer_state_commit'], audit['producer_core_checkout']
    queue = json.loads(frozen(producer, 'data/state/pending_queue.json'))
    old = json.loads(frozen('9083056a7127656e90ff40d4fcd7aef0ac407dbc', 'data/state/pending_queue.json'))
    execution = json.loads(frozen(producer, 'data/audits/pulso_runtime_2026_10_11.json'))['last_core_execution']
    telemetry = [json.loads(line) for line in frozen(producer, 'data/ai_usage/responses.jsonl').splitlines() if line]
    window = {e['response_id']: e for e in telemetry
              if timestamp(execution['started_at']) <= timestamp(e['at']) <= timestamp(execution['finished_at'])}
    assert len(window) == audit['actual_current_window_event_count'] == 10
    assert all(e['kind'] == 'fast' and e['success'] is True for e in window.values())
    assert execution['code_sha'] == code
    assert execution['runtime_fingerprint']['sha256'] == audit['runtime_fingerprint_sha256']
    assert execution['budget_after']['month']['fast']['attempted'] - execution['budget_before']['month']['fast']['attempted'] == 10
    assert execution['budget_after']['month']['deep'] == execution['budget_before']['month']['deep']
    proof_path = 'src/radar_salud/pulso_editorial_proof.py'
    guard_bytes = frozen(code, proof_path)
    assert digest(guard_bytes) == audit['guard_sha256'] == execution['runtime_fingerprint']['files'][proof_path]
    guard = {'__name__':'radar_salud._audit_actual12_guard', '__file__':str(ROOT / proof_path)}
    exec(compile(guard_bytes, guard['__file__'], 'exec'), guard)
    assert len(audit['rows']) == 12
    assert Counter(r['disposition'] for r in audit['rows']) == {'reuse_code_fn':2, 'assess_contract_or_semantic_defect':10}
    assert Counter(r['status'] for r in audit['rows']) == {'published':5, 'rejected':2, 'retry':5}
    for row in audit['rows']:
        entry = queue[row['queue_key']]
        meta = entry['raw']['metadata']
        before = old[row['queue_key']]['raw']
        assert entry['status'] == row['status'] and entry['reason'] == row['reason']
        assert entry['attempts'] == row['attempts'] == row['previous_attempts'] + 1 == 4
        assert meta['analysis_model_output'] == row['full_current_paid_model']
        assert meta['pulso_editorial_proof_validation'] == row['full_current_validation']
        assert digest(meta['analysis_model_output']) == row['model_output_sha256']
        assert meta['page_text'] == row['full_primary_body'] == before['metadata']['page_text']
        assert entry['raw']['event_date'] == row['publication_date'] == before['event_date']
        revision = [r for r in meta['evidence_revisions'] if r.get('reason') == 'verified_current_paid_guard_revalidation_admission']
        original = json.loads(json.dumps(before)); original['metadata'].pop('evidence_revisions')
        assert len(revision) == 1 and revision[0]['previous_processing_raw'] == original
        assert meta['evidence_revisions'][:-1] == before['metadata']['evidence_revisions']
        validation = guard['validate_pulso_editorial_proof'](meta['analysis_model_output'], meta['page_text'])
        validation.update(primary_article_body_sha256=meta['analysis_base_article_body_sha256'],
                          request_input_sha256=meta['analysis_request_input_sha256'],
                          model_response=meta['analysis_model_output']['_pulso_analysis_meta'])
        assert validation == row['full_current_validation']
        primary = row['primary_original']
        compressed = (ROOT / primary['gzip_file']).read_bytes()
        payload = gzip.decompress(compressed)
        assert digest(compressed) == primary['gzip_sha256']
        assert digest(payload) == primary['raw_sha256']
        fixture = json.loads(frozen(producer, primary['fixture_manifest']))
        record = next(r for r in fixture['requests'] if r.get('url') == row['url']
                      and r.get('sha256') == primary['raw_sha256'])
        html = payload.decode(record.get('charset') or 'utf-8', errors='replace')
        assert digest(html.encode()) == row['primary_html_sha256']
        _, body, original = extract_article(html, row['url'])
        assert body == row['full_primary_body'] and original['publication_date'] == row['publication_date']
        assert primary['captured_at'] == record['captured_at']
        if row['disposition'] == 'reuse_code_fn':
            assert row['response_id'] == row['original_response_id'] and row['response_id'] not in window
            assert row['full_current_paid_model'] == before['metadata']['analysis_model_output']
            receipt = meta['current_paid_guard_revalidation_receipt']
            at = receipt['revalidated_at']
            assert receipt['previous_validation'] == before['metadata']['pulso_editorial_proof_validation']
        else:
            assert row['response_id'] in window and row['response_id'] != row['original_response_id']
            receipt = meta['current_paid_new_fast_attempt_receipts'][0]
            assert receipt['full_model_output'] == row['full_current_paid_model']
            at = receipt['assessed_at']
        assert receipt['validator_guard_sha256'] == audit['guard_sha256']
        assert receipt['new_validation'] == row['full_current_validation']
        assert timestamp(execution['started_at']) <= timestamp(at) <= timestamp(execution['finished_at'])


def test_all101_terminal_entries_and_native5293_897_preserved_without_false_acceptance():
    audit = json.loads(AUDIT.read_bytes())
    producer, code = audit['producer_state_commit'], audit['producer_core_checkout']
    before = json.loads(frozen(code, 'data/state/pending_queue.json'))
    after = json.loads(frozen(producer, 'data/state/pending_queue.json'))
    selected = set(json.loads(frozen(code, 'data/audits/pulso_material_recovery_cohort_2026_10_11.json'))['urls'])
    terminal = {k:v for k,v in before.items() if v.get('source') == 'pulso_latercera'
                and v['raw']['url'] in selected and v['status'] in {'published','rejected'}}
    assert len(terminal) == audit['selected101_preexisting_terminal_count'] == 101
    assert all(after[k] == v for k,v in terminal.items())
    native_before = {k:v for k,v in before.items() if v.get('source') != 'pulso_latercera'}
    native_after = {k:v for k,v in after.items() if v.get('source') != 'pulso_latercera'}
    assert native_before == native_after and len(native_after) == audit['other_sources_queue_count'] == 5293
    histories = [json.loads(frozen(ref, 'data/history/superintendencia_signals.json'))['signals'] for ref in (code,producer)]
    natives = [[r for r in history if r.get('source_name') != 'Pulso / La Tercera'] for history in histories]
    assert natives[0] == natives[1] and len(natives[1]) == audit['native_history_count'] == 897
    health = json.loads(frozen(producer, 'data/source_health.json'))['sources']['pulso_latercera']
    assert health['published_total'] == audit['effective_published_history_count'] == audit['feed_source_url_count'] == 68
    assert health['last_signal_at'] == audit['effective_last_signal_at'] == '2026-10-10'
    assert health['latest_original_at'] == '2026-10-11'
    qa = json.loads(frozen(producer, 'data/audits/pulso_directed_processing_qa_2026_10_11.json'))
    assert qa['findings'] == audit['qa_findings'] and len(qa['findings']) == audit['qa_findings_count'] == 22
    assert qa['discovery_qa'] == audit['discovery_qa'] == 'PASS'
    assert qa['processing_qa'] == audit['processing_qa'] == 'FAIL'
    assert audit['acceptance'].startswith('NOT_ACCEPTED_')
