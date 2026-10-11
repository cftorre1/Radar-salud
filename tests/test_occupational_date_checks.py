"""Publisher alternatives diagnose ambiguity without choosing a convenient day."""
from datetime import date
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote

from radar_salud.occupational_capture import CaptureLoader
from radar_salud.occupational_date_checks import TPS_URL, _Disclosures, blog_publication_date_issues, ist_publication_date_issue
from radar_salud.occupational_sources import Article

AS_OF = date(2026, 10, 11)
API_URL = 'https://ist.cl/wp-json/wp/v2/posts?per_page=100&after=2026-07-12T23%3A59%3A59&before=2026-10-12T00%3A00%3A00'


def blog_record(publication, editorial, *, created='sep. 4, 2026, 13:59'):
    fields = {'navigateUrl': '/blog/detalle/una-publicacion', 'Title': 'Una publicación de salud',
              'PublicationDate': publication, 'FechaArticulo': editorial,
              'DateCreated': created, 'LastModified': created}
    return '<div class="cf_item">' + ''.join(f'<span class="{key}">{value}</span>' for key, value in fields.items()) + '</div>'


def test_historical_conflicting_dates_stay_unknown_but_modified_and_created_cannot_make_them_current():
    report = blog_publication_date_issues(blog_record('abr. 9, 2026, 14:00', 'mar. 9, 2026, 14:00'), as_of=AS_OF)
    assert report['unknown_exact_publication_dates'] == report['historical_90_day_issues'] == 1
    assert report['potentially_current_90_day_issues'] == 0
    row = report['date_issues'][0]
    assert row['publication_date'] is None and row['event_date'] is None and row['status'] == 'pending'
    assert row['observed_publication_days'] == ['2026-03-09', '2026-04-09']
    assert row['ignored_for_publication'] == ['LastModified', 'DateCreated']


def test_one_possible_current_publication_day_keeps_the_blog_record_pending():
    report = blog_publication_date_issues(blog_record('sep. 4, 2026, 13:22', 'abr. 9, 2026, 14:00'), as_of=AS_OF)
    assert report['potentially_current_90_day_issues'] == 1 and report['historical_90_day_issues'] == 0
    assert report['date_issues'][0]['potentially_within_90_days']
    assert not report['date_issues'][0]['potentially_within_30_days']
    assert report['date_issues'][0]['publication_date'] is None


def test_an_invalid_or_future_field_cannot_be_bounded_as_a_historical_record():
    for invalid in ('oct. 12, 2026, 14:00', 'periodo2025', ''):
        report = blog_publication_date_issues(blog_record('abr. 9, 2026, 14:00', invalid), as_of=AS_OF)
        assert report['potentially_current_90_day_issues'] == 1
        assert report['historical_90_day_issues'] == 0
        assert report['date_issues'][0]['publication_date'] is None


def test_jsonld_requires_article_url_binding_and_never_uses_modified_as_publication():
    schema = [{'@type': 'Article', 'url': TPS_URL, 'datePublished': '2026-08-12T14:38:53+00:00',
               'dateModified': '2026-10-10T10:00:00-03:00'},
              {'@type': 'Article', 'url': 'https://ist.cl/otra-noticia/', 'datePublished': '2026-10-10'}]
    html = ('<head><meta property="article:published_time" content="2026-08-12T14:38:53+00:00">'
            '<meta property="article:modified_time" content="2026-10-10T10:00:00-03:00">'
            '<script type="application/ld+json">' + json.dumps(schema) + '</script></head>'
            '<h1>Realizamos una jornada preventiva en TPS</h1><span class="published">Ago 12, 2026</span>')
    post = {'id': 105186, 'link': TPS_URL, 'status': 'publish', 'date': '2026-08-12T11:38:53',
            'date_gmt': '2026-08-12T14:38:53', 'modified': '2026-10-10T10:00:00',
            'content': {'rendered': '<p>10/08/2026</p><h1>Realizamos una jornada preventiva en TPS</h1>'}}
    rss = '<rss><channel><lastBuildDate>Sun, 11 Oct 2026 12:00:00 +0000</lastBuildDate></channel></rss>'
    report = ist_publication_date_issue(html, post, rss, as_of=AS_OF)
    assert report['api_native_publication']['date'] == '2026-08-12'
    assert report['jsonld_publication_fields'] == [{'kind': 'jsonld:datePublished', 'url': TPS_URL,
        'value': '2026-08-12T14:38:53+00:00', 'date': '2026-08-12'}]
    assert report['unlabelled_content_header_dates'][0]['date'] == '2026-08-10'
    assert report['publication_date'] is None and report['event_date'] is None and report['status'] == 'pending'
    assert report['ignored_publication_fields']['api']['modified'] == '2026-10-10T10:00:00'
    assert not report['rss']['can_resolve_this_post']


