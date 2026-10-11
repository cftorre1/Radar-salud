"""Explicit synthetic conflicts test the processor boundary, without inventing originals."""
import json
from copy import deepcopy

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing
from radar_salud.pulso_source import _verified_detail, verified_publication_date_conflict


URL = 'https://www.latercera.com/nacional/noticia/unit-primary-conflicting-dates/'
BODY = 'La clínica modificó prestaciones de su red y la atención hospitalaria. ' * 5


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


def test_bound_primary_conflict_is_pending_before_fetch_materiality_or_ai(monkeypatch):
    raw = conflict_raw()
    raw.metadata.update(detected_at='2026-10-11T06:00:00Z', attempts=2, ingestion_mode='BACKFILL')
    before = deepcopy(raw.metadata)
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda *args: pytest.fail('Conflict must not be retried'))
    monkeypatch.setattr(beta_sources, '_material', lambda *args: pytest.fail('Conflicting dates cannot reach materiality'))
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Conflicting dates cannot consume AI'))
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


@pytest.mark.parametrize('tamper', ['identity', 'body_hash', 'byline', 'evidence', 'raw_url', 'raw_date'])
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
    else:
        raw.event_date = '2026-07-30'
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
