"""Audit every retained original response offline, never invent primary body text.

Reads an already authorized Actions capture artifact. Does not fetch URLs, run
discovery, change queue/history/budgets or invoke analysis. Full health bodies are
projected only from hash-verified original HTML; thin originals survive rejection.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from radar_salud.beta_sources import _material
from radar_salud.pulso_source import _Article, _nodes, _visible_byline_day, extract_article, health_anchor, publication_day

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "pulso_latercera"
SHA = re.compile(r"[0-9a-f]{64}")
CLINICAL = re.compile(r"salud|sanitari|m[eé]dic|hospital|cl[ií]nic|fonasa|isapre|"
                      r"psiquiatr|psicol[oó]g|trastorno obsesivo|\bTOC\b|pacientes?|terap[eé]ut|"
                      r"oncolog|c[aá]ncer|demencia|alzheimer|sarcopenia|vacun|epidemi", re.I)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def normalized_url(value, base="https://www.latercera.com/"):
    parsed = urlsplit(urljoin(base, value or ""))
    if parsed.scheme != "https" or parsed.netloc not in {"www.latercera.com", "latercera.com"}:
        return None
    return urlunsplit(("https", "www.latercera.com", parsed.path.rstrip("/") + "/", "", ""))


def safe_file(base, relative):
    relative = Path(relative or "")
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("unsafe_capture_path")
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError("unsafe_capture_path")
    return path


def verify_original(base, record):
    if not SHA.fullmatch(str(record.get("sha256", ""))):
        raise ValueError("invalid_original_sha256")
    compressed = safe_file(base, record.get("gzip_file")).read_bytes()
    if digest(compressed) != record.get("gzip_sha256"):
        raise ValueError("gzip_sha256_mismatch")
    payload = gzip.decompress(compressed)
    if digest(payload) != record["sha256"] or len(payload) != record.get("bytes"):
        raise ValueError("original_bytes_hash_or_size_mismatch")
    text = payload.decode(record.get("charset") or "utf-8", errors="replace")
    if record.get("returned_text_utf8_sha256") and digest(text.encode()) != record["returned_text_utf8_sha256"]:
        raise ValueError("returned_text_sha256_mismatch")
    return compressed, payload, text


def manifests(artifact, explicit=None):
    paths = [explicit] if explicit is not None and explicit.exists() else []
    if artifact.exists():
        paths.extend(sorted(artifact.rglob("manifest.json")))
    result = []
    seen = set()
    for path in paths:
        if path.resolve() in seen:
            continue
        seen.add(path.resolve())
        if path != explicit and not path.resolve().is_relative_to(artifact.resolve()):
            raise ValueError("unsafe_artifact_manifest_path")
        payload = path.read_bytes()
        value = json.loads(payload)
        if (value.get("source") == SOURCE and value.get("mode") == "actual_core_http_observation_no_inventory_injection"
                and isinstance(value.get("requests"), list)):
            result.append((path.parent, digest(payload), value["requests"]))
    return result


def discovery_snapshots(artifact, explicit=None):
    paths = [explicit] if explicit is not None and explicit.exists() else []
    if artifact.exists():
        paths.extend(sorted(artifact.rglob("discovery_run.json")))
    snapshots = []
    seen = set()
    for path in paths:
        if path.resolve() in seen:
            continue
        seen.add(path.resolve())
        if path != explicit and not path.resolve().is_relative_to(artifact.resolve()):
            raise ValueError("unsafe_artifact_discovery_path")
        payload = path.read_bytes()
        value = json.loads(payload)
        if SOURCE in value.get("source_details", {}):
            snapshots.append((value.get("at") or "", digest(payload), value))
    return snapshots


def discovery_snapshot(artifact, explicit=None):
    snapshots = discovery_snapshots(artifact, explicit)
    return max(snapshots, key=lambda row: row[0]) if snapshots else (None, None, {})


def primary_projection(text, url):
    """Keep URL-bound text even when the production parser's length gate fails."""
    expected = normalized_url(url)
    parser = _Article()
    parser.feed(text)
    nodes, videos = [], []
    for script in parser.scripts:
        try:
            for node in _nodes(json.loads(script)):
                kinds = node.get("@type")
                kinds = kinds if isinstance(kinds, list) else [kinds]
                link = node.get("url") or node.get("mainEntityOfPage") or node.get("@id")
                if isinstance(link, dict):
                    link = link.get("@id")
                if link and normalized_url(link, url) == expected:
                    if any(kind in {"NewsArticle", "Article", "ReportageNewsArticle"} for kind in kinds):
                        nodes.append(node)
                    if "VideoObject" in kinds:
                        videos.append(node)
        except (ValueError, TypeError):
            continue
    node = nodes[0] if len(nodes) == 1 else {}
    title = " ".join((node.get("headline") or " ".join(parser.headline) or parser.metas.get("og:title", "")).split())
    if isinstance(node.get("articleBody"), str):
        body = " ".join(node["articleBody"].split())
        body_source = "url_bound_json_ld_articleBody"
    else:
        body = " ".join(parser.body or parser.paragraphs)
        body_source = "article_html" if body else "primary_text_missing_in_original"
    visible_error = None
    try:
        visible = _visible_byline_day(parser.byline_dates)
    except ValueError as error:
        visible, visible_error = None, str(error)
    timestamps = [("json_ld_datePublished", node.get("datePublished")),
                  ("article_published_time", parser.metas.get("article:published_time"))]
    timestamps.extend(("article_time", value) for value in parser.times)
    result = {"title": title, "title_chars": len(title), "canonical": parser.canonical,
              "canonical_matches_requested": normalized_url(parser.canonical) == expected,
              "url_bound_article_nodes": len(nodes), "section": node.get("articleSection") or parser.metas.get("article:section"),
              "url_bound_video_objects": len(videos),
              "url_bound_video_evidence": [{key: video.get(key) for key in (
                  "@type", "@id", "url", "mainEntityOfPage", "name", "description", "uploadDate", "embedUrl")}
                  for video in videos],
              "visible_byline_text": " ".join(parser.byline_dates), "visible_byline_day": visible,
              "visible_byline_error": visible_error,
              "publication_evidence": [{"source": kind, "timestamp": value, "timestamp_calendar_day": publication_day(value)}
                                       for kind, value in timestamps if value],
              "primary_body_source": body_source, "primary_body_chars": len(body), "primary_body_sha256": digest(body.encode()),
              "primary_body_available": bool(body), "primary_body_below_160": len(body) < 160,
              "title_below_18": len(title) < 18,
              "original_metadata_description": node.get("description") or parser.metas.get("og:description"),
              "keywords": node.get("keywords", []), "full_primary_body": body}
    try:
        parsed_title, parsed_body, metadata = extract_article(text, url)
        result["current_parser"] = {"status": "verified", "title": parsed_title,
                                    "body_chars": len(parsed_body), "metadata": metadata,
                                    "body_matches_original_projection": parsed_body == body}
    except Exception as error:
        result["current_parser"] = {"status": "error", "error_type": type(error).__name__, "reason": str(error)}
    combined = title + " " + body + " " + str(result["keywords"]) + " " + str(result["original_metadata_description"] or "")
    result["health_anchor_current_source"] = health_anchor(combined)
    result["health_anchor_broad_clinical_audit"] = bool(CLINICAL.search(combined))
    result["health_related_original"] = result["health_anchor_current_source"] or result["health_anchor_broad_clinical_audit"]
    result["materiality_prefilter_observations"] = {"full_primary_body": _material("media", title, body),
                                                   "body_first_5500": _material("media", title, body[:5500]),
                                                   "body_first_18000": _material("media", title, body[:18000])}
    result["body_complete_as_original"] = bool(body and len(nodes) == 1 and result["canonical_matches_requested"])
    if not result["canonical_matches_requested"] or len(nodes) != 1:
        diagnosis = "unbound_or_ambiguous_primary_document_requires_investigation"
    elif len(title) < 18 and len(body) >= 160:
        diagnosis = ("url_bound_complete_primary_body_with_short_headline" if result["current_parser"]["status"] == "verified"
                     else "url_bound_complete_primary_body_rejected_by_short_headline_length_gate")
    elif len(body) < 160 and urlsplit(url).path.startswith("/videos/"):
        diagnosis = "publisher_video_route_with_primary_article_text_below_160"
    elif len(body) < 160:
        diagnosis = "url_bound_primary_article_text_below_160"
    else:
        diagnosis = "primary_title_and_body_above_existing_minimums"
    result["primary_document_diagnosis"] = diagnosis
    return result


