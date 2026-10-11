"""Pure read-only contract tests; no model/engine is mocked or executed.

Unit-shaped snapshots are not genuine processing evidence. The real existing
failed paid run is separately checked to ensure it cannot become a baseline.
"""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pulso_idempotence", ROOT / "scripts/pulso_idempotence.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
NOW = datetime(2026, 10, 11, 14, 2, tzinfo=timezone.utc)


def counters(fast=0):
    return {"fast": {"attempted": fast, "successful": fast, "failed": 0},
            "deep": {"attempted": 0, "successful": 0, "failed": 0}}


def unit_context():
    """Transparent unit snapshots, never saved as actual publisher observations."""
    urls = [f"https://www.latercera.com/pulso/noticia/unit-contract-{index}/" for index in range(113)]
    cohort = {"source": audit.SOURCE, "urls": urls, "items": [dict(url=url, queue_fingerprint=f"unit-fingerprint-{index}",
              body_sha256=audit.digest(b"unit primary text"), body_characters=len("unit primary text"), publication_date="2026-10-01")
              for index, url in enumerate(urls)]}
    selection_sha = audit.digest(cohort)
    selected = dict(source=audit.SOURCE, sha256=selection_sha, file_sha256=selection_sha,
                    reason="explicit_queue_selection", selected_urls=urls, selected_url_count=113,
                    matched_existing_url_count=113, ready_selected_urls=urls,
                    skipped_terminal_urls=[], skipped_not_due_urls=[], skipped_in_progress_urls=[])
    execution = dict(mode="real_core_processing", engine_called=True, engine_completed=True,
                     ai_guardrails_modified=False, started_at="2026-10-11T14:00:00Z", finished_at="2026-10-11T14:01:00Z",
                     budget_before={"run": counters(), "month": counters()},
                     budget_after={"run": counters(1), "month": counters(1)},
                     processing_selection=selected, processing_attempts_increased=113)
    execution.update(code_sha="1" * 40, runtime_fingerprint={"files": {"engine.py": "unit-engine-sha", "source.py": "unit-source-sha"},
                                                          "sha256": "unit-runtime", "git_or_marker_sha_used": False})
    queue = {}
    for index, url in enumerate(urls):
        queue[f"unit-fingerprint-{index}"] = dict(source=audit.SOURCE, status="published", attempts=1,
            lane="BACKFILL", raw=dict(url=url, event_date="2026-10-01", metadata=dict(page_text="unit primary text",
                article_body_sha256=audit.digest(b"unit primary text"), editorial_assessment={"decision": "published", "reason": "gate_passed", "relevance_score": 80})))
    held = queue["unit-fingerprint-112"]
    held.update(status="retry", retry_at="2026-10-11T18:00:00Z", reason="incremental_publication_not_proven")
    held["raw"]["metadata"]["editorial_assessment"] = {"decision": "pending", "reason": held["reason"]}
    signals = [dict(source_url=url, event_date="2026-10-01", publication_date="2026-10-01", evidence_maturity="media_reported",
                    what_happened="unit semantic copy", editorial_relevance=80, editorial_review={"review_sha256": "unit-review-provenance"})
               for url in urls[:-1]]
    report = dict(source=audit.SOURCE, runtime="daily_core", core_source_present=True,
                  last_core_execution=execution, discovery_persisted_by_current_execution=True,
                  matrix=[dict(url=url, current_core_detected=True, current_core_verified_health=True,
                               publication_date="2026-10-01", publication_date_verified=True,
                               current_discovery_trace=[{"article_body_sha256": audit.digest(b"unit primary text")}]) for url in urls])
    delta = audit.budget_delta(execution)
    return dict(selection=cohort, report=report,
        processing_qa=dict(phase="real_core_processing", requested_phase="processing", verdict="PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW",
                           acceptance="PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW", discovery_qa="PASS", processing_qa="PASS",
                           findings=[], checks={"actual_ai_budget_delta": delta, "actual_fast_response_events": 1,
                                                "processing_selection": {"sha256": selection_sha, "selected_urls": 113}}),
        discovery=dict(at="2026-10-11T14:00:30Z", runtime="daily_core", selected_sources=[audit.SOURCE],
                       sources={audit.SOURCE: {"technical_status": "ok", "discovered": 113}},
                       processing_selection=selected, processing_attempts=113), queue=queue,
        history={"signals": signals}, feed={"generated_at": "2026-10-11T14:01:01Z", "signals": deepcopy(signals)},
        ledgers={"2026-10.json": counters(1)},
        events=[{"at": "2026-10-11T14:00:45Z", "kind": "fast", "success": True, "response_id": "unit-contract-not-real-response"}],
        observed_files={audit.DEFAULT_SELECTION: selection_sha, audit.DEFAULT_REPORT: "unit-report-sha", audit.DEFAULT_QA: "unit-qa-sha"},
        runtime_fingerprint={"files": {"engine.py": "unit-engine-sha", "source.py": "unit-source-sha"}, "sha256": "unit-runtime", "git_or_marker_sha_used": False},
        recorded_core_runtime_fingerprint={"files": {"engine.py": "unit-engine-sha", "source.py": "unit-source-sha"}, "sha256": "unit-runtime", "git_or_marker_sha_used": False})


