"""Staging audit 29-oct-2026: defects fixed at the generator/exporter."""
import json
from datetime import date
from pathlib import Path

import pytest

import scripts.export_web_snapshot as exporter
from radar_salud import sis_news
from radar_salud.normative_relations import clean_subject, related_documents, target_key
from radar_salud.sis_bulletins import apply_bulletin_period, documents_period
from radar_salud.sis_news import (SuperintendenciaNoticiasScout, choose_title, clean_title, fold_news_into_acts,
                                  headline_act, is_generic_title, parse_article, repair_stored_news)
from radar_salud.story_groups import apply_story_groups, chile_day, same_title_groups

SIS = "Superintendencia de Salud"
FIX = Path(__file__).parent / "fixtures" / "sis"


@pytest.fixture(autouse=True)
def _isolated_failure_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(SuperintendenciaNoticiasScout, "_failures_path", lambda self: tmp_path / "news_failures.json")


# --- 3. Normativa relacionada: one act, whatever the number mark -----------------------------

@pytest.mark.parametrize("spelling", ["Circular IF/N°528", "Circular IF/Nº528", "Circular IF/No. 528", "Circular IF/N.º 528",
                                      "Circular IF/N˚528", "Circular IF/N 528"])
def test_number_mark_variants_are_one_act(spelling):
    assert target_key(spelling) == "circular-if-528"


def test_subject_cleaning_drops_only_the_unpaired_quote():
    raw = ("Imparte instrucciones sobre la cobertura de prestaciones relacionadas con el tratamiento del Trastorno "
           "del Espectro Autista (TEA)\" y cuyo objetivo es establecer")
    assert clean_subject(raw) == raw.replace('"', "")
    assert clean_subject('Modifica la "Circular IF/N°1" vigente') == 'Modifica la "Circular IF/N°1" vigente'
    assert clean_subject("Texto «citado sin cierre") == "Texto citado sin cierre"
    assert clean_subject("  ") is None
    # Apostrophes and inch marks are not quotes (review of #114).
    assert clean_subject("Región de O’Higgins y la ‘norma’ de O'Higgins") == "Región de O’Higgins y la ‘norma’ de O'Higgins"
    assert clean_subject('Monitor de 12" en la sala') == 'Monitor de 12" en la sala'
    assert clean_subject('Monitor de 12" y (TEA)" cuyo') == 'Monitor de 12" y (TEA)" cuyo'  # even count: ambiguous, kept
    assert clean_subject('Monitor de 12" (TEA)" y "x') == 'Monitor de 12" (TEA) y "x'


def _resolution_11156(related_context):
    return {"title": "Resolución Exenta IF/N°11156", "source_name": SIS, "event_date": "2026-10-20",
            "source_url": "https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n11156/",
            "normative_document_label": "Resolución Exenta IF/N°11156",
            "official_subject": "Acoge parcialmente los recursos de reposición interpuestos en contra de la Circular IF/N°528 y modifica la misma.",
            "related_context": related_context}


def test_related_documents_dedupe_across_number_marks(tmp_path):
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"acts": {"circular-if-528": {
        "id": "Circular IF/N°528", "url": "https://www.superdesalud.gob.cl/normativa/circular-if-n528-2/",
        "event_date": "2026-05-26", "official_subject": "Imparte instrucciones (TEA)\" y cuyo objetivo es establecer"}}}),
        encoding="utf-8")
    pending = {"title": "Circular IF/Nº528", "summary": None, "relationship": "Acto modificado.", "url": None,
               "event_date": None, "verified": False}
    law = {"title": "Ley Nº21.545", "summary": None, "relationship": "Base legal.", "url": None, "event_date": None, "verified": False}
    card, = exporter._late_related_documents([_resolution_11156([pending, law])], [], index)
    titles = [x["title"] for x in card["related_context"]]
    assert titles == ["Circular IF/N°528", "Ley Nº21.545"]  # the "enlace pendiente" twin is gone
    assert card["related_context"][0]["verified"] is True
    assert '"' not in card["related_context"][0]["summary"]


def test_related_context_dedupes_cited_ids_by_act():
    row = dict(_resolution_11156([]), related_reference_ids=["Circular IF/N°528", "Circular IF/Nº528"])
    row.pop("related_context")
    out, = exporter._related_context([row], resolve_external=False)
    assert [x["title"] for x in out["related_context"]] == ["Circular IF/N°528"]


