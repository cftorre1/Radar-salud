"""Regressions for Mutual's native publisher cards and IBM query detail IDs."""
from datetime import date
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit

import pytest

from radar_salud.mutual_sources import (
    DETAIL_PAGE, PAGE, MutualNewsScout, _OfficialRedirect, _detail_url,
    fetch_mutual_html, parse_detail, parse_listing,
    same_article_url,
)
from radar_salud.occupational_sources import SourceDiscoveryError

TODAY = date(2026, 10, 11)
TITLE = "Mutual implementa nuevo protocolo para reintegro laboral"
BODY = ("Mutual implementa un nuevo protocolo para el reintegro laboral y la atención clínica. "
        "El procedimiento define la evaluación de los trabajadores y la coordinación de los equipos. "
        "La nueva herramienta estará disponible en los centros de atención de la institución.")


def detail_url(slug):
    return PAGE + "?" + urlencode({"1dmy": "", "page": DETAIL_PAGE,
        "urile": "wcm:path:/Mutual+2024+Paginas+Sitio+Publico+Empresa/SA_SitioEmpresa/SA_Home/"
                 "SA_NuestraMutual/SA_Noticias/SA_Noticias_Detalle/" + slug})


def card(slug, published="9 oct. 2026", title=TITLE):
    return (f'<div class="card-noticia"><div class="fecha">{published}</div>'
            f'<p class="title-card">{title}</p><p class="descrption-card">Resumen.</p>'
            f'<a class="href-button" href="{escape(detail_url(slug))}">Continúa leyendo</a></div>')


def branch(number, cards, next_href=None):
    link = f'<a id="pc123_nextPage" href="{escape(next_href)}">chevron_forward</a>' if next_href else ""
    return f'<div id="component-{number}" class="cards-noticias wb-products wb-text">{cards}{link}</div>'


def listing(*branches):
    return '<html><script>collectUniqueCards; chunkArray;</script><main>' + "".join(branches) + '</main></html>'


def detail(published="9 oct. 2026", title=TITLE, body=BODY, *, metadata="", prefix="", suffix=""):
    header_date = f'<div class="fecha">{published}</div>' if published is not None else ""
    return f'<html><head>{metadata}</head><body>{prefix}<article><h1>{title}</h1>{header_date}<p>{body}</p></article>{suffix}</body></html>'


def native_detail(published="9 oct. 2026", title=TITLE, body=BODY, related="", metadata=""):
    header_date = f'<div class="fecha-noticia">{published}</div>' if published is not None else ""
    return (f'<html><head>{metadata}</head><div class="noticias"><div class="noticia-conteiner">'
            f'<div class="cabecera-noticia"><h1 class="titulo-noticia">{title}</h1>{header_date}</div>'
            f'<div class="noticia-body"><div class="noticia-content"><div class="text-noticia"><p>{body}</p>'
            f'</div></div></div></div><div class="noticias-relacionadas">{related}</div></div></html>')


def scout(mapping, **kwargs):
    calls = []
    def load(url):
        calls.append(url)
        result = mapping[url]
        if isinstance(result, Exception):
            raise result
        return result
    source = MutualNewsScout(fetcher=load, as_of=TODAY, **kwargs)
    return source, calls


def test_detail_query_is_preserved_and_article_ids_remain_distinct():
    first, second = detail_url("first"), detail_url("second")
    assert _detail_url(first) == first
    assert _detail_url(second) == second
    assert _detail_url(first + "#not-evidence") == first
    assert first != second and urlsplit(first).path == urlsplit(second).path


@pytest.mark.parametrize("url", [
    PAGE, "http://www.mutual.cl/" + detail_url("a").split("?", 1)[1],
    detail_url("a").replace("www.mutual.cl", "www.mutual.cl.evil.test"),
    detail_url("a").replace(DETAIL_PAGE, "noticias"),
    detail_url("a").replace("SA_Noticias_Detalle", "SA_Private"),
    detail_url(""),
    detail_url("a") + "&page=other",
])
def test_nonarticle_or_unofficial_links_are_not_discoverable(url):
    assert _detail_url(url) is None


def test_listing_reads_all_category_components_and_native_full_dates():
    html = listing(branch(0, card("new")), branch(1, card("older", "16 sept. 2026"), "p0/OBSERVED=GH=/"))
    parsed = parse_listing(html, as_of=TODAY)
    assert parsed["client_union_pagination"]
    assert list(parsed["branches"]) == ["component-0", "component-1"]
    assert parsed["branches"]["component-1"]["cards"][0]["listing_date"] == "2026-09-16"
    assert parsed["branches"]["component-1"]["next_url"] == urljoin(PAGE, "p0/OBSERVED=GH=/")


