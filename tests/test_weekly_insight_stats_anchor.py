"""Weekly Insight anchored on a stats-family release (Dirección, 2-nov-2026): selection rule,
ficha-vs-Insight contract and an end-to-end dry run with fake models. No network, no paid calls.

Fixtures: the live F1 ficha committed in the repo, copied to a temporary root with its
``published_at`` and ``first_verified_at`` moved into the Insight week; the cross-reference signals
below are test fixtures on a ``fixture.alicanto.test`` host, not product data."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from radar_salud import stats_fichas as sf
from radar_salud import weekly_insight_a as gen
from radar_salud import weekly_insight_stats_anchor as sa
from radar_salud.weekly_freshness import presentation_a_errors

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = date(2026, 11, 2)
FX = "https://fixture.alicanto.test/"
FV = "2026-10-30T14:00:00+00:00"  # first verification inside the week before Monday 2-nov

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
    f1 = f1 if f1 is not None else {**_ficha("f1_cartera"), "published_at": "2026-10-30", "first_verified_at": FV}
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
    assert "período nuevo" in p["reason"] and "materialidad 2" in p["reason"]
    # Decision 1: both dates are recorded, the SIS publication and the first verification.
    assert "la SIS lo publicó el 2026-10-30" in p["reason"] and "verificó por primera vez el 2026-10-30" in p["reason"]
    assert p["anchor"]["first_verified_basis"] == "ficha.first_verified_at"
    assert {x["url"] for x in p["cross_refs"]} == {SANCTION["source_url"], BILL["source_url"]}
    assert {x["kind"] for x in p["cross_refs"]} == {"sancion", "congreso"}
    assert all(x["why_relevant"] for x in p["cross_refs"])
    summary = sa.summary(p)
    assert summary["authorization"] == "Dirección 2026-11-02" and summary["anchor"]["ficha_id"] == "stats-ficha:F1:2026-08"


def test_materiality_breaks_ties_crossed_threshold_beats_a_later_plain_new_period(tmp_path):
    f1 = {**_ficha("f1_cartera"), "published_at": "2026-10-27", "first_verified_at": FV}  # featured, threshold_crossed
    f6 = {**_ficha("f6_prestadores"), "published_at": "2026-10-31", "first_verified_at": FV, "triggers": ["new_period"],
          "featured": False}
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
    ({"first_verified_at": "2026-10-20T12:00:00+00:00"}, "first_verified_outside_week"),
    ({"first_verified_at": "2026-11-02T12:00:00+00:00"}, "first_verified_outside_week"),  # the Monday is next week's
    ({"published_at": "2026-10-02"}, "sis_publication_older_than_30d"),   # verified this week, SIS release 31 days old
    ({"status": "HOLD"}, "not_verified_pass"),
    ({"verification": {"verdict": "FAIL"}}, "not_verified_pass"),
    ({"triggers": ["revision"]}, "not_a_new_period"),
])
def test_only_a_verified_new_period_inside_the_week_is_eligible(tmp_path, change, reason):
    root = make_root(tmp_path, f1={**_ficha("f1_cartera"), "published_at": "2026-10-30", "first_verified_at": FV, **change})
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
    def __init__(self, drafts, review, cost=0.1):
        self.drafts, self.review, self.calls, self.cost = list(drafts), review, [], cost

    def __call__(self, prompt, *, feature, preferred_model, allow_luna_fallback, max_output_tokens):
        self.calls.append({"feature": feature, "model": preferred_model, "prompt": prompt})
        out = self.drafts.pop(0) if feature.endswith("draft") else self.review
        return SimpleNamespace(output=deepcopy(out), model=preferred_model, estimated_cost_usd=self.cost,
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
    # The pipeline leaves the same brief + contract record an editorial session must leave.
    assert payload["weekly_insight"]["stats_anchor"]["brief_id"].startswith("stats-brief:2026-11-02:stats-ficha:F1:2026-08:")
    assert json.loads(Path(written["contract_record"]).read_text(encoding="utf-8"))["check"]["verdict"] == "PASS"
    assert sa.contract_gate(root) == []


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
    root = make_root(tmp_path, f1={**_ficha("f1_cartera"), "first_verified_at": "2026-10-28T08:10:11+00:00"})  # outside
    fake = FakeModels([{}], PASS_REVIEW)
    result = gen.run_weekly_a(SIGNALS, as_of=ANCHOR, root=root, model_call=fake)
    assert result["topic_selection"]["status"] == "fallback"
    assert [c["feature"] for c in fake.calls] == ["weekly_insight_a_draft"]
    assert result["evidence"]["candidate"]["url"] == UNRELATED["source_url"]


def test_contract_fail_fallback_stops_when_the_second_draft_does_not_fit_the_run_cap(selected):
    """Decision 2 (kept): the normal-topic redraft is paid only inside the same MAX_RUN_USD cap."""
    root, _, evidence = selected
    weak = valid_draft(evidence)
    weak["essay"]["reading"]["paragraphs"][1] += " El gasto subiría 37%."
    fake = FakeModels([weak, {}], PASS_REVIEW, cost=0.95)
    result = gen.run_weekly_a(SIGNALS, as_of=ANCHOR, root=root, model_call=fake)
    assert [c["feature"] for c in fake.calls] == ["weekly_insight_a_stats_draft"]
    assert result["status"] == "generation_error" and "weekly_run_cap_would_be_exceeded" in result["error"]
    assert result["weekly_insight"] is None and result["total_cost_usd"] <= gen.MAX_RUN_USD
    assert result["stats_anchor_attempt"]["status"] == "deterministic_fail"


def test_contract_fail_fallback_can_be_switched_off(tmp_path):
    root = make_root(tmp_path, cfg={"fallback_redraft_after_contract_fail": False})
    p = sa.plan(SIGNALS, ANCHOR, root=root)
    evidence = sa.build_evidence(p, root)
    weak = valid_draft(evidence)
    weak["essay"]["reading"]["paragraphs"][1] += " El gasto subiría 37%."
    fake = FakeModels([weak], PASS_REVIEW)
    result = gen.run_weekly_a(SIGNALS, as_of=ANCHOR, root=root, model_call=fake)
    assert len(fake.calls) == 1 and result["status"] == "deterministic_fail" and result["weekly_insight"] is None


# --- 4. decision 1: "new in the week" = first verification, SIS release ≤ 30 days -----------------

def test_late_verified_release_anchors_when_sis_publication_is_recent(tmp_path):
    # SIS published 12 days before the Monday; Alicanto verified it only on Friday.
    f1 = {**_ficha("f1_cartera"), "published_at": "2026-10-21", "first_verified_at": "2026-10-30T22:00:00+00:00"}
    p = sa.plan(SIGNALS, ANCHOR, root=make_root(tmp_path, f1=f1))
    assert p["status"] == "selected"
    assert "la SIS lo publicó el 2026-10-21 (12 días antes del lunes, tope 30)" in p["reason"]
    assert "verificó por primera vez el 2026-10-30" in p["reason"]
    assert sa.summary(p)["anchor"]["first_verified_at"] == "2026-10-30T22:00:00+00:00"


@pytest.mark.parametrize("published, eligible", [("2026-10-03", True), ("2026-10-02", False)])
def test_sis_publication_age_limit_is_thirty_days(tmp_path, published, eligible):
    f1 = {**_ficha("f1_cartera"), "published_at": published, "first_verified_at": FV}
    p = sa.plan(SIGNALS, ANCHOR, root=make_root(tmp_path, f1=f1))
    assert (p["status"] == "selected") is eligible


def test_first_verification_day_is_the_chile_calendar_day(tmp_path):
    # 2-nov 01:30 UTC is still Sunday 1-nov in Santiago: inside the week before Monday 2-nov.
    f1 = {**_ficha("f1_cartera"), "published_at": "2026-10-30", "first_verified_at": "2026-11-02T01:30:00+00:00"}
    assert sa.plan(SIGNALS, ANCHOR, root=make_root(tmp_path, f1=f1))["status"] == "selected"


def test_first_verified_falls_back_to_the_git_history_of_the_live_file(tmp_path):
    """A legacy live file without the stamp: the first committed PASS of the same release_key counts,
    not the later rebuild's generated_at."""
    root = make_root(tmp_path, f1={**_ficha("f1_cartera"), "published_at": "2026-10-30",
                                   "generated_at": "2026-10-29T15:00:00+00:00"})
    git = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
    git("init", "-q")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "first PASS")
    live = root / "data/stats_fichas/live/f1_cartera.json"
    ficha = json.loads(live.read_text(encoding="utf-8"))
    live.write_text(json.dumps({**ficha, "generated_at": "2026-11-05T10:00:00+00:00"}), encoding="utf-8")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "rebuild same release")
    sa._git_first_pass.cache_clear()
    fv = sa.first_verified(json.loads(live.read_text(encoding="utf-8")), root)
    assert fv["at"] == "2026-10-29T15:00:00+00:00" and fv["basis"].startswith("git_history:")
    # Outside a repository the live generated_at is used and labelled as an upper bound.
    assert sa.first_verified({**ficha, "slug": "nope"}, tmp_path / "x")["basis"].startswith("ficha.generated_at")


