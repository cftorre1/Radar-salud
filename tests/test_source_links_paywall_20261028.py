"""Dirección 28-oct-2026: dead MINSAL "fuente original" links and DF paywall excess."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from radar_salud.models import RawItem
from radar_salud.source_rights import (excess_fields, is_paywalled, paywall_policy, purge_raw_metadata,
                                       redact_signal, restrict_raw_to_public, teaser_from_raw)
from radar_salud.source_urls import (card_link_problems, minsal_article_url, normalize_source_url,
                                     safe_source_url, sanitize_card_links, source_url_problem)

SNAPSHOT = Path("web/data/radar_today.json")
HISTORY = Path("data/history/superintendencia_signals.json")
DF_URL = "https://www.df.cl/economia-y-politica/df-tax/tribunal-tributario-marca-un-hito-y-permite-a-una-isapre-descontar-de-sus"
DF_TEASER = ("Un TTA de la Región Metropolitana acogió un requerimiento de Nueva Masvida contra un giro de más de "
             "$ 600 millones del SII, que consideró que no podían utilizarse esos recursos como gasto necesario para "
             "producir la renta. Impuestos Internos apelará.")
LOCKED = ("En la última década, las Isapres han sido objeto de miles de demandas. Este año las cortes han emitido "
          "ocho fallos sobre la materia: seis favorables al SII y dos desfavorables. ") * 4


@pytest.mark.parametrize("url,problem", [
    ("https://www.minsal.cl/campana-invierno-2026/", None),
    ("https://www.minsal.cl/wp-content/uploads/2026/09/26-Reporte-Semanal-Campana-de-Invierno-24-09-2026_.pdf", None),
    ("/campana-invierno-2026/", "relative_or_non_https"),
    ("minsal.cl/campana-invierno-2026/", "relative_or_non_https"),
    ("http://www.minsal.cl/campana-invierno-2026/", "insecure_http"),
    ("https://minsal.cl/campana-invierno-2026/", "non_canonical_host"),
    ("https://www.minsal.cl/campana-invierno-2026/ ", "whitespace"),
    ("https://www.minsal.cl/campana-de-vacunacion-e-inmunizacion-2026/%20", "encoded_whitespace"),
    ("https://www.minsal.cl/campana-invierno-2026/?utm_source=twitter", "tracking_parameters"),
    ("https://www.minsal.cl/?p=158873", "minsal_shortlink"),
    ("https://www.minsal.cl/2026/09/17/", "minsal_date_archive"),
    ("https://www.minsal.cl/category/noticias/", "minsal_listing"),
    # Legacy Drupal documents are not presumed dead (only a verified failure withholds them).
    ("https://www.minsal.cl/sites/default/files/ResolucionExenta211.pdf", None),
    ("https://www.minsal.cl/portal/url/item/abc.pdf", "minsal_retired_path"),
    ("https://www.minsal.cl/noticias/minsal-informa/", "minsal_retired_path"),
    ("https://www.minsal.cl/", "minsal_home"),
    ("https://www.df.cl/https/www.df.cl/empresas/salud/x", "nested_url_in_path"),
    ("https://www.df.cl/economia-y-politica/df-tax/{{fotofija_comun600}}", "template_placeholder"),
    ("", "missing"),
    (None, "missing"),
])
def test_source_url_problems_are_classified(url, problem):
    assert source_url_problem(url) == problem


def test_repairable_urls_are_normalised_and_unrepairable_give_no_link():
    assert safe_source_url(" https://minsal.cl/foo/?utm_source=x&fbclid=y#top ") == "https://www.minsal.cl/foo/"
    assert safe_source_url("https://www.minsal.cl/campana-2026/%20") == "https://www.minsal.cl/campana-2026/"
    assert safe_source_url("https://www.df.cl/https/www.df.cl/empresas/salud/x") == "https://www.df.cl/empresas/salud/x"
    assert normalize_source_url("https://repositoriodeis.minsal.cl/A/Año 2024.xlsx").endswith("/A/A%C3%B1o%202024.xlsx")
    assert safe_source_url("https://www.minsal.cl/sites/default/files/x.pdf") == "https://www.minsal.cl/sites/default/files/x.pdf"
    for dead in ("https://www.minsal.cl/?p=1", "/relative/", "javascript:x"):
        assert safe_source_url(dead) is None


def test_minsal_scout_keeps_only_canonical_publication_slugs():
    from radar_salud.scouts import MinsalNewsScout
    html = """
    <a href="https://www.minsal.cl/ministra-inaugura-hospital-regional-de-nuble/ ">Ministra inaugura Hospital Regional de Ñuble con 400 camas</a>
    <a href="http://minsal.cl/minsal-presenta-plan-de-listas-de-espera?utm_source=fb">Minsal presenta plan nacional de listas de espera 2027</a>
    <a href="https://www.minsal.cl/?p=158873">Subsecretario coordina avances del Hospital Regional de Ñuble</a>
    <a href="https://www.minsal.cl/2026/09/17/">Publicaciones del 17 de septiembre de 2026 en el sitio</a>
    <a href="https://www.minsal.cl/sites/default/files/ResolucionExenta211.pdf">Resolución N° 211 Designa Sujetos Pasivos Ley del Lobby</a>
    <a href="/campana-invierno-2026/%20">Campaña de Invierno 2026: reporte semanal de urgencias</a>
    """
    urls = [item.url for item in MinsalNewsScout().discover_from_html(html)]
    assert urls == ["https://www.minsal.cl/ministra-inaugura-hospital-regional-de-nuble/",
                    "https://www.minsal.cl/minsal-presenta-plan-de-listas-de-espera/",
                    "https://www.minsal.cl/campana-invierno-2026/"]
    assert all(source_url_problem(u) is None for u in urls)


def test_minsal_extraction_uses_publisher_canonical_and_clean_attachments():
    from radar_salud.minsal_pipeline import extract_minsal_detail
    raw = RawItem("minsal", "x", "https://www.minsal.cl/subsecretario-destaca-avances/", "Ministerio de Salud", "official")
    html = ('<link rel="canonical" href="https://www.minsal.cl/subsecretario-coordina-avances-hospital-nuble/">'
            '<h1>Subsecretario coordina avances</h1><p>Septiembre 25, 2026</p>'
            '<a href="https://www.minsal.cl/wp-content/uploads/2026/09/informe.pdf ">Descargar informe</a>'
            '<a href="https://www.minsal.cl/sites/default/files/viejo.pdf">PDF antiguo</a>')
    out = extract_minsal_detail(raw, html)
    assert out.url == "https://www.minsal.cl/subsecretario-coordina-avances-hospital-nuble/"
    assert out.metadata["requested_url"] == raw.url
    assert [a["url"] for a in out.metadata["attachments"]] == ["https://www.minsal.cl/wp-content/uploads/2026/09/informe.pdf",
                                                               "https://www.minsal.cl/sites/default/files/viejo.pdf"]


def test_process_minsal_rejects_invalid_source_url_before_any_fetch(monkeypatch):
    from radar_salud import public_source_pipeline as psp
    monkeypatch.setattr(psp, "fetch_html", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no fetch")))
    raw = RawItem("minsal", "Minsal presenta plan nacional de vacunación 2027", "https://www.minsal.cl/?p=12",
                  "Ministerio de Salud", "official")
    assert psp.process_minsal(raw, {"slug": "minsal"}) is None
    assert raw.metadata["rejection_reason"] == "minsal_invalid_source_url"


def test_web_snapshot_rejects_malformed_source_urls():
    """Every link the public snapshot renders must open: absolute https, canonical host, no junk."""
    cards = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["signals"]
    problems = {c.get("title"): card_link_problems(c) for c in cards}
    assert {t: p for t, p in problems.items() if p} == {}
    # The validator itself must catch a malformed row.
    broken = dict(cards[0], source_url="https://www.minsal.cl/?p=158873", source_link=None, source_link_status=None)
    assert card_link_problems(broken)
    assert sanitize_card_links(broken)["source_link_status"] == "invalid"
    assert card_link_problems(sanitize_card_links(broken)) == []


def test_ui_renders_no_link_for_invalid_rows():
    js = Path("web/app.js").read_text(encoding="utf-8")
    assert "function originalLink(s){if(!s||s.source_link_status==='invalid')return ''" in js
    assert "sourceLink(s.source_url)" not in js
    assert "href='${esc(s.source_url)}'" not in js


def test_paywall_policy_covers_df_premium_lt_and_preventive_outlets():
    assert paywall_policy(DF_URL)["id"] == "diario_financiero"
    assert paywall_policy("https://www.latercera.com/pulso/noticia/x/")["id"] == "la_tercera_premium"
    assert paywall_policy("https://www.latercera.com/la-tercera-pm/noticia/x/")["id"] == "la_tercera_premium"
    assert paywall_policy("https://www.latercera.com/nacional/noticia/x/") is None
    assert is_paywalled("https://www.latercera.com/nacional/noticia/x/", {"isAccessibleForFree": False})
    assert is_paywalled("https://www.emol.com/noticias/x.html") and is_paywalled("https://www.ex-ante.cl/x/")
    assert not is_paywalled("https://www.minsal.cl/x/")
    config = json.loads(Path("config/paywalled_press.json").read_text())
    assert config["policy"] == "public_teaser_only"
    assert {s["id"] for s in config["sources"]} >= {"diario_financiero", "la_tercera_premium", "el_mercurio", "ex_ante"}


def _df_html():
    return (f'<meta property="og:description" content="{DF_TEASER}">'
            '<meta name="cXenseParse:recs:publishtime" content="2026-10-22T13:50:50Z">'
            '<script type="application/ld+json">{"@type":"NewsArticle","url":"' + DF_URL + '",'
            '"headline":"Tribunal Tributario permite a una Isapre descontar de sus impuestos las costas por juicios contra afiliados",'
            '"datePublished":"2026-10-22T13:50:50Z"}</script>'
            f'<div id="articleLock" class="CUERPO"><p>{LOCKED}</p></div>')


def test_df_capture_stores_only_public_bajada_with_receipt():
    from radar_salud.df_article import bind_df_article
    raw = RawItem("diario_financiero", "Tribunal Tributario permite...", DF_URL, "Diario Financiero", "press_high_trust")
    raw = bind_df_article(raw, _df_html())
    dumped = json.dumps(raw.metadata, ensure_ascii=False) + raw.raw_text
    assert "seis favorables" not in dumped and "miles de demandas" not in dumped
    assert raw.metadata["page_text"] == DF_TEASER == raw.raw_text == raw.metadata["public_teaser"]
    assert raw.metadata["paywalled"] is True
    receipt = next(r for r in raw.metadata["rights_redactions"] if r["field"] == "page_text")
    assert receipt["characters"] > len(DF_TEASER) and len(receipt["sha256"]) == 64
    assert raw.event_date == "2026-10-22"


def test_df_analysis_sees_only_title_and_bajada_and_card_shows_only_public_text(monkeypatch):
    from radar_salud.df_article import bind_df_article
    from radar_salud.public_source_pipeline import process_df
    from test_press_pipeline import DF_CFG
    seen = {}

    def model(**kw):
        seen.update(kw)
        return {"relevance_score": 82, "what_happened": "El TTA acogió el requerimiento de Nueva Masvida; el SII apelará.",
                "why_it_matters": "Puede cambiar el tratamiento tributario de las costas judiciales.",
                "reason": "Fallo tributario material para isapres."}
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news", model)
    raw = bind_df_article(RawItem("diario_financiero", "Tribunal Tributario", DF_URL, "Diario Financiero",
                                  "press_high_trust"), _df_html())
    row = process_df(raw, DF_CFG)
    assert seen["text"] == DF_TEASER and "MURO DE PAGO" in seen["kind"]
    assert row["what_happened"] == DF_TEASER and row["why_it_matters"] == ""
    assert row["paywalled"] is True and row["analysis_basis"] == "public_teaser_only"
    assert excess_fields(row) == []
    assert "reason" not in row["editorial_assessment"]


def test_legacy_queue_item_with_locked_body_is_redacted_and_idempotent():
    raw = {"url": DF_URL, "title": "Tribunal Tributario permite ... afiliados " + DF_TEASER, "raw_text": DF_TEASER,
           "metadata": {"page_text": LOCKED, "article_title": "Tribunal Tributario permite ... afiliados",
                        "what_happened": "Según DF, ocho fallos: seis favorables al SII.",
                        "editorial_assessment": {"score": 82, "reason": "decisiones judiciales divididas"}}}
    assert teaser_from_raw(raw) == DF_TEASER
    assert purge_raw_metadata(raw) is True
    text = json.dumps(raw, ensure_ascii=False)
    assert "seis favorables" not in text and "divididas" not in text
    assert raw["metadata"]["page_text"] == DF_TEASER
    snapshot = copy.deepcopy(raw)
    assert purge_raw_metadata(raw) is False and raw == snapshot


def test_teaser_rejects_body_fallback_and_restricts_raw():
    raw = RawItem("diario_financiero", "T", DF_URL, "Diario Financiero", "press_high_trust", raw_text=LOCKED[:300],
                  metadata={"page_text": LOCKED})
    restrict_raw_to_public(raw)
    assert raw.metadata["page_text"] == "" and raw.raw_text == ""


def test_public_snapshot_and_history_carry_no_paywalled_excess():
    for path in (SNAPSHOT, HISTORY):
        rows = json.loads(path.read_text(encoding="utf-8"))["signals"]
        offenders = {r.get("source_url"): excess_fields(r) for r in rows if excess_fields(r)}
        assert offenders == {}, path
    card = next(c for c in json.loads(SNAPSHOT.read_text())["signals"] if c["source_url"] == DF_URL)
    assert card["what_happened"] == DF_TEASER and card["paywalled"] is True
    blob = SNAPSHOT.read_text(encoding="utf-8")
    assert "seis favorables al SII" not in blob and "ocho fallos" not in blob


def test_redaction_and_link_migration_are_idempotent():
    spec = importlib.util.spec_from_file_location("mig", Path("scripts/migrate_source_rights_links_2026_10_28.py"))
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    rows = [{"title": "T", "source_name": "Diario Financiero", "source_url": DF_URL, "event_date": "2026-10-22",
             "what_happened": "Según DF, ocho fallos: seis favorables al SII.", "why_it_matters": "x",
             "key_points": ["seis favorables"], "editorial_assessment": {"score": 82, "reason": "r"}},
            {"title": "M", "source_name": "Ministerio de Salud", "source_url": "https://www.minsal.cl/?p=158873"}]
    report = {"links": [], "paywalled": []}
    assert mig.migrate_rows(rows, {DF_URL: DF_TEASER}, report, "t") == 2
    assert rows[0]["what_happened"] == DF_TEASER and excess_fields(rows[0]) == []
    assert rows[1]["source_url"].endswith("?p=158873") and rows[1]["source_link_status"] == "invalid"
    once = copy.deepcopy(rows)
    assert mig.migrate_rows(rows, {DF_URL: DF_TEASER}, {"links": [], "paywalled": []}, "t") == 0
    assert rows == once
    assert redact_signal(rows[0]) == rows[0]
