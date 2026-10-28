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

5. (v3) Paid model outputs are preserved: a verbatim body quote inside one becomes
   an in-place receipt and the output's pre-redaction digest is recorded
   (``analysis_model_output_rights``) so earlier validations still bind to it.
   CSV audit cells are scrubbed too. ``remaining_fingerprinted`` scans every
   tracked text file outside tests/fixtures and reports what is left, split into
   paywalled/no-URL context and open-URL context (open sections that publish the
   same sentence). The receipt also simulates the paid-output reuse decision.

6. (v4, review 3) Open La Tercera paths: a stored capture whose body reproduces a
   known paywalled body (sentence fingerprints) at >= 50% of its sentences is
   paywalled (``paywall_overlap``) and redacted like a premium piece; below that only
   the overlapping sentences become inline receipts (the capture hash stays provable,
   ``article_body_sentence_redaction``). Matches under other open URLs in tracked
   files are redacted sentence by sentence. Stored La Tercera items without a
   per-article access flag keep their path classification, marked
   ``access_verified: false``; ``counts.la_tercera_access`` reports how many are
   "open by path only". Nothing is re-fetched.

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
from radar_salud.source_rights import (OVERLAP_KEY, access_classification, apply_overlap_policy,  # noqa: E402
                                       body_overlap)
from radar_salud.source_urls import card_link_problems, sanitize_card_links, source_url_problem  # noqa: E402

LT_HOSTS = {"latercera.com", "www.latercera.com"}


def _lt(url):
    from urllib.parse import urlsplit
    try:
        return (urlsplit(str(url or "")).hostname or "").lower() in LT_HOSTS
    except ValueError:
        return False


def apply_overlap(queue, cache, fps):
    """v4: overlap rule on every stored La Tercera capture (queue, nested history, Pulso cache)."""
    stats = {"records_paywalled_by_overlap": 0, "records_sentences_redacted": 0, "paywalled_urls": [],
             "sentence_redacted_urls": []}
    flagged, partial = set(), set()
    new_bodies = []

    def run(record):
        url = record.get("url")
        md = record.get("metadata") or {}
        texts = [md.get("page_text"), record.get("raw_text"), record.get("body")]
        outcome = apply_overlap_policy(record, fps)
        if outcome == "paywalled":
            stats["records_paywalled_by_overlap"] += 1
            flagged.add(_key(url))
            new_bodies.extend((t, [record.get("title") or "", md.get("description") or ""]) for t in texts
                              if isinstance(t, str) and len(t) >= 160)
        elif outcome == "sentences":
            stats["records_sentences_redacted"] += 1
            partial.add(_key(url))

    for item in queue.values():
        for raw in list(_raws(item)):
            if _lt(raw.get("url")):
                run(raw)
    for url, entry in (cache.get("articles") or {}).items():
        if isinstance(entry, dict) and _lt(url):
            entry.setdefault("url", url)
            run(entry)
    # Every sentence of a body now known to be paywalled is fingerprinted too.
    for text, public in new_bodies:
        fps |= body_fingerprints(text, public)
    stats["paywalled_urls"] = sorted(flagged)
    stats["sentence_redacted_urls"] = sorted(partial - flagged)
    return stats, flagged


def mark_access(queue, cache):
    """v4: stored La Tercera items without a per-article flag stay path-classified, ``access_verified: false``."""
    from collections import Counter
    counts = {"queue": Counter(), "cache": Counter()}
    for label, records in (("queue", [(item.get("raw") or {}) for item in queue.values()]),
                           ("cache", [e for e in (cache.get("articles") or {}).values() if isinstance(e, dict)])):
        for record in records:
            md = record.get("metadata")
            if not _lt(record.get("url")) or not isinstance(md, dict):
                continue
            if md.get("access_verified") is not True:
                md["access_verified"] = False
            c = access_classification(record["url"], md)
            counts[label]["total"] += 1
            counts[label][("paywalled_by_" if c["paywalled"] else "open_by_") + c["basis"]] += 1
            if not c["paywalled"] and not c["access_verified"]:
                counts[label]["open_by_path_only"] += 1
            if c["access_verified"]:
                counts[label]["access_verified"] += 1
    return {k: dict(sorted(v.items())) for k, v in counts.items()}

