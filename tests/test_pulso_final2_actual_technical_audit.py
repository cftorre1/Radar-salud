"""Immutable FINAL2 runtime evidence; no Source, queue, publisher or AI mutation."""
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from radar_salud.pulso_source import extract_article

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'data/audits/pulso_final2_actual_technical_evidence_2026_10_11.json'


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()


def frozen(ref, path):
    return subprocess.check_output(['git', 'show', ref + ':' + path], cwd=ROOT)


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def test_two_real_final_receipts_preserve_paid_models_and_emit_without_any_new_ai():
    audit = json.loads(AUDIT.read_bytes())
    producer, launch = audit['producer_state_commit'], audit['launch_sha']
    queue = json.loads(frozen(producer, 'data/state/pending_queue.json'))
    before = json.loads(frozen(launch, 'data/state/pending_queue.json'))
    execution = json.loads(frozen(producer, 'data/audits/pulso_runtime_2026_10_11.json'))['last_core_execution']
    assert execution['code_sha'] == launch
    assert execution['runtime_fingerprint']['sha256'] == audit['actual_runtime_fingerprint_sha256']
    assert execution['processing_attempts_increased'] == 2
    assert execution['budget_before'] == execution['budget_after']
    assert execution['budget_after']['month']['fast']['attempted'] == 516
    assert execution['budget_after']['month']['deep']['attempted'] == 14
    events = [json.loads(line) for line in frozen(producer, 'data/ai_usage/responses.jsonl').splitlines() if line]
    assert not [event for event in events if timestamp(execution['started_at']) <= timestamp(event['at']) <= timestamp(execution['finished_at'])]
    assert len(audit['rows']) == 2
    guard_path = 'src/radar_salud/pulso_editorial_proof.py'
    guard_bytes = frozen(launch, guard_path)
    assert digest(guard_bytes) == audit['actual_guard_sha256'] == execution['runtime_fingerprint']['files'][guard_path]
    guard = {'__name__': 'radar_salud._immutable_actual_final2_guard', '__file__': str(ROOT / guard_path)}
    exec(compile(guard_bytes, guard['__file__'], 'exec'), guard)
    for row in audit['rows']:
        key = row['queue_fingerprint']
        entry, original = queue[key], before[key]
        meta, old = entry['raw']['metadata'], original['raw']['metadata']
        assert entry['status'] == 'published' and entry['attempts'] == original['attempts'] + 1 == 6
        assert meta['analysis_model_output'] == old['analysis_model_output'] == row['full_unchanged_paid_model']
        assert meta['page_text'] == old['page_text'] == row['full_original_primary_body']
        assert row['response_id'] == meta['analysis_model_output']['_pulso_analysis_meta']['response_id']
        validation = guard['validate_pulso_editorial_proof'](meta['analysis_model_output'], meta['page_text'])
        validation.update(primary_article_body_sha256=meta['analysis_base_article_body_sha256'],
                          request_input_sha256=meta['analysis_request_input_sha256'],
                          model_response=meta['analysis_model_output']['_pulso_analysis_meta'])
        assert validation == meta['pulso_editorial_proof_validation'] == row['full_actual_validation']
        assert validation['decision'] == 'ready'
        receipt = meta['final_paid_guard_revalidation_receipt']
        assert receipt == row['full_final_validator_receipt']
        assert receipt['producer_state_commit'] == '323b73ef5fb0ec39410024c21d70e6fd99b065e2'
        assert receipt['previous_validation'] == old['pulso_editorial_proof_validation']
        assert receipt['new_validation'] == validation and receipt['new_model_request'] is False
        assert receipt['original_model_output_unchanged'] is True and receipt['publication_approved'] is False
        assert receipt['validator_guard_sha256'] == audit['actual_guard_sha256']
        assert timestamp(execution['started_at']) <= timestamp(receipt['revalidated_at']) <= timestamp(execution['finished_at'])
        assert meta['evidence_revisions'][:-1] == old['evidence_revisions']
        archived = json.loads(json.dumps(original['raw']))
        archived['metadata'].pop('evidence_revisions')
        assert meta['evidence_revisions'][-1]['previous_processing_raw'] == archived
        for field in ['paid_guard_revalidation_admission', 'paid_guard_new_fast_attempt_receipts',
                      'current_paid_guard_revalidation_admission', 'current_paid_new_fast_attempt_receipts',
                      'followup_paid_guard_revalidation_admission', 'followup_paid_new_fast_attempt_receipts']:
            assert meta[field] == old[field]
        signal, emitted = row['full_published_signal'], row['full_serialized_feed_signal']
        assert all(emitted.get(k) == v for k, v in signal.items())
        assert signal['evidence_maturity'] == 'media_reported' and signal['source_type'] == 'press_high_trust'
        assert signal['editorial_relevance'] == row['score'] == meta['analysis_model_output']['relevance_score'] >= 72
        assert signal['what_happened'] == 'Según Pulso / La Tercera, ' + meta['analysis_model_output']['what_happened']
        assert row['serialized_feed_matches_immutable_normal_offline_curator'] is True


