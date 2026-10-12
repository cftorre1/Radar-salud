"""Replay all five actual paid outcomes; technical lineage never implies acceptance."""
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from radar_salud.pulso_source import extract_article

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'data/audits/pulso_followup5_actual_technical_evidence_2026_10_11.json'


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(value).hexdigest()


def frozen(ref, path):
    return subprocess.check_output(['git', 'show', ref + ':' + path], cwd=ROOT)


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def test_all5_real_models_originals_receipts_and_exact_two_paid_events():
    audit = json.loads(AUDIT.read_bytes())
    producer, launch = audit['producer_state_commit'], audit['launch_sha']
    queue = json.loads(frozen(producer, 'data/state/pending_queue.json'))
    before = json.loads(frozen(launch, 'data/state/pending_queue.json'))
    execution = json.loads(frozen(producer, 'data/audits/pulso_runtime_2026_10_11.json'))['last_core_execution']
    telemetry = [json.loads(line) for line in frozen(producer, 'data/ai_usage/responses.jsonl').splitlines() if line]
    window = {e['response_id']: e for e in telemetry
              if timestamp(execution['started_at']) <= timestamp(e['at']) <= timestamp(execution['finished_at'])}
    assert len(window) == 2
    assert all(e['kind'] == 'fast' and e['success'] is True for e in window.values())
    assert list(window.values()) == audit['actual_new_model_events']
    assert execution['code_sha'] == launch
    assert execution['runtime_fingerprint']['sha256'] == audit['expected_runtime_fingerprint']
    assert execution['budget_before']['month']['fast']['attempted'] == 514
    assert execution['budget_after']['month']['fast']['attempted'] == 516
    assert execution['budget_before']['month']['deep'] == execution['budget_after']['month']['deep']
    guard_path = 'src/radar_salud/pulso_editorial_proof.py'
    guard_bytes = frozen(launch, guard_path)
    assert digest(guard_bytes) == audit['actual_guard_sha256'] == execution['runtime_fingerprint']['files'][guard_path]
    guard = {'__name__': 'radar_salud._audit_actual_followup5_guard', '__file__': str(ROOT / guard_path)}
    exec(compile(guard_bytes, guard['__file__'], 'exec'), guard)
    assert len(audit['rows']) == 5
    assert Counter(r['disposition'] for r in audit['rows']) == {'reuse_code_fn': 3, 'assess_contract_or_semantic_defect': 2}
    assert Counter(r['status'] for r in audit['rows']) == {'published': 3, 'retry': 2}
    for row in audit['rows']:
        entry = queue[row['queue_fingerprint']]
        meta = entry['raw']['metadata']
        oldmeta = before[row['queue_fingerprint']]['raw']['metadata']
        model = meta['analysis_model_output']
        assert entry['status'] == row['status'] and entry['reason'] == row['reason']
        assert entry['attempts'] == row['attempts'] == row['previous_attempts'] + 1 == 5
        assert model == row['full_actual_model'] and digest(model) == row['model_output_sha256']
        assert model['_pulso_analysis_meta']['response_id'] == row['response_id']
        assert meta['page_text'] == row['full_primary_body'] == oldmeta['page_text']
        assert entry['raw']['event_date'] == row['publication_date']
        assert entry['raw']['metadata']['market_role'] == 'media'
        assert entry['raw']['source_type'] == 'press_high_trust'
        validation = guard['validate_pulso_editorial_proof'](model, meta['page_text'])
        validation.update(primary_article_body_sha256=meta['analysis_base_article_body_sha256'],
                          request_input_sha256=meta['analysis_request_input_sha256'],
                          model_response=model['_pulso_analysis_meta'])
        assert validation == meta['pulso_editorial_proof_validation'] == row['full_actual_validation']
        revisions = [r for r in meta['evidence_revisions'] if r.get('reason') == 'verified_followup_paid_guard_revalidation_admission']
        original = json.loads(json.dumps(before[row['queue_fingerprint']]['raw']))
        original['metadata'].pop('evidence_revisions')
        assert len(revisions) == 1 and revisions[0]['previous_processing_raw'] == original
        assert meta['evidence_revisions'][:-1] == oldmeta['evidence_revisions']
        primary = row['original_html']
        compressed = frozen(producer, primary['gzip_file'])
        payload = gzip.decompress(compressed)
        assert digest(compressed) == primary['gzip_sha256']
        assert digest(payload) == primary['raw_sha256']
        manifest_bytes = frozen(producer, primary['fixture_manifest'])
        assert digest(manifest_bytes) == primary['fixture_manifest_sha256']
        record = next(r for r in json.loads(manifest_bytes)['requests']
                      if r.get('url') == row['url'] and r.get('sha256') == primary['raw_sha256'])
        html = payload.decode(record.get('charset') or 'utf-8', errors='replace')
        assert digest(html.encode()) == row['html_sha256']
        _, body, evidence = extract_article(html, row['url'])
        assert body == row['full_primary_body'] and evidence['publication_date'] == row['publication_date']
        assert evidence['canonical_url'] == row['url']
        receipt = row['full_validator_receipt']
        assert receipt['validator_guard_sha256'] == audit['actual_guard_sha256']
        assert receipt['new_validation'] == validation
        if row['disposition'] == 'reuse_code_fn':
            assert model == oldmeta['analysis_model_output']
            assert row['response_id'] == row['original_response_id'] and row['response_id'] not in window
            assert meta['followup_paid_guard_revalidation_receipt'] == receipt
            at = receipt['revalidated_at']
        else:
            assert row['response_id'] != row['original_response_id'] and row['response_id'] in window
            assert meta['followup_paid_new_fast_attempt_receipts'] == [receipt]
            for key in ['current_paid_new_fast_attempt_receipts', 'paid_guard_new_fast_attempt_receipts']:
                assert meta[key][:-1] == oldmeta[key]
                assert meta[key][-1]['full_model_output'] == model
            assert validation['decision'] == 'deferred'
            at = receipt['assessed_at']
        assert timestamp(execution['started_at']) <= timestamp(at) <= timestamp(execution['finished_at'])