# --- 4/5. SIS news headlines -----------------------------------------------------------------

def test_site_suffix_is_stripped_and_generic_labels_detected():
    assert clean_title("Más de 62 millones de casos GES desde 2005: Salud presenta cifras - Superintendencia de Salud") == \
        "Más de 62 millones de casos GES desde 2005: Salud presenta cifras"
    assert clean_title("Seminario de Entidades Acreditadoras | Superintendencia de Salud") == "Seminario de Entidades Acreditadoras"
    # The institution's name inside the headline stays.
    assert clean_title("Superintendencia de Salud realizó Seminario") == "Superintendencia de Salud realizó Seminario"
    assert clean_title("Isapres: Superintendencia de Salud instruye cobertura") == "Isapres: Superintendencia de Salud instruye cobertura"
    assert clean_title("Bonos con cédula : Superintendencia de Salud") == "Bonos con cédula"
    assert clean_title("A - Superintendencia de Salud - Superintendencia de Salud") == "A - Superintendencia de Salud"  # one suffix only
    assert clean_title("Superintendencia de Salud") == "Superintendencia de Salud"
    assert is_generic_title("COMUNICADO DE PRENSA - Superintendencia de Salud") and is_generic_title("Noticias")
    assert choose_title("COMUNICADO DE PRENSA - Superintendencia de Salud", "Noticias",
                        "Isapres deberán emitir el bono con cédula") == "Isapres deberán emitir el bono con cédula"
    assert choose_title("COMUNICADO DE PRENSA", "Noticias") == "COMUNICADO DE PRENSA"  # nothing better: never invented


def _page(og, h1s, title="", body="Texto."):
    heads = "".join(f"<h1>{h}</h1>" for h in h1s)
    return (f'<html><head><title>{title}</title><meta property="og:title" content="{og}">'
            f'<meta property="article:published_time" content="2026-09-30T12:00:00-03:00"></head>'
            f"<body>{heads}<p>{body}</p></body></html>")


def test_article_headline_prefers_informative_h1_over_generic_og_title():
    page = _page("COMUNICADO DE PRENSA - Superintendencia de Salud", ["Noticias", "Isapres deberán emitir bonos con cédula"])
    assert parse_article(page)["title"] == "Isapres deberán emitir bonos con cédula"
    page = _page("Más de 62 millones de casos GES - Superintendencia de Salud", ["Noticias"])
    assert parse_article(page)["title"] == "Más de 62 millones de casos GES"


ACT_534 = {"title": "Isapres deberán emitir bonos con cédula", "source_name": SIS, "signal_types": ["Normativa"],
           "event_type": "REGULATION", "normative_document_label": "Circular IF/N°534",
           "source_url": "https://www.superdesalud.gob.cl/normativa/circular-if-n534/"}
COMUNICADO = "https://www.superdesalud.gob.cl/noticias/2026/09/comunicado-de-prensa-3/"


def _discover_comunicado(page):
    listing = (FIX / "noticias_2026_listing_20261028.html").read_text(encoding="utf-8")
    pages = {"https://www.superdesalud.gob.cl/noticias/2026/": listing, COMUNICADO: page}

    def fetch(u):
        if u == sis_news.ROBOTS:
            return "User-agent: *\nAllow: /\n"
        if u in pages:
            return pages[u]
        raise OSError("not in fixture")
    scout = SuperintendenciaNoticiasScout(fetch=fetch, today=date(2026, 10, 28))
    return next(i for i in scout.discover() if i.url == COMUNICADO)


def _as_card(item):
    return {"title": item.title, "source_name": SIS, "source_url": item.url, "event_date": item.event_date,
            "signal_types": ["Noticias"], "mentioned_acts": item.metadata["mentioned_acts"]}


