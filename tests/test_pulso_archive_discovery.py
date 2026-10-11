"""Official XML structure fixtures plus adversarial bounded archive replays."""
import gzip
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar_salud.pulso_source import (
    SITEMAP_INDEX, SITEMAP_PAGE, discover_archive, discover_pulso,
    extract_article, parse_sitemap,
)

REAL = Path(__file__).parent / 'fixtures/pulso_real'
NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'
TODAY = date(2026, 10, 11)


def xml_index(offsets=(0,)):
    return f'<sitemapindex xmlns="{NS}">' + ''.join(
        f'<sitemap><loc>{SITEMAP_PAGE.replace("&", "&amp;")}' + (f'&amp;from={n}' if n else '') + '</loc></sitemap>'
        for n in offsets) + '</sitemapindex>'


def xml_page(offset, count=100, lastmod='2026-10-09T12:00:00Z'):
    return f'<urlset xmlns="{NS}" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">' + ''.join(
        f'<url><loc>https://www.latercera.com/nacional/noticia/gobierno-{offset+i}/</loc><lastmod>{lastmod}</lastmod>'
        '<image:image><image:loc>https://www.latercera.com/image.jpg</image:loc></image:image></url>'
        for i in range(count)) + '</urlset>'


def html_article(url, day='2026-10-09', health=True, timestamp=None, byline=''):
    body = ("La nueva financiación de hospitales y la deuda de las clínicas afectarán la capacidad de los prestadores y las listas de espera. " if health
            else "El gobierno anunció un cambio a la política de transporte y reordenó el calendario de licitaciones de trenes y carreteras nacionales. ") * 2
    node = dict({'@type': 'NewsArticle', 'url': url, 'headline': 'Gobierno anuncia un nuevo plan para las regiones',
                 'datePublished': timestamp or day, 'articleBody': body, 'articleSection': 'Nacional'})
    return f'<link rel="canonical" href="{url}"><script type="application/ld+json">{json.dumps(node)}</script><article>{byline}</article>'


def test_real_index_and_urlset_read_all_primary_loc_but_no_image_loc():
    kind, index = parse_sitemap(gzip.decompress((REAL / 'sitemap_index.xml.gz').read_bytes()).decode())
    assert kind == 'index' and len(index) == 100
    assert index[-1]['url'].endswith('&from=9900')
    kind, urls = parse_sitemap(gzip.decompress((REAL / 'sitemap_first_page.xml.gz').read_bytes()).decode())
    assert kind == 'urls' and len(urls) == 100
    assert all('/noticia/' in item['url'] for item in urls)
    assert not any('/resizer/' in item['url'] for item in urls)


def test_archive_reads_every_detail_and_health_in_body_with_generic_title(tmp_path):
    calls = []
    def loader(url):
        calls.append(url)
        if url == SITEMAP_INDEX:
            return xml_index()
        if url == SITEMAP_PAGE:
            return xml_page(0)
        if '/arc/outboundfeeds/' in url:
            return f'<urlset xmlns="{NS}" />'
        return html_article(url, health=url.endswith('gobierno-99/'))
    audit = []
    items = discover_pulso(loader, audit, cache_path=tmp_path / 'cache.json', today=TODAY, include_listings=False, include_public_feeds=False)
    assert len([url for url in calls if '/noticia/' in url]) == 100
    assert [item.url for item in items] == ['https://www.latercera.com/nacional/noticia/gobierno-99/']
    summary = next(entry for entry in audit if entry['status'] == 'archive_coverage')
    assert not summary['coverage_complete'] and summary['complete_90_days'] == {'start': '2026-07-13', 'end': '2026-10-10'}
    assert summary['complete_30_days'] == {'start': '2026-09-11', 'end': '2026-10-10'}
    assert len([entry for entry in audit if entry['status'] == 'excluded']) == 99
    assert all(entry.get('publication_date_source') for entry in audit if entry['status'] in ('discovered', 'excluded'))


