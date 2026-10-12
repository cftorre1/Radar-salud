"""Cache admission regressions replay a retained original, then corrupt its proof."""
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_source import _verified_detail


REAL = Path(__file__).parent / 'fixtures/pulso_runtime_real'


@pytest.fixture
def retained_cache():
    manifest = json.loads((REAL / 'manifest.json').read_text())
    row = next(row for row in manifest['fixtures'] if '/horizontes/noticia/' in row['url'])
    packed = (REAL / row['path']).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == row['gzip_sha256']
    raw = gzip.decompress(packed)
    assert hashlib.sha256(raw).hexdigest() == row['sha256']
    html = raw.decode(row.get('charset', 'utf-8'))
    entry = dict(url=row['url'], listing='retained-original', lastmod='unchanged-publisher-token')
    cached = _verified_detail(entry, lambda _: html, None)
    cached['metadata']['captured_at'] = row['captured_at']
    cached['metadata'].pop('primary_identity_verified')
    cached['metadata'].pop('publication_date_verified')
    return entry, html, cached


def test_missing_legacy_flags_reuse_original_capture_without_claiming_a_new_fetch(retained_cache):
    entry, _, cached = retained_cache
    result = _verified_detail(entry, lambda _: pytest.fail('Verified original should be reusable'), cached)
    assert result['cache_hit']
    assert result['metadata']['primary_identity_verified'] is True
    assert result['metadata']['publication_date_verified'] is True
    for field in ('captured_at', 'html_sha256', 'article_body_sha256', 'publication_date', 'publication_evidence'):
        assert result['metadata'][field] == cached['metadata'][field]


@pytest.mark.parametrize('captured_at', [None, '', 'not-a-time', '2026-10-10',
                                      '2026-10-10T12:00:00', '2099-01-01T12:00:00Z'])
def test_missing_naive_invalid_or_future_capture_cannot_promote_legacy_proof(retained_cache, captured_at):
    entry, html, cached = retained_cache
    cached['metadata']['captured_at'] = captured_at
    calls = []
    result = _verified_detail(entry, lambda url: calls.append(url) or html, cached)
    assert calls == [entry['url']] and not result['cache_hit']
    assert result['metadata']['publication_date'] != '2099-01-01'


@pytest.mark.parametrize('timestamp', ['2099-01-01', '2099-01-01T12:00:00Z'])
def test_coherent_future_publication_cannot_bypass_original_date_validation(retained_cache, timestamp):
    entry, html, cached = retained_cache
    metadata = cached['metadata']
    metadata.update(publication_date='2099-01-01', publication_timestamp=timestamp,
                    visible_publication_date='2099-01-01', publisher_date_convention='calendar_agreement')
    for row in metadata['publication_evidence']:
        row.update(timestamp=timestamp, publisher_day='2099-01-01',
                   timestamp_calendar_day='2099-01-01', america_santiago_day='2099-01-01')
    calls = []
    result = _verified_detail(entry, lambda url: calls.append(url) or html, cached)
    assert calls == [entry['url']] and not result['cache_hit']
    assert result['metadata']['publication_date'] != '2099-01-01'
    assert result['metadata']['publication_date_verified'] is True


@pytest.mark.parametrize('url', ['https://www.latercera.com.evil.test/horizontes/noticia/clinica/',
                               'https://www.latercera.com/horizontes/noticia/clinica/extra/',
                               'https://www.latercera.com/opinion/noticia/clinica/'])
def test_legacy_verified_flags_cannot_authorize_an_unsupported_identity(retained_cache, url):
    entry, html, cached = retained_cache
    entry = dict(entry, url=url)
    cached = copy.deepcopy(cached)
    cached['url'] = cached['metadata']['canonical_url'] = url
    calls = []
    result = _verified_detail(entry, lambda value: calls.append(value) or html, cached)
    assert calls == [url] and result['status'] == 'detail_error'
    assert result['reason'] == 'unexpected_article_host_or_path'

