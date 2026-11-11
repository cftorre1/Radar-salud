"""Weekly insight format A v2: news-style essay (Dirección 10-nov-2026).

Fixture: the 9-nov residencias insight, migrated to v2 from the approved mockup, with the evidence package of
its 8-nov editorial session (candidates/2026-11-09-residencias-evidence.json)."""
from copy import deepcopy
from datetime import date
import glob
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from radar_salud import weekly_insight_a as gen
from radar_salud import weekly_insight_essay as essay
from radar_salud import weekly_insight_stats_anchor as sa
from radar_salud.weekly_freshness import presentation_a, presentation_a_errors, reviewed_weekly

ROOT = Path(__file__).resolve().parents[1]
APPROVED = ROOT / "data/weekly_insight/editorial_approved.json"
EVIDENCE = ROOT / "data/weekly_insight/candidates/2026-11-09-residencias-evidence.json"
ANCHOR = date(2026, 11, 9)


def payload():
    return json.loads(APPROVED.read_text(encoding="utf-8"))


def weekly():
    return payload()["weekly_insight"]


def evidence():
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def block(w, kind, n=0):
    return [b for b in w["body"] if b["type"] == kind][n]


# --- the committed insight -----------------------------------------------------------------

def test_current_insight_is_v2_and_passes_deterministic_verification():
    w = weekly()
    assert w["schema_version"] == essay.SCHEMA_V2 and presentation_a(w)
    assert presentation_a_errors(w) == []
    result = gen.verify_candidate(w, evidence(), ANCHOR)
    assert result["verdict"] == "PASS", result["errors"]
    assert 500 <= essay.essay_words(w) <= 1000


def test_current_insight_keeps_ids_anchor_and_expiry():
    w = weekly()
    assert w["id"] == "weekly-insight:2026-11-09:residencias-mayores-camas"
    assert (w["freshness_anchor_date"], w["expires_on"], w["event_date"]) == ("2026-11-09", "2026-11-16", "2026-11-02")
    assert [bool(reviewed_weekly(payload(), date(2026, 11, d))) for d in (8, 9, 15, 16)] == [False, True, True, False]


def test_public_copies_serve_the_same_v2_insight():
    w = weekly()
    assert json.loads((ROOT / "data/weekly_insight/latest.json").read_text())["weekly_insight"] == w
    free = json.loads((ROOT / "web/data/free_value.json").read_text())
    assert free["weekly_insight"] == w
    assert free["selection_policy"]["weekly_presentation"] == {"format": essay.SCHEMA_V2, "errors": []}


def test_migration_uses_only_existing_evidence_urls_and_archives_nothing_new():
    w, ev = weekly(), evidence()
    assert {s["url"] for s in w["sources"]} == set(ev["allowed_urls"]) == set(w["source_refs"])
    assert {s["type"] for s in w["sources"]} == {"oficial", "prensa"}
    assert sorted(Path(p).name for p in glob.glob(str(ROOT / "data/weekly_insight/archive/*.json"))) == [
        "2026-09-14.json", "2026-10-10.json", "2026-10-23.json", "2026-11-02.json"]


def test_archived_v1_insights_still_pass_their_own_rules():
    for name in ("2026-10-23.json", "2026-11-02.json"):
        w = json.loads((ROOT / "data/weekly_insight/archive" / name).read_text())["weekly_insight"]
        assert not essay.is_v2(w) and presentation_a_errors(w) == [], name


def test_v1_is_retired_for_mondays_from_16_nov():
    w = json.loads((ROOT / "data/weekly_insight/archive/2026-11-02.json").read_text())["weekly_insight"]
    assert "schema_v1_retired_use_weekly_insight_a_v2" not in presentation_a_errors(w)
    w.update(freshness_anchor_date="2026-11-16", expires_on="2026-11-23")
    assert "schema_v1_retired_use_weekly_insight_a_v2" in presentation_a_errors(w)


# --- rules fail closed -----------------------------------------------------------------------

def _mut_words(w, n):
    block(w, "paragraph", 3)["text"] += " palabra" * n


