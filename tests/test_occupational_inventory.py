"""Synthetic pagination regressions plus a captured native IST API replay."""
from datetime import date, timedelta
import json
import hashlib
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from radar_salud.beta_sources import CuratedBetaSourceScout
from radar_salud.occupational_inventory import discover_inventory, enrich_inventory_from_ist_api, ist_api_url


AS_OF = date(2026, 10, 11)
ACHS = "https://www.achs.cl/centro-de-noticias"
ARTICLE = ACHS + "/noticia/2026/"
BODY = ("La nueva guía de tratamiento de patologías laborales incorpora recomendaciones "
        "para evaluación, atención clínica y reintegro laboral. Se implementa una nueva "
        "herramienta operativa para equipos tratantes, con evaluación y reportes de resultados.")


def detail(title="Nueva guía de tratamiento en salud mental laboral", published="2026-10-10", body=BODY):
    meta = f'<meta property="article:published_time" content="{published}T10:00:00-03:00">' if published else ""
    return meta + f"<article><h1>{title}</h1><p>{body}</p></article>"


def listing(urls, next_url=None, next_label="Siguiente", *, ist=False, rel="next"):
    articles = "".join(f'<h2><a href="{url}">Una noticia de salud laboral {index}</a></h2>'
                       if ist else f'<a href="{url}">Ver detalle</a>'
                       for index, url in enumerate(urls))
    return articles + (f'<a href="{next_url}" rel="{rel}">{next_label}</a>' if next_url else "")


def loader_for(pages):
    visited = []
    def load(url):
        visited.append(url)
        value = pages[url]
        if isinstance(value, Exception):
            raise value
        return value
    return load, visited


def test_achs_follows_observed_numeric_next_links_and_closes_at_verified_boundary():
    urls = [ARTICLE + slug for slug in ("latest", "thirty", "ninety", "older")]
    pages = {
        ACHS: listing(urls[:1], ACHS + "/2", next_label="2", rel=""),
        ACHS + "/2": listing(urls[1:3], ACHS + "/3", next_label="3", rel=""),
        ACHS + "/3": listing(urls[3:]),
        urls[0]: detail(published="2026-10-11"),
        urls[1]: detail(published="2026-09-11"),
        urls[2]: detail(published="2026-07-13"),
        urls[3]: detail(published="2026-07-12"),
    }
    load, visited = loader_for(pages)
    scout = CuratedBetaSourceScout("achs_seguro_laboral")
    scout.decisions = [{"untouched": True}]
    result = discover_inventory(scout, load, as_of=AS_OF)
    assert result["coverage_complete"] is True
    assert result["stop_reason"] == "verified_older_boundary"
    assert result["window"]["start_90"] == "2026-07-13"
    assert result["window"]["convention"] == "rolling_elapsed_days_inclusive"
    assert result["metrics"]["30"]["dated_articles"] == 2
    assert result["metrics"]["90"]["dated_articles"] == 3
    assert len(result["raw_items"]) == 3
    assert result["rows"][-1]["status"] == "outside_window"
    assert result["outside_boundary"]["date"] == "2026-07-12"
    assert [row["url"] for row in result["pages"]] == [ACHS, ACHS + "/2", ACHS + "/3"]
    assert visited.count(urls[0]) == 1
    assert scout.decisions == [{"untouched": True}]


def test_ist_preserves_actual_query_and_category_pagination_without_navigation_candidates():
    root = "https://ist.cl/noticias/"
    second = "https://ist.cl/noticias/page/2/?et_blog"
    first, old = "https://ist.cl/nueva-guia/", "https://ist.cl/nota-anterior/"
    pages = {
        root: '<nav><h2><a href="/historia/">Historia del IST</a></h2></nav>' + listing([first], second, "« Entradas más antiguas", ist=True, rel=""),
        second: listing([old], ist=True),
        first: detail(published="2026-10-07"), old: detail(published="2026-07-12"),
    }
    load, visited = loader_for(pages)
    result = discover_inventory(CuratedBetaSourceScout("ist"), load, AS_OF)
    assert result["coverage_complete"]
    assert second in visited and "https://ist.cl/historia/" not in visited
    assert len(result["rows"]) == 2
    assert result["pages"][0]["next_url"] == second


