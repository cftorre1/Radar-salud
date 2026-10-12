"""Dual producer proof tests on all 18 real revalidated publications.

Temporary accept audits exercise provenance only. They do not approve these
signals semantically, modify repository state or invoke a model.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from radar_salud.pulso_editorial_review import apply_review

ROOT = Path(__file__).parents[1]
PRODUCER = '9083056a'
spec = importlib.util.spec_from_file_location('revalidated_review_qa', ROOT / 'scripts/qa_pulso_recovery.py')
qa = importlib.util.module_from_spec(spec); spec.loader.exec_module(qa)


def blob(path):
    return subprocess.check_output(['git', 'show', PRODUCER + ':' + path], cwd=ROOT)


def save(root, path, value):
    target = root / path; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return qa.digest(target.read_bytes())


@pytest.fixture
def actual_reused_reviews(tmp_path):
    commit = subprocess.check_output(['git', 'rev-parse', PRODUCER], cwd=ROOT, text=True).strip()
    (tmp_path / '.git').symlink_to(subprocess.check_output(
        ['git', 'rev-parse', '--absolute-git-dir'], cwd=ROOT, text=True).strip(), target_is_directory=True)
    for path in qa.paid_revalidation_proof_files(ROOT):
        target = tmp_path / path; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    origin = qa.paid_revalidation_origin(tmp_path)
    paths = dict(history='data/history/superintendencia_signals.json', queue='data/state/pending_queue.json',
                 runtime_report='data/audits/pulso_runtime_2026_10_11.json', telemetry='data/ai_usage/responses.jsonl')
    history = json.loads(blob(paths['history']))['signals']; queue = json.loads(blob(paths['queue']))
    execution = json.loads(blob(paths['runtime_report']))['last_core_execution']
    telemetry = [json.loads(line) for line in blob(paths['telemetry']).splitlines() if line]
    readers, records, selected = [], [], {}
    for row in origin['rows'].values():
        if row['runtime_route'] != 'reuse_code_fn':
            continue
        item = queue[row['queue_fingerprint']]; meta = item['raw']['metadata']; model = meta['analysis_model_output']
        signal = next(value for value in history if value.get('source_url') == row['url'])
        proof = qa.verify_paid_guard_revalidation(item, tmp_path, execution=execution,
            telemetry=telemetry, origin=origin, archived_execution=True)
        dual = dict(original_producer=qa.PAID_REVALIDATION_PRODUCER, original_core_code=qa.PAID_REVALIDATION_CODE,
                    publication_execution_code=execution['code_sha'], manifest_ref=qa.PAID_REVALIDATION_PATH,
                    manifest_sha256=qa.PAID_REVALIDATION_SHA256,
                    actual_receipt_sha256=qa.object_digest(meta['paid_guard_revalidation_receipt']), proof=proof)
        quote = meta['page_text'][:100]
        reason = 'Temporary unit audit of the two immutable genuine provenances; no semantic approval.'
        reader = dict(url=row['url'], publication_date=row['publication_date'], decision='accept', exact_reason=reason,
            full_original_body_read=True, full_signal_read=True, original_full_primary_body=meta['page_text'],
            original_body_sha256=meta['article_body_sha256'], original_html_sha256=meta['html_sha256'],
            original_signal_sha256=qa.object_digest(signal), original_full_signal=deepcopy(signal),
            original_published_what_happened=signal['what_happened'], original_published_why_it_matters=signal['why_it_matters'],
            supporting_verbatim_quotes=[dict(origin='original', text=quote)],
            original_output_binding=dict(retained_model_output_semantic_sha256=qa.object_digest(model),
                model_response=model['_pulso_analysis_meta'], signal_sha256=qa.object_digest(signal),
                revalidated_paid_response=dual))
        readers.append(reader)
        records.append(dict(url=row['url'], publication_date=row['publication_date'], original_signal=deepcopy(signal),
            original_signal_sha256=qa.object_digest(signal), original_body_sha256=meta['article_body_sha256'],
            original_model_assessment=deepcopy(meta['editorial_assessment']), decision='accept', reason=reason,
            evidence_quotes=[quote]))
        selected[row['queue_fingerprint']] = deepcopy(item)
    assert len(readers) == len(records) == len(selected) == 18
    reader_document = dict(source_id=qa.SOURCE, inputs={key: dict(commit=commit, path=path, file_sha256=qa.digest(blob(path)))
        for key, path in paths.items()}, all_signals=readers)
    audit = dict(schema_version='pulso_editorial_review_v1', source_id=qa.SOURCE,
                 review_id='unit_only_all18_dual_paid_provenance', records=records)
    return dict(root=tmp_path, queue=selected, history=[deepcopy(signal) for signal in history
                if signal.get('source_url') in {row['url'] for row in records}], audit=audit, reader=reader_document)


def inspect(value):
    reader_path = 'data/audits/pulso_unit_revalidated_reader.json'
    review_path = 'data/audits/pulso_unit_revalidated_review.json'
    for record, reader in zip(value['audit']['records'], value['reader']['all_signals']):
        record['independent_review_record_sha256'] = qa.object_digest(reader)
    reader_sha = save(value['root'], reader_path, value['reader'])
    value['audit']['independent_review'] = dict(path=reader_path, sha256=reader_sha)
    review_sha = save(value['root'], review_path, value['audit'])
    save(value['root'], qa.EDITORIAL_REGISTRY_PATH, dict(schema_version='pulso_paid_editorial_review_registry_v1',
        source_id=qa.SOURCE, reviews=[dict(review_file=review_path, review_sha256=review_sha,
            independent_review_file=reader_path, independent_review_sha256=reader_sha)]))
    history, queue, _ = apply_review(value['history'], value['queue'], value['audit'],
        audit_path=review_path, audit_sha256=review_sha)
    return qa.verify_additional_editorial_reviews(queue, history, dict(signals=deepcopy(history)), value['root'])


def test_all18_revalidated_publications_keep_original_paid_and_later_guard_provenance(actual_reused_reviews):
    proofs, failures = inspect(actual_reused_reviews)
    assert len(proofs) == 18 and failures == []


@pytest.mark.parametrize('attack', ['missing_dual', 'old_producer', 'new_execution', 'manifest', 'receipt_sha', 'response_id'])
def test_rehashed_reader_cannot_replace_either_genuine_provenance(actual_reused_reviews, attack):
    reader = actual_reused_reviews['reader']['all_signals'][0]
    dual = reader['original_output_binding']['revalidated_paid_response']
    if attack == 'missing_dual': reader['original_output_binding'].pop('revalidated_paid_response')
    elif attack == 'old_producer': dual['original_producer'] = '0' * 40
    elif attack == 'new_execution': dual['publication_execution_code'] = '0' * 40
    elif attack == 'manifest': dual['manifest_sha256'] = '0' * 64
    elif attack == 'receipt_sha': dual['actual_receipt_sha256'] = '0' * 64
    else: dual['proof']['original_response_id'] = 'resp_fabricated_prior_receipt'
    assert any(failure['error'] == 'editorial_revalidated_response_dual_provenance_changed'
               for failure in inspect(actual_reused_reviews)[1])


def test_archived_guard_uses_actual_producer_bytes_not_later_checkout(actual_reused_reviews):
    path = actual_reused_reviews['root'] / 'src/radar_salud/pulso_editorial_proof.py'
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text('raise AssertionError("Not the producer guard")\n')
    proofs, failures = inspect(actual_reused_reviews)
    assert len(proofs) == 18 and failures == []
