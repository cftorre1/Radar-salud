"""Daily run 28-oct-2026 02:12 UTC: explicit causes for four source errors.

ACHS fixtures start from the real achs.cl article captured by Actions run
38116209530 (11-oct-2026). The only recorded fact about the 28-oct failure is
the extracted H1, "Upgraded to Sitefinity {{currentVersion}}", on five article
URLs (data/state/occupational_source_discovery.json); the placeholder variants
below reproduce exactly that heading. datos.gob.cl uses the real FONASA CKAN
capture of run 38117618594.
"""
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urljoin

import pytest

from radar_salud import occupational_sources as sources
from radar_salud.beta_sources import CuratedBetaSourceScout, coverage_gap_diagnostics
from radar_salud.datos_gob_sources import DatosGobScout, ROBOTS
from radar_salud.isp_sources import IspSurveillanceScout
from radar_salud.occupational_inventory import discover_inventory

ROOT = Path(__file__).resolve().parents[1]
ACHS_CAPTURE = ROOT / "data/audits/source_e_recovery/actions/38116209530/inventory/capture/a2b95068261acc188842-0.body"
INNOVAR = "https://www.achs.cl/centro-de-noticias/noticia/2026/innovar-para-llegar-a-tiempo"
FONASA = ROOT / ("data/audits/public_sources_c_20261011/recovery/runs/38117618594/captures/"
                 "16a36dc92d59e1da36982c7b864e908b371d3529a0c5bc5d87cedad11b023490.html")
AS_OF = date(2026, 10, 28)
PLACEHOLDER = "Upgraded to Sitefinity {{currentVersion}}"


def real_article():
    return ACHS_CAPTURE.read_text(encoding="utf-8")


def placeholder_only():
    # Same page shell, the article section replaced by the CMS template H1.
    html = real_article()
    start = html.index('<section class="c-interior mb-small"')
    end = html.index("</section>", start) + len("</section>")
    template = ('<section class="sf-upgrade"><h1>' + PLACEHOLDER + '</h1>'
                '<p>Sitefinity has been upgraded. ' + "Lorem ipsum " * 20 + '</p></section>')
    return html[:start] + template + html[end:]


def placeholder_before_article():
    html = real_article()
    start = html.index('<section class="c-interior mb-small"')
    notice = '<div class="sf-upgrade"><h1>' + PLACEHOLDER + '</h1><p>What is new in this version.</p></div>'
    return html[:start] + notice + html[start:]


def test_real_capture_still_binds_native_achs_header_date():
    article = sources.Article(url=INNOVAR)
    article.feed(real_article())
    title, published, _, kind = article.result(today=AS_OF)
    assert (title, published, kind) == ("Innovar para llegar a tiempo", "2026-08-25", "publisher:achs_div_fecha")
    assert not article.cms_placeholder


def test_placeholder_heading_is_never_a_title_and_does_not_hide_the_real_header():
    article = sources.Article(url=INNOVAR)
    article.feed(placeholder_before_article())
    title, published, _, kind = article.result(today=AS_OF)
    assert article.cms_placeholder
    assert (title, published, kind) == ("Innovar para llegar a tiempo", "2026-08-25", "publisher:achs_div_fecha")


def _scout(page="https://www.achs.cl/centro-de-noticias"):
    cfg = CuratedBetaSourceScout("achs_seguro_laboral").cfg
    return SimpleNamespace(slug="achs_seguro_laboral", cfg={**cfg, "page": page}, decisions=[], diagnostics=[])


def test_placeholder_only_page_is_an_explicit_external_pending_not_a_missing_date():
    scout = _scout()
    listing = f'<a href="{INNOVAR}">Innovar para llegar a tiempo</a>'
    with pytest.raises(sources.SourceDiscoveryError) as caught:
        sources.discover_items(scout, listing, lambda url: placeholder_only(), as_of=AS_OF)
    assert caught.value.code == "publisher_cms_placeholder"
    diagnostic = scout.diagnostics[0]
    assert diagnostic["code"] == "publisher_cms_placeholder" and diagnostic["external"] is True
    assert scout.decisions[0]["status"] == "pending" and scout.decisions[0]["reason"] == "publisher_cms_placeholder"


