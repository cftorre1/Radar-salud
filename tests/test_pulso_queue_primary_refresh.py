"""Queue migrations use retained original HTML and preserve paid bookkeeping."""
import copy
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, fingerprint
from radar_salud.pulso_source import (_verified_detail, verified_publication_date_conflict,
                                    verified_sponsored_content, verified_video_without_text)

FIXTURES = Path(__file__).parent/'fixtures/pulso_editorial_exception_real'
MANIFEST = json.loads((FIXTURES/'manifest.json').read_text())
NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def fresh_original(row):
    packed = (FIXTURES/row['gzip_file']).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == row['gzip_sha256']
    original = gzip.decompress(packed)
    assert hashlib.sha256(original).hexdigest() == row['sha256']
    result = _verified_detail({'url': row['url'], 'listing': 'original-fixture'},
                              lambda _: original.decode(row['charset']), None)
    return RawItem('pulso_latercera', result['title'], row['url'], 'Pulso / La Tercera',
                   'press_high_trust', result['metadata'].get('publication_date'),
                   result['body'], result['metadata'])


def test_all_original_publisher_holds_replace_stale_pending_proof_without_resetting_queue(tmp_path):
    migrated = []
    for row in MANIFEST['requests']:
        fresh = fresh_original(row)
        metadata = fresh.metadata
        if not (verified_publication_date_conflict(metadata) or verified_video_without_text(metadata)
                or verified_sponsored_content(metadata)):
            continue
        queue = PendingQueue(tmp_path/(str(len(migrated))+'.json'))
        stale = copy.deepcopy(fresh)
        stale.metadata = {'article_verified': True, 'page_text': metadata.get('page_text'),
                          'editorial_hold': 'possible_duplicate_requires_incremental_review',
                          'event_equivalence_review': {'decision': 'pending'}}
        queue.discover('pulso_latercera', [stale], now=NOW)
        key = fingerprint(stale)
        queue.start(key)
        queue.finish(key, 'retry', 'old_verification_failure', now=NOW)
        before = copy.deepcopy(queue.items[key])
        assert queue.discover('pulso_latercera', [fresh], now=NOW) == 0
        current = queue.items[key]
        assert {k:v for k,v in current.items() if k != 'raw'} == {k:v for k,v in before.items() if k != 'raw'}
        saved = current['raw']['metadata']
        assert saved['article_verified'] == metadata['article_verified']
        assert saved['publication_date_verified'] == metadata['publication_date_verified']
        assert saved['article_body_sha256'] == metadata['article_body_sha256']
        assert current['raw']['event_date'] == fresh.event_date
        assert saved['event_equivalence_review'] == stale.metadata['event_equivalence_review']
        if metadata.get('editorial_hold'):
            assert saved['editorial_hold'] == metadata['editorial_hold']
        assert len(saved['evidence_revisions']) == 1
        snapshot = copy.deepcopy(current)
        queue.discover('pulso_latercera', [fresh], now=NOW)
        assert queue.items[key] == snapshot
        for status in ['published', 'rejected', 'archived']:
            queue.items[key]['status'] = status
            terminal = copy.deepcopy(queue.items[key])
            queue.discover('pulso_latercera', [fresh], now=NOW)
            assert queue.items[key] == terminal
        migrated.append(row['url'])
    assert len(migrated) == 27


@pytest.mark.parametrize('bad_proof', ['primary_identity_verified', 'publication_date_verified', 'canonical_url'])
def test_same_text_factual_proof_refresh_is_fail_closed_and_preserves_unrelated_records(tmp_path, bad_proof):
    row = next(row for row in MANIFEST['requests'] if '/horizontes/noticia/' in row['url'])
    fresh = fresh_original(row)
    queue = PendingQueue(tmp_path/'queue.json')
    stale = copy.deepcopy(fresh)
    stale.metadata = {'article_verified': True, 'page_text': fresh.metadata['page_text']}
    queue.discover('pulso_latercera', [stale], now=NOW)
    key = fingerprint(stale)
    queue.items['unrelated'] = {'source': 'minsal', 'status': 'pending', 'raw': {'url': 'official-original'}}
    original = copy.deepcopy(queue.items)
    invalid = copy.deepcopy(fresh)
    invalid.metadata[bad_proof] = False if bad_proof != 'canonical_url' else 'https://www.latercera.com/nacional/noticia/different/'
    queue.discover('pulso_latercera', [invalid], now=NOW)
    assert queue.items == original
    queue.discover('pulso_latercera', [fresh], now=NOW)
    assert queue.items['unrelated'] == original['unrelated']
    assert queue.items[key]['raw']['metadata']['primary_identity_verified'] is True
    assert queue.items[key]['raw']['metadata']['publication_date_verified'] is True