def test_generic_comunicado_is_shown_as_is_and_never_folded_from_body_or_navigation():
    # The act appears only in the body and in navigation text; the headline is generic.
    page = ('<html><head><title>COMUNICADO DE PRENSA - Superintendencia de Salud</title>'
            '<meta property="og:title" content="COMUNICADO DE PRENSA - Superintendencia de Salud">'
            '<meta property="article:published_time" content="2026-09-30T12:00:00-03:00"></head><body>'
            '<nav><a href="/normativa/circular-if-n534/">Circular IF/N°534</a></nav><h1>COMUNICADO DE PRENSA</h1>'
            '<p>La Superintendencia de Salud dictó la Circular IF/N°534 sobre bonos electrónicos.</p></body></html>')
    item = _discover_comunicado(page)
    assert item.title == "COMUNICADO DE PRENSA" and item.metadata["generic_title"] is True
    assert not item.metadata.get("listing_title_mismatch")
    out = fold_news_into_acts([ACT_534, _as_card(item)])
    assert [c["source_url"] for c in out] == [ACT_534["source_url"], COMUNICADO]
    assert not out[0].get("source_alternatives")


def test_specific_h1_improves_the_headline_and_folds_only_when_it_names_the_act():
    page = _page("COMUNICADO DE PRENSA - Superintendencia de Salud", ["Noticias", "Superintendencia dicta la Circular IF/N°534 sobre bonos con cédula"])
    item = _discover_comunicado(page)
    assert item.title == "Superintendencia dicta la Circular IF/N°534 sobre bonos con cédula"
    out = fold_news_into_acts([ACT_534, _as_card(item)])
    assert len(out) == 1 and out[0]["source_alternatives"][0]["url"] == COMUNICADO


@pytest.mark.parametrize("headline", [
    "Circular IF/N°540 modifica la Circular IF/N°534",          # modified by another act
    "Superintendencia modifica la Circular IF/N°534 sobre bonos",  # object of a modification
    "Isapres reportan alza de reclamos, según la Circular IF/N°534",  # passing mention
    "Isapres presentan recursos contra la Circular IF/N°534",
    "Isapres informan nuevos planes de salud",                    # no act in the headline
])
def test_headline_without_a_subject_act_never_folds(headline):
    assert headline_act(headline) is None
    news = {"title": headline, "source_name": SIS, "source_url": COMUNICADO, "event_date": "2026-09-30",
            "signal_types": ["Noticias"], "mentioned_acts": ["circular-if-534"]}  # lead/body mentions never decide
    assert len(fold_news_into_acts([ACT_534, news])) == 2


def test_stored_generic_news_keeps_its_row_and_only_loses_the_suffix():
    news = {"title": "COMUNICADO DE PRENSA - Superintendencia de Salud", "source_name": SIS, "source_type": "official",
            "source_url": COMUNICADO, "event_date": "2026-09-30", "mentioned_acts": [], "signal_types": ["Noticias"],
            "what_happened": "La Superintendencia de Salud dictó la Circular IF/N°534, que regirá desde el 1 de diciembre de 2026."}
    fixed = repair_stored_news(news)
    assert fixed["title"] == "COMUNICADO DE PRENSA" and fixed["source_page_title"] == news["title"]
    assert fixed["mentioned_acts"] == [] and fixed["generic_title"] is True  # nothing read from the summary
    assert len(fold_news_into_acts([ACT_534, fixed])) == 2
    seminar = repair_stored_news(dict(news, title="Superintendencia de Salud realizó Seminario - Superintendencia de Salud"))
    assert seminar["title"] == "Superintendencia de Salud realizó Seminario"
    other = {"title": "X - Superintendencia de Salud", "source_name": "Minsal", "source_url": "https://www.minsal.cl/x/"}
    assert repair_stored_news(other) is other


# --- 6. Same headline, same day, two official sources ------------------------------------------

def _story(source, url, title, day="2026-10-14", score=60, kind="official"):
    return {"title": title, "source_name": source, "source_url": url, "event_date": day, "radar_score": score,
            "source_type": kind, "what_happened": "x"}


