"""Read-only directed QA of original Pulso runtime evidence.

A discovery PASS is not end-to-end acceptance. Even automated processing PASS
requires independent review of the actual published facts on the final SHA.
The frozen controls are a recall benchmark, never an inventory or publication
quota. This reader cannot change the queue, history, budget or source code.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

SOURCE = "pulso_latercera"
ROOT = Path(__file__).resolve().parents[1]
WINDOWS = {"30": ("2026-09-11", "2026-10-10", 29), "90": ("2026-07-13", "2026-10-10", 79)}
REQUIRED_FEEDS = {"section:" + name for name in (
    "pulso", "nacional", "politica", "tendencias", "que-pasa", "paula", "sustentabilidad",
    "lt-board", "sociales", "servicios", "tecnologia", "la-tercera-pm", "horizontes",
)} | {"tag:" + name for name in ("salud", "isapres", "fonasa", "clinicas", "hospitales", "listas-de-espera", "banmedica")}
PRIMARY_DATE_SOURCES = {"visible_article_byline", "json_ld_datePublished", "article_published_time", "article_time"}
SHA = re.compile(r"[0-9a-f]{64}")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def normalized_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value or "")
    if parsed.scheme != "https" or parsed.netloc not in {"www.latercera.com", "latercera.com"}:
        return None
    return urlunsplit(("https", "www.latercera.com", parsed.path.rstrip("/") + "/", "", ""))


def stamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def publisher_day(value):
    try:
        return date.fromisoformat(value).isoformat() if len(value) == 10 else (
            stamp(value).astimezone(ZoneInfo("America/Santiago")).date().isoformat())
    except (ValueError, TypeError, AttributeError):
        return None


class PrimaryDates(HTMLParser):
    """Independent URL/date projection, without importing the source parser."""
    def __init__(self):
        super().__init__()
        self.canonical, self.published, self.nodes, self.parts = None, [], [], None
        self.article_depth, self.article_text, self.title_text = 0, [], []
        self.in_title, self.blocked = False, 0

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "link" and "canonical" in attr.get("rel", "").split():
            self.canonical = normalized_url(attr.get("href"))
        if tag == "meta" and (attr.get("property") or attr.get("name")) == "article:published_time":
            self.published.append(attr.get("content"))
        if tag == "script" and attr.get("type") == "application/ld+json":
            self.parts = []
        if tag in {"script", "style", "noscript"}:
            self.blocked += 1
        if tag == "article":
            self.article_depth += 1
        if tag == "h1":
            self.in_title = True

    def handle_data(self, data):
        if self.parts is not None:
            self.parts.append(data)
        if not self.blocked and self.article_depth:
            self.article_text.append(data)
        if not self.blocked and self.in_title:
            self.title_text.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.parts is not None:
            try:
                self.nodes.extend(self.walk(json.loads("".join(self.parts))))
            except (ValueError, TypeError):
                pass
            self.parts = None
        if tag in {"script", "style", "noscript"}:
            self.blocked = max(0, self.blocked - 1)
        if tag == "article":
            self.article_depth = max(0, self.article_depth - 1)
        if tag == "h1":
            self.in_title = False

    @classmethod
    def walk(cls, node):
        if isinstance(node, list):
            return [value for child in node for value in cls.walk(child)]
        if not isinstance(node, dict):
            return []
        return [node] + cls.walk(node.get("@graph", []))

    def days_for(self, url):
        dates = list(self.published) if self.canonical == url else []
        for node in self.nodes:
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            entity = node.get("mainEntityOfPage")
            entity = entity.get("@id") if isinstance(entity, dict) else entity
            identities = (node.get("url"), node.get("@id"), entity)
            if "NewsArticle" in types and any(normalized_url(value) == url for value in identities if isinstance(value, str)):
                dates.append(node.get("datePublished"))
        return {publisher_day(value) for value in dates if publisher_day(value)}

    def primary_text(self, url):
        for node in self.nodes:
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if "NewsArticle" in types and normalized_url(node.get("url") or node.get("@id")) == url:
                body, title = node.get("articleBody"), node.get("headline")
                if isinstance(body, str) and len(body.strip()) >= 160 and isinstance(title, str):
                    return title, body
        if self.canonical == url:
            return " ".join(self.title_text), " ".join(self.article_text)
        return "", ""


def local_capture_path(root, relative):
    path = Path(relative or "")
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("unsafe_capture_path")
    if path.parts[0] == "responses":
        path = Path("data/audits/pulso_runtime_capture") / path
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("unsafe_capture_path")
    return target


def verify_primary_capture(row, root):
    """Require original bytes matching the primary detail hash and URL/date."""
    url, expected = row["url"], row.get("primary_detail_sha256")
    errors = []
    for record in row.get("original_http_captures", []):
        if record.get("status") != 200 or normalized_url(record.get("url")) != url:
            continue
        if expected not in {record.get("sha256"), record.get("returned_text_utf8_sha256")}:
            continue
        try:
            compressed = local_capture_path(root, record.get("gzip_file")).read_bytes()
            if record.get("gzip_sha256") and digest(compressed) != record["gzip_sha256"]:
                raise ValueError("gzip_sha256_mismatch")
            raw = gzip.decompress(compressed)
            if digest(raw) != record.get("sha256"):
                raise ValueError("original_bytes_sha256_mismatch")
            text = raw.decode(record.get("charset") or "utf-8", errors="replace")
            if digest(text.encode()) != expected:
                raise ValueError("primary_returned_text_sha256_mismatch")
            parser = PrimaryDates()
            parser.feed(text)
            if parser.canonical != url or parser.days_for(url) != {row.get("publication_date")}:
                raise ValueError("independent_primary_url_or_publication_date_mismatch")
            title, body = parser.primary_text(url)
            if len(title.strip()) < 18 or len(body.strip()) < 160:
                raise ValueError("original_primary_title_or_body_missing")
            if row.get("primary_detail_cache_hit"):
                if record.get("capture_provenance") != "preserved_original_http_response":
                    raise ValueError("cached_primary_capture_provenance_missing")
                if not SHA.fullmatch(str(record.get("original_capture_manifest_sha256", ""))):
                    raise ValueError("cached_primary_manifest_sha256_missing")
            return None
        except (OSError, ValueError, TypeError, UnicodeError, EOFError) as error:
            errors.append(type(error).__name__ + ":" + str(error))
    return errors or ["matching_original_primary_capture_missing"]


def budget_delta(execution):
    delta = {}
    try:
        for tier in ("fast", "deep"):
            delta[tier] = {}
            for metric in ("attempted", "successful", "failed"):
                values = []
                for scope in ("run", "month"):
                    before = execution["budget_before"][scope][tier][metric]
                    after = execution["budget_after"][scope][tier][metric]
                    if type(before) is not int or type(after) is not int or before < 0 or after < before:
                        raise ValueError("ledger_counter_decreased_or_invalid")
                    values.append(after - before)
                if values[0] != values[1]:
                    raise ValueError("run_and_month_delta_disagree")
                delta[tier][metric] = values[0]
            if delta[tier]["attempted"] != delta[tier]["successful"] + delta[tier]["failed"]:
                raise ValueError("attempts_without_recorded_results")
        return delta, None
    except (KeyError, TypeError, ValueError) as error:
        return delta, str(error)


def workflow_limits(path):
    text = path.read_text()
    return dict(re.findall(r"^\s+(RADAR_(?:FAST|DEEP)_PER_(?:RUN|MONTH)):\s*(\d+)\s*$", text, re.M))


def api_page_key(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "www.latercera.com":
            return None
        query = json.loads(parse_qs(parsed.query)["query"][0])
        if parsed.path.endswith("/story-feed-sections-fetch"):
            feed = "section:" + query["includeSections"].lstrip("/")
        elif parsed.path.endswith("/story-feed-tag-fetch"):
            feed = "tag:" + query["tagSlug"]
        else:
            return None
        return feed, query["feedOffset"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def verify_api_pages(pages, records, root):
    """HTTP hashes for the cursor chain; original JSON for first/boundary pages."""
    failures = []
    proof_offsets = {row.get("offset") for row in pages[:1] + pages[-3:]}
    for index, page in enumerate(pages):
        key = (page.get("feed"), page.get("offset"))
        if not SHA.fullmatch(str(page.get("json_sha256", ""))):
            failures.append(dict(code="public_api_page_hash_missing", offset=page.get("offset")))
            continue
        candidates = [record for record in records if api_page_key(record.get("url", "")) == key
                      and record.get("status") == 200
                      and page.get("json_sha256") in {record.get("sha256"), record.get("returned_text_utf8_sha256")}
                      and stamp(record.get("captured_at"))]
        if not candidates:
            failures.append(dict(code="public_api_http_chain_unproven", offset=page.get("offset")))
            continue
        if index and (pages[index - 1].get("next") != page.get("offset") or page.get("offset", -1) <= pages[index - 1].get("offset", -1)):
            failures.append(dict(code="public_api_cursor_chain_nonadvancing", offset=page.get("offset")))
        if page.get("offset") not in proof_offsets:
            continue
        verified = False
        for record in candidates:
            try:
                base = Path(record.get("_capture_root") or root)
                relative = Path(record.get("gzip_file") or "")
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe_capture_path")
                path = (base / relative).resolve()
                if not path.is_relative_to(base.resolve()):
                    raise ValueError("unsafe_capture_path")
                compressed = path.read_bytes()
                raw = gzip.decompress(compressed)
                text = raw.decode(record.get("charset") or "utf-8", errors="replace")
                if digest(raw) != record.get("sha256") or digest(text.encode()) != page.get("json_sha256"):
                    raise ValueError("raw_api_sha256_mismatch")
                if record.get("gzip_sha256") and digest(compressed) != record["gzip_sha256"]:
                    raise ValueError("raw_api_gzip_sha256_mismatch")
                document = json.loads(text)
                document = document.get("data", document)
                entries = document["content_elements"]
                if (not isinstance(entries, list) or len(entries) != page.get("primary_entries")
                        or document.get("count") != page.get("count") or document.get("next") != page.get("next")):
                    raise ValueError("raw_api_inventory_or_cursor_disagrees")
                days = [publisher_day(entry.get("first_publish_date")) for entry in entries]
                if page.get("inventory_day_max") and (None in days or max(days) != page["inventory_day_max"]):
                    raise ValueError("raw_api_publication_boundary_disagrees")
                verified = True
                break
            except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, EOFError):
                continue
        if not verified:
            failures.append(dict(code="public_api_original_boundary_json_missing_or_invalid", offset=page.get("offset")))
    return failures


def capture_records(root, artifact=None):
    """Read live, retained or downloaded original proof without restoring state."""
    paths = [root / "data/audits/pulso_runtime_capture/manifest.json", root / "tests/fixtures/pulso_runtime_real/manifest.json"]
    if artifact and artifact.exists():
        paths.extend(artifact.rglob("manifest.json"))
    records = []
    for path in paths:
        if not path.exists():
            continue
        value = json.loads(path.read_text())
        if value.get("source") == SOURCE:
            records.extend(dict(record, _capture_root=str(path.parent)) for record in value.get("requests", []))
    return records


def evaluate(report, control, *, root, discovery, queue, history, snapshot, telemetry=(), control_sha=None, captures=(), phase="auto"):
    findings, checks = [], {}
    def fail(domain, code, **evidence):
        findings.append(dict(domain=domain, code=code, **evidence))
    execution = report.get("last_core_execution") or report.get("execution", {})
    mode = execution.get("mode")
    actual_processing = mode == "real_core_processing"
    processing = actual_processing and phase != "discovery"
    if mode not in {"discovery_only", "real_core_processing"}:
        fail("discovery", "genuine_core_execution_missing", mode=mode)
    if phase == "processing" and not actual_processing:
        fail("processing", "requested_processing_has_no_actual_processing_execution")
    if not execution.get("engine_called") or not execution.get("engine_completed"):
        fail("discovery", "core_did_not_complete", error=execution.get("error_type"))
    start, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    discovered_at = stamp(report.get("discovery_run_at"))
    if not start or not end or end < start or not discovered_at or not start <= discovered_at <= end:
        fail("discovery", "stale_or_unbound_discovery_timestamp")
    if report.get("runtime") != "daily_core" or report.get("selected_sources") != [SOURCE] or not report.get("core_source_present"):
        fail("discovery", "real_source_scoped_core_missing")
    if report.get("audit_discovery_error"):
        fail("discovery", "audit_discovery_error", error=report["audit_discovery_error"])
    if report.get("unrelated_queue_unchanged") is not True:
        fail("discovery", "other_source_queue_changed_or_unproven")
    if execution.get("ai_guardrails_modified") is not False:
        fail("discovery", "ai_guardrails_preservation_unproven")
    try:
        daily = workflow_limits(root / ".github/workflows/daily-radar.yml")
        recovery = workflow_limits(root / ".github/workflows/pulso-runtime-recovery.yml")
        if len(daily) != 4 or daily != recovery:
            fail("discovery", "recovery_budget_limits_differ_from_daily_core", daily=daily, recovery=recovery)
    except OSError as error:
        fail("discovery", "budget_workflow_evidence_missing", error=str(error))
    delta, error = budget_delta(execution)
    checks["actual_ai_budget_delta"] = delta
    if error:
        fail("discovery", "ai_ledger_invalid", error=error)
    elif not actual_processing and any(value for tier in delta.values() for value in tier.values()):
        fail("discovery", "discovery_consumed_analysis_budget")
    if control_sha and report.get("external_control_sha256") != control_sha:
        fail("discovery", "frozen_control_hash_mismatch")
    controls = {normalized_url(row.get("url")): row for row in control.get("articles", [])}
    rows = {row.get("url"): row for row in report.get("matrix", [])}
    details = discovery.get("source_details", {}).get(SOURCE, [])
    actual = {normalized_url(row.get("url")) for row in details if row.get("status") == "discovered"}
    for days, (first, last, count) in WINDOWS.items():
        expected = {url for url, article in controls.items() if url and article.get("recall_expected")
                    and first <= (article.get("publication_date") or "") <= last}
        window = report.get("windows", {}).get(days, {})
        misses = sorted(expected - actual)
        checks["window_" + days] = dict(start=first, end=last, frozen_expected=len(expected), detected=len(expected & actual), misses=misses)
        if control.get("window_" + days, {}).get("start") != first or control.get("window_" + days, {}).get("end") != last:
            fail("discovery", "complete_calendar_window_changed", days=days)
        if (len(expected) != count or control.get("counts", {}).get("primary_recall_expected_" + days) != count
                or window.get("control_expected") != count or window.get("control_declared_expected") != count
                or window.get("control_denominator_consistent") is not True):
            fail("discovery", "frozen_control_denominator_changed", days=days, expected=count, observed=len(expected))
        if window.get("start") != first or window.get("end") != last:
            fail("discovery", "reported_window_incomplete", days=days)
        actual_recall = len(expected & actual) / len(expected) if expected else None
        if window.get("control_detected_by_current_core") != len(expected & actual) or window.get("recall") != actual_recall:
            fail("discovery", "reported_recall_not_supported_by_core_traces", days=days)
        if misses:
            fail("discovery", "important_external_control_omissions", days=days,
                 omissions=[dict(url=url, explanation=rows.get(url, {}).get("omission")) for url in misses])
        if window.get("date_conflicts"):
            fail("discovery", "external_publication_date_conflicts", days=days, urls=window["date_conflicts"])
    coverage = report.get("primary_coverage") or {}
    declared = set(coverage.get("required_feeds", []))
    summaries = {row.get("feed"): row for row in report.get("coverage", []) if row.get("status") == "public_feed_coverage"}
    if coverage.get("status") != "runtime_coverage" or coverage.get("coverage_complete") is not True or declared != REQUIRED_FEEDS:
        fail("discovery", "primary_required_public_feed_coverage_incomplete", missing=sorted(REQUIRED_FEEDS - declared))
    for name in REQUIRED_FEEDS:
        summary = summaries.get(name, {})
        ending = summary.get("termination")
        pages = [row for row in details if row.get("status") == "public_feed_page" and row.get("feed") == name]
        if not pages or pages[0].get("offset") != 0 or len(pages) != summary.get("pages_attempted"):
            fail("discovery", "complete_public_api_page_chain_missing", feed=name)
        for problem in verify_api_pages(pages, captures, root):
            fail("discovery", problem.pop("code"), feed=name, **problem)
        if not summary.get("coverage_complete") or summary.get("errors") != 0:
            fail("discovery", "feed_incomplete_or_errors", feed=name, summary=summary)
        elif ending == "three_publication_ordered_detail_verified_old_pages":
            boundary = pages[-3:]
            cutoff = (date.fromisoformat(WINDOWS["90"][0]) - timedelta(days=2)).isoformat()
            if len(boundary) != 3 or any(row.get("primary_entries") != 24 or not row.get("inventory_day_max")
                                       or row["inventory_day_max"] >= cutoff for row in boundary) or boundary[-1].get("boundary_pages", 0) < 3:
                fail("discovery", "three_old_pages_boundary_unproven", feed=name)
        elif ending == "all_feed_count_delimited_articles":
            last_page = pages[-1] if pages else {}
            total = summary.get("publisher_count")
            if type(total) is not int or not 0 <= total < 10000 or last_page.get("offset", -1) + last_page.get("primary_entries", 0) < total:
                fail("discovery", "count_delimited_feed_exhaustion_unproven", feed=name)
        else:
            fail("discovery", "feed_cap_or_unknown_boundary", feed=name, termination=ending)
    current_queue = {}
    for fingerprint, item in queue.items():
        if item.get("source") == SOURCE:
            url = normalized_url(item.get("raw", {}).get("url"))
            current_queue.setdefault(url, []).append((fingerprint, item))
    for baseline in report.get("baseline_queue", []):
        candidates = current_queue.get(baseline.get("url"), [])
        item = next((item for key, item in candidates if key == baseline.get("fingerprint")), None)
        if (not item or any(item.get(key) != baseline.get(key) for key in ("lane", "detected_at"))
                or item.get("attempts", 0) < baseline.get("attempts", 0)
                or baseline.get("status") in {"published", "rejected", "archived"} and item.get("status") != baseline["status"]):
            fail("discovery", "baseline_queue_identity_or_bookkeeping_changed", url=baseline.get("url"))
    for url in actual:
        row = rows.get(url, {})
        if row.get("current_core_detected") is not True:
            fail("discovery", "matrix_not_bound_to_actual_discovery", url=url)
        if row.get("publication_date_source") not in PRIMARY_DATE_SOURCES or not SHA.fullmatch(str(row.get("primary_detail_sha256", ""))):
            fail("discovery", "primary_publication_evidence_missing", url=url)
        if url in controls and controls[url].get("publication_date") != row.get("publication_date"):
            fail("discovery", "original_control_date_disagrees", url=url)
        captured = stamp(row.get("primary_detail_captured_at"))
        if not captured or end and captured > end:
            fail("discovery", "primary_capture_timestamp_invalid", url=url)
        if row.get("primary_detail_cache_hit"):
            if (row.get("publication_date_evidence") != "reused_verified_primary_byline_unchanged_publisher_lastmod"
                    or not row.get("publisher_lastmod")):
                fail("discovery", "cached_primary_falsely_labeled_fresh_or_unbound", url=url)
        elif row.get("publication_date_evidence") != "current_verified_detail" or start and captured and captured < start:
            fail("discovery", "current_primary_capture_freshness_unproven", url=url)
        # Original bytes for every independent important control, not just a
        # manually chosen tiny positive sample. Other positives keep SHA traces.
        if url in controls and controls[url].get("recall_expected"):
            error = verify_primary_capture(row, root)
            if error:
                fail("discovery", "original_primary_capture_not_verified", url=url, errors=error)
        candidates = current_queue.get(url, [])
        if len(candidates) != 1:
            fail("discovery", "canonical_queue_missing_or_duplicated", url=url, count=len(candidates))
            continue
        metadata = candidates[0][1].get("raw", {}).get("metadata", {})
        if (metadata.get("article_verified") is not True or metadata.get("source_quality_gate") != "passed"
                or normalized_url(metadata.get("canonical_url")) != url
                or metadata.get("publication_date") != row.get("publication_date")
                or metadata.get("publication_date_source") not in PRIMARY_DATE_SOURCES
                or publisher_day(metadata.get("publication_timestamp")) != row.get("publication_date")
                or metadata.get("html_sha256") != row.get("primary_detail_sha256")
                or len(str(metadata.get("page_text") or "").strip()) < 160):
            fail("discovery", "queue_primary_detail_evidence_unverified", url=url)
    if processing:
        if not delta.get("fast", {}).get("attempted") or not delta.get("fast", {}).get("successful"):
            fail("processing", "no_actual_successful_fast_editorial_analysis")
        events = [row for row in telemetry if stamp(row.get("at")) and start and end and start <= stamp(row["at"]) <= end and row.get("kind") == "fast"]
        if len(events) != delta.get("fast", {}).get("attempted") or sum(row.get("success") is True for row in events) != delta.get("fast", {}).get("successful"):
            fail("processing", "actual_api_telemetry_and_ledger_delta_disagree")
        if any(row.get("success") is True and not row.get("response_id") for row in events):
            fail("processing", "successful_analysis_without_actual_api_response_id")
        checks["actual_fast_response_events"] = len(events)
        feed = {normalized_url(row.get("source_url")): row for row in snapshot.get("signals", [])}
        historical = {normalized_url(row.get("source_url")): row for row in history}
        feed_evidence = report.get("feed_evidence", {})
        if not feed_evidence.get("serialized_feed_verified") or feed_evidence.get("generated_after_current_history") is not True:
            fail("processing", "actual_serialized_feed_missing_or_stale")
        if report.get("source_attribution_findings") or report.get("unresolved_recent_feed_exclusions"):
            fail("processing", "unresolved_media_attribution_or_feed_loss")
        if report.get("unresolved_pending_operational_reasons"):
            fail("processing", "pending_operational_reasons_unresolved")
        for url in actual:
            row = rows.get(url, {})
            reason = row.get("exact_reason") or ""
            if not reason or any(term in reason for term in ("no_editorial_verdict", "processor_rejected", "reason_missing", "unknown", "specific exclusion is not emitted")):
                fail("processing", "outcome_reason_unresolved", url=url, reason=reason)
            if row.get("consistency_findings") or row.get("traceability_unresolved"):
                fail("processing", "queue_history_feed_inconsistent", url=url)
            if bool(row.get("feed_present")) != (url in feed) or bool(row.get("history_present")) != (url in historical):
                fail("processing", "reported_history_or_feed_presence_not_actual", url=url)
            if len(current_queue.get(url, [])) != 1:
                continue
            item = current_queue[url][0][1]
            assessment = item.get("raw", {}).get("metadata", {}).get("editorial_assessment") or {}
            score = assessment.get("relevance_score")
            if score is not None and assessment.get("threshold") != 72:
                fail("processing", "media_editorial_threshold_changed", url=url, assessment=assessment)
            if url in controls and controls[url].get("recall_expected") and WINDOWS["30"][0] <= controls[url].get("publication_date", "") <= WINDOWS["30"][1]:
                if item.get("status") == "pending" or reason in {"analysis_unavailable", "article_verification_failed", "budget_or_analysis_deferred"}:
                    fail("processing", "recent_important_control_not_editorially_processed", url=url, reason=reason)
            if item.get("status") == "published":
                if assessment.get("decision") != "published" or type(score) is not int or score < 72 or not assessment.get("analysis_reason"):
                    fail("processing", "published_without_unchanged_editorial_gate_trace", url=url)
                published = historical.get(url, {})
                text = " ".join(str(published.get(key) or "") for key in ("title", "what_happened", "why_it_matters"))
                if (published.get("evidence_maturity") != "media_reported"
                        or not re.search(r"seg[uú]n\s+(?:pulso|la tercera)|(?:pulso|la tercera).*(?:report|inform|public|señal)", str(published.get("what_happened") or ""), re.I)
                        or published.get("publication_date") != row.get("publication_date")):
                    fail("processing", "published_media_attribution_or_real_date_invalid", url=url)
                if "presupuesto-salud-2027-rebajas" in url and not re.search(r"propuest|proyect|discusi|tramit", text, re.I):
                    fail("processing", "budget_proposal_presented_as_enacted", url=url)
                if "isapres-logran-detener-la-fuga" in url and (not re.search(r"mayo", text, re.I) or not re.search(r"contrat|suscrip|firm", text, re.I)):
                    fail("processing", "historical_contract_flow_period_or_metric_lost", url=url)
                if "senior-housing-los-grupos" in url and re.search(r"fne\s+(?:aprob[oó]|autoriz[oó])", text, re.I):
                    fail("processing", "publisher_fne_notification_upgraded_to_approval", url=url)
            elif item.get("status") == "rejected" and (assessment.get("decision") != "rejected" or not assessment.get("reason")):
                fail("processing", "rejection_without_exact_assessment", url=url)
            elif item.get("status") == "retry" and (assessment.get("decision") != "pending" or assessment.get("reason") != reason):
                fail("processing", "deferred_without_exact_assessment", url=url)
    discovery_failures = [row for row in findings if row["domain"] == "discovery"]
    processing_failures = [row for row in findings if row["domain"] == "processing"]
    return dict(schema_version=1, source=SOURCE, reviewed_code_sha=report.get("code_sha"), phase=mode, requested_phase=phase,
                discovery_qa="FAIL" if discovery_failures else "PASS",
                processing_qa=("FAIL" if processing_failures or discovery_failures else "PASS") if processing else "NOT_RUN",
                verdict="FAIL" if findings else "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW" if processing else "PASS_DISCOVERY_ONLY_NOT_END_TO_END_ACCEPTANCE",
                acceptance="NOT_ACCEPTED" if findings or not processing else "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW",
                findings=findings, checks=checks,
                limitations=["Frozen 29/79 controls benchmark recall; they are not a publication quota or proof of every publisher article.",
                             "An automated PASS cannot settle semantic editorial correctness, final staging QA, or close issues/PR acceptance."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, default=Path("data/audits/pulso_runtime_2026_10_11.json"))
    parser.add_argument("--control", type=Path, default=Path("data/audits/pulso_external_control_2026_10_11.json"))
    parser.add_argument("--output", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--discovery", action="store_true", help="Check discovery only; never infer end-to-end acceptance")
    modes.add_argument("--processing", action="store_true", help="Require a genuine processing execution and editorial outcomes")
    parser.add_argument("--capture-artifact", type=Path, default=Path(".scratch/pulso-prior-capture"))
    args = parser.parse_args()
    root = args.root.resolve()
    def path(value):
        return value if value.is_absolute() else root / value
    def read(value):
        return json.loads(path(Path(value)).read_text())
    try:
        report, control = read(args.report), read(args.control)
        history = read("data/history/superintendencia_signals.json")
        history = history.get("signals", []) if isinstance(history, dict) else history
        telemetry_path = root / "data/ai_usage/responses.jsonl"
        telemetry = [json.loads(line) for line in telemetry_path.read_text().splitlines() if line.strip()] if telemetry_path.exists() else []
        result = evaluate(report, control, root=root, discovery=read("data/state/discovery_run.json"),
                          queue=read("data/state/pending_queue.json"), history=history,
                          snapshot=read("web/data/radar_today.json"), telemetry=telemetry,
                          control_sha=digest(path(args.control).read_bytes()),
                          captures=capture_records(root, path(args.capture_artifact)),
                          phase="processing" if args.processing else "discovery" if args.discovery else "auto")
        if not args.discovery and (report.get("last_core_execution") or report.get("execution", {})).get("mode") == "real_core_processing":
            if report.get("feed_evidence", {}).get("sha256") != digest((root / "web/data/radar_today.json").read_bytes()):
                result["findings"].append(dict(domain="processing", code="serialized_feed_hash_changed_after_audit"))
                result.update(processing_qa="FAIL", verdict="FAIL", acceptance="NOT_ACCEPTED")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        result = dict(discovery_qa="FAIL", processing_qa="NOT_RUN", verdict="FAIL", acceptance="NOT_ACCEPTED",
                      findings=[dict(domain="evidence", code="required_evidence_unreadable", error=type(error).__name__ + ":" + str(error))])
    if args.output:
        destination = path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["verdict"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