CASES = {
    "number_untraced:key_figures[0].value:251": lambda w: w["key_figures"]["items"][0].update(value="251"),
    "number_untraced:body[0].paragraph:7.777": lambda w: w["body"][0].update(text=w["body"][0]["text"] + " Hubo 7.777 casos."),
    "number_untraced:method.discarded:94.500.000.000": lambda w: w["method"]["discarded"].append("El gasto de $94,5 mil millones."),
    "number_untraced:closing:9": lambda w: w["closing"].update(text=w["closing"]["text"] + " Son 9 de cada 10 camas."),
    "quote_not_literal_in_evidence:body[1]": lambda w: w["body"][1].update(text="No reduce la competencia en ningún segmento"),
    "quote_source_unresolved:body[1]": lambda w: w["body"][1].update(source_ref="f42"),
    "inline_quote_not_literal_in_cited_source:body[2].paragraph": lambda w: w["body"][2].update(
        text=w["body"][2]["text"].replace("“foco en proyectos de mayor tamaño”", "“foco en proyectos muy grandes”")),
    "source_ref_unresolved:body[0]:f12": lambda w: w["body"][0].update(text=w["body"][0]["text"].replace("](f2)", "](f12)")),
    "source_never_cited:f9": lambda w: block(w, "paragraph", 7).update(text=block(w, "paragraph", 7)["text"].replace("[Ley 21.822](f9)", "Ley 21.822")),
    "source_type_invalid:f2": lambda w: w["sources"][1].update(type="blog"),
    "section_label_not_allowed:body[4]": lambda w: w["body"][4].update(text="Qué pasó"),
    "chart_not_after_paragraph:catastro": lambda w: w["body"].insert(w["body"].index({"type": "chart", "chart_ref": "catastro"}),
                                                                     {"type": "subhead", "text": "Un subtítulo"}),
    "chart_not_placed_once:hospitalizacion_social": lambda w: w["body"].remove({"type": "chart", "chart_ref": "hospitalizacion_social"}),
    "essay_words_out_of_range": lambda w: _mut_words(w, 500),
    "lead_must_be_a_paragraph": lambda w: w["body"].insert(0, {"type": "subhead", "text": "Antes de la entrada"}),
    "key_figures_count_out_of_range:2": lambda w: w["key_figures"].update(items=w["key_figures"]["items"][:2]),
    "key_figures_count_out_of_range:6": lambda w: w["key_figures"]["items"].append(dict(w["key_figures"]["items"][0])),
    "key_figure_without_universe:1": lambda w: w["key_figures"]["items"][1].pop("universe"),
    "key_figure_universe_not_shown:1": lambda w: w["key_figures"]["items"][1].update(universe="hogares de todo el país"),
    "key_figure_kind_invalid:0": lambda w: w["key_figures"]["items"][0].update(kind="rumor"),
    "key_figure_source_unresolved:0": lambda w: w["key_figures"]["items"][0].update(source_ref="f99"),
    "key_figure_estimate_unresolved:2": lambda w: w["key_figures"]["items"][2].pop("estimate_ref"),
    "key_figures_more_than_one_wide": lambda w: w["key_figures"]["items"][0].update(wide=True),
    "estimate_chart_without_estimate:altas_vs_cupos": lambda w: w["charts"][1].pop("estimate_ref"),
    "estimate_missing_from_method:catastro_total": lambda w: w["method"]["estimates"].remove("catastro_total"),
    "estimate_mismatch:sin_autorizacion": lambda w: w["estimates"][1].update(value=40.0),
    "method_limits_empty": lambda w: w["method"].update(limits=[]),
    "normative_id_unexplained:body[15]": lambda w: w["body"][15].update(text="Atención a la Ley 21.822 y su política."),
    "v1_field_in_v2:watch": lambda w: w.update(watch=[{"headline": "x", "explanation": "y"}]),
    "headline_over_140_chars": lambda w: w.update(headline="a" * 141),
    "dek_over_30_words": lambda w: w.update(dek=" ".join(["palabra"] * 31)),
    # Dirección 11-nov: the dek is ONE sentence (one idea), and there is no topic kicker above the headline.
    "dek_more_than_one_sentence": lambda w: w.update(dek="La FNE aprobó el fondo. En junio, 1.056 personas seguían hospitalizadas."),
    "kicker_not_used": lambda w: w.update(kicker="Personas mayores y cuidados"),
}


