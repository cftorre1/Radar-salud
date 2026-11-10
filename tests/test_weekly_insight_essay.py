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
    "number_untraced:method.discarded:94,5": lambda w: w["method"]["discarded"].append("El gasto de $94,5 mil millones."),
    "number_untraced:closing:9": lambda w: w["closing"].update(text=w["closing"]["text"] + " Son 9 de cada 10 camas."),
    "quote_not_literal_in_evidence:body[1]": lambda w: w["body"][1].update(text="No reduce la competencia en ningún segmento"),
    "quote_source_unresolved:body[1]": lambda w: w["body"][1].update(source_ref="f42"),
    "inline_quote_not_literal_in_evidence:body[2]": lambda w: w["body"][2].update(
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
    "dek_over_40_words": lambda w: w.update(dek=" ".join(["palabra"] * 41)),
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


def test_ratio_traces_only_to_an_estimate_that_rounds_to_it():
    w = weekly()
    assert essay.strip_ratios("8 de cada 10 cupos", [80.12]).strip() == "cupos"
    assert "9 de cada 10" in essay.strip_ratios("9 de cada 10 cupos", [80.12])
    assert "1 de cada 3" not in essay.strip_ratios("1 de cada 3", [33.71])
    assert presentation_a_errors(w) == []


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

AUTHORED = ("kicker", "headline", "dek", "body", "closing", "key_figures", "charts", "estimates", "method", "sources",
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
