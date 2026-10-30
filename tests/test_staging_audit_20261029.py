"""Staging audit 29-oct-2026: defects fixed at the generator/exporter."""
import json
from datetime import date
from pathlib import Path

import pytest

import scripts.export_web_snapshot as exporter
from radar_salud import sis_news
from radar_salud.normative_relations import clean_subject, related_documents, target_key
from radar_salud.sis_bulletins import apply_bulletin_period, documents_period
from radar_salud.sis_news import SuperintendenciaNoticiasScout, clean_title, fold_news_into_acts, repair_stored_news
from radar_salud.story_groups import apply_story_groups, load_groups

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

def test_site_suffix_is_stripped_only_at_the_end():
    assert clean_title("Más de 62 millones de casos GES desde 2005: Salud presenta cifras - Superintendencia de Salud") == \
        "Más de 62 millones de casos GES desde 2005: Salud presenta cifras"
    assert clean_title("Seminario de Entidades Acreditadoras | Superintendencia de Salud") == "Seminario de Entidades Acreditadoras"
    # The institution's name inside the headline stays.
    assert clean_title("Superintendencia de Salud realizó Seminario") == "Superintendencia de Salud realizó Seminario"
    assert clean_title("Isapres: Superintendencia de Salud instruye cobertura") == "Isapres: Superintendencia de Salud instruye cobertura"
    assert clean_title("Bonos con cédula : Superintendencia de Salud") == "Bonos con cédula"
    assert clean_title("A - Superintendencia de Salud - Superintendencia de Salud") == "A - Superintendencia de Salud"  # one suffix only
    assert clean_title("Superintendencia de Salud") == "Superintendencia de Salud"


COMUNICADO = "https://www.superdesalud.gob.cl/noticias/2026/09/comunicado-de-prensa-3/"
ACT_534 = {"title": "Isapres deberán emitir bonos con cédula", "source_name": SIS, "signal_types": ["Normativa"],
           "event_type": "REGULATION", "normative_document_label": "Circular IF/N°534",
           "source_url": "https://www.superdesalud.gob.cl/normativa/circular-if-n534/"}


def test_stored_news_only_loses_the_site_suffix_and_comunicado_stays_its_own_row():
    news = {"title": "COMUNICADO DE PRENSA - Superintendencia de Salud", "source_name": SIS, "source_type": "official",
            "source_url": COMUNICADO, "event_date": "2026-09-30", "mentioned_acts": [], "signal_types": ["Noticias"],
            "what_happened": "La Superintendencia de Salud dictó la Circular IF/N°534, que regirá desde el 1 de diciembre de 2026."}
    fixed = repair_stored_news(news)
    assert fixed["title"] == "COMUNICADO DE PRENSA" and fixed["source_page_title"] == news["title"]
    assert {k: v for k, v in fixed.items() if k not in ("title", "source_page_title")} == \
        {k: v for k, v in news.items() if k != "title"}  # nothing else changes, no act read from the summary
    # No automatic fold (review of PR #114): the pre-existing mechanism, unchanged, sees no named act.
    assert [c["source_url"] for c in fold_news_into_acts([ACT_534, fixed])] == [ACT_534["source_url"], COMUNICADO]
    other = {"title": "X - Superintendencia de Salud", "source_name": "Minsal", "source_url": "https://www.minsal.cl/x/"}
    assert repair_stored_news(other) is other
    assert repair_stored_news(fixed) is fixed


def test_scout_strips_suffix_from_article_title_without_flagging_a_mismatch():
    from radar_salud import sis_news
    listing = (FIX / "noticias_2026_listing_20261028.html").read_text(encoding="utf-8")
    ges = ("https://www.superdesalud.gob.cl/noticias/2026/10/mas-de-62-millones-de-casos-ges-desde-2005-salud-presenta-"
           "cifras-actualizadas-y-llama-a-ejercer-las-garantias/")
    page = ('<html><head><meta property="og:title" content="Más de 62 millones de casos GES desde 2005: Salud presenta cifras '
            'actualizadas y llama a ejercer las garantías - Superintendencia de Salud">'
            '<meta property="article:published_time" content="2026-10-14T10:00:00-03:00"></head><body><p>Texto.</p></body></html>')
    pages = {"https://www.superdesalud.gob.cl/noticias/2026/": listing, ges: page}

    def fetch(u):
        if u == sis_news.ROBOTS:
            return "User-agent: *\nAllow: /\n"
        if u in pages:
            return pages[u]
        raise OSError("not in fixture")
    item = next(i for i in SuperintendenciaNoticiasScout(fetch=fetch, today=date(2026, 10, 28)).discover() if i.url == ges)
    assert item.title == "Más de 62 millones de casos GES desde 2005: Salud presenta cifras actualizadas y llama a ejercer las garantías"
    assert not item.metadata.get("listing_title_mismatch")


# --- 6. Same GES story from SIS and Minsal: curated group (no automatic grouping) -----------------

GES_SIS = ("https://www.superdesalud.gob.cl/noticias/2026/10/mas-de-62-millones-de-casos-ges-desde-2005-salud-presenta-"
           "cifras-actualizadas-y-llama-a-ejercer-las-garantias/")
GES_MINSAL = ("https://www.minsal.cl/mas-de-62-millones-de-casos-ges-desde-2005-salud-presenta-cifras-actualizadas-y-"
              "llama-a-ejercer-las-garantias/")


def test_ges_duplicate_is_a_curated_lead_group_for_exactly_two_urls():
    group = next(g for g in load_groups() if g["id"] == "ges-62-millones-2026-10-14")
    assert group["mode"] == "lead" and group["lead_url"] == GES_SIS
    assert group["member_urls"] == [GES_SIS, GES_MINSAL]
    assert "Dirección" in group["reason"] and "29-oct" in group["reason"]
    import radar_salud.story_groups as sg
    assert not hasattr(sg, "same_title_groups")  # no automatic title grouping
    sis = {"title": "Más de 62 millones de casos GES desde 2005", "source_name": SIS, "source_url": GES_SIS, "event_date": "2026-10-14"}
    minsal = dict(sis, source_name="Ministerio de Salud", source_url=GES_MINSAL)
    other = dict(sis, source_name="Ministerio de Salud", source_url="https://www.minsal.cl/otra/")
    cards, _ = apply_story_groups([sis, minsal, other], [group])
    assert [c["source_url"] for c in cards] == [GES_SIS, "https://www.minsal.cl/otra/"]
    assert cards[0]["source_alternatives"][0]["url"] == GES_MINSAL


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
