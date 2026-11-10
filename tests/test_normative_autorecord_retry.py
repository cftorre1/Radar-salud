"""Repair loop, attempt caps, budget guard, latency and hourly step (Dirección 9-nov-2026 20:35)."""
import ast
import importlib.util
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import yaml

from src.radar_salud import normative_autorecord as auto
from src.radar_salud.normative_evidence import EVIDENCE_DIR, _key
from tests.test_normative_autorecord import EVIDENCE, GOOD, PDF, URL, _repo

TODAY = date(2026, 10, 27)
BAD = {**GOOD, "action_terms": ["Exige"],  # verb absent from the official text, paraphrased quote
       "plain_language_title": "Circular IF/N°537 · Urgencias GES: Exige a prestadores notificar en 24 horas",
       "evidence_quotes": ["La notificación se debe hacer en un plazo máximo de 24 horas.",
                           "Las presentes instrucciones entrarán en vigencia a contar del 1 de marzo de 2027."]}


def _fake(drafts, reviews=None, log=None):
    drafts, reviews = iter(drafts), iter(reviews or [])
    def call(prompt, *, feature, preferred_model, allow_luna_fallback=True):
        if log is not None:
            log.append((feature, prompt))
        if feature == auto.REVIEW_FEATURE:
            return SimpleNamespace(output=next(reviews, {"verdict": "PASS"}), estimated_cost_usd=0.005)
        return SimpleNamespace(output=next(drafts), estimated_cost_usd=0.01)
    return call


def _store(root):
    return json.loads((Path(root) / auto.AUTO_PATH).read_text(encoding="utf-8"))


def test_repair_loop_fake_model_fails_first_and_passes_second(tmp_path):
    signals = _repo(tmp_path)
    log = []
    out = auto.build_auto_records(tmp_path, signals, call=_fake([BAD, GOOD], log=log), today=TODAY, run_id="r1")
    assert out == [URL]
    assert [f for f, _ in log] == [auto.DRAFT_FEATURE, auto.REPAIR_FEATURE, auto.REVIEW_FEATURE]
    repair_prompt = log[1][1]
    # exact problem list, literal-only rules and the official text excerpt are fed back
    assert "action_not_in_official_text:Exige" in repair_prompt and "quote_not_literal" in repair_prompt
    assert "LITERALMENTE" in repair_prompt and "Elimina toda afirmación" in repair_prompt
    assert "menos puntos, más cortos y literales" in repair_prompt and "TEXTO OFICIAL:\nCIRCULAR IF/N°537" in repair_prompt
    store = _store(tmp_path)
    act = store["acts"][URL]
    assert act["attempts"] == 1 and act["runs"] == ["r1"] and act["status"] == "published"  # failed attempts
    assert store["source_records"][URL]["attempts"] == 2
    assert [e["kind"] for e in act["attempt_log"]] == [auto.DRAFT_FEATURE, auto.REPAIR_FEATURE, auto.REVIEW_FEATURE]
    assert act["attempt_log"][0]["cost_usd"] == 0.01 and act["attempt_log"][0]["problems"]
    assert store["source_records"][URL]["origin"] == "auto_verified" and URL not in store["rejected"]
    assert act["rejection_history"] == []  # nothing rejected at the end of the run


def test_only_drafts_passing_both_checks_are_written(tmp_path):
    signals = _repo(tmp_path)
    fail = {"verdict": "FAIL", "reason": "exagera"}
    out = auto.build_auto_records(tmp_path, signals, call=_fake([GOOD] * 3, [fail] * 3), today=TODAY, run_id="r1")
    assert out == [] and not _store(tmp_path)["source_records"]
    assert _store(tmp_path)["rejected"][URL]["problems"] == ["independent_review:exagera"]


def test_attempt_caps_six_attempts_then_final_rejection_with_history(tmp_path):
    signals = _repo(tmp_path)
    log = []
    for run in ("r1", "r2", "r3"):
        auto.build_auto_records(tmp_path, signals, call=_fake([BAD] * 10, log=log), today=TODAY, run_id=run)
    store = _store(tmp_path)
    act = store["acts"][URL]
    assert len(log) == 6 and act["attempts"] == 6 and act["runs"] == ["r1", "r2"]
    assert act["status"] == "final_rejected" and store["rejected"][URL]["final"] is True
    assert "quote_not_literal" in store["rejected"][URL]["problems"]
    assert [h.get("run_id") for h in act["rejection_history"][:2]] == ["r1", "r2"] and act["rejection_history"][-1]["final"]
    # the next run of r2 starts from the stored failure: repair prompt, not a fresh draft
    assert log[3][0] == auto.REPAIR_FEATURE
    # a changed official text re-opens the act with fresh counters
    (tmp_path / EVIDENCE_DIR / f"{_key(PDF)}.json").write_text(json.dumps({"text": EVIDENCE + " Texto corregido."}))
    assert auto.build_auto_records(tmp_path, signals, call=_fake([GOOD]), today=TODAY, run_id="r4") == [URL]