HISTORY = ROOT / "data/history/superintendencia_signals.json"
QUEUE = ROOT / "data/state/pending_queue.json"
PULSO_CACHE = ROOT / "data/state/pulso_discovery_cache.json"
SNAPSHOT = ROOT / "web/data/radar_today.json"
DESIGN_SNAPSHOT = ROOT / "design/bandeja/data/radar_today.json"  # prototype copy of the public feed
RECEIPT = ROOT / "data/audits/rights_links_migration_2026_10_28.json"
FINGERPRINTS = ROOT / FINGERPRINTS_PATH
WEEKLY = [ROOT / "data/weekly_insight/latest.json", ROOT / "data/weekly_insight/editorial_approved.json"]
SCAN_ROOTS = ("data/", "web/", "design/", "config/")
SKIP = {str(p.relative_to(ROOT)) for p in (QUEUE, PULSO_CACHE, RECEIPT, FINGERPRINTS, HISTORY, SNAPSHOT,
                                                      DESIGN_SNAPSHOT)} | {
    "data/audits/rights_redacted_originals_2026_10_28.json"}
# Keys holding publisher text: the key ends with a body-like term ("page_text", "original_body",
# "body_excerpt"). Reviewer prose such as "body_specific_independent_editorial_reason" is
# Alicanto text and must not be fingerprinted as publisher body.
_BODYISH = re.compile(r"(?:^|_)(?:body|page_text|raw_text|excerpt|paragraphs?|primary_text|full_text|article_text|"
                      r"body_text|primary_body)$", re.I)


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
        # The lead with proven provenance is public even when it differs from ``description``.
        public.append(teaser_with_source({"title": entry.get("title"), "url": url,
                                          "source_slug": "pulso_latercera", "metadata": md})[0])
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
    """Remember the pre-redaction git blob of each redacted file (QA replays read it from history).

    Covers historical audits and the queue/Pulso cache state as committed before
    this migration redacted them (the bound editorial-review QA replays the queue
    that review was applied to). Only an unredacted, committed original qualifies.
    """
    import hashlib
    doc = json.loads(ORIGINALS.read_text(encoding="utf-8")) if ORIGINALS.exists() else {"files": {}}
    for path in paths:
        rel = str(path.relative_to(ROOT))
        if rel in doc["files"] or rel.endswith("rights_links_migration_2026_10_28.json"):
            continue
        # The blob of the exact bytes about to be redacted, if git already stores it
        # (i.e. it was committed: staging's version). Nothing is written to git here.
        oid = subprocess.run(["git", "hash-object", "--", rel], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        exists = oid and subprocess.run(["git", "cat-file", "-e", oid], cwd=ROOT, capture_output=True).returncode == 0
        blob = subprocess.run(["git", "cat-file", "blob", oid], cwd=ROOT, capture_output=True).stdout if exists else b""
        if blob and blob == path.read_bytes():  # only an unredacted, committed original qualifies
            doc["files"][rel] = {"git_blob": oid, "sha256": hashlib.sha256(blob).hexdigest(),
                                 "characters": len(blob.decode("utf-8", "replace"))}
    doc["files"] = dict(sorted(doc["files"].items()))
    ORIGINALS.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


_TEXT_SUFFIXES = (".json", ".json.gz", ".jsonl", ".md", ".html", ".htm", ".js", ".cjs", ".mjs", ".css", ".txt", ".csv",
                  ".tsv", ".py", ".yml", ".yaml", ".xml", ".svg")
CHECK_EXCLUDE_PREFIXES = ("tests/fixtures/",)
CHECK_EXCLUDE = {str(FINGERPRINTS_PATH), "data/audits/rights_redacted_originals_2026_10_28.json"}


def _strings(node, url=None):
    """(string, url context) for every string in a JSON value (dict keys that are URLs give context)."""
    if isinstance(node, dict):
        url = next((node[k] for k in ("url", "source_url", "canonical_url", "requested_url", "final_url")
                    if isinstance(node.get(k), str) and node.get(k)), url)
        for key, value in node.items():
            child = key if isinstance(key, str) and re.match(r"https?://", key) else url
            yield from _strings(value, child)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value, url)
    elif isinstance(node, str):
        yield node, url