def test_category_archive_is_followed_only_when_seen_as_the_next_anchor():
    scout = CuratedBetaSourceScout("ist")
    scout.cfg = {**scout.cfg, "page": "https://ist.cl/category/noticias/"}
    root, second = scout.cfg["page"], "https://ist.cl/category/noticias/page/2/"
    first, old = "https://ist.cl/nueva-guia/", "https://ist.cl/nota-anterior/"
    load, visited = loader_for({root: listing([first], second, "Entradas más antiguas", ist=True, rel=""),
                               second: listing([old], ist=True), first: detail(), old: detail(published="2026-07-12")})
    result = discover_inventory(scout, load, AS_OF)
    assert result["coverage_complete"] and second in visited


def test_more_than_sixty_details_are_inventoried_and_editorial_rejections_are_retained():
    urls = [ARTICLE + f"story-{index}" for index in range(65)]
    old = ARTICLE + "older"
    pages = {ACHS: listing(urls, ACHS + "/2"), ACHS + "/2": listing([old]),
             old: detail(published="2026-07-12")}
    pages.update({url: detail(title="Campaña por salud mental laboral", published="2026-10-10",
                             body="La actividad educativa promueve bienestar y consejos generales entre personas trabajadoras. " * 4)
                  for url in urls})
    load, visited = loader_for(pages)
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF)
    assert result["coverage_complete"]
    assert len(result["rows"]) == 66 and len(result["raw_items"]) == 65
    assert result["metrics"]["90"]["rejected"] == 65
    assert all(row["reason"] == "campaign_event_testimonial_or_recognition" for row in result["rows"][:65])
    assert all(visited.count(url) == 1 for url in urls)


def test_distinct_provider_clinic_centers_and_mutuality_roles_remain_explicit():
    guide, clinic, centers, old = [ARTICLE + part for part in ("guide", "clinic", "centers", "old")]
    pages = {ACHS: listing([guide, clinic, centers, old]), guide: detail(published="2026-10-10"),
             clinic: detail("Clínicas Achs Salud activa SAFED de Fonasa", "2026-09-28",
                            "Clínicas Achs Salud incorpora Clínica Atacama a SAFED de Fonasa, habilitando consultas, " * 4),
             centers: detail("Master Plan Achs Salud: modernizamos centros y ampliamos servicios", "2026-09-20",
                             "Nuevo Centro San Javier. Fuera de horario acudir a Clínica Lircay Achs Salud. " * 4),
             old: detail(published="2026-07-12")}
    load, _ = loader_for(pages)
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF)
    assert result["coverage_complete"]
    assert [row["market_role"] for row in result["rows"][:3]] == ["mutuality", "provider_achs", "provider_achs_centers"]
    assert [row["status"] for row in result["rows"][:3]] == ["candidate", "excluded_role", "excluded_role"]
    assert result["metrics"]["90"]["excluded_role"] == 2
    assert [item.url for item in result["raw_items"]] == [guide]
    load, _ = loader_for(pages)
    clinic_result = discover_inventory(CuratedBetaSourceScout("clinicas_achs_salud"), load, AS_OF)
    assert [item.url for item in clinic_result["raw_items"]] == [clinic, centers]
    provider_rows = [row for row in clinic_result["rows"] if row["status"] == "candidate"]
    assert [row["provider_subtype"] for row in provider_rows] == ["clinicas", "centros"]
    assert clinic_result["metrics"]["90"]["expected_role"] == 2


