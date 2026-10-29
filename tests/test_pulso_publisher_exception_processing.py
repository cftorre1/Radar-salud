"""Real primary taxonomy survives source registration and older queue records."""
import gzip
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing
from radar_salud.pulso_source import (_verified_detail, article_body_evidence,
                                    publisher_taxonomy_requires_revalidation,
                                    verified_sponsored_content)
from pulso_fixture_witnesses import cold_urls
from pulso_editorial_test_support import valid_assessment
from pulso_editorial_real_test_witnesses import real_witness


REAL = Path(__file__).parent / 'fixtures/pulso_editorial_exception_real'
ENTRIES = json.loads((REAL / 'manifest.json').read_text())['requests']
SPONSORS = [row for row in ENTRIES if 'explicit_commercial_publisher_section' in row['retention_categories']]
OPINIONS = [row for row in ENTRIES if 'explicit_opinion_or_column_keyword_under_article_path' in row['retention_categories']]


def original(entry, root=REAL):
    compressed = (root / entry['gzip_file']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == entry['gzip_sha256']
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
    return payload.decode(entry['charset'])


def unavailable_analysis(monkeypatch):
    monkeypatch.setattr(beta_sources, '_material', lambda *args: pytest.fail('Publisher exclusion must precede materiality'))
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Publisher exclusion must precede AI'))
    monkeypatch.setattr(llm_analysis, '_client', lambda: pytest.fail('Publisher exclusion must precede Responses'))


def raw_from_source(entry):
    result = _verified_detail({'url': entry['url'], 'listing': 'retained-real-original'},
                              lambda _: original(entry), None)
    metadata = result['metadata']
    return RawItem('pulso_latercera', result['title'], entry['url'], 'Pulso / La Tercera',
                   'press_high_trust', metadata['publication_date'], result['body'], metadata)


@pytest.mark.parametrize('entry', SPONSORS, ids=lambda row: row['url'].split('/')[-2])
def test_all_original_commercial_pages_hold_without_ai_and_date_conflict_has_priority(entry, monkeypatch):
    assert cold_urls('explicit_commercial_publisher_section').issubset(row['url'] for row in SPONSORS)
    raw = raw_from_source(entry)
    before = deepcopy(raw.metadata)
    conflict = 'observed_primary_publication_date_conflict' in entry['retention_categories']
    expected = 'publisher_conflicting_publication_dates' if conflict else 'publisher_sponsored_content_review_required'
    assert raw.metadata['publisher_content_classification'] == 'sponsored'
    assert verified_sponsored_content(raw.metadata) is (not conflict)
    assert raw.metadata['article_body_sha256'] == entry['primary_body_sha256']
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda *args: pytest.fail('Verified commercial hold must not refetch'))
    unavailable_analysis(monkeypatch)
    with pytest.raises(DeferredProcessing, match='^' + expected + '$'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.metadata['editorial_assessment'] == {'decision': 'pending', 'reason': expected}
    assert raw.metadata['article_body_complete'] is True
    assert raw.metadata['publisher_taxonomy'] == before['publisher_taxonomy']
    assert raw.metadata['article_body_sha256'] == before['article_body_sha256']
    assert raw.event_date == before['publication_date']
    if conflict:
        assert raw.event_date is None and raw.metadata['publication_timestamp'] is None
    assert 'analysis_input_complete' not in raw.metadata


@pytest.mark.parametrize('entry', SPONSORS + OPINIONS, ids=lambda row: row['url'].split('/')[-2])
def test_all_legacy_nonfactual_records_revalidate_original_and_preserve_exact_disposition(entry, monkeypatch):
    assert cold_urls('explicit_commercial_publisher_section').issubset(row['url'] for row in SPONSORS)
    assert cold_urls('explicit_opinion_or_column_keyword_under_article_path').issubset(row['url'] for row in OPINIONS)
    metadata = dict(article_verified=True, market_role='media', canonical_url=entry['url'],
                    publication_date=entry['visible_byline_day'], section=entry['section'],
                    keywords=entry['keywords'], source_quality_gate='passed',
                    detected_at='2026-10-11T06:00:00Z', attempts=2, ingestion_mode='BACKFILL',
                    **article_body_evidence(entry['full_primary_body']))
    assert publisher_taxonomy_requires_revalidation(metadata)
    raw = RawItem('pulso_latercera', entry['title'], entry['url'], 'Pulso / La Tercera',
                   'press_high_trust', metadata['publication_date'], entry['full_primary_body'][:1800], metadata)
    calls = []
    def fetch(url):
        calls.append(url)
        return original(entry)
    monkeypatch.setattr(beta_sources, 'fetch_html', fetch)
    unavailable_analysis(monkeypatch)
    if entry in OPINIONS:
        assert beta_sources.process_curated_beta_source(raw, {}) is None
        assert raw.metadata['editorial_assessment'] == {'decision': 'rejected', 'reason': 'publisher_opinion_taxonomy'}
        assert raw.metadata['rejection_reason'] == 'publisher_opinion_taxonomy'
        assert raw.metadata['publisher_content_classification'] == 'opinion'
    else:
        conflict = 'observed_primary_publication_date_conflict' in entry['retention_categories']
        expected = 'publisher_conflicting_publication_dates' if conflict else 'publisher_sponsored_content_review_required'
        with pytest.raises(DeferredProcessing, match='^' + expected + '$'):
            beta_sources.process_curated_beta_source(raw, {})
        assert raw.metadata['editorial_assessment'] == {'decision': 'pending', 'reason': expected}
        if conflict:
            assert raw.event_date is None and raw.metadata['publication_timestamp'] is None
    assert calls == [entry['url']]
    assert raw.metadata['article_body_sha256'] == entry['primary_body_sha256']
    from radar_salud.source_rights import is_paywalled, redacted_body_verified
    if is_paywalled(entry['url']):
        # Premium section: only the lead remains; the receipt proves the same body (Dirección 28-oct-2026).
        assert redacted_body_verified(raw.metadata) and raw.metadata['page_text'] == raw.metadata['public_teaser']
    else:
        assert raw.metadata['page_text'] == entry['full_primary_body']
    assert raw.metadata['html_sha256'] == entry['sha256']
    assert raw.metadata['primary_identity_verified'] is True
    assert raw.metadata['detected_at'] == '2026-10-11T06:00:00Z'
    assert raw.metadata['attempts'] == 2 and raw.metadata['ingestion_mode'] == 'BACKFILL'
    assert 'analysis_input_complete' not in raw.metadata


@pytest.mark.parametrize('tamper', ['identity', 'body_hash', 'taxonomy', 'raw_url', 'raw_date'])
def test_unproven_commercial_flags_force_original_before_any_publisher_hold(tamper, monkeypatch):
    entry = next(row for row in SPONSORS if 'observed_primary_publication_date_conflict' not in row['retention_categories'])
    raw = raw_from_source(entry)
    if tamper == 'identity':
        raw.metadata['primary_identity_verified'] = False
    elif tamper == 'body_hash':
        raw.metadata['article_body_sha256'] = '0' * 64
    elif tamper == 'taxonomy':
        raw.metadata['publisher_taxonomy']['section'] = 'Nacional'
    elif tamper == 'raw_url':
        raw.url = 'https://www.latercera.com/branded/noticia/other/'
    else:
        raw.event_date = '2026-10-01'
    calls = []
    def missing(url):
        calls.append(url)
        raise OSError('Original unavailable')
    monkeypatch.setattr(beta_sources, 'fetch_html', missing)
    unavailable_analysis(monkeypatch)
    with pytest.raises(DeferredProcessing, match='Pulso article verification failed'):
        beta_sources.process_curated_beta_source(raw, {})
    assert calls == [raw.url]
    assert raw.metadata['editorial_assessment']['reason'] == 'article_verification_failed'


def test_untrusted_legacy_opinion_label_is_replaced_by_original_factual_taxonomy(monkeypatch):
    root = Path(__file__).parent / 'fixtures/pulso_targeted_primary_real'
    entry = next(row for row in json.loads((root / 'manifest.json').read_text())['requests']
                 if 'kast-anuncia-uso-de-inteligencia-artificial' in row['url'])
    source = _verified_detail({'url': entry['url'], 'listing': 'retained-real-original'},
                              lambda _: original(entry, root), None)
    metadata = source['metadata']
    assert metadata['publisher_content_classification'] == 'factual'
    metadata.pop('publisher_taxonomy')
    metadata['keywords'] = ['Opinión']
    metadata['article_body_complete'] = True
    metadata['publisher_exception_reason'] = 'publisher_sponsored_content_review_required'
    metadata['editorial_hold'] = 'publisher_sponsored_content_review_required'
    assert publisher_taxonomy_requires_revalidation(metadata)
    raw = RawItem('pulso_latercera', source['title'], entry['url'], 'Pulso / La Tercera',
                   'press_high_trust', metadata['publication_date'], source['body'], metadata)
    calls, assessed = [], []
    def fetch(url):
        calls.append(url)
        return original(entry, root)
    def assess(**kwargs):
        assessed.append(kwargs)
        return valid_assessment({'relevance_score': 71, 'reason': 'Bajo el umbral editorial vigente.',
                'what_happened': '', 'why_it_matters': ''},
                kwargs, witness=real_witness(kwargs))
    monkeypatch.setattr(beta_sources, 'fetch_html', fetch)
    monkeypatch.setattr(llm_analysis, 'analyze_news', assess)
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert calls == [entry['url']] and len(assessed) == 1
    assert raw.metadata['publisher_content_classification'] == 'factual'
    assert 'Opinión' not in raw.metadata['keywords']
    assert 'publisher_exception_reason' not in raw.metadata and 'editorial_hold' not in raw.metadata
    assert raw.metadata['rejection_reason'] == 'editorial_relevance_below_threshold'
    assert raw.metadata['editorial_assessment']['threshold'] == 72
    assert assessed[0]['text'] == raw.metadata['page_text'] and assessed[0]['full_text']
