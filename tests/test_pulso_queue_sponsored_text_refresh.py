"""A real empty sponsored primary replaces stale factual flags, not paid state."""
import copy
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, fingerprint
from radar_salud.pulso_source import _verified_detail, verified_sponsored_without_text


def test_real_empty_original_refresh_keeps_canonical_queue_and_retry_bookkeeping(tmp_path):
    fixtures = Path(__file__).parent / 'fixtures/pulso_targeted_primary_real'
    record, = [row for row in json.loads((fixtures / 'manifest.json').read_text())['requests']
               if row['target_reason'] == 'core_detail_error_incomplete_article_evidence']
    packed = (fixtures / record['gzip_file']).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == record['gzip_sha256']
    original = gzip.decompress(packed)
    assert hashlib.sha256(original).hexdigest() == record['sha256']
    detail = _verified_detail(dict(url=record['url'], listing='targeted_original'),
                             lambda _: original.decode(record['charset']), None)
    metadata = detail['metadata']
    assert verified_sponsored_without_text(metadata)
    assert metadata['html_sha256'] == record['sha256']
    assert metadata['publication_date'] == '2026-10-11'
    assert metadata['page_text'] == '' and metadata['article_verified'] is False
    assert metadata['article_body_complete'] is False
    raw = RawItem('pulso_latercera', detail['title'], record['url'], 'Pulso / La Tercera',
                  'press_high_trust', metadata['publication_date'], detail['body'], metadata)
    stale = copy.deepcopy(raw)
    stale.metadata.update(article_verified=True, article_body_complete=True, page_text='Unproven older description',
                          editorial_hold='possible_duplicate_requires_incremental_review',
                          event_equivalence_review={'decision':'pending'})
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    queue = PendingQueue(tmp_path / 'queue.json')
    queue.discover('pulso_latercera', [stale], now=now)
    key = fingerprint(stale)
    queue.start(key)
    queue.finish(key, 'retry', 'prior_verification_failure', now=now)
    before = copy.deepcopy(queue.items[key])
    assert queue.discover('pulso_latercera', [raw], now=now) == 0
    current = queue.items[key]
    assert {k:v for k,v in current.items() if k != 'raw'} == {k:v for k,v in before.items() if k != 'raw'}
    proof = current['raw']['metadata']
    assert verified_sponsored_without_text(proof)
    assert proof['editorial_hold'] == 'publisher_sponsored_text_unavailable'
    assert proof['event_equivalence_review'] == {'decision':'pending'}
    assert len(proof['evidence_revisions']) == 1
    snapshot = copy.deepcopy(current)
    queue.discover('pulso_latercera', [raw], now=now)
    assert queue.items[key] == snapshot
    for status in ('published', 'rejected', 'archived'):
        current['status'] = status
        snapshot = copy.deepcopy(current)
        queue.discover('pulso_latercera', [raw], now=now)
        assert queue.items[key] == snapshot