def test_attempt_caps_at_most_three_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(auto, "MAX_ATTEMPTS_PER_RUN", 1)
    signals = _repo(tmp_path)
    log = []
    for run in ("r1", "r2", "r3", "r4"):
        auto.build_auto_records(tmp_path, signals, call=_fake([BAD] * 10, log=log), today=TODAY, run_id=run)
    act = _store(tmp_path)["acts"][URL]
    assert len(log) == 3 and act["runs"] == ["r1", "r2", "r3"] and act["status"] == "final_rejected"


def test_legacy_rejections_are_requeued_and_kept_in_history(tmp_path):
    signals = _repo(tmp_path)
    (tmp_path / "data/analysis_cache").mkdir(parents=True, exist_ok=True)
    import hashlib
    old = {"problems": ["quote_not_literal"], "at": "2026-10-27T14:11:55+00:00",
           "evidence_sha256": hashlib.sha256(EVIDENCE.encode()).hexdigest()}
    (tmp_path / auto.AUTO_PATH).write_text(json.dumps({"version": 1, "source_records": {}, "rejected": {URL: old}}))
    log = []
    assert auto.build_auto_records(tmp_path, signals, call=_fake([GOOD], log=log), today=TODAY, run_id="r1") == [URL]
    assert log[0][0] == auto.REPAIR_FEATURE and "quote_not_literal" in log[0][1]  # stricter retry, same text
    assert _store(tmp_path)["acts"][URL]["rejection_history"][0]["problems"] == ["quote_not_literal"]


def test_budget_guard_is_checked_between_attempts(tmp_path):
    signals = _repo(tmp_path)
    log = []
    budget = iter([1.0, 1.0])  # enough to start the act and the first draft, then exhausted
    out = auto.build_auto_records(tmp_path, signals, call=_fake([BAD] * 3, log=log), today=TODAY, run_id="r1",
                                  headroom=lambda: next(budget, 0.0))
    assert out == [] and len(log) == 1
    act = _store(tmp_path)["acts"][URL]
    assert act["attempts"] == 1 and act["status"] == "rejected"  # one counted attempt, retried next run
    # no headroom for a worst-case act run: nothing starts, nothing counted
    (tmp_path / "b").mkdir()
    signals_b = _repo(tmp_path / "b")
    log_b = []
    auto.build_auto_records(tmp_path / "b", signals_b, call=_fake([GOOD], log=log_b), today=TODAY, run_id="r1",
                            headroom=lambda: 0.0)
    assert log_b == [] and _store(tmp_path / "b")["acts"][URL]["attempts"] == 0


def test_budget_exhaustion_from_runtime_stops_without_counting(tmp_path):
    signals = _repo(tmp_path)
    def broke(prompt, **kw):
        raise RuntimeError("weekly_api_budget_exhausted")
    auto.build_auto_records(tmp_path, signals, call=broke, today=TODAY, run_id="r1")
    act = _store(tmp_path)["acts"][URL]
    assert act["attempts"] == 0 and act["runs"] == [] and URL not in _store(tmp_path)["rejected"]


def test_newest_acts_first_and_max_per_run(tmp_path):
    signals = _repo(tmp_path)
    newer_pdf = PDF.replace("537", "538")
    (tmp_path / EVIDENCE_DIR / f"{_key(newer_pdf)}.json").write_text(json.dumps({"text": EVIDENCE.replace("537", "538")}))
    newer = {**signals[0], "title": "Circular IF/N°538", "normative_document_label": "Circular IF/N°538",
             "source_url": URL.replace("537", "538"), "event_date": "2026-10-25", "source_documents": [{"url": newer_pdf}]}
    log = []
    good538 = json.loads(json.dumps(GOOD).replace("537", "538"))
    out = auto.build_auto_records(tmp_path, [signals[0], newer], call=_fake([good538], log=log), today=TODAY,
                                  run_id="r1", max_new=1)
    assert out == [newer["source_url"]]