def test_modified_date_is_not_a_publication_filter_and_detail_hash_is_durable(tmp_path):
    url = 'https://www.latercera.com/nacional/noticia/gobierno-0/'
    def loader(value):
        if value == SITEMAP_INDEX:
            return xml_index()
        if value == SITEMAP_PAGE:
            return xml_page(0, count=1, lastmod='2020-01-01T00:00:00Z')
        if '/arc/outboundfeeds/' in value:
            return f'<urlset xmlns="{NS}" />'
        return html_article(value)
    audit = []
    items, _, _ = discover_archive(loader, audit, tmp_path / 'cache.json', today=TODAY)
    assert [item.url for item in items] == [url]
    trace = next(entry for entry in audit if entry['status'] == 'discovered')
    assert trace['publication_date'] == '2026-10-09' and len(trace['html_sha256']) == 64
    assert json.loads((tmp_path / 'cache.json').read_text())['articles'][url]['lastmod'].startswith('2020-')


def test_cache_reuses_verified_exclusions_and_revalidates_changed_lastmod(tmp_path):
    calls, token = [], ['2026-10-09T00:00:00Z']
    def loader(value):
        calls.append(value)
        if value == SITEMAP_INDEX:
            return xml_index()
        if value == SITEMAP_PAGE:
            return xml_page(0, count=2, lastmod=token[0])
        if '/arc/outboundfeeds/' in value:
            return f'<urlset xmlns="{NS}" />'
        return html_article(value, health=value.endswith('gobierno-1/'))
    cache = tmp_path / 'cache.json'
    discover_archive(loader, [], cache, today=TODAY)
    assert len([u for u in calls if '/noticia/' in u]) == 2
    calls.clear()
    audit = []
    discover_archive(loader, audit, cache, today=TODAY)
    assert not any('/noticia/' in u for u in calls)
    assert all(e['cache_hit'] for e in audit if e['status'] in ('discovered', 'excluded'))
    token[0] = '2026-10-10T00:00:00Z'
    calls.clear()
    discover_archive(loader, [], cache, today=TODAY)
    assert len([u for u in calls if '/noticia/' in u]) == 2


def test_all_advertised_pages_processed_before_verified_older_boundary(tmp_path):
    offsets = []
    def loader(value):
        if value == SITEMAP_INDEX:
            return xml_index((0, 100))
        if '/arc/outboundfeeds/sitemap/' in value:
            offset = int(value.split('from=')[-1]) if 'from=' in value else 0
            offsets.append(offset)
            return xml_page(offset)
        num = int(value.rstrip('/').rsplit('-', 1)[1])
        # Even after an old advertised page the next announced page is read.
        return html_article(value, day='2026-10-09' if 100 <= num < 200 else '2026-07-01')
    audit = []
    items, _, summary = discover_archive(loader, audit, tmp_path / 'cache.json', today=TODAY, max_pages=10)
    assert offsets == [0, 100, 200, 300, 400]
    assert len(items) == 100 and summary['coverage_complete']
    assert summary['termination'] == 'consecutive_detail_verified_older_pages'


@pytest.mark.parametrize('failure', ['empty_bytes', 'http_error'])
def test_errors_after_announced_index_are_bounded_and_never_success(tmp_path, failure):
    calls = []
    def loader(value):
        calls.append(value)
        if value == SITEMAP_INDEX:
            return xml_index()
        if value == SITEMAP_PAGE:
            return xml_page(0, count=1)
        if '/arc/outboundfeeds/' in value:
            if failure == 'empty_bytes':
                return ''
            raise OSError('404 publisher archive hard cap')
        return html_article(value)
    audit = []
    _, _, summary = discover_archive(loader, audit, tmp_path / 'cache.json', today=TODAY, max_pages=8)
    assert summary['pages_attempted'] == 4
    assert not summary['coverage_complete']
    assert summary['termination'] == 'consecutive_archive_page_errors'
    assert any(e.get('reason') == 'archive_coverage_incomplete' for e in audit)


def test_explicit_page_cap_cannot_declare_complete(tmp_path):
    def loader(value):
        if value == SITEMAP_INDEX:
            return xml_index((0, 100, 200))
        if '/arc/outboundfeeds/' in value:
            offset = int(value.split('from=')[-1]) if 'from=' in value else 0
            return xml_page(offset, count=1)
        return html_article(value)
    _, _, summary = discover_archive(loader, [], tmp_path / 'cache.json', today=TODAY, max_pages=1)
    assert summary['pages_attempted'] == 1 and not summary['coverage_complete']
    assert summary['termination'] == 'explicit_page_limit'


