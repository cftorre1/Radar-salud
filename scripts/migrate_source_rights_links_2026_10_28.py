"""Deterministic migration (Dirección 28-oct-2026): source links + paywalled press.

1. Source links: rows keep ``source_url`` (identity, read-state keys); a
   repairable malformed URL gets ``source_link``; an unrepairable one gets
   ``source_link_status: invalid`` so the UI renders no link. Legacy MINSAL
   ``/sites/default/files/`` documents keep their link unless the row records a
   verified failure (``source_link_check``).
2. Paywalled press (config/paywalled_press.json: DF, Pulso, La Tercera PM, LT
   Board): public rows keep title, public lead, date and link; derived text is
   replaced by sha256/length receipts.
3. Stored captures: every queue item of a paywalled source is redacted,
   including nested history (``recovery_observations``, ``superseded_records``,
   ``evidence_revisions``, ``rediscovery_repairs``...). The Pulso discovery
   cache keeps lead + body receipt. A DF lead whose provenance cannot be shown
   to be the public og:description (the parser used to fall back to the body)
   becomes title-only.
4. Verbatim body sentences anywhere else in data/, web/, design/ and config/
   (audits, manifests, reviews) are replaced by receipts, using sentence
   fingerprints (hash prefixes, no text) persisted in
   data/audits/paywalled_body_fingerprints_2026_10_28.json.

Idempotent: a second run changes nothing. No network access, no model calls.
Usage: python scripts/migrate_source_rights_links_2026_10_28.py [--check]
"""
import argparse
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_salud.source_rights import (BODY_KEYS, FINGERPRINTS_PATH, TITLE_ONLY,  # noqa: E402
                                       body_fingerprints, public_fingerprints, clean_teaser, is_paywalled, load_fingerprints,
                                       paywall_policy, public_teaser, public_teaser_index, redact_public_payload,
                                       redact_signal, scrub_fingerprinted, scrub_queue_item, teaser_from_raw,
                                       teaser_with_source)
from radar_salud.source_urls import card_link_problems, sanitize_card_links, source_url_problem  # noqa: E402

HISTORY = ROOT / "data/history/superintendencia_signals.json"
QUEUE = ROOT / "data/state/pending_queue.json"
PULSO_CACHE = ROOT / "data/state/pulso_discovery_cache.json"
SNAPSHOT = ROOT / "web/data/radar_today.json"
RECEIPT = ROOT / "data/audits/rights_links_migration_2026_10_28.json"
FINGERPRINTS = ROOT / FINGERPRINTS_PATH
WEEKLY = [ROOT / "data/weekly_insight/latest.json", ROOT / "data/weekly_insight/editorial_approved.json"]
SCAN_ROOTS = ("data/", "web/", "design/", "config/")
SKIP = {str(p.relative_to(ROOT)) for p in (QUEUE, PULSO_CACHE, RECEIPT, FINGERPRINTS, HISTORY, SNAPSHOT)} | {
    "data/audits/rights_redacted_originals_2026_10_28.json"}
_BODYISH = re.compile(r"(body|page_text|raw_text|excerpt|paragraph|primary_text|full_text|article_text)", re.I)


def _key(url):
    return str(url or "").strip().rstrip("/")


def _dump(path, value, like=None):
    """Write JSON in the file's existing style (indent, ASCII escaping, trailing newline)."""
    style = _style(like) if like is not None else {"indent": 2, "ensure_ascii": False, "newline": False}
    text = json.dumps(value, ensure_ascii=style["ensure_ascii"], indent=style["indent"],
                      separators=style.get("separators"))
    data = (text + ("\n" if style["newline"] else "")).encode("utf-8")
    if path.suffix == ".gz":
        data = gzip.compress(data, mtime=0)
    path.write_bytes(data)


def _style(text):
    head = text[:4096]
    indent = None
    m = re.search(r"\n( +)\S", head)
    if m:
        indent = len(m.group(1))
    elif re.search(r"\n\S", head):
        indent = 0
    ensure_ascii = "\\u00" in text[:2_000_000] and not re.search(r"[À-ſ]", text[:2_000_000])
    separators = None if indent is not None else ((", ", ": ") if ", \"" in head or ": " in head else (",", ":"))
    return {"indent": indent, "ensure_ascii": ensure_ascii, "newline": text.endswith("\n"), "separators": separators}


