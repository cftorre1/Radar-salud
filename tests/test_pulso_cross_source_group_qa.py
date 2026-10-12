"""Independent read-only QA of three real, already-reviewed duplicate groups.

All inputs are immutable Git snapshots. Temporary applications only construct
reader fixtures; they do not alter runtime state or call an AI provider.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from radar_salud.pulso_editorial_review import apply_review

ROOT = Path(__file__).parents[1]
REVIEW = 'data/audits/pulso_cross_source_three_duplicate_publications_editorial_group_2026_10_11.json'
READER = 'data/audits/pulso_cross_source_three_duplicate_publications_independent_review_2026_10_11.json'
REVIEW_SHA = 'a148a3e9bbbb71ae9430f05f6212a468760df298e3765d6549f5d141408befac'
READER_SHA = '361fea64fddce6689795d174371443ce306884e501276085f38894c27c7cfbdd'
spec = importlib.util.spec_from_file_location('cross_source_independent_qa', ROOT / 'scripts/qa_pulso_recovery.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


def encode(root, path, document):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    return qa.digest(target.read_bytes())


@pytest.fixture(scope='module')
def real_originals():
    reader, audit = [json.loads((ROOT / path).read_bytes()) for path in (READER, REVIEW)]
    assert qa.digest((ROOT / READER).read_bytes()) == READER_SHA
    assert qa.digest((ROOT / REVIEW).read_bytes()) == REVIEW_SHA
    original = {}
    for name in ('queue', 'history'):
        ref = reader['inputs'][name]
        payload = subprocess.check_output(['git', 'show', ref['commit'] + ':' + ref['path']], cwd=ROOT)
        assert qa.digest(payload) == ref['file_sha256']
        original[name] = json.loads(payload)
    return dict(reader=reader, audit=audit, **original)


@pytest.fixture
def reviewed(real_originals, tmp_path):
    root = tmp_path
    (root / '.git').symlink_to(subprocess.check_output(
        ['git', 'rev-parse', '--absolute-git-dir'], cwd=ROOT, text=True).strip(), target_is_directory=True)
    registry = json.loads((ROOT / qa.EDITORIAL_REGISTRY_PATH).read_bytes())
    paths = {READER, REVIEW, qa.EDITORIAL_REVIEW_PATH, qa.INDEPENDENT_EDITORIAL_PATH}
    for path, (_, reader_path, _) in qa.FOLLOWUP_REVIEW_PINS.items():
        paths.update((path, reader_path))
    for row in registry['reviews']:
        paths.update((row['review_file'], row['independent_review_file']))
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    if not any(row['review_file'] == REVIEW for row in registry['reviews']):
        registry['reviews'].append(dict(review_file=REVIEW, review_sha256=REVIEW_SHA,
            independent_review_file=READER, independent_review_sha256=READER_SHA))
    encode(root, qa.EDITORIAL_REGISTRY_PATH, registry)
    new5 = json.loads((root / next(iter(qa.FOLLOWUP_REVIEW_PINS))).read_bytes())
    urls = {row['url'] for row in real_originals['audit']['records']} | {row['url'] for row in new5['records']}
    urls |= {row['duplicate_of']['url'] for row in real_originals['audit']['records']}
    queue = {key: deepcopy(row) for key, row in real_originals['queue'].items() if row['raw'].get('url') in urls}
    history = [deepcopy(row) for row in real_originals['history']['signals'] if row.get('source_url') in urls]
    after, updated, _ = apply_review(history, queue, real_originals['audit'], audit_sha256=REVIEW_SHA, audit_path=REVIEW)
    return dict(root=root, queue=updated, history=after,
        snapshot=dict(signals=[deepcopy(row) for row in after if row.get('feed_visibility') is not False]))


def inspect(value):
    return qa.verify_additional_editorial_reviews(**value)


def repin(value, reader, audit):
    # An authorized registry entry still cannot authorize a false original.
    for row in audit['records']:
        reading = next(r for r in reader['all_signals'] if (r['url'], r['publication_date']) == (row['url'], row['publication_date']))
        row['independent_review_record_sha256'] = qa.object_digest(reading)
    audit['independent_review']['sha256'] = encode(value['root'], READER, reader)
    audit_sha = encode(value['root'], REVIEW, audit)
    registry = json.loads((value['root'] / qa.EDITORIAL_REGISTRY_PATH).read_bytes())
    registered = next(row for row in registry['reviews'] if row['review_file'] == REVIEW)
    registered.update(review_sha256=audit_sha, independent_review_sha256=audit['independent_review']['sha256'])
    encode(value['root'], qa.EDITORIAL_REGISTRY_PATH, registry)
    by_url = {row['url']: row for row in audit['records']}
    for item in list(value['queue'].values()) + value['history']:
        meta = item.get('raw', {}).get('metadata')
        provenance = meta.get('editorial_review') if meta else item.get('editorial_review')
        if provenance and provenance.get('review_file') == REVIEW:
            record = by_url[item['raw']['url'] if meta else item['source_url']]
            provenance.update(review_sha256=audit_sha, record_sha256=qa.object_digest(record))
            if record.get('duplicate_of'):
                provenance['duplicate_of'] = deepcopy(record['duplicate_of'])
            if meta:
                meta['editorial_assessment']['review_sha256'] = audit_sha
    return audit_sha


def test_three_exact_group_chains_accept_legacy_limitation_without_fabricating_a_response(reviewed, real_originals):
    proofs, findings = inspect(reviewed)
    assert findings == []
    assert len(proofs) == 6  # ALL5 first focus publications plus the legacy UC publication.
    assert sum(proof['decision'] == 'group' for proof in proofs.values()) == 3
    legacy = next(row for row in real_originals['reader']['all_signals'] if row['original_model_output_missing'])
    source = next(row for row in reviewed['queue'].values() if row['raw']['url'] == legacy['url'])
    assert source['raw']['metadata'].get('analysis_model_output') is None
    assert source['raw']['metadata']['editorial_review']['previous_editorial_review']['review_sha256'] == qa.EDITORIAL_REVIEW_SHA256
    for row in real_originals['reader']['all_signals']:
        target = reviewed['queue'][row['duplicate_survivor_binding']['queue_fingerprint']]
        assert target == real_originals['queue'][row['duplicate_survivor_binding']['queue_fingerprint']]
    assert len([row for row in reviewed['queue'].values() if row['raw']['url'] == 'https://www.suseso.gob.cl/605/w3-article-790601.html']) == 2


@pytest.mark.parametrize('attack', ['rejected_same_url', 'wrong_source', 'wrong_signal', 'missing_fingerprint',
    'target_primary', 'target_quote', 'target_feed_copy', 'legacy_missing_flag', 'legacy_fabricated_model',
    'legacy_binding', 'predecessor_reason', 'group_proposed', 'paid_model', 'attempt_reset'])
def test_rehashed_registered_group_cannot_replace_real_survivor_primary_or_prior_paid_evidence(reviewed, real_originals, attack):
    reader, audit = deepcopy(real_originals['reader']), deepcopy(real_originals['audit'])
    row = next(r for r in audit['records'] if 'chomali-por-listas' in r['url'])
    parent = next(r for r in reader['all_signals'] if r['url'] == row['url'])
    legacy = next(r for r in reader['all_signals'] if r['original_model_output_missing'])
    original = next(r for r in reviewed['queue'].values() if r['raw']['url'] == row['url'])
    if attack == 'rejected_same_url':
        sibling = next(key for key, item in reviewed['queue'].items()
            if item['source'] == 'suseso_fiscalizacion' and item['raw']['url'] == row['duplicate_of']['url'])
        row['duplicate_of']['queue_fingerprint'] = parent['duplicate_survivor_binding']['queue_fingerprint'] = sibling
    elif attack == 'wrong_source': row['duplicate_of']['source_id'] = parent['duplicate_survivor_binding']['source_id'] = 'suseso_fiscalizacion'
    elif attack == 'wrong_signal': row['duplicate_of']['survivor_signal_sha256'] = parent['duplicate_survivor_binding']['survivor_signal_sha256'] = 'f' * 64
    elif attack == 'missing_fingerprint':
        row['duplicate_of'].pop('queue_fingerprint'); parent['duplicate_survivor_binding'].pop('queue_fingerprint')
    elif attack == 'target_primary': parent['target_full_primary_content'] += ' invented operational claim'
    elif attack == 'target_quote': parent['target_supporting_verbatim_quotes'][0]['text'] = 'invented operational claim absent from the primary'
    elif attack == 'target_feed_copy':
        next(r for r in reviewed['snapshot']['signals'] if r['source_url'] == row['duplicate_of']['url'])['why_it_matters'] += ' invented'
    elif attack == 'legacy_missing_flag': legacy['original_model_output_missing'] = False
    elif attack == 'legacy_fabricated_model':
        legacy['original_full_model_output'] = dict(_pulso_analysis_meta=dict(response_id='invented'))
    elif attack == 'legacy_binding': legacy['original_output_binding']['signal_sha256'] = 'f' * 64
    elif attack == 'predecessor_reason': row['previous_editorial_review']['reason'] += ' unaudited'
    elif attack == 'group_proposed': row['proposed'] = dict(what_happened='invented')
    elif attack == 'paid_model': original['raw']['metadata']['analysis_model_output']['what_happened'] += ' invented'
    else: original['attempts'] = 0
    repin(reviewed, reader, audit)
    assert inspect(reviewed)[1]


def test_three_groups_preserve_all_native_stock_and_the_other_first32_reviews(reviewed, real_originals):
    root = reviewed['root']
    paths = set(qa.paid_revalidation_proof_files(ROOT)) | set(qa.current_paid_proof_files(ROOT))
    paths |= set(qa.followup_paid_proof_files(ROOT)) | {qa.CODE_REPAIR_PINS_PATH, 'src/radar_salud/pulso_editorial_proof.py'}
    followup = json.loads((ROOT / qa.FOLLOWUP_PAID_PATH).read_bytes())
    for ref in followup['semantic_references']:
        reader = json.loads((ROOT / ref['path']).read_bytes())
        if reader.get('actual_fixture'):
            paths.add(reader['actual_fixture']['path'])
    for path in paths:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    stock = real_originals['queue']
    original_history = real_originals['history']['signals']
    after, queue, _ = apply_review(original_history, stock, real_originals['audit'], audit_sha256=REVIEW_SHA, audit_path=REVIEW)
    snapshot = dict(signals=[deepcopy(row) for row in after if row.get('feed_visibility') is not False])
    proofs, findings = qa.verify_bound_editorial_review(queue, after, snapshot, root)
    assert findings == []
    assert len(proofs) >= 32
    assert sum(item['source'] != qa.SOURCE for item in stock.values()) == 5293
    assert {key: row for key, row in queue.items() if row['source'] != qa.SOURCE} == {
        key: row for key, row in stock.items() if row['source'] != qa.SOURCE}
    native = [row for row in original_history if not qa.normalized_url(row.get('source_url'))]
    assert len(native) == 897
    assert [row for row in after if not qa.normalized_url(row.get('source_url'))] == native
