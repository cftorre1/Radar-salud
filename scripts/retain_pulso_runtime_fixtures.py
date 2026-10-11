"""Preserve exact observed publisher bytes; controls select retention, never discovery.

Can read a downloaded Actions artifact without restoring its queue, cache, history
or ledgers. Missing controls and invalid hashes remain explicit in the manifest.
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
from urllib.parse import parse_qs, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from radar_salud.pulso_source import extract_article

SOURCE = "pulso_latercera"
ROOT = Path(__file__).resolve().parents[1]


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def normalized_url(value):
    parsed = urlsplit(value or "")
    if parsed.scheme != "https" or parsed.netloc not in {"www.latercera.com", "latercera.com"}:
        return None
    return urlunsplit(("https", "www.latercera.com", parsed.path.rstrip("/") + "/", "", ""))


def safe_file(base, relative):
    relative = Path(relative or "")
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("unsafe_capture_path")
    resolved = (base / relative).resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError("unsafe_capture_path")
    return resolved


def verify_original(base, record):
    """Check both the verbatim gzip and original response hashes before copying."""
    if not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")):
        raise ValueError("invalid_original_sha256")
    compressed = safe_file(base, record.get("gzip_file")).read_bytes()
    if sha256(compressed) != record.get("gzip_sha256"):
        raise ValueError("gzip_sha256_mismatch")
    payload = gzip.decompress(compressed)
    if sha256(payload) != record["sha256"]:
        raise ValueError("original_sha256_mismatch")
    if len(payload) != record.get("bytes"):
        raise ValueError("original_size_mismatch")
    text = payload.decode(record.get("charset") or "utf-8", errors="replace")
    if record.get("returned_text_utf8_sha256") and sha256(text.encode()) != record["returned_text_utf8_sha256"]:
        raise ValueError("returned_text_sha256_mismatch")
    return compressed, text


def capture_manifests(capture_manifest, artifact_dir=None):
    paths = [capture_manifest] if capture_manifest.exists() else []
    if artifact_dir is not None and artifact_dir.exists():
        paths.extend(sorted(artifact_dir.rglob("manifest.json")))
    result = []
    for path in paths:
        if artifact_dir is not None and path != capture_manifest and not path.resolve().is_relative_to(artifact_dir.resolve()):
            raise ValueError("unsafe_artifact_manifest_path")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("source") == SOURCE and isinstance(manifest.get("requests"), list):
            result.append((path.parent, sha256(path.read_bytes()), manifest["requests"]))
    return result


def api_page_key(url):
    """Identify an observed publisher request, keeping query and cursor intact."""
    try:
        parsed = urlsplit(url or "")
        if parsed.scheme != "https" or parsed.netloc != "www.latercera.com":
            return None
        query = json.loads(parse_qs(parsed.query)["query"][0])
        if parsed.path == "/pf/api/v3/content/fetch/story-feed-sections-fetch":
            feed = "section:" + query["includeSections"].lstrip("/")
        elif parsed.path == "/pf/api/v3/content/fetch/story-feed-tag-fetch":
            feed = "tag:" + query["tagSlug"]
        else:
            return None
        offset = query["feedOffset"]
        return (feed, offset) if type(offset) is int and offset >= 0 else None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def api_inventory_day(value):
    """Match the API traversal calendar; never establish a final article date."""
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).date().isoformat()
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(ZoneInfo("America/Santiago")).date().isoformat()
    except (ValueError, TypeError, AttributeError):
        return None


def discovery_evidence(discovery_path, artifact_dir=None):
    paths = [discovery_path] if discovery_path is not None and discovery_path.exists() else []
    if artifact_dir is not None and artifact_dir.exists():
        paths.extend(sorted(artifact_dir.rglob("discovery_run.json")))
    candidates = []
    for path in paths:
        if artifact_dir is not None and path != discovery_path and not path.resolve().is_relative_to(artifact_dir.resolve()):
            raise ValueError("unsafe_artifact_discovery_path")
        payload = path.read_bytes()
        value = json.loads(payload)
        details = value.get("source_details", {}).get(SOURCE, [])
        if any(row.get("status") in {"public_feed_page", "discovered_metadata_only"} for row in details):
            candidates.append((value.get("at") or "", sha256(payload), details))
    return max(candidates, key=lambda row: row[0]) if candidates else None


def preserve_api_proof(sources, evidence, output, requests):
    """Retain first/last-three JSON originals and all observed HTTP chain hashes."""
    if evidence is None:
        return {"status": "PUBLIC_API_PROOF_NOT_AVAILABLE", "feeds": [], "required_feeds": []}
    discovery_at, discovery_hash, details = evidence
    runtime = next((row for row in reversed(details) if row.get("status") == "runtime_coverage"), {})
    required = runtime.get("required_feeds", [])
    summaries = {row["feed"]: row for row in details if row.get("status") == "public_feed_coverage"}
    candidates = {}
    for base, manifest_hash, records in sources:
        for record in records:
            key = api_page_key(record.get("url"))
            if key:
                candidates.setdefault(key, []).append((base, manifest_hash, record))
    feeds = []
    for feed in sorted(set(required) | set(summaries)):
        pages = [row for row in details if row.get("status") == "public_feed_page" and row.get("feed") == feed]
        proof_offsets = {row.get("offset") for row in pages[:1] + pages[-3:]}
        chain = []
        for index, page in enumerate(pages):
            linked = [candidate for candidate in candidates.get((feed, page.get("offset")), [])
                      if candidate[2].get("status") == 200 and candidate[2].get("captured_at")
                      and re.fullmatch(r"[0-9a-f]{64}", page.get("json_sha256", ""))
                      and page.get("json_sha256") in {candidate[2].get("sha256"), candidate[2].get("returned_text_utf8_sha256")}
                      and re.fullmatch(r"[0-9a-f]{64}", candidate[2].get("sha256", ""))]
            linked.sort(key=lambda candidate: candidate[2].get("captured_at") or "", reverse=True)
            item = dict(page, proof_status="missing_observed_http_response",
                        cursor_links_previous=(index == 0 and page.get("offset") == 0) or
                            (index > 0 and pages[index-1].get("next") == page.get("offset") and
                             page.get("offset", -1) > pages[index-1].get("offset", -1)),
                        raw_payload_required=page.get("offset") in proof_offsets)
            errors = []
            for base, manifest_hash, record in linked:
                compact = {key: record.get(key) for key in (
                    "url", "requested_at", "captured_at", "status", "final_url", "content_type", "charset",
                    "bytes", "sha256", "returned_text_utf8_sha256", "gzip_sha256")}
                compact.update(feed=feed, offset=page["offset"], next=page.get("next"),
                               json_sha256=page.get("json_sha256"), gzip_file=None,
                               capture_provenance="observed_public_api_http_chain_metadata",
                               raw_payload_retained=False,
                               original_gzip_file=record.get("original_gzip_file", record.get("gzip_file")),
                               original_capture_manifest_sha256=record.get("original_capture_manifest_sha256", manifest_hash))
                if not item["raw_payload_required"]:
                    requests[(compact["url"], compact["sha256"])] = compact
                    item.update(proof_status="observed_http_sha_bound", http=compact)
                    break
                try:
                    compressed, text = verify_original(base, record)
                    document = json.loads(text)
                    document = document.get("data", document)
                    nodes = document["content_elements"]
                    if (not isinstance(nodes, list) or len(nodes) != page.get("primary_entries")
                            or document.get("count") != page.get("count") or document.get("next") != page.get("next")):
                        raise ValueError("original_api_inventory_or_cursor_mismatch")
                    timestamps = [node.get("first_publish_date") for node in nodes]
                    days = [api_inventory_day(value or "") for value in timestamps]
                    if page.get("inventory_day_max") and (None in days or max(days) != page["inventory_day_max"]):
                        raise ValueError("original_api_publication_boundary_mismatch")
                    if page.get("inventory_day_min") and (None in days or min(days) != page["inventory_day_min"]):
                        raise ValueError("original_api_publication_boundary_mismatch")
                    relative = compact["sha256"] + ".json.gz"
                    destination = output / relative
                    if destination.exists() and sha256(destination.read_bytes()) != compact["gzip_sha256"]:
                        raise ValueError("existing_fixture_gzip_sha256_mismatch")
                    destination.write_bytes(compressed)
                    compact.update(gzip_file=relative, raw_payload_retained=True,
                                   capture_provenance="preserved_original_public_api_response")
                    requests[(compact["url"], compact["sha256"])] = compact
                    item.update(proof_status="verified_original_boundary_json", http=compact,
                                inventory_calendar="America/Santiago",
                                original_first_publish_timestamps=timestamps,
                                original_inventory_days_santiago=days)
                    break
                except Exception as error:
                    errors.append({"error_type": type(error).__name__, "reason": str(error),
                                   "captured_at": record.get("captured_at"), "sha256": record.get("sha256")})
            if errors:
                item["original_verification_errors"] = errors
            chain.append(item)
        summary = summaries.get(feed, {})
        complete = (bool(chain) and len(chain) == summary.get("pages_attempted")
                    and all(row["cursor_links_previous"] and row["proof_status"] in {
                        "observed_http_sha_bound", "verified_original_boundary_json"} for row in chain))
        feeds.append({"feed": feed, "summary": summary, "http_and_boundary_proof_complete": complete,
                      "proof_payload_offsets": sorted(proof_offsets), "pages": chain})
    chain_bytes = json.dumps([row.get("http") for feed in feeds for row in feed["pages"]],
                            sort_keys=True, separators=(",", ":")).encode()
    complete = bool(required and len(feeds) == len(required) and all(feed["http_and_boundary_proof_complete"] for feed in feeds))
    return {"status": "PUBLIC_API_HTTP_AND_BOUNDARY_PROOF_AVAILABLE_NOT_SOURCE_ACCEPTANCE" if complete else "PUBLIC_API_PROOF_PARTIAL",
            "discovery_at": discovery_at, "discovery_run_sha256": discovery_hash,
            "required_feeds": required, "runtime_coverage": runtime,
            "inventory_calendar": "America/Santiago for API first_publish_date traversal only; final article dates require original primary byline corroboration",
            "http_chain_sha256": sha256(chain_bytes), "feeds": feeds,
            "raw_payload_retention": "Exact observed first and last three API responses per feed; interior pages retain observed HTTP metadata only."}


def preserve_paid_originals(sources, pins_path, queue_path, output, requests):
    """Retain bounded paid input originals, without reopening or restoring rows.

    The fixed producer pins select retention only. Current queue primary text,
    exact original HTTP provenance and parser replay must all agree before an
    original can become a witness. A newer same-URL response is insufficient.
    """
    if pins_path is None:
        return {"status": "PAID_ORIGINAL_RETENTION_NOT_REQUESTED", "rows": []}
    pin_bytes = pins_path.read_bytes()
    pins = json.loads(pin_bytes)
    articles = pins.get("articles", [])
    urls = [row.get("url") for row in articles]
    if (pins.get("schema") != "pulso_v5_paid_missing_original_retention_pins_v1"
            or pins.get("source") != SOURCE or not articles
            or pins.get("required_original_count") != len(articles)
            or len(set(urls)) != len(urls)
            or any(normalized_url(url) != url for url in urls)):
        raise ValueError("invalid_paid_original_retention_pins")
    expected_manifest = pins["original_capture"]["source_manifest_sha256"]
    try:
        queue_bytes = queue_path.read_bytes()
        queue = json.loads(queue_bytes)
        if not isinstance(queue, dict):
            raise ValueError("invalid_current_queue")
        queue_error = None
    except Exception as error:
        queue_bytes, queue = b"", {}
        queue_error = {"reason": "current_queue_unavailable", "error_type": type(error).__name__}
    candidates = {}
    for base, manifest_hash, records in sources:
        for record in records:
            if record.get("url") in urls:
                candidates.setdefault(record["url"], []).append((base, manifest_hash, record))
    rows = []
    for pin in articles:
        result = {"url": pin["url"], "producer_queue_key": pin["producer_queue_key"],
                  "expected_primary_html_sha256": pin["current_primary_html_sha256"],
                  "expected_primary_body_sha256": pin["primary_body_sha256"],
                  "expected_publication_date": pin["publication_date"],
                  "fixture_status": "missing_paid_input_original", "editorial_acceptance": False,
                  "capture_attempts": []}
        try:
            if queue_error:
                raise ValueError(queue_error["reason"])
            entry = queue.get(pin["producer_queue_key"], {})
            raw = entry.get("raw", {})
            metadata = raw.get("metadata", {})
            body = metadata.get("page_text")
            if entry.get("source") != SOURCE or raw.get("source_slug") != SOURCE or raw.get("url") != pin["url"]:
                raise ValueError("current_paid_primary_identity_mismatch")
            if metadata.get("html_sha256") != pin["current_primary_html_sha256"]:
                raise ValueError("current_paid_primary_html_sha256_mismatch")
            if (not isinstance(body, str) or sha256(body.encode()) != pin["primary_body_sha256"]
                    or len(body) != pin["primary_body_characters"]
                    or metadata.get("article_body_sha256") != pin["primary_body_sha256"]
                    or metadata.get("article_body_characters") != pin["primary_body_characters"]):
                raise ValueError("current_paid_primary_body_mismatch")
            if (raw.get("event_date") != pin["publication_date"]
                    or metadata.get("publication_date") != pin["publication_date"]):
                raise ValueError("current_paid_primary_date_mismatch")
            if (metadata.get("source_quality_gate") != "passed"
                    or any(metadata.get(flag) is not True for flag in (
                        "article_body_complete", "primary_identity_verified", "publication_date_verified", "article_verified"))):
                raise ValueError("current_paid_primary_evidence_not_verified")
            result["current_queue_primary_bound"] = True
            expected = pin["original_http"]
            entries = sorted(candidates.get(pin["url"], []),
                             key=lambda row: row[2].get("captured_at") or "", reverse=True)
            if not entries:
                result["reason"] = "no_observed_original_http_record"
            for base, manifest_hash, record in entries:
                attempt = {"sha256": record.get("sha256"), "captured_at": record.get("captured_at")}
                try:
                    original_manifest = record.get("original_capture_manifest_sha256", manifest_hash)
                    if original_manifest != expected_manifest:
                        raise ValueError("paid_original_capture_manifest_sha256_mismatch")
                    for key in ("url", "requested_at", "captured_at", "status", "final_url", "content_type",
                                "charset", "bytes", "sha256", "returned_text_utf8_sha256", "gzip_sha256"):
                        if record.get(key) != expected.get(key):
                            raise ValueError("paid_original_http_record_mismatch:" + key)
                    if expected.get("status") != 200:
                        raise ValueError("paid_original_not_http_200")
                    original_path = record.get("original_gzip_file", record.get("gzip_file"))
                    if original_path != expected.get("gzip_file"):
                        raise ValueError("paid_original_gzip_path_mismatch")
                    compressed, text = verify_original(base, record)
                    if sha256(text.encode()) != pin["current_primary_html_sha256"]:
                        raise ValueError("paid_original_utf8_primary_sha256_mismatch")
                    title, parsed_body, primary = extract_article(text, pin["url"])
                    if (parsed_body != body or sha256(parsed_body.encode()) != pin["primary_body_sha256"]
                            or len(parsed_body) != pin["primary_body_characters"]):
                        raise ValueError("paid_original_parsed_body_mismatch")
                    if (primary.get("canonical_url") != pin["url"]
                            or any(primary.get(flag) is not True for flag in (
                                "primary_identity_verified", "publication_date_verified", "article_verified"))):
                        raise ValueError("paid_original_parsed_identity_or_date_unverified")
                    if (primary.get("publication_date") != pin["publication_date"]
                            or primary.get("visible_publication_date") != pin["publication_date"]
                            or primary.get("publication_date_source") != "visible_article_byline"):
                        raise ValueError("paid_original_primary_byline_date_mismatch")
                    relative = expected["sha256"] + ".html.gz"
                    destination = output / relative
                    if destination.exists() and sha256(destination.read_bytes()) != expected["gzip_sha256"]:
                        raise ValueError("existing_fixture_gzip_sha256_mismatch")
                    destination.write_bytes(compressed)
                    witness = {key: primary.get(key) for key in (
                        "canonical_url", "primary_identity_verified", "publication_date_verified", "article_verified",
                        "publication_date", "visible_publication_date", "publication_date_source",
                        "publication_timestamp", "publication_evidence", "publisher_date_convention", "section", "body_source")}
                    witness.update(primary_body_sha256=sha256(parsed_body.encode()),
                                   primary_body_characters=len(parsed_body), complete_paid_primary_body_matches=True)
                    retained = dict(record, gzip_file=relative, original_gzip_file=expected["gzip_file"],
                                    original_capture_manifest_sha256=expected_manifest,
                                    capture_provenance="preserved_original_http_response",
                                    paid_input_original_witness=dict(witness, paid_producer=pins["paid_producer"],
                                        producer_queue_key=pin["producer_queue_key"], retention_pins_sha256=sha256(pin_bytes)))
                    requests[(pin["url"], record["sha256"])] = retained
                    result.update(fixture_status="verified_exact_paid_input_original", original_bytes_verified=True,
                                  path=relative, sha256=record["sha256"], gzip_sha256=record["gzip_sha256"],
                                  returned_text_utf8_sha256=record["returned_text_utf8_sha256"],
                                  captured_at=record["captured_at"], requested_at=record["requested_at"],
                                  original_gzip_file=expected["gzip_file"],
                                  original_capture_manifest_sha256=expected_manifest, title=title,
                                  primary_witness=witness)
                    result.pop("reason", None)
                    result["capture_attempts"].append(dict(attempt, status="verified_exact_original"))
                    break
                except Exception as error:
                    result["capture_attempts"].append(dict(attempt, status="original_verification_error",
                                                          error_type=type(error).__name__, reason=str(error)))
                    result["reason"] = str(error)
        except Exception as error:
            result.update(fixture_status="paid_input_primary_binding_error", error_type=type(error).__name__, reason=str(error))
        rows.append(result)
    complete = all(row["fixture_status"] == "verified_exact_paid_input_original" for row in rows)
    return {"status": "ALL_EXACT_PAID_INPUT_ORIGINALS_RETAINED_NOT_EDITORIAL_ACCEPTANCE" if complete else "PAID_INPUT_ORIGINAL_RETENTION_PARTIAL",
            "retention_pins_sha256": sha256(pin_bytes), "paid_producer": pins["paid_producer"],
            "producer_references": pins.get("producer_references", {}), "original_capture": pins["original_capture"],
            "artifact_zip_digest_verified_by_this_retainer": False,
            "current_queue_sha256": sha256(queue_bytes) if queue_bytes else None,
            "required_original_count": len(articles), "verified_original_count": sum(
                row["fixture_status"] == "verified_exact_paid_input_original" for row in rows),
            "counts": dict(Counter(row["fixture_status"] for row in rows)), "rows": rows,
            "acceptance_note": "Exact historical HTTP 200 bytes and current full-primary/date replay only; no refetch, state restoration or editorial acceptance."}


def retain(control_path, capture_manifest, output, artifact_dir=None, max_debug=10, discovery_path=None,
           original_fixture_manifests=None, paid_original_pins_path=None, current_queue_path=None):
    control_bytes = control_path.read_bytes()
    control = json.loads(control_bytes)
    window = control["window_90"]
    controls = {normalized_url(row["url"]): row for row in control["articles"]
                if row.get("recall_expected") and window["start"] <= (row.get("publication_date") or "") <= window["end"]}
    if None in controls or not controls:
        raise ValueError("invalid_or_empty_primary_control")
    output.mkdir(parents=True, exist_ok=True)
    previous_path = output / "manifest.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    sources = capture_manifests(capture_manifest, artifact_dir)
    fallback_fixture_sources = set()
    # Warm discovery can legitimately reuse primary bytes preserved by the
    # original corpus collector. Retention does not recapture or relabel them.
    if original_fixture_manifests is None:
        original_fixture_manifests = [ROOT / "tests/fixtures" / name / "manifest.json" for name in (
            "pulso_editorial_exception_real", "pulso_thin_primary_real", "pulso_targeted_primary_real")]
    for path in original_fixture_manifests:
        if path.exists():
            value = json.loads(path.read_bytes())
            if value.get("source") == SOURCE and isinstance(value.get("requests"), list):
                manifest_hash = sha256(path.read_bytes())
                sources.append((path.parent, manifest_hash, value["requests"]))
                fallback_fixture_sources.add((path.parent, manifest_hash))
    # Existing verified fixtures preserve original provenance when the next run
    # serves details from a cache and its HTTP observer captures no article HTML.
    if previous.get("requests"):
        sources.append((output, sha256(previous_path.read_bytes()), previous["requests"]))
    evidence = discovery_evidence(discovery_path, artifact_dir)
    metadata_targets = {}
    control_targets = {}
    for trace in evidence[2] if evidence is not None else []:
        url = normalized_url(trace.get("url"))
        if trace.get("status") == "discovered_metadata_only" and url is not None:
            metadata_targets.setdefault(url, []).append(trace)
        if trace.get("status") == "discovered" and url in controls:
            control_targets.setdefault(url, []).append(trace)
    candidates = {}
    metadata_candidates = {}
    debug = []
    for base, manifest_hash, records in sources:
        for record in records:
            url = normalized_url(record.get("url"))
            candidate = (base, manifest_hash, record)
            if url in controls:
                candidates.setdefault(url, []).append(candidate)
            if url in metadata_targets:
                metadata_candidates.setdefault(url, []).append(candidate)
            if (record.get("primary_article_error") and record.get("gzip_file")
                    and (base, manifest_hash) not in fallback_fixture_sources):
                debug.append(candidate)
    requests = {}

    def preserve(candidate, expected=None):
        base, manifest_hash, record = candidate
        result = {"url": normalized_url(record.get("url")), "status": record.get("status"),
                  "captured_at": record.get("captured_at"), "sha256": record.get("sha256"),
                  "gzip_sha256": record.get("gzip_sha256"), "bytes": record.get("bytes"),
                  "original_capture_manifest_sha256": record.get("original_capture_manifest_sha256", manifest_hash),
                  "primary_article_error": record.get("primary_article_error")}
        try:
            compressed, text = verify_original(base, record)
            relative = record["sha256"] + ".html.gz"
            destination = output / relative
            if destination.exists() and sha256(destination.read_bytes()) != record["gzip_sha256"]:
                raise ValueError("existing_fixture_gzip_sha256_mismatch")
            destination.write_bytes(compressed)
            retained = dict(record, url=result["url"], gzip_file=relative,
                            capture_provenance="preserved_original_http_response",
                            original_capture_manifest_sha256=result["original_capture_manifest_sha256"])
            requests[(result["url"], record["sha256"])] = retained
            result.update(path=relative, original_bytes_verified=True)
            if record.get("status") != 200:
                result["fixture_status"] = "http_error_original_preserved"
            else:
                title, body, metadata = extract_article(text, result["url"])
                result.update(title=title, publication_date=metadata["publication_date"],
                              publication_date_source=metadata.get("publication_date_source"),
                              section=metadata.get("section"), primary_body_chars=len(body),
                              parsed_primary_identity_verified=metadata.get("primary_identity_verified"),
                              parsed_publication_date_verified=metadata.get("publication_date_verified"),
                              parsed_publisher_exception_reason=metadata.get("publisher_exception_reason"))
                result["fixture_status"] = "verified_original"
                if expected and metadata["publication_date"] != expected.get("publication_date"):
                    result["fixture_status"] = "original_date_conflict"
        except Exception as error:
            result.update(fixture_status="original_verification_error", error_type=type(error).__name__, reason=str(error))
        return result

    rows = []
    for url, expected in sorted(controls.items()):
        entries = sorted(candidates.get(url, []), key=lambda x: x[2].get("captured_at") or "", reverse=True)
        # A prior retained successful original remains useful if a later HTTP
        # attempt failed; all latest failures are recorded separately.
        entries.sort(key=lambda x: x[2].get("status") != 200)
        expected_shas = {trace.get("html_sha256") for trace in control_targets.get(url, [])
                         if re.fullmatch(r"[0-9a-f]{64}", str(trace.get("html_sha256", "")))}
        # A newer observation of the same URL is not the original used by a
        # cached current discovery. Prefer its exact primary hash, not recency.
        if expected_shas:
            entries.sort(key=lambda x: not expected_shas.intersection(
                {x[2].get("sha256"), x[2].get("returned_text_utf8_sha256")}))
        result = {"url": url, "fixture_status": "missing_original_capture"}
        attempts = []
        for candidate in entries:
            result = preserve(candidate, expected)
            attempts.append(dict(result))
            if result["fixture_status"] in {"verified_original", "original_date_conflict"}:
                break
        result.update(expected_publication_date=expected.get("publication_date"),
                      expected_section=expected.get("section"), topic=expected.get("topic"),
                      recall_expected=True, capture_attempts=attempts,
                      observed_capture_errors=[{"status": r.get("status"), "captured_at": r.get("captured_at"),
                          "error_type": r.get("error_type"), "reason": r.get("error") or r.get("primary_article_error")}
                          for _, _, r in entries if r.get("status") != 200 or r.get("primary_article_error")])
        rows.append(result)
    debug_rows = []
    seen = set()
    for candidate in sorted(debug, key=lambda x: x[2].get("captured_at") or "", reverse=True):
        digest = candidate[2].get("sha256")
        if digest not in seen:
            debug_rows.append(preserve(candidate))
            seen.add(digest)
        if len(debug_rows) >= max_debug:
            break
    # Metadata holds are substantive current runtime outcomes, not incidental
    # parser-debug samples. Every URL must bind to its CURRENT primary SHA.
    def preserve_current(targets, observed, kind):
        current_rows = []
        for url, traces in sorted(targets.items()):
            expected_shas = {trace.get("html_sha256") for trace in traces
                             if re.fullmatch(r"[0-9a-f]{64}", str(trace.get("html_sha256", "")))}
            entries = [candidate for candidate in observed.get(url, []) if candidate[2].get("status") == 200
                       and expected_shas.intersection({candidate[2].get("sha256"), candidate[2].get("returned_text_utf8_sha256")})]
            entries.sort(key=lambda item: item[2].get("captured_at") or "", reverse=True)
            result = {"url": url, "fixture_status": "missing_current_" + kind + "_original"}
            attempts = []
            for candidate in entries:
                result = preserve(candidate)
                attempts.append(dict(result))
                if result.get("original_bytes_verified"):
                    # This verifies observed bytes even when parser replay
                    # rejects the page; it gives no date/editorial credit.
                    result["original_parser_replay_status"] = result["fixture_status"]
                    result["fixture_status"] = "hash_verified_current_" + kind + "_original"
                    break
            result.update(expected_current_primary_sha256s=sorted(expected_shas),
                          source_observations=[{key: trace.get(key) for key in (
                              "status", "reason", "publisher_exception_reason", "source_quality_gate", "possible_publication_days",
                              "publication_date", "publication_date_verified", "primary_identity_verified", "article_verified",
                              "article_body_complete", "source_content_unavailable_reason", "html_sha256", "captured_at",
                              "cache_hit", "publisher_lastmod")} for trace in traces],
                          capture_attempts=attempts, editorial_acceptance=False,
                          source_sha_missing_or_ambiguous=len(expected_shas) != 1)
            current_rows.append(result)
        return current_rows

    metadata_rows = preserve_current(metadata_targets, metadata_candidates, "metadata_hold")
    current_control_rows = preserve_current(control_targets, candidates, "control_primary")
    paid_originals = preserve_paid_originals(sources, paid_original_pins_path, current_queue_path, output, requests)
    paid_urls = {row["url"] for row in paid_originals["rows"]}
    # Preserve already retained observed variants by URL+SHA. Rebuilding the
    # manifest must not orphan the original a warm cache still references when
    # a later targeted observation supplies different publisher bytes.
    for record in previous.get("requests", []):
        key = (normalized_url(record.get("url")), record.get("sha256"))
        if key[0] in set(controls) | set(metadata_targets) | paid_urls and record.get("gzip_file") and key not in requests:
            preserve((output, sha256(previous_path.read_bytes()), record))
    api_proof = preserve_api_proof(sources, evidence, output, requests)
    counts = dict(Counter(row["fixture_status"] for row in rows))
    manifest = {"schema_version": "1.0", "source": SOURCE,
                "mode": "retention_only_no_discovery_or_queue_injection",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "status": "ORIGINAL_FIXTURES_AVAILABLE_NOT_SOURCE_ACCEPTANCE" if counts.get("verified_original") == len(controls) else "ORIGINAL_FIXTURES_PARTIAL",
                "window_90": window, "external_control_sha256": sha256(control_bytes),
                "expected_controls": len(controls), "counts": counts,
                "fixtures": rows, "debug_parser_errors": debug_rows,
                "current_metadata_hold_originals": metadata_rows,
                "current_metadata_hold_expected_unique_urls": len(metadata_targets),
                "current_metadata_hold_original_status": "ALL_CURRENT_METADATA_HOLD_ORIGINALS_RETAINED_NOT_EDITORIAL_ACCEPTANCE" if metadata_rows and all(
                    row["fixture_status"] == "hash_verified_current_metadata_hold_original" and not row["source_sha_missing_or_ambiguous"]
                    for row in metadata_rows) else ("CURRENT_METADATA_HOLD_ORIGINAL_RETENTION_PARTIAL" if metadata_rows else "NO_CURRENT_METADATA_HOLDS"),
                "current_control_primary_originals": current_control_rows,
                "current_control_primary_expected_unique_urls": len(control_targets),
                "current_control_primary_original_status": "ALL_CURRENT_CONTROL_PRIMARY_ORIGINALS_RETAINED_NOT_EDITORIAL_ACCEPTANCE" if current_control_rows and all(
                    row["fixture_status"] == "hash_verified_current_control_primary_original" and not row["source_sha_missing_or_ambiguous"]
                    for row in current_control_rows) else ("CURRENT_CONTROL_PRIMARY_ORIGINAL_RETENTION_PARTIAL" if current_control_rows else "NO_CURRENT_CONTROL_PRIMARY_TRACES"),
                "public_api_proof": api_proof,
                "paid_input_original_retention": paid_originals,
                "requests": list(requests.values()), "unique_original_payloads": len({row["sha256"] for row in requests.values() if row.get("gzip_file")}),
                "acceptance_note": "These fixtures prove captured bytes and parser replay; they do not establish discovery recall or editorial acceptance."}
    temporary = previous_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(previous_path)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, default=ROOT / "data/audits/pulso_external_control_2026_10_11.json")
    parser.add_argument("--capture-manifest", type=Path, default=ROOT / "data/audits/pulso_runtime_capture/manifest.json")
    parser.add_argument("--capture-artifact", type=Path)
    parser.add_argument("--discovery", type=Path, default=ROOT / "data/state/discovery_run.json")
    parser.add_argument("--paid-original-pins", type=Path, default=ROOT / "data/audits/pulso_v5_paid_missing_originals_2026_10_11.json")
    parser.add_argument("--current-queue", type=Path, default=ROOT / "data/state/pending_queue.json")
    parser.add_argument("--output", type=Path, default=ROOT / "tests/fixtures/pulso_runtime_real")
    args = parser.parse_args()
    manifest = retain(args.control, args.capture_manifest, args.output, args.capture_artifact, discovery_path=args.discovery,
                      paid_original_pins_path=args.paid_original_pins, current_queue_path=args.current_queue)
    print(json.dumps(dict({key: manifest[key] for key in ("status", "expected_controls", "counts", "unique_original_payloads")},
                          paid_input_original_retention=manifest["paid_input_original_retention"]["status"])))


if __name__ == "__main__":
    main()