@pytest.mark.parametrize("expected", list(CASES))
def test_v2_rule_breaks_fail_closed(expected):
    p = payload()
    CASES[expected](p["weekly_insight"])
    errors = presentation_a_errors(p["weekly_insight"])
    assert any(e.startswith(expected) for e in errors), (expected, errors)
    assert reviewed_weekly(p, date(2026, 11, 10)) is None


def test_key_figures_box_is_optional():
    w = weekly()
    w.pop("key_figures")
    w["body"] = [b for b in w["body"] if b["type"] != "key_figures"]
    # The card values that only the box showed (none here) do not matter; estimates must still be marked.
    errors = presentation_a_errors(w)
    assert not any(e.startswith("key_figure") for e in errors), errors


# --- numbers written as words and ratios (review of PR #174, item 1) ---------------------------

def test_number_words_are_scanned_like_digits():
    assert essay.digits("ocho de cada diez y seis meses; un tercio") == "8 de cada 10 y 6 meses; 1 de cada 3"
    assert essay.digits("la mitad") == "la mitad"  # «mitad» is read only inside an estimate marker
    assert essay.digits("una cama y un fondo") == "una cama y un fondo"  # articles are not numbers
    w = weekly()
    w["body"][2]["text"] += " Hubo diecisiete cierres."
    assert "number_untraced:body[2].paragraph:17" in presentation_a_errors(w)


@pytest.mark.parametrize("phrase", ["nueve de cada diez", "2 de cada 3", "dos tercios"])
def test_unbacked_ratio_fails(phrase):
    w = weekly()
    w["body"][5]["text"] += f" Son {phrase} hogares."
    assert any(e.startswith(f"ratio_not_backed_by_estimate:") and e.endswith(":body[5].paragraph")
               for e in presentation_a_errors(w)), presentation_a_errors(w)


@pytest.mark.parametrize("phrase, expected", [
    ("Hay dos mil camas.", "number_untraced:body[5].paragraph:2.000"),      # one value, not 2 and 1.000
    ("Hay treinta camas.", "number_untraced:body[5].paragraph:30"),
    ("Hay veinticinco camas.", "number_untraced:body[5].paragraph:25"),
    ("Hay ciento cuarenta y dos camas.", "number_untraced:body[5].paragraph:142"),
    ("Son dos tercios de los hogares.", "ratio_not_backed_by_estimate:2 de cada 3:body[5].paragraph"),
    ("Son tres cuartos de los hogares.", "ratio_not_backed_by_estimate:3 de cada 4:body[5].paragraph"),
    ("Hay miles de camas.", "number_word_unparsed:miles:body[5].paragraph"),
    ("Hay 2 millones de camas.", "number_untraced:body[5].paragraph:2.000.000"),
])
def test_spanish_number_phrases_are_one_value_and_checked(phrase, expected):
    w = weekly()
    w["body"][5]["text"] += " " + phrase
    assert expected in presentation_a_errors(w), presentation_a_errors(w)


@pytest.mark.parametrize("phrase", ["el doble de camas", "el triple de casos", "las camas se duplicó", "el gasto quintuplicó",
                                    "mitad de los hogares", "la mitad de los hogares", "un par de hospitales",
                                    "el cuádruple", "se triplicaron", "se cuadruplicó", "el gasto dobló",
                                    "las camas doblaron", "la oferta redobló"])
def test_multiples_and_mitad_outside_an_estimate_marker_fail(phrase):
    w = weekly()
    w["body"][5]["text"] += f" Hubo {phrase}."
    assert any(e.startswith("number_word_unparsed:") and e.endswith(":body[5].paragraph") for e in presentation_a_errors(w)), \
        presentation_a_errors(w)


