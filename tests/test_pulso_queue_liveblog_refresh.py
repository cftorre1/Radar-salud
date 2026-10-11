"""Pending originals acquire verified entry dates without paid-state resets."""
import copy
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, fingerprint
from radar_salud.pulso_source import article_body_evidence, extract_article, verified_liveblog_temporal_evidence

FIXTURES = Path(__file__).parent / 'fixtures/pulso_liveblog_temporal_real'
ORIGINALS = json.loads((FIXTURES / 'manifest.json').read_text())['fixtures']
NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def primary(row):
    packed = (FIXTURES / row['path']).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == row['gzip_sha256']
    payload = gzip.decompress(packed)
    assert hashlib.sha256(payload).hexdigest() == row['sha256']
    title, body, metadata = extract_article(payload.decode(row['charset']), row['url'])
    metadata.update(article_body_evidence(body), captured_at=row['captured_at'], source_quality_gate='passed')
    assert verified_liveblog_temporal_evidence(metadata)
    return RawItem('pulso_latercera', title, row['url'], 'Pulso / La Tercera',
                   'press_high_trust', metadata['publication_date'], body[:1800], metadata)


@pytest.mark.parametrize('row', ORIGINALS)
@pytest.mark.parametrize('old_hold', ['publisher_liveblog_entry_dates_unverified',
                                   'possible_duplicate_requires_incremental_review'])
def test_same_original_refreshes_full_timeline_only_preserving_incremental_reviews_and_attempts(tmp_path, row, old_hold):
    fresh = primary(row)
    stale = copy.deepcopy(fresh)
    for field in ('publisher_document_type', 'liveblog_temporal_evidence', 'liveblog_temporal_evidence_verified'):
        stale.metadata.pop(field)
    stale.metadata.update(editorial_hold=old_hold, event_equivalence_review={'decision': 'pending'})
    queue = PendingQueue(tmp_path / 'queue.json')
    queue.discover('pulso_latercera', [stale], now=NOW)
    key = fingerprint(stale)
    queue.start(key)
    queue.finish(key, 'retry', 'prior_temporal_review', now=NOW)
    before = copy.deepcopy(queue.items[key])
    assert queue.discover('pulso_latercera', [fresh], now=NOW) == 0
    current = queue.items[key]
    assert {k:v for k,v in current.items() if k != 'raw'} == {k:v for k,v in before.items() if k != 'raw'}
    proof = current['raw']['metadata']
    assert verified_liveblog_temporal_evidence(proof)
    assert proof['html_sha256'] == before['raw']['metadata']['html_sha256']
    assert proof['page_text'] == before['raw']['metadata']['page_text']
    assert proof['event_equivalence_review'] == {'decision': 'pending'}
    assert proof.get('editorial_hold') == (old_hold if old_hold.startswith('possible_duplicate') else None)
    assert len(proof['evidence_revisions']) == 1
    saved = copy.deepcopy(current)
    queue.discover('pulso_latercera', [fresh], now=NOW)
    assert queue.items[key] == saved
    for terminal in ('published', 'rejected', 'archived'):
        current['status'] = terminal
        saved = copy.deepcopy(current)
        queue.discover('pulso_latercera', [fresh], now=NOW)
        assert queue.items[key] == saved


@pytest.mark.parametrize('row', ORIGINALS)
def test_invalid_entry_hash_cannot_resolve_real_temporal_hold(tmp_path, row):
    fresh = primary(row)
    stale = copy.deepcopy(fresh)
    stale.metadata.update(editorial_hold='publisher_liveblog_entry_dates_unverified')
    stale.metadata.pop('liveblog_temporal_evidence')
    queue = PendingQueue(tmp_path / 'queue.json')
    queue.discover('pulso_latercera', [stale], now=NOW)
    key = fingerprint(stale)
    before = copy.deepcopy(queue.items[key])
    fresh.metadata['liveblog_temporal_evidence']['entries'][0]['body'] += ' unverified mutation'
    assert not verified_liveblog_temporal_evidence(fresh.metadata)
    queue.discover('pulso_latercera', [fresh], now=NOW)
    assert queue.items[key] == before
