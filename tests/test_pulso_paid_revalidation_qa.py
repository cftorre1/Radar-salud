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
from radar_salud.processing import DeferredProcessing

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


@pytest.mark.parametrize('claim', ['receipt', 'revision', 'new_fast_receipt'])
def test_removing_admission_cannot_hide_surviving_paid_provenance_claim(reused_case, claim):
    value = deepcopy(reused_case); meta = value['item']['raw']['metadata']
    del meta[paid.STAMP]
    if claim == 'receipt':
        meta['evidence_revisions'] = []
    elif claim == 'revision':
        del meta[paid.RECEIPT]
    else:
        meta[paid.NEW_FAST_RECEIPTS] = [deepcopy(meta.pop(paid.RECEIPT))]
        meta['evidence_revisions'] = []
    assert qa.has_paid_revalidation_claim(meta)
    with pytest.raises(ValueError, match='admission_or_unique_revision_changed'):
        inspect(value)


def test_rehashed_receipt_cannot_forge_the_execution_bound_guard_verdict(reused_case):
    value = deepcopy(reused_case); meta = value['item']['raw']['metadata']; receipt = meta[paid.RECEIPT]
    validation = meta['pulso_editorial_proof_validation']
    # A forged rejection is also a false decision: it could falsely close an
    # important discovered article instead of leaving a real model judgment.
    validation['decision'] = 'rejected'
    validation['reason'] = 'invented_rejection_of_actual_paid_output'
    if receipt['admission']['disposition'] == 'reuse_below_gate_reject':
        # All gate fields retain their original rejection. Alter only a
        # recorded validator result that receipt rehashing used to authorize.
        validation['prospective_evidence'] = True
        validation['reason'] = 'editorial_relevance_below_threshold'
        receipt['new_validation'] = deepcopy(validation)
        receipt['new_validation_sha256'] = qa.object_digest(validation)
        with pytest.raises(ValueError, match='recorded_verdict_not_actual_guard_result'):
            inspect(value)
        return
    receipt['new_validation'] = deepcopy(validation)
    receipt['new_validation_sha256'] = qa.object_digest(validation)
    with pytest.raises(ValueError, match='recorded_verdict_not_actual_guard_result'):
        inspect(value)


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


def test_new_fast_receipt_cannot_rehash_a_false_ready_result(actual_origin, tmp_path, monkeypatch):
    # An OPEN-section defect that still reaches a new request: a premium piece never gets a
    # full-input request (rights policy, Dirección 28-oct-2026) and a known original66 or
    # final-two candidate defers to its later authority before any request.
    from radar_salud import pulso_final_paid_revalidation as final
    from radar_salud import pulso_followup_paid_revalidation as followup
    from paywall_test_support import is_premium
    from radar_salud.pulso_editorial_proof import validate_pulso_editorial_proof
    def reaches_new_fast(row):
        raw = RawItem(**deepcopy(actual_origin['originals'][row['queue_fingerprint']]['raw']))
        if is_premium(raw) or followup.known_original_candidate(raw) or final.known_original_candidate(raw):
            return False
        # The scenario resends the unchanged answer, so it needs one the current guard still defers.
        return validate_pulso_editorial_proof(raw.metadata['analysis_model_output'],
                                              raw.metadata['page_text'])['decision'] == 'deferred'
    row = next(row for row in actual_origin['rows'].values()
               if row['runtime_route'] == 'assess_contract_or_semantic_defect' and reaches_new_fast(row))
    original = deepcopy(actual_origin['originals'][row['queue_fingerprint']])
    fresh = deepcopy(original['raw'])
    for field in list(fresh['metadata']):
        if field.startswith('analysis_') or field in ('article_body_complete', 'editorial_assessment',
                'pulso_editorial_proof_validation', 'primary_item_binding', 'evidence_revisions',
                'queue_identity_fingerprint', 'editorial_code_repair_admission', paid.STAMP, paid.RECEIPT):
            fresh['metadata'].pop(field)
    queue = PendingQueue(tmp_path / 'queue.json')
    queue.items = {row['queue_fingerprint']: original}
    now = datetime.now(timezone.utc)
    queue.discover(qa.SOURCE, [RawItem(**fresh)], now=now)
    item = queue.items[row['queue_fingerprint']]
    model = deepcopy(original['raw']['metadata']['analysis_model_output'])
    # Synthetic unit-only response/event: the actual model input and answer
    # remain unchanged. This creates no network call or runtime acceptance.
    model['_pulso_analysis_meta']['response_id'] = 'resp_unit_new_attempt_for_verdict_tamper'
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: deepcopy(model))
    raw = RawItem(**deepcopy(item['raw']))
    with pytest.raises(DeferredProcessing):
        beta_sources.process_curated_beta_source(raw, {})
    item['raw'] = asdict(raw); item['attempts'] += 1; item['status'] = 'retry'
    meta = item['raw']['metadata']; latest = meta[paid.NEW_FAST_RECEIPTS][-1]
    assert meta['pulso_editorial_proof_validation']['decision'] == 'deferred'
    event_time = datetime.now(timezone.utc)
    envelope = dict(started_at=(now - timedelta(seconds=1)).isoformat(),
        finished_at=(event_time + timedelta(seconds=1)).isoformat(),
        runtime_fingerprint=dict(files={'src/radar_salud/pulso_editorial_proof.py':
            qa.digest((ROOT / 'src/radar_salud/pulso_editorial_proof.py').read_bytes())}))
    telemetry = [dict(kind='fast', success=True, response_id=model['_pulso_analysis_meta']['response_id'],
                      at=event_time.isoformat())]
    with pytest.raises(ValueError, match='actual_validation_still_deferred'):
        qa.verify_paid_guard_revalidation(item, ROOT, execution=envelope, telemetry=telemetry, origin=actual_origin)
    meta['pulso_editorial_proof_validation'].update(decision='ready', reason='invented_ready_result')
    latest['new_validation'] = deepcopy(meta['pulso_editorial_proof_validation'])
    latest['new_validation_sha256'] = qa.object_digest(latest['new_validation'])
    with pytest.raises(ValueError, match='recorded_verdict_not_actual_guard_result'):
        qa.verify_paid_guard_revalidation(item, ROOT, execution=envelope, telemetry=telemetry, origin=actual_origin)