def test_marked_multiple_passes_only_with_an_estimate_of_its_size():
    w = weekly()
    w["estimates"].append({"id": "dias_vs_egresos", "label": "días-cama frente a egresos, veces", "value": 15.3,
                           "unit": "veces", "display": "15,3 veces", "formula": "15.3 / 1"})
    w["estimates"].append({"id": "doble_x", "label": "razón, %", "value": 200.0, "unit": "%", "display": "200%",
                           "formula": "1056 / 528 * 100"})
    w["method"]["estimates"] += ["dias_vs_egresos", "doble_x"]
    w["body"][12]["text"] += (" Es [el doble](est:doble_x), el gasto [se dobló](est:doble_x) y [15,3 veces]"
                              "(est:dias_vs_egresos).")
    errors = presentation_a_errors(w)
    assert not any("doble" in e or "multiplier" in e for e in errors), errors
    ests = essay._estimates(w)
    assert essay.resolve_ratios("[el triple](est:doble_x)", ests)[1] == ["multiplier_off_its_estimate:triple:doble_x"]
    assert essay.resolve_ratios("[redobló](est:doble_x)", ests)[1] == []
    assert essay.resolve_ratios("[dobló](est:sin_autorizacion)", ests)[1] == ["multiplier_off_its_estimate:dobló:sin_autorizacion"]
    assert essay.resolve_ratios("[se duplicó](est:sin_autorizacion)", ests)[1] == [
        "multiplier_off_its_estimate:duplicó:sin_autorizacion"]


def test_spanish_number_phrases_parse_compounds_and_keep_articles():
    cases = {"dos mil camas": "2.000 camas", "treinta y dos": "32", "veintitrés": "23", "un millón trescientos mil":
             "1.300.000", "doscientas cincuenta habitaciones": "250 habitaciones", "1,5 millones": "1.500.000",
             "dos tercios": "2 de cada 3", "un quinto": "1 de cada 5", "cincuenta por ciento": "50%",
             "una cama y un fondo": "una cama y un fondo", "el cuarto trimestre": "el cuarto trimestre"}
    for text, expected in cases.items():
        assert essay.digits(text) == expected, text
    # A compound that traces passes: «doscientas cincuenta habitaciones» is the 250 of the evidence.
    w = weekly()
    w["body"][0]["text"] += " Son doscientas cincuenta habitaciones."
    assert presentation_a_errors(w) == []


def test_ratio_inside_an_estimate_marker_is_checked_against_that_estimate_only():
    w = weekly()
    ests = essay._estimates(w)
    assert essay.resolve_ratios("[ocho de cada diez](est:altas_vs_cupos)", ests)[1] == []   # 80 vs 80,12
    assert essay.resolve_ratios("[nueve de cada diez](est:altas_vs_cupos)", ests)[1] == [
        "ratio_off_its_estimate:9 de cada 10:altas_vs_cupos"]                               # 90 vs 80,12
    # Another estimate that would fit does not rescue it: the marker names its estimate.
    assert essay.resolve_ratios("[uno de cada tres](est:altas_vs_cupos)", ests)[1] == [
        "ratio_off_its_estimate:1 de cada 3:altas_vs_cupos"]
    # Outside a marker, a ratio is backed only by the estimate whose display it is («uno de cada tres» → 33,71).
    assert essay.resolve_ratios("1 de cada 3 hogares", ests)[1] == []
    assert presentation_a_errors(w) == []


def test_quotes_come_only_from_evidence_excerpts_never_from_labels_or_roles():
    w, ev = weekly(), evidence()
    role = next(s["role"] for s in ev["sources"] if s["url"] == w["sources"][0]["url"])
    assert role.startswith("Fuente primaria de la noticia")
    w["evidence_excerpts"].append({"source_ref": "f1", "text": "Fuente primaria de la noticia"})
    w["body"][1]["text"] = "Fuente primaria de la noticia"
    errors = gen.verify_candidate(w, ev, ANCHOR)["errors"]
    assert f"excerpt_not_in_evidence:{len(w['evidence_excerpts']) - 1}:f1" in errors
    pool = essay.quote_pool_by_url(ev)[w["sources"][0]["url"]]
    assert all("fuente primaria" not in p for p in pool)


