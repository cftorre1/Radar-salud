"""Adversarial HTML examples; these are not captures of live publisher HTML."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from radar_salud.beta_sources import CuratedBetaSourceScout
from radar_salud.pulso_source import article_url, extract_article, health_anchor, publication_day

URL = "https://www.latercera.com/nacional/noticia/clinica-suspende-operaciones/"
DAY = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
TITLE = "Clínica suspende operaciones y traslada pacientes a otros prestadores"
BODY = "La clínica reportó una suspensión temporal de operaciones y redistribución de consultas y procedimientos en su red. El cierre afecta la capacidad asistencial y la continuidad de atención de los pacientes."


def article(url=URL, day=DAY, title=TITLE, body=BODY, **fields):
    node = dict({"@type": "NewsArticle", "url": url, "headline": title, "datePublished": day}, **fields)
    return (f'<link rel="canonical" href="{url}">'
            '<script>window.navigationDate="2020-01-01"; inversión de banco</script>'
            f'<script type="application/ld+json">{json.dumps({"@graph": [node]})}</script>'
            f'<nav>2021-01-01 salud y bonos</nav><article><h1>{title}</h1>'
            f'<div class="body-chain"><p>{body}</p><aside>2022-01-01 premio</aside></div>'
            '<div class="related-stories"><p>Salud aumenta capital de banco</p></div></article>')


def test_date_and_body_bound_to_primary_article_not_script_navigation_or_event_date():
    title, body, evidence = extract_article(article(body=BODY + " El incidente ocurrió el 8 de octubre de 2026."), URL)
    assert title == TITLE
    assert evidence["publication_date"] == DAY
    assert evidence["publication_date_source"] == "json_ld_datePublished"
    assert not any(word in body for word in ("navigationDate", "premio", "banco", "bonos"))
    assert "8 de octubre" in body


@pytest.mark.parametrize("html,reason", [
    (article(day="2026-02-30"), "invalid_publication"),
    (article(day=None), "invalid_publication"),
    (article(day="2099-01-01"), "future_publication"),
    (article(url="https://www.latercera.com/pulso/noticia/otro-articulo/"), "identity_mismatch"),
    (article() + '<meta property="article:published_time" content="2020-01-01">', "conflicting_publication"),
])
def test_fail_closed_on_invalid_missing_future_or_unbound_dates(html, reason):
    with pytest.raises(ValueError, match=reason):
        extract_article(html, URL)


def test_related_json_ld_date_does_not_date_primary_article():
    html = article().replace(f'"url": "{URL}"', '"url": "https://www.latercera.com/pulso/noticia/related/"')
    with pytest.raises(ValueError, match="invalid_publication"):
        extract_article(html, URL)


def test_publication_calendar_date_preserves_publisher_offset():
    assert publication_day("2026-10-11T01:30:00Z") == "2026-10-11"
    assert publication_day("2026-10-10T22:30:00-03:00") == "2026-10-10"
    assert publication_day("2026-10-10T22:30:00") is None


def test_nacional_and_legacy_news_paths_supported_with_exact_host_controls():
    assert article_url(URL + "?outputType=base-amp-type#top") == URL
    assert article_url("https://latercera.com/pulso/noticia/isapres/" + "A" * 26 + "/")
    for url in ("http://www.latercera.com/pulso/noticia/clinica/",
                "https://www.latercera.com.evil.test/pulso/noticia/clinica/",
                "https://www.latercera.com/opinion/noticia/clinica/",
                "https://www.latercera.com/pulso/noticia/clinica/extra/",
                "https://user@www.latercera.com/pulso/noticia/clinica/"):
        assert article_url(url) is None


def test_listing_dedupes_canonical_urls_and_retains_nacional_health_candidate():
    html = f'<a href="{URL}?x=1">{TITLE}</a><a href="{URL}">{TITLE}</a>'
    calls = []
    def load(url):
        calls.append(url)
        return article()
    items = CuratedBetaSourceScout("pulso_latercera").discover_from_html(html, load)
    assert calls == [URL]
    assert items[0].metadata["article_verified"]
    assert items[0].event_date == DAY
    assert items[0].metadata["page_text"] == BODY


def test_more_than_thirty_health_candidates_are_not_silently_truncated():
    urls = [URL.replace("clinica-suspende-operaciones", f"clinica-{i}") for i in range(35)]
    listing = "".join(f'<a href="{url}">{TITLE}</a>' for url in urls)
    items = CuratedBetaSourceScout("pulso_latercera").discover_from_html(listing, lambda url: article(url=url))
    assert len(items) == 35


def test_failed_detail_is_audited_without_discarding_readable_articles():
    bad = URL.replace("clinica-suspende-operaciones", "clinica-invalid-date")
    listing = f'<a href="{URL}">{TITLE}</a><a href="{bad}">{TITLE}</a>'
    scout = CuratedBetaSourceScout("pulso_latercera")
    items = scout.discover_from_html(listing, lambda url: article(url=url, day=None if url == bad else DAY))
    assert [item.url for item in items] == [URL]
    assert scout.discovery_audit[-1]["url"] == bad
    assert scout.discovery_audit[-1]["status"] == "detail_error"
    assert scout.discovery_audit[-1]["reason"] == "missing_or_invalid_publication_date"


def test_health_anchor_excludes_generic_finance_but_includes_senior_care():
    assert not health_anchor("Banco aumenta capital para inversión inmobiliaria")
    assert health_anchor("Senior housing: inversión y competencia entre residencias para adultos mayores")