def test_launch_terminal108_native5293_897_and_failed_acceptance_remain_honest():
    audit = json.loads(AUDIT.read_bytes())
    producer, launch = audit['producer_state_commit'], audit['launch_sha']
    before = json.loads(frozen(launch, 'data/state/pending_queue.json'))
    after = json.loads(frozen(producer, 'data/state/pending_queue.json'))
    cohort = set(json.loads(frozen(launch, 'data/audits/pulso_material_recovery_cohort_2026_10_11.json'))['urls'])
    terminals = {k: v for k, v in before.items() if v.get('source') == 'pulso_latercera'
                 and v['raw']['url'] in cohort and v['status'] in {'published', 'rejected'}}
    assert len(terminals) == 108 and all(after[k] == v for k, v in terminals.items())
    assert {k: digest(v) for k, v in terminals.items()} == audit['terminal108_entry_sha256']
    natives = [{k: v for k, v in q.items() if v.get('source') != 'pulso_latercera'} for q in [before, after]]
    assert natives[0] == natives[1] and len(natives[1]) == 5293
    history = [json.loads(frozen(ref, 'data/history/superintendencia_signals.json'))['signals'] for ref in [launch, producer]]
    native_history = [[r for r in rows if r.get('source_name') != 'Pulso / La Tercera'] for rows in history]
    assert native_history[0] == native_history[1] and len(native_history[1]) == 897
    selected = [r for r in after.values() if r.get('source') == 'pulso_latercera' and r['raw']['url'] in cohort]
    assert Counter(r['status'] for r in selected) == audit['selected113_outcomes'] == {'published': 63, 'rejected': 48, 'retry': 2}
    health = json.loads(frozen(producer, 'data/source_health.json'))['sources']['pulso_latercera']
    feed = json.loads(frozen(producer, 'web/data/radar_today.json'))['signals']
    assert health['published_total'] == audit['effective_published_count'] == audit['source_feed_count'] == 68
    assert len([r for r in feed if r.get('source_name') == 'Pulso / La Tercera']) == 68
    assert health['last_signal_at'] == '2026-10-10' and health['latest_original_at'] == '2026-10-11'
    for path, expected in audit['producer_input_files'].items():
        assert digest(frozen(producer, path)) == expected
    qa = json.loads(frozen(producer, 'data/audits/pulso_directed_processing_qa_2026_10_11.json'))
    assert qa['findings'] == audit['qa_findings'] and len(qa['findings']) == 9
    assert qa['discovery_qa'] == audit['discovery_qa'] == 'PASS'
    assert qa['processing_qa'] == audit['processing_qa'] == 'FAIL'
    assert audit['source_acceptance'] == 'NOT_ACCEPTED_ACTUAL_PROCESSING_QA_FAIL'
    assert audit['technical_lineage_findings'] == []
    assert all(r['bookkeeping_unchanged'] for r in audit['unselected_pulso_refresh_details'])