def test_invalid_detail_is_audited_and_not_cached_as_verified(tmp_path):
    def loader(value):
        if value == SITEMAP_INDEX:
            return xml_index()
        if value == SITEMAP_PAGE:
            return xml_page(0, count=1)
        if '/arc/outboundfeeds/' in value:
            return f'<urlset xmlns="{NS}" />'
        return '<html>Publisher error response</html>'
    audit = []
    _, _, summary = discover_archive(loader, audit, tmp_path / 'cache.json', today=TODAY)
    assert not summary['coverage_complete']
    assert next(e for e in audit if e['status'] == 'detail_error')['reason'] == 'article_identity_mismatch'
    assert json.loads((tmp_path / 'cache.json').read_text())['articles'] == {}


def test_visible_byline_is_calendar_date_and_utc_timestamp_can_cross_midnight():
    url = 'https://www.latercera.com/nacional/noticia/hospital-anuncio/'
    html = html_article(url, timestamp='2026-10-11T01:30:00Z', byline='<time class="article-body__byline__date">10 OCTUBRE 2026</time>')
    _, _, metadata = extract_article(html, url)
    assert metadata['publication_date'] == '2026-10-10'
    assert metadata['publication_timestamp'] == '2026-10-11T01:30:00Z'
    assert metadata['publication_date_source'] == 'visible_article_byline'


def test_timestamp_in_future_rejected_even_when_calendar_day_is_today():
    url = 'https://www.latercera.com/nacional/noticia/hospital-anuncio/'
    with pytest.raises(ValueError, match='future_publication_date'):
        extract_article(html_article(url, timestamp=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()), url)


def test_visible_byline_conflicting_with_bound_publication_evidence_rejected():
    url = 'https://www.latercera.com/nacional/noticia/hospital-anuncio/'
    html = html_article(url, timestamp='2026-10-10T14:30:00Z', byline='<time class="article-body__byline__date">9 OCTUBRE 2026</time>')
    with pytest.raises(ValueError, match='conflicting_publication_dates'):
        extract_article(html, url)


def rss_page(url, *, health=True, short=False, title='Gobierno anuncia un nuevo plan para las regiones'):
    body = ('Hospitales y clínicas tendrán nuevos recursos para financiamiento y atención de listas de espera. ' if health else
            'El nuevo plan incluye contratos de transporte, ajustes al calendario de trenes y permisos para obras en carreteras nacionales. ') * (1 if short else 3)
    if short:
        body = 'Resumen breve'
    return '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>' + (
        f'<link>{url}</link><title>{title}</title><pubDate>Fri, 09 Oct 2026 15:00:00 GMT</pubDate>'
        f'<content:encoded><![CDATA[<p>{body}</p>]]></content:encoded></item></channel></rss>')


def test_real_rss_has_full_primary_story_bodies_not_search_snippets():
    from radar_salud.pulso_source import parse_fulltext_rss
    items = parse_fulltext_rss(gzip.decompress((REAL / 'rss.xml.gz').read_bytes()).decode())
    assert len(items) == 80  # 100 RSS entries minus opinion/unsupported routes
    assert sum(item['fulltext_complete'] for item in items.values()) == 76
    assert any(not item['fulltext_complete'] for item in items.values())  # videos must fall back to detail
    assert max(len(item['body']) for item in items.values()) > 10_000
    assert all(item['rss_inventory_day'] for item in items.values())


