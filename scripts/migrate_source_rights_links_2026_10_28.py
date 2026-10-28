"""Deterministic migration (Dirección 28-oct-2026): source links + paywalled press.

1. Source links: rows keep ``source_url`` (identity, read-state keys); a
   repairable malformed URL gets ``source_link``; an unrepairable one gets
   ``source_link_status: invalid`` so the UI renders no link.
2. Paywalled press (config/paywalled_press.json): public rows keep title, public
   lead, date and link; derived text is removed and replaced by sha256/length
   receipts. DF bodies stored in the public queue/audits are redacted likewise.
   La Tercera queue/corpus bodies are NOT touched here (paid-revalidation
   identity depends on them; pending Dirección decision, see receipt).

Idempotent: a second run changes nothing. No network access.
Usage: python scripts/migrate_source_rights_links_2026_10_28.py [--check]
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_salud.source_rights import (is_paywalled, paywall_policy, public_teaser, purge_long_text,  # noqa: E402
                                       purge_raw_metadata, redact_signal, teaser_from_raw)
from radar_salud.source_urls import card_link_problems, sanitize_card_links, source_url_problem  # noqa: E402

HISTORY = ROOT / "data/history/superintendencia_signals.json"
QUEUE = ROOT / "data/state/pending_queue.json"
SNAPSHOT = ROOT / "web/data/radar_today.json"
RECEIPT = ROOT / "data/audits/rights_links_migration_2026_10_28.json"
DF_AUDITS = sorted((ROOT / "data/audits").glob("df_*.json"))


def _key(url):
    return str(url or "").strip().rstrip("/")


def _dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


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
        return public_teaser(title[match.start():])
    return ""


def migrate_rows(rows, teasers, report, label):
    changed = 0
    for i, row in enumerate(rows):
        before = json.dumps(row, ensure_ascii=False, sort_keys=True)
        new = row
        if is_paywalled(new.get("source_url"), new) and new.get("derived_from") != "editorial_story_group":
            teaser = (new.get("public_teaser") if new.get("paywalled") else teasers.get(_key(new.get("source_url")), "")) \
                or listing_deck(new)
            new = redact_signal(new, teaser or "")
            report["paywalled"].append({"set": label, "source_url": new["source_url"], "has_public_teaser": bool(teaser),
                                        "redacted_fields": sorted({r["field"] for r in new["rights_redactions"]})})
        problem = source_url_problem(new.get("source_url"))
        new = sanitize_card_links(new)
        if problem:
            report["links"].append({"set": label, "source_name": new.get("source_name"), "source_url": new.get("source_url"),
                                    "problem": problem, "status": new.get("source_link_status"),
                                    "source_link": new.get("source_link")})
        if json.dumps(new, ensure_ascii=False, sort_keys=True) != before:
            rows[i] = new
            changed += 1
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    args = ap.parse_args()
    report = {"migration": "rights_links_2026_10_28", "policy": "config/paywalled_press.json",
              "links": [], "paywalled": [], "counts": {}, "not_migrated": [
                  "La Tercera bodies in data/state/pending_queue.json, data/state/pulso_discovery_cache.json and "
                  "data/audits/pulso_* (paid-revalidation receipts depend on them): Dirección decision required.",
                  "Git history keeps pre-redaction content; removing it requires a history rewrite or a private repo."]}
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    teasers = teasers_from_queue(queue)

    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    report["counts"]["history_rows_changed"] = migrate_rows(history["signals"], teasers, report, "history")

    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    report["counts"]["snapshot_cards_changed"] = migrate_rows(snapshot["signals"], teasers, report, "web_snapshot")
    report["counts"]["snapshot_link_problems_after"] = sum(len(card_link_problems(c)) for c in snapshot["signals"])

    df_items = 0
    for item in queue.values():
        raw = item.get("raw") or {}
        if item.get("source") == "diario_financiero" and purge_raw_metadata(raw):
            df_items += 1
    report["counts"]["df_queue_items_redacted"] = df_items

    audits_changed = {}
    for path in DF_AUDITS:
        payload = json.loads(path.read_text(encoding="utf-8"))
        n = purge_long_text(payload)
        if n:
            audits_changed[path] = (payload, n)
    report["counts"]["df_audit_fields_redacted"] = {str(p.relative_to(ROOT)): n for p, (_, n) in audits_changed.items()}
    report["counts"]["link_problem_rows"] = len(report["links"])
    report["counts"]["paywalled_rows"] = len(report["paywalled"])

    if args.check:
        print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
        return
    _dump(HISTORY, history)
    _dump(SNAPSHOT, snapshot)
    _dump(QUEUE, queue)
    for path, (payload, _) in audits_changed.items():
        _dump(path, payload)
    if RECEIPT.exists():
        previous = json.loads(RECEIPT.read_text(encoding="utf-8"))
        report["first_run_counts"] = previous.get("first_run_counts") or previous.get("counts")
    _dump(RECEIPT, report)
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