def exceptional_categories(row, window):
    """Observed taxonomy and parser evidence select retention, never adoption."""
    observed_day = row.get("visible_byline_day") or row.get("current_parser", {}).get("metadata", {}).get("publication_date")
    if (not window or not observed_day or not window["start"] <= observed_day <= window["end"]
            or not row.get("canonical_matches_requested")):
        return []
    video_category = ["url_bound_primary_video_object"] if row.get("url_bound_video_objects", 0) else []
    # Standalone VideoObject documents are still primary video evidence. They
    # cannot supply an Article body or authorize a factual date exception.
    if row.get("url_bound_article_nodes") != 1:
        return video_category
    categories = []
    native_days, chile_days = [], []
    for evidence in row.get("publication_evidence", []):
        value = evidence.get("timestamp") or ""
        try:
            if len(value) == 10:
                native = chile = datetime.fromisoformat(value).date().isoformat()
            else:
                stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    continue
                native = stamp.date().isoformat()
                chile = stamp.astimezone(ZoneInfo("America/Santiago")).date().isoformat()
            native_days.append(native)
            chile_days.append(chile)
        except (ValueError, TypeError):
            continue
    byline_conflict = bool(row.get("visible_byline_day") and native_days
                          and set(native_days) != {row["visible_byline_day"]}
                          and set(chile_days) != {row["visible_byline_day"]})
    parser = row.get("current_parser", {})
    reason = parser.get("reason") or parser.get("metadata", {}).get("publisher_exception_reason")
    if byline_conflict or reason in {"conflicting_publication_dates", "publisher_conflicting_publication_dates"}:
        categories.append("observed_primary_publication_date_conflict")
    keywords = row.get("keywords")
    keywords = keywords if isinstance(keywords, list) else [keywords]
    if any(str(value).strip().casefold() in {"opinión", "opinion", "columna"} for value in keywords):
        categories.append("explicit_opinion_or_column_keyword_under_article_path")
    if str(row.get("section", "")).strip().casefold() in {"branded", "publirreportajes"}:
        categories.append("explicit_commercial_publisher_section")
    return categories + video_category