@pytest.mark.parametrize('health,short,opens_detail', [(True, False, True), (False, False, True), (False, True, True)])
def test_rss_body_never_excludes_cold_urls_from_unmarked_truncated_excerpt(tmp_path, health, short, opens_detail):
    calls = []
    url = 'https://www.latercera.com/nacional/noticia/gobierno-0/'
    def loader(value):
        calls.append(value)
        if value == SITEMAP_INDEX:
            return xml_index()
        if value == SITEMAP_PAGE:
            return xml_page(0, count=1)
        if '/arc/outboundfeeds/rss/' in value:
            return rss_page(url, health=health, short=short)
        if '/arc/outboundfeeds/' in value:
            return f'<urlset xmlns="{NS}" />'
        return html_article(value, health=True)
    audit = []
    items, _, summary = discover_archive(loader, audit, tmp_path / 'cache.json', today=TODAY)
    assert (url in calls) == opens_detail
    assert bool(items) == opens_detail
    if not opens_detail:
        trace = next(e for e in audit if e.get('url') == url and e['status'] == 'excluded')
        assert trace['reason'] == 'fulltext_rss_no_health_anchor'
        assert trace['publication_date'] is None and trace['publication_date_source'] == 'not_detail_verified'
        assert len(trace['rss_fulltext_sha256']) == 64
        assert summary['rss_fulltext_exclusions'] == 1


def test_rss_missing_primary_url_falls_back_to_original_detail(tmp_path):
    calls = []
    def loader(value):
        calls.append(value)
        if value == SITEMAP_INDEX:
            return xml_index()
        if value == SITEMAP_PAGE:
            return xml_page(0, count=1)
        if '/arc/outboundfeeds/rss/' in value:
            return rss_page('https://www.latercera.com/nacional/noticia/another-story/', health=False)
        if '/arc/outboundfeeds/' in value:
            return f'<urlset xmlns="{NS}" />'
        return html_article(value)
    items, _, _ = discover_archive(loader, [], tmp_path / 'cache.json', today=TODAY)
    assert len(items) == 1 and items[0].url in calls


def test_valid_empty_page_before_required_window_is_a_cap_not_success(tmp_path):
    def loader(value):
        if value == SITEMAP_INDEX:
            return xml_index()
        if value == SITEMAP_PAGE:
            return xml_page(0, count=1)
        if '/arc/outboundfeeds/' in value:
            return f'<urlset xmlns="{NS}" />'
        return html_article(value, day='2026-08-12')
    _, _, summary = discover_archive(loader, [], tmp_path / 'cache.json', today=TODAY)
    assert not summary['coverage_complete']
    assert summary['termination'] == 'archive_exhausted_before_required_window'


def test_opinion_under_news_path_is_traced_editorial_exclusion_not_detail_error(tmp_path):
    def loader(value):
        if value == SITEMAP_INDEX:
            return xml_index()
        if value == SITEMAP_PAGE:
            return xml_page(0, count=1)
        if '/arc/outboundfeeds/' in value:
            return f'<urlset xmlns="{NS}" />'
        return html_article(value).replace('"articleSection": "Nacional"', '"articleSection": "Opinión"')
    audit = []
    items, _, summary = discover_archive(loader, audit, tmp_path / 'cache.json', today=TODAY)
    assert not items and summary['errors'] == 0
    trace = next(e for e in audit if e.get('reason') == 'excluded_opinion_content')
    assert trace['status'] == 'excluded' and trace['publication_date'] == '2026-10-09'
    assert not any(e['status'] == 'detail_error' for e in audit)
    cached = json.loads((tmp_path / 'cache.json').read_text())['articles']
    assert next(iter(cached.values()))['exclusion_reason'] == 'excluded_opinion_content'


def ans_feed(offset=0, *, count=10000, day='2026-10-09', size=24, next_cursor=None):
    entries = []
    for i in range(size):
        entries.append(dict(_id=f'publisher-{offset+i}', headlines={'basic': 'Gobierno anuncia un nuevo plan para las regiones'},
                            websites={'la-tercera': {'website_url': f'/nacional/noticia/gobierno-{offset+i}/'}},
                            first_publish_date=day+'T15:00:00Z', publish_date=day+'T15:00:00Z',
                            last_updated_date='2026-10-09T15:00:00Z', taxonomy={'primary_section': {'path': '/nacional'}}))
    return json.dumps(dict(content_elements=entries, count=count, next=offset+size if next_cursor is None else next_cursor))


