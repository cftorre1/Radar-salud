"""Synthetic native clinical layouts; no current endpoint health is fabricated."""
import json
import hashlib
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import pytest

from radar_salud.achs_clinics import CLINICS, ClinicArticle, clinic_for_host, discover_clinics_inventory
from radar_salud.beta_sources import CuratedBetaSourceScout

AS_OF = date(2026, 10, 11)
BODY = ("Habilitamos nuevos pabellones y ampliamos servicios de atención para la comunidad. "
        "El nuevo equipamiento permite ampliar prestaciones quirúrgicas y consultas médicas, "
        "con mayor capacidad de atención y nuevos servicios disponibles para pacientes.")
TITLE = "Habilitamos nuevos pabellones para atención de la comunidad"


def article(published="2026-10-10", title=TITLE, body=BODY, *, sidebar="", visible_date=None):
    meta = f'<meta property="article:published_time" content="{published}">' if published else ""
    time = f'<time class="published" datetime="{visible_date}">{visible_date}</time>' if visible_date else ""
    return (f'<html><head>{meta}</head><body><header class="site-header"><h1>Logotipo Clínicas Achs Salud</h1></header>'
            f'<article><header class="entry-header"><h1 class="entry-title">{title}</h1>{time}</header>'
            f'<div class="entry-content"><p>{body}</p></div></article>{sidebar}'
            '<footer>Últimas noticias: 11/10/2026. Copyright 2026.</footer></body></html>')


def listing(urls, next_url=None):
    cards = ''.join(f'<article><h2 class="entry-title"><a href="{url}">Una noticia de la clínica</a></h2></article>' for url in urls)
    return cards + (f'<a rel="next" href="{next_url}">Siguiente</a>' if next_url else '')


class Loader:
    def __init__(self, bodies, headers=None):
        self.bodies, self.records, self.visited = bodies, {}, []
        self.headers = headers or {}
    def __call__(self, url):
        self.visited.append(url)
        value = self.bodies[url]
        if isinstance(value, Exception):
            raise value
        self.records[url] = {"hops": [{"headers": [self.headers.get(url, {})]}]}
        return value


def fixture(clinics=CLINICS):
    bodies = {}
    for clinic in clinics:
        current, old = clinic['home'] + 'nuevos-pabellones/', clinic['home'] + 'nueva-upc-2025/'
        bodies.update({clinic['home']: '<h1>Inicio de la clínica</h1>', clinic['news']: listing([current, old]),
                       current: article(), old: article('2025-06-05')})
    return bodies


def test_all_nine_verified_publishers_have_individual_inventory_and_explicit_provider_role():
    loader = Loader(fixture())
    result = discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), loader, AS_OF)
    assert result['surface_slug'] == 'achs_clinics_network'
    assert len(result['clinic_reports']) == 9 and len(result['rows']) == 18
    assert len(result['raw_items']) == 9 and result['coverage_complete']
    assert result['metrics']['90']['dated_articles'] == 9
    assert all(row['market_role'] == 'provider_achs' and row['provider_subtype'] == 'clinicas' for row in result['rows'])
    assert all(item.metadata['clinic_id'] and item.metadata['provider_subtype'] == 'clinicas' for item in result['raw_items'])
    assert all('raw_items' not in branch for branch in result['clinic_reports'])
    json.dumps({key: value for key, value in result.items() if key != 'raw_items'})


def test_clinic_article_scopes_wordpress_body_and_ignores_logo_and_old_capacity_sidebar():
    clinic = CLINICS[0]
    sidebar = '<div class="sidebar"><h2>Lo más visto</h2><h3>Nueva unidad de cuidados intensivos</h3><p>Inauguramos nuevos pabellones en 2025.</p></div>'
    parser = ClinicArticle(url=clinic['home'] + 'reconocimiento/')
    parser.feed(article(title='Recibimos un reconocimiento por satisfacción de pacientes',
                        body='Recibimos un reconocimiento y agradecemos el compromiso de nuestros equipos. ' * 4, sidebar=sidebar))
    title, published, body, evidence = parser.result(today=AS_OF)
    assert title == 'Recibimos un reconocimiento por satisfacción de pacientes'
    assert published == '2026-10-10' and evidence == 'article:published_time'
    assert parser.content_scope == 'wordpress:entry-content'
    assert 'pabellones' not in body and 'Logotipo' not in title