def test_legacy_verified_cache_flags_require_bound_original_hash_and_coherent_dates():
    row = next(row for row in MANIFEST['requests'] if '/horizontes/noticia/' in row['url'])
    original = gzip.decompress((FIXTURES/row['gzip_file']).read_bytes()).decode(row['charset'])
    entry = {'url': row['url'], 'listing': 'primary-feed', 'lastmod': 'unchanged-publisher-token'}
    valid = _verified_detail(entry, lambda _: original, None)
    legacy = copy.deepcopy(valid)
    legacy['metadata'].pop('primary_identity_verified')
    legacy['metadata'].pop('publication_date_verified')
    calls = []

    def loader(url):
        calls.append(url)
        return original

    reused = _verified_detail(entry, loader, legacy)
    assert not calls and reused['cache_hit']
    assert reused['metadata']['primary_identity_verified'] is True
    assert reused['metadata']['publication_date_verified'] is True
    for field in ['captured_at', 'html_sha256', 'article_body_sha256', 'publication_date', 'publication_evidence']:
        assert reused['metadata'][field] == valid['metadata'][field]
    for field, value in [('canonical_url', 'https://www.latercera.com/nacional/noticia/different/'),
                         ('html_sha256', 'invalid-hash'), ('publication_evidence', []),
                         ('primary_identity_verified', False), ('publication_date_verified', False)]:
        corrupted = copy.deepcopy(legacy)
        corrupted['metadata'][field] = value
        refreshed = _verified_detail(entry, loader, corrupted)
        assert not refreshed['cache_hit'] and calls[-1] == row['url']
    assert len(calls) == 5


@pytest.mark.parametrize('old_hold', ['publisher_conflicting_publication_dates', 'publisher_video_text_unavailable',
                                    'publisher_sponsored_content_review_required', 'publisher_opinion_taxonomy',
                                    'possible_duplicate_requires_incremental_review'])
def test_verified_factual_rediscovery_resolves_only_obsolete_publisher_holds(tmp_path, old_hold):
    row = next(row for row in MANIFEST['requests'] if '/horizontes/noticia/' in row['url'])
    fresh = fresh_original(row)
    assert fresh.metadata['publisher_taxonomy']['classification'] == 'factual'
    stale = copy.deepcopy(fresh)
    stale.metadata.update(editorial_hold=old_hold, article_verified=False,
                          publisher_exception_reason=old_hold,
                          event_equivalence_review={'decision': 'pending', 'reason': 'separate_event_review'})
    queue = PendingQueue(tmp_path/'queue.json')
    queue.discover('pulso_latercera', [stale], now=NOW)
    key = fingerprint(stale)
    queue.start(key)
    queue.finish(key, 'retry', 'prior_hold', now=NOW)
    before = copy.deepcopy(queue.items[key])
    queue.discover('pulso_latercera', [fresh], now=NOW)
    current = queue.items[key]
    assert {k:v for k,v in current.items() if k != 'raw'} == {k:v for k,v in before.items() if k != 'raw'}
    metadata = current['raw']['metadata']
    assert metadata['event_equivalence_review'] == stale.metadata['event_equivalence_review']
    assert 'publisher_exception_reason' not in metadata
    assert metadata.get('editorial_hold') == (old_hold if old_hold.startswith('possible_duplicate') else None)
    snapshot = copy.deepcopy(current)
    queue.discover('pulso_latercera', [fresh], now=NOW)
    assert queue.items[key] == snapshot