def test_same_headline_same_day_groups_official_sources():
    t = "Más de 62 millones de casos GES desde 2005: Salud presenta cifras actualizadas y llama a ejercer las garantías"
    sis = _story(SIS, "https://www.superdesalud.gob.cl/noticias/2026/10/ges/", t + " - Superintendencia de Salud", score=68)
    minsal = _story("Ministerio de Salud", "https://www.minsal.cl/ges/", t, score=63)
    press = _story("Pulso / La Tercera", "https://www.latercera.com/ges/", t, kind="press_high_trust")
    other_day = _story("Ministerio de Salud", "https://www.minsal.cl/ges-2/", t, day="2026-10-15")
    groups = same_title_groups([sis, minsal, press, other_day])
    assert len(groups) == 1 and groups[0]["lead_url"] == sis["source_url"]
    assert set(groups[0]["member_urls"]) == {sis["source_url"], minsal["source_url"]}
    assert groups == same_title_groups([sis, minsal, press, other_day])  # deterministic id
    cards, _ = apply_story_groups([sis, minsal, press, other_day], groups)
    assert [c["source_url"] for c in cards] == [sis["source_url"], press["source_url"], other_day["source_url"]]
    assert cards[0]["source_alternatives"][0]["source_name"] == "Ministerio de Salud"
    # Configured groups win; short labels never group by title; one source alone is no group.
    assert same_title_groups([sis, minsal], [{"member_urls": [minsal["source_url"]]}]) == []
    assert same_title_groups([_story(SIS, "a", "Comunicado de prensa"), _story("Ministerio de Salud", "b", "Comunicado de prensa")]) == []
    assert same_title_groups([sis, dict(sis, source_url="https://www.superdesalud.gob.cl/x/")]) == []


@pytest.mark.parametrize("title", [
    "Comunicado de prensa de la Superintendencia de Salud",           # only generic words
    "Cuenta Pública Participativa de la Autoridad Sanitaria",          # institutional agenda label
])
def test_generic_identical_headlines_never_group(title):
    a = _story(SIS, "https://www.superdesalud.gob.cl/noticias/a/", title)
    b = _story("Ministerio de Salud", "https://www.minsal.cl/a/", title)
    assert same_title_groups([a, b]) == []


def test_grouping_uses_the_chile_calendar_day():
    t = "Más de 62 millones de casos GES desde 2005: Salud presenta cifras actualizadas"
    # 14-oct 23:30 in Santiago is 15-oct 02:30 UTC: the same Chile day as a 14-oct date.
    late = _story(SIS, "https://www.superdesalud.gob.cl/noticias/late/", t, day="2026-10-15T02:30:00+00:00")
    dated = _story("Ministerio de Salud", "https://www.minsal.cl/late/", t, day="2026-10-14")
    assert chile_day(late["event_date"]) == "2026-10-14"
    assert len(same_title_groups([late, dated])) == 1
    # 15-oct 01:00 UTC vs a 15-oct date: different Chile days, no group.
    early = _story(SIS, "https://www.superdesalud.gob.cl/noticias/e/", t, day="2026-10-15T01:00:00Z")
    assert same_title_groups([early, _story("Ministerio de Salud", "https://www.minsal.cl/e/", t, day="2026-10-15")]) == []


# --- 7. Bulletin period from its documents ---------------------------------------------------------

DOCS = [{"url": f"https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-{t}-enero-junio-2026{s}.pdf"}
        for t, s in (("acreditacion", "-2"), ("mediacion", ""), ("reclamos", ""), ("rnpi", ""))]


def test_bulletin_title_takes_the_period_of_its_documents():
    row = {"title": "Boletín Estadístico Informativo IP – Septiembre 2026", "source_documents": DOCS}
    out = apply_bulletin_period(row)
    assert out["display_title"] == "Boletín Estadístico Informativo IP N°2 · enero–junio 2026"
    assert out["data_period"] == "enero–junio 2026" and out["source_title_full"] == row["title"]
    # Documents that disagree or do not state a period: nothing is changed.
    mixed = DOCS + [{"url": "https://www.superdesalud.gob.cl/app/uploads/2026/10/boletin-n3-2026-rnpi-julio-septiembre-2026.pdf"}]
    assert documents_period(mixed) is None and "display_title" not in apply_bulletin_period(dict(row, source_documents=mixed))
    assert "display_title" not in apply_bulletin_period(dict(row, source_documents=[{"url": "https://x.cl/informe.pdf"}]))
    assert apply_bulletin_period(dict(row, display_title="Curado"))["display_title"] == "Curado"
    assert "display_title" not in apply_bulletin_period({"title": "Estadística mensual", "source_documents": DOCS})