def unit_second_core(context):
    after = deepcopy(context)
    execution = after["report"]["last_core_execution"]
    execution.update(started_at="2026-10-11T14:03:00Z", finished_at="2026-10-11T14:04:00Z", processing_attempts_increased=0,
                     budget_before={"run": counters(), "month": counters(1)}, budget_after={"run": counters(), "month": counters(1)})
    selection = execution["processing_selection"]
    urls = after["selection"]["urls"]
    selection.update(ready_selected_urls=[], skipped_terminal_urls=urls[:-1], skipped_not_due_urls=urls[-1:])
    after["discovery"].update(at="2026-10-11T14:03:30Z", processing_attempts=0, processing_selection=selection)
    after["feed"]["generated_at"] = "2026-10-11T14:04:01Z"
    return after


def test_real_prior_failed_paid_processing_cannot_become_baseline(tmp_path):
    context = audit.read_context(ROOT)
    # This repository has genuine responses, but its latest prior processing
    # failed acceptance; no status-only promotion or second mocked run is used.
    if context["processing_qa"].get("processing_qa") == "PASS":
        pytest.skip("A later genuine passing processing checkpoint supersedes the prior failed run")
    assert any(row.get("success") is True and row.get("response_id") for row in context["events"])
    with pytest.raises(ValueError, match="paid_processing_qa_pass_required"):
        audit.capture_baseline(context, now=NOW)
    assert not list(tmp_path.iterdir())


def test_contract_capture_keeps_pending_final_acceptance_and_paid_observation_proofs():
    context = unit_context()
    baseline = audit.capture_baseline(context, now=NOW)
    assert baseline["processing_qa"]["acceptance"] == "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW"
    assert baseline["paid_budget_delta"]["fast"]["successful"] == 1
    assert baseline["paid_successful_response_ids"] == [context["events"][0]["response_id"]]
    assert len(baseline["selection"]["current_partition"]["terminal_urls"]) == 112
    assert len(baseline["selection"]["current_partition"]["held_not_due_urls"]) == 1
    audit.validate_baseline(baseline)


@pytest.mark.parametrize("change,reason", [
    (lambda c: c["events"][0].update(response_id=None), "response_id_missing"),
    (lambda c: c["events"].clear(), "response_events_ledger_mismatch"),
    (lambda c: c["ledgers"]["2026-10.json"]["fast"].update(successful=2), "persisted_month_ledger_mismatch"),
    (lambda c: c["processing_qa"]["checks"].update(actual_fast_response_events=0), "not_bound_to_actual_paid"),
    (lambda c: c["discovery"]["sources"][audit.SOURCE].update(technical_status="error"), "discovery_not_complete"),
    (lambda c: c["recorded_core_runtime_fingerprint"]["files"].update(engine="changed-since-paid-run"), "actual_core_runtime_fingerprint_unverified"),
    (lambda c: c["queue"]["unit-fingerprint-112"]["raw"]["metadata"]["editorial_assessment"].update(reason="analysis_unavailable"), "non_editorial_or_unresolved_hold"),
    (lambda c: c["queue"]["unit-fingerprint-112"]["raw"]["metadata"]["editorial_assessment"].update(reason="pulso_editorial_proof_missing_current_body"), "non_editorial_or_unresolved_hold"),
    (lambda c: c["queue"]["unit-fingerprint-0"]["raw"]["metadata"].update(page_text="changed primary body"), "selected_primary_body_or_date_changed"),
])
def test_capture_fails_closed_on_missing_actual_proof(change, reason):
    context = unit_context()
    change(context)
    with pytest.raises(ValueError, match=reason):
        audit.capture_baseline(context, now=NOW)


def test_preflight_checks_code_policy_cohort_and_hold_due_before_engine():
    context = unit_context()
    baseline = audit.capture_baseline(context, now=NOW)
    assert audit.preflight(baseline, context, now=NOW)["verdict"] == "PASS"
    changed = deepcopy(context)
    changed["runtime_fingerprint"]["files"]["engine.py"] = "changed-code"
    with pytest.raises(ValueError, match="implementation_or_policy_changed"):
        audit.preflight(baseline, changed, now=NOW)
    changed = deepcopy(context)
    changed["observed_files"][audit.DEFAULT_SELECTION] = "changed-cohort"
    with pytest.raises(ValueError, match="113_selection_changed"):
        audit.preflight(baseline, changed, now=NOW)
    with pytest.raises(ValueError, match="hold_is_due"):
        audit.preflight(baseline, context, now=NOW.replace(hour=19))


