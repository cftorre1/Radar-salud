"""Independent receipt QA on actual paid originals, temporary queues and spies.

Only the post-processing execution envelope is synthetic. These tests make no
model calls and grant no runtime acceptance to their simulated queue results.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis, pulso_paid_revalidation as paid
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('paid_independent_qa', ROOT / 'scripts/qa_pulso_recovery.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


@pytest.fixture(scope='module')
def actual_origin():
    return qa.paid_revalidation_origin(ROOT)


@pytest.fixture(params=['reuse_code_fn', 'reuse_below_gate_reject'])
def reused_case(request, tmp_path, actual_origin, monkeypatch):
    row = next(row for row in actual_origin['rows'].values() if row['runtime_route'] == request.param)
    original = deepcopy(actual_origin['originals'][row['queue_fingerprint']])
    fresh = deepcopy(original['raw'])
    for field in list(fresh['metadata']):
        if field.startswith('analysis_') or field in ('article_body_complete', 'editorial_assessment',
                'pulso_editorial_proof_validation', 'primary_item_binding', 'evidence_revisions',
                'queue_identity_fingerprint', 'editorial_code_repair_admission', paid.STAMP, paid.RECEIPT):
            fresh['metadata'].pop(field)
    queue = PendingQueue(tmp_path / 'queue.json'); queue.items = {row['queue_fingerprint']: deepcopy(original)}
    now = datetime.now(timezone.utc)
    queue.discover(qa.SOURCE, [RawItem(**fresh)], now=now)
    item = queue.items[row['queue_fingerprint']]
    assert item['raw']['metadata'][paid.STAMP]['disposition'] == request.param
    def forbidden(**kwargs):
        pytest.fail('This real-output receipt fixture cannot call a model')
    monkeypatch.setattr(llm_analysis, 'analyze_news', forbidden)
    raw = RawItem(**deepcopy(item['raw']))
    signal = beta_sources.process_curated_beta_source(raw, {})
    item['raw'] = asdict(raw); item['attempts'] += 1
    item['status'] = 'published' if signal else 'rejected'
    envelope = dict(started_at=(now - timedelta(seconds=1)).isoformat(),
        finished_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        runtime_fingerprint=dict(files={'src/radar_salud/pulso_editorial_proof.py':
            qa.digest((ROOT / 'src/radar_salud/pulso_editorial_proof.py').read_bytes())}))
    return dict(item=item, execution=envelope, origin=actual_origin, telemetry=[])


def inspect(case):
    return qa.verify_paid_guard_revalidation(root=ROOT, **case)


def test_actual_original_response_and_new_guard_receipt_are_distinct_provenance(reused_case):
    result = inspect(reused_case)
    assert result['old_paid_output_reused'] is True
    assert result['original_response_id'] == result['current_response_id']
    assert result['original_producer_preserved'] is True and result['publication_approved'] is False


@pytest.mark.parametrize('attack', ['model', 'body', 'date', 'classification', 'old_validation',
    'guard_hash', 'guard_not_execution', 'receipt_before_run', 'receipt_flag', 'output_receipt_hash',
    'archive', 'attempt_reset', 'producer', 'route', 'revision_duplicate'])
def test_rehashed_or_mutable_claims_cannot_replace_original_paid_and_current_guard_proofs(reused_case, attack):
    value = deepcopy(reused_case); item = value['item']; meta = item['raw']['metadata']; receipt = meta[paid.RECEIPT]
    if attack == 'model': meta['analysis_model_output']['what_happened'] += ' fabricated'
    elif attack == 'body': meta['page_text'] += ' fabricated'
    elif attack == 'date': item['raw']['event_date'] = '2026-10-11'
    elif attack == 'classification': meta['market_role'] = 'provider'
    elif attack == 'old_validation': receipt['previous_validation']['decision'] = 'ready'
    elif attack == 'guard_hash': receipt['validator_guard_sha256'] = '0' * 64
    elif attack == 'guard_not_execution': value['execution']['runtime_fingerprint']['files']['src/radar_salud/pulso_editorial_proof.py'] = '0' * 64
    elif attack == 'receipt_before_run': receipt['revalidated_at'] = '2026-10-10T00:00:00+00:00'
    elif attack == 'receipt_flag': receipt['publication_approved'] = True
    elif attack == 'output_receipt_hash': receipt['new_validation_sha256'] = '0' * 64
    elif attack == 'archive': meta['evidence_revisions'][-1]['previous_processing_raw']['metadata']['analysis_model_output']['why_it_matters'] += ' fabricated'
    elif attack == 'attempt_reset': item['attempts'] = 0
    elif attack == 'producer': meta[paid.STAMP]['producer_state_commit'] = '0' * 40
    elif attack == 'route': meta[paid.STAMP]['disposition'] = 'assess_contract_or_semantic_defect'
    elif attack == 'revision_duplicate': meta['evidence_revisions'].append(deepcopy(meta['evidence_revisions'][-1]))
    with pytest.raises(ValueError):
        inspect(value)


def test_separate_semantic_files_are_pinned_before_any_queue_admission(actual_origin, tmp_path):
    proof_files = qa.paid_revalidation_proof_files(ROOT)
    for path in proof_files:
        target = tmp_path / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes((ROOT / path).read_bytes())
    assert qa.paid_revalidation_proof_files(tmp_path) == proof_files
    reader = next(path for path in proof_files if path != qa.PAID_REVALIDATION_PATH)
    with (tmp_path / reader).open('ab') as stream:
        stream.write(b' ')
    with pytest.raises(ValueError, match='separate_semantic_reader_changed'):
        qa.paid_revalidation_proof_files(tmp_path)


@pytest.mark.parametrize('replacement', ['unchanged_original', 'other_old_paid_response'])
def test_literal_or_semantic_defect_cannot_reuse_any_prior_paid_response_as_new_fast(actual_origin, tmp_path, replacement):
    row = next(row for row in actual_origin['rows'].values() if row['runtime_route'] == 'assess_contract_or_semantic_defect')
    original = deepcopy(actual_origin['originals'][row['queue_fingerprint']])
    fresh = deepcopy(original['raw'])
    for field in list(fresh['metadata']):
        if field.startswith('analysis_') or field in ('article_body_complete', 'editorial_assessment',
                'pulso_editorial_proof_validation', 'primary_item_binding', 'evidence_revisions',
                'queue_identity_fingerprint', 'editorial_code_repair_admission', paid.STAMP, paid.RECEIPT):
            fresh['metadata'].pop(field)
    queue = PendingQueue(tmp_path / 'queue.json'); queue.items = {row['queue_fingerprint']: original}
    now = datetime.now(timezone.utc)
    queue.discover(qa.SOURCE, [RawItem(**fresh)], now=now)
    item = queue.items[row['queue_fingerprint']]; item['attempts'] += 1
    if replacement == 'other_old_paid_response':
        other = next(value for value in actual_origin['successful_response_ids'] if value != row['original_response_id'])
        item['raw']['metadata']['analysis_model_output']['_pulso_analysis_meta']['response_id'] = other
    # All actual old events remain present, but none is a newly paid response in
    # this new synthetic execution envelope. No fabricated events are added.
    telemetry = deepcopy(actual_origin['telemetry'])
    envelope = dict(started_at=now.isoformat(), finished_at=(now + timedelta(seconds=1)).isoformat())
    with pytest.raises(ValueError, match='contract_defect_requires_new_genuine_fast'):
        qa.verify_paid_guard_revalidation(item, ROOT, execution=envelope, telemetry=telemetry, origin=actual_origin)
