"""Weekly Insight anchored on a stats-family release (Dirección, 2-nov-2026): selection rule,
ficha-vs-Insight contract and an end-to-end dry run with fake models. No network, no paid calls.

Fixtures: the live F1 ficha committed in the repo, copied to a temporary root with its
``published_at`` moved into the Insight week; the cross-reference signals below are test
fixtures on a ``fixture.alicanto.test`` host, not product data."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from radar_salud import weekly_insight_a as gen
from radar_salud import weekly_insight_stats_anchor as sa
from radar_salud.weekly_freshness import presentation_a_errors

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = date(2026, 11, 2)
FX = "https://fixture.alicanto.test/"

SANCTION = {"title": "Superintendencia multa a tres isapres por alzas de planes de salud no informadas",
            "source_name": "Superintendencia de Salud", "source_type": "official", "source_url": FX + "sis-multa",
            "signal_types": ["Fiscalización"], "event_type": "SANCTION", "event_date": "2026-10-14",
            "what_happened": "La Superintendencia de Salud sancionó a tres isapres con multas por 1.200 UF en total por "
                             "aplicar alzas de precio base sin informar a sus cotizantes.",
            "entity_refs": [{"canonical_id": "cl:isapre:67"}], "editorial_relevance": 60}
BILL = {"title": "Comisión de Salud del Senado vota indicaciones a la ley corta de isapres",
        "source_name": "Congreso Nacional · Tramitación (Senado, datos abiertos)", "source_type": "official",
        "source_url": FX + "senado-ley-corta", "signal_types": ["Legal"], "event_type": "LEGAL", "event_date": "2026-10-21",
        "what_happened": "La comisión de Salud del Senado aprobó 14 indicaciones y rechazó 6 al proyecto que ajusta la ley "
                         "corta de isapres y la tabla de factores.", "editorial_relevance": 55}
UNRELATED = {"title": "Hospitales públicos reportan alza de consultas por virus respiratorios",
             "source_name": "Ministerio de Salud", "source_type": "official", "source_url": FX + "minsal-virus",
             "signal_types": ["Noticias"], "event_type": "OTHER", "event_date": "2026-10-29",
             "what_happened": "Las consultas por virus respiratorios subieron 18% en la última semana en la red pública.",
             "why_it_matters": "Presión asistencial en invierno tardío.", "editorial_relevance": 70,
             "economic_impact_score": 40, "source_quality_score": 80}
SIGNALS = [SANCTION, BILL, UNRELATED]


def _ficha(slug):
    return json.loads((ROOT / "data/stats_fichas/live" / f"{slug}.json").read_text(encoding="utf-8"))


def make_root(tmp_path, *, f1=None, f6=None, cfg=None):
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "config/stats_fichas_v1.json", tmp_path / "config/stats_fichas_v1.json")
    conf = json.loads((ROOT / "config/weekly_insight_stats_anchor_v1.json").read_text(encoding="utf-8"))
    conf.update(cfg or {})
    (tmp_path / "config/weekly_insight_stats_anchor_v1.json").write_text(json.dumps(conf), encoding="utf-8")
    live = tmp_path / "data/stats_fichas/live"
    live.mkdir(parents=True, exist_ok=True)
    f1 = f1 if f1 is not None else {**_ficha("f1_cartera"), "published_at": "2026-10-30"}
    for slug, ficha in (("f1_cartera", f1), ("f6_prestadores", f6)):
        if ficha:
            (live / f"{slug}.json").write_text(json.dumps(ficha, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "data/weekly_insight").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/global").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/global/themes.json").write_text(json.dumps({"themes": []}), encoding="utf-8")
    return tmp_path


# --- 1. selection rule ------------------------------------------------------------------------

def test_new_period_pass_in_week_is_the_primary_candidate_with_reason(tmp_path):
    root = make_root(tmp_path)
    p = sa.plan(SIGNALS, ANCHOR, root=root)
    assert p["status"] == "selected" and p["anchor"]["family"] == "F1"
    assert "período nuevo" in p["reason"] and "2026-10-30" in p["reason"] and "materialidad 2" in p["reason"]
    assert {x["url"] for x in p["cross_refs"]} == {SANCTION["source_url"], BILL["source_url"]}
    assert {x["kind"] for x in p["cross_refs"]} == {"sancion", "congreso"}
    assert all(x["why_relevant"] for x in p["cross_refs"])
    summary = sa.summary(p)
    assert summary["authorization"] == "Dirección 2026-11-02" and summary["anchor"]["ficha_id"] == "stats-ficha:F1:2026-08"


def test_materiality_breaks_ties_crossed_threshold_beats_a_later_plain_new_period(tmp_path):
    f1 = {**_ficha("f1_cartera"), "published_at": "2026-10-27"}  # featured, threshold_crossed
    f6 = {**_ficha("f6_prestadores"), "published_at": "2026-10-31", "triggers": ["new_period"], "featured": False}
    root = make_root(tmp_path, f1=f1, f6=f6)
    cfg = sa.load_config(root)
    ranked = [c for c in sa.stats_anchor_candidates(root, ANCHOR, cfg) if c["eligible"]]
    assert [c["family"] for c in ranked] == ["F1", "F6"]
    assert ranked[0]["materiality_level"] == 2 and ranked[1]["materiality_level"] == 1
    # Same materiality: the most recent publication wins.
    plain_f1 = {**f1, "triggers": ["new_period"], "featured": False}
    root = make_root(tmp_path, f1=plain_f1, f6=f6)
    ranked = [c for c in sa.stats_anchor_candidates(root, ANCHOR, cfg) if c["eligible"]]
    assert [c["family"] for c in ranked] == ["F6", "F1"]


@pytest.mark.parametrize("change, reason", [
    ({"published_at": "2026-10-02"}, "published_outside_week"),
    ({"published_at": "2026-11-02"}, "published_outside_week"),          # the Monday itself is next week's
    ({"status": "HOLD"}, "not_verified_pass"),
    ({"verification": {"verdict": "FAIL"}}, "not_verified_pass"),
    ({"triggers": ["revision"]}, "not_a_new_period"),
])
def test_only_a_verified_new_period_inside_the_week_is_eligible(tmp_path, change, reason):
    root = make_root(tmp_path, f1={**_ficha("f1_cartera"), "published_at": "2026-10-30", **change})
    p = sa.plan(SIGNALS, ANCHOR, root=root)
    assert p["status"] == "fallback" and p["reason"] == "no_stats_new_period_in_week"
    f1 = next(c for c in p["considered"] if c["family"] == "F1")
    assert not f1["eligible"] and reason in f1["reason"]


def test_config_flag_off_disables_the_rule(tmp_path):
    root = make_root(tmp_path, cfg={"enabled": False})
    assert sa.plan(SIGNALS, ANCHOR, root=root)["status"] == "disabled"


def test_same_ficha_is_not_anchored_two_weeks_in_a_row(tmp_path):
    root = make_root(tmp_path)
    prev = {"weekly_insight": {"stats_anchor": {"ficha_id": "stats-ficha:F1:2026-08"}}}
    p = sa.plan(SIGNALS, ANCHOR, root=root, previous=prev)
    assert p["status"] == "fallback" and "anchored_last_week" in p["considered"][0]["reason"]


def test_fewer_than_two_cross_sources_falls_back_before_any_draft(tmp_path):
    root = make_root(tmp_path)
    p = sa.plan([SANCTION, UNRELATED], ANCHOR, root=root)
    assert p["status"] == "fallback" and p["reason"] == "insufficient_cross_refs"
    assert p["tried"][0]["reason"] == "insufficient_cross_refs:1"


def test_own_series_loose_cards_and_held_signals_are_not_cross_references(tmp_path):
    root = make_root(tmp_path)
    loose = {"title": "Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE a Agosto 2026",
             "source_name": "Superintendencia de Salud", "signal_types": ["Datos"], "source_url": FX + "cartera-loose",
             "event_date": "2026-10-30", "what_happened": "Cartera de beneficiarios y cotizantes de isapres."}
    held = {**BILL, "source_url": FX + "held", "editorial_hold": True}
    p = sa.plan(SIGNALS + [loose, held], ANCHOR, root=root)
    urls = {x["url"] for x in p["cross_refs"]}
    assert FX + "cartera-loose" not in urls and FX + "held" not in urls


# --- 2. contract ------------------------------------------------------------------------------

def valid_draft(evidence):
    anchor_src = next(s for s in evidence["sources"] if s["role"] == "ancla")
    return {
        "headline": "Isapres: los cotizantes vuelven a crecer mientras el regulador multa alzas y el Senado reescribe la ley corta",
        "dek": "La cartera Isapre sumó 1.551.169 cotizantes en el último corte. En octubre, la Superintendencia multó a tres "
               "isapres por alzas no informadas y el Senado aprobó 14 indicaciones a la ley corta.",
        "key_figures": ["1.551.169 cotizantes en el sistema (ficha F1, Superintendencia de Salud)",
                        "1.296 cotizantes más que el mes previo (ficha F1)",
                        "1.200 UF en multas a tres isapres (Superintendencia de Salud)",
                        "14 indicaciones aprobadas y 6 rechazadas (Senado)"],
        "figure_sources": [{"figure": "1.551.169", "source_url": anchor_src["url"]},
                           {"figure": "1.296", "source_url": anchor_src["url"]},
                           {"figure": "1.200", "source_url": SANCTION["source_url"]},
                           {"figure": "14", "source_url": BILL["source_url"]},
                           {"figure": "6", "source_url": BILL["source_url"]}],
        "estimates": [],
        "charts": [{"id": "c1", "form": "columns", "headline": "El Senado aprobó la mayoría de las indicaciones",
                    "subtitle": "Indicaciones votadas en la comisión de Salud", "unit": "indicaciones",
                    "rows": [{"label": "Aprobadas", "value": 14}, {"label": "Rechazadas", "value": 6}],
                    "source": "Senado, datos abiertos", "note_refs": ["n3"]}],
        "essay": {
            "facts": {"heading": "Qué pasó", "paragraphs": [
                "La ficha de cartera de la Superintendencia registró 1.551.169 cotizantes y un aumento de 1.296 frente "
                "al corte previo.[^n1] En el mismo período, el regulador sancionó a tres isapres con multas por 1.200 UF "
                "en total por aplicar alzas de precio base sin informar a sus cotizantes.[^n2]",
                "En el Congreso, la comisión de Salud del Senado votó las indicaciones al proyecto que ajusta la ley corta "
                "y la tabla de factores, que fija cuánto paga cada afiliado según su edad y sexo.[^n3]"]},
            "reading": {"heading": "Tesis", "paragraphs": [
                "La recuperación de afiliados ocurre en un mercado con más vigilancia sobre precios y con reglas todavía en "
                "discusión. Si las aseguradoras ganan clientes mientras el regulador castiga alzas mal comunicadas, el "
                "espacio para recomponer ingresos vía precio se estrecha y la competencia se desplaza hacia la retención "
                "y el servicio.",
                "Para un ejecutivo, el repunte luce frágil: depende de que el Senado cierre la reforma sin nuevas "
                "obligaciones de devolución y de que la fiscalización no escale a más aseguradoras. Si ambas condiciones "
                "se cumplen, la mejora puede consolidarse; si no, el alivio sería transitorio."]}},
        "watch": [{"headline": "Votación en sala de la reforma",
                   "explanation": "Si el Senado aprueba las indicaciones sin cambios, la tabla de factores quedará fijada "
                                  "para los planes que se vendan el próximo año."},
                  {"headline": "Nuevas sanciones por alzas de precio base",
                   "explanation": "Una segunda ronda de multas indicaría que la fiscalización se extiende más allá de las "
                                  "aseguradoras ya sancionadas este mes."}],
        "watch_heading": "Qué mirar",
        "notes": [{"id": "n1", "kind": "coverage", "text": "Cifras de la ficha F1 de cartera de la Superintendencia de Salud."},
                  {"id": "n2", "kind": "coverage", "text": "Monto total informado por el regulador en la resolución de multa."},
                  {"id": "n3", "kind": "non_final", "text": "Proyecto en tramitación: lo votado en comisión aún no es ley."}],
        "sources": [{"label": anchor_src["label"], "url": anchor_src["url"], "role": "Dato ancla: cartera Isapre",
                     "short_label": "SIS cartera", "short_role": "ancla"},
                    {"label": "Superintendencia: multas por alzas no informadas", "url": SANCTION["source_url"],
                     "role": "Cruce: sanciones", "short_label": "SIS multas", "short_role": "sanciones"},
                    {"label": "Senado: indicaciones a la ley corta", "url": BILL["source_url"], "role": "Cruce: Congreso",
                     "short_label": "Senado", "short_role": "Congreso"}],
        "insight_teaser": "Los cotizantes vuelven a crecer, pero con multas por alzas y una reforma abierta el repunte es frágil.",
    }


@pytest.fixture
def selected(tmp_path):
    root = make_root(tmp_path)
    p = sa.plan(SIGNALS, ANCHOR, root=root)
    assert p["status"] == "selected"
    return root, p, sa.build_evidence(p, root)


def checked(raw, evidence):
    weekly = gen.normalize_draft(raw, evidence, ANCHOR)
    return weekly, sa.contract_check(weekly, evidence), gen.verify_candidate(weekly, evidence, ANCHOR)


def test_valid_draft_passes_contract_and_format_a(selected):
    _, _, evidence = selected
    weekly, contract, verification = checked(valid_draft(evidence), evidence)
    assert presentation_a_errors(weekly) == []
    assert verification["verdict"] == "PASS", verification["errors"]
    assert contract["verdict"] == "PASS", contract["errors"]
    assert contract["anchor_figures_used"] == 2 and len(contract["cross_sources_cited"]) == 2


def test_contract_fewer_than_two_cross_sources_cited_fails(selected):
    _, _, evidence = selected
    raw = valid_draft(evidence)
    raw["sources"] = [s for s in raw["sources"] if s["url"] != BILL["source_url"]]
    _, contract, _ = checked(raw, evidence)
    assert "cross_sources_below_min:1" in contract["errors"]


def test_contract_redundant_sentence_fails(selected):
    _, _, evidence = selected
    ficha_sentence = next(s for s in evidence["redundancy_corpus"] if not any(ch.isdigit() for ch in s)
                          and len(s.split()) >= 8)
    raw = valid_draft(evidence)
    raw["essay"]["reading"]["paragraphs"][1] += " " + ficha_sentence
    _, contract, _ = checked(raw, evidence)
    assert any(e.startswith("sentence_redundant_with_ficha:essay.reading[1]") for e in contract["errors"]), contract["errors"]


def test_contract_untraced_figure_fails(selected):
    _, _, evidence = selected
    raw = valid_draft(evidence)
    raw["essay"]["reading"]["paragraphs"][1] += " El gasto subiría 37%."
    _, contract, _ = checked(raw, evidence)
    assert "figure_untraced:essay.reading:37" in contract["errors"]
    # A figure attributed to a source that does not contain it also fails.
    raw = valid_draft(evidence)
    raw["figure_sources"][2] = {"figure": "1.200", "source_url": BILL["source_url"]}
    _, contract, _ = checked(raw, evidence)
    assert "figure_not_in_its_source:1.200" in contract["errors"]


def test_contract_more_than_two_anchor_figures_fails(selected):
    _, _, evidence = selected
    anchor_url = evidence["anchor_urls"][0]
    raw = valid_draft(evidence)
    raw["dek"] = raw["dek"].replace("en el último corte", "de 2.486.683 beneficiarios")
    raw["key_figures"].append("2.486.683 beneficiarios (ficha F1)")
    raw["figure_sources"].append({"figure": "2.486.683", "source_url": anchor_url})
    _, contract, _ = checked(raw, evidence)
    assert "anchor_figures_over_max:3" in contract["errors"]


def test_contract_paragraph_restating_ficha_fails(selected):
    _, _, evidence = selected
    raw = valid_draft(evidence)
    raw["essay"]["facts"]["paragraphs"][0] = ("Los cotizantes del sistema subieron a 1.551.169 en agosto, con +1.296 "
                                              "frente a julio.[^n1][^n2]")
    _, contract, _ = checked(raw, evidence)
    assert any(e.startswith("paragraph_restates_ficha:essay.facts[0]") for e in contract["errors"]), contract["errors"]


def test_contract_requires_tesis_and_que_mirar(selected):
    _, _, evidence = selected
    raw = valid_draft(evidence)
    raw["essay"]["reading"]["heading"] = "Lectura Alicanto"
    raw["watch"] = raw["watch"][:1]
    _, contract, _ = checked(raw, evidence)
    assert {"tesis_missing", "que_mirar_missing"} <= set(contract["errors"])


def test_brief_for_a_human_drafter_has_anchor_cross_refs_figures_and_contract(selected):
    _, p, evidence = selected
    brief = sa.build_brief(p, evidence, ANCHOR)
    assert brief["anchor"]["ficha_id"] == "stats-ficha:F1:2026-08" and brief["anchor"]["sources"]
    assert {x["url"] for x in brief["cross_references"]} == {SANCTION["source_url"], BILL["source_url"]}
    assert all(f["refs"] for f in brief["allowed_anchor_figures"])
    assert brief["contract"]["max_anchor_figures"] == 2 and "Tesis" in brief["contract"]["text"]
    json.dumps(brief, ensure_ascii=False)  # serialisable


# --- 3. end-to-end dry run (fake models, no network, no paid calls) ---------------------------

class FakeModels:
    def __init__(self, drafts, review):
        self.drafts, self.review, self.calls = list(drafts), review, []

    def __call__(self, prompt, *, feature, preferred_model, allow_luna_fallback, max_output_tokens):
        self.calls.append({"feature": feature, "model": preferred_model, "prompt": prompt})
        out = self.drafts.pop(0) if feature.endswith("draft") else self.review
        return SimpleNamespace(output=deepcopy(out), model=preferred_model, estimated_cost_usd=0.1,
                               response_id=f"fake-{len(self.calls)}")


PASS_REVIEW = {"verdict": "PASS", "issues": [], "lenses": {"editorial": "PASS"}}


@pytest.fixture(autouse=True)
def no_budget_file(monkeypatch):
    monkeypatch.setattr(gen, "monthly_budget", lambda: None)


def test_end_to_end_stats_anchor_publishes_with_selection_record(selected):
    root, _, evidence = selected
    fake = FakeModels([valid_draft(evidence)], PASS_REVIEW)
    result = gen.run_weekly_a(SIGNALS, as_of=ANCHOR, root=root, model_call=fake)
    assert result["status"] == "pass", (result.get("verification"), result.get("review"))
    assert [c["feature"] for c in fake.calls] == ["weekly_insight_a_stats_draft", "weekly_insight_a_review"]
    assert [c["model"] for c in fake.calls] == ["gpt-6-astra", "gpt-5.6-terra"]  # same writer and reviewer
    assert "CONTRATO FICHA ≠ INSIGHT" in fake.calls[0]["prompt"] and "CONTRATO FICHA" in fake.calls[1]["prompt"]
    assert result["topic_selection"]["status"] == "selected"
    assert result["verification"]["stats_anchor_contract"]["verdict"] == "PASS"
    assert result["weekly_insight"]["stats_anchor"]["ficha_id"] == "stats-ficha:F1:2026-08"
    assert result["total_cost_usd"] <= gen.MAX_RUN_USD
    written = gen.publish(result, root)
    payload = json.loads(Path(written["approved"]).read_text(encoding="utf-8"))
    assert payload["topic_selection"]["anchor"]["family"] == "F1"
    assert "período nuevo" in payload["topic_selection"]["reason"]


def test_end_to_end_contract_fail_falls_back_to_normal_topic(selected):
    root, _, evidence = selected
    weak = valid_draft(evidence)
    weak["essay"]["reading"]["paragraphs"][1] += " El gasto subiría 37%."
    normal = valid_draft(evidence)  # not valid for the normal topic's evidence: fails closed, never publishes
    fake = FakeModels([weak, normal], PASS_REVIEW)
    result = gen.run_weekly_a(SIGNALS, as_of=ANCHOR, root=root, model_call=fake)
    assert [c["feature"] for c in fake.calls] == ["weekly_insight_a_stats_draft", "weekly_insight_a_draft"]
    assert result["topic_selection"]["status"] == "fallback"
    assert result["topic_selection"]["reason"] == "stats_anchor_contract_fail"
    assert any(e.startswith("stats_contract:figure_untraced") for e in result["stats_anchor_attempt"]["verification"]["errors"])
    assert result["evidence"]["candidate"]["url"] == UNRELATED["source_url"]  # normal ranking took over
    assert result["status"] == "deterministic_fail" and result["weekly_insight"] is None
    written = gen.publish(result, root)
    record = json.loads(Path(written["candidate"]).read_text(encoding="utf-8"))
    assert record["stats_anchor_attempt"]["status"] == "deterministic_fail"


def test_end_to_end_without_stats_release_uses_normal_selection(tmp_path):
    root = make_root(tmp_path, f1={**_ficha("f1_cartera")})  # published 2-oct: outside the week
    fake = FakeModels([{}], PASS_REVIEW)
    result = gen.run_weekly_a(SIGNALS, as_of=ANCHOR, root=root, model_call=fake)
    assert result["topic_selection"]["status"] == "fallback"
    assert [c["feature"] for c in fake.calls] == ["weekly_insight_a_draft"]
    assert result["evidence"]["candidate"]["url"] == UNRELATED["source_url"]
