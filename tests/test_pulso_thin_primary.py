"""Every cold thin detail replays exact original bytes, never a title sample."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_source import _verified_detail, extract_article

REAL = Path(__file__).parent / 'fixtures/pulso_thin_primary_real'
MANIFEST = json.loads((REAL / 'manifest.json').read_text())
SHORT_HEADLINES = [row for row in MANIFEST['requests'] if row['title_below_18']]


def original(row):
    raw = gzip.decompress((REAL / row['gzip_file']).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == row['sha256']
    return raw.decode(row['charset'])


def test_all_thirteen_short_primary_headlines_are_covered():
    assert len(SHORT_HEADLINES) == 13
    assert all(row['url_bound_article_nodes'] == 1 and row['body_complete_as_original']
               and not row['primary_body_below_160'] for row in SHORT_HEADLINES)


@pytest.mark.parametrize('row', SHORT_HEADLINES, ids=lambda row: row['url'].split('/')[-2])
def test_legitimate_short_headline_retains_complete_original_body_and_date(row):
    from radar_salud.pulso_source import ExcludedArticle
    if row['url'].split('/')[-2] in ('nada-es-imposible', 'lo-dijimos'):
        # These complete short texts are explicitly publisher-labelled columns;
        # a valid short headline must not turn that taxonomy into factual news.
        with pytest.raises(ExcludedArticle, match='^publisher_opinion_taxonomy$') as raised:
            extract_article(original(row), row['url'])
        title, body, metadata = raised.value.title, raised.value.body, raised.value.metadata
    else:
        title, body, metadata = extract_article(original(row), row['url'])
    assert title == row['title'].strip()
    assert 0 < len(title) < 18 and len(body) >= 160
    assert body == row['full_primary_body']
    assert hashlib.sha256(body.encode()).hexdigest() == row['primary_body_sha256']
    assert metadata['publication_date'] == row['visible_byline_day']
    assert metadata['canonical_url'] == row['url']


def test_short_health_headline_opens_full_detail_and_cannot_be_false_negative():
    row = next(row for row in SHORT_HEADLINES if '/vivir-con-toc/' in row['url'])
    result = _verified_detail(dict(url=row['url'], listing='official-primary', lastmod='real-token'),
                              lambda _: original(row), None)
    assert result['relevant'] is True
    assert result['metadata']['page_text'] == row['full_primary_body']
    assert result['metadata']['article_body_characters'] == 8690
    assert 'status' not in result


VIDEOS = [row for row in MANIFEST['requests'] if '/videos/' in row['url']]


def test_all_sixteen_incomplete_original_videos_are_covered():
    assert len(VIDEOS) == 16


@pytest.mark.parametrize('row', VIDEOS, ids=lambda row: row['url'].split('/')[-2])
def test_real_video_identity_and_date_are_verified_without_inventing_text(row):
    from radar_salud.pulso_source import TextUnavailableArticle, complete_article_body, verified_video_without_text
    with pytest.raises(TextUnavailableArticle, match='publisher_video_text_unavailable') as raised:
        extract_article(original(row), row['url'])
    evidence = raised.value.metadata
    assert evidence['canonical_url'] == row['url']
    assert evidence['publication_date'] == row['visible_byline_day']
    assert evidence['primary_identity_verified'] and evidence['publication_date_verified']
    assert evidence['article_verified'] is False and evidence['article_body_complete'] is False
    assert evidence['video_evidence']['url'] == row['url']
    assert evidence['video_evidence']['id'] == row['url'] + '#video'
    assert verified_video_without_text(evidence)
    # Original HTMLwrapper contains only byline/share/tags; none is a transcript.
    assert raised.value.body == ''
    result = _verified_detail(dict(url=row['url'], listing='official-primary', lastmod='real-token'),
                              lambda _: original(row), None)
    assert result['relevant'] and result['deferred_reason'] == 'publisher_video_text_unavailable'
    assert result['metadata']['page_text'] == '' and not complete_article_body(result['metadata'])
    assert result['metadata']['source_quality_gate'] == 'deferred_video_text'
    assert result['metadata']['html_sha256'] == row['sha256']


def test_real_video_ignores_short_json_body_and_long_metadata_wrapper():
    """Adversarial mutation of an original video, not an additional live capture."""
    from radar_salud.pulso_source import TextUnavailableArticle
    row = VIDEOS[0]
    html = original(row)
    # Model the independently observed Alzheimer84/HTML251 publisher layout.
    # A URL-bound short body remains short; wrapper length cannot upgrade it.
    needle = '"articleSection":"Videos"'
    assert needle in html
    html = html.replace(needle, '"articleBody":' + json.dumps('Titular sobre avances de Alzheimer ' * 2) + ',' + needle, 1)
    html = html.replace('</body>', '<div class="article-body"><span>Compartir Redes Más sobre: Salud Ciencia </span>' * 8 + '</div>' * 8 + '</body>')
    with pytest.raises(TextUnavailableArticle) as raised:
        extract_article(html, row['url'])
    assert len(raised.value.body) < 160
    assert raised.value.metadata['article_body_complete'] is False


def test_structural_video_exception_requires_bound_primary_identity_and_verified_date():
    from radar_salud.pulso_source import verified_video_without_text
    row = VIDEOS[0]
    result = _verified_detail(dict(url=row['url'], listing='primary'), lambda _: original(row), None)
    evidence = result['metadata']
    for change in ({'canonical_url': None}, {'publication_date_verified': False},
                   {'video_evidence': dict(evidence['video_evidence'], url='https://www.latercera.com/videos/noticia/related/')},
                   {'source_content_unavailable_reason': 'unknown'}, {'primary_identity_verified': False},
                   {'publication_evidence': []}, {'publication_date': '2099-01-01'}, {'article_verified': True}):
        assert not verified_video_without_text(dict(evidence, **change))
    national_url = evidence['canonical_url'].replace('/videos/', '/nacional/')
    moved = dict(evidence, canonical_url=national_url,
                 video_evidence=dict(evidence['video_evidence'], url=national_url, id=national_url+'#video'))
    assert not verified_video_without_text(moved)
    with pytest.raises(ValueError, match='article_identity_mismatch'):
        extract_article(original(row).replace('rel="canonical"', 'rel="related"').replace('property="og:url"', 'property="related"'), row['url'])


def test_video_cache_reuses_structural_proof_but_revalidates_legacy_wrapper_success():
    row = VIDEOS[0]
    entry = dict(url=row['url'], listing='primary', lastmod='unchanged')
    calls = []
    def loader(_):
        calls.append(row['url'])
        return original(row)
    cold = _verified_detail(entry, loader, None)
    warm = _verified_detail(entry, loader, cold)
    assert len(calls) == 1 and warm['cache_hit']
    assert warm['metadata']['html_sha256'] == cold['metadata']['html_sha256']
    # Old video wrapper was marked full/verified; it lacks VideoObject proof.
    legacy = dict(cold, metadata=dict(cold['metadata'], article_verified=True))
    legacy['metadata'].pop('video_identity_verified')
    refreshed = _verified_detail(entry, loader, legacy)
    assert len(calls) == 2 and not refreshed['cache_hit']
    assert refreshed['metadata']['article_verified'] is False


def test_full_original_thin_inventory_separates_queued_videos_from_verified_text_and_old_exclusions(tmp_path):
    from datetime import date
    from urllib.parse import parse_qs, urlparse
    from radar_salud.pulso_source import discover_public_feeds
    rows = MANIFEST['requests']
    by_url = {row['url']: row for row in rows}
    opened = []
    def loader(url):
        if '/canal/' in url:
            return 'Fusion.deployment="1284";'
        if '/pf/api/' in url:
            offset = json.loads(parse_qs(urlparse(url).query)['query'][0])['feedOffset']
            elements = [dict(_id=str(i), websites={'la-tercera': {'website_url': row['url']}},
                             first_publish_date=row['publication_evidence'][0]['timestamp'],
                             last_updated_date=row['publication_evidence'][0]['timestamp'])
                        for i, row in enumerate(rows)][offset:offset+24]
            return json.dumps(dict(content_elements=elements, count=len(rows), next=24 if offset == 0 else None))
        opened.append(url)
        return original(by_url[url])
    audit = []
    candidates, coverage = discover_public_feeds(loader, audit, tmp_path/'cache.json',
                                                today=date(2026, 10, 11), feeds=[('tag', 'salud')])
    assert len(opened) == len(set(opened)) == 29 and coverage['coverage_complete']
    assert not any(row['status'] in ('detail_error', 'listing_error') for row in audit)
    metadata_only = [row for row in audit if row['status'] == 'discovered_metadata_only']
    assert len(metadata_only) == 12
    assert all(row['reason'] == 'publisher_video_text_unavailable' and row['publication_date_verified']
               and not row['article_verified'] and not row['article_body_complete'] for row in metadata_only)
    video_candidates = [raw for raw in candidates if raw.metadata.get('publisher_document_type') == 'video']
    assert len(video_candidates) == coverage['metadata_only_video_candidates'] == 12
    assert all(not raw.metadata['article_body_complete'] and raw.metadata['page_text'] == ''
               for raw in video_candidates)
    old_video_urls = {row['url'] for row in VIDEOS if row['visible_byline_day'] < '2026-07-13'}
    assert len(old_video_urls) == 4
    assert all(row['status'] == 'excluded' and row['reason'] == 'outside_90_day_window'
               for row in audit if row.get('url') in old_video_urls and 'publication_date' in row)
    assert coverage['publication_date_coverage_only_for_text_unavailable_candidates'] is True