def retain_editorial_exceptions(originals, output, window, discovery_hash, discovered_at, observed_traces=()):
    output.mkdir(parents=True, exist_ok=True)
    retained = []
    conflict_observations = {}
    for trace in observed_traces:
        if (trace.get("publisher_exception_reason") != "publisher_conflicting_publication_dates"
                and trace.get("reason") != "publisher_conflicting_publication_dates"):
            continue
        url = normalized_url(trace.get("url"))
        if url is not None:
            observation = {key: trace.get(key) for key in ("status", "reason", "publisher_exception_reason",
                "possible_publication_days", "publication_date", "publication_date_verified", "visible_publication_date",
                "publication_evidence", "html_sha256", "captured_at", "cache_hit", "publisher_lastmod")}
            conflict_observations.setdefault(url, []).append(observation)
    for url, candidates in sorted(originals.items()):
        eligible = []
        for row, compressed, body in candidates:
            categories = exceptional_categories(row, window)
            if url in conflict_observations:
                # Retain explicitly observed old date conflicts as exclusion
                # evidence too. Raw identity/date disagreement still has to
                # verify; a source trace alone cannot fabricate an original.
                outside_categories = exceptional_categories(row, {"start": "0001-01-01", "end": "9999-12-31"})
                if ("observed_primary_publication_date_conflict" in outside_categories
                        and "observed_primary_publication_date_conflict" not in categories):
                    categories = ["observed_primary_publication_date_conflict"] + categories
            eligible.append((row, compressed, body, categories))
        eligible = [item for item in eligible if item[3]]
        if not eligible:
            continue
        row, compressed, body, categories = max(eligible, key=lambda item: item[0].get("captured_at") or "")
        video = "url_bound_primary_video_object" in categories
        relative = (Path("video") if video else Path(".")) / (row["sha256"] + ".html.gz")
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(compressed)
        retained.append(dict(row, gzip_file=str(relative), full_primary_body=body, retention_categories=categories,
                             observed_current_discovery_date_conflict=conflict_observations.get(url, []),
                             original_visible_byline_outside_complete_90_window=bool(window and row.get("visible_byline_day") and
                                 not window["start"] <= row["visible_byline_day"] <= window["end"]),
                             capture_provenance="preserved_original_cold_core_editorial_or_video_exception",
                             fixture_status="hash_verified_original_retained_without_date_or_editorial_adoption"))
    retained_conflicts = {row["url"] for row in retained if "observed_primary_publication_date_conflict" in row["retention_categories"]}
    targets = [{"url": url, "source_observations": observations,
                "fixture_status": "hash_verified_original_conflict_retained" if url in retained_conflicts else "missing_hash_verified_original_conflict"}
               for url, observations in sorted(conflict_observations.items())]
    missing_conflicts = [target["url"] for target in targets if target["fixture_status"] != "hash_verified_original_conflict_retained"]
    result = {"schema_version": "1.0", "source": SOURCE,
              "mode": "offline_original_editorial_and_video_exception_retention_no_inventory_injection",
              "window_90": window, "discovery_at": discovered_at, "discovery_run_sha256": discovery_hash,
              "requests": retained, "unique_urls": len(retained),
              "observed_current_discovery_date_conflict_targets": targets,
              "missing_observed_current_discovery_date_conflict_originals": missing_conflicts,
              "category_counts": dict(Counter(category for row in retained for category in row["retention_categories"])),
              "status": "OBSERVED_EXCEPTION_ORIGINAL_RETENTION_PARTIAL" if missing_conflicts else (
                  "OBSERVED_EXCEPTION_ORIGINALS_RETAINED_NOT_SOURCE_ACCEPTANCE" if retained else "EXCEPTION_ORIGINALS_NOT_AVAILABLE"),
              "selection_policy": "Hash-verified URL-bound originals in the observed visible-byline calendar window: ALL primary publisher date conflicts regardless of topic, EXACT Opinión/Opinion/Columna keywords, EXACT Branded/Publirreportajes sections, and ALL URL-bound VideoObject primary documents. Also retain ALL date-conflict URLs explicitly observed in the current source traces, including old excluded documents, only after original identity/date disagreement verifies. Dates remain observations; neither article paths nor retention grant editorial acceptance."}
    (output / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def audit(artifact, output, thin_output, discovery=None, capture_manifest=None, exception_output=None):
    source_manifests = manifests(artifact, capture_manifest)
    snapshots = discovery_snapshots(artifact, discovery)
    discovered_at, discovery_hash, snapshot = max(snapshots, key=lambda row: row[0]) if snapshots else (None, None, {})
    # A successful later parser must not erase the historical cold originals
    # selected by earlier incomplete-detail observations.
    traces = [trace for _, _, observed in snapshots for trace in observed.get("source_details", {}).get(SOURCE, [])]
    thin_urls = {normalized_url(row.get("url")) for row in traces if row.get("status") == "detail_error"
                 and row.get("reason") == "incomplete_article_evidence"}
    thin_urls.discard(None)
    window = None
    if discovered_at:
        day = datetime.fromisoformat(discovered_at.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Santiago")).date()
        window = {"start": (day-timedelta(days=90)).isoformat(), "end": (day-timedelta(days=1)).isoformat()}
    rows, originals, health = [], {}, []
    seen = set()
    raw_counts = Counter()
    for base, manifest_hash, records in source_manifests:
        for record in records:
            raw_counts["observed_http_records"] += 1
            if not record.get("gzip_file"):
                raw_counts["metadata_only_no_retained_original"] += 1
                continue
            key = (record.get("url"), record.get("sha256"))
            if key in seen:
                raw_counts["duplicate_original_identity"] += 1
                continue
            seen.add(key)
            row = {key: record.get(key) for key in ("url", "status", "captured_at", "sha256", "gzip_sha256", "bytes",
                                                  "charset", "returned_text_utf8_sha256", "content_type", "primary_article_error")}
            row["original_capture_manifest_sha256"] = manifest_hash
            row["original_capture_gzip_file"] = record["gzip_file"]
            try:
                compressed, payload, text = verify_original(base, record)
                row["original_bytes_verified"] = True
                content_type = record.get("content_type", "")
                html = "html" in content_type or bool(re.match(r"\s*(?:<!doctype\s+html|<html)\b", text, re.I))
                row["response_kind"] = "html" if html else "non_html_original"
                raw_counts[row["response_kind"]] += 1
                if html:
                    # Every retained HTML is parsed, including listing/challenge
                    # documents. Such pages cannot supply a factual primary body.
                    projection = primary_projection(text, record["url"])
                    factual_path = bool(re.search(r"/[^/]+/noticia/", urlsplit(record["url"]).path))
                    row.update({key: value for key, value in projection.items() if key != "full_primary_body"})
                    row["original_article_path"] = factual_path
                    if factual_path:
                        originals.setdefault(normalized_url(record["url"]), []).append((row, compressed, projection["full_primary_body"]))
                    if factual_path and projection["health_related_original"]:
                        health.append(dict(row, full_primary_body=projection["full_primary_body"],
                                           evidence_maturity="media_reported", analysis_performed=False))
            except Exception as error:
                row.update(original_bytes_verified=False, error_type=type(error).__name__, reason=str(error))
                raw_counts["original_verification_errors"] += 1
            rows.append(row)
    thin_output.mkdir(parents=True, exist_ok=True)
    thin_rows = []
    for url in sorted(thin_urls):
        candidates = sorted(originals.get(url, []), key=lambda item: item[0].get("captured_at") or "", reverse=True)
        if not candidates:
            thin_rows.append({"url": url, "fixture_status": "missing_hash_verified_original",
                              "cold_discovery_reason": "incomplete_article_evidence"})
            continue
        row, compressed, body = candidates[0]
        relative = row["sha256"] + ".html.gz"
        (thin_output / relative).write_bytes(compressed)
        thin_rows.append(dict(row, gzip_file=relative, fixture_status="original_retained_even_if_current_parser_rejects",
                              capture_provenance="preserved_original_cold_core_incomplete_detail",
                              cold_discovery_reason="incomplete_article_evidence", full_primary_body=body))
    thin_manifest = {"schema_version": "1.0", "source": SOURCE,
                     "mode": "exact_offline_retention_of_all_cold_incomplete_detail_originals_no_inventory_injection",
                     "discovery_run_sha256": discovery_hash, "discovery_at": discovered_at,
                     "observed_discovery_run_sha256s": sorted({digest for _, digest, _ in snapshots}),
                     "expected_unique_incomplete_urls": len(thin_urls), "requests": thin_rows,
                     "status": "ALL_COLD_THIN_ORIGINALS_RETAINED_NOT_SOURCE_ACCEPTANCE" if thin_urls and all(
                         row.get("original_bytes_verified") for row in thin_rows) else "THIN_ORIGINAL_RETENTION_PARTIAL"}
    (thin_output / "manifest.json").write_text(json.dumps(thin_manifest, ensure_ascii=False, indent=2) + "\n")
    exception_manifest = retain_editorial_exceptions(originals, exception_output, window, discovery_hash, discovered_at,
        snapshot.get("source_details", {}).get(SOURCE, [])) if exception_output is not None else None
    report = {"schema_version": "1.0", "source": SOURCE,
              "mode": "complete_offline_audit_of_retained_original_response_corpus_without_analysis_or_inventory_injection",
              "generated_at": datetime.now(timezone.utc).isoformat(), "network_requests": 0, "ai_calls": 0,
              "discovery_at": discovered_at, "discovery_run_sha256": discovery_hash,
              "observed_discovery_run_sha256s": sorted({digest for _, digest, _ in snapshots}),
              "capture_manifest_sha256s": [manifest_hash for _, manifest_hash, _ in source_manifests],
              "status": "ALL_RETAINED_ORIGINALS_AUDITED_NOT_SOURCE_ACCEPTANCE" if source_manifests and not raw_counts["original_verification_errors"] else "PRIMARY_CORPUS_AUDIT_PARTIAL",
              "counts": dict(raw_counts, audited_retained_original_identities=len(rows),
                             health_originals=len(health), health_unique_urls=len({row["url"] for row in health})),
              "original_response_audit": rows, "all_health_originals_with_full_body": health,
              "thin_originals": thin_manifest,
              "editorial_and_video_exception_originals": exception_manifest,
              "method": "Every gzip_file in every actual core capture manifest is checked against compressed SHA, original bytes SHA/size and returned UTF8 SHA; every retained HTML is parsed without a title filter. Full bodies are copied only from verified original HTML. Metadata-only records never fabricate bodies. _material is observed, never used to publish."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-artifact", type=Path, default=ROOT / ".scratch/pulso-prior-capture")
    parser.add_argument("--capture-manifest", type=Path)
    parser.add_argument("--discovery", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/audits/pulso_primary_corpus_2026_10_11.json")
    parser.add_argument("--thin-output", type=Path, default=ROOT / "tests/fixtures/pulso_thin_primary_real")
    parser.add_argument("--exception-output", type=Path, default=ROOT / "tests/fixtures/pulso_editorial_exception_real")
    args = parser.parse_args()
    report = audit(args.capture_artifact, args.output, args.thin_output, args.discovery, args.capture_manifest, args.exception_output)
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "thin_status": report["thin_originals"]["status"], "network_requests": 0, "ai_calls": 0}))


if __name__ == "__main__":
    main()
