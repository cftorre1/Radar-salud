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
    items = discover_pulso(loader, audit, cache_path=tmp_path / 'cache.json', today=TODAY, include_listings=False)
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


@pytest.mark.parametrize('health,short,opens_detail', [(True, False, True), (False, False, False), (False, True, True)])
def test_rss_body_prescreen_never_uses_title_alone_or_truncated_body(tmp_path, health, short, opens_detail):
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
