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
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

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


def discovery_snapshot(artifact, explicit=None):
    paths = [explicit] if explicit is not None and explicit.exists() else []
    if artifact.exists():
        paths.extend(sorted(artifact.rglob("discovery_run.json")))
    snapshots = []
    for path in paths:
        if path != explicit and not path.resolve().is_relative_to(artifact.resolve()):
            raise ValueError("unsafe_artifact_discovery_path")
        payload = path.read_bytes()
        value = json.loads(payload)
        if SOURCE in value.get("source_details", {}):
            snapshots.append((value.get("at") or "", digest(payload), value))
    return max(snapshots, key=lambda row: row[0]) if snapshots else (None, None, {})


def primary_projection(text, url):
    """Keep URL-bound text even when the production parser's length gate fails."""
    expected = normalized_url(url)
    parser = _Article()
    parser.feed(text)
    nodes = []
    for script in parser.scripts:
        try:
            for node in _nodes(json.loads(script)):
                kinds = node.get("@type")
                kinds = kinds if isinstance(kinds, list) else [kinds]
                link = node.get("url") or node.get("mainEntityOfPage") or node.get("@id")
                if isinstance(link, dict):
                    link = link.get("@id")
                if any(kind in {"NewsArticle", "Article"} for kind in kinds) and link and normalized_url(link, url) == expected:
                    nodes.append(node)
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
        diagnosis = "url_bound_complete_primary_body_rejected_by_short_headline_length_gate"
    elif len(body) < 160 and urlsplit(url).path.startswith("/videos/"):
        diagnosis = "publisher_video_route_with_primary_article_text_below_160"
    elif len(body) < 160:
        diagnosis = "url_bound_primary_article_text_below_160"
    else:
        diagnosis = "primary_title_and_body_above_existing_minimums"
    result["primary_document_diagnosis"] = diagnosis
    return result


def audit(artifact, output, thin_output, discovery=None, capture_manifest=None):
    source_manifests = manifests(artifact, capture_manifest)
    discovered_at, discovery_hash, snapshot = discovery_snapshot(artifact, discovery)
    traces = snapshot.get("source_details", {}).get(SOURCE, [])
    thin_urls = {normalized_url(row.get("url")) for row in traces if row.get("status") == "detail_error"
                 and row.get("reason") == "incomplete_article_evidence"}
    thin_urls.discard(None)
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
                     "expected_unique_incomplete_urls": len(thin_urls), "requests": thin_rows,
                     "status": "ALL_COLD_THIN_ORIGINALS_RETAINED_NOT_SOURCE_ACCEPTANCE" if thin_urls and all(
                         row.get("original_bytes_verified") for row in thin_rows) else "THIN_ORIGINAL_RETENTION_PARTIAL"}
    (thin_output / "manifest.json").write_text(json.dumps(thin_manifest, ensure_ascii=False, indent=2) + "\n")
    report = {"schema_version": "1.0", "source": SOURCE,
              "mode": "complete_offline_audit_of_retained_original_response_corpus_without_analysis_or_inventory_injection",
              "generated_at": datetime.now(timezone.utc).isoformat(), "network_requests": 0, "ai_calls": 0,
              "discovery_at": discovered_at, "discovery_run_sha256": discovery_hash,
              "capture_manifest_sha256s": [manifest_hash for _, manifest_hash, _ in source_manifests],
              "status": "ALL_RETAINED_ORIGINALS_AUDITED_NOT_SOURCE_ACCEPTANCE" if source_manifests and not raw_counts["original_verification_errors"] else "PRIMARY_CORPUS_AUDIT_PARTIAL",
              "counts": dict(raw_counts, audited_retained_original_identities=len(rows),
                             health_originals=len(health), health_unique_urls=len({row["url"] for row in health})),
              "original_response_audit": rows, "all_health_originals_with_full_body": health,
              "thin_originals": thin_manifest,
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
    args = parser.parse_args()
    report = audit(args.capture_artifact, args.output, args.thin_output, args.discovery, args.capture_manifest)
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "thin_status": report["thin_originals"]["status"], "network_requests": 0, "ai_calls": 0}))


if __name__ == "__main__":
    main()