def _read(path):
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    text = data.decode("utf-8")
    return text, json.loads(text)


def teasers_from_queue(queue):
    out = {}
    for item in queue.values():
        raw = item.get("raw") or {}
        if not paywall_policy(raw.get("url", ""), raw.get("metadata")):
            continue
        teaser = teaser_from_raw(raw)
        if teaser:
            out.setdefault(_key(raw["url"]), teaser)
    return out


def listing_deck(row):
    """DF listing cards concatenate headline + public deck in ``title`` (see export _separate_df_deck)."""
    title = str(row.get("source_title_full") or row.get("title") or "")
    match = re.search(r"\s+El\s+(?=(?:plan|alcalde|principal ejecutivo)\b)", title)
    if row.get("source_name") == "Diario Financiero" and len(title) > 180 and match and match.start() >= 60:
        return public_teaser(title[match.start():], source="df_listing_card")
    return ""


def migrate_rows(rows, teasers, report, label):
    changed = 0
    for i, row in enumerate(rows):
        before = json.dumps(row, ensure_ascii=False, sort_keys=True)
        new = row
        if is_paywalled(new.get("source_url"), new):
            url = _key(new.get("source_url"))
            # The queue is authoritative for the lead and its provenance; a row's
            # stored lead is kept only when the queue has no record of the piece.
            teaser = teasers.get(url) if url in teasers else (
                new.get("public_teaser") if new.get("paywalled") else "") or listing_deck(new)
            if url in report.setdefault("_title_only_urls", set()):
                # The queue cannot prove the stored lead was the og:description; only
                # the DF listing card (headline + deck, as the row title shows it) is public.
                headline = clean_teaser(report.get("_headlines", {}).get(url))
                title = clean_teaser(new.get("title"))
                teaser = (public_teaser(title[len(headline):], source="df_listing_card")
                          if headline and title.startswith(headline) and len(title) > len(headline) + 20 else "")
                # The exporter splits the deck off the card title: reuse the deck proven on the history row.
                decks = report.setdefault("_decks", {})
                teaser = teaser or decks.get(url, "")
                if teaser:
                    decks[url] = teaser
            new = redact_signal(new, teaser or "")
            report["paywalled"].append({"set": label, "source_url": new["source_url"], "has_public_teaser": bool(teaser),
                                        "redacted_fields": sorted({r["field"] for r in new["rights_redactions"]})})
        problem = source_url_problem(new.get("source_url"))
        new = sanitize_card_links(new)
        if problem or new.get("source_link_status"):
            report["links"].append({"set": label, "source_name": new.get("source_name"), "source_url": new.get("source_url"),
                                    "problem": problem or new.get("source_link_problem"),
                                    "status": new.get("source_link_status"), "source_link": new.get("source_link")})
        if json.dumps(new, ensure_ascii=False, sort_keys=True) != before:
            rows[i] = new
            changed += 1
    return changed


# --- Legacy DF lead provenance -------------------------------------------------

def _page_text_receipt(md):
    return next((r for r in md.get("rights_redactions") or [] if isinstance(r, dict)
                 and r.get("field") in ("metadata.page_text", "page_text")), None)


def establish_df_provenance(raw):
    """Decide once whether a legacy DF lead was the public og:description or body text.

    DF's parser stored ``raw_text = og:description or body[:1800]``. A lead is
    proven public only if a distinct, longer body was captured beside it (its
    receipt shows more characters) or no body existed at all. Otherwise the lead
    may be the locked body itself: title only.
    """
    md = raw.get("metadata")
    if not isinstance(md, dict) or md.get("public_teaser_source"):
        return None
    teaser = clean_teaser(md.get("public_teaser") or raw.get("raw_text"))
    body = md.get("page_text") or ""
    rec = _page_text_receipt(md)
    if teaser and rec and rec["characters"] > len(teaser) + 40:
        source = "legacy_description_verified"
    elif teaser and not rec and not body and not md.get("article_body_characters"):
        source = "legacy_description_verified"  # no body at capture: the lead could only be the description
    elif teaser and body and clean_teaser(body) != teaser and len(clean_teaser(body)) > len(teaser) + 40:
        source = "legacy_description_verified"  # unredacted nested capture with a distinct body
    else:
        source = TITLE_ONLY
    md["public_teaser_source"] = source
    md["public_teaser"] = teaser if source != TITLE_ONLY else ""
    if source == TITLE_ONLY and teaser:
        from radar_salud.source_rights import receipt
        md.setdefault("rights_redactions", []).append(receipt(teaser, "metadata.public_teaser",
                                                              reason="lead_provenance_unproven_body_fallback"))
    if rec and not md.get("article_body_sha256"):
        md["article_body_sha256"], md["article_body_characters"] = rec["sha256"], rec["characters"]
        md["body_redacted"] = True
    return source


