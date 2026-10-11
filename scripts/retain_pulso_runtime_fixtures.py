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
        if any(row.get("status") == "public_feed_page" for row in details):
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
                    from radar_salud.pulso_source import publication_day
                    days = [publication_day(node.get("first_publish_date") or "") for node in nodes]
                    if page.get("inventory_day_max") and (None in days or max(days) != page["inventory_day_max"]):
                        raise ValueError("original_api_publication_boundary_mismatch")
                    relative = compact["sha256"] + ".json.gz"
                    destination = output / relative
                    if destination.exists() and sha256(destination.read_bytes()) != compact["gzip_sha256"]:
                        raise ValueError("existing_fixture_gzip_sha256_mismatch")
                    destination.write_bytes(compressed)
                    compact.update(gzip_file=relative, raw_payload_retained=True,
                                   capture_provenance="preserved_original_public_api_response")
                    requests[(compact["url"], compact["sha256"])] = compact
                    item.update(proof_status="verified_original_boundary_json", http=compact)
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
            "http_chain_sha256": sha256(chain_bytes), "feeds": feeds,
            "raw_payload_retention": "Exact observed first and last three API responses per feed; interior pages retain observed HTTP metadata only."}


def retain(control_path, capture_manifest, output, artifact_dir=None, max_debug=10, discovery_path=None):
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
    # Existing verified fixtures preserve original provenance when the next run
    # serves details from a cache and its HTTP observer captures no article HTML.
    if previous.get("requests"):
        sources.append((output, sha256(previous_path.read_bytes()), previous["requests"]))
    candidates = {}
    debug = []
    for base, manifest_hash, records in sources:
        for record in records:
            url = normalized_url(record.get("url"))
            candidate = (base, manifest_hash, record)
            if url in controls:
                candidates.setdefault(url, []).append(candidate)
            if record.get("primary_article_error") and record.get("gzip_file"):
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
                              section=metadata.get("section"), primary_body_chars=len(body))
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
    evidence = discovery_evidence(discovery_path, artifact_dir)
    api_proof = preserve_api_proof(sources, evidence, output, requests)
    counts = dict(Counter(row["fixture_status"] for row in rows))
    manifest = {"schema_version": "1.0", "source": SOURCE,
                "mode": "retention_only_no_discovery_or_queue_injection",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "status": "ORIGINAL_FIXTURES_AVAILABLE_NOT_SOURCE_ACCEPTANCE" if counts.get("verified_original") == len(controls) else "ORIGINAL_FIXTURES_PARTIAL",
                "window_90": window, "external_control_sha256": sha256(control_bytes),
                "expected_controls": len(controls), "counts": counts,
                "fixtures": rows, "debug_parser_errors": debug_rows,
                "public_api_proof": api_proof,
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
    parser.add_argument("--output", type=Path, default=ROOT / "tests/fixtures/pulso_runtime_real")
    args = parser.parse_args()
    manifest = retain(args.control, args.capture_manifest, args.output, args.capture_artifact, discovery_path=args.discovery)
    print(json.dumps({key: manifest[key] for key in ("status", "expected_controls", "counts", "unique_original_payloads")}))


if __name__ == "__main__":
    main()