def test_detail_failure_preserves_valid_items_and_does_not_certify_coverage():
    valid, bad, old = [ARTICLE + part for part in ("valid", "timeout", "old")]
    load, visited = loader_for({ACHS: listing([valid, bad, old]), valid: detail(),
                               bad: TimeoutError("detail request timed out"), old: detail(published="2026-07-12")})
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF)
    assert not result["coverage_complete"]
    assert len(result["rows"]) == 3 and [item.url for item in result["raw_items"]] == [valid]
    assert result["rows"][1]["status"] == "pending"
    assert any(error["url"] == bad for error in result["errors"])
    assert old in visited


@pytest.mark.parametrize("bad_detail", [detail(published=""), detail(published="2026-10-12"),
                                       detail(published="31/02/2026"),
                                       detail(published="") + "<footer>07/10/2026</footer>"])
def test_unknown_invalid_future_or_footer_dates_cannot_close_inventory(bad_detail):
    unknown, old = ARTICLE + "unknown", ARTICLE + "old"
    load, _ = loader_for({ACHS: listing([unknown, old]), unknown: bad_detail, old: detail(published="2026-07-12")})
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF)
    assert result["coverage_complete"] is False
    assert result["rows"][0]["publication_date"] is None
    assert result["unknown_publication_dates"] == 1


def test_archive_failure_records_exact_url_after_preserving_prior_page():
    url = ARTICLE + "latest"
    load, _ = loader_for({ACHS: listing([url], ACHS + "/2"), url: detail(),
                         ACHS + "/2": ConnectionError("archive connection reset")})
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF)
    assert not result["coverage_complete"] and len(result["raw_items"]) == 1
    assert result["pages"][-1]["status"] == "blocked"
    assert result["errors"][-1]["url"] == ACHS + "/2"


@pytest.mark.parametrize("next_url,code", [(ACHS, "pagination_cycle"),
                                          (ACHS + "/3", "pagination_gap"),
                                          ("http://www.achs.cl/centro-de-noticias/2", "unsafe_next_page"),
                                          ("https://foreign.example/archive/2", "unsafe_next_page"),
                                          ("https://www.achs.cl/unrelated/2", "unrecognized_next_page")])
def test_cycle_gap_and_unsafe_next_links_never_trigger_a_request(next_url, code):
    url = ARTICLE + "latest"
    load, visited = loader_for({ACHS: listing([url], next_url), url: detail()})
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF)
    assert not result["coverage_complete"]
    assert any(error["code"] == code for error in result["errors"])
    assert len(visited) == 2


def test_max_page_limit_does_not_convert_a_recent_sample_to_complete_inventory():
    url = ARTICLE + "latest"
    load, visited = loader_for({ACHS: listing([url], ACHS + "/2"), url: detail()})
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF, max_pages=1)
    assert result["stop_reason"] == "max_pages_exhausted" and not result["coverage_complete"]
    assert ACHS + "/2" not in visited


def test_no_pagination_or_old_boundary_leaves_a_one_page_sample_incomplete():
    url = ARTICLE + "latest"
    load, visited = loader_for({ACHS: listing([url]), url: detail()})
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF)
    assert result["stop_reason"] == "no_verified_older_boundary"
    assert not result["coverage_complete"] and len(visited) == 2


def test_chronology_violation_blocks_completion_even_with_an_old_boundary():
    first, second, old = [ARTICLE + part for part in ("first", "second", "old")]
    load, _ = loader_for({ACHS: listing([first, second, old]), first: detail(published="2026-09-01"),
                         second: detail(published="2026-10-10"), old: detail(published="2026-07-12")})
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF)
    assert not result["coverage_complete"]
    assert any(error["code"] == "publication_order_not_monotonic" for error in result["errors"])


def test_duplicate_articles_across_pages_are_counted_and_loaded_once():
    first, old = ARTICLE + "first", ARTICLE + "old"
    load, visited = loader_for({ACHS: listing([first], ACHS + "/2"), ACHS + "/2": listing([first, old]),
                               first: detail(), old: detail(published="2026-07-12")})
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF)
    assert result["coverage_complete"] and len(result["rows"]) == 2
    assert visited.count(first) == 1