def test_latency_fields_and_summary(tmp_path):
    signals = _repo(tmp_path)
    signals[0]["detected_at"] = "2026-10-27T10:00:00+00:00"
    ev = tmp_path / EVIDENCE_DIR / f"{_key(PDF)}.json"
    ev.write_text(json.dumps({"text": EVIDENCE, "fetched_at": "2026-10-27T10:05:00+00:00"}))
    summary = auto.run_step(tmp_path, signals, capture=lambda root, sigs: [], call=_fake([GOOD]), today=TODAY,
                            run_id="r1")
    act = _store(tmp_path)["acts"][URL]
    assert act["detected_at"] == "2026-10-27T10:00:00+00:00" and act["evidence_at"] == "2026-10-27T10:05:00+00:00"
    assert act["first_attempt_at"] and act["published_at"] and act["first_attempt_at"] <= act["published_at"]
    assert summary["records_written"] == 1 and summary["published_with_latency"] == 1
    assert summary["latency_hours_median"] == summary["latency_hours_max"] > 0
    lat = auto.latency_summary({"acts": {"a": {"detected_at": "2026-11-01T00:00:00+00:00", "published_at": "2026-11-01T02:00:00+00:00"},
                                         "b": {"detected_at": "2026-11-01T00:00:00+00:00", "published_at": "2026-11-01T06:00:00+00:00"},
                                         "c": {"detected_at": "2026-11-01T00:00:00+00:00"}}})
    assert lat["latency_hours_median"] == 4.0 and lat["latency_hours_max"] == 6.0 and lat["published_with_latency"] == 2
    assert "mediana 4.0" in auto.format_summary({**lat, "cost_estimate": auto.cost_estimate(tmp_path)})


def test_evidence_is_captured_in_the_same_run_before_records(tmp_path):
    signals = _repo(tmp_path)
    ev = tmp_path / EVIDENCE_DIR / f"{_key(PDF)}.json"
    text = ev.read_text()
    ev.unlink()
    def capture(root, sigs):
        ev.write_text(text)
        return [PDF]
    summary = auto.run_step(tmp_path, signals, capture=capture, call=_fake([GOOD]), today=TODAY, run_id="r1")
    assert summary["evidence_captured"] == 1 and summary["records_written"] == 1


def test_cost_estimate_from_ledger(tmp_path):
    (tmp_path / "data/state").mkdir(parents=True)
    (tmp_path / auto.LEDGER_PATH).write_text(json.dumps({"calls": [
        {"feature": "normative_autorecord", "estimated_cost_usd": 0.01},
        {"feature": "normative_autorecord", "estimated_cost_usd": 0.008},
        {"feature": "normative_autorecord_review", "estimated_cost_usd": 0.005}]}))
    est = auto.cost_estimate(tmp_path)
    assert est["draft_usd"] == 0.009 and est["review_usd"] == 0.005 and est["act_pass_first_usd"] == 0.014
    assert est["act_worst_run_usd"] > est["act_pass_first_usd"] and est["act_worst_total_usd"] > est["act_worst_run_usd"]


def test_hourly_workflow_runs_step_non_blocking_with_daily_env():
    wf = yaml.safe_load(open(".github/workflows/queue-hourly.yml", encoding="utf-8"))
    daily = yaml.safe_load(open(".github/workflows/daily-radar.yml", encoding="utf-8"))
    job = wf["jobs"]["batch"]
    steps = job["steps"]
    step = next(s for s in steps if s.get("id") == "autorecord")
    assert "scripts/run_normative_autorecord.py" in step["run"] and step["continue-on-error"] is True
    assert step["if"] == "${{ !cancelled() }}" and "pending" not in step["if"]  # runs even with an empty queue
    names = [s.get("id") or s.get("name") for s in steps]
    assert names.index("autorecord") < names.index("Export public snapshot") < names.index("commit")
    for key in ("OPENAI_API_KEY", "RADAR_DEEP_MODEL", "RADAR_CAPTURE_EVIDENCE", "RADAR_MONTHLY_USD"):
        assert job["env"][key] == daily["jobs"]["build"]["env"][key]
    # one path per job: engine_cli does not run the step again (no 2 x MAX_PER_RUN acts per hour)
    assert job["env"]["RADAR_NORMATIVE_AUTORECORD_IN_ENGINE"] == "0"
    assert "RADAR_NORMATIVE_AUTORECORD_IN_ENGINE" not in daily["jobs"]["build"]["env"]
    engine = Path("src/radar_salud/engine_cli.py").read_text(encoding="utf-8")
    assert 'os.getenv("RADAR_NORMATIVE_AUTORECORD_IN_ENGINE","1")=="0"' in engine
    commit = next(s for s in steps if s.get("id") == "commit")
    assert "steps.autorecord.outcome" in commit["if"]  # counters and billed calls persist