def test_contract_second_core_ignores_feed_wrapper_time_but_retains_full_signal_semantics():
    context = unit_context()
    baseline = audit.capture_baseline(context, now=NOW)
    after = unit_second_core(context)
    result = audit.compare(baseline, after, now=NOW.replace(minute=5))
    assert result["verdict"] == "PASS" and result["findings"] == []
    assert result["actual_budget_delta"]["fast"] == {"attempted": 0, "successful": 0, "failed": 0}
    assert result["history_signal_count"] == result["feed_signal_count"] == 112
    for field, value in (("what_happened", "changed copy"), ("publication_date", "2026-10-02"), ("editorial_relevance", 71),
                         ("editorial_review", {"review_sha256": "changed"})):
        changed = deepcopy(after)
        changed["history"]["signals"][0][field] = value
        assert "changed_history" in {row["code"] for row in audit.compare(baseline, changed, now=NOW.replace(minute=5))["findings"]}


def test_model_requests_attempt_resets_missing_skips_and_duplicate_signals_fail():
    context = unit_context()
    baseline = audit.capture_baseline(context, now=NOW)
    after = unit_second_core(context)
    after["queue"]["unit-fingerprint-0"]["attempts"] = 0
    assert "changed_existing_source_queue" in {row["code"] for row in audit.compare(baseline, after, now=NOW.replace(minute=5))["findings"]}
    after = unit_second_core(context)
    after["events"].append(dict(after["events"][0], at="2026-10-11T14:03:45Z", response_id="new-unit-event"))
    codes = {row["code"] for row in audit.compare(baseline, after, now=NOW.replace(minute=5))["findings"]}
    assert {"genuine_second_core_proof_invalid", "changed_response_event_sha256s"} <= codes
    after = unit_second_core(context)
    after["discovery"]["processing_selection"]["skipped_terminal_urls"] = []
    assert "actual_terminal_skip_or_held_not_due_not_proven" in {row["code"] for row in audit.compare(baseline, after, now=NOW.replace(minute=5))["findings"]}
    after = unit_second_core(context)
    after["history"]["signals"].append(after["history"]["signals"][0])
    with pytest.raises(ValueError, match="duplicate_effective_signal_identity"):
        audit.compare(baseline, after, now=NOW.replace(minute=5))


def test_unselected_truthful_discovery_is_disclosed_without_analysis_or_publication():
    context = unit_context()
    baseline = audit.capture_baseline(context, now=NOW)
    after = unit_second_core(context)
    url = "https://www.latercera.com/pulso/noticia/new-unit-unselected/"
    after["queue"]["new-unit-fingerprint"] = dict(source=audit.SOURCE, status="pending", attempts=0,
                                                  raw={"url": url, "event_date": "2026-10-11", "metadata": {}})
    after["report"]["matrix"].append(dict(url=url, current_core_detected=True, current_core_verified_health=True,
                                        publication_date="2026-10-11", publication_date_verified=True, current_discovery_trace=[]))
    result = audit.compare(baseline, after, now=NOW.replace(minute=5))
    assert result["verdict"] == "PASS"
    assert result["new_unselected_discovery"]["source_queue"] == [url]
    after["queue"]["new-unit-fingerprint"]["attempts"] = 1
    assert "new_unselected_discovery_was_processed" in {row["code"] for row in audit.compare(baseline, after, now=NOW.replace(minute=5))["findings"]}


def test_bundle_tamper_and_runtime_state_output_are_rejected(tmp_path):
    baseline = audit.capture_baseline(unit_context(), now=NOW)
    baseline["semantic"]["history"].clear()
    with pytest.raises(ValueError, match="payload_sha256_mismatch"):
        audit.validate_baseline(baseline)
    with pytest.raises(ValueError, match="refusing_to_overwrite_runtime_state"):
        audit.write_result(tmp_path, Path("data/state/pending_queue.json"), {})


def test_runtime_fingerprint_covers_new_implementation_and_policy_without_marker_sha():
    result = audit.runtime_fingerprint(ROOT)
    for path in ("src/radar_salud/beta_sources.py", "src/radar_salud/llm_analysis.py", "src/radar_salud/pending_queue.py",
                 "src/radar_salud/queue_selection.py", "src/radar_salud/pulso_incremental_review.py",
                 "src/radar_salud/pulso_editorial_review.py", "src/radar_salud/ai_budget.py",
                 "config/media_early_signal_gate.json", ".github/workflows/daily-radar.yml",
                 "scripts/qa_pulso_recovery.py"):
        assert path in result["files"]
    assert result["sha256"] == audit.digest(result["files"])
    assert result["git_or_marker_sha_used"] is False
    assert not any("orchestrator_queue" in path or "run-pulso" in path for path in result["files"])