def test_as_of_controls_both_publication_validation_and_rolling_metrics():
    historical = date(2025, 10, 11)
    first, boundary = ARTICLE + "historical", ARTICLE + "boundary"
    load, _ = loader_for({ACHS: listing([first, boundary]), first: detail(published="2025-10-10"),
                         boundary: detail(published=(historical - timedelta(days=91)).isoformat())})
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, historical)
    assert result["coverage_complete"]
    assert [item.event_date for item in result["raw_items"]] == ["2025-10-10"]


def test_unrecognized_listing_and_invalid_page_budget_cannot_claim_success():
    load, _ = loader_for({ACHS: "<h1>Noticias</h1><p>No verified article structure</p>"})
    result = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF)
    assert not result["coverage_complete"] and not result["rows"]
    with pytest.raises(ValueError, match="max_pages"):
        discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, AS_OF, 0)


def test_mutual_waf_challenge_is_not_a_zero_article_inventory():
    scout = CuratedBetaSourceScout("mutual_seguridad")
    load, _ = loader_for({scout.cfg["page"]: '<iframe src="/_Incapsula_Resource?incident_id=example"></iframe>'})
    result = discover_inventory(scout, load, AS_OF)
    assert not result["coverage_complete"] and result["technical_status"] == "blocked"
    assert result["errors"][0]["code"] == "external_waf_challenge"


@pytest.mark.parametrize("archive", ["http://www.achs.cl/centro-de-noticias",
                                     "https://[broken/centro-de-noticias"])
def test_unsafe_or_malformed_starting_archives_are_reported_without_fetching(archive):
    scout = CuratedBetaSourceScout("achs_seguro_laboral")
    scout.cfg = {**scout.cfg, "page": archive}
    load, visited = loader_for({})
    result = discover_inventory(scout, load, AS_OF)
    assert result["technical_status"] == "blocked"
    assert result["stop_reason"] == "unsafe_archive_url"
    assert result["pages"][0]["status"] == "blocked"
    assert not visited


IST_FIRST = "https://ist.cl/nueva-guia/"
IST_OLD = "https://ist.cl/nota-anterior/"
IST_REPORT = "https://ist.cl/reporte-sostenibilidad-2025/"


def ist_baseline(published="2026-10-10"):
    scout = CuratedBetaSourceScout("ist")
    load, _ = loader_for({scout.cfg["page"]: listing([IST_FIRST, IST_OLD], ist=True),
                          IST_FIRST: detail(published=published), IST_OLD: detail(published="2026-07-12")})
    return scout, discover_inventory(scout, load, AS_OF)


def api_post(url=IST_FIRST, identifier=1, published="2026-10-10T11:00:00", visible="10/10/2026",
             title="Nueva guía de tratamiento en salud mental laboral", categories=(14,)):
    return {"id": identifier, "link": url, "status": "publish", "date": published,
            "date_gmt": "2026-10-12T00:00:00", "modified": "2026-10-11T12:00:00",
            "categories": list(categories), "title": {"rendered": title},
            "content": {"rendered": (f"<p>{visible}</p>" if visible else "") + f"<h1>{title}</h1><p>{BODY}</p>"}}


def report_post():
    return api_post(IST_REPORT, 2, "2026-07-14T14:52:49", visible="",
                    title="Reporte Sostenibilidad 2025", categories=(1,))


