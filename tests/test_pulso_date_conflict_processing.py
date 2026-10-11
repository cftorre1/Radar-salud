"""Original date conflicts and explicit synthetic tampering preserve the boundary."""
import gzip
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing
from radar_salud.pulso_source import _verified_detail, verified_publication_date_conflict
from pulso_fixture_witnesses import cold_urls


URL = 'https://www.latercera.com/nacional/noticia/unit-primary-conflicting-dates/'
BODY = 'La clínica modificó prestaciones de su red y la atención hospitalaria. ' * 5
REAL = Path(__file__).parent / 'fixtures/pulso_editorial_exception_real'
CONFLICTS = [row for row in json.loads((REAL / 'manifest.json').read_text())['requests']
             if 'observed_primary_publication_date_conflict' in row['retention_categories']]


def conflict_raw():
    node = {'@type': 'NewsArticle', 'url': URL, 'headline': 'Cambios en atención hospitalaria',
            'datePublished': '2026-08-06T21:20:49.55Z', 'articleBody': BODY}
    html = (f'<link rel="canonical" href="{URL}">'
            f'<script type="application/ld+json">{json.dumps(node)}</script>'
            '<meta property="article:published_time" content="2026-08-06T21:20:49.55Z">'
            '<article><time class="article-body__byline__date">30 JULIO 2026</time></article>')
    result = _verified_detail({'url': URL, 'listing': 'unit-test'}, lambda _: html, None)
    assert verified_publication_date_conflict(result['metadata'])
    return RawItem('pulso_latercera', result['title'], URL, 'Pulso / La Tercera',
                   'press_high_trust', None, result['body'], result['metadata'])


def assert_conflict_deferred_without_analysis(raw, monkeypatch):
    raw.metadata.update(detected_at='2026-10-11T06:00:00Z', attempts=2, ingestion_mode='BACKFILL')
    before = deepcopy(raw.metadata)
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda *args: pytest.fail('Conflict must not be retried'))
    monkeypatch.setattr(beta_sources, '_material', lambda *args: pytest.fail('Conflicting dates cannot reach materiality'))
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Conflicting dates cannot consume AI'))
    monkeypatch.setattr(llm_analysis, '_client', lambda: pytest.fail('Conflicting dates cannot invoke Responses'))
    with pytest.raises(DeferredProcessing, match='^publisher_conflicting_publication_dates$'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.event_date is None
    assert raw.metadata['publication_date'] is None and raw.metadata['publication_timestamp'] is None
    assert raw.metadata['article_body_complete'] is True
    assert raw.metadata['publication_date_verified'] is False
    assert raw.metadata['source_quality_gate'] == 'deferred_publication_date'
    assert raw.metadata['editorial_assessment'] == {
        'decision': 'pending', 'reason': 'publisher_conflicting_publication_dates'}
    assert 'analysis_input_complete' not in raw.metadata
    for key in ('detected_at', 'attempts', 'ingestion_mode', 'canonical_url', 'visible_publication_date',
                'possible_publication_days', 'publication_evidence', 'page_text', 'article_body_sha256',
                'article_body_characters', 'html_sha256'):
        assert raw.metadata[key] == before[key]


def test_bound_synthetic_conflict_is_pending_before_fetch_materiality_or_ai(monkeypatch):
    assert_conflict_deferred_without_analysis(conflict_raw(), monkeypatch)


@pytest.mark.parametrize('entry', CONFLICTS, ids=lambda row: row['url'].split('/')[-2])
def test_all_original_conflicts_preserve_body_and_both_days_before_analysis(entry, monkeypatch):
    assert cold_urls('observed_primary_publication_date_conflict').issubset(row['url'] for row in CONFLICTS)
    assert entry['original_bytes_verified'] is True
    compressed = (REAL / entry['gzip_file']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == entry['gzip_sha256']
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
    result = _verified_detail({'url': entry['url'], 'listing': 'retained-real-original'},
                              lambda _: payload.decode(entry['charset']), None)
    metadata = result['metadata']
    assert verified_publication_date_conflict(metadata)
    assert metadata['html_sha256'] == entry['sha256']
    assert metadata['canonical_url'] == entry['canonical'] == entry['url']
    assert metadata['page_text'] == entry['full_primary_body']
    assert metadata['article_body_characters'] == entry['primary_body_chars']
    assert metadata['article_body_sha256'] == entry['primary_body_sha256']
    assert metadata['visible_publication_date'] == entry['visible_byline_day']
    assert len(metadata['possible_publication_days']) > 1
    assert [(row['source'], row['timestamp']) for row in metadata['publication_evidence']] == [
        (row['source'], row['timestamp']) for row in entry['publication_evidence']]
    raw = RawItem('pulso_latercera', result['title'], entry['url'], 'Pulso / La Tercera',
                   'press_high_trust', None, result['body'], metadata)
    assert_conflict_deferred_without_analysis(raw, monkeypatch)


@pytest.mark.parametrize('tamper', ['identity', 'body_hash', 'byline', 'evidence', 'raw_url', 'raw_date',
                                   'chosen_timestamp', 'article_verified'])
def test_unproven_conflict_flag_cannot_bypass_original_verification(tamper, monkeypatch):
    raw = conflict_raw()
    if tamper == 'identity':
        raw.metadata['primary_identity_verified'] = False
    elif tamper == 'body_hash':
        raw.metadata['article_body_sha256'] = '0' * 64
    elif tamper == 'byline':
        raw.metadata['visible_publication_date'] = '2026-08-06'
    elif tamper == 'evidence':
        raw.metadata['publication_evidence'] = []
    elif tamper == 'raw_url':
        raw.url = 'https://www.latercera.com/nacional/noticia/other/'
    elif tamper == 'raw_date':
        raw.event_date = '2026-07-30'
    elif tamper == 'chosen_timestamp':
        raw.metadata['publication_timestamp'] = '2026-08-06T21:20:49.55Z'
    else:
        raw.metadata['article_verified'] = True
    calls = []
    def unavailable(url):
        calls.append(url)
        raise OSError('Original unavailable')
    monkeypatch.setattr(beta_sources, 'fetch_html', unavailable)
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Unverified conflict cannot consume AI'))
    with pytest.raises(DeferredProcessing, match='Pulso article verification failed'):
        beta_sources.process_curated_beta_source(raw, {})
    assert calls == [raw.url]
    assert raw.metadata['editorial_assessment']['reason'] == 'article_verification_failed'