def test_all79_original_dates_replay_and111_terminals_native_stocks_and_costs_are_unchanged():
    audit = json.loads(AUDIT.read_bytes())
    producer, launch = audit['producer_state_commit'], audit['launch_sha']
    before = json.loads(frozen(launch, 'data/state/pending_queue.json'))
    after = json.loads(frozen(producer, 'data/state/pending_queue.json'))
    assert len(audit['terminal111_entry_sha256']) == 111
    assert all(before[key] == after[key] and digest(after[key]) == expected
               for key, expected in audit['terminal111_entry_sha256'].items())
    native = [{k:v for k,v in rows.items() if v.get('source') != 'pulso_latercera'} for rows in [before, after]]
    assert native[0] == native[1] and len(native[1]) == 5293
    histories = [json.loads(frozen(ref, 'data/history/superintendencia_signals.json'))['signals'] for ref in [launch, producer]]
    native_history = [[r for r in rows if r.get('source_name') != 'Pulso / La Tercera'] for rows in histories]
    assert native_history[0] == native_history[1] and len(native_history[1]) == 897
    for path, hashes in audit['ai_usage_file_hashes'].items():
        assert frozen(launch, path) == frozen(producer, path)
        assert hashes['before'] == hashes['after'] == digest(frozen(producer, path))
    assert len(audit['control79']) == 79 and sum(row['in_30_day_window'] for row in audit['control79']) == 29
    for row in audit['control79']:
        original = row['original_html']
        compressed = frozen(producer, original['gzip_file'])
        payload = gzip.decompress(compressed)
        assert digest(compressed) == original['gzip_sha256'] and digest(payload) == original['raw_sha256']
        manifest_bytes = frozen(producer, original['fixture_manifest'])
        assert digest(manifest_bytes) == original['fixture_manifest_sha256']
        record = next(r for r in json.loads(manifest_bytes)['requests']
                      if r.get('url') == row['url'] and r.get('sha256') == original['raw_sha256'])
        html = payload.decode(record.get('charset') or 'utf-8', errors='replace')
        _, body, evidence = extract_article(html, row['url'])
        assert evidence['publication_date'] == row['primary_publication_date'] == row['independent_publication_date']
        assert evidence['canonical_url'] == row['url'] and evidence['publication_date_verified'] is True
        assert digest(body.encode()) == row['full_primary_body_sha256']
        assert row['current_core_detected'] is True and row['status'] in {'published', 'rejected'}
    for path, expected in audit['producer_input_files'].items():
        assert digest(frozen(producer, path)) == expected
    for path, expected in audit['runtime_source_impl_file_hashes'].items():
        assert digest(frozen(launch, path)) == expected
    assert audit['actual_control_recall']['30']['recall'] == audit['actual_control_recall']['90']['recall'] == 1.0
    assert audit['selected113_outcomes'] == {'published': 65, 'rejected': 48}
    health = json.loads(frozen(producer, 'data/source_health.json'))['sources']['pulso_latercera']
    assert health['published_total'] == audit['effective_published_count'] == audit['source_feed_count'] == 70
    assert health['last_signal_at'] == '2026-10-10' and health['latest_original_at'] == '2026-10-11'
    assert audit['source_feed_duplicate_identities'] is False
    qa = json.loads(frozen(producer, 'data/audits/pulso_directed_processing_qa_2026_10_11.json'))
    assert qa['findings'] == audit['qa_findings'] and len(qa['findings']) == 24
    assert qa['verdict'] == audit['qa_verdict'] == 'FAIL'
    assert audit['acceptance'] == 'NOT_ACCEPTED_ACTUAL_QA_FAIL_PRESERVED'
    assert audit['technical_lineage_findings'] == []