@pytest.mark.parametrize('tail', ['Lo más visto', 'Photostream', 'Archivos', 'Noticias que te podrían interesar'])
def test_verified_native_tail_headings_stop_materiality_even_inside_article_fallback(tail):
    parser = ClinicArticle(url=CLINICS[0]['home'] + 'reconocimiento/')
    parser.feed('<head><meta property="article:published_time" content="2026-10-10"></head>'
                '<article><h1>Reconocimiento para los equipos de atención clínica</h1><p>' + 'Agradecemos a nuestro equipo por su dedicación. ' * 4 +
                f'</p><h2>{tail}</h2><p>Habilitamos nuevos pabellones y ampliamos prestaciones.</p></article>')
    _, published, body, _ = parser.result(today=AS_OF)
    assert published == '2026-10-10' and 'pabellones' not in body


def test_conflicting_explicit_detail_dates_fail_closed():
    parser = ClinicArticle(url=CLINICS[0]['home'] + 'noticia/')
    parser.feed(article('2026-08-12', visible_date='2026-08-10'))
    assert parser.result(today=AS_OF)[1] is None
    assert parser.result(today=AS_OF)[3] == 'conflicting_publication_dates'


@pytest.mark.parametrize('bad', [article(''), article('2026-10-12'), article('31/02/2026')])
def test_undated_future_invalid_and_footer_dates_cannot_promote_current_article(bad):
    clinic = CLINICS[0]; bodies = fixture([clinic]); current = clinic['home'] + 'nuevos-pabellones/'
    bodies[current] = bad
    result = discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), Loader(bodies), AS_OF, manifest=[clinic])
    assert not result['coverage_complete'] and not result['raw_items']
    assert result['rows'][0]['publication_date'] is None and result['rows'][0]['status'] == 'pending'


def test_missing_native_container_cannot_use_branding_h1_as_article():
    parser = ClinicArticle(url=CLINICS[0]['home'] + 'noticia/')
    parser.feed('<head><meta property="article:published_time" content="2026-10-10"></head>'
                f'<h1>Logotipo de la clínica</h1><p>{BODY}</p>')
    assert parser.result(today=AS_OF)[2] == ''
    assert parser.content_scope == 'missing_native_article_container'


def test_observed_medicenter_post_content_requires_a_singular_post_scope():
    inside = '<li class="single post"><div class="post-content"><h1 class="post-title">' + TITLE + '</h1><p>' + BODY + '</p></div></li>'
    for singular in (True, False):
        parser = ClinicArticle(url=CLINICS[0]['home'] + 'noticia/')
        parser.feed('<head><meta property="article:published_time" content="2026-10-10"></head>'
                    '<body class="' + ('single-post' if singular else 'page') + '"><h1 class="page-title">Banner de la clínica</h1>'
                    + inside + '<aside>Inauguramos pabellones antiguos en 2025.</aside></body>')
        title, published, body, _ = parser.result(today=AS_OF)
        if singular:
            assert title == TITLE and published == '2026-10-10' and body == BODY
            assert parser.content_scope == 'wordpress:medicenter_post-content'
        else:
            assert body == '' and parser.content_scope == 'missing_native_article_container'


@pytest.mark.parametrize('url,published', [
    ('https://clinicamaitenes.cl/nueva-unidad-de-paciente-critico/', '2025-06-05'),
    ('https://clinicalircay.cl/modulo-fonasa-talca-lircay/', '2023-12-13'),
    ('https://www.clinicalosandes.cl/inauguramos-nuestro-nuevo-centro-medico/', '2022-12-21'),
    ('https://clinica-curico.cl/nuevo-scanner-tac/', '2025-09-22'),
    ('https://clinica-curico.cl/nuevo-resonador-magnetico-signa-creator/', '2025-09-22'),
    ('https://clinicamaitenes.cl/mes-del-corazon-salud-cardiaca/', '2026-08-05'),
    ('https://clinica-curico.cl/clinicas-achs-salud-primer-lugar-total-brands/', '2026-08-12'),
    ('https://clinicaloscoihues.cl/clinicas-achs-salud-primer-lugar-total-brands', '2026-08-12'),
])
def test_current_origin_capture_native_clinic_layouts_preserve_publication_year(url, published):
    base = Path(__file__).resolve().parents[1] / 'data/audits/source_e_recovery/actions/38117675962'
    report = json.loads((base / 'report.json').read_text())
    record = next(row for row in report['records'] if row['url'] == url)
    hop = record['hops'][-1]
    raw = (base / hop['body_file']).read_bytes()
    assert record['http_status'] == 200 and hop['tls']['verified']
    assert hashlib.sha256(raw).hexdigest() == hop['sha256']
    parser = ClinicArticle(url=url)
    parser.feed(raw.decode('utf-8', errors='replace'))
    title, actual, body, evidence = parser.result(today=AS_OF)
    assert actual == published and len(title) >= 18 and len(body) >= 160
    assert parser.publication_evidence(today=AS_OF)['url'] == url
    assert parser.publication_evidence(today=AS_OF)['date'] == published
    assert 'Leave a reply' not in body
    if 'clinicaloscoihues' in url:
        assert evidence == 'publisher:publication_container'
        assert parser.date_candidates == [{'kind': evidence, 'value': '12/08/2026'}]
        assert parser.content_scope == 'html:article'
        assert 'Mejor Ambiente Laboral' not in body
    else:
        assert evidence == 'article:published_time'
        assert parser.content_scope == 'wordpress:medicenter_post-content'