def test_api_adds_official_report_with_verified_detail_and_keeps_data_period_separate():
    scout, baseline = ist_baseline()
    endpoint = ist_api_url(AS_OF)
    load, _ = loader_for({endpoint: json.dumps([api_post(), report_post()]),
                          IST_REPORT: detail("Reporte de Sostenibilidad IST 2025", "2026-07-14")})
    result = enrich_inventory_from_ist_api(baseline, scout, load, api_url=endpoint,
                                         api_headers={"X-WP-Total": "2", "X-WP-TotalPages": "1"})
    assert result["coverage_complete"] and result["ist_api"]["response_complete"]
    assert result["ist_api"]["additional_urls"] == [IST_REPORT]
    row = next(row for row in result["rows"] if row["url"] == IST_REPORT)
    assert row["publication_date"] == "2026-07-14" and row["data_period"] == "2025"
    assert row["type"] == "report" and row["section"] == "publicaciones_institucionales"
    item = next(item for item in result["raw_items"] if item.url == IST_REPORT)
    assert item.event_date == "2026-07-14"
    assert item.metadata["publication_evidence"]["url"] == IST_REPORT
    assert item.metadata["api_publication_evidence"]["value"] == "2026-07-14T14:52:49"
    assert len(baseline["rows"]) == 2 and len(result["rows"]) == 3
    assert result["metrics"]["90"]["dated_articles"] == 2


def test_api_visible_header_date_conflict_removes_existing_raw_and_leaves_pending():
    scout, baseline = ist_baseline("2026-08-12")
    endpoint = ist_api_url(AS_OF)
    post = api_post(published="2026-08-12T11:38:53", visible="10/08/2026")
    load, visited = loader_for({endpoint: json.dumps([post])})
    result = enrich_inventory_from_ist_api(baseline, scout, load, api_headers={"x-wp-total": "1", "x-wp-totalpages": "1"})
    row = next(row for row in result["rows"] if row["url"] == IST_FIRST)
    assert row["publication_date"] is None and row["status"] == "pending"
    assert row["reason"] == "api_visible_publication_date_conflict"
    assert not result["raw_items"] and not result["coverage_complete"]
    assert visited == [endpoint]


def test_api_missing_headers_still_discovers_details_but_does_not_claim_complete_capture():
    scout, baseline = ist_baseline()
    endpoint = ist_api_url(AS_OF)
    load, _ = loader_for({endpoint: json.dumps([api_post(), report_post()]),
                          IST_REPORT: detail("Reporte de Sostenibilidad IST 2025", "2026-07-14")})
    result = enrich_inventory_from_ist_api(baseline, scout, load)
    assert IST_REPORT in result["ist_api"]["additional_urls"]
    assert any(item.url == IST_REPORT for item in result["raw_items"])
    assert not result["ist_api"]["response_complete"] and not result["coverage_complete"]
    assert any(error["code"] == "api_total_headers_missing" for error in result["errors"])


def test_api_pagination_uses_verified_total_contract_and_preserves_first_page_on_failure():
    scout, baseline = ist_baseline()
    endpoint = ist_api_url(AS_OF).replace("per_page=100", "per_page=1")
    second = endpoint + "&page=2"
    headers = lambda url: [{"x-wp-total": "2", "x-wp-totalpages": "2"}]
    load, visited = loader_for({endpoint: json.dumps([api_post()]), second: json.dumps([report_post()]),
                               IST_REPORT: detail("Reporte de Sostenibilidad IST 2025", "2026-07-14")})
    result = enrich_inventory_from_ist_api(baseline, scout, load, api_url=endpoint, api_headers=headers)
    assert result["coverage_complete"] and second in visited
    assert [page["page_number"] for page in result["ist_api"]["pages"]] == [1, 2]
    load, _ = loader_for({endpoint: json.dumps([api_post()]), second: TimeoutError("API page two timeout")})
    partial = enrich_inventory_from_ist_api(baseline, scout, load, api_url=endpoint, api_headers=headers)
    assert not partial["coverage_complete"] and not partial["ist_api"]["response_complete"]
    assert partial["raw_items"][0].url == IST_FIRST
    assert partial["errors"][-1]["url"] == second


