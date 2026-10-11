"""Synthetic pagination regressions; these fixtures are not live captures."""
from datetime import date, timedelta

import pytest

from radar_salud.beta_sources import CuratedBetaSourceScout
from radar_salud.occupational_inventory import discover_inventory


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
