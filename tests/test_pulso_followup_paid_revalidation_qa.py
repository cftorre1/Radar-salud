"""Independent five-member authority; synthetic calls only in processor units."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('followup_paid_independent_qa', ROOT / 'scripts/qa_pulso_recovery.py')
qa = importlib.util.module_from_spec(spec); spec.loader.exec_module(qa)
ALL_URLS = [row['url'] for row in json.loads((ROOT / qa.FOLLOWUP_PAID_PATH).read_text())['rows']]
# Premium sections never re-enter the full-body paid paths (rights policy, Dirección 28-oct-2026);
# their policy outcome is checked in test_premium_member_keeps_its_paid_answer_without_any_request.
from paywall_test_support import assert_premium_replay, is_premium, premium_under_path_scope
from radar_salud.source_rights import paywall_policy
PREMIUM_URLS = [url for url in ALL_URLS if premium_under_path_scope(url)]
URLS = [url for url in ALL_URLS if url not in PREMIUM_URLS]


@pytest.fixture(scope='module')
def actual_origin():
    return qa.followup_paid_origin(ROOT)


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


@pytest.fixture(params=URLS, ids=[url.split('/')[-2][:35] for url in URLS])
def case(request, tmp_path, actual_origin, monkeypatch):
    # This unit isolates the earlier five-member processing envelope. The
    # subsequently paid final-two authority is exercised with claim-erasure
    # attacks in test_pulso_final_paid_revalidation_qa, never disabled at runtime.
    from radar_salud import pulso_final_paid_revalidation
    monkeypatch.setattr(pulso_final_paid_revalidation, 'known_original_candidate', lambda raw: False)
    row = actual_origin['rows'][request.param]
    key = row['queue_fingerprint']; original = actual_origin['originals'][key]
    queue = PendingQueue(tmp_path / 'queue.json'); queue.items = {key: deepcopy(original)}
    start = datetime.now(timezone.utc) - timedelta(seconds=1)
    queue.discover(qa.SOURCE, [fresh(original)], now=start)
    item = queue.items[key]; raw = RawItem(**deepcopy(item['raw']))
    assert qa.FOLLOWUP_PAID_STAMP in raw.metadata
    def forbidden(**kwargs):
        pytest.fail('This unit cannot fetch the publisher or request an external model')
    monkeypatch.setattr(beta_sources, 'fetch_html', forbidden)
    events = deepcopy(actual_origin['telemetry'])
    if row['runtime_route'] == 'reuse_code_fn':
        monkeypatch.setattr(llm_analysis, 'analyze_news', forbidden)
    else:
        model = deepcopy(original['raw']['metadata']['analysis_model_output'])
        model['relevance_score'] = 71  # Synthetic conservative rejection, never paid evidence.
        model['_pulso_analysis_meta']['response_id'] = 'resp_synthetic_unit_followup5_distinct'
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
    return qa.verify_followup_paid_revalidation(root=ROOT, **case)


def test_premium_member_keeps_its_paid_answer_without_any_request(actual_origin, tmp_path, monkeypatch):
    assert len(PREMIUM_URLS) == 1 and len(URLS) == 4
    def forbidden(**kwargs):
        pytest.fail('A premium piece cannot fetch the publisher or request a model without AI budget')
    monkeypatch.setattr(beta_sources, 'fetch_html', forbidden)
    monkeypatch.setattr(llm_analysis, 'analyze_news', forbidden)
    for url in PREMIUM_URLS:
        row = actual_origin['rows'][url]
        original = actual_origin['originals'][row['queue_fingerprint']]
        queue = PendingQueue(tmp_path / 'queue.json'); queue.items = {row['queue_fingerprint']: deepcopy(original)}
        queue.discover(qa.SOURCE, [fresh(original)], now=datetime.now(timezone.utc))
        raw = RawItem(**deepcopy(queue.items[row['queue_fingerprint']]['raw']))
        assert is_premium(raw)
        assert_premium_replay(beta_sources.process_curated_beta_source, raw)


def test_original_five_are_genuine_deferred_premise_not_approved(actual_origin):
    assert len(actual_origin['originals']) == 5 and len(actual_origin['successful_response_ids']) == 10
    assert all(row['status'] == 'retry' and row['attempts'] == 4 for row in actual_origin['originals'].values())
    assert actual_origin['execution']['code_sha'] == qa.FOLLOWUP_PAID_CODE
    assert len(actual_origin['proof_files']) == 3
    for item in actual_origin['originals'].values():
        assert not qa.requires_followup_paid_authority(item, actual_origin)
        assert qa.verify_followup_paid_revalidation(item, ROOT, execution=actual_origin['execution'],
                   telemetry=actual_origin['telemetry'], origin=actual_origin, archived_execution=True) is None


def test_followup_partitions_use_three_intact_paid_answers_or_new_below_gate_reject(case):
    proof = inspect(case)
    assert proof['prior981_and908_and66_paid_provenances_preserved'] and proof['publication_approved'] is False
    assert (proof['current_response_id'] == proof['original_response_id']) == proof['old_paid_output_reused']
    if not proof['old_paid_output_reused']:
        assert case['item']['raw']['metadata']['pulso_editorial_proof_validation']['reason'] == 'editorial_relevance_below_threshold'


def test_erasing_every_followup_claim_cannot_fall_back_to_genuinely_valid_current12(case):
    value = deepcopy(case); metadata = value['item']['raw']['metadata']
    for field in (qa.FOLLOWUP_PAID_STAMP, qa.FOLLOWUP_PAID_RECEIPT, qa.FOLLOWUP_PAID_ATTEMPTS):
        metadata.pop(field, None)
    metadata['evidence_revisions'] = [row for row in metadata['evidence_revisions'] if row.get('reason') != qa.FOLLOWUP_PAID_REVISION]
    assert not qa.has_followup_paid_claim(metadata)
    if value['origin']['rows'][value['item']['raw']['url']]['runtime_route'] == 'assess_contract_or_semantic_defect':
        assert qa.verify_current_paid_revalidation(value['item'], ROOT, execution=value['execution'],
                   telemetry=value['telemetry'])['disposition'] == 'assess_contract_or_semantic_defect'
    assert qa.requires_followup_paid_authority(value['item'], value['origin'])
    with pytest.raises(ValueError, match='followup_paid_required_authority_missing'):
        inspect(value)


@pytest.mark.parametrize('field', [qa.FOLLOWUP_PAID_STAMP, qa.FOLLOWUP_PAID_RECEIPT, qa.FOLLOWUP_PAID_ATTEMPTS])
def test_surviving_claim_or_archive_keeps_authority_required(case, field):
    value = deepcopy(case); value['item']['raw']['metadata'].pop(field, None)
    if field != qa.FOLLOWUP_PAID_STAMP and field not in case['item']['raw']['metadata']:
        return
    with pytest.raises(ValueError):
        inspect(value)


@pytest.mark.parametrize('mutation', ['body', 'day', 'role', 'attempts', 'archive', 'verdict', 'window', 'guard', 'telemetry'])
def test_original_proofs_and_actual_guard_telemetry_cannot_be_forged(case, mutation):
    value = deepcopy(case); item = value['item']; metadata = item['raw']['metadata']
    if mutation == 'body': metadata['page_text'] += ' invented body'
    elif mutation == 'day': item['raw']['event_date'] = '2026-10-10'
    elif mutation == 'role': metadata['market_role'] = 'official'
    elif mutation == 'attempts': item['attempts'] = 4
    elif mutation == 'archive':
        next(row for row in metadata['evidence_revisions'] if row['reason'] == qa.FOLLOWUP_PAID_REVISION)['previous_processing_raw']['title'] += ' invented'
    elif mutation == 'verdict':
        metadata['pulso_editorial_proof_validation']['decision'] = 'rejected'
        metadata['pulso_editorial_proof_validation']['reason'] = 'invented_rehashed_unit_verdict'
        if qa.FOLLOWUP_PAID_RECEIPT in metadata:
            receipt = metadata[qa.FOLLOWUP_PAID_RECEIPT]; receipt['new_validation'] = deepcopy(metadata['pulso_editorial_proof_validation'])
            receipt['new_validation_sha256'] = qa.object_digest(receipt['new_validation'])
        else:
            for field in (qa.FOLLOWUP_PAID_ATTEMPTS, qa.CURRENT_PAID_ATTEMPTS, 'paid_guard_new_fast_attempt_receipts'):
                receipt = metadata[field][-1]; receipt['new_validation'] = deepcopy(metadata['pulso_editorial_proof_validation'])
                receipt['new_validation_sha256'] = qa.object_digest(receipt['new_validation'])
    elif mutation == 'window': value['execution']['finished_at'] = value['execution']['started_at']
    elif mutation == 'guard': value['execution']['runtime_fingerprint']['files']['src/radar_salud/pulso_editorial_proof.py'] = '0' * 64
    elif mutation == 'telemetry':
        response = metadata['analysis_model_output']['_pulso_analysis_meta']['response_id']
        if qa.FOLLOWUP_PAID_RECEIPT in metadata:
            value['origin']['successful_response_ids'].discard(response)
        else: value['telemetry'] = [event for event in value['telemetry'] if event.get('response_id') != response]
    with pytest.raises(ValueError):
        inspect(value)


def test_seven_terminal12_and_all37_older_paid_outputs_keep_real_guard_and_window(actual_origin):
    original12 = qa.current_paid_origin(ROOT)
    older = qa.paid_revalidation_origin(ROOT)
    checked12 = checked49 = 0
    for item in actual_origin['queue'].values():
        if item.get('source') != qa.SOURCE or item.get('status') not in {'published', 'rejected'}:
            continue
        meta = item['raw']['metadata']
        if qa.has_current_paid_claim(meta):
            execution = qa.unchanged_current_paid_execution(item, actual_origin)
            assert execution is actual_origin['execution']
            assert qa.verify_current_paid_revalidation(item, ROOT, execution=execution, telemetry=actual_origin['telemetry'],
                       origin=original12, archived_execution=True)
            checked12 += 1
        elif qa.has_paid_revalidation_claim(meta):
            execution = qa.unchanged_previous_paid_execution(item, original12)
            assert execution is original12['execution']
            assert qa.verify_paid_guard_revalidation(item, ROOT, execution=execution, telemetry=actual_origin['telemetry'],
                       origin=older, archived_execution=True)
            checked49 += 1
    assert (checked12, checked49) == (7, 37)
