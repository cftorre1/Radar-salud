"""Independent QA on immutable908 responses and temporary processor outputs.

New model responses and execution envelopes in unit fixtures are explicitly
synthetic. No external model, publisher or repository state is written.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis, pulso_current_paid_revalidation as current
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('current_paid_independent_qa', ROOT / 'scripts/qa_pulso_recovery.py')
qa = importlib.util.module_from_spec(spec); spec.loader.exec_module(qa)


@pytest.fixture(scope='module')
def actual_origin():
    return qa.current_paid_origin(ROOT)


def fresh(entry):
    value = deepcopy(entry['raw'])
    for field in list(value['metadata']):
        if field.startswith('analysis_') or field in (
                'article_body_complete', 'editorial_assessment', 'pulso_editorial_proof_validation',
                'primary_item_binding', 'evidence_revisions', 'queue_identity_fingerprint',
                'editorial_code_repair_admission', 'paid_guard_revalidation_admission',
                'paid_guard_revalidation_receipt', 'paid_guard_new_fast_attempt_receipts',
                qa.CURRENT_PAID_STAMP, qa.CURRENT_PAID_RECEIPT, qa.CURRENT_PAID_ATTEMPTS):
            value['metadata'].pop(field)
    return RawItem(**value)


@pytest.fixture(params=['reuse_code_fn', 'assess_contract_or_semantic_defect'])
def case(request, tmp_path, actual_origin, monkeypatch):
    # Premium sections never re-enter the full-body paid paths (rights policy, Dirección
    # 28-oct-2026; see tests/paywall_test_support.py): the unit uses the first OPEN-section row
    # that this current authority still governs (not superseded by the later followup/final ones).
    from radar_salud import pulso_final_paid_revalidation as final
    from radar_salud import pulso_followup_paid_revalidation as followup
    from paywall_test_support import is_premium
    def governed_open(row):
        raw = RawItem(**deepcopy(actual_origin['originals'][row['queue_fingerprint']]['raw']))
        return not (is_premium(raw) or followup.known_original_candidate(raw) or final.known_original_candidate(raw))
    row = next(row for row in actual_origin['rows'].values() if row['runtime_route'] == request.param
               and governed_open(row))
    key = row['queue_fingerprint']; original = actual_origin['originals'][key]
    queue = PendingQueue(tmp_path / 'queue.json'); queue.items = {key: deepcopy(original)}
    start = datetime.now(timezone.utc) - timedelta(seconds=1)
    queue.discover(qa.SOURCE, [fresh(original)], now=start)
    item = queue.items[key]; raw = RawItem(**deepcopy(item['raw']))
    def forbidden(**kwargs):
        pytest.fail('The unit cannot fetch the publisher or request an external model')
    monkeypatch.setattr(beta_sources, 'fetch_html', forbidden)
    events = deepcopy(actual_origin['telemetry'])
    if request.param == 'reuse_code_fn':
        monkeypatch.setattr(llm_analysis, 'analyze_news', forbidden)
    else:
        model = deepcopy(original['raw']['metadata']['analysis_model_output'])
        model['relevance_score'] = 71  # Explicit synthetic conservative rejection.
        model['_pulso_analysis_meta']['response_id'] = 'resp_synthetic_unit_current12_new_distinct'
        model['_pulso_analysis_meta']['raw_model_output_sha256'] = qa.object_digest({
            key: value for key, value in model.items() if key != '_pulso_analysis_meta'})
        monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: deepcopy(model))
        events.append(dict(at=datetime.now(timezone.utc).isoformat(), kind='fast', success=True,
                           response_id=model['_pulso_analysis_meta']['response_id']))
    signal = beta_sources.process_curated_beta_source(raw, {})
    item['raw'] = asdict(raw); item['attempts'] += 1
    item['status'] = 'published' if signal else 'rejected'
    execution = dict(started_at=start.isoformat(), finished_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        runtime_fingerprint=dict(files={'src/radar_salud/pulso_editorial_proof.py':
            qa.digest((ROOT / 'src/radar_salud/pulso_editorial_proof.py').read_bytes())}))
    return dict(item=item, execution=execution, telemetry=events, origin=actual_origin)


def inspect(case):
    return qa.verify_current_paid_revalidation(root=ROOT, **case)


def test_all12_original25_calls_two_semantic_readers_and_failed_908_producer_remain_honest(actual_origin):
    assert len(actual_origin['originals']) == 12 and len(actual_origin['successful_response_ids']) == 25
    assert all(row['status'] == 'retry' and row['attempts'] == 3 for row in actual_origin['originals'].values())
    assert actual_origin['execution']['code_sha'] == qa.CURRENT_PAID_CODE
    assert len(actual_origin['proof_files']) == 3


def test_two_current_origins_and_normal_existing_threshold_remain_distinct(case):
    proof = inspect(case)
    assert proof['prior981_and908_paid_provenances_preserved'] is True and proof['publication_approved'] is False
    assert (proof['current_response_id'] == proof['original_response_id']) == proof['old_paid_output_reused']
    if not proof['old_paid_output_reused']:
        assert case['item']['raw']['metadata']['pulso_editorial_proof_validation']['reason'] == 'editorial_relevance_below_threshold'


@pytest.mark.parametrize('claim', ['receipt', 'revision', 'attempt'])
def test_missing_stamp_never_hides_surviving_current_claim(case, claim):
    value = deepcopy(case); metadata = value['item']['raw']['metadata']; metadata.pop(qa.CURRENT_PAID_STAMP)
    if claim == 'receipt':
        metadata[qa.CURRENT_PAID_RECEIPT] = metadata.get(qa.CURRENT_PAID_RECEIPT, {'unit_surviving_claim': True})
        metadata['evidence_revisions'] = []
    elif claim == 'revision':
        metadata.pop(qa.CURRENT_PAID_RECEIPT, None); metadata.pop(qa.CURRENT_PAID_ATTEMPTS, None)
    else:
        metadata[qa.CURRENT_PAID_ATTEMPTS] = metadata.get(qa.CURRENT_PAID_ATTEMPTS, [{'unit_surviving_claim': True}])
        metadata.pop(qa.CURRENT_PAID_RECEIPT, None); metadata['evidence_revisions'] = []
    assert qa.has_current_paid_claim(metadata)
    with pytest.raises(ValueError, match='admission_archive_or_historical_chain_changed'):
        inspect(value)


def test_processed_frozen12_cannot_erase_all_current_claims_and_fall_back_to_legacy(case):
    value = deepcopy(case); metadata = value['item']['raw']['metadata']
    for field in (qa.CURRENT_PAID_STAMP, qa.CURRENT_PAID_RECEIPT, qa.CURRENT_PAID_ATTEMPTS):
        metadata.pop(field, None)
    metadata['evidence_revisions'] = [revision for revision in metadata['evidence_revisions']
                                      if revision.get('reason') != qa.CURRENT_PAID_REVISION]
    assert not qa.has_current_paid_claim(metadata)
    if value['origin']['rows'][value['item']['raw']['url']]['runtime_route'] == 'assess_contract_or_semantic_defect':
        # The older49 authority genuinely passes; it cannot replace the exact908
        # archive/admission required for this already-processed member of12.
        assert qa.verify_paid_guard_revalidation(value['item'], ROOT, execution=value['execution'],
                    telemetry=value['telemetry'])['disposition'] == 'assess_contract_or_semantic_defect'
    assert qa.requires_current_paid_authority(value['item'], value['origin'])
    with pytest.raises(ValueError, match='current_paid_required_authority_missing'):
        inspect(value)
    with pytest.raises(ValueError, match='current_paid_required_authority_missing'):
        qa.verify_current_paid_revalidation(value['item'], ROOT, execution=value['execution'], telemetry=value['telemetry'])


def test_unprocessed_immutable908_remains_historical_evidence_not_new_authority(actual_origin):
    for original in actual_origin['originals'].values():
        assert not qa.requires_current_paid_authority(original, actual_origin)
        assert qa.verify_current_paid_revalidation(original, ROOT, execution=actual_origin['execution'],
                    telemetry=actual_origin['telemetry'], origin=actual_origin) is None
        processed = deepcopy(original); processed['attempts'] += 1
        assert qa.requires_current_paid_authority(processed, actual_origin)


@pytest.mark.parametrize('attack', ['body', 'html', 'role', 'day', 'attempt', 'prior_model', 'old_receipt', 'old_revision'])
def test_rehashed_local_metadata_cannot_change_primary_or_either_original_chain(case, attack):
    value = deepcopy(case); item = value['item']; meta = item['raw']['metadata']
    if attack == 'body': meta['page_text'] += ' altered'
    elif attack == 'html': meta['html_sha256'] = '0' * 64
    elif attack == 'role': meta['market_role'] = 'official'
    elif attack == 'day': item['raw']['event_date'] = '2026-10-10'
    elif attack == 'attempt': item['attempts'] = True
    elif attack == 'prior_model':
        revision = next(r for r in meta['evidence_revisions'] if r['reason'] == qa.CURRENT_PAID_REVISION)
        revision['previous_processing_raw']['metadata']['analysis_model_output']['why_it_matters'] += ' forged'
    elif attack == 'old_receipt': meta['paid_guard_new_fast_attempt_receipts'][0]['new_response_id'] = 'resp_forged_old'
    else: meta['evidence_revisions'] = [r for r in meta['evidence_revisions'] if r['reason'] != 'verified_paid_guard_revalidation_admission']
    with pytest.raises(ValueError): inspect(value)


def test_synced_rehashed_new_verdict_is_replayed_against_actual_guard(case):
    value = deepcopy(case); meta = value['item']['raw']['metadata']; validation = meta['pulso_editorial_proof_validation']
    validation['reason'] = 'invented-reason-retaining-all-other-genuine-fields'
    if qa.CURRENT_PAID_RECEIPT in meta:
        meta[qa.CURRENT_PAID_RECEIPT].update(new_validation=deepcopy(validation), new_validation_sha256=qa.object_digest(validation))
    else:
        for key in (qa.CURRENT_PAID_ATTEMPTS, 'paid_guard_new_fast_attempt_receipts'):
            meta[key][-1].update(new_validation=deepcopy(validation), new_validation_sha256=qa.object_digest(validation))
    with pytest.raises(ValueError, match='recorded_verdict_not_execution_bound_guard_result'):
        inspect(value)


def test_new_fast_requires_current_window_event_and_cannot_reuse_original908_id(case):
    if case['origin']['rows'][case['item']['raw']['url']]['runtime_route'] == 'reuse_code_fn':
        return
    value = deepcopy(case); value['telemetry'] = deepcopy(case['origin']['telemetry'])
    with pytest.raises(ValueError, match='requires_new_actual_bound_fast'):
        inspect(value)


def test_terminal908_unchanged_inputs_keep_their_real_guard_window_not_later_execution(actual_origin):
    rows = [item for item in actual_origin['queue'].values() if item.get('source') == qa.SOURCE
            and item.get('status') in {'published', 'rejected'}
            and item.get('raw', {}).get('metadata', {}).get('paid_guard_revalidation_admission')]
    assert len(rows) == 37
    for item in rows:
        assert qa.unchanged_previous_paid_execution(item, actual_origin) == actual_origin['execution']
        for field in ('analysis_model_output', 'pulso_editorial_proof_validation', 'paid_guard_new_fast_attempt_receipts'):
            altered = deepcopy(item); altered['raw']['metadata'][field] = {'unit_changed': True}
            assert qa.unchanged_previous_paid_execution(altered, actual_origin) is None
    assert all(qa.unchanged_previous_paid_execution(item, actual_origin) is None
               for item in actual_origin['originals'].values())