def test_inventory_stops_at_the_crossed_boundary_and_keeps_the_gap_explicit():
    page = "https://www.achs.cl/centro-de-noticias"
    article = "https://www.achs.cl/centro-de-noticias/noticia/2026/"
    old = article + "antigua"
    old_html = real_article().replace("25/08/2026", "01/07/2026")
    pages = {
        page: f'<a href="{INNOVAR}">Innovar para llegar a tiempo</a><a href="{page}/2">2</a>',
        page + "/2": f'<a href="{old}">Nota antigua</a><a href="{page}/3">3</a>',
        INNOVAR: placeholder_only(), old: old_html,
    }
    visited = []

    def load(url):
        visited.append(url)
        return pages[url]

    report = discover_inventory(CuratedBetaSourceScout("achs_seguro_laboral"), load, as_of=AS_OF)
    assert report["stop_reason"] == "older_boundary_reached_with_gaps" and not report["coverage_complete"]
    assert page + "/3" not in visited  # 28-oct crawled 20 pages back to 2023
    row = next(row for row in report["rows"] if row["url"] == INNOVAR)
    assert row["reason"] == "publisher_cms_placeholder" and row["title"] == "Innovar para llegar a tiempo"
    assert row["publication_date"] is None and row["status"] == "pending"
    assert {error["code"] for error in report["errors"]} == {"publisher_cms_placeholder"}


def test_mutual_stalled_paginator_is_named_per_branch_not_a_bare_listing_url():
    # Shape of the 28-oct inventory: no per-URL error, 13 branches stopped by
    # repeated_pagination_page_stop before the 90-day start.
    inventory = {"errors": [], "stop_reason": "inventory_incomplete", "pagination_notes": [
        {"url": "https://www.mutual.cl/p0/A=GH=/", "branch": "component-2", "code": "repeated_pagination_page_stop",
         "oldest_verified_listing_date": "2026-10-01", "reached_90_day_cutoff": False},
        {"url": "https://www.mutual.cl/p0/A=GD=/", "branch": "component-1", "code": "repeated_pagination_page_stop",
         "oldest_verified_listing_date": "2026-07-01", "reached_90_day_cutoff": True}]}
    gaps = coverage_gap_diagnostics(inventory)
    assert [gap["branch"] for gap in gaps] == ["component-2"]
    assert gaps[0]["code"] == "pagination_stalled_before_90_day_cutoff"
    assert gaps[0]["oldest_verified_listing_date"] == "2026-10-01"
    fallback = coverage_gap_diagnostics({"errors": [], "stop_reason": "max_pages_exhausted"})
    assert fallback[0]["code"] == "inventory_capture_incomplete" and "max_pages_exhausted" in fallback[0]["detail"]


def _datos(robots_error=None):
    calls = []

    def fetch(url):
        calls.append(url)
        if url == ROBOTS:
            if robots_error:
                raise robots_error
            return b"User-agent: *\nDisallow: /api/\n", {}
        return FONASA.read_bytes(), {"sha256": "x" * 64, "captured_at": "2026-10-28T02:00:00+00:00"}
    return DatosGobScout(fetch=fetch, today=date(2026, 10, 28), window_days=1, enabled=True), calls


@pytest.mark.parametrize("status", [404, 410])
def test_datos_missing_robots_file_allows_the_api_per_rfc9309(status):
    scout, calls = _datos(HTTPError(ROBOTS, status, "Not Found", {}, None))
    assert scout.discover() == []  # real FONASA catalog: no release in window
    assert scout.diagnostics["robots_status"] == f"http_{status}_no_robots_file"
    assert not scout.diagnostics["errors"] and calls.count(ROBOTS) == 1


def test_datos_robots_disallow_and_unavailable_are_named_in_the_failure():
    scout, calls = _datos()
    with pytest.raises(RuntimeError, match="robots_disallowed: /api/3/action/package_search"):
        scout.discover()
    assert not any("package_search" in url for url in calls)
    scout, calls = _datos(HTTPError(ROBOTS, 403, "Forbidden", {}, None))
    with pytest.raises(RuntimeError, match="robots_disallowed"):
        scout.discover()
    assert scout.diagnostics["robots_status"] == "http_403_disallow_all"
    scout, _ = _datos(HTTPError(ROBOTS, 503, "Unavailable", {}, None))
    with pytest.raises(RuntimeError, match="robots_unavailable: HTTP 503"):
        scout.discover()
    assert all("robots_unavailable" in error["reason"] for error in scout.diagnostics["errors"])


def test_engine_persists_datos_gob_diagnostics_like_other_public_data_sources():
    from radar_salud.engine_cli import PUBLIC_DATA_SOURCES
    assert "datos_gob_cl" in PUBLIC_DATA_SOURCES and "isp_surveillance" in PUBLIC_DATA_SOURCES


def test_isp_empty_respiratory_listing_records_its_structure():
    scout = IspSurveillanceScout()
    channel, url = scout.PAGES[1]
    html = ('<div class="informes"><p>Semana 41, 2026</p>'
            '<a href="https://www.ispch.cl/documento/semana-41-2026/">Ver</a></div>'
            '<table><tbody></tbody></table>')
    with pytest.raises(RuntimeError, match="no verified document rows") as caught:
        scout.discover_from_html(html, url, channel)
    message = str(caught.value)
    assert "tables=1, rows=0" in message and "semana_texts=1" in message
    assert "documento_links=1" in message and "semana-41-2026" in message