def test_public_frontend_url_matches_observed_button_and_parses_complete_inventory():
    from urllib.parse import parse_qs, urlparse
    from radar_salud.pulso_source import _public_feed_url, parse_public_feed
    url = _public_feed_url('tag', 'salud', 24, '1284')
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.path.endswith('/story-feed-tag-fetch')
    assert json.loads(query['query'][0]) == dict(feedOffset=24, feedSize=24, fromComponent='result-list', tagSlug='salud')
    assert set(query) == {'query', '_website', 'd'}
    entries, count, next_cursor = parse_public_feed(ans_feed())
    assert len(entries) == 24 and count == 10000 and next_cursor == 24
    assert all(entry['url'].startswith('https://www.latercera.com/nacional/noticia/') for entry in entries)


def test_public_feed_traverses_next_to_verified_90_day_boundary_without_title_gate(tmp_path):
    from urllib.parse import parse_qs, urlparse
    from radar_salud.pulso_source import discover_public_feeds
    offsets, opened = [], []
    def loader(value):
        if '/canal/' in value:
            return 'Fusion.deployment="1284";'
        if '/pf/api/' in value:
            query = json.loads(parse_qs(urlparse(value).query)['query'][0])
            offset = query['feedOffset']
            offsets.append(offset)
            return ans_feed(offset, day='2026-10-09' if offset == 0 else '2026-07-01')
        opened.append(value)
        number = int(value.rstrip('/').rsplit('-', 1)[1])
        return html_article(value, day='2026-10-09' if number < 24 else '2026-07-01')
    audit = []
    items, summary = discover_public_feeds(loader, audit, tmp_path/'cache.json', today=TODAY, feeds=[('section','nacional')])
    assert offsets == [0,24,48,72]
    assert len(opened) == 96 and len(items) == 24
    assert summary['coverage_complete']
    assert next(e for e in audit if e['status']=='public_feed_coverage')['termination'] == 'three_publication_ordered_detail_verified_old_pages'


def test_public_feed_count_short_scope_can_be_exhaustive_and_empty_capped_scope_cannot(tmp_path):
    from radar_salud.pulso_source import discover_public_feeds
    def loader(value):
        if '/canal/' in value:
            return ''
        if '/pf/api/' in value:
            return ans_feed(count=1, size=1)
        return html_article(value)
    items, summary = discover_public_feeds(loader, [], tmp_path/'cache.json', today=TODAY, feeds=[('tag','salud')])
    assert len(items) == 1 and summary['coverage_complete']
    def capped(value):
        if '/canal/' in value:
            return ''
        return ans_feed(count=10000, size=0)
    audit = []
    _, summary = discover_public_feeds(capped, audit, tmp_path/'cache2.json', today=TODAY, feeds=[('tag','salud')])
    assert not summary['coverage_complete']
    assert next(e for e in audit if e['status']=='public_feed_coverage')['termination'] == 'feed_exhausted_without_verified_window'


def test_public_feed_repeated_page_nonadvancing_cursor_and_cap_are_finite(tmp_path):
    from radar_salud.pulso_source import discover_public_feeds
    for mode in ('repeat','cursor','cap'):
        calls = []
        def loader(value):
            if '/canal/' in value:
                return ''
            if '/pf/api/' in value:
                calls.append(value)
                return ans_feed(0 if mode=='repeat' else len(calls)*24, next_cursor=0 if mode=='cursor' else None)
            return html_article(value)
        audit = []
        _, summary = discover_public_feeds(loader, audit, tmp_path/f'{mode}.json', today=TODAY,
                                          feeds=[('section','pulso')], max_feed_pages=2)
        assert len(calls) <= 2 and not summary['coverage_complete']
        assert any(e['status']=='listing_error' for e in audit)


def test_public_api_date_is_not_used_as_final_or_sufficient_boundary(tmp_path):
    from radar_salud.pulso_source import discover_public_feeds
    calls = []
    def loader(value):
        if '/canal/' in value:
            return ''
        if '/pf/api/' in value:
            calls.append(value)
            return ans_feed((len(calls)-1)*24, day='2026-07-01')
        return html_article(value, day='2026-10-09')
    audit = []
    items, summary = discover_public_feeds(loader, audit, tmp_path/'cache.json', today=TODAY,
                                          feeds=[('section','pulso')], max_feed_pages=4)
    assert len(calls) == 4 and not summary['coverage_complete']
    assert len(items) == 96 and all(item.event_date=='2026-10-09' for item in items)