@pytest.mark.parametrize("published", ["31 sept. 2026", "12 oct. 2026", "Datos del 9 oct. 2026", "oct. 2026", ""])
def test_invalid_future_partial_or_period_dates_do_not_supply_publication(published):
    source, _ = scout({PAGE: listing(branch(0, card("invalid", published)))})
    report = source.discover_inventory()
    assert report["rows"][0]["status"] == "pending"
    assert report["raw_items"] == [] and not report["coverage_complete"]


def test_detail_native_publication_header_has_explicit_evidence():
    parsed = parse_detail(detail(), detail_url("one"), as_of=TODAY)
    assert parsed["event_date"] == "2026-10-09"
    assert parsed["evidence"] == {"url": detail_url("one"), "kind": "publisher:mutual_div_fecha",
                                   "value": "9 oct. 2026", "date": "2026-10-09"}


def test_live_native_markup_binds_header_and_excludes_related_materiality():
    body = "Los trabajadores asistieron a una jornada de sensibilización y recibieron consejos de autocuidado. " * 3
    title = "Mutual impulsa jornada de autocuidado"
    related = ('<div class="title-noticias">Noticias relacionadas</div>'
               '<div class="card-noticia-relacionada"><div class="fecha-noticia-relacionada">30 ene. 2026</div>'
               '<p>Mutual inaugura nueva clínica con inversión de $100 millones.</p></div>')
    html = native_detail(title=title, body=body, related=related)
    parsed = parse_detail(html, detail_url("one"), as_of=TODAY)
    assert parsed["body"] == body.strip() and "inversión" not in parsed["body"]
    assert parsed["event_date"] == "2026-10-09"
    assert parsed["evidence"]["kind"] == "publisher:mutual_detail_fecha"
    source, _ = scout({PAGE: listing(branch(0, card("one", title=title))), detail_url("one"): html})
    report = source.discover_inventory()
    assert report["coverage_complete"] and report["rows"][0]["status"] == "rejected"


def test_native_related_dates_do_not_supply_missing_article_publication():
    parsed = parse_detail(native_detail(None, related='<div class="fecha-noticia">9 oct. 2026</div>'),
                          detail_url("one"), as_of=TODAY)
    assert parsed["event_date"] is None and parsed["reason"] == "missing_publication_date"


def test_native_conflicting_metadata_and_header_date_fail_closed():
    parsed = parse_detail(native_detail(metadata='<meta property="article:published_time" content="2026-10-08">'),
                          detail_url("one"), as_of=TODAY)
    assert parsed["event_date"] is None and parsed["reason"] == "conflicting_publication_dates"


def test_native_container_structure_changes_are_pending_not_generic_fallback():
    html = native_detail().replace('class="text-noticia"', 'class="changed-body"')
    parsed = parse_detail(html, detail_url("one"), as_of=TODAY)
    assert parsed["event_date"] is None and parsed["reason"] == "article_structure_unrecognized"


@pytest.mark.parametrize("final", [
    PAGE + "noticias_detalle/one/",
    PAGE + "noticias_detalle/one/!ut/p/z1/OBSERVED/dz/d5/STATE/",
    detail_url("one"),
])
def test_official_query_to_permalink_redirect_preserves_exact_article_identity(final):
    assert same_article_url(detail_url("one"), final)


@pytest.mark.parametrize("final", [
    PAGE + "noticias_detalle/another/",
    PAGE + "noticias_detalle/one/private/",
    PAGE + "noticias_detalle/one/?article=another",
    PAGE,
    PAGE.replace("www.mutual.cl", "example.test") + "noticias_detalle/one/",
    "https://www.mutual.cl/portal/privado/noticias_detalle/one/",
])
def test_unrelated_or_unofficial_redirect_never_preserves_article_identity(final):
    assert not same_article_url(detail_url("one"), final)


def test_dates_in_navigation_related_cards_and_body_are_not_header_evidence():
    html = detail(None, prefix='<nav><div class="fecha">1 oct. 2026</div></nav>',
                  body=BODY + " Jornada realizada el 9 de octubre de 2026.",
                  suffix='<div class="card-noticia"><div class="fecha">9 oct. 2026</div></div><div class="fecha">7 oct. 2026</div>')
    parsed = parse_detail(html, detail_url("one"), as_of=TODAY)
    assert parsed["event_date"] is None and parsed["reason"] == "missing_publication_date"


@pytest.mark.parametrize("published,metadata,reason", [
    ("8 oct. 2026", '<meta property="article:published_time" content="2026-10-09">', "conflicting_publication_dates"),
    ("12 oct. 2026", "", "invalid_publication_date"),
    ("9 oct. 2026", '<meta property="article:published_time" content="bogus">', "invalid_publication_date"),
])
def test_invalid_or_conflicting_declared_detail_date_fails_closed(published, metadata, reason):
    parsed = parse_detail(detail(published, metadata=metadata), detail_url("one"), as_of=TODAY)
    assert parsed["event_date"] is None and parsed["reason"] == reason


