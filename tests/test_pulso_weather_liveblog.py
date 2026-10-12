"""All 336 real historical weather updates retain strict entry-level proof."""
import gzip
import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing
from radar_salud.pulso_source import (
    _verified_detail, article_body_evidence, complete_article_body, extract_article,
    liveblog_analysis_text, verified_liveblog_temporal_evidence,
)

FIXTURE_ROOT = Path(__file__).parent / 'fixtures'
WITNESS = json.loads((FIXTURE_ROOT / 'pulso_weather_liveblog_witness.json').read_text())
ROWS = WITNESS['fixtures']


def original(row):
    packed = (FIXTURE_ROOT / WITNESS['fixture_directory'] / row['gzip_file']).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == row['gzip_sha256']
    payload = gzip.decompress(packed)
    assert len(payload) == row['bytes']
    assert hashlib.sha256(payload).hexdigest() == row['sha256']
    return payload.decode(row['charset'])


def primary(row, html=None):
    title, body, metadata = extract_article(html or original(row), row['url'])
    metadata.update(article_body_evidence(body), captured_at=row['captured_at'],
                    market_role='media', source_quality_gate='passed')
    return RawItem('pulso_latercera', title, row['url'], 'Pulso / La Tercera',
                   'press_high_trust', metadata['publication_date'], body[:1800], metadata)


def publisher_node(html):
    # Independent enumeration directly from the original JSON, without using
    # the source's entry parser or its projected proof as the denominator.
    for match in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        node = json.loads(match[1])
        if node.get('@type') == 'LiveBlogPosting':
            return node
    pytest.fail('Original publisher LiveBlogPosting absent')


@pytest.mark.parametrize('row', ROWS, ids=lambda row: row['document_publication_date'])
def test_all_336_original_updates_match_dates_headlines_bodies_and_unchanged_document(row):
    html = original(row)
    raw = primary(row)
    meta = raw.metadata
    assert verified_liveblog_temporal_evidence(meta)
    assert meta['html_sha256'] == row['sha256'] != row['prior_process_html_sha256']
    assert meta['captured_at'] == row['captured_at']
    assert meta['article_body_characters'] == row['baseline_article_body_characters']
    assert meta['article_body_sha256'] == row['baseline_article_body_sha256']
    assert raw.event_date == row['document_publication_date']
    assert meta['publication_date_verified'] is True
    node = publisher_node(html)
    proof = meta['liveblog_temporal_evidence']
    assert proof['errors'] == []
    assert proof['document_publication_timestamp'] == row['document_publication_timestamp'] == node['datePublished']
    assert proof['document_modified_timestamp'] == row['document_modified_timestamp'] == node['dateModified']
    assert len(proof['entries']) == row['entry_count'] == len(node['liveBlogUpdate'])
    for projected, publisher in zip(proof['entries'], node['liveBlogUpdate']):
        assert projected['url'] == publisher['url']
        assert projected['timestamp'] == projected['html_datetime'] == publisher['datePublished']
        stamp = datetime.fromisoformat(publisher['datePublished'].replace('Z', '+00:00'))
        assert projected['publisher_day'] == stamp.astimezone(ZoneInfo('America/Santiago')).date().isoformat()
        assert projected['headline'] == publisher['headline']
        assert projected['body'] == publisher['articleBody']
        assert projected['body_sha256'] == hashlib.sha256(publisher['articleBody'].encode()).hexdigest()
    # These documents span midnight. Publication cannot replace entry dates.
    assert any(entry['publisher_day'] != raw.event_date for entry in proof['entries'])


def test_real_second_h3_is_subsection_not_another_entry_headline_or_discarded_primary_text():
    raw = primary(ROWS[0])
    entry = raw.metadata['liveblog_temporal_evidence']['entries'][45]
    assert entry['headline'] == '4% del país está sin suministro eléctrico'
    assert entry['url'].endswith('#lbp-PVHX5FYQ75DZFDFL43CL4FZLSU')
    assert '324.915' in entry['body'] and 'Carlos Gaete' in entry['body']
    assert 'Armada de Chile aborda próximo sistema frontal en la zona central' in raw.metadata['page_text']
    assert entry['html_body_corroboration'] == 'primary_entry_paragraphs'


@pytest.mark.parametrize('row', ROWS)
def test_complete_model_payload_contains_all_entries_and_the_entire_unmodified_base(row):
    raw = primary(row)
    payload = liveblog_analysis_text(raw.metadata)
    assert raw.metadata['page_text'] in payload
    for entry in raw.metadata['liveblog_temporal_evidence']['entries']:
        assert f"ENTRADA {entry['index']} | {entry['url']}" in payload
        assert entry['timestamp'] in payload and f"fecha visible: {entry['publisher_day']}" in payload
        assert entry['body'] in payload
    request = llm_analysis.news_analysis_input(title=raw.title, text=payload,
                                             source_name=raw.source_name, full_text=True)
    assert request.split('Contenido:\n', 1)[1] == payload
    assert len(payload) > row['baseline_article_body_characters'] > 18000


