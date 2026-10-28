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


# The 2-nov candidate was written from four La Tercera rows (/horizontes/, /nacional/, /pulso/).
# Since Dirección 28-oct (policy 1.3.0) every La Tercera section is paid, so those rows now
# carry only title + public lead. The generator/validator mechanics below replay the history
# as committed on staging dd94d38d (before the rights migration), read from git; the 2-nov
# gate test checks the current history too.
STAGING_HISTORY = ("dd94d38d96328f75ce766d4ab1d0980b53fff154", "data/history/superintendencia_signals.json")


def _staging_blob(path):
    import subprocess
    out = subprocess.run(["git", "show", f"{STAGING_HISTORY[0]}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode:
        pytest.skip("staging blob unavailable (shallow clone)")
    return json.loads(out.stdout)


def historical_history():
    return _staging_blob(STAGING_HISTORY[1])["signals"]


def historical_draft():
    """The 2-nov draft as committed on staging (its La Tercera-derived copy is now redacted)."""
    return _staging_blob("data/weekly_insight/candidates/2026-11-02-draft.json")


def approved_weekly():
    return json.loads((ROOT / "data/weekly_insight/editorial_approved.json").read_text(encoding="utf-8"))["weekly_insight"]


def draft():
    return json.loads(DRAFT.read_text(encoding="utf-8"))


def ageing_signals():
    sig = historical_history()
    find = lambda p: next(s for s in sig if s["title"].startswith(p))
    # Dirección 28-oct-2026: the topic must come from the 7 days before the Monday; move the
    # recorded lead story into that window (complements keep their real, older dates).
    main = {**find("Chile, país poco preparado para envejecer"), "event_date": "2026-10-28"}
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
    raw = {**historical_draft()["weekly_insight"], "event_date": "2026-10-28"}
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


def test_topic_selection_uses_7_days_before_monday_and_skips_last_week():
    sig = history()
    prev = approved_weekly()
    ranked = gen.select_topic(sig, ANCHOR, recent_urls=set(prev["source_refs"]), recent_text=prev["headline"])
    assert ranked
    for row in ranked:
        d = date.fromisoformat(row["signal"]["event_date"][:10])
        assert 0 < (ANCHOR - d).days <= 7
        assert row["signal"]["source_url"] not in prev["source_refs"]
    assert ranked == gen.select_topic(sig, ANCHOR, recent_urls=set(prev["source_refs"]), recent_text=prev["headline"])


# --- draft for Monday 2-nov-2026 ------------------------------------------------------------

def evidence_for(signals):
    return gen.build_evidence({"signal": signals[0], "related": signals[1:]})


def test_november_2_draft_passes_deterministic_rules_but_stays_on_hold(pipeline):
    # As written (staging), against the history it was written from, the gate passes.
    weekly = {**historical_draft()["weekly_insight"], "event_date": "2026-10-28"}  # 23-oct lead vs 7-day rule
    verification = gen.verify_candidate(weekly, evidence_for(pipeline["signals"]), ANCHOR)
    assert verification["verdict"] == "PASS", verification["errors"]
    assert presentation_a_errors(weekly) == []
    assert weekly["freshness_anchor_date"] == "2026-11-02" and date(2026, 11, 2).weekday() == 0
    # Policy 1.3.0 (Dirección 28-oct): its four La Tercera sources are paid. The stored draft
    # keeps only text the public leads support (the rest is receipted) and, against the current
    # history, no longer traces its figures: it cannot leave HOLD as written.
    payload = draft()
    current_draft = {**payload["weekly_insight"], "event_date": "2026-10-28"}
    assert current_draft["key_figures"] == [] and any(r["field"] == "key_figures"
                                                      for r in current_draft["rights_redactions"])
    current = {s["source_url"]: s for s in history()}
    signals = [dict(current[s["source_url"]], event_date=s["event_date"]) for s in pipeline["signals"]]
    assert all(s["paywalled"] is True for s in signals)
    now = gen.verify_candidate(current_draft, evidence_for(signals), ANCHOR)
    assert now["verdict"] == "FAIL"
    assert payload["audit"]["verdict"] == "HOLD" and current_draft["editorial_review_pass"] is False
    assert reviewed_weekly(payload, ANCHOR) is None  # never published without independent review
    assert all(s["url"].startswith("https://") for s in current_draft["sources"])


# --- rule 3: traceability -------------------------------------------------------------------

def normalized(pipeline, raw=None):
    evidence = evidence_for(pipeline["signals"])
    return gen.normalize_draft(deepcopy(raw or pipeline["raw"]), evidence, ANCHOR), evidence


def verify_errors(weekly, evidence):
    result = gen.verify_candidate(weekly, evidence, ANCHOR)
    assert result["verdict"] == "FAIL"
    return result["errors"]


def test_rule3_self_referencing_estimate_fails(pipeline):
    weekly, evidence = normalized(pipeline)
    weekly["estimates"].append({"id": "own", "label": "x", "value": 3717, "formula": "3717", "inputs": [],
                                "note_ref": "n2"})
    weekly["essay"]["reading"]["paragraphs"].append("Serían 3.717 personas.")
    assert "estimate_input_not_in_evidence:own:3717" in verify_errors(weekly, evidence)


def test_rule3_estimate_may_use_an_earlier_estimate_but_not_a_later_one(pipeline):
    weekly, evidence = normalized(pipeline)
    # Factor 24 (comunas, open Desarrollo Social source). The former factor 2 only existed in the
    # locked Pulso body, which the evidence no longer carries (rights policy, Dirección 28-oct-2026).
    weekly["estimates"].append({"id": "chain", "label": "x", "value": 7416.0, "formula": "309 * 24", "inputs": [],
                                "note_ref": "n2"})
    errors = gen.verify_candidate(weekly, evidence, ANCHOR)["errors"]
    assert not any(":chain:" in e for e in errors)  # 309 = earlier estimate comunas_actuales
    weekly["estimates"].insert(0, weekly["estimates"].pop())  # now it comes before 309 is derived
    assert "estimate_input_not_in_evidence:chain:309" in verify_errors(weekly, evidence)


def test_rule3_number_only_in_estimate_inputs_or_display_fails(pipeline):
    weekly, evidence = normalized(pipeline)
    weekly["estimates"][0]["inputs"].append("4.321 comunas rurales")
    weekly["essay"]["reading"]["paragraphs"].append("Hay 4.321 comunas rurales.")
    errors = verify_errors(weekly, evidence)
    assert "estimate_inputs_not_in_evidence:cobertura_red:4.321" in errors
    assert "number_untraced:essay.reading:4.321" in errors  # inputs are not a trace origin
    weekly, evidence = normalized(pipeline)
    weekly["estimates"][1]["display"] = "5.555"
    weekly["dek"] += " Unas 5.555."
    errors = verify_errors(weekly, evidence)
    assert "estimate_display_not_traced:comunas_actuales:5.555" in errors
    assert "number_untraced:dek:5.555" in errors
    assert "number_untraced:estimate.comunas_actuales.display:5.555" in errors


@pytest.mark.parametrize("where,mutate", [
    ("chart.iniciativas.subtitle", lambda w: w["charts"][0].update(subtitle="Iniciativas, 47% de las analizadas")),
    ("chart.iniciativas.headline", lambda w: w["charts"][0].update(headline="Solo 47 iniciativas miran el envejecimiento")),
    ("chart.iniciativas.row_label", lambda w: w["charts"][0]["rows"][0].update(label="Todas (847)")),
    ("chart.red_cuidados.partial_label", lambda w: w["charts"][1]["rows"][1].update(partial_label="meta a 47 meses")),
    ("chart.iniciativas.source", lambda w: w["charts"][0].update(source="Estudio con 47 expertos.")),
    ("notes", lambda w: w["notes"][0].update(text=w["notes"][0]["text"] + " Margen de error 47%.")),
    ("insight_teaser", lambda w: w.update(insight_teaser="47% de los mayores dice no tener apoyo.")),
    ("sources.label", lambda w: w["sources"][0].update(label="La Tercera · 47 claves del envejecimiento")),
    ("sources.role", lambda w: w["sources"][1].update(role="Prensa: 47 comunas nuevas.")),
    ("headline", lambda w: w.update(headline="47% sin apoyo")),
    ("watch", lambda w: w["watch"][0].update(explanation=w["watch"][0]["explanation"] + " Hay 47 casos.")),
])
def test_rule3_invented_number_in_any_displayed_field_fails(pipeline, where, mutate):
    weekly, evidence = normalized(pipeline)
    mutate(weekly)
    errors = verify_errors(weekly, evidence)
    assert any(e.startswith(f"number_untraced:{where}:") and e.endswith(("47", "847")) for e in errors), errors
    assert reviewed_weekly({"audit": {"verdict": "PASS", "editorial_business_review_pass": True},
                            "weekly_insight": weekly}, ANCHOR) is None


def test_rule3_short_press_dates_are_not_quantities():
    assert numbers_in("La Tercera (23 oct) y Pulso, 9-10 oct.; 47 mayores") == [("47", 47.0, 0)]


def test_parse_failed_call_cost_counts_in_run_total(pipeline):
    class ParseError(RuntimeError):
        estimated_cost_usd, response_id = 0.42, "resp-x"

    def broken(prompt, **kw):
        raise ParseError("model_call_failed:JSONDecodeError")
    result = gen.run_weekly_a(pipeline["signals"], as_of=ANCHOR, model_call=broken)
    assert result["status"] == "generation_error" and result["total_cost_usd"] == pytest.approx(0.42)
    assert result["model_calls"][0]["cost_usd"] == pytest.approx(0.42)


def test_monthly_paced_budget_blocks_call_before_spending(pipeline, monkeypatch):
    monkeypatch.setattr(gen, "monthly_budget", lambda: {"spent_usd": 4.95, "paced_budget_usd": 5.0})
    fake = FakeModels(pipeline["raw"], PASS_REVIEW)
    result = gen.run_weekly_a(pipeline["signals"], as_of=ANCHOR, model_call=fake)
    assert result["status"] == "generation_error" and "monthly_paced_budget" in result["error"]
    assert fake.calls == []


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
    w = {"anchor_kind": "monday", "freshness_anchor_date": "2026-11-02", "expires_on": "2026-11-09", "event_date": "2026-10-28"}
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
                dict(event_date="2026-10-25"),                                       # 8 days before anchor (7-day rule)
                dict(event_date="2026-11-03"),                                       # after the anchor
                dict(expires_on=None)):
        assert not freshness_gate(monday_weekly(**bad), date(2026, 11, 3))["eligible"], bad


def test_legacy_friday_anchor_keeps_its_own_rule():
    w = approved_weekly()
    assert "anchor_kind" not in w
    assert freshness_gate(w, date(2026, 10, 29))["eligible"]
    # Bridged until Monday 2-nov by Dirección's switch to Monday insights (27-oct-2026).
    assert freshness_gate(w, date(2026, 11, 1))["eligible"]
    assert not freshness_gate(w, date(2026, 11, 2))["eligible"]


# --- schedule -------------------------------------------------------------------------------

def test_weekly_insight_workflow_runs_monday_on_staging_writer():
    text = (ROOT / ".github/workflows/weekly-insight.yml").read_text(encoding="utf-8")
    for cron in ("cron: '30 9 * * 1'", "cron: '45 11 * * 1'", "cron: '45 15 * * 1'"):
        assert cron in text
    assert "group: alicanto-staging-writer" in text and "ref: staging" in text
    assert "scripts/run_weekly_insight_a.py" in text and "tests/test_reviewer.py" in text
    assert "git pull --rebase origin staging" in text and "staging-preview.yml" in text
    assert "web/data/free_value.json" in text and "data/weekly_insight" in text
    for forbidden in ("ref: main", "origin main", "HEAD:main", "--ref main"):
        assert forbidden not in text
    # Approved/public files only on success; candidates + ledger always; key scoped to generation.
    assert "if: always()" in text and "job.status == 'success'" in text
    key_lines = [i for i, line in enumerate(text.splitlines()) if "OPENAI_API_KEY:" in line]
    generate = next(i for i, line in enumerate(text.splitlines()) if "- name: Generate" in line)
    assert len(key_lines) == 1 and generate < key_lines[0] < generate + 4  # only the generation step
    assert "git rebase --abort" in text
    v2 = (ROOT / ".github/workflows/weekly-insight-v2.yml").read_text(encoding="utf-8")
    assert "schedule:" not in v2 and "push:" not in v2 and "workflow_dispatch" in v2
    assert "group: alicanto-staging-writer" in v2


def test_legacy_insight_bridges_to_the_next_monday_only():
    from datetime import date
    from radar_salud.weekly_freshness import freshness_gate
    sig = {"event_date": "2026-10-23", "freshness_anchor_date": "2026-10-23", "expires_on": "2026-11-02"}
    assert freshness_gate(sig, date(2026, 11, 1))["eligible"]
    assert not freshness_gate(sig, date(2026, 11, 2))["eligible"]
    assert not freshness_gate({**sig, "expires_on": "2026-11-09"}, date(2026, 11, 1))["eligible"]
    # Sunset: the bridge is a one-off for 2-nov; a later Friday insight cannot stretch to Monday.
    later = {"event_date": "2026-11-13", "freshness_anchor_date": "2026-11-13", "expires_on": "2026-11-23"}
    assert not freshness_gate(later, date(2026, 11, 21))["eligible"]


def test_runner_skips_a_paid_fail_candidate_unless_forced(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_weekly_insight_a", ROOT / "scripts/run_weekly_insight_a.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    folder = tmp_path / "data/weekly_insight/candidates"
    folder.mkdir(parents=True)
    assert runner.paid_fail_candidate(ANCHOR, tmp_path) is None
    path = folder / "2026-11-02-candidate.json"
    path.write_text(json.dumps({"status": "generation_error", "total_cost_usd": 0}))
    assert runner.paid_fail_candidate(ANCHOR, tmp_path) is None  # nothing paid: a backstop may retry
    for record in ({"status": "review_fail", "total_cost_usd": 0.3}, {"status": "deterministic_fail"},
                   {"status": "generation_error", "total_cost_usd": 0.2}):
        path.write_text(json.dumps(record))
        assert runner.paid_fail_candidate(ANCHOR, tmp_path)["status"] == record["status"]