def test_inline_quotes_match_the_cited_source_only_in_every_displayed_text():
    w = weekly()
    w["body"][2]["text"] = w["body"][2]["text"].replace("La [FNE](f1)", "La FNE")  # quote left without its source
    assert "inline_quote_not_literal_in_cited_source:body[2].paragraph" in presentation_a_errors(w)
    w = weekly()
    w["body"][2]["text"] = w["body"][2]["text"].replace("](f1)", "](f2)")  # FNE words credited to CNN
    assert "inline_quote_not_literal_in_cited_source:body[2].paragraph" in presentation_a_errors(w)
    for where, mutate in {"headline": lambda w: w.update(headline=w["headline"] + " con “foco en proyectos de mayor tamaño”"),
                          "body[4].subhead": lambda w: w["body"][4].update(text="El “foco en proyectos de mayor tamaño”"),
                          "key_figures[0].label": lambda w: w["key_figures"]["items"][0].update(label="“Una oferta muy grande”"),
                          "chart.catastro.headline": lambda w: w["charts"][0].update(headline="“Uno de cada tres hogares”")}.items():
        w = weekly()
        mutate(w)
        assert f"inline_quote_not_literal_in_cited_source:{where}" in presentation_a_errors(w), where


def test_sources_must_match_source_refs_and_quotes_their_attribution():
    w = weekly()
    w["source_refs"] = w["source_refs"][:-1]
    assert "source_refs_do_not_match_sources" in presentation_a_errors(w)
    w = weekly()
    fne = w["sources"][0]
    assert essay.issuer(fne["label"]) == "FNE"
    assert essay.attribution_names_source("Fiscalía Nacional Económica", fne)          # its initials
    assert essay.attribution_names_source("la FNE", fne)
    # Sharing a word of the title is not enough: «residencias» is in the FNE label, but not its issuer.
    assert not essay.attribution_names_source("Asociación de residencias", fne)
    for bad in ("Ministerio de Salud", "Asociación de residencias"):
        w["body"][1]["attribution"] = bad
        assert "quote_attribution_not_its_source:body[1]" in presentation_a_errors(w), bad


def test_migrated_text_carries_the_review_corrections():
    w = weekly()
    text = " ".join([w["dek"], w["closing"]["text"]] + [b.get("text", "") for b in w["body"]])
    # The dek was rewritten on 11-nov (one idea, no numbers) instead of stringing the FNE news and the 1.056 together.
    assert "Las cifras oficiales muestran" not in w["dek"] and "1.056" not in w["dek"] and essay.sentence_count(w["dek"]) == 1
    assert "kicker" not in w
    card = next(x for x in w["key_figures"]["items"] if x["label"] == "Altas que no salen")
    assert "todas las edades" in card["universe"] and card["universe"] in card["text"]
    assert w["closing"]["text"].count("cuando se publique") == 2 and "apunta a sumar" in w["closing"]["text"]
    assert "donde nadie la presupuesta" not in text and "Parte del cuidado que no encuentra" not in text
    assert any("no identificados" in x for x in w["method"]["limits"])
    assert 600 <= essay.essay_words(w) <= 900
    assert "para otro segmento" not in w["closing"]["text"]
    review = w["independent_review"]
    # The final PASS is recorded by coordination after the reviewer passes the fix commit, never before.
    assert review["status"] == "final" and review["verdict"] == "PASS"
    assert [(r["round"], r["verdict"]) for r in review["rounds"]] == [
        (1, "PASS_WITH_CORRECTIONS"), (2, "FAIL"), (3, "FAIL"), ("3-fix", "FAIL"), (4, "PASS")]
    assert review["rounds"][4] == {"round": 4, "on": "2026-11-10", "reviewed_commit": "c8ee171f", "verdict": "PASS"}
    assert review["rounds"][3] == {"round": "3-fix", "reviewed_commit": "8b9487f7", "verdict": "FAIL",
                                   "blocker": "verbo doblar; registro prematuro"}
    assert review["rounds"][2] == {"round": 3, "on": "2026-11-10", "reviewed_commit": "9c960e9b", "verdict": "FAIL",
                                   "blocker": "multiplier words"}