def test_stats_fichas_publish_stamps_first_verification_once_per_release(tmp_path):
    base = {k: v for k, v in _ficha("f1_cartera").items() if k != "first_verified_at"}
    res = lambda ficha: {"status": "pass", "slug": "f1_cartera", "ficha": deepcopy(ficha)}
    first = {**base, "generated_at": "2026-10-28T08:00:00+00:00"}
    sf.publish(res(first), tmp_path)
    assert sf.load_live(tmp_path, "f1_cartera")["first_verified_at"] == "2026-10-28T08:00:00+00:00"
    sf.publish(res({**base, "generated_at": "2026-11-04T08:00:00+00:00"}), tmp_path)  # rebuild, same release
    assert sf.load_live(tmp_path, "f1_cartera")["first_verified_at"] == "2026-10-28T08:00:00+00:00"
    sf.publish(res({**base, "release_key": "2026-09:new", "generated_at": "2026-11-06T08:00:00+00:00"}), tmp_path)
    assert sf.load_live(tmp_path, "f1_cartera")["first_verified_at"] == "2026-11-06T08:00:00+00:00"
    # A legacy live file of the same release without the stamp stays unstamped (git history decides).
    legacy = tmp_path / "legacy"
    sf._write(sf.paths(legacy, "f1_cartera")["live"], base)
    sf.publish(res({**base, "generated_at": "2026-11-07T08:00:00+00:00"}), legacy)
    assert "first_verified_at" not in sf.load_live(legacy, "f1_cartera")


