"""Observe genuine source-scoped Daily core execution and reconcile its evidence.

Discovery owns its inventory. The frozen external control is used only to join
results and select original HTTP responses for retention; it never supplies URLs
to discovery, queue or processing. This script never resets terminal decisions,
replaces analysis, changes AI guardrails or treats stored queue rows as recall.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urldefrag, urlsplit, urlunsplit
from urllib.request import Request, urlopen

SOURCE = "pulso_latercera"
REPOSITORY = Path(__file__).resolve().parents[1]


def normalized_url(value):
    """Retain every publisher control, including intentionally excluded opinion."""
    parsed = urlsplit(urldefrag(value or "")[0])
    if (parsed.scheme != "https" or parsed.netloc not in {"latercera.com", "www.latercera.com"}
            or parsed.username or parsed.password):
        return None
    return urlunsplit(("https", "www.latercera.com", parsed.path.rstrip("/") + "/", "", ""))


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def queue_snapshot(queue):
    return [{"fingerprint": key, "url": normalized_url(item.get("raw", {}).get("url")),
             "status": item.get("status"), "reason": item.get("reason"),
             "attempts": item.get("attempts", 0), "lane": item.get("lane"),
             "detected_at": item.get("detected_at"), "publication_date": item.get("raw", {}).get("event_date")}
            for key, item in queue.items() if item.get("source") == SOURCE]


class CaptureMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonical = None
        self.metadata = {}
        self.json_ld = []
        self.parts = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "link" and "canonical" in attributes.get("rel", "").split():
            self.canonical = attributes.get("href")
        if tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            if key in {"og:url", "og:title", "article:published_time", "article:modified_time", "article:section"}:
                self.metadata[key] = attributes.get("content")
        if tag == "script" and attributes.get("type") == "application/ld+json":
            self.parts = []

    def handle_data(self, data):
        if self.parts is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.parts is not None:
            try:
                self.json_ld.extend(project_json_ld(json.loads("".join(self.parts))))
            except (ValueError, TypeError):
                self.json_ld.append({"parse_error": True})
            self.parts = None


def project_json_ld(value):
    if isinstance(value, list):
        return [node for item in value for node in project_json_ld(item)]
    if not isinstance(value, dict):
        return []
    keys = ("@type", "@id", "url", "mainEntityOfPage", "headline", "datePublished",
            "dateModified", "articleSection", "keywords")
    own = {key: value[key] for key in keys if key in value}
    return ([own] if own else []) + project_json_ld(value.get("@graph", []))


class CaptureObserver:
    """HTTP observer using the normal loader's headers, charset and exceptions."""
    def __init__(self, output, control_urls=(), opener=None):
        self.output = Path(output)
        self.control_urls = set(control_urls)
        self.opener = opener or urlopen
        self.lock = threading.Lock()
        self.last_flush = time.monotonic()
        self.manifest = {"schema_version": "1.0", "source": SOURCE,
                         "mode": "actual_core_http_observation_no_inventory_injection",
                         "started_at": datetime.now(timezone.utc).isoformat(), "requests": []}

    def __call__(self, url, timeout=20):
        from radar_salud import pulso_source
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc not in {"www.latercera.com", "latercera.com"}:
            raise ValueError("runtime_observer_unexpected_source_host")
        record = {"url": url, "requested_at": datetime.now(timezone.utc).isoformat()}
        try:
            request = Request(url, headers={"User-Agent": "RadarSaludBot/0.1 (+public-source-monitor)"})
            try:
                response = self.opener(request, timeout=timeout)
            except HTTPError as error:
                response = error
            with response:
                payload = response.read()
                content_type = response.headers.get("Content-Type", "")
                charset = response.headers.get_content_charset() or "utf-8"
                record.update(status=response.status, final_url=response.geturl(),
                              content_type=content_type, charset=charset)
            text = payload.decode(charset, errors="replace")
            record.update(captured_at=datetime.now(timezone.utc).isoformat(), bytes=len(payload),
                          sha256=hashlib.sha256(payload).hexdigest(),
                          returned_text_utf8_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
            xml = "xml" in content_type or "/arc/outboundfeeds/" in parsed.path
            primary_article = pulso_source.article_url(url)
            retain = xml or not primary_article or record["status"] != 200 or normalized_url(url) in self.control_urls
            retention = "xml_or_listing_surface" if xml or not primary_article else "external_control" if retain else None
            markup = CaptureMarkup()
            markup.feed(text)
            record["observed"] = {"canonical": markup.canonical, "metadata": markup.metadata,
                                   "json_ld": markup.json_ld}
            if record["status"] == 200 and primary_article:
                try:
                    title, body, evidence = pulso_source.extract_article(text, url)
                    health = pulso_source.health_anchor(title + " " + body + " " + str(evidence.get("keywords", "")))
                    record["primary_article"] = {"title": title, "publication_date": evidence.get("publication_date"),
                        "publication_timestamp": evidence.get("publication_timestamp"),
                        "publication_date_source": evidence.get("publication_date_source"),
                        "section": evidence.get("section"), "health_relevant": health}
                    if health:
                        retain, retention = True, "verified_primary_health_article"
                except Exception as error:
                    retain, retention = True, "primary_article_verification_error"
                    record["primary_article_error"] = {"error_type": type(error).__name__, "reason": str(error)}
            if retain:
                relative = Path("responses") / (record["sha256"] + ".gz")
                path = self.output / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                compressed = gzip.compress(payload, mtime=0)
                path.write_bytes(compressed)
                record.update(gzip_file=str(relative), gzip_sha256=hashlib.sha256(compressed).hexdigest(),
                              retention_reason=retention or "http_error_response")
            else:
                record["retention_reason"] = "primary_nonhealth_hash_and_metadata_only"
            if record["status"] >= 400:
                raise HTTPError(url, record["status"], "publisher_http_error", response.headers, None)
            return text
        except BaseException as error:
            record.setdefault("status", "error")
            record.update(error_type=type(error).__name__, error=str(error)[:350])
            raise
        finally:
            record.setdefault("captured_at", datetime.now(timezone.utc).isoformat())
            with self.lock:
                self.manifest["requests"].append(record)
                # Flush incrementally without repeatedly rewriting a growing
                # 10,000-response manifest on every concurrent detail request.
                if len(self.manifest["requests"]) % 50 == 0 or time.monotonic() - self.last_flush >= 15:
                    self._flush_unlocked()

    def _flush_unlocked(self):
        self.manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(self.output / "manifest.json", self.manifest)
        self.last_flush = time.monotonic()
        print(json.dumps(dict(event="original_capture_checkpoint",
            at=self.manifest["updated_at"], observed_http_responses=len(self.manifest["requests"]),
            original_responses_retained=sum(bool(row.get("gzip_file")) for row in self.manifest["requests"]),
            http_statuses=dict(Counter(str(row.get("status")) for row in self.manifest["requests"])))), flush=True)

    def flush(self):
        with self.lock:
            self._flush_unlocked()


@contextmanager
def observe_pulso_fetches(observer):
    """Capture both discovery and legacy-detail validation in Pulso-only core."""
    from radar_salud import beta_sources, pulso_source
    original_discovery = pulso_source.fetch_html
    original_processing = beta_sources.fetch_html
    pulso_source.fetch_html = observer
    beta_sources.fetch_html = observer
    try:
        yield
    finally:
        pulso_source.fetch_html = original_discovery
        beta_sources.fetch_html = original_processing


def join_report(discovery, queue, history, feed, control, *, baseline=(), captures=None):
    """Pure evidence join. Queue presence never becomes discovery recall."""
    details = discovery.get("source_details", {}).get(SOURCE, [])
    traces = {}
    for detail in details:
        url = normalized_url(detail.get("url"))
        if url:
            traces.setdefault(url, []).append(detail)
    text_candidates = {url for url, rows in traces.items() if any(row.get("status") == "discovered" for row in rows)}
    metadata_candidates = {url for url, rows in traces.items() if any(
        row.get("status") == "discovered_metadata_only" for row in rows)} - text_candidates
    source_result = discovery.get("sources", {}).get(SOURCE, {})
    source_exception = source_result.get("error_type")
    returned_to_core = source_exception in (None, "partial_discovery")
    current = text_candidates if returned_to_core else set()
    metadata_only = metadata_candidates if returned_to_core else set()
    enumerated = current | metadata_only
    queued = {}
    for fingerprint, item in queue.items():
        if item.get("source") != SOURCE:
            continue
        raw = item.get("raw", {})
        url = normalized_url(raw.get("url"))
        if url:
            queued.setdefault(url, []).append({"fingerprint": fingerprint, "status": item.get("status"),
                "lane": item.get("lane"), "attempts": item.get("attempts", 0), "reason": item.get("reason"),
                "detected_at": item.get("detected_at"), "updated_at": item.get("updated_at"),
                "retry_at": item.get("retry_at"), "publication_date": raw.get("event_date"),
                "article_verified": raw.get("metadata", {}).get("article_verified", False),
                "title": raw.get("title"), "topics": raw.get("metadata", {}).get("topics", []),
                "publication_date_source": raw.get("metadata", {}).get("publication_date_source"),
                "assessment": raw.get("metadata", {}).get("editorial_assessment"),
                "rejection_reason": raw.get("metadata", {}).get("rejection_reason"),
                "editorial_hold": raw.get("metadata", {}).get("editorial_hold"),
                "article_body_complete": raw.get("metadata", {}).get("article_body_complete"),
                "source_content_unavailable_reason": raw.get("metadata", {}).get("source_content_unavailable_reason"),
                "publication_date_verified": raw.get("metadata", {}).get("publication_date_verified")})
    history_by_url = {url: row for row in history if (url := normalized_url(row.get("source_url")))}
    feed_urls = {url for row in feed if (url := normalized_url(row.get("source_url")))}
    controls = {url: row for row in control.get("articles", []) if (url := normalized_url(row.get("url")))}
    baseline_urls = {row.get("url") for row in baseline}
    captures_by_url = {}
    for response in (captures or {}).get("requests", []):
        url = normalized_url(response.get("url"))
        if url:
            captures_by_url.setdefault(url, []).append({key: response.get(key) for key in (
                "url", "status", "captured_at", "sha256", "returned_text_utf8_sha256", "gzip_file", "gzip_sha256", "charset",
                "retention_reason", "error_type", "error", "primary_article", "primary_article_error",
                "capture_provenance", "original_capture_manifest_sha256") if response.get(key) is not None})
    coverage = [row for row in details if row.get("status") in {
        "archive_coverage", "coverage_summary", "public_feed_coverage", "runtime_coverage"}]
    primary_coverage = next((row for row in reversed(coverage) if row.get("status") == "runtime_coverage"), None)
    if primary_coverage is None:
        primary_coverage = next((row for row in reversed(coverage) if row.get("status") == "coverage_summary"), None)
    if primary_coverage is None:
        primary_coverage = next((row for row in reversed(coverage) if row.get("status") == "archive_coverage"), None)
    source_error = discovery.get("audit_discovery_error") or discovery.get("sources", {}).get(SOURCE, {}).get("error_type")
    matrix = []
    for url in sorted(text_candidates | metadata_candidates | set(queued) | set(controls) | set(history_by_url)):
        observed = traces.get(url, [])
        primary = next((row for row in observed if row.get("status") in {
            "discovered", "discovered_metadata_only", "excluded"}), {})
        verified = next((row for row in observed if row.get("publication_date")
            and row.get("publication_date_verified") is not False
            and row.get("status") in {"discovered", "discovered_metadata_only", "excluded"}), {})
        rows = queued.get(url, [])
        original = controls.get(url, {})
        historical = history_by_url.get(url)
        assessments = [row["assessment"] for row in rows if isinstance(row.get("assessment"), dict)]
        rejected = next((row for row in rows if row["status"] == "rejected"), None)
        retry = next((row for row in rows if row["status"] in {"retry", "processing"}), None)
        published = next((row for row in rows if row["status"] == "published"), None)
        passed = True if any(a.get("decision") == "published" for a in assessments) else (
            False if rejected or any(a.get("decision") in {"reject", "rejected"} for a in assessments) else None)
        if historical:
            disposition = "published_in_history_and_feed" if url in feed_urls else "published_in_history_feed_excluded"
            reason = "history_and_feed_present" if url in feed_urls else "feed_curator_excluded; specific exclusion is not emitted by curate"
            if url in feed_urls:
                passed = True
        elif rejected:
            disposition, reason = "rejected", rejected.get("reason") or rejected.get("rejection_reason") or "rejection_reason_missing"
        elif retry:
            disposition = "deferred"
            reason = retry.get("reason") or (retry.get("assessment") or {}).get("reason") or "deferred_reason_missing"
        elif published:
            disposition, reason = "published_queue_history_missing", "queue_history_consistency_failure"
        elif rows:
            disposition = "archived" if all(row["status"] == "archived" for row in rows) else "pending"
            reason = (next((row.get("reason") for row in rows if row.get("reason")), None)
                      or next((row.get("editorial_hold") for row in rows if row.get("editorial_hold")), None)
                      or next((assessment.get("reason") for assessment in assessments if assessment.get("reason")), None)
                      or "not_processed; run_limit_budget_or_discovery_only; no_editorial_verdict")
        else:
            disposition, reason = "not_detected", "not_in_queue_or_history; no_editorial_verdict"
        omission = None
        if url not in enumerated:
            precise = next((row for row in observed if row.get("status") in {"detail_error", "excluded", "excluded_path"}), None)
            if not returned_to_core and url in text_candidates | metadata_candidates:
                omission = dict(status="core_source_exception", reason="source_exception_before_core_registration:" + str(source_exception),
                                error_type=source_exception, url_level_cause_verified=True)
            elif precise:
                omission = {"status": precise["status"], "reason": precise.get("reason") or "reason_not_emitted",
                            "error_type": precise.get("error_type"), "url_level_cause_verified": True}
            else:
                incomplete = primary_coverage if primary_coverage and not primary_coverage.get(
                    "coverage_complete", primary_coverage.get("complete", False)) else None
                omission = {"status": "not_observed_in_current_core", "reason": (
                    ("runtime_coverage_incomplete:" if incomplete.get("status") == "runtime_coverage" else "archive_coverage_incomplete:") + str(
                        incomplete.get("termination", "required_public_feed_incomplete" if incomplete.get("status") == "runtime_coverage" else "unknown")) if incomplete else
                    "source_error:" + str(source_error) if source_error else "URL_not_enumerated_by_current_core"),
                    "url_level_cause_verified": False}
        runtime_day = verified.get("publication_date")
        unresolved_primary_day = (primary.get("status") == "discovered_metadata_only"
                                  and primary.get("publication_date_verified") is False)
        comparison = "match" if runtime_day and original.get("publication_date") == runtime_day else (
            "conflict" if runtime_day and original.get("publication_date") else "runtime_original_date_unverified" if original else "no_external_date_control")
        title = primary.get("title") or original.get("title") or (historical or {}).get("title") or next((row["title"] for row in rows if row.get("title")), None)
        historical_day = (historical or {}).get("publication_date") or (historical or {}).get("event_date")
        matrix.append({"url": url, "title": title,
            "publication_date": None if unresolved_primary_day else runtime_day or original.get("publication_date") or historical_day,
            "publication_date_evidence": "unresolved_primary_publisher_date_conflict" if unresolved_primary_day else ("reused_verified_primary_byline_unchanged_publisher_lastmod" if verified.get("cache_hit") else "current_verified_detail") if runtime_day else original.get("verification_method") or (
                "recorded_history_date_requires_current_original_verification" if historical_day else "unverified"),
            "primary_detail_captured_at": primary.get("captured_at"),
            "primary_detail_cache_hit": primary.get("cache_hit", False),
            "primary_detail_sha256": primary.get("content_sha256") or primary.get("html_sha256"),
            "publisher_lastmod": primary.get("publisher_lastmod"),
            "publication_timestamp": verified.get("publication_timestamp"),
            "publication_date_source": verified.get("publication_date_source") or primary.get("publication_date_source"),
            "section": primary.get("section") or original.get("section") or urlsplit(url).path.split("/")[1],
            "topics": primary.get("topics") or ([original["topic"]] if original.get("topic") else []) or next((row["topics"] for row in rows if row.get("topics")), []),
            "current_core_detected": url in enumerated,
            "source_inventory_candidate": url in text_candidates | metadata_candidates,
            "current_core_verified_health": url in current,
            "metadata_only_candidate": url in metadata_only,
            "publication_date_verified": bool(runtime_day),
            "article_body_complete": primary.get("article_body_complete") if primary else None,
            "source_content_unavailable_reason": primary.get("source_content_unavailable_reason"),
            "publisher_exception_reason": primary.get("publisher_exception_reason"),
            "publisher_document_type": primary.get("publisher_document_type"),
            "publication_evidence": primary.get("publication_evidence", []),
            "visible_publication_date": primary.get("visible_publication_date"),
            "possible_publication_days": primary.get("possible_publication_days", []),
            "publisher_date_conflict": primary.get("publisher_date_conflict"),
            "baseline_queue_present": url in baseline_urls,
            "legacy_queue_only": url in baseline_urls and url not in enumerated,
            "queue_present": bool(rows), "queue": rows, "passed_gate": passed,
            "editorial_outcome": disposition, "exact_reason": reason,
            "history_present": bool(historical), "feed_present": url in feed_urls,
            "traceability_unresolved": bool(historical and url not in feed_urls),
            "source_attribution": {"evidence_maturity": (historical or {}).get("evidence_maturity"),
                "attribution_present": bool(re.search(r"pulso|la tercera", (historical or {}).get("what_happened", ""), re.I)),
                "confirmation_policy": (historical or {}).get("confirmation_policy")},
            "consistency_findings": (["published_queue_history_missing"] if published and not historical else []) +
                (["history_present_with_terminal_queue_rejection"] if historical and rejected else []),
            "current_discovery_trace": observed, "original_http_captures": captures_by_url.get(url, []),
            "omission": omission, "external_control": {"present": bool(original),
                "recall_expected": original.get("recall_expected", False), "cohort": original.get("recall_cohort"),
                "publication_date": original.get("publication_date"), "date_comparison": comparison,
                "independence": original.get("control_independence")}})
    index = {row["url"]: row for row in matrix}
    windows = {}
    for days in (30, 90):
        window = control.get("window_" + str(days), {})
        start, end = window.get("start"), window.get("end")
        eligible = [url for url, article in controls.items() if article.get("recall_expected")
                    and start and end and start <= (article.get("publication_date") or "") <= end]
        detected = [url for url in eligible if url in current]
        missed = [url for url in eligible if url not in current]
        declared = control.get("counts", {}).get("primary_recall_expected_" + str(days))
        dated_health = [row for row in matrix if row["current_core_verified_health"] and start and end
                        and start <= (row["publication_date"] or "") <= end]
        dated_metadata = [row for row in matrix if row["metadata_only_candidate"] and start and end
                          and start <= (row["publication_date"] or "") <= end]
        windows[str(days)] = {**window, "control_expected": len(eligible), "control_declared_expected": declared,
            "control_denominator_consistent": declared is None or declared == len(eligible),
            "control_detected_by_current_core": len(detected), "recall": len(detected) / len(eligible) if eligible else None,
            "missed": [{"url": url, "omission": index[url]["omission"], "legacy_queue_only": index[url]["legacy_queue_only"]} for url in missed],
            "current_verified_health_urls": len(dated_health),
            "metadata_only_candidates_with_verified_dates": len(dated_metadata),
            "metadata_only_candidate_urls": [row["url"] for row in dated_metadata],
            "editorial_outcomes": dict(Counter(row["editorial_outcome"] for row in dated_health)),
            "date_conflicts": [row["url"] for row in matrix if row["external_control"]["date_comparison"] == "conflict"
                               and row["url"] in eligible]}
    attribution_findings = [row["url"] for row in matrix if row["history_present"] and (
        row["source_attribution"]["evidence_maturity"] != "media_reported" or not row["source_attribution"]["attribution_present"])]
    start = control.get("window_90", {}).get("start")
    end = control.get("snapshot_date") or control.get("window_90", {}).get("end")
    unresolved_feed = [row["url"] for row in matrix if row["traceability_unresolved"] and (
        not row["publication_date"] or not start or not end or start <= row["publication_date"] <= end)]
    return {"source": SOURCE, "verdict": "EVIDENCE_REQUIRES_COVERAGE_AND_EDITORIAL_REVIEW",
        "discovery_run_at": discovery.get("at"), "runtime": discovery.get("runtime"),
        "selected_sources": discovery.get("selected_sources"), "core_source_present": SOURCE in discovery.get("sources", {}),
        "audit_discovery_error": discovery.get("audit_discovery_error"),
        "core_source": discovery.get("sources", {}).get(SOURCE), "coverage": coverage,
        "source_inventory_returned_to_core": returned_to_core,
        "source_inventory_exception": source_exception if not returned_to_core else None,
        "processing_deferrals": discovery.get("processing_deferrals", {}),
        "primary_coverage": primary_coverage,
        "complementary_archive_limits": [row for row in coverage if row.get("status") == "archive_coverage"],
        "baseline_queue": list(baseline), "windows": windows, "matrix": matrix,
        "source_attribution_findings": attribution_findings,
        "unresolved_recent_feed_exclusions": unresolved_feed,
        "counts": {"current_core_discovered_urls": len(enumerated),
                   "current_core_verified_health_urls": len(current),
                   "source_trace_candidate_urls": len(text_candidates | metadata_candidates),
                   "metadata_only_candidates": len(metadata_only), "source_queue_urls": len(queued),
                   "external_control_urls": len(controls), "history_urls": len(history_by_url),
                   "published_in_feed": sum(row["history_present"] and row["feed_present"] for row in matrix)},
        "publisher_editorial_exceptions": [row for row in matrix if row["metadata_only_candidate"]],
        "method": "Current source_details discovered records establish verified health recall; discovered_metadata_only records establish enumerated identities without verified article content and never inflate health recall. Queue/history/control are separate evidence joins. Control dates define frozen complete calendar windows. No search snippet supplies a date."}


def curate_history(history):
    spec = importlib.util.spec_from_file_location("pulso_runtime_feed", REPOSITORY / "scripts/export_web_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.curate(history, resolve_external=False)


def snapshot_feed(snapshot, history_modified_at=None):
    """Only serialized snapshot rows establish actual candidate feed presence."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("signals"), list):
        return [], {"mode": "candidate_snapshot_missing_or_invalid", "serialized_feed_verified": False}
    fresh = None
    if history_modified_at is not None:
        try:
            stamp = datetime.fromisoformat(snapshot["generated_at"].replace("Z", "+00:00"))
            fresh = stamp.tzinfo is not None and stamp.timestamp() >= history_modified_at
        except (ValueError, TypeError, KeyError):
            fresh = False
    return snapshot["signals"], {"mode": "actual_serialized_candidate_snapshot",
        "serialized_feed_verified": True, "generated_at": snapshot.get("generated_at"),
        "generated_after_current_history": fresh}


def current_execution_discovery(discovery, started_at):
    """An interrupted crawl cannot borrow a previous run's discovery evidence."""
    try:
        stamp = datetime.fromisoformat(discovery["at"].replace("Z", "+00:00"))
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        fresh = stamp.tzinfo is not None and start.tzinfo is not None and stamp >= start
    except (ValueError, TypeError, KeyError):
        fresh = False
    if fresh:
        return discovery, True
    stale = dict(discovery)
    stale["source_details"] = {**discovery.get("source_details", {}), SOURCE: []}
    stale["sources"] = {key: row for key, row in discovery.get("sources", {}).items() if key != SOURCE}
    stale["processing_deferrals"] = {key: row for key, row in discovery.get("processing_deferrals", {}).items() if key != SOURCE}
    stale["audit_discovery_error"] = "discovery_not_persisted_by_current_execution"
    return stale, False


def report_only_discovery(discovery, prior_report):
    """A fixture-only rejoin preserves an interrupted core's stale-run guard."""
    execution = prior_report.get("last_core_execution") or prior_report.get("execution") or {}
    if execution.get("engine_called") and execution.get("started_at"):
        return current_execution_discovery(discovery, execution["started_at"])
    return discovery, None


def annotate_pending(report, execution):
    """Explain operational pending states only when current observations support it."""
    unresolved = []
    for row in report["matrix"]:
        if row["editorial_outcome"] != "pending" or not row["exact_reason"].startswith("not_processed;"):
            continue
        reason = None
        pending = [item for item in row["queue"] if item["status"] == "pending"]
        ended = execution.get("finished_at") or execution.get("started_at")
        if ended and pending and all(item.get("publication_date") and item["publication_date"] > ended[:10] for item in pending):
            reason = "processing_not_attempted:future_BACKFILL_date_excluded_by_queue_ready"
        elif ended and pending and all(item.get("retry_at") and item["retry_at"] > ended for item in pending):
            reason = "processing_not_attempted:retry_at_not_reached"
        elif execution.get("engine_called") and not execution.get("engine_completed"):
            reason = "processing_not_completed:runtime_error:" + str(execution.get("error_type", "unknown"))
        elif execution.get("mode") == "discovery_only":
            reason = "processing_not_attempted:explicit_discovery_only"
        elif execution.get("engine_completed"):
            deferral = report.get("processing_deferrals", {}).get(SOURCE, {})
            limit = execution.get("processing_limit", 0)
            if deferral.get("required_tier") == "fast" and deferral.get("before_queue_start"):
                reason = "processing_not_attempted:" + str(deferral.get("reason", "fast_analysis_capacity_exhausted"))
            elif limit and execution.get("processing_attempts_increased", 0) >= limit:
                reason = "processing_not_attempted:global_processing_limit_reached"
            elif execution.get("model_capacity_after", {}).get("fast") is False:
                reason = "processing_not_attempted:fast_analysis_capacity_exhausted"
        if reason:
            row["exact_reason"] = reason
            row["operational_reason_evidence"] = "execution flags, real attempt deltas and read-only budget state; no editorial rejection inferred"
        else:
            row["operational_reason_unresolved"] = True
            unresolved.append(row["url"])
    report["unresolved_pending_operational_reasons"] = unresolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY)
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--discovery-only", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--control", type=Path, default=Path("data/audits/pulso_external_control_2026_10_11.json"))
    parser.add_argument("--output", type=Path, default=Path("data/audits/pulso_runtime_2026_10_11.json"))
    parser.add_argument("--capture", type=Path, default=Path("data/audits/pulso_runtime_capture"))
    args = parser.parse_args()
    root = args.root.resolve()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=REPOSITORY, text=True).strip()
    branch = branch or os.environ.get("GITHUB_REF_NAME", "")
    if not branch.startswith("codex/b-pulso"):
        parser.error("Runtime evidence writes require isolated codex/b-pulso* branch; main/staging are prohibited")
    os.environ["RADAR_ROOT"] = str(root)
    control_path = args.control if args.control.is_absolute() else root / args.control
    out = args.output if args.output.is_absolute() else root / args.output
    capture_path = args.capture if args.capture.is_absolute() else root / args.capture
    control = read_json(control_path, {})
    if not control.get("articles"):
        parser.error("Frozen external control is required; refusing an empty recall benchmark")
    queue_path = root / "data/state/pending_queue.json"
    before = read_json(queue_path, {})
    prior = read_json(out, {})
    baseline = prior.get("baseline_queue", []) if args.report_only else queue_snapshot(before)
    unrelated_before = digest_json({key: row for key, row in before.items() if row.get("source") != SOURCE})
    execution = {"mode": "report_only_rejoin" if args.report_only else "discovery_only" if args.discovery_only else "real_core_processing",
                 "engine_called": False, "engine_completed": False,
                 "started_at": datetime.now(timezone.utc).isoformat(), "processing_limit": args.limit,
                 "ai_credentials_present": bool(os.environ.get("OPENAI_API_KEY")), "ai_guardrails_modified": False}
    if not args.report_only:
        from radar_salud import ai_budget, engine_cli
        try:
            execution["budget_before"] = json.loads(json.dumps(ai_budget.status()))
        except Exception as error:
            execution["budget_before_read_error"] = type(error).__name__ + ":" + str(error)[:200]
        observer = CaptureObserver(capture_path, {normalized_url(row["url"]) for row in control["articles"]})
        original_argv = sys.argv
        previous_term = signal.getsignal(signal.SIGTERM)
        def terminate(signum, frame):
            raise KeyboardInterrupt("runtime_terminated_signal_" + str(signum))
        signal.signal(signal.SIGTERM, terminate)
        sys.argv = ["engine_cli", "--sources", SOURCE, "--limit", str(args.limit)]
        if args.discovery_only:
            sys.argv.append("--discovery-only")
        try:
            execution["engine_called"] = True
            with observe_pulso_fetches(observer):
                engine_cli.main()
            execution["engine_completed"] = True
        except (Exception, KeyboardInterrupt) as error:
            execution.update(error_type=type(error).__name__, error=str(error)[:500])
        finally:
            sys.argv = original_argv
            signal.signal(signal.SIGTERM, previous_term)
            observer.flush()
            try:
                execution["budget_after"] = json.loads(json.dumps(ai_budget.status()))
                execution["model_capacity_after"] = {kind: ai_budget.has_capacity(kind) for kind in ("fast", "deep")}
            except Exception as error:
                execution["budget_after_read_error"] = type(error).__name__ + ":" + str(error)[:200]
            execution["finished_at"] = datetime.now(timezone.utc).isoformat()
    discovery = read_json(root / "data/state/discovery_run.json", {})
    discovery_record = discovery
    discovery_current = None
    if not args.report_only:
        discovery, discovery_current = current_execution_discovery(discovery, execution["started_at"])
    else:
        discovery, discovery_current = report_only_discovery(discovery, prior)
    after = read_json(queue_path, {})
    if not args.report_only:
        execution["processing_attempts_increased"] = sum(max(0, item.get("attempts", 0) - before.get(key, {}).get("attempts", 0))
            for key, item in after.items() if item.get("source") == SOURCE)
    history_value = read_json(root / "data/history/superintendencia_signals.json", [])
    history = history_value.get("signals", []) if isinstance(history_value, dict) else history_value
    candidate = curate_history(history)
    snapshot_path = root / "web/data/radar_today.json"
    history_path = root / "data/history/superintendencia_signals.json"
    feed, feed_evidence = snapshot_feed(read_json(snapshot_path, {}), history_path.stat().st_mtime if history_path.exists() else None)
    captures = read_json(capture_path / "manifest.json", {})
    preserved_path = root / "tests/fixtures/pulso_runtime_real/manifest.json"
    preserved = read_json(preserved_path, {})
    # Retained raw responses survive warm-cache runs, while the live observer
    # remains scoped to the current HTTP execution. Never call them fresh polls.
    preserved_requests = []
    preserved_manifests = []
    for directory in ("pulso_runtime_real", "pulso_editorial_exception_real", "pulso_targeted_primary_real"):
        relative = Path("tests/fixtures") / directory
        fixture_manifest = root / relative / "manifest.json"
        fixture = read_json(fixture_manifest, {})
        if fixture_manifest.exists():
            preserved_manifests.append(dict(path=str(relative / "manifest.json"),
                sha256=hashlib.sha256(fixture_manifest.read_bytes()).hexdigest(), status=fixture.get("status")))
        for record in fixture.get("requests", []):
            retained = dict(record)
            if record.get("gzip_file"):
                retained["gzip_file"] = str(relative / record["gzip_file"])
            retained["original_capture_manifest_sha256"] = (
                record.get("original_capture_manifest_sha256") or (
                    hashlib.sha256(fixture_manifest.read_bytes()).hexdigest() if fixture_manifest.exists() else None))
            preserved_requests.append(retained)
    joined_captures = dict(captures, requests=captures.get("requests", []) + preserved_requests)
    report = join_report(discovery, after, history, feed, control, baseline=baseline, captures=joined_captures)
    candidate_urls = {url for row in candidate if (url := normalized_url(row.get("source_url")))}
    for row in report["matrix"]:
        row["in_memory_curate_eligible"] = row["url"] in candidate_urls
    report.update(at=datetime.now(timezone.utc).isoformat(), branch=branch,
                  code_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True).strip(),
                  execution=execution, prior_execution=prior.get("execution") if args.report_only else None,
                  discovery_persisted_by_current_execution=discovery_current,
                  persisted_discovery_record_at=discovery_record.get("at"),
                  fresh_publisher_poll_claimed=not args.report_only and any(row.get("status") == 200 and (
                      "/arc/outboundfeeds/" in row.get("url", "") or "/canal/" in row.get("url", "") or "/etiqueta/" in row.get("url", ""))
                      for row in captures.get("requests", [])),
                  capture_status_counts=dict(Counter(str(row.get("status", "unknown")) for row in captures.get("requests", []))),
                  last_core_execution=execution if execution["engine_called"] else prior.get("last_core_execution", prior.get("execution")),
                  external_control_path=str(control_path.relative_to(root)),
                  external_control_sha256=hashlib.sha256(control_path.read_bytes()).hexdigest(),
                  capture_manifest=str(capture_path / "manifest.json"),
                  preserved_original_fixture_manifest=str(preserved_path) if preserved_path.exists() else None,
                  preserved_original_fixture_status=preserved.get("status"),
                  preserved_original_fixture_manifests=preserved_manifests,
                  unrelated_queue_unchanged=(prior.get("unrelated_queue_unchanged") if args.report_only else
                      unrelated_before == digest_json({key: row for key, row in after.items() if row.get("source") != SOURCE})),
                  feed_method="actual serialized web/data/radar_today.json; full-history curate(resolve_external=False) eligibility recorded separately; no injected rows",
                  feed_evidence={**feed_evidence, "path": str(snapshot_path),
                      "sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest() if snapshot_path.exists() else None})
    annotate_pending(report, report["last_core_execution"] or execution)
    atomic_json(out, report)
    print(json.dumps({"report": str(out), "core_source_present": report["core_source_present"],
                      "counts": report["counts"], "recall": {days: row["recall"] for days, row in report["windows"].items()},
                      "verdict": report["verdict"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