def test_default_discovery_cache_is_in_durable_daily_state(tmp_path, monkeypatch):
    from radar_salud import paths
    monkeypatch.setattr(paths, 'project_root', lambda: tmp_path)
    def loader(value):
        if value == SITEMAP_INDEX:
            return xml_index()
        if value == SITEMAP_PAGE:
            return xml_page(0, count=1)
        if '/arc/outboundfeeds/' in value:
            return f'<urlset xmlns="{NS}" />'
        return html_article(value)
    discover_pulso(loader, [], today=TODAY, include_listings=False, include_public_feeds=False)
    assert (tmp_path/'data/state/pulso_discovery_cache.json').exists()


def test_public_feed_accepts_frontend_data_envelope():
    from radar_salud.pulso_source import parse_public_feed
    entries, count, next_cursor = parse_public_feed(json.dumps({'data': json.loads(ans_feed())}))
    assert len(entries) == 24 and count == 10000 and next_cursor == 24



def test_all_primary_control_factual_sections_have_explicit_historical_feeds():
    from radar_salud.pulso_source import PUBLIC_FEEDS
    controls = json.loads((Path(__file__).parents[1] / 'data/audits/pulso_external_control_2026_10_11.json').read_text())
    required = {item['section'] for item in controls['articles'] if item.get('recall_expected') and item.get('in_90_day_window')}
    configured = {name for kind, name in PUBLIC_FEEDS if kind == 'section'}
    assert 'horizontes' in required
    assert required <= configured


def test_api_archive_overlap_returns_one_canonical_article_with_occurrence_diagnostics(tmp_path):
    url = 'https://www.latercera.com/nacional/noticia/gobierno-0/'
    def loader(value):
        if '/canal/' in value:
            return 'Fusion.deployment="1284";'
        if '/pf/api/' in value:
            return ans_feed(count=1, size=1)
        if value == SITEMAP_INDEX:
            return xml_index()
        if value == SITEMAP_PAGE:
            return xml_page(0, count=1, lastmod='2026-10-09T15:00:00Z')
        if '/arc/outboundfeeds/' in value:
            return f'<urlset xmlns="{NS}" />'
        return html_article(value)
    audit = []
    items = discover_pulso(loader, audit, cache_path=tmp_path/'cache.json', today=TODAY,
                           include_listings=False, feeds=[('section','nacional')])
    assert [item.url for item in items] == [url]
    summary = next(item for item in audit if item['status']=='discovery_inventory')
    assert summary == dict(status='discovery_inventory', unique_health_urls=1,
                           inventory_health_occurrences=2, duplicate_inventory_occurrences=1)
    occurrences = [item for item in audit if item['status']=='discovered']
    assert [item['duplicate_inventory_url'] for item in occurrences] == [False, True]



def test_warm_public_feed_trace_retains_real_primary_publisher_change_token(tmp_path):
    from radar_salud.pulso_source import discover_public_feeds
    loaded=[]
    def loader(value):
        if '/canal/' in value:
            return ''
        if '/pf/api/' in value:
            return ans_feed(count=1,size=1)
        loaded.append(value)
        return html_article(value)
    cache=tmp_path/'cache.json'
    _, _ = discover_public_feeds(loader, [], cache, today=TODAY, feeds=[('section','nacional')])
    cold_fetches=len(loaded)
    audit=[]
    discover_public_feeds(loader,audit,cache,today=TODAY,feeds=[('section','nacional')])
    trace=next(item for item in audit if item['status']=='discovered')
    stored=json.loads(cache.read_text())['articles'][trace['url']]['metadata']
    assert len(loaded)==cold_fetches==1 and trace['cache_hit'] is True
    assert trace['publisher_lastmod']==stored['publisher_lastmod']=='2026-10-09T15:00:00Z'
    assert trace['captured_at']==stored['captured_at'] and trace['html_sha256']==stored['html_sha256']