# --- 5. decision 3: editorial gate (contract-check record) -------------------------------------

def editorial_insight(root, evidence, *, anchor_id=True):
    """An Insight written by an editorial session from the brief (no model)."""
    brief = sa.build_brief(sa.plan(SIGNALS, ANCHOR, root=root), evidence, ANCHOR)
    brief_path = root / "data/weekly_insight/candidates" / f"{ANCHOR.isoformat()}-stats-brief.json"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
    weekly = gen.normalize_draft(valid_draft(evidence), evidence, ANCHOR)
    weekly["model_trace"] = {"mode": "senior_editorial_work_session", "api_call": False}
    if anchor_id:
        weekly["stats_anchor"] = {"ficha_id": brief["anchor"]["ficha_id"], "brief_id": brief["brief_id"]}
    else:
        weekly.pop("stats_anchor", None)
    payload = {"status": "pass", "weekly_insight": weekly}
    (root / "data/weekly_insight/editorial_approved.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return weekly, brief, brief_path


def test_gate_blocks_an_anchored_editorial_insight_without_a_contract_record(selected):
    root, _, evidence = selected
    editorial_insight(root, evidence)
    errors = sa.contract_gate(root)
    assert len(errors) == 1 and "missing_contract_record(declared_stats_anchor)" in errors[0]


def test_gate_detects_an_undeclared_anchor_by_its_primary_stats_source(selected):
    root, _, evidence = selected
    weekly, _, _ = editorial_insight(root, evidence, anchor_id=False)
    assert weekly["source_url"] in sa.stats_source_urls(root)
    assert "missing_contract_record(primary_source_is_stats_ficha)" in sa.contract_gate(root)[0]


def test_gate_passes_with_a_pass_record_and_fails_once_the_insight_is_edited(selected):
    root, _, evidence = selected
    weekly, brief, brief_path = editorial_insight(root, evidence)
    rec = sa.write_contract_record(root, weekly, brief, brief_path, source_sha="abc123")
    assert rec["check"]["verdict"] == "PASS" and rec["brief_id"] == brief["brief_id"] and rec["source_sha"] == "abc123"
    assert rec["brief_path"] == "data/weekly_insight/candidates/2026-11-02-stats-brief.json"
    assert sa.contract_gate(root) == []
    approved = root / "data/weekly_insight/editorial_approved.json"
    payload = json.loads(approved.read_text(encoding="utf-8"))
    payload["weekly_insight"]["dek"] += " Cambio posterior."
    approved.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert "insight_changed_after_check" in sa.contract_gate(root)[0]


def test_gate_rejects_a_fail_record_and_a_forged_pass_record(selected):
    root, _, evidence = selected
    weekly, brief, brief_path = editorial_insight(root, evidence)
    weekly["essay"]["reading"]["paragraphs"][1] += " El gasto subiría 37%."
    payload = {"status": "pass", "weekly_insight": weekly}
    (root / "data/weekly_insight/editorial_approved.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    rec = sa.write_contract_record(root, weekly, brief, brief_path)
    assert rec["check"]["verdict"] == "FAIL"
    assert "contract_record_not_pass" in sa.contract_gate(root)[0]
    forged = {**json.loads(Path(rec["path"]).read_text(encoding="utf-8")), "check": {"verdict": "PASS", "errors": []}}
    Path(rec["path"]).write_text(json.dumps(forged), encoding="utf-8")
    assert "contract_recheck_fail" in sa.contract_gate(root)[0]


def test_gate_rejects_a_tampered_brief(selected):
    root, _, evidence = selected
    weekly, brief, brief_path = editorial_insight(root, evidence)
    sa.write_contract_record(root, weekly, brief, brief_path)
    tampered = json.loads(brief_path.read_text(encoding="utf-8"))
    tampered["contract_inputs"]["contract"]["min_cross_sources"] = 0
    brief_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
    assert "contract_recheck_fail" in sa.contract_gate(root)[0] and "brief_id_mismatch" in sa.contract_gate(root)[0]


def test_gate_does_not_block_normal_topic_insights(tmp_path):
    root = make_root(tmp_path)
    for name in ("editorial_approved.json", "archive/2026-10-26.json"):
        path = root / "data/weekly_insight" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": "pass", "weekly_insight": {
            "id": "weekly-insight:2026-10-26:licencias", "source_url": FX + "suseso",
            # a stats file cited as a secondary source does not make the Insight anchored
            "sources": [{"url": FX + "suseso"}, {"url": _ficha("f1_cartera")["sources"][0]["url"]}]}}), encoding="utf-8")
    assert sa.contract_gate(root) == []


def test_committed_weekly_insights_pass_the_contract_gate():
    """The CI gate itself: an editorial PR that adds a stats-anchored Insight without a PASS
    contract-check record for its exact content fails here (scripts/check_weekly_insight_contract.py --gate)."""
    assert sa.contract_gate(ROOT) == []
