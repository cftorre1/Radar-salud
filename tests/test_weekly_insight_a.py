"""Monday weekly insight, format A: generator with fake models, validator rules 3 and 5, Monday anchor."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from radar_salud import weekly_insight_a as gen
from radar_salud.weekly_freshness import (freshness_gate, monday_anchor, numbers_in, presentation_a_errors,
                                          reviewed_weekly, unexplained_normative_ids, untraced_numbers,
                                          chart_repetition_warnings)

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = date(2026, 11, 2)
DRAFT = ROOT / "data/weekly_insight/candidates/2026-11-02-draft.json"


def history():
    return json.loads((ROOT / "data/history/superintendencia_signals.json").read_text(encoding="utf-8"))["signals"]


def approved_weekly():
    return json.loads((ROOT / "data/weekly_insight/editorial_approved.json").read_text(encoding="utf-8"))["weekly_insight"]


def draft():
    return json.loads(DRAFT.read_text(encoding="utf-8"))


def ageing_signals():
    sig = history()
    find = lambda p: next(s for s in sig if s["title"].startswith(p))
    main = find("Chile, país poco preparado para envejecer")
    return main, [find("Comité Social: Salud y Mideso"), find("Ministro Mas en Chile 100"), find("Senior housing")]


class FakeModels:
    """Fake writer/reviewer: records calls, returns canned JSON, never touches the network."""

    def __init__(self, draft_output, review_output=None, cost=0.1, same_model=False):
        self.draft_output, self.review_output, self.cost, self.same_model = draft_output, review_output, cost, same_model
        self.calls = []

    def __call__(self, prompt, *, feature, preferred_model, allow_luna_fallback, max_output_tokens):
        self.calls.append({"feature": feature, "model": preferred_model, "max_output_tokens": max_output_tokens,
                           "fallback": allow_luna_fallback, "prompt": prompt})
        output = self.draft_output if feature.endswith("draft") else self.review_output
        model = self.calls[0]["model"] if self.same_model else preferred_model
        return SimpleNamespace(output=deepcopy(output), model=model, estimated_cost_usd=self.cost,
                               response_id=f"fake-{len(self.calls)}", fallback_used=False)


@pytest.fixture
def pipeline(monkeypatch):
    main, related = ageing_signals()
    monkeypatch.setattr(gen, "related_signals", lambda c, s, a, **kw: related if c is main else [])
    raw = draft()["weekly_insight"]
    return {"signals": [main] + related, "raw": raw}


PASS_REVIEW = {"verdict": "PASS", "issues": [{"severity": "minor", "where": "dek", "text": "ok"}],
               "lenses": {"editorial": "PASS", "health_business": "PASS", "data": "PASS", "evidence": "PASS",
                          "decision_intelligence": "PASS"}}


# --- generator with fake models -------------------------------------------------------------

def test_pass_publishes_monday_insight_and_archives_previous(pipeline, tmp_path):
    fake = FakeModels(pipeline["raw"], PASS_REVIEW)
    result = gen.run_weekly_a(pipeline["signals"], as_of=date(2026, 11, 2), model_call=fake)
    assert result["status"] == "pass", (result.get("verification"), result.get("review"))
    assert [c["feature"] for c in fake.calls] == ["weekly_insight_a_draft", "weekly_insight_a_review"]
    assert fake.calls[0]["model"] == "gpt-6-astra" and fake.calls[1]["model"] == "gpt-5.6-terra"
    assert not any(c["fallback"] for c in fake.calls)
    weekly = result["weekly_insight"]
    assert weekly["freshness_anchor_date"] == "2026-11-02" and weekly["expires_on"] == "2026-11-09"
    assert weekly["anchor_kind"] == "monday" and weekly["schema_version"] == "weekly_insight_a_v1"
    folder = tmp_path / "data/weekly_insight"
    folder.mkdir(parents=True)
    (folder / "editorial_approved.json").write_text((ROOT / "data/weekly_insight/editorial_approved.json").read_text())
    written = gen.publish(result, tmp_path)
    assert written["published"] and (folder / "archive/2026-10-23.json").exists()
    payload = json.loads((folder / "editorial_approved.json").read_text())
    for day in (date(2026, 11, 2), date(2026, 11, 8)):
        assert reviewed_weekly(payload, day)["id"] == weekly["id"]
    assert reviewed_weekly(payload, date(2026, 11, 9)) is None  # expires the next Monday
    assert reviewed_weekly(payload, date(2026, 11, 1)) is None


def test_invented_number_fails_deterministically_without_review_or_publication(pipeline, tmp_path):
    raw = deepcopy(pipeline["raw"])
    raw["essay"]["reading"]["paragraphs"][1] += " El gasto subiría 37%."
    fake = FakeModels(raw, PASS_REVIEW)
    result = gen.run_weekly_a(pipeline["signals"], as_of=ANCHOR, model_call=fake)
    assert result["status"] == "deterministic_fail"
    assert any(e.startswith("number_untraced:essay.reading:37") for e in result["verification"]["errors"])
    assert len(fake.calls) == 1  # the reviewer is never paid for a deterministic FAIL
    folder = tmp_path / "data/weekly_insight"
    folder.mkdir(parents=True)
    before = (ROOT / "data/weekly_insight/editorial_approved.json").read_text()
    (folder / "editorial_approved.json").write_text(before)
    written = gen.publish(result, tmp_path)
    assert not written["published"]
    assert (folder / "editorial_approved.json").read_text() == before
    saved = json.loads((folder / "candidates/2026-11-02-candidate.json").read_text())
    assert saved["status"] == "deterministic_fail" and saved["candidate"]["headline"]


def test_key_figure_not_in_evidence_and_foreign_source_fail(pipeline):
    raw = deepcopy(pipeline["raw"])
    raw["key_figures"].append("El 47% de los mayores vive solo.")
    raw["sources"].append({"label": "Otra", "url": "https://example.org/otra", "role": "x"})
    weekly = gen.normalize_draft(raw, gen.build_evidence({"signal": pipeline["signals"][0], "related": pipeline["signals"][1:]}), ANCHOR)
    assert "https://example.org/otra" not in weekly["source_refs"]  # dropped, never published
    errors = gen.verify_candidate(weekly, gen.build_evidence({"signal": pipeline["signals"][0], "related": pipeline["signals"][1:]}), ANCHOR)["errors"]
    assert "key_figure_not_in_evidence:47" in errors


def test_estimates_are_recomputed_and_chart_series_come_from_repo(pipeline):
    raw = deepcopy(pipeline["raw"])
    raw["estimates"][0]["value"] = 50  # model's arithmetic is ignored
    evidence = gen.build_evidence({"signal": pipeline["signals"][0], "related": pipeline["signals"][1:]})
    evidence["series"] = [{"id": "s1", "label": "Serie", "unit": "x", "source_url": None,
                           "rows": [{"label": "a", "value": 309}, {"label": "b", "value": 345}]}]
    raw["charts"][1]["series_ref"] = "s1"
    raw["charts"][1]["rows"] = [{"label": "a", "value": 999}]
    weekly = gen.normalize_draft(raw, evidence, ANCHOR)
    assert weekly["estimates"][0]["value"] == pytest.approx(96.52, abs=0.01)
    assert [r["value"] for r in weekly["charts"][1]["rows"]] == [309, 345]


def test_reviewer_fail_or_blocker_never_publishes(pipeline):
    for review in ({"verdict": "FAIL", "issues": []},
                   {"verdict": "PASS", "issues": [{"severity": "blocker", "where": "headline", "text": "causalidad"}]}):
        result = gen.run_weekly_a(pipeline["signals"], as_of=ANCHOR, model_call=FakeModels(pipeline["raw"], review))
        assert result["status"] == "review_fail" and result["weekly_insight"] is None


def test_reviewer_must_be_a_different_model(pipeline):
    fake = FakeModels(pipeline["raw"], PASS_REVIEW, same_model=True)
    result = gen.run_weekly_a(pipeline["signals"], as_of=ANCHOR, model_call=fake)
    assert result["status"] == "review_fail"


def test_run_cost_cap_blocks_calls_before_spending(pipeline):
    fake = FakeModels(pipeline["raw"], PASS_REVIEW)
    result = gen.run_weekly_a(pipeline["signals"], as_of=ANCHOR, model_call=fake, max_run_usd=0.05)
    assert result["status"] == "generation_error" and "weekly_run_cap" in result["error"]
    assert fake.calls == []


def test_cost_estimate_stays_under_one_dollar(pipeline):
    evidence = gen.build_evidence({"signal": pipeline["signals"][0], "related": pipeline["signals"][1:]})
    cost = gen.estimate_run_cost(evidence, anchor=ANCHOR)
    assert cost["draft_model"] == "gpt-6-astra" and cost["review_model"] == "gpt-5.6-terra"
    assert cost["typical_usd"] < cost["worst_case_usd"] < 1.0


def test_model_error_is_fail_closed(pipeline):
    def broken(prompt, **kw):
        raise RuntimeError("monthly_api_budget_exhausted")
    result = gen.run_weekly_a(pipeline["signals"], as_of=ANCHOR, model_call=broken)
    assert result["status"] == "generation_error" and result["weekly_insight"] is None


def test_topic_selection_uses_14_days_before_monday_and_skips_last_week():
    sig = history()
    prev = approved_weekly()
    ranked = gen.select_topic(sig, ANCHOR, recent_urls=set(prev["source_refs"]), recent_text=prev["headline"])
    assert ranked
    for row in ranked:
        d = date.fromisoformat(row["signal"]["event_date"][:10])
        assert 0 < (ANCHOR - d).days <= 14
        assert row["signal"]["source_url"] not in prev["source_refs"]
    assert ranked == gen.select_topic(sig, ANCHOR, recent_urls=set(prev["source_refs"]), recent_text=prev["headline"])


# --- draft for Monday 2-nov-2026 ------------------------------------------------------------

def test_november_2_draft_passes_deterministic_rules_but_stays_on_hold():
    payload = draft()
    weekly = payload["weekly_insight"]
    assert payload["verification"]["verdict"] == "PASS"
    assert presentation_a_errors(weekly) == []
    assert weekly["freshness_anchor_date"] == "2026-11-02" and date(2026, 11, 2).weekday() == 0
    assert payload["audit"]["verdict"] == "HOLD" and weekly["editorial_review_pass"] is False
    assert reviewed_weekly(payload, ANCHOR) is None  # never published without independent review
    assert all(s["url"].startswith("https://") for s in weekly["sources"])


# --- rule 3: traceability -------------------------------------------------------------------

def test_rule3_number_parsing_ignores_dates_years_and_normative_ids():
    found = [t for t, _, _ in numbers_in("La Ley 21.822 rige desde el 1 de junio de 2027; Circular 3931 e IF/N°10670: 5.155.495 y −12,3%")]
    assert found == ["5.155.495", "−12,3"]


def test_rule3_approved_licencias_insight_traces_every_number():
    w = approved_weekly()
    assert untraced_numbers(w) == []
    assert chart_repetition_warnings(w) == []


def test_rule3_untraced_numbers_fail():
    w = approved_weekly()
    w["essay"]["facts"]["paragraphs"].append("Las Isapres gastaron 41,7% más.")
    w["charts"][1]["rows"][0]["value"] = 37
    w["dek"] += " Y 9.999 casos."
    errors = presentation_a_errors(w)
    assert "number_untraced:essay.facts:41,7" in errors
    assert "number_untraced:chart.sanciones:Ago=37.0" in errors
    assert "number_untraced:dek:9.999" in errors


def test_rule3_rounded_display_traces_to_estimate_with_half_up():
    w = approved_weekly()
    w["estimates"].append({"id": "x", "value": 96.52, "formula": "333 / 345 * 100"})
    w["essay"]["reading"]["paragraphs"].append("Cerca del 97% del mapa.")
    assert not any("97" in e for e in untraced_numbers(w))
    w["essay"]["reading"]["paragraphs"].append("O 96,6% exacto.")
    assert "essay.reading:96,6" in untraced_numbers(w)


def test_rule3_chart_value_repeated_in_facts_is_only_a_warning():
    w = approved_weekly()
    w["essay"]["facts"]["paragraphs"][0] += " Hubo 36 oficios en agosto."
    assert "chart_value_repeated_in_facts:36" in chart_repetition_warnings(w)
    assert presentation_a_errors(w) == []


# --- rule 5: normative IDs in plain language ------------------------------------------------

def test_rule5_watch_id_requires_plain_language_rule():
    w = approved_weekly()
    assert unexplained_normative_ids(w) == []
    w["watch"][1]["explanation"] = "Seguir de cerca la aplicación práctica de la Circular 3931 en las próximas semanas."
    assert unexplained_normative_ids(w) == ["watch[1]:Circular 3931"]
    assert any(e.startswith("normative_id_unexplained:watch[1]") for e in presentation_a_errors(w))


def test_rule5_essay_sentence_with_bare_id_fails_and_explained_id_passes():
    w = approved_weekly()
    w["essay"]["reading"]["paragraphs"].append("Atención al DS 3.")
    assert "essay:DS 3" in unexplained_normative_ids(w)
    w = approved_weekly()
    w["essay"]["reading"]["paragraphs"].append("La Ley 21.822 obliga a dictar una política nacional de envejecimiento.")
    assert unexplained_normative_ids(w) == []


# --- Monday anchor and expiry ---------------------------------------------------------------

def test_monday_anchor_for_every_day_of_the_week():
    for offset in range(7):
        assert monday_anchor(date(2026, 11, 2 + offset)) == ANCHOR
    assert monday_anchor(date(2026, 11, 9)) == date(2026, 11, 9)


def monday_weekly(**kw):
    w = {"anchor_kind": "monday", "freshness_anchor_date": "2026-11-02", "expires_on": "2026-11-09", "event_date": "2026-10-23"}
    w.update(kw)
    return w


def test_monday_gate_window_and_expiry():
    assert freshness_gate(monday_weekly(), date(2026, 11, 2))["eligible"]
    assert freshness_gate(monday_weekly(), date(2026, 11, 8))["eligible"]
    assert not freshness_gate(monday_weekly(), date(2026, 11, 9))["eligible"]
    assert not freshness_gate(monday_weekly(), date(2026, 11, 1))["eligible"]
    assert freshness_gate(monday_weekly(), date(2026, 11, 2))["expires_on"] == "2026-11-09"


def test_monday_gate_rejects_bad_anchor_expiry_or_old_event():
    for bad in (dict(freshness_anchor_date="2026-11-03", expires_on="2026-11-10"),   # not a Monday
                dict(expires_on="2026-11-16"),                                       # longer than a week
                dict(event_date="2026-10-18"),                                       # 15 days before anchor
                dict(event_date="2026-11-03"),                                       # after the anchor
                dict(expires_on=None)):
        assert not freshness_gate(monday_weekly(**bad), date(2026, 11, 3))["eligible"], bad


def test_legacy_friday_anchor_keeps_its_own_rule():
    w = approved_weekly()
    assert "anchor_kind" not in w
    assert freshness_gate(w, date(2026, 10, 29))["eligible"]
    assert not freshness_gate(w, date(2026, 10, 30))["eligible"]


# --- schedule -------------------------------------------------------------------------------

def test_weekly_insight_workflow_runs_monday_on_staging_writer():
    text = (ROOT / ".github/workflows/weekly-insight.yml").read_text(encoding="utf-8")
    assert "cron: '30 9 * * 1'" in text
    assert "group: alicanto-staging-writer" in text and "ref: staging" in text
    assert "scripts/run_weekly_insight_a.py" in text and "tests/test_reviewer.py" in text
    assert "git pull --rebase origin staging" in text and "staging-preview.yml" in text
    assert "web/data/free_value.json" in text and "data/weekly_insight" in text
    for forbidden in ("ref: main", "origin main", "HEAD:main", "--ref main"):
        assert forbidden not in text
    v2 = (ROOT / ".github/workflows/weekly-insight-v2.yml").read_text(encoding="utf-8")
    assert "schedule:" not in v2
