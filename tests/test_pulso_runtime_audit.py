"""Evidence-join tests use synthetic state; they do not certify a live source."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("audit_pulso_runtime", Path(__file__).parents[1] / "scripts/audit_pulso_runtime.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

SOURCE = "pulso_latercera"
BASE = "https://www.latercera.com/nacional/noticia/"


def control(articles, counts=None):
    return {"articles": articles, "window_30": {"start": "2026-09-11", "end": "2026-10-10"},
            "window_90": {"start": "2026-07-13", "end": "2026-10-10"}, "counts": counts or {}}


def original(slug, day="2026-10-10", expected=True):
    return {"url": BASE + slug + "/", "publication_date": day, "recall_expected": expected,
            "verification_method": "publisher_original_rendered_byline", "topic": "providers"}


def discovery(rows, coverage=None):
    return {"at": "2026-10-11T10:00:00Z", "runtime": "daily_core", "selected_sources": [SOURCE],
            "sources": {SOURCE: {"discovered": len(rows)}},
            "source_details": {SOURCE: rows + ([coverage] if coverage else [])}}


def trace(slug, day="2026-10-10", **values):
    return {"url": BASE + slug + "/", "publication_date": day, "status": "discovered", **values}


def item(slug, status, reason=None, assessment=None):
    return {"source": SOURCE, "status": status, "reason": reason, "attempts": 1, "lane": "BACKFILL",
            "detected_at": "2026-10-11T09:00:00Z", "raw": {"url": BASE + slug + "/", "event_date": "2026-10-10",
            "metadata": {"article_verified": True, "editorial_assessment": assessment}}}


def test_legacy_queue_presence_never_counts_as_current_discovery_recall():
    legacy = original("legacy")
    report = audit.join_report(discovery([], {"status": "archive_coverage", "coverage_complete": False,
                                           "termination": "publisher_archive_cap"}),
        {"key": item("legacy", "pending")}, [], [], control([legacy]),
        baseline=[{"url": legacy["url"], "status": "pending"}])
    row = report["matrix"][0]
    assert row["baseline_queue_present"] and row["legacy_queue_only"]
    assert row["queue_present"] and not row["current_core_detected"]
    assert row["passed_gate"] is None
    assert report["windows"]["90"]["recall"] == 0
    assert row["omission"]["reason"] == "archive_coverage_incomplete:publisher_archive_cap"
    assert row["omission"]["url_level_cause_verified"] is False


def test_published_history_and_actual_feed_have_attribution_and_gate_trace():
    url = BASE + "published/"
    history = [{"source_url": url, "evidence_maturity": "media_reported",
                "what_happened": "Según Pulso / La Tercera, la clínica amplió su capacidad.",
                "confirmation_policy": "upgrade_same_signal_when_company_or_official_source_confirms"}]
    report = audit.join_report(discovery([trace("published")]),
        {"published": item("published", "published", assessment={"decision": "published", "relevance_score": 83, "threshold": 72})},
        history, history, control([original("published")]))
    row = report["matrix"][0]
    assert row["passed_gate"] is True
    assert row["editorial_outcome"] == "published_in_history_and_feed"
    assert row["history_present"] and row["feed_present"]
    assert row["source_attribution"]["evidence_maturity"] == "media_reported"
    assert row["source_attribution"]["attribution_present"]
    assert not report["source_attribution_findings"]
    assert row["queue"][0]["assessment"]["threshold"] == 72


def test_rejected_and_deferred_keep_exact_reasons_without_false_gate_pass():
    report = audit.join_report(discovery([trace("below"), trace("hold")]), {
        "below": item("below", "rejected", "editorial_relevance_below_threshold",
                      {"decision": "rejected", "relevance_score": 71, "threshold": 72}),
        "hold": item("hold", "retry", "incremental_value_review_required",
                     {"decision": "pending", "reason": "incremental_value_review_required"})},
        [], [], control([original("below"), original("hold")]))
    rows = {row["url"]: row for row in report["matrix"]}
    assert rows[BASE + "below/"]["passed_gate"] is False
    assert rows[BASE + "below/"]["exact_reason"] == "editorial_relevance_below_threshold"
    assert rows[BASE + "hold/"]["passed_gate"] is None
    assert rows[BASE + "hold/"]["editorial_outcome"] == "deferred"
    assert rows[BASE + "hold/"]["exact_reason"] == "incremental_value_review_required"
    assert report["windows"]["30"]["recall"] == 1


def test_complete_calendar_control_windows_exclude_current_day_and_negative_cohort():
    articles = [original("start30", "2026-09-11"), original("end", "2026-10-10"),
                original("start90", "2026-07-13"), original("old", "2026-07-12"),
                original("current", "2026-10-11"), original("negative", "2026-08-01", False)]
    report = audit.join_report(discovery([trace("start30", "2026-09-11"), trace("end"), trace("current", "2026-10-11")]),
        {}, [], [], control(articles, {"primary_recall_expected_30": 2, "primary_recall_expected_90": 3}))
    assert report["windows"]["30"]["control_expected"] == 2
    assert report["windows"]["90"]["control_expected"] == 3
    assert report["windows"]["30"]["recall"] == 1
    assert report["windows"]["90"]["recall"] == 2 / 3
    assert report["windows"]["90"]["control_denominator_consistent"]
    assert [row["url"] for row in report["windows"]["90"]["missed"]] == [BASE + "start90/"]


def test_discovery_exclusion_and_date_conflict_remain_explicit():
    report = audit.join_report(discovery([
        trace("excluded", status="excluded", reason="no_health_anchor"),
        trace("conflict", "2026-10-09")]), {}, [], [], control([original("excluded"), original("conflict")]))
    rows = {row["url"]: row for row in report["matrix"]}
    assert rows[BASE + "excluded/"]["omission"] == {"status": "excluded", "reason": "no_health_anchor",
                                                        "error_type": None, "url_level_cause_verified": True}
    assert rows[BASE + "conflict/"]["external_control"]["date_comparison"] == "conflict"
    assert report["windows"]["30"]["date_conflicts"] == [BASE + "conflict/"]


def test_control_normalization_keeps_opinion_without_foreign_host_acceptance():
    assert audit.normalized_url("https://latercera.com/opinion/noticia/test?x=1#top") == "https://www.latercera.com/opinion/noticia/test/"
    assert audit.normalized_url("https://www.latercera.com.evil.test/pulso/noticia/test/") is None


def test_interrupted_execution_cannot_reuse_previous_discovery_recall():
    old = discovery([trace("prior")])
    filtered, current = audit.current_execution_discovery(old, "2026-10-11T11:00:00+00:00")
    assert current is False
    report = audit.join_report(filtered, {}, [], [], control([original("prior")]))
    assert report["windows"]["30"]["recall"] == 0
    assert not report["core_source_present"]
    assert report["audit_discovery_error"] == "discovery_not_persisted_by_current_execution"
    assert old["source_details"][SOURCE][0]["url"] == BASE + "prior/"
    filtered, current = audit.current_execution_discovery(old, "2026-10-11T09:00:00+00:00")
    assert current and filtered is old