def test_drupal_native_date_class_is_restricted_to_the_observed_clinic_publisher():
    for clinic in (CLINICS[0], CLINICS[2]):
        parser = ClinicArticle(url=clinic['home'] + 'noticia/')
        parser.feed('<article class="single-noticia"><span class="date-noticia">12/08/2026</span><h1>'
                    + TITLE + '</h1><p>' + BODY + '</p></article>'
                    '<article class="card-noticia"><span class="date-noticia">13/08/2026</span><h1>Otra noticia</h1></article>')
        result = parser.result(today=AS_OF)
        assert result[1] == ('2026-08-12' if clinic['id'] == 'los_coihues' else None)


def test_observed_next_href_is_followed_and_a_page_budget_remains_partial():
    clinic = CLINICS[0]; bodies = fixture([clinic]); current = clinic['home'] + 'nuevos-pabellones/'; old = clinic['home'] + 'nueva-upc-2025/'
    second = clinic['news'] + 'page/2/'
    bodies[clinic['news']] = listing([current], second); bodies[second] = listing([old])
    loader = Loader(bodies)
    report = discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), loader, AS_OF, manifest=[clinic])
    assert report['coverage_complete'] and second in loader.visited
    limited = discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), Loader(bodies), AS_OF, max_pages=1, manifest=[clinic])
    assert not limited['coverage_complete'] and limited['clinic_reports'][0]['stop_reason'] == 'max_pages_exhausted'


@pytest.mark.parametrize('target', ['https://foreign.example/noticias/page/2/', 'http://clinicaportada.cl/noticias/page/2/', 'https://clinicaportada.cl/noticias/page/3/'])
def test_unsafe_or_gapped_next_links_are_not_requested(target):
    clinic = CLINICS[0]; bodies = fixture([clinic]); current = clinic['home'] + 'nuevos-pabellones/'
    bodies[clinic['news']] = listing([current], target)
    loader = Loader(bodies)
    result = discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), loader, AS_OF, manifest=[clinic])
    assert not result['coverage_complete'] and target not in loader.visited


def test_one_clinic_blocker_does_not_stop_other_eight_publishers():
    bodies = fixture(); bodies[CLINICS[0]['news']] = TimeoutError('Origin newsroom timeout')
    result = discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), Loader(bodies), AS_OF)
    assert len(result['clinic_reports']) == 9 and len(result['raw_items']) == 8
    assert not result['coverage_complete']
    assert result['clinic_reports'][1]['coverage_complete']
    assert any(error['url'] == CLINICS[0]['news'] for error in result['errors'])


def test_disclosed_rss_timezone_is_normalized_and_last_build_date_does_not_replace_publication():
    clinic = CLINICS[0]; bodies = fixture([clinic]); current = clinic['home'] + 'nuevos-pabellones/'; feed = clinic['home'] + 'feed/'
    bodies[clinic['home']] = f'<link rel="alternate" type="application/rss+xml" title="Clínica RSS" href="{feed}">'
    bodies[current] = article('2026-10-06T00:22:30+00:00')
    bodies[feed] = f'<rss><channel><lastBuildDate>Sun, 11 Oct 2026 12:00:00 +0000</lastBuildDate><item><title>{TITLE}</title><link>{current}</link><pubDate>Tue, 06 Oct 2026 00:22:30 +0000</pubDate></item></channel></rss>'
    result = discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), Loader(bodies), AS_OF, manifest=[clinic])
    assert result['coverage_complete'] and result['raw_items'][0].event_date == '2026-10-05'