@pytest.mark.parametrize('row', ROWS)
def test_observed_invalid_timeline_cache_refetches_new_primary_bytes_instead_of_relabelling_old_capture(row):
    raw = primary(row)
    stale = deepcopy(raw.metadata)
    stale.update(html_sha256=row['prior_process_html_sha256'],
                 liveblog_temporal_evidence_verified=False, captured_at='2026-10-11T12:58:30+00:00')
    stale['liveblog_temporal_evidence'].update(verified=False, entries=[],
        original_html_sha256=row['prior_process_html_sha256'],
        errors=[dict(index=0, reason='liveblog_entry_headline_mismatch')])
    assert not verified_liveblog_temporal_evidence(stale)
    lastmod = row['document_modified_timestamp']
    cached = dict(url=raw.url, title=raw.title, body=raw.raw_text, metadata=stale, relevant=True, lastmod=lastmod)
    listing = dict(url=raw.url, listing='official_sitemap', lastmod=lastmod)
    calls = []
    fresh = _verified_detail(listing, lambda url: calls.append(url) or original(row), cached)
    assert calls == [raw.url] and fresh['cache_hit'] is False
    assert verified_liveblog_temporal_evidence(fresh['metadata'])
    assert fresh['metadata']['html_sha256'] == row['sha256']
    assert fresh['metadata']['article_body_sha256'] == row['baseline_article_body_sha256']
    assert fresh['metadata']['captured_at'] != stale['captured_at']
    warm = _verified_detail(listing, lambda _: pytest.fail('Verified timeline needs no repeated fetch'), fresh)
    assert warm['cache_hit'] and warm['metadata']['captured_at'] == fresh['metadata']['captured_at']


@pytest.mark.parametrize('row', ROWS)
@pytest.mark.parametrize('mutation', ['headline', 'datetime', 'body'])
def test_original_h3_does_not_relax_headline_time_or_body_binding_and_unverified_updates_never_reach_ai(row, mutation, monkeypatch):
    html = original(row)
    first = publisher_node(html)['liveBlogUpdate'][0]
    if mutation == 'headline':
        # Adversarial mutation only: original JSON remains unchanged.
        headline = re.search(r'(<h[123][^>]*>)(.*?)(</h[123]>)', html[html.index('class="liveblog-entry"'):], re.S)
        assert headline is not None
        html = html.replace(headline[0], headline[1] + 'Invented clinical action' + headline[3], 1)
    elif mutation == 'datetime':
        needle = f'dateTime="{first["datePublished"]}"'
        assert needle in html
        html = html.replace(needle, 'dateTime="2026-07-20T12:00:00Z"', 1)
    else:
        match = next(m for m in re.finditer(r'(<script[^>]+type="application/ld\+json"[^>]*>)(.*?)(</script>)', html, re.S)
                     if json.loads(m[2]).get('@type') == 'LiveBlogPosting')
        node = json.loads(match[2])
        node['liveBlogUpdate'][0]['articleBody'] += ' Invented clinical closure.'
        html = html[:match.start(2)] + json.dumps(node, ensure_ascii=False, separators=(',', ':')) + html[match.end(2):]
    raw = primary(row, html)
    assert not verified_liveblog_temporal_evidence(raw.metadata)
    assert raw.event_date == row['document_publication_date']
    assert raw.metadata['publication_date_verified'] is True
    assert complete_article_body(raw.metadata)
    reasons = [error['reason'] for error in raw.metadata['liveblog_temporal_evidence']['errors'] if isinstance(error, dict)]
    expected = {'headline': 'liveblog_entry_headline_mismatch',
                'datetime': 'liveblog_entry_timestamp_uncorroborated', 'body': 'liveblog_entry_body_mismatch'}
    assert expected[mutation] in reasons
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda _: html)
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **_: pytest.fail('Invalid entry cannot reach AI'))
    with pytest.raises(DeferredProcessing, match='publisher_liveblog_entry_dates_unverified'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.metadata['article_body_complete'] is True
    assert raw.metadata['editorial_assessment']['reason'] == 'publisher_liveblog_entry_dates_unverified'
    assert 'analysis_input_complete' not in raw.metadata


def test_weather_witness_is_all_diagnostic_entries_not_a_frozen_control_change():
    assert Counter(row['entry_count'] for row in ROWS) == {90: 1, 170: 1, 76: 1}
    assert sum(row['entry_count'] for row in ROWS) == 336
    assert sum(row['prior_headline_mismatch_count'] for row in ROWS) == 299
    assert all(row['prior_process_run_id'] == 38141096276 for row in ROWS)