def test_missing_detail_date_uses_exact_card_binding_with_listing_and_detail_hashes():
    url = detail_url("one")
    source, _ = scout({PAGE: listing(branch(0, card("one"))), url: detail(None)})
    report = source.discover_inventory()
    evidence = report["raw_items"][0].metadata["publication_date_evidence"]
    assert report["coverage_complete"] and report["rows"][0]["status"] == "candidate"
    assert evidence["url"] == PAGE and evidence["item_url"] == url
    assert evidence["kind"] == "publisher:mutual_card_fecha"
    assert evidence["date"] == "2026-10-09" and evidence["value"] == "9 oct. 2026"
    assert len(evidence["listing_sha256"]) == len(evidence["detail_sha256"]) == 64
    assert report["raw_items"][0].metadata["publication_date_source"] == evidence["kind"]


@pytest.mark.parametrize("html,reason", [
    (detail("8 oct. 2026"), "listing_detail_date_conflict"),
    (detail(None, title="Otra noticia institucional"), "missing_publication_date"),
    (detail(None, body="Resumen breve."), "missing_publication_date"),
    (detail("12 oct. 2026"), "invalid_publication_date"),
])
def test_listing_date_cannot_overwrite_detail_conflict_or_unverified_identity(html, reason):
    source, _ = scout({PAGE: listing(branch(0, card("one"))), detail_url("one"): html})
    report = source.discover_inventory()
    assert not report["coverage_complete"] and report["raw_items"] == []
    assert report["rows"][0]["reason"] == reason


def test_pagination_covers_categories_independently_and_stops_after_ninety_day_boundary():
    next_url = urljoin(PAGE, "p0/OBSERVED=GH=/")
    mapping = {PAGE: listing(branch(0, card("one")), branch(1, card("two", "1 sept. 2026"), "p0/OBSERVED=GH=/")),
               next_url: listing(branch(1, card("three", "1 ago. 2026") + card("boundary", "12 jul. 2026"), "p0/NO-FETCH=/")),
               detail_url("one"): detail(), detail_url("two"): detail("1 sept. 2026"),
               detail_url("three"): detail("1 ago. 2026")}
    source, calls = scout(mapping)
    report = source.discover_inventory()
    assert report["coverage_complete"] and len(report["pages"]) == 2
    assert len(report["raw_items"]) == 3
    assert report["metrics"]["30"]["dated_articles"] == 1
    assert report["metrics"]["90"]["candidates"] == 3
    assert detail_url("boundary") not in calls and urljoin(next_url, "p0/NO-FETCH=/") not in calls
    assert report["branches"][1]["reason"] == "crossed_90_day_cutoff"


def test_unordered_category_cannot_stop_early_at_older_item():
    next_url = urljoin(PAGE, "p0/NEXT=/")
    source, calls = scout({PAGE: listing(branch(0, card("old", "12 jul. 2026") + card("new"), "p0/NEXT=/")),
                           next_url: listing(branch(0, card("middle", "1 sept. 2026"))),
                           detail_url("new"): detail(), detail_url("middle"): detail("1 sept. 2026")})
    report = source.discover_inventory()
    assert next_url in calls and report["coverage_complete"]
    assert len(report["raw_items"]) == 2 and report["branches"][0]["reason"] == "branch_exhausted"


def test_repeated_paging_fails_coverage_without_infinite_requests():
    next_url = urljoin(PAGE, "p0/NEXT=/")
    page = listing(branch(0, card("one"), "p0/NEXT=/"))
    source, calls = scout({PAGE: page, next_url: page, detail_url("one"): detail()})
    report = source.discover_inventory()
    assert not report["coverage_complete"] and len(report["raw_items"]) == 1
    assert any(error["reason"] == "repeated_pagination_page" for error in report["errors"])
    assert calls.count(next_url) == 1


def test_failed_category_keeps_other_categories_and_exact_transport_attribution():
    next_url = urljoin(PAGE, "p0/NEXT=/")
    source, calls = scout({PAGE: listing(branch(0, card("one")), branch(1, card("two"), "p0/NEXT=/")),
                           next_url: URLError("Tunnel connection failed: 403 Forbidden"),
                           detail_url("one"): detail(), detail_url("two"): detail()})
    report = source.discover_inventory()
    assert not report["coverage_complete"] and len(report["raw_items"]) == 2
    assert report["errors"][0]["code"] == "executor_proxy_denied"
    assert "http_status" not in report["errors"][0] and next_url in calls


