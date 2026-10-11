"""Observed ACHS Salud DOM fields and safe material-detail promotion."""
from datetime import date
from html import escape
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from radar_salud.achs_blog import BLOG_URL, discover_blog_inventory

TODAY = date(2026, 10, 11)
ADVICE = "Consejos para cuidar tu salud y la de tu familia"
ADVICE_BODY = "Consulta a tu profesional de salud y cuida tus hábitos diarios para favorecer tu bienestar. " * 4
CHANGE = "Centros Achs Salud inaugura un nuevo centro de atención"
CHANGE_BODY = "Se inaugura un nuevo centro con 20 boxes y se amplía equipamiento para atención clínica. " * 4


def scout():
    return SimpleNamespace(slug="clinicas_achs_salud", cfg={"name": "Achs Salud/Clínicas", "type": "institution_verified"})


def record(slug="consejos", title=ADVICE, body=ADVICE_BODY, published="oct. 1, 2026, 08:31", custom="oct. 1, 2026, 09:30", sort="20261001083113", extra=""):
    values = {"navigateUrl": "/blog/detalle/" + slug, "Title": title, "Contenido": body,
              "PublicationDate": published, "FechaArticulo": custom, "sortPublicationDate": sort,
              "LastModified": "oct. 10, 2026, 23:59", "DateCreated": "oct. 10, 2026, 23:59"}
    return '<div class="cf_item">' + "".join(f'<span class="{key}">{escape(value)}</span>' for key, value in values.items() if value is not None) + extra + '</div>'


def run(html, detail=None):
    visited = []
    def loader(url):
        visited.append(url)
        if url == BLOG_URL:
            return html
        if isinstance(detail, Exception):
            raise detail
        if detail is None:
            raise AssertionError("General advice must not load a detail")
        return detail
    return discover_blog_inventory(scout(), loader, TODAY), visited


def detail_html(title=CHANGE, published="2026-10-01", body=CHANGE_BODY):
    return f'<meta property="article:published_time" content="{published}"><h1>{title}</h1><p>{body}</p>'


def test_real_actions_capture_counts_all_serialized_records_and_rejects_advice():
    path = Path(__file__).resolve().parents[1] / "data/audits/source_e_recovery/actions/38115274609/820f6e40aa4d4b72408c-0.body"
    report, visited = run(path.read_bytes().decode("utf-8"))
    assert len(report["rows"]) == 43
    assert report["pages"][0]["sha256"] == "3024f5f157482a2c95bb3125403d0fbab2aaf223f2d42a7596437400968f3503"
    assert report["observed_dataset_exhausted"] and not report["coverage_complete"]
    assert report["metrics"]["30"]["dated_articles"] == report["metrics"]["90"]["dated_articles"] == 3
    assert report["metrics"]["30"]["rejected"] == report["metrics"]["90"]["rejected"] == 3
    assert report["metrics"]["90"]["publisher_reported_articles"] == 4
    assert report["metrics"]["90"]["pending"] == 1
    assert report["unknown_publication_dates"] == 25
    assert not report["raw_items"] and visited == [BLOG_URL]
    conflict = report["rows"][3]
    assert conflict["publisher_reported_date"] == "2026-09-04"
    assert conflict["publication_date"] is None
    assert conflict["reason"] == "publication_editorial_date_conflict"


def test_lastmodified_recent_does_not_refresh_historical_publication():
    report, _ = run(record(published="feb. 3, 2026, 09:07", custom="feb. 3, 2026, 00:00", sort="20260203090727"))
    row = report["rows"][0]
    assert row["publication_date"] == "2026-02-03" and row["status"] == "outside_window"
    assert report["metrics"]["90"]["dated_articles"] == 0


@pytest.mark.parametrize("published,sort", [
    (None, None), ("prefix oct. 1, 2026, 08:31", None),
    ("oct. 1, 2026, 08:31 suffix", None), ("feb. 31, 2026, 08:31", None),
    ("oct. 12, 2026, 08:31", None), ("oct. 1, 2026, 99:31", None),
])
def test_missing_invalid_or_future_cms_publication_cannot_use_other_dates(published, sort):
    report, _ = run(record(published=published, sort=sort))
    assert report["rows"][0]["publication_date"] is None
    assert report["rows"][0]["status"] == "pending"
    assert not report["raw_items"]


@pytest.mark.parametrize("sort", ["20261002083113", "20261001093213", "date=20261001083113", "20260231083113"])
def test_sortable_publication_mismatch_or_junk_remains_pending(sort):
    report, _ = run(record(sort=sort))
    assert report["rows"][0]["status"] == "pending"
    assert report["rows"][0]["reason"] in ("conflicting_publication_dates", "invalid_sort_publication_date")


def test_conflicting_duplicate_publisher_fields_are_not_overwritten():
    report, _ = run(record(extra='<span class="PublicationDate">sep. 24, 2026, 09:14</span>'))
    assert report["rows"][0]["publication_date"] is None
    assert report["rows"][0]["reason"] == "conflicting_publication_dates"