def test_step_script_never_fails_the_run(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("run_normative_autorecord", "scripts/run_normative_autorecord.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import radar_salud.normative_autorecord as rt
    def boom(*a, **k):
        raise RuntimeError("anything")
    monkeypatch.setattr(rt, "run_step", boom)
    assert mod.main() == 0
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "sum"))
    monkeypatch.setattr(rt, "run_step", lambda root, sigs: {"evidence_captured": 0, "records_written": 2,
                                                            "cost_estimate": {}})
    assert mod.main() == 0 and "written=2" in out.read_text() and "Latencia" in (tmp_path / "sum").read_text()


def test_emision_suffix_is_stripped_from_the_act_identity(tmp_path):
    signals = _repo(tmp_path)
    pdf540 = "https://www.superdesalud.gob.cl/app/uploads/2026/11/circular-if-n-540-2026.pdf"
    (tmp_path / EVIDENCE_DIR / f"{_key(pdf540)}.json").write_text(json.dumps({"text": EVIDENCE.replace("537", "540")}))
    signals[0].update(title="Circular IF/N°540 - Emisión: 4/11/2026", source_documents=[{"url": pdf540}],
                      normative_document_label="Circular IF/N°540 - Emisión: 4/11/2026")
    good540 = {**GOOD, "plain_language_title": GOOD["plain_language_title"].replace("537", "540")}
    out = auto.build_auto_records(tmp_path, signals, call=_fake([good540]), today=TODAY, run_id="r1")
    assert out == [URL]
    rec = _store(tmp_path)["source_records"][URL]
    assert rec["legal_identity"] == "Circular IF/N°540" and rec["plain_language_title"].startswith("Circular IF/N°540 · ")


def test_review_skipped_for_budget_keeps_verified_draft_pending_review(tmp_path):
    signals = _repo(tmp_path)
    log = []
    budget = iter([1.0, 1.0])  # start + draft allowed; the review is not
    auto.build_auto_records(tmp_path, signals, call=_fake([GOOD], log=log), today=TODAY, run_id="r1",
                            headroom=lambda: next(budget, 0.0))
    store = _store(tmp_path)
    act = store["acts"][URL]
    assert [f for f, _ in log] == [auto.DRAFT_FEATURE]
    assert act["attempts"] == 0 and act["runs"] == [] and act["status"] == "pending_review"  # not a failure
    assert act["pending_review"]["record"] == GOOD and URL not in store["rejected"] and not store["source_records"]
    # next run: only the review, no redraft
    log2 = []
    assert auto.build_auto_records(tmp_path, signals, call=_fake([], log=log2), today=TODAY, run_id="r2") == [URL]
    assert [f for f, _ in log2] == [auto.REVIEW_FEATURE]
    act = _store(tmp_path)["acts"][URL]
    assert "pending_review" not in act and act["status"] == "published"
    # a runtime budget error on the review is also a deferral, not a failure
    (tmp_path / "b").mkdir()
    signals_b = _repo(tmp_path / "b")
    def broke_review(prompt, *, feature, preferred_model, allow_luna_fallback=True):
        if feature == auto.REVIEW_FEATURE:
            raise RuntimeError("weekly_api_budget_exhausted")
        return SimpleNamespace(output=GOOD, estimated_cost_usd=0.01)
    auto.build_auto_records(tmp_path / "b", signals_b, call=broke_review, today=TODAY, run_id="r1")
    act_b = _store(tmp_path / "b")["acts"][URL]
    assert act_b["status"] == "pending_review" and act_b["attempts"] == 0


def test_pending_review_failure_counts_and_repairs_in_same_run(tmp_path):
    signals = _repo(tmp_path)
    budget = iter([1.0, 1.0])
    auto.build_auto_records(tmp_path, signals, call=_fake([GOOD]), today=TODAY, run_id="r1",
                            headroom=lambda: next(budget, 0.0))
    log = []
    out = auto.build_auto_records(tmp_path, signals, call=_fake([GOOD], [{"verdict": "FAIL", "reason": "x"}], log=log),
                                  today=TODAY, run_id="r2")
    assert out == [URL]
    assert [f for f, _ in log] == [auto.REVIEW_FEATURE, auto.REPAIR_FEATURE, auto.REVIEW_FEATURE]
    assert _store(tmp_path)["acts"][URL]["attempts"] == 1


def test_python_311_parse():
    for path in ("src/radar_salud/normative_autorecord.py", "scripts/run_normative_autorecord.py",
                 "src/radar_salud/engine_cli.py", "tests/test_normative_autorecord_retry.py"):
        ast.parse(Path(path).read_text(encoding="utf-8"), feature_version=(3, 11))