def test_origin_http_failure_keeps_status_and_other_article():
    source, _ = scout({PAGE: listing(branch(0, card("one") + card("two"))),
                       detail_url("one"): HTTPError(detail_url("one"), 503, "unavailable", {}, None),
                       detail_url("two"): detail()})
    report = source.discover_inventory()
    assert not report["coverage_complete"] and len(report["raw_items"]) == 1
    assert report["errors"][0]["code"] == "origin_http_status" and report["errors"][0]["http_status"] == 503


def test_malformed_card_is_recorded_instead_of_silent_complete_coverage():
    html = listing(branch(0, card("good") + '<div class="card-noticia"><div class="fecha">9 oct. 2026</div></div>'))
    source, _ = scout({PAGE: html, detail_url("good"): detail()})
    report = source.discover_inventory()
    assert not report["coverage_complete"] and len(report["raw_items"]) == 1
    assert report["errors"][0]["reason"] == "listing_card_identity_unrecognized"


def test_dropdown_category_missing_from_server_html_is_a_coverage_gap():
    html = listing(branch(0, card("good"))) + ('<select id="product-select"><option value="0">Todas</option>'
                                             '<option value="1">Salud laboral</option></select>')
    source, _ = scout({PAGE: html, detail_url("good"): detail()})
    report = source.discover_inventory()
    assert not report["coverage_complete"] and len(report["raw_items"]) == 1
    assert report["errors"][0]["reason"] == "listed_category_component_missing"
    assert report["errors"][0]["branch"] == "component-1"


def test_missing_next_link_is_not_treated_as_terminal_when_last_page_link_exists():
    html = listing(branch(0, card("good") + '<a id="pc123_lastPage" href="p0/LAST=/">Última</a>'))
    source, _ = scout({PAGE: html, detail_url("good"): detail()})
    report = source.discover_inventory()
    assert not report["coverage_complete"] and len(report["raw_items"]) == 1
    assert report["errors"][0]["reason"] == "pagination_next_link_missing"


def test_conflicting_repeated_card_binding_fails_closed():
    source, _ = scout({PAGE: listing(branch(0, card("one")), branch(1, card("one", "8 oct. 2026")))})
    report = source.discover_inventory()
    assert not report["coverage_complete"] and report["raw_items"] == []
    assert report["rows"][0]["reason"] == "invalid_or_conflicting_listing_date"


def test_max_pages_is_explicit_incomplete_and_does_not_discard_captured_article():
    source, _ = scout({PAGE: listing(branch(0, card("one"), "p0/NEXT=/")), detail_url("one"): detail()}, max_pages=1)
    report = source.discover_inventory()
    assert not report["coverage_complete"] and len(report["raw_items"]) == 1
    assert report["errors"][0]["reason"] == "max_pages_reached"


def test_no_silent_sixty_article_cap():
    mapping = {PAGE: listing(branch(0, "".join(card(str(i)) for i in range(61))))}
    mapping.update({detail_url(str(i)): detail() for i in range(61)})
    source, calls = scout(mapping)
    report = source.discover_inventory()
    assert report["coverage_complete"] and len(report["raw_items"]) == 61 and len(calls) == 62


def test_editorial_noise_is_discovered_rejected_with_verified_date():
    title, body = "Mutual realiza campaña de bienestar", "Los participantes recibieron consejos de prevención. " * 5
    source, _ = scout({PAGE: listing(branch(0, card("noise", title=title))), detail_url("noise"): detail(title=title, body=body)})
    report = source.discover_inventory()
    assert report["coverage_complete"] and report["rows"][0]["status"] == "rejected"
    assert report["rows"][0]["date_verified"] and len(report["raw_items"]) == 1
    assert not report["raw_items"][0].metadata["materiality_accepted"]


def test_waf_response_is_never_a_zero_item_healthy_listing():
    source, _ = scout({PAGE: '<iframe src="/_Incapsula_Resource"></iframe>'})
    report = source.discover_inventory()
    assert not report["coverage_complete"] and report["technical_status"] == "blocked"
    assert report["errors"][0]["code"] == "external_waf_challenge"


def test_default_transport_rejects_official_scope_violations_before_request():
    with pytest.raises(SourceDiscoveryError, match="unverified_official_url"):
        fetch_mutual_html("https://example.test/article")
    with pytest.raises(SourceDiscoveryError, match="unverified_official_url"):
        fetch_mutual_html("https://www.mutual.cl/portal/privado/profile")
    with pytest.raises(SourceDiscoveryError, match="redirect_outside_public_official_scope"):
        _OfficialRedirect().redirect_request(None, None, 302, "found", {}, "https://example.test/article")


@pytest.mark.parametrize("limit", [0, -1, True, "100"])
def test_page_limit_requires_positive_integer(limit):
    with pytest.raises(ValueError):
        MutualNewsScout(as_of=TODAY, max_pages=limit)