def remaining_fingerprinted(fps, files=None, paywalled_urls=frozenset()):
    """Scan every tracked text file outside tests/fixtures for paywalled-body sentences.

    Truthful count: every string (JSON) or sentence (other text) containing a
    fingerprinted sentence is counted, whatever its context; matches sitting under
    an open (non-paywalled) URL -- an open source quoting the same sentence -- are
    reported separately from those under a paywalled URL or with no URL.
    """
    from radar_salud.source_rights import _segment_hash, _segments, contains_fingerprinted
    if files is None:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode()
        files = [f for f in out.split("\0") if f.endswith(_TEXT_SUFFIXES)
                 and not f.startswith(CHECK_EXCLUDE_PREFIXES) and f not in CHECK_EXCLUDE]
    result = {"files_scanned": 0, "characters": 0, "strings": 0, "open_context_characters": 0,
              "open_context_strings": 0, "by_file": {}}
    for f in files:
        path = ROOT / f
        try:
            data = path.read_bytes()
            if f.endswith(".gz"):
                data = gzip.decompress(data)
            text = data.decode("utf-8")
        except (OSError, UnicodeDecodeError, EOFError):
            continue
        result["files_scanned"] += 1
        hits = []
        if f.endswith((".json", ".json.gz")):
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            if payload is not None:
                for value, url in _strings(payload):
                    if contains_fingerprinted(value, fps):
                        hits.append((len(value), bool(url) and not is_paywalled(url)
                                     and _key(url) not in paywalled_urls))
            else:
                hits = [(len(seg), False) for seg in _segments(text) if _segment_hash(seg) in fps]
        else:
            hits = [(len(seg), False) for seg in _segments(text) if _segment_hash(seg) in fps]
        if hits:
            chars = sum(n for n, _ in hits)
            open_chars = sum(n for n, open_ in hits if open_)
            result["by_file"][f] = {"strings": len(hits), "characters": chars, "open_context_characters": open_chars}
            result["strings"] += len(hits)
            result["characters"] += chars
            result["open_context_strings"] += sum(1 for _, open_ in hits if open_)
            result["open_context_characters"] += open_chars
    result["paywalled_context_characters"] = result["characters"] - result["open_context_characters"]
    return result


def simulate_paid_reuse(queue):
    """The reuse decision ``pulso_paywall.full_body_output`` would take for every paid premium Pulso item."""
    from collections import Counter
    from radar_salud.models import RawItem
    from radar_salud import pulso_paywall
    reasons, by_status = Counter(), Counter()
    for item in queue.values():
        raw = item.get("raw") or {}
        md = raw.get("metadata") or {}
        if raw.get("source_slug") != "pulso_latercera" or not paywall_policy(raw.get("url", ""), md):
            continue
        if pulso_paywall._meta(md.get("analysis_model_output")) is None:
            continue
        r = RawItem(**{k: raw.get(k) for k in ("source_slug", "title", "url", "source_name", "source_type",
                                                 "event_date", "raw_text", "metadata")})
        model, why = pulso_paywall.full_body_output(r.metadata, pulso_paywall.prior_binding(r.metadata),
                                                    pulso_paywall.public_text_for(r.title, r.metadata, r.event_date))
        reasons[why] += 1
        by_status[f"{item.get('status')}:{why}"] += 1
    return {"paid_premium_items": sum(reasons.values()), "reusable_without_new_call": reasons.get("reused", 0),
            "reasons": dict(reasons.most_common()), "by_queue_status": dict(sorted(by_status.items()))}


def _tracked(suffix):
    out = subprocess.run(["git", "ls-files", "-z", "--", *SCAN_ROOTS], cwd=ROOT, capture_output=True, check=True)
    return [f for f in out.stdout.decode().split("\0") if f.endswith(suffix) and f not in SKIP]


def scrub_csv(text, fps):
    """(new text, cells, characters): fingerprinted cells -> receipt strings; None-op otherwise."""
    import csv
    import io
    from radar_salud.source_rights import contains_fingerprinted, sha256_text
    rows = list(csv.reader(io.StringIO(text, newline="")))
    term = "\r\n" if "\r\n" in text else "\n"
    count = chars = 0
    for row in rows:
        for i, cell in enumerate(row):
            if contains_fingerprinted(cell, fps):
                row[i] = f"[redactado: muro de pago; sha256={sha256_text(cell)}; caracteres={len(cell)}]"
                count += 1
                chars += len(cell)
    if not count:
        return text, 0, 0
    out = io.StringIO()
    csv.writer(out, lineterminator=term).writerows(rows)
    return out.getvalue(), count, chars