def test_same_day_custom_editorial_time_is_consistent_but_different_day_is_not():
    report, _ = run(record())
    assert report["rows"][0]["publication_date"] == "2026-10-01"
    assert report["rows"][0]["status"] == "rejected"
    conflicting, _ = run(record(custom="abr. 9, 2026, 14:00"))
    assert conflicting["rows"][0]["publication_date"] is None
    assert conflicting["metrics"]["90"]["pending"] == 1


def test_read_every_serialized_record_without_inventing_server_pagination():
    report, visited = run("".join(record(slug=f"consejo-{n}") for n in range(61)))
    assert len(report["rows"]) == 61
    assert report["metrics"]["90"]["rejected"] == 61
    assert visited == [BLOG_URL] and report["pages"][0]["next_url"] is None


def test_script_and_footer_record_strings_are_ignored():
    html = '<script>' + record(slug="fake-script") + '</script><footer>' + record(slug="fake-footer") + '</footer>' + record()
    report, _ = run(html)
    assert len(report["rows"]) == 1
    assert report["rows"][0]["url"].endswith("/consejos")


def test_unclosed_record_is_a_gap_not_empty_healthy_archive():
    report, _ = run(record()[:-6])
    assert not report["observed_dataset_exhausted"] and not report["coverage_complete"]
    assert any(error["code"] == "unclosed_blog_record" for error in report["errors"])


def test_untrusted_record_url_cannot_be_loaded_as_a_detail():
    html = record(title=CHANGE, body=CHANGE_BODY).replace('/blog/detalle/consejos', 'https://example.net/blog/detalle/evil')
    report, visited = run(html)
    assert report["rows"][0]["reason"] == "blog_record_content_unrecognized"
    assert visited == [BLOG_URL] and not report["raw_items"]


def test_material_listing_requires_its_own_verified_detail_date():
    no_publication = f'<h1>{CHANGE}</h1><div>01/10/2026</div><p>{CHANGE_BODY}</p>'
    report, visited = run(record(title=CHANGE, body=CHANGE_BODY), no_publication)
    assert len(visited) == 2
    assert report["rows"][0]["status"] == "pending" and not report["raw_items"]
    assert report["rows"][0]["reason"] == "detail_listing_publication_or_content_mismatch"


def test_verified_material_detail_gets_own_url_evidence_and_centers_role():
    report, _ = run(record(title=CHANGE, body=CHANGE_BODY), detail_html())
    assert report["rows"][0]["status"] == "candidate"
    raw = report["raw_items"][0]
    assert raw.metadata["market_role"] == "provider_achs_centers"
    assert raw.metadata["publication_evidence"]["url"] == raw.url
    assert raw.metadata["publication_evidence"]["date"] == raw.event_date == "2026-10-01"
    assert raw.metadata["publication_date_source"] == "article:published_time"


@pytest.mark.parametrize("detail", [detail_html(published="2026-09-30"), detail_html(title="Otro centro nuevo con equipamiento")])
def test_detail_date_or_identity_mismatch_never_promotes_listing(detail):
    report, _ = run(record(title=CHANGE, body=CHANGE_BODY), detail)
    assert report["rows"][0]["status"] == "pending" and not report["raw_items"]


def test_one_material_detail_failure_preserves_other_dated_advice():
    report, _ = run(record(slug="capacity", title=CHANGE, body=CHANGE_BODY) + record(), TimeoutError("connect timeout 12s"))
    assert [row["status"] for row in report["rows"]] == ["pending", "rejected"]
    assert report["errors"][0]["detail"] == "connect timeout 12s"
    assert report["metrics"]["90"]["rejected"] == 1 and report["metrics"]["90"]["pending"] == 1


def test_waf_challenge_remains_exact_source_error():
    report, _ = run('<iframe src="/_Incapsula_Resource"></iframe>')
    assert report["stop_reason"] == "external_waf_challenge"
    assert report["technical_status"] == "blocked"
    assert not report["coverage_complete"]


def test_http_error_is_distinct_from_executor_proxy_denial():
    def loader(error):
        def failing(url):
            raise error
        return failing
    http = discover_blog_inventory(scout(), loader(HTTPError(BLOG_URL, 403, "Forbidden", {}, None)), TODAY)
    assert http["errors"][0]["code"] == "blog_fetch_failed" and http["errors"][0]["http_status"] == 403
    proxy = discover_blog_inventory(scout(), loader(URLError("Tunnel connection failed: 403 Forbidden")), TODAY)
    assert proxy["errors"][0]["code"] == "executor_proxy_denied"
    assert "http_status" not in proxy["errors"][0]


def test_insurance_lane_cannot_claim_provider_blog():
    wrong = scout()
    wrong.slug = "achs_seguro_laboral"
    with pytest.raises(ValueError, match="provider lane"):
        discover_blog_inventory(wrong, lambda url: record(), TODAY)
