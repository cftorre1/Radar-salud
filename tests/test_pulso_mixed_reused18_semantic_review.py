"""Replay ALL retained originals and immutable paid human-review inputs.

Application runs only on temporary copies; these checks grant no final runtime
acceptance and never re-run a model or alter live queue/history/feed files.
"""
from copy import deepcopy
import gzip
import html
import importlib.util
import json
from pathlib import Path
import subprocess

from radar_salud.pulso_editorial_review import apply_review

ROOT = Path(__file__).parents[1]
READER = 'data/audits/pulso_mixed_reused18_independent_semantic_review_2026_10_11.json'
REVIEW = 'data/audits/pulso_mixed_reused18_editorial_corrections_2026_10_11.json'
spec = importlib.util.spec_from_file_location('mixed18_semantic_reader_qa', ROOT / 'scripts/qa_pulso_recovery.py')
qa = importlib.util.module_from_spec(spec); spec.loader.exec_module(qa)


def test_all24_full_body_model_and_original_html_dates_remain_exact():
    reader = json.loads((ROOT / READER).read_bytes())
    rows = reader['all_signals'] + reader['all_rejections']
    assert len(reader['all_signals']) == 18 and len(reader['all_rejections']) == 6
    assert len({row['url'] for row in rows}) == 24
    assert sum(len(row['original_full_primary_body']) for row in rows) == 80183
    for row in rows:
        body, model = row['original_full_primary_body'], row['original_full_model_output']
        assert qa.digest(body.encode()) == row['original_body_sha256']
        assert model['_pulso_analysis_meta']['analysis_text_sha256'] == row['original_body_sha256']
        assert row['original_byte_proof']['verified'] is True
        for capture in row['original_byte_proof']['records']:
            compressed = (ROOT / capture['gzip_file']).read_bytes()
            assert qa.digest(compressed) == capture['gzip_sha256']
            raw = gzip.decompress(compressed)
            assert qa.digest(raw) == capture['sha256']
            parser = qa.PrimaryDates(); parser.feed(raw.decode('utf-8'))
            assert parser.canonical == row['url']
            assert parser.days_for(row['url']) == {row['publication_date']}
            _, original_body = parser.primary_text(row['url'])
            assert ' '.join(html.unescape(original_body).split()) == ' '.join(body.split())
        if row in reader['all_rejections']:
            assert row['relevance_score'] < 72 and row['actual_reason'] == 'editorial_relevance_below_threshold'
            assert model['relevance_score'] == row['relevance_score']


def test_all18_temp_application_and_replay_bind_actual_two_producer_provenances(tmp_path):
    audit = json.loads((ROOT / REVIEW).read_bytes())
    reader = json.loads((ROOT / READER).read_bytes())
    assert audit['independent_review']['sha256'] == qa.digest((ROOT / READER).read_bytes())
    urls = {row['url'] for row in audit['records']}
    producer = reader['producer_state_commit']
    queue = json.loads(subprocess.check_output(['git', 'show', producer + ':data/state/pending_queue.json'], cwd=ROOT))
    history = json.loads(subprocess.check_output(['git', 'show', producer + ':data/history/superintendencia_signals.json'], cwd=ROOT))['signals']
    queue = {key: row for key, row in queue.items() if row.get('raw', {}).get('url') in urls}
    history = [row for row in history if row.get('source_url') in urls]
    assert len(queue) == len(history) == 18
    (tmp_path / '.git').symlink_to(subprocess.check_output(
        ['git', 'rev-parse', '--absolute-git-dir'], cwd=ROOT, text=True).strip(), target_is_directory=True)
    for path in list(qa.paid_revalidation_proof_files(ROOT)) + [READER, REVIEW]:
        target = tmp_path / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes((ROOT / path).read_bytes())
    registry = dict(schema_version='pulso_paid_editorial_review_registry_v1', source_id=qa.SOURCE,
        reviews=[dict(review_file=REVIEW, review_sha256=qa.digest((ROOT / REVIEW).read_bytes()),
                      independent_review_file=READER, independent_review_sha256=qa.digest((ROOT / READER).read_bytes()))])
    (tmp_path / qa.EDITORIAL_REGISTRY_PATH).write_text(json.dumps(registry))
    new_history, new_queue, summary = apply_review(history, queue, audit,
        audit_path=REVIEW, audit_sha256=qa.digest((ROOT / REVIEW).read_bytes()))
    assert summary['decisions'] == dict(accept=15, correct=2, group=1, reject=0)
    assert summary['ai_calls'] == summary['queue_attempt_resets'] == summary['primary_evidence_mutations'] == 0
    snapshot = dict(signals=[deepcopy(row) for row in new_history if row.get('feed_visibility') is True])
    proofs, failures = qa.verify_additional_editorial_reviews(new_queue, new_history, snapshot, tmp_path)
    assert len(proofs) == 18 and failures == []
    replay_history, replay_queue, replay = apply_review(new_history, new_queue, audit,
        audit_path=REVIEW, audit_sha256=qa.digest((ROOT / REVIEW).read_bytes()))
    assert replay_history == new_history and replay_queue == new_queue
    assert replay['unchanged_on_replay'] == 18