def test_current_run9_origin_captures_bound_the_two_ambiguities_without_automatic_resolution(tmp_path):
    base = Path(__file__).resolve().parents[1] / 'data/audits/source_e_recovery/actions/38119024441/inventory'
    loader = CaptureLoader(tmp_path, replay=base)
    blog = blog_publication_date_issues(loader('https://www.achssalud.cl/blog'), as_of=AS_OF)
    assert blog['records'] == 43 and blog['unknown_exact_publication_dates'] == 25
    assert blog['historical_90_day_issues'] == 24 and blog['potentially_current_90_day_issues'] == 1
    current = next(row for row in blog['date_issues'] if row['potentially_within_90_days'])
    assert 'duelo-migratorio' in current['url'] and current['observed_publication_days'] == ['2026-04-09', '2026-09-04']
    tps = ist_publication_date_issue(loader(TPS_URL), loader(API_URL), loader('https://ist.cl/feed/'), as_of=AS_OF)
    assert tps['api_native_publication']['post_id'] == 105186
    assert tps['api_native_publication']['date'] == '2026-08-12'
    assert {row['date'] for row in tps['html_publication_fields']} == {'2026-08-12'}
    assert tps['unlabelled_content_header_dates'][0]['date'] == '2026-08-10'
    assert not tps['jsonld_present'] and tps['rss']['returned_items'] == 10
    assert not tps['rss']['matching_post_publications']
    assert tps['publication_date'] is None and tps['no_automatic_date_selection']
    assert tps['official_api_self_links'] == [{'href': 'https://ist.cl/wp-json/wp/v2/posts/105186'}]


def test_current_exact_official_alternatives_still_do_not_resolve_the_two_date_issues(tmp_path):
    root = Path(__file__).resolve().parents[1] / 'data/audits/source_e_recovery/actions'
    base = root / '38120060930'
    records = json.loads((base / 'report.json').read_text())['records']

    def verified_body(url):
        record = next(row for row in records if row['url'] == url)
        hop = record['hops'][-1]
        body = (base / hop['body_file']).read_bytes()
        assert record['stop_reason'] == 'response_captured'
        assert hop['http_status'] == 200 and hop['tls']['verified']
        assert hashlib.sha256(body).hexdigest() == hop['sha256']
        return body.decode('utf-8')

    duelo_url = ('https://www.achssalud.cl/blog/detalle/'
                 'duelo-migratorio--qu%C3%A9-es-y-c%C3%B3mo-adaptarte-a-tu-nueva-ciudad')
    detail = verified_body(duelo_url)
    article = Article(url=duelo_url)
    article.feed(detail)
    disclosures = _Disclosures(duelo_url)
    disclosures.feed(detail)
    assert article.date_candidates == []
    assert disclosures.jsonld == []
    canonical = [row['url'] for row in disclosures.links if row['rel'] == 'canonical']
    assert canonical == [unquote(duelo_url)]
    assert not any(row['type'] in ('application/rss+xml', 'application/json') for row in disclosures.links)

    loader = CaptureLoader(tmp_path, replay=root / '38119024441/inventory')
    tps = ist_publication_date_issue(loader(TPS_URL),
        verified_body('https://ist.cl/wp-json/wp/v2/posts/105186'), loader('https://ist.cl/feed/'), as_of=AS_OF)
    assert tps['api_native_publication'] == {'value': '2026-08-12T11:38:53',
        'date': '2026-08-12', 'field': 'date', 'post_id': 105186}
    assert {row['date'] for row in tps['html_publication_fields']} == {'2026-08-12'}
    assert tps['unlabelled_content_header_dates'] == [{'kind': 'rendered_content:unlabelled_date_before_h1',
        'value': '10/08/2026', 'date': '2026-08-10'}]
    assert tps['publication_date'] is None and tps['event_date'] is None
    assert tps['status'] == 'pending' and tps['no_automatic_date_selection']