def test_api_date_gmt_and_modified_never_replace_missing_native_publication_date():
    scout, baseline = ist_baseline()
    endpoint = ist_api_url(AS_OF)
    load, _ = loader_for({endpoint: json.dumps([api_post(published=None, visible="")])})
    result = enrich_inventory_from_ist_api(baseline, scout, load, api_headers={"x-wp-total": "1", "x-wp-totalpages": "1"})
    assert not result["raw_items"]
    assert result["rows"][0]["publication_date"] is None
    assert result["rows"][0]["reason"] == "api_publication_date_invalid"


def test_old_native_publication_modified_recently_cannot_keep_a_current_raw_item():
    scout, baseline = ist_baseline()
    endpoint = ist_api_url(AS_OF)
    load, _ = loader_for({endpoint: json.dumps([api_post(published="2016-08-25T10:22:31", visible="25/08/2016")])})
    result = enrich_inventory_from_ist_api(baseline, scout, load, api_headers={"x-wp-total": "1", "x-wp-totalpages": "1"})
    assert not result["raw_items"] and not result["coverage_complete"]
    assert result["rows"][0]["publication_date"] is None
    assert result["rows"][0]["reason"] == "api_publication_outside_requested_window"


def test_api_does_not_use_a_landing_page_date_or_native_date_to_promote_unverified_detail():
    scout, baseline = ist_baseline()
    endpoint = ist_api_url(AS_OF)
    load, _ = loader_for({endpoint: json.dumps([api_post(), report_post()]),
                          IST_REPORT: detail("Reporte de Sostenibilidad IST 2025", "2016-08-25")})
    result = enrich_inventory_from_ist_api(baseline, scout, load, api_headers={"x-wp-total": "2", "x-wp-totalpages": "1"})
    row = next(row for row in result["rows"] if row["url"] == IST_REPORT)
    assert row["status"] == "pending" and row["publication_date"] is None
    assert all(item.url != IST_REPORT for item in result["raw_items"])
    assert row["reason"] == "api_detail_publication_unverified"


def test_observed_midnight_lower_bound_is_a_complete_response_with_explicit_window_limit():
    scout, baseline = ist_baseline()
    endpoint = "https://ist.cl/wp-json/wp/v2/posts?per_page=100&after=2026-07-13T00%3A00%3A00&before=2026-10-12T00%3A00%3A00"
    load, _ = loader_for({endpoint: json.dumps([api_post()])})
    result = enrich_inventory_from_ist_api(baseline, scout, load, api_url=endpoint,
                                         api_headers={"x-wp-total": "1", "x-wp-totalpages": "1"})
    assert result["ist_api"]["response_complete"]
    assert not result["ist_api"]["inclusive_90_day_bounds"] and not result["coverage_complete"]
    assert parse_qs(urlsplit(ist_api_url(AS_OF)).query)["after"] == ["2026-07-12T23:59:59"]


@pytest.mark.parametrize("endpoint", ["https://foreign.example/wp-json/wp/v2/posts?per_page=100",
                                      "http://ist.cl/wp-json/wp/v2/posts?per_page=100",
                                      ist_api_url(AS_OF) + "&page=2"])
def test_api_route_and_starting_page_guards_prevent_any_request(endpoint):
    scout, baseline = ist_baseline()
    load, visited = loader_for({})
    with pytest.raises(ValueError):
        enrich_inventory_from_ist_api(baseline, scout, load, api_url=endpoint)
    assert not visited


