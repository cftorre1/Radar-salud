"""Synthetic strict publication-conflict regressions; originals are retained separately."""
import copy
import json
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from radar_salud.pulso_source import (ConflictingPublicationArticle, _verified_detail,
                                    discover_public_feeds, extract_article,
                                    verified_publication_date_conflict)

URL = 'https://www.latercera.com/paula/noticia/corazon-atencion/'
BODY = 'La clínica modificó las prestaciones de su red y el financiamiento de consultas. El cambio afecta la atención y las listas de espera hospitalarias. ' * 3


def article(url=URL, timestamp='2026-08-06T21:20:49.55Z', byline='30 JULIO 2026', body=BODY):
    node = dict({'@type': 'NewsArticle', 'url': url, 'datePublished': timestamp,
                 'headline': 'Una nueva política de atención para los hospitales', 'articleBody': body})
    return (f'<link rel="canonical" href="{url}"><script type="application/ld+json">{json.dumps(node)}</script>'
            f'<meta property="article:published_time" content="{timestamp}">'
            f'<article><time class="article-body__byline__date">{byline}</time></article>')


def test_strict_extraction_preserves_conflict_without_selecting_or_inventing_a_date():
    with pytest.raises(ConflictingPublicationArticle, match='conflicting_publication_dates') as raised:
        extract_article(article(), URL)
    metadata = raised.value.metadata
    assert metadata['publication_date'] is None and metadata['publication_timestamp'] is None
    assert metadata['visible_publication_date'] == '2026-07-30'
    assert metadata['primary_identity_verified'] and not metadata['publication_date_verified']
    assert metadata['article_verified'] is False and metadata['article_body_complete']
    assert metadata['possible_publication_days'] == ['2026-07-30', '2026-08-06']
    result = _verified_detail(dict(url=URL, listing='public-feed', lastmod='token'), lambda _: article(), None)
    assert verified_publication_date_conflict(result['metadata'])
    assert result['metadata']['page_text'] == BODY.strip()
    assert result['deferred_reason'] == 'publisher_conflicting_publication_dates'


def test_bound_original_conflict_reuses_unchanged_identity_and_body_without_reinterpreting_date():
    calls = []
    def loader(url):
        calls.append(url)
        return article()
    entry = dict(url=URL, listing='public-feed', lastmod='unchanged')
    cold = _verified_detail(entry, loader, None)
    warm = _verified_detail(entry, loader, cold)
    assert calls == [URL] and warm['cache_hit']
    assert warm['metadata'] == cold['metadata']
    assert warm['metadata']['publication_date'] is None


def test_publisher_conflict_cannot_hide_missing_identity_body_or_byline():
    for html in (article().replace('rel="canonical"', 'rel="unbound"'),
                 article(body='Very short body'), article(byline='').replace(
                     '<meta property="article:published_time" content="2026-08-06T21:20:49.55Z">',
                     '<meta property="article:published_time" content="2026-07-30T12:00:00Z">'),
                 article(timestamp='2099-01-01T10:00:00Z')):
        result = _verified_detail(dict(url=URL, listing='public-feed'), lambda _: html, None)
        assert result['status'] == 'detail_error'
        assert not result.get('deferred_reason')
    valid = _verified_detail(dict(url=URL, listing='public'), lambda _: article(), None)['metadata']
    for change in ({'publication_date_verified': True}, {'publication_date': '2026-07-30'},
                   {'primary_identity_verified': False}, {'page_text': 'Missing original body'},
                   {'visible_publication_date': '2026-08-06'}):
        assert not verified_publication_date_conflict(dict(valid, **change))


def test_ambiguous_date_cannot_verify_old_boundary_and_requires_three_later_independent_pages(tmp_path):
    offsets = []
    unknown_url = 'https://www.latercera.com/nacional/noticia/hospital-unknown/'
    def loader(url):
        if '/canal/' in url:
            return ''
        if '/pf/api/' in url:
            offset = json.loads(parse_qs(urlparse(url).query)['query'][0])['feedOffset']
            offsets.append(offset)
            urls = [unknown_url if offset == 0 and i == 0 else
                    f'https://www.latercera.com/nacional/noticia/hospital-{offset+i}/' for i in range(24)]
            nodes = [dict(_id=str(offset+i), websites={'la-tercera': {'website_url': value}},
                          first_publish_date='2026-07-01T12:00:00Z', last_updated_date='2026-10-10T12:00:00Z')
                     for i, value in enumerate(urls)]
            return json.dumps(dict(content_elements=nodes, count=10000, next=offset+24))
        return article(url) if url == unknown_url else article(url, timestamp='2026-07-01T12:00:00Z', byline='1 JULIO 2026')
    audit = []
    candidates, coverage = discover_public_feeds(loader, audit, tmp_path/'cache.json',
                                                today=date(2026, 10, 11), feeds=[('section', 'nacional')])
    assert offsets == [0, 24, 48, 72]
    pages = [row for row in audit if row['status'] == 'public_feed_page']
    assert [row['boundary_pages'] for row in pages] == [0, 1, 2, 3]
    assert pages[0]['verified_details'] == 23
    assert coverage['coverage_complete'] and coverage['enumerated_with_editorial_exceptions']
    assert coverage['publisher_exceptions'] == 1 and not coverage['publication_date_coverage_complete']
    assert not any(row['status'] in ('detail_error', 'listing_error') for row in audit)
    assert len(candidates) == coverage['metadata_only_date_conflict_candidates'] == 1
    assert candidates[0].event_date is None and candidates[0].metadata['publication_timestamp'] is None
    trace = next(row for row in audit if row.get('url') == unknown_url)
    assert trace['status'] == 'discovered_metadata_only'
    assert trace['publisher_exception_reason'] == 'publisher_conflicting_publication_dates'