def _raws(node):
    if isinstance(node, dict):
        if isinstance(node.get("url"), str) and isinstance(node.get("metadata"), dict):
            yield node
        for value in node.values():
            yield from _raws(value)
    elif isinstance(node, list):
        for value in node:
            yield from _raws(value)


# --- Fingerprints ---------------------------------------------------------------

# Leads count as public only through ``teaser_with_source`` (proven provenance), never
# from a stored ``public_teaser`` that may be a body fallback.
_PUBLIC_KEYS = {"title", "article_title", "primary_header_title", "description", "og_description",
                "headline", "public_title", "display_title", "source_title_full", "label", "legacy_title"}


def collect_fingerprints(queue, cache, audit_payloads, public_rows=()):
    """Sentence hashes of every paywalled body still present (plus the persisted set).

    Public text (every title, lead and publisher description seen anywhere) is
    subtracted globally, so a headline repeated inside a body is never redacted.
    """
    body, public = set(), []

    def add_body(text):
        nonlocal body
        if isinstance(text, str) and len(text) >= 160:
            body |= body_fingerprints(text)

    def gather_public(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _PUBLIC_KEYS and isinstance(value, str):
                    public.append(value)
                else:
                    gather_public(value)
        elif isinstance(node, list):
            for value in node:
                gather_public(value)

    for item in queue.values():
        raw0 = item.get("raw") or {}
        if paywall_policy(raw0.get("url", ""), raw0.get("metadata")):
            gather_public(item)
        else:
            public.extend([raw0.get("title") or "", (raw0.get("metadata") or {}).get("article_title") or ""])
            continue
        for raw in _raws(item):
            md = raw["metadata"]
            public.append(teaser_with_source(raw)[0])
            for text in [md.get(k) for k in BODY_KEYS] + [raw.get("raw_text")]:
                add_body(text)
            for entry in (md.get("liveblog_temporal_evidence") or {}).get("entries") or []:
                if isinstance(entry, dict):
                    add_body(entry.get("body"))
    for url, entry in (cache.get("articles") or {}).items():
        if not isinstance(entry, dict):
            continue
        public.append(entry.get("title") or "")
        if not is_paywalled(url, entry.get("metadata")):
            continue
        md = entry.get("metadata") or {}
        public.append(md.get("description") or "")
        add_body(md.get("page_text"))
        add_body(entry.get("body"))
    for row in public_rows:
        gather_public(row)

    def walk(node, url=None):
        if isinstance(node, dict):
            url = next((node[k] for k in ("url", "source_url", "canonical_url") if isinstance(node.get(k), str)), url)
            for key, value in node.items():
                if isinstance(value, str) and key in _PUBLIC_KEYS:
                    public.append(value)
                elif (isinstance(value, str) and len(value) >= 160 and url and is_paywalled(url)
                        and _BODYISH.search(key)):
                    add_body(value)
                else:
                    # Audits often key records by URL: {"originals": {"https://www.df.cl/...": {...}}}.
                    walk(value, key if re.match(r"https?://", key) else url)
        elif isinstance(node, list):
            for value in node:
                walk(value, url)

    for payload in audit_payloads:
        walk(payload)
    return (load_fingerprints(ROOT) | body) - public_fingerprints(public)


ORIGINALS = ROOT / "data/audits/rights_redacted_originals_2026_10_28.json"


def record_originals(paths):
    """Remember the pre-redaction git blob of each historical audit (QA replays read it from history)."""
    import hashlib
    doc = json.loads(ORIGINALS.read_text(encoding="utf-8")) if ORIGINALS.exists() else {"files": {}}
    for path in paths:
        rel = str(path.relative_to(ROOT))
        if rel in doc["files"] or rel.endswith("rights_links_migration_2026_10_28.json"):
            continue
        oid = subprocess.run(["git", "rev-parse", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        blob = subprocess.run(["git", "cat-file", "blob", oid], cwd=ROOT, capture_output=True).stdout if oid else b""
        if blob and blob == path.read_bytes():  # only an unredacted, committed original qualifies
            doc["files"][rel] = {"git_blob": oid, "sha256": hashlib.sha256(blob).hexdigest(),
                                 "characters": len(blob.decode("utf-8", "replace"))}
    doc["files"] = dict(sorted(doc["files"].items()))
    ORIGINALS.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def tracked_json_files():
    out = subprocess.run(["git", "ls-files", "-z", "--", *SCAN_ROOTS], cwd=ROOT, capture_output=True, check=True)
    files = [f for f in out.stdout.decode().split("\0") if f.endswith((".json", ".json.gz"))]
    return [f for f in files if f not in SKIP]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    args = ap.parse_args()
    report = {"migration": "rights_links_2026_10_28", "version": 2, "policy": "config/paywalled_press.json",
              "links": [], "paywalled": [], "counts": {}, "not_migrated": [
                  "Git history keeps pre-redaction content; removing it requires a history rewrite (decision for Dirección).",
                  "tests/fixtures keep real publisher HTML/JSON used as parser regression inputs (see counts.fixtures_note).",
                  "Non-premium latercera.com sections without an isAccessibleForFree=false flag are metered, "
                  "not paywalled under the policy (pending_decision in config/paywalled_press.json)."]}
    writes = {}

    # 1. Queue: lead provenance, then every nested capture.
    queue_text, queue = _read(QUEUE)
    cache_text, cache = _read(PULSO_CACHE)
    provenance = {}
    title_only_urls, headlines = set(), {}
    for item in queue.values():
        raw = item.get("raw") or {}
        if item.get("source") == "diario_financiero" and paywall_policy(raw.get("url", ""), raw.get("metadata")):
            source = establish_df_provenance(raw)
            if source:
                provenance[source] = provenance.get(source, 0) + 1
            if (raw.get("metadata") or {}).get("public_teaser_source") == TITLE_ONLY:
                title_only_urls.add(_key(raw["url"]))
                headlines[_key(raw["url"])] = (raw.get("metadata") or {}).get("article_title") or raw.get("title")
    report["counts"]["df_lead_provenance_established"] = provenance
    report["_title_only_urls"] = title_only_urls
    report["_headlines"] = headlines

    audit_files = [f for f in tracked_json_files() if re.match(r"data/audits/(pulso_|df_)", f)]
    audit_payloads = []
    for f in audit_files:
        try:
            audit_payloads.append(_read(ROOT / f)[1])
        except (ValueError, OSError):
            pass
    history_text, history = _read(HISTORY)
    snapshot_text, snapshot = _read(SNAPSHOT)
    fps = collect_fingerprints(queue, cache, audit_payloads, history["signals"] + snapshot["signals"])
    del audit_payloads

    q = {"items_scanned": 0, "nested_records_redacted": 0, "body_characters_removed": 0,
         "fingerprint_strings": 0, "fingerprint_characters": 0, "items_changed": 0}
    for item in queue.values():
        before = json.dumps(item, ensure_ascii=False, sort_keys=True) if not args.check else None
        stats = scrub_queue_item(item, fps)
        if stats["records"] or stats["fingerprint_strings"] or stats["characters"]:
            q["items_scanned"] += 1
        q["nested_records_redacted"] += stats["records"]
        q["body_characters_removed"] += stats["characters"]
        q["fingerprint_strings"] += stats["fingerprint_strings"]
        q["fingerprint_characters"] += stats["fingerprint_characters"]
        if before is not None and json.dumps(item, ensure_ascii=False, sort_keys=True) != before:
            q["items_changed"] += 1
    report["counts"]["queue"] = q
    teasers = teasers_from_queue(queue)
    writes[QUEUE] = (queue, queue_text)

    # 2. Pulso discovery cache: premium entries keep lead + body receipt.
    from radar_salud.pulso_source import public_capture
    c = {"entries_redacted": 0, "body_characters_removed": 0, "fingerprint_strings": 0}
    for url, entry in (cache.get("articles") or {}).items():
        if not isinstance(entry, dict) or not is_paywalled(url, entry.get("metadata")):
            continue
        before = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        md = entry.get("metadata") or {}
        chars = len(md.get("page_text") or "") if md.get("body_redacted") is not True else 0
        public_capture(entry)
        n, _ = scrub_fingerprinted(entry, fps, force=True)
        c["fingerprint_strings"] += n
        if json.dumps(entry, ensure_ascii=False, sort_keys=True) != before:
            c["entries_redacted"] += 1
            c["body_characters_removed"] += chars
    report["counts"]["pulso_discovery_cache"] = c
    writes[PULSO_CACHE] = (cache, cache_text)

    # 3. Public rows: history + snapshot.
    report["counts"]["history_rows_changed"] = migrate_rows(history["signals"], teasers, report, "history")
    report["counts"]["snapshot_cards_changed"] = migrate_rows(snapshot["signals"], teasers, report, "web_snapshot")
    report["counts"]["snapshot_link_problems_after"] = sum(len(card_link_problems(c)) for c in snapshot["signals"])
    writes[HISTORY] = (history, history_text)
    writes[SNAPSHOT] = (snapshot, snapshot_text)
    index = {**public_teaser_index(history["signals"], snapshot["signals"]), **teasers}

    # 4. Every other tracked JSON: verbatim body sentences -> receipts; weekly
    #    outputs also get the public-payload check.
    files = {"changed": {}, "open_context_matches": 0}
    weekly = {str(p.relative_to(ROOT)) for p in WEEKLY} | {
        f for f in tracked_json_files() if f.startswith("data/weekly_insight/")}
    for f in tracked_json_files():
        path = ROOT / f
        try:
            text, payload = _read(path)
        except (ValueError, OSError, UnicodeDecodeError):
            continue
        n, chars = scrub_fingerprinted(payload, fps)
        stats = {"signals": 0, "fields": 0}
        redacted = redact_public_payload(payload, index, stats) if f in weekly else payload
        if n or redacted is not payload:
            payload = redacted
            new_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            if new_text != json.dumps(json.loads(text), ensure_ascii=False, sort_keys=True):
                files["changed"][f] = {"strings": n, "characters": chars, "public_payload_fields": stats["fields"]}
                writes[path] = (payload, text)
    report["counts"]["files"] = files
    report["counts"]["fingerprint_segments"] = len(fps)
    report["counts"]["link_problem_rows"] = len(report["links"])
    report["counts"]["paywalled_rows"] = len(report["paywalled"])
    report.pop("_title_only_urls", None)
    report.pop("_headlines", None)
    report.pop("_decks", None)

    if args.check:
        print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
        return
    record_originals([p for p in writes if str(p.relative_to(ROOT)).startswith("data/audits/")])
    for path, (payload, original_text) in writes.items():
        _dump(path, payload, original_text)
    FINGERPRINTS.write_text(json.dumps({
        "purpose": "Sentence fingerprints of paywalled publisher bodies (sha256 prefix, 20 hex) used to find and "
                   "redact verbatim copies. No text is stored; a hash cannot be read back.",
        "segment_rule": "split on sentence punctuation/newlines, whitespace-collapsed, casefolded, >= 60 chars; "
                        "sentences also present in the public title/lead are excluded",
        "segment_sha256_prefix20": sorted(fps)}, indent=0) + "\n", encoding="utf-8")
    if RECEIPT.exists():
        previous = json.loads(RECEIPT.read_text(encoding="utf-8"))
        report["first_run_counts"] = previous.get("first_run_counts") or previous.get("counts")
        report["v2_first_run_counts"] = previous.get("v2_first_run_counts") or (
            previous.get("counts") if previous.get("version") == 2 else report["counts"])
    _dump(RECEIPT, report)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main()