def test_captured_live_api_keeps_all_twenty_one_posts_and_pending_unverified_details():
    base = Path(__file__).resolve().parents[1] / "data/audits/source_e_recovery/actions/38115274609"
    capture = json.loads((base / "report.json").read_text())
    record = next(row for row in capture["records"] if row.get("surface") == "api_90_days")
    hop = record["hops"][-1]
    body = (base / hop["body_file"]).read_text()
    assert record["http_status"] == 200 and hop["tls"]["verified"]
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == hop["sha256"]
    scout = CuratedBetaSourceScout("ist")
    report = {"source_slug": "ist", "as_of": AS_OF.isoformat(), "rows": [], "raw_items": [],
              "pages": [], "errors": [], "coverage_complete": False,
              "metrics": {"30": {}, "90": {}}}
    visited = []
    def load(url):
        visited.append(url)
        if url == record["url"]:
            return body
        raise LookupError("Linked detail was not captured in this route-probe run")
    result = enrich_inventory_from_ist_api(report, scout, load, api_url=record["url"], api_headers=hop["headers"])
    assert result["ist_api"]["response_complete"]
    assert len(result["ist_api"]["posts"]) == 21 and len(result["rows"]) == 21
    report_row = next(row for row in result["rows"] if row["url"] == IST_REPORT)
    assert report_row["api_publication_evidence"]["date"] == "2026-07-14"
    assert report_row["data_period"] == "2025" and report_row["status"] == "pending"
    tps_url = "https://ist.cl/realizamos-una-exitosa-jornada-preventiva-en-tps/"
    tps = next(row for row in result["rows"] if row["url"] == tps_url)
    assert tps["reason"] == "api_visible_publication_date_conflict" and tps_url not in visited
    assert not result["raw_items"] and not result["coverage_complete"]


def test_real_ist_details_recover_cms_months_without_promoting_conflict_or_missing_report():
    audit = Path(__file__).resolve().parents[1] / "data/audits/source_e_recovery/actions"
    capture = json.loads((audit / "38115274609/report.json").read_text())
    api_record = next(row for row in capture["records"] if row.get("surface") == "api_90_days")
    api_hop = api_record["hops"][-1]
    index = json.loads((audit / "38116209530/inventory/capture_index.json").read_text())
    repo = Path(__file__).resolve().parents[1]
    visited = []

    def load(url):
        visited.append(url)
        record = api_record if url == api_record["url"] else index[url]
        hop = record["hops"][-1]
        path = (audit / "38115274609" if record is api_record else repo / record["artifact_dir"])
        body = (path / hop["body_file"]).read_bytes().decode("utf-8")
        assert record["http_status"] == 200 and hop["tls"]["verified"]
        assert hashlib.sha256(body.encode("utf-8")).hexdigest() == hop["sha256"]
        return body

    baseline = {"source_slug": "ist", "as_of": AS_OF.isoformat(), "rows": [], "raw_items": [],
                "pages": [], "errors": [], "coverage_complete": False,
                "metrics": {"30": {}, "90": {}}}
    result = enrich_inventory_from_ist_api(baseline, CuratedBetaSourceScout("ist"), load,
        api_url=api_record["url"], api_headers=api_hop["headers"])
    assert len(result["ist_api"]["posts"]) == 21 and result["ist_api"]["response_complete"]
    assert len(result["raw_items"]) == 19
    assert result["metrics"]["90"]["dated_articles"] == 19
    rows = {row["url"]: row for row in result["rows"]}
    tps = "https://ist.cl/realizamos-una-exitosa-jornada-preventiva-en-tps/"
    assert rows[tps]["reason"] == "api_visible_publication_date_conflict"
    assert rows[tps]["publication_date"] is None and tps not in visited
    assert rows[IST_REPORT]["status"] == "pending" and rows[IST_REPORT]["data_period"] == "2025"
    assert rows[IST_REPORT]["publication_date"] is None
    assert rows[IST_REPORT]["api_publication_evidence"]["date"] == "2026-07-14"
    ebco = "https://ist.cl/dimos-inicio-a-la-semana-de-la-seguridad-junto-a-ebco/"
    assert rows[ebco]["publication_date"] == "2026-10-05"
    for item in result["raw_items"]:
        assert item.metadata["publication_date"] == rows[item.url]["api_publication_evidence"]["date"]
        assert item.metadata["publication_evidence"]["url"] == item.url
    assert not result["coverage_complete"] and not result["ist_api"]["inclusive_90_day_bounds"]