def tracked_json_files():
    out = subprocess.run(["git", "ls-files", "-z", "--", *SCAN_ROOTS], cwd=ROOT, capture_output=True, check=True)
    files = [f for f in out.stdout.decode().split("\0") if f.endswith((".json", ".json.gz"))]
    return [f for f in files if f not in SKIP]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    args = ap.parse_args()
    report = {"migration": "rights_links_2026_10_28", "version": 4, "policy": "config/paywalled_press.json",
              "links": [], "paywalled": [], "counts": {}, "not_migrated": [
                  "Git history keeps pre-redaction content; removing it requires a history rewrite (decision for Dirección).",
                  "tests/fixtures keep real publisher HTML/JSON used as parser regression inputs (see counts.fixtures_note).",
                  "Non-premium latercera.com sections without an isAccessibleForFree=false flag are metered, "
                  "not paywalled under the policy (pending_decision in config/paywalled_press.json)."]}
    writes = {}
    csv_writes = {}

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
    overlap_stats, overlap_urls = apply_overlap(queue, cache, fps)
    report["counts"]["la_tercera_sentence_overlap"] = overlap_stats
    for row in history["signals"] + snapshot["signals"]:
        if _key(row.get("source_url")) in overlap_urls and not isinstance(row.get(OVERLAP_KEY), dict):
            row[OVERLAP_KEY] = {"paywalled": True, "basis": "sentence_overlap_with_paywalled_body"}

    q = {"items_scanned": 0, "nested_records_redacted": 0, "body_characters_removed": 0,
         "fingerprint_strings": 0, "fingerprint_characters": 0, "items_changed": 0}
    for item in queue.values():
        before = json.dumps(item, ensure_ascii=False, sort_keys=True) if not args.check else None
        stats = scrub_queue_item(item, fps)
        raw0 = item.get("raw") or {}
        if _lt(raw0.get("url")) and not paywall_policy(raw0.get("url", ""), raw0.get("metadata")):
            # Open piece: only sentences reproducing a paywalled body become receipts.
            n, chars = scrub_fingerprinted(item, fps, open_sentences=True, paywalled_urls=overlap_urls)
            stats["fingerprint_strings"] += n
            stats["fingerprint_characters"] += chars
        if stats["records"] or stats["fingerprint_strings"] or stats["characters"]:
            q["items_scanned"] += 1
        q["nested_records_redacted"] += stats["records"]
        q["body_characters_removed"] += stats["characters"]
        q["fingerprint_strings"] += stats["fingerprint_strings"]
        q["fingerprint_characters"] += stats["fingerprint_characters"]
        if before is not None and json.dumps(item, ensure_ascii=False, sort_keys=True) != before:
            q["items_changed"] += 1
    report["counts"]["queue"] = q
    from radar_salud.source_rights import MODEL_OUTPUT_RIGHTS
    records = [md for item in queue.values() for raw in _raws(item) for md in [raw["metadata"]]
               if isinstance(md.get(MODEL_OUTPUT_RIGHTS), dict)]
    report["counts"]["paid_model_outputs_with_redacted_quotes"] = {
        "records": len(records),
        "top_level_items": sum(1 for item in queue.values()
                               if isinstance(((item.get("raw") or {}).get("metadata") or {}).get(MODEL_OUTPUT_RIGHTS), dict)),
        "original_digest_unknown": sum(1 for md in records if not md[MODEL_OUTPUT_RIGHTS].get("original_model_output_sha256")),
        "quote_receipts": sum(len(md[MODEL_OUTPUT_RIGHTS]["redactions"]) for md in records)}
    report["counts"]["paid_reuse_simulation"] = simulate_paid_reuse(queue)
    teasers = teasers_from_queue(queue)
    writes[QUEUE] = (queue, queue_text)

    # 2. Pulso discovery cache: premium entries keep lead + body receipt.
    from radar_salud.pulso_source import public_capture
    c = {"entries_redacted": 0, "body_characters_removed": 0, "fingerprint_strings": 0}
    for url, entry in (cache.get("articles") or {}).items():
        if isinstance(entry, dict) and not is_paywalled(url, entry.get("metadata")):
            n, _ = scrub_fingerprinted(entry, fps, open_sentences=True, paywalled_urls=overlap_urls)
            c["open_sentence_strings"] = c.get("open_sentence_strings", 0) + n
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
    report["counts"]["la_tercera_access"] = mark_access(queue, cache)
    writes[PULSO_CACHE] = (cache, cache_text)

    # 3. Public rows: history + snapshot.
    report["counts"]["history_rows_changed"] = migrate_rows(history["signals"], teasers, report, "history")
    report["counts"]["snapshot_cards_changed"] = migrate_rows(snapshot["signals"], teasers, report, "web_snapshot")
    report["counts"]["snapshot_link_problems_after"] = sum(len(card_link_problems(c)) for c in snapshot["signals"])
    writes[HISTORY] = (history, history_text)
    writes[SNAPSHOT] = (snapshot, snapshot_text)
    design_text, design = _read(DESIGN_SNAPSHOT)
    report["counts"]["design_snapshot_cards_changed"] = migrate_rows(design["signals"], teasers, report, "design_snapshot")
    scrub_fingerprinted(design, fps)
    writes[DESIGN_SNAPSHOT] = (design, design_text)
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
        n, chars = scrub_fingerprinted(payload, fps, open_sentences=True, paywalled_urls=overlap_urls)
        stats = {"signals": 0, "fields": 0}
        redacted = redact_public_payload(payload, index, stats) if f in weekly else payload
        if n or redacted is not payload:
            payload = redacted
            new_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            if new_text != json.dumps(json.loads(text), ensure_ascii=False, sort_keys=True):
                files["changed"][f] = {"strings": n, "characters": chars, "public_payload_fields": stats["fields"]}
                writes[path] = (payload, text)
    # CSV audit matrices: a cell reproducing a paywalled body sentence becomes a receipt
    # string (sha256 + length), rows and quoting otherwise byte-identical.
    for f in _tracked(".csv"):
        path = ROOT / f
        text = path.read_text(encoding="utf-8")
        new_text, n, chars = scrub_csv(text, fps)
        if n:
            files["changed"][f] = {"strings": n, "characters": chars, "public_payload_fields": 0}
            csv_writes[path] = new_text
    report["counts"]["files"] = files
    report["counts"]["fingerprint_segments"] = len(fps)
    report["counts"]["link_problem_rows"] = len(report["links"])
    report["counts"]["paywalled_rows"] = len(report["paywalled"])
    report.pop("_title_only_urls", None)
    report.pop("_headlines", None)
    report.pop("_decks", None)

    if args.check:
        report["counts"]["remaining_fingerprinted_before_write"] = remaining_fingerprinted(fps, None, overlap_urls)
        print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
        return
    record_originals([p for p in [*writes, *csv_writes] if str(p.relative_to(ROOT)).startswith("data/audits/")
                      or p in (QUEUE, PULSO_CACHE)])
    for path, (payload, original_text) in writes.items():
        _dump(path, payload, original_text)
    for path, new_text in csv_writes.items():
        path.write_bytes(new_text.encode("utf-8"))
    FINGERPRINTS.write_text(json.dumps({
        "purpose": "Sentence fingerprints of paywalled publisher bodies (sha256 prefix, 20 hex) used to find and "
                   "redact verbatim copies. No text is stored; a hash cannot be read back.",
        "segment_rule": "split on sentence punctuation/newlines, whitespace-collapsed, casefolded, >= 60 chars; "
                        "sentences also present in the public title/lead are excluded",
        "segment_sha256_prefix20": sorted(fps)}, indent=0) + "\n", encoding="utf-8")
    report["counts"]["remaining_fingerprinted"] = remaining_fingerprinted(fps, None, overlap_urls)
    if RECEIPT.exists():
        previous = json.loads(RECEIPT.read_text(encoding="utf-8"))
        report["first_run_counts"] = previous.get("first_run_counts") or previous.get("counts")
        report["v2_first_run_counts"] = previous.get("v2_first_run_counts") or (
            previous.get("counts") if previous.get("version") == 2 else None)
        # v3 (review 2, 28-oct): paid outputs keep their original digest, new premium
        # prefixes/sections, CSV cells, strict public-text check, review verdicts kept.
        report["v3_first_run_counts"] = previous.get("v3_first_run_counts") or (
            previous.get("counts") if previous.get("version") == 3 else report["counts"])
        # v4 (review 3, 28-oct): paid outputs archived before a teaser re-analysis, La
        # Tercera access flags + "open by path only" report, sentence-overlap rule.
        report["v4_first_run_counts"] = previous.get("v4_first_run_counts") or (
            previous.get("counts") if previous.get("version") == 4 else report["counts"])
    _dump(RECEIPT, report)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main()