def test_a_number_word_in_a_figure_counts_only_within_one_evidence_item():
    w, ev = weekly(), evidence()
    w["evidence_figures"].append("Ley 21.822 y CNN Chile: seis meses para los dos primeros proyectos.")  # 6 and 2: two items
    errors = gen.verify_candidate(w, ev, ANCHOR)["errors"]
    assert "evidence_figure_word_not_in_one_item:6" in errors and "evidence_figure_word_not_in_one_item:2" in errors
    w = weekly()
    w["evidence_figures"].append("Ley 21.822: deberá dictarse dentro de seis meses.")
    assert gen.verify_candidate(w, ev, ANCHOR)["verdict"] == "PASS"


def test_evidence_checks_excerpts_and_figures_against_the_package():
    w, ev = weekly(), evidence()
    w["evidence_excerpts"].append({"source_ref": "f2", "text": "foco en proyectos de mayor tamaño"})  # FNE text, not CNN
    w["evidence_figures"].append("CNN Chile: 4.321 habitaciones más.")
    errors = gen.verify_candidate(w, ev, ANCHOR)["errors"]
    assert f"excerpt_not_in_evidence:{len(w['evidence_excerpts']) - 1}:f2" in errors
    assert "evidence_figure_not_in_evidence:4.321" in errors


def test_quote_may_skip_words_with_an_ellipsis():
    w = weekly()
    w["body"][1]["text"] = "No resulta apta para reducir sustancialmente la competencia […] segmentos analizados"
    assert presentation_a_errors(w) == []
    w["body"][1]["text"] = "No resulta apta […] segmentos inventados"
    assert "quote_not_literal_in_evidence:body[1]" in presentation_a_errors(w)


# --- writer: future Mondays come out in v2 ----------------------------------------------------

AUTHORED = ("headline", "dek", "body", "closing", "key_figures", "charts", "estimates", "method", "sources",
            "evidence_figures", "evidence_excerpts", "notes", "insight_teaser")


class FakeModels:
    def __init__(self, draft):
        self.draft, self.calls = draft, []

    def __call__(self, prompt, *, feature, preferred_model, allow_luna_fallback, max_output_tokens):
        self.calls.append({"feature": feature, "prompt": prompt, "max": max_output_tokens})
        out = deepcopy(self.draft) if feature.endswith("draft") else {"verdict": "PASS", "issues": [], "lenses": {}}
        return SimpleNamespace(output=out, model=preferred_model, estimated_cost_usd=0.1, response_id="fake")


def test_pipeline_writes_and_publishes_v2(monkeypatch, tmp_path):
    ev = evidence()
    ev["candidate"] = {"title": "FNE residencias", "url": ev["allowed_urls"][0], "event_date": "2026-11-02",
                       "source_name": "FNE"}
    ev.update(related=[], series=[])
    signal = {"title": "FNE residencias", "source_url": ev["candidate"]["url"], "event_date": "2026-11-02"}
    monkeypatch.setattr(gen, "select_topic", lambda *a, **k: [{"score": 1, "signal": signal, "related": []}])
    monkeypatch.setattr(gen, "build_evidence", lambda choice, root=None: deepcopy(ev))
    monkeypatch.setattr(gen, "stats_anchor_plan", lambda *a, **k: {"rule": "stats_anchor_v1", "status": "disabled"})
    monkeypatch.setattr(gen, "monthly_budget", lambda: None)
    draft = {k: deepcopy(weekly()[k]) for k in AUTHORED}
    fake = FakeModels(draft)
    result = gen.run_weekly_a([signal], as_of=date(2026, 11, 9), model_call=fake, root=tmp_path)
    assert result["status"] == "pass", result.get("verification")
    w = result["weekly_insight"]
    assert w["schema_version"] == essay.SCHEMA_V2 and w["freshness_anchor_date"] == "2026-11-09"
    assert result["audit"]["presentation"]["format"] == essay.SCHEMA_V2
    prompt = fake.calls[0]["prompt"]
    assert "Formato A v2" in prompt and "evidence_excerpts" in prompt and "unas 750 palabras" in prompt
    assert fake.calls[0]["max"] == gen.DRAFT_MAX_OUTPUT
    assert "evidence_excerpts" in fake.calls[1]["prompt"]  # the reviewer sees the v2 fields
    assert w["independent_review"]["verdict"] == "PASS" and w["independent_review"]["reviewer"] != w["independent_review"]["writer"]


