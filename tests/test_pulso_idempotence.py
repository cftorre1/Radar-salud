"""Pure read-only contract tests; no model/engine is mocked or executed.

Unit-shaped snapshots are not genuine processing evidence. The real existing
failed paid run is separately checked to ensure it cannot become a baseline.
"""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
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
    context = dict(selection=cohort, report=report,
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
    # An explicit reviewed hold, not a generic retry label. All primary/target
    # snapshots below remain transparent unit values, not publisher evidence.
    document = json.loads((ROOT / audit.INCREMENTAL_REVIEW).read_bytes())
    entry = next(row for row in document["reviews"] if row["decision"] == "keep_hold")
    url, day = entry["source_url"], entry["publication_date"]
    body = "Unit primary budget example; this is no original publisher text. " * 5
    body_sha = audit.digest(body.encode())
    cohort["urls"][-1] = url
    cohort["items"][-1].update(url=url, body_sha256=body_sha, body_characters=len(body), publication_date=day)
    held["reason"] = entry["reason"]
    held["raw"].update(url=url, event_date=day)
    held["raw"]["metadata"].update(
        page_text=body, article_body_sha256=body_sha, article_verified=True,
        primary_identity_verified=True, publication_date_verified=True,
        publication_date=day, canonical_url=url, source_quality_gate="passed",
        html_sha256="0" * 64, captured_at="2026-10-11T14:00:30Z", editorial_hold=entry["reason"],
        editorial_assessment={"decision": "pending", "reason": entry["reason"]},
        incremental_review=dict(review_ref=audit.INCREMENTAL_REVIEW, review_sha256=audit.INCREMENTAL_REVIEW_SHA256,
            decision="keep_hold", publication_approved=False, verified_publication_date=day,
            verified_body_sha256=body_sha, verified_html_sha256="0" * 64, verified_captured_at="2026-10-11T14:00:30Z"))
    target = entry["compared_signal"]
    copy = dict(what_happened="Unit canonical budget statement, not actual publication evidence.",
                why_it_matters="Unit canonical target consequence, not an actual editorial judgment.")
    queue["unit-canonical-target"] = dict(source="minsal", status="published", attempts=1,
        lane="BACKFILL", raw=dict(url=target["source_url"], event_date=target["publication_date"],
            metadata=dict(page_text=body, article_body_sha256=body_sha, article_verified=True,
                primary_identity_verified=True, article_body_complete=True,
                html_sha256="1" * 64, captured_at="2026-10-11T14:00:30Z",
                canonical_url=target["source_url"], publication_date=target["publication_date"],
                publication_date_verified=True, source_quality_gate="passed", **copy)))
    target_signal = dict(source_url=target["source_url"], event_date=target["publication_date"],
                         source_type="official", editorial_relevance=92, **copy)
    context["history"]["signals"].append(target_signal)
    context["feed"]["signals"].append(deepcopy(target_signal))
    context["report"]["matrix"][-1].update(url=url, publication_date=day,
                                            current_discovery_trace=[{"article_body_sha256": body_sha}])
    selection_sha = audit.digest(cohort)
    selected.update(sha256=selection_sha, file_sha256=selection_sha)
    context["observed_files"][audit.DEFAULT_SELECTION] = selection_sha
    context["processing_qa"]["checks"]["processing_selection"]["sha256"] = selection_sha
    context["referenced_proof_files"] = {audit.INCREMENTAL_REVIEW: audit.INCREMENTAL_REVIEW_SHA256}
    context["incremental_review_files"] = {audit.INCREMENTAL_REVIEW: document}
    return context


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


def test_real_cohort_historical_observation_references_are_not_live_immutable_proofs():
    context = audit.read_context(ROOT)
    inputs = context["selection"]["inputs"]
    assert context["cohort_declared_reference_provenance"] == inputs
    assert audit.DEFAULT_REPORT not in context["referenced_proof_files"]
    assert "data/state/pending_queue.json" not in context["referenced_proof_files"]
    for key in audit.IMMUTABLE_COHORT_INPUTS:
        reference = inputs[key]
        assert context["referenced_proof_files"][reference["path"]] == reference["sha256"]


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
    assert result["history_signal_count"] == result["feed_signal_count"] == 113
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


def test_native_offices_share_listing_but_keep_distinct_office_identities():
    offices = json.loads((ROOT / "tests/fixtures/pulso_native_offices_shared_listing.json").read_bytes())["signals"]
    indexed = audit.signal_index(offices)
    assert len(indexed) == 3
    assert set(indexed.values()) == {audit.digest(office) for office in offices}
    with pytest.raises(ValueError, match="duplicate_effective_signal_identity"):
        audit.signal_index(offices + [deepcopy(offices[0])])


def test_press_cannot_bypass_url_date_dedupe_with_native_record_ids():
    first = dict(source_url="https://www.latercera.com/pulso/noticia/same-article/",
                 event_date="2026-10-02", source_type="official", source_record_id="fake-office-1")
    second = dict(first, source_record_id="fake-office-2")
    with pytest.raises(ValueError, match="duplicate_effective_signal_identity"):
        audit.signal_index([first, second])


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


@pytest.mark.parametrize("reason", [
    "pulso_editorial_model_binding_mismatch", "pulso_editorial_future_status_mismatch",
    "pulso_editorial_human_scope_conflicts_with_non_human_quote", "pulso_editorial_incremental_value_uncertain",
    "pulso_primary_item_identity_or_date_mismatch", "processing_not_attempted:required_fast_budget_exhausted",
    "publisher_liveblog_entry_dates_unverified",
])
def test_generic_retry_alias_does_not_conceal_unresolved_processing_reason(reason):
    context = unit_context()
    held = context["queue"]["unit-fingerprint-112"]
    held["reason"] = reason
    held["raw"]["metadata"]["editorial_assessment"]["reason"] = "retry_not_due"
    with pytest.raises(ValueError, match="non_editorial_or_unresolved_hold"):
        audit.capture_baseline(context, now=NOW)


@pytest.mark.parametrize("status", ["retry", "published", "rejected"])
@pytest.mark.parametrize("field,value", [
    ("pulso_editorial_proof_validation", {"decision": "deferred", "reason": "unit-binding-failure"}),
    ("primary_item_binding", {"verified": False}),
    ("analysis_input_complete", False), ("article_body_complete", False),
])
def test_failed_processing_metadata_cannot_be_hidden_by_terminal_status_or_alias(status, field, value):
    context = unit_context()
    row = context["queue"]["unit-fingerprint-0"]
    row.update(status=status, reason="retry_not_due", retry_at="2026-10-11T18:00:00Z")
    row["raw"]["metadata"][field] = value
    before = deepcopy(row)
    with pytest.raises(ValueError, match="non_editorial_or_unresolved_hold"):
        audit.capture_baseline(context, now=NOW)
    assert row == before  # Detection never resets or rewrites terminal records.


@pytest.mark.parametrize("change", [
    lambda c: c["queue"]["unit-fingerprint-112"]["raw"]["metadata"].pop("incremental_review"),
    lambda c: c["queue"]["unit-fingerprint-112"]["raw"]["metadata"]["incremental_review"].update(verified_body_sha256="f" * 64),
    lambda c: c["queue"]["unit-fingerprint-112"]["raw"]["metadata"]["incremental_review"].update(verified_publication_date="2026-10-06"),
    lambda c: c["queue"]["unit-fingerprint-112"]["raw"]["metadata"]["incremental_review"].update(decision="release_hold_for_editorial_analysis"),
    lambda c: c["queue"]["unit-canonical-target"].update(status="retry"),
    lambda c: c["queue"]["unit-canonical-target"]["raw"].update(event_date=None),
    lambda c: c["queue"]["unit-canonical-target"]["raw"]["metadata"].update(article_body_sha256="f" * 64),
    lambda c: c["queue"]["unit-canonical-target"]["raw"]["metadata"].update(canonical_url="https://example.org/wrong-target"),
    lambda c: c["queue"]["unit-canonical-target"]["raw"]["metadata"].pop("html_sha256"),
    lambda c: c["history"]["signals"][-1].update(editorial_relevance=71),
    lambda c: c["history"]["signals"][-1].update(what_happened="A changed unbound canonical statement"),
    lambda c: c["history"]["signals"].append(deepcopy(c["history"]["signals"][-1])),
    lambda c: c["referenced_proof_files"].update({audit.INCREMENTAL_REVIEW: "f" * 64}),
])
def test_reviewed_hold_requires_exact_primary_and_actual_published_canonical_proof(change):
    context = unit_context()
    url = context["selection"]["urls"][-1]
    assert url in audit.reviewed_hold_bindings(context)
    change(context)
    assert url not in audit.reviewed_hold_bindings(context)
    with pytest.raises(ValueError, match="non_editorial_or_unresolved_hold|duplicate_effective_signal_identity"):
        audit.capture_baseline(context, now=NOW)


def test_real_incremental_review_reference_is_preserved_without_claiming_current_target_proof():
    context = audit.read_context(ROOT)
    metadata = [item.get("raw", {}).get("metadata", {}) for item in context["queue"].values()
                if item.get("source") == audit.SOURCE]
    reviews = [value["incremental_review"] for value in metadata if value.get("incremental_review")]
    assert reviews
    assert context["referenced_proof_files"][audit.INCREMENTAL_REVIEW] == audit.INCREMENTAL_REVIEW_SHA256
    assert context["incremental_review_files"][audit.INCREMENTAL_REVIEW]["editorial_policy"]["publication_approved"] is False
    for url, binding in audit.reviewed_hold_bindings(context).items():
        target = context["queue"][binding["target_queue_fingerprint"]]
        assert target["status"] == "published"
        assert target["raw"]["event_date"] == binding["target_publication_date"]


def addendum_reference_queue():
    # Temporary admission metadata cites the two genuine immutable audits;
    # it is not a model output or a claim that paid processing has occurred.
    return {"unit-reference-only": {"source": audit.SOURCE, "raw": {"metadata": {
        "incremental_review": {"review_ref": audit.INCREMENTAL_REVIEW,
                               "review_sha256": audit.INCREMENTAL_REVIEW_SHA256},
        "incremental_review_addendum": {"review_ref": audit.INCREMENTAL_ADDENDUM,
            "review_sha256": audit.INCREMENTAL_ADDENDUM_SHA256,
            "prior_review_ref": audit.INCREMENTAL_REVIEW,
            "prior_review_sha256": audit.INCREMENTAL_REVIEW_SHA256,
            "decision": "release_hold_for_editorial_analysis", "publication_approved": False}}}}}


def test_new_analysis_addendum_preserves_both_original_pinned_audits():
    documents = audit.incremental_proof_files(ROOT, addendum_reference_queue())
    assert set(documents) == {audit.INCREMENTAL_REVIEW, audit.INCREMENTAL_ADDENDUM}
    addendum = documents[audit.INCREMENTAL_ADDENDUM]
    assert addendum["prior_review"] == dict(ref=audit.INCREMENTAL_REVIEW,
        sha256=audit.INCREMENTAL_REVIEW_SHA256,
        decision="keep_hold", reason="duplicate_budget_announcement_no_verified_material_increment",
        preserved_unchanged=True)
    assert addendum["editorial_policy"]["analysis_release_only"] is True
    assert addendum["editorial_policy"]["publication_approved"] is False


@pytest.mark.parametrize("change", [
    lambda m: m.pop("incremental_review"),
    lambda m: m["incremental_review_addendum"].update(review_ref="../../unverified.json"),
    lambda m: m["incremental_review_addendum"].update(review_sha256="0" * 64),
    lambda m: m["incremental_review_addendum"].update(prior_review_sha256="0" * 64),
    lambda m: m["incremental_review_addendum"].update(decision="publish"),
    lambda m: m["incremental_review_addendum"].update(publication_approved=True),
])
def test_incremental_addendum_cannot_erase_prior_review_or_become_approval(change):
    queue = addendum_reference_queue()
    change(queue["unit-reference-only"]["raw"]["metadata"])
    with pytest.raises(ValueError, match="incremental_.*unverified"):
        audit.incremental_proof_files(ROOT, queue)


def test_incremental_addendum_file_bytes_must_remain_pinned(tmp_path):
    for relative in (audit.INCREMENTAL_REVIEW, audit.INCREMENTAL_ADDENDUM):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    (tmp_path / audit.INCREMENTAL_ADDENDUM).write_bytes((ROOT / audit.INCREMENTAL_ADDENDUM).read_bytes() + b"\n")
    with pytest.raises(ValueError, match="incremental_review_addendum_file_changed"):
        audit.incremental_proof_files(tmp_path, addendum_reference_queue())
