"""Replay every retained exception original, validating immutable response bytes."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_source import (ConflictingPublicationArticle, TextUnavailableArticle,
                                    _verified_detail, extract_article,
                                    verified_publication_date_conflict, verified_video_without_text,
                                    ExcludedArticle, SponsoredArticle, verified_sponsored_content,
                                    publisher_taxonomy_requires_revalidation)
from pulso_fixture_witnesses import COLD_RECORDS, assert_cold_witnesses, cold_urls

REAL = Path(__file__).parent / 'fixtures/pulso_editorial_exception_real'
MANIFEST = json.loads((REAL / 'manifest.json').read_text())
CONFLICTS = [row for row in MANIFEST['requests']
             if 'observed_primary_publication_date_conflict' in row['retention_categories']]
VIDEO_OBJECTS = [row for row in MANIFEST['requests']
                 if 'url_bound_primary_video_object' in row['retention_categories']]
OPINIONS = [row for row in MANIFEST['requests']
            if 'explicit_opinion_or_column_keyword_under_article_path' in row['retention_categories']]
COMMERCIAL = [row for row in MANIFEST['requests']
              if 'explicit_commercial_publisher_section' in row['retention_categories']]


def original(row):
    compressed = (REAL / row['gzip_file']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == row['gzip_sha256']
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == row['sha256']
    assert len(payload) == row['bytes']
    return payload.decode(row['charset'])


def commercial_health_urls():
    """A commercial taxonomy alone does not make a primary article about health."""
    from scripts.audit_pulso_primary_corpus import primary_projection
    from radar_salud.pulso_source import health_anchor
    relevant = set()
    for row in COMMERCIAL:
        projection = primary_projection(original(row), row['url'])
        assert projection['canonical_matches_requested']
        assert projection['primary_body_sha256'] == row['primary_body_sha256']
        combined = (projection['title'] + ' ' + projection['full_primary_body']
                    + ' ' + str(projection['keywords']))
        if health_anchor(combined):
            relevant.add(row['url'])
    # The four independently reviewed cold health witnesses cannot disappear
    # when unrelated commercial originals, such as Ballerinas, are retained.
    assert cold_urls('explicit_commercial_publisher_section').issubset(relevant)
    return relevant


def test_all_cold_original_witnesses_remain_in_the_expanding_retained_inventory():
    assert_cold_witnesses(MANIFEST['requests'])
    assert len(COLD_RECORDS) == 58
    for category, expected_count in (
            ('observed_primary_publication_date_conflict', 4),
            ('url_bound_primary_video_object', 44),
            ('explicit_opinion_or_column_keyword_under_article_path', 8),
            ('explicit_commercial_publisher_section', 4)):
        assert len(cold_urls(category)) == expected_count
    assert sum('/videos/' in url for url in cold_urls('url_bound_primary_video_object')) == 21


@pytest.mark.parametrize('row', CONFLICTS, ids=lambda row: row['url'].split('/')[-2])
def test_every_actual_publisher_date_conflict_stays_unresolved_with_complete_primary_body(row):
    html = original(row)
    with pytest.raises(ConflictingPublicationArticle, match='^conflicting_publication_dates$') as raised:
        extract_article(html, row['url'])
    metadata = raised.value.metadata
    assert metadata['publication_date'] is metadata['publication_timestamp'] is None
    assert metadata['visible_publication_date'] == row['visible_byline_day']
    assert metadata['primary_identity_verified'] and not metadata['publication_date_verified']
    assert metadata['canonical_url'] == row['canonical'] == row['url']
    assert hashlib.sha256(raised.value.body.encode()).hexdigest() == row['primary_body_sha256']
    assert len(raised.value.body) == row['primary_body_chars'] >= 160
    result = _verified_detail(dict(url=row['url'], listing='retained-original', lastmod='actual-original'),
                              lambda _: html, None)
    assert verified_publication_date_conflict(result['metadata'])
    assert result['deferred_reason'] == 'publisher_conflicting_publication_dates'
    assert result['metadata']['html_sha256'] == row['sha256']
    assert [entry['timestamp'] for entry in result['metadata']['publication_evidence']] == [
        entry['timestamp'] for entry in row['publication_evidence']]


@pytest.mark.parametrize('row', VIDEO_OBJECTS, ids=lambda row: row['url'].split('/')[-2])
def test_every_original_video_object_distinguishes_embedded_video_from_missing_transcript(row):
    html = original(row)
    result = _verified_detail(dict(url=row['url'], listing='retained-original'), lambda _: html, None)
    assert 'status' not in result
    metadata = result['metadata']
    assert metadata['canonical_url'] == row['url'] and metadata['html_sha256'] == row['sha256']
    if row['visible_byline_day']:
        assert metadata['publication_date'] == row['visible_byline_day']
    else:
        # Retained live blogs have no visible time byline or bound Article
        # node; their own canonical-page publication metadata dates the HTML.
        assert row['url_bound_article_nodes'] == 0
        assert metadata['publication_date'] == row['publication_evidence'][0]['timestamp'][:10]
        assert metadata['publication_date_source'] == 'article_published_time'
    missing_transcript = (row['primary_body_chars'] < 160
                          or row['primary_body_source'] != 'url_bound_json_ld_articleBody')
    if '/videos/' in row['url'] and missing_transcript:
        assert result['deferred_reason'] == 'publisher_video_text_unavailable'
        assert verified_video_without_text(metadata)
        assert not metadata['article_verified'] and not metadata['article_body_complete']
        assert len(metadata['page_text']) < 160
    else:
        if row['section'] == 'Branded':
            assert result['deferred_reason'] == 'publisher_sponsored_content_review_required'
            assert verified_sponsored_content(metadata)
        else:
            assert not result.get('deferred_reason')
        assert metadata['article_verified'] and metadata['article_body_characters'] >= 160
        assert metadata['article_body_sha256'] == row['primary_body_sha256']
        if result['relevant']:
            assert len(metadata['page_text']) >= 160


def test_actual_alzheimer_original_does_not_upgrade_eighty_four_characters_with_metadata_wrapper():
    row = next(row for row in VIDEO_OBJECTS if '/radar-lt-descubren-doble-avance-' in row['url'])
    assert row['primary_body_chars'] == 84
    with pytest.raises(TextUnavailableArticle) as raised:
        extract_article(original(row), row['url'])
    assert len(raised.value.body) == 84
    assert hashlib.sha256(raised.value.body.encode()).hexdigest() == row['primary_body_sha256']
    assert raised.value.metadata['article_body_complete'] is False
    assert raised.value.metadata['body_source'] == 'url_bound_json_ld_articleBody'


@pytest.mark.parametrize('row', OPINIONS, ids=lambda row: row['url'].split('/')[-2])
def test_all_eight_original_opinions_are_excluded_by_bound_publisher_taxonomy(row):
    html = original(row)
    with pytest.raises(ExcludedArticle, match='^publisher_opinion_taxonomy$') as raised:
        extract_article(html, row['url'])
    taxonomy = raised.value.metadata['publisher_taxonomy']
    assert taxonomy['source'] == 'url_bound_json_ld' and taxonomy['canonical_url'] == row['url']
    assert taxonomy['classification'] == 'opinion' and taxonomy['labels'] == row['keywords']
    assert taxonomy['matched_opinion_labels']
    assert raised.value.metadata['publication_date'] == row['visible_byline_day']
    assert hashlib.sha256(raised.value.body.encode()).hexdigest() == row['primary_body_sha256']
    result = _verified_detail(dict(url=row['url'], listing='original', lastmod='unchanged'), lambda _: html, None)
    assert result['exclusion_reason'] == 'publisher_opinion_taxonomy' and not result['relevant']
    assert result['metadata']['html_sha256'] == row['sha256']
    assert not publisher_taxonomy_requires_revalidation(result['metadata'])


@pytest.mark.parametrize('row', COMMERCIAL, ids=lambda row: row['url'].split('/')[-2])
def test_all_four_original_commercial_pages_preserve_provenance_and_exact_review_hold(row):
    html = original(row)
    error = ConflictingPublicationArticle if row in CONFLICTS else SponsoredArticle
    with pytest.raises(error):
        extract_article(html, row['url'])
    result = _verified_detail(dict(url=row['url'], listing='original'), lambda _: html, None)
    metadata = result['metadata']
    assert metadata['publisher_content_classification'] == 'sponsored'
    assert metadata['publisher_taxonomy']['classification'] == 'sponsored'
    assert metadata['publisher_taxonomy']['section'] == row['section']
    assert metadata['publisher_taxonomy']['canonical_url'] == row['url']
    assert hashlib.sha256(metadata['page_text'].encode()).hexdigest() == row['primary_body_sha256']
    if row in CONFLICTS:
        assert result['deferred_reason'] == 'publisher_conflicting_publication_dates'
        assert verified_publication_date_conflict(metadata) and not verified_sponsored_content(metadata)
        assert metadata['publication_date'] is None
    else:
        assert result['deferred_reason'] == 'publisher_sponsored_content_review_required'
        assert verified_sponsored_content(metadata)
        assert metadata['source_quality_gate'] == 'deferred_sponsored_content_review'
        assert metadata['publication_date'] == row['visible_byline_day']


def test_legacy_factual_opinion_and_commercial_cache_requires_real_primary_reclassification():
    import copy
    for row in OPINIONS + [value for value in COMMERCIAL if value not in CONFLICTS]:
        entry = dict(url=row['url'], listing='original', lastmod='unchanged')
        html, calls = original(row), []
        cold = _verified_detail(entry, lambda _: html, None)
        legacy = copy.deepcopy(cold)
        legacy['metadata'].pop('publisher_taxonomy')
        legacy['metadata'].pop('publisher_content_classification')
        legacy['metadata']['article_verified'] = True
        legacy.pop('deferred_reason', None)
        legacy.pop('exclusion_reason', None)
        assert publisher_taxonomy_requires_revalidation(legacy['metadata'])
        def loader(url):
            calls.append(url)
            return html
        refreshed = _verified_detail(entry, loader, legacy)
        assert calls == [row['url']] and not refreshed['cache_hit']
        assert refreshed.get('deferred_reason') or refreshed.get('exclusion_reason')


def test_words_in_body_or_related_article_taxonomy_do_not_classify_primary_factual_news():
    from test_pulso_date_exceptions import article, URL
    html = article(timestamp='2026-10-09T12:00:00Z', byline='9 OCTUBRE 2026')
    html = html.replace('La clínica', 'Una columna editorial cita la opinión de un doctor. La clínica')
    related = {'@type': 'NewsArticle', 'url': URL.replace('corazon-atencion', 'related'), 'keywords': ['Opinión']}
    html += '<script type="application/ld+json">' + json.dumps(related) + '</script>'
    assert extract_article(html, URL)[2]['publisher_content_classification'] == 'factual'


def test_commercial_provenance_flags_cannot_bypass_primary_identity_dates_and_body():
    import copy
    row = next(value for value in COMMERCIAL if value not in CONFLICTS)
    metadata = _verified_detail(dict(url=row['url'], listing='original'), lambda _: original(row), None)['metadata']
    for change in ({'primary_identity_verified': False}, {'publication_date_verified': False},
                   {'article_verified': False}, {'article_body_complete': False}, {'page_text': ''},
                   {'section': 'Pulso'}, {'canonical_url': row['url'].replace('/branded/', '/nacional/')},
                   {'publisher_exception_reason': 'unknown'}, {'publication_evidence': []}):
        assert not verified_sponsored_content(dict(metadata, **change))
    tampered = copy.deepcopy(metadata)
    tampered['publisher_taxonomy']['article_type'] = 'RelatedArticle'
    assert not verified_sponsored_content(tampered)


def test_real_taxonomy_inventory_excludes_opinions_and_holds_commercial_pages_without_claiming_factual_health(tmp_path):
    from datetime import date
    from radar_salud.pulso_source import discover_public_feeds
    rows = OPINIONS + COMMERCIAL
    by_url = {row['url']: row for row in rows}
    opened = []
    def loader(url):
        if '/canal/' in url:
            return ''
        if '/pf/api/' in url:
            elements = [dict(_id=str(i), websites={'la-tercera': {'website_url': row['url']}},
                             first_publish_date=row['publication_evidence'][0]['timestamp'],
                             last_updated_date='retained-original-token') for i, row in enumerate(rows)]
            return json.dumps(dict(content_elements=elements, count=len(rows), next=None))
        opened.append(url)
        return original(by_url[url])
    audit = []
    health_commercial = commercial_health_urls()
    expected = {row['url'] for row in COMMERCIAL
                if row['url'] in health_commercial or row in CONFLICTS}
    candidates, coverage = discover_public_feeds(loader, audit, tmp_path/'cache.json',
                                                today=date(2026, 10, 11), feeds=[('tag', 'salud')])
    assert len(opened) == len(set(opened)) == len(by_url)
    assert {raw.url for raw in candidates} == expected
    assert len(candidates) == coverage['new_inventory_urls'] == len(expected) and coverage['new_health_urls'] == 0
    assert coverage['metadata_only_sponsored_candidates'] == sum(
        row['url'] in expected and row not in CONFLICTS for row in COMMERCIAL)
    assert coverage['metadata_only_date_conflict_candidates'] == sum(row in CONFLICTS for row in COMMERCIAL)
    assert coverage['coverage_complete'] and not coverage['publication_date_coverage_complete']
    assert not any(row['status'] in ('detail_error', 'listing_error') for row in audit)
    traces = {row['url']: row for row in audit if row.get('url') in by_url}
    for row in OPINIONS:
        trace = traces[row['url']]
        assert trace['status'] == 'excluded' and trace['reason'] == 'publisher_opinion_taxonomy'
        assert trace['publisher_taxonomy']['classification'] == 'opinion'
        assert trace['html_sha256'] == row['sha256'] and trace['publication_date'] == row['visible_byline_day']
    for row in COMMERCIAL:
        trace = traces[row['url']]
        if row['url'] in expected:
            assert trace['status'] == 'discovered_metadata_only'
        else:
            assert trace['status'] == 'excluded' and trace['reason'] == 'no_health_anchor'
        assert trace['publisher_content_classification'] == 'sponsored'
        assert trace['publisher_taxonomy']['canonical_url'] == row['url']
        assert trace['html_sha256'] == row['sha256']
    opened.clear()
    warm_candidates, _ = discover_public_feeds(loader, [], tmp_path/'cache.json',
                                               today=date(2026, 10, 11), feeds=[('tag', 'salud')])
    assert not opened and {raw.url for raw in warm_candidates} == {raw.url for raw in candidates}


LISTING_CASES = [
    next(row for row in VIDEO_OBJECTS if '/horizontes/' in row['url']),
    next(row for row in VIDEO_OBJECTS if '/radar-lt-descubren-doble-avance-' in row['url']),
    next(row for row in COMMERCIAL if '/publirreportajes/' in row['url']),
    next(row for row in CONFLICTS if '/el-trabajo-tambien-' in row['url']),
    next(row for row in OPINIONS if '/lo-dijimos/' in row['url']),
]


@pytest.mark.parametrize('row', LISTING_CASES, ids=lambda row: row['url'].split('/')[-2])
def test_listing_only_candidates_keep_the_complete_original_trace_contract(row):
    from radar_salud.pulso_source import discover_listing
    audit, opened = [], []
    def loader(url):
        opened.append(url)
        return original(row)
    # This inventory is synthetic; every primary response is exact retained HTML.
    candidates = discover_listing(f'<a href="{row["url"]}">Información general</a>',
                                  'https://www.latercera.com/canal/pulso/', loader, audit, set())
    assert opened == [row['url']] and len(audit) == 1
    trace = audit[0]
    assert trace['canonical_url'] == row['url']
    assert trace['html_sha256'] == row['sha256'] and trace['captured_at']
    assert trace['publication_date_source'] and trace['publication_evidence']
    assert trace['visible_publication_date'] == row['visible_byline_day']
    assert trace['primary_identity_verified'] is True
    assert trace['article_body_characters'] == row['primary_body_chars']
    assert trace['article_body_sha256'] == row['primary_body_sha256']
    assert trace['cache_hit'] is False
    assert trace['publisher_taxonomy']['canonical_url'] == row['url']
    if row in CONFLICTS:
        assert trace['publication_date'] is trace['publication_timestamp'] is None
        assert trace['publication_date_verified'] is trace['article_verified'] is False
        assert trace['publisher_exception_reason'] == 'publisher_conflicting_publication_dates'
    else:
        assert trace['publication_date'] == row['visible_byline_day']
        assert trace['publication_date_verified'] is True
        assert trace['publication_timestamp'] == row['publication_evidence'][0]['timestamp']
    if row in OPINIONS:
        assert candidates == [] and trace['status'] == 'excluded'
        assert trace['reason'] == 'publisher_opinion_taxonomy'
    elif row in COMMERCIAL and row['url'] not in commercial_health_urls() and row not in CONFLICTS:
        assert candidates == [] and trace['status'] == 'excluded'
        assert trace['reason'] == 'no_health_anchor'
        assert trace['publisher_content_classification'] == 'sponsored'
    else:
        assert len(candidates) == 1
        assert trace['publication_date_source'] == candidates[0].metadata['publication_date_source']
        assert trace['html_sha256'] == candidates[0].metadata['html_sha256']


def test_normal_discovery_hook_retains_complete_proof_for_an_article_found_only_in_fallback_listing(tmp_path):
    from datetime import date
    from radar_salud.pulso_source import LISTINGS, SITEMAP_INDEX, discover_pulso
    row = LISTING_CASES[0]
    def loader(url):
        if url == SITEMAP_INDEX:
            return '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" />'
        if '/arc/outboundfeeds/' in url:
            return '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" />'
        if url in LISTINGS:
            return f'<a href="{row["url"]}">Información general</a>' if url == LISTINGS[0] else ''
        assert url == row['url']
        return original(row)
    audit = []
    candidates = discover_pulso(loader, audit, cache_path=tmp_path/'cache.json', today=date(2026, 10, 11),
                               include_public_feeds=False)
    assert [raw.url for raw in candidates] == [row['url']]
    trace = next(item for item in audit if item.get('url') == row['url'])
    assert trace['status'] == 'discovered' and trace['listing'] == LISTINGS[0]
    assert trace['html_sha256'] == row['sha256'] and trace['captured_at']
    assert trace['publication_date_source'] == 'visible_article_byline'
    assert trace['primary_identity_verified'] and trace['publication_date_verified']
    assert trace['article_verified'] and trace['article_body_complete']
    assert trace['publisher_content_classification'] == 'factual'