def _stats_evidence_from_frozen_brief():
    b = json.loads((ROOT / "data/weekly_insight/candidates/2026-11-09-stats-brief.json").read_text(encoding="utf-8"))
    a = b["anchor"]
    return {"mode": "stats_anchor", "contract": b["contract"], "allowed_figures": b["allowed_anchor_figures"],
            "ficha_text": b["ficha_text_do_not_repeat"], "stats_anchor": {k: v for k, v in a.items() if k not in ("headline", "dek", "sources")},
            "candidate": {"title": a["headline"], "what": a["dek"], "url": (a["sources"] or [{}])[0].get("url")},
            "related": [{**{k: x[k] for k in ("label", "url", "source_name", "event_date")}, **(x.get("brief") or {})}
                        for x in b["cross_references"]],
            "sources": a["sources"]}


def test_worst_case_stats_anchor_run_fits_the_one_dollar_cap():
    """Item 8: stats draft (contract FAIL) + normal-topic redraft + review, each at full max_output."""
    routes = gen._routes()
    stats_prompt = sa.draft_prompt(_stats_evidence_from_frozen_brief(), ANCHOR)
    normal = json.loads((ROOT / "data/weekly_insight/candidates/2026-11-09-evidence.json").read_text(encoding="utf-8"))["evidence"]
    normal_prompt = gen.draft_prompt(normal, ANCHOR)
    review = gen.review_prompt(weekly(), normal, {"verdict": "PASS", "errors": []}) + sa.REVIEW_SUFFIX
    worst = (gen.worst_case_cost(routes[gen.DRAFT_ROUTE], stats_prompt, gen.DRAFT_MAX_OUTPUT)
             + gen.worst_case_cost(routes[gen.DRAFT_ROUTE], normal_prompt, gen.DRAFT_MAX_OUTPUT)
             + gen.worst_case_cost(routes[gen.REVIEW_ROUTE], review, gen.REVIEW_MAX_OUTPUT))
    assert worst < gen.MAX_RUN_USD, worst
    cost = gen.estimate_run_cost(normal, anchor=ANCHOR)
    assert cost["typical_usd"] < cost["worst_case_usd"] < gen.MAX_RUN_USD


def test_writer_prompt_drops_the_fixed_sections():
    assert gen.FORMAT_A == essay.FORMAT_V2 and gen.RULES == essay.RULES_V2
    assert '"essay"' not in gen.FORMAT_A and '"watch"' not in gen.FORMAT_A
    assert "Qué mirar" in gen.RULES and "Prohibidos" in gen.RULES  # named only as forbidden subheads


def test_stats_contract_reads_the_v2_closing():
    w = weekly()
    ev = {"contract": {}, "cross_refs": [], "source_pools": {}, "allowed_figures": [], "redundancy_corpus": []}
    errors = sa.contract_check(w, ev)["errors"]
    assert "tesis_missing" not in errors and "que_mirar_missing" not in errors and "closing_missing" not in errors
    w["closing"]["text"] = "Corto."
    assert "closing_missing" in sa.contract_check(w, ev)["errors"]


def test_sentence_count_ignores_thousands_and_decimals():
    assert essay.sentence_count("En junio, 1.056 personas y UF 1.500.000 en el fondo, el 15,3% de los días-cama.") == 1
    assert essay.sentence_count("Primera idea. Segunda idea.") == 2
    assert essay.sentence_count("¿Quién paga el cuidado?") == 1 and essay.sentence_count("") == 0
