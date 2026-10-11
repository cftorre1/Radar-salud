"""Evidence-join tests use synthetic state; they do not certify a live source."""
import importlib.util
import gzip
import hashlib
import io
import json
from email.message import Message
from pathlib import Path

import pytest

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


def test_legacy_unverified_processor_retains_original_and_restores_both_bindings(tmp_path):
    from radar_salud import beta_sources, pulso_source
    from radar_salud.models import RawItem
    from radar_salud.processing import DeferredProcessing
    url = BASE + "legacy-held/"
    title = "Clínica suspende operaciones y dispone el traslado de pacientes"
    body = "La clínica informó el cierre temporal y el traslado de pacientes a otros hospitales de su red. " * 3
    node = {"@type": "NewsArticle", "url": url, "headline": title, "datePublished": "2026-10-10T15:00:00Z"}
    payload = (f'<link rel="canonical" href="{url}"><script type="application/ld+json">'
               f'{json.dumps(node)}</script><article><h1>{title}</h1><p>{body}</p></article>').encode()

    class Response(io.BytesIO):
        status = 200
        headers = Message()
        headers["Content-Type"] = "text/html; charset=utf-8"
        def geturl(self):
            return url

    observer = audit.CaptureObserver(tmp_path, opener=lambda request, timeout: Response(payload))
    originals = pulso_source.fetch_html, beta_sources.fetch_html
    raw = RawItem(SOURCE, "Título antiguo de la cola", url, "Pulso / La Tercera", "press_high_trust",
                  metadata={"editorial_hold": "incremental_value_review_required"})
    with audit.observe_pulso_fetches(observer):
        assert pulso_source.fetch_html is observer and beta_sources.fetch_html is observer
        with pytest.raises(DeferredProcessing):
            beta_sources.process_curated_beta_source(raw, {})
    observer.flush()
    assert (pulso_source.fetch_html, beta_sources.fetch_html) == originals
    assert raw.metadata["article_verified"]
    assert raw.metadata["editorial_assessment"]["reason"] == "incremental_value_review_required"
    record = observer.manifest["requests"][0]
    assert record["sha256"] == hashlib.sha256(payload).hexdigest()
    assert gzip.decompress((tmp_path / record["gzip_file"]).read_bytes()) == payload


def test_recent_history_feed_exclusion_is_flagged_unresolved():
    row = {"source_url": BASE + "dropped/", "event_date": "2026-10-10", "evidence_maturity": "media_reported",
           "what_happened": "Según La Tercera, el prestador reportó una ampliación."}
    report = audit.join_report(discovery([trace("dropped")]), {}, [row], [], control([]))
    assert report["matrix"][0]["traceability_unresolved"]
    assert report["unresolved_recent_feed_exclusions"] == [row["source_url"]]
    assert "specific exclusion is not emitted" in report["matrix"][0]["exact_reason"]


@pytest.mark.parametrize("execution,reason", [
    ({"engine_called": True, "engine_completed": True, "mode": "discovery_only"}, "explicit_discovery_only"),
    ({"engine_called": True, "engine_completed": True, "mode": "real_core_processing", "processing_limit": 250,
      "processing_attempts_increased": 250, "model_capacity_after": {"fast": False, "deep": False}}, "global_processing_limit_reached"),
    ({"engine_called": True, "engine_completed": True, "mode": "real_core_processing", "processing_limit": 250,
      "processing_attempts_increased": 45, "model_capacity_after": {"fast": False, "deep": False}}, "both_model_budget_capacities_exhausted"),
])
def test_pending_reason_uses_observed_execution_and_preserves_unknown_editorial_gate(execution, reason):
    report = audit.join_report(discovery([trace("pending")]), {"pending": item("pending", "pending")}, [], [], control([]))
    audit.annotate_pending(report, execution)
    assert report["matrix"][0]["exact_reason"] == "processing_not_attempted:" + reason
    assert report["matrix"][0]["passed_gate"] is None
    assert not report["unresolved_pending_operational_reasons"]


def test_pending_without_observed_stop_cause_remains_unresolved():
    report = audit.join_report(discovery([trace("pending")]), {"pending": item("pending", "pending")}, [], [], control([]))
    audit.annotate_pending(report, {"mode": "report_only_rejoin", "engine_called": False})
    assert report["matrix"][0]["operational_reason_unresolved"]
    assert report["unresolved_pending_operational_reasons"] == [BASE + "pending/"]