def test_rss_only_date_cannot_promote_a_detail_without_publication_evidence():
    clinic = CLINICS[0]; bodies = fixture([clinic]); current = clinic['home'] + 'nuevos-pabellones/'; feed = clinic['home'] + 'feed/'
    bodies[clinic['home']] = f'<a href="{feed}">RSS</a>'; bodies[current] = article('')
    bodies[feed] = f'<rss><channel><item><title>{TITLE}</title><link>{current}</link><pubDate>Sat, 10 Oct 2026 12:00:00 +0000</pubDate></item></channel></rss>'
    result = discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), Loader(bodies), AS_OF, manifest=[clinic])
    assert not result['raw_items'] and not result['coverage_complete']
    assert result['rows'][0]['publication_date'] is None


def test_clinic_domain_allowlist_and_provider_lane_are_required():
    assert clinic_for_host('www.achs.cl') is None
    assert clinic_for_host('clinicaportada.cl')['id'] == 'portada'
    with pytest.raises(ValueError, match='provider lane'):
        discover_clinics_inventory(CuratedBetaSourceScout('achs_seguro_laboral'), Loader({}), AS_OF)
    manifest = [{**CLINICS[0], 'hosts': ['foreign.example'], 'home': 'https://foreign.example/'}]
    with pytest.raises(ValueError, match='unverified'):
        discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), Loader({}), AS_OF, manifest=manifest)


@pytest.mark.parametrize('complete_headers', [True, False])
def test_advertised_native_api_recovers_extra_current_post_with_schema_and_total_headers(complete_headers):
    clinic = CLINICS[0]; bodies = fixture([clinic]); api = clinic['home'] + 'wp-json/'
    bodies[clinic['home']] = f'<link rel="https://api.w.org/" href="{api}">'
    bodies[api] = json.dumps({'routes': {'/wp/v2/posts': {'endpoints': [{'methods': ['GET'], 'args': {'after': {}, 'before': {}, 'page': {}, 'per_page': {'maximum': 100}}}]}}})
    posts_url = api + 'wp/v2/posts?' + urlencode({'per_page': 100, 'after': '2026-07-12T23:59:59', 'before': '2026-10-12T00:00:00'})
    first, extra = clinic['home'] + 'nuevos-pabellones/', clinic['home'] + 'nueva-prestacion/'
    bodies[posts_url] = json.dumps([{'id': 1, 'link': first, 'date': '2026-10-10T11:00:00', 'status': 'publish', 'title': {'rendered': TITLE}},
                                   {'id': 2, 'link': extra, 'date': '2026-09-22T11:00:00', 'status': 'publish', 'title': {'rendered': TITLE}}])
    bodies[extra] = article('2026-09-22')
    headers = {posts_url: {'x-wp-total': '2', 'x-wp-totalpages': '1'}} if complete_headers else {}
    result = discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), Loader(bodies, headers), AS_OF, manifest=[clinic])
    assert result['clinic_reports'][0]['api_window_complete'] == complete_headers
    assert result['coverage_complete'] == complete_headers
    assert len(result['raw_items']) == 2 and extra in [row['url'] for row in result['rows']]


def test_future_feed_field_invalidates_existing_raw_and_keeps_other_dates_honest():
    clinic = CLINICS[0]; bodies = fixture([clinic]); current = clinic['home'] + 'nuevos-pabellones/'; feed = clinic['home'] + 'feed/'
    bodies[clinic['home']] = f'<link rel="alternate" type="application/rss+xml" href="{feed}">'
    bodies[feed] = f'<rss><channel><item><title>{TITLE}</title><link>{current}</link><pubDate>Mon, 12 Oct 2026 12:00:00 +0000</pubDate></item></channel></rss>'
    result = discover_clinics_inventory(CuratedBetaSourceScout('clinicas_achs_salud'), Loader(bodies), AS_OF, manifest=[clinic])
    assert not result['raw_items'] and not result['coverage_complete']
    assert result['rows'][0]['reason'] == 'clinic_feed_publication_unverified'
