"""DF-only original/queue/history/feed reconciliation with incremental evidence.

Live execution must run on an isolated branch. Bounded inventories are explicitly
partial: neither zero results nor a green workflow proves 30/90-day completeness.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from radar_salud import engine_cli, source_scouts, public_source_pipeline
from radar_salud.df_article import parse_df_article, article_url
from radar_salud.history import load_history
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, atomic_json
from radar_salud.scouts import fetch_html
from radar_salud.source_scouts import DfHealthScout, _A


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--process-limit", type=int, default=30)
    ap.add_argument("--max-details", type=int, default=260)
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--minutes", type=int, default=12)
    ap.add_argument("--reuse-originals", action="store_true",help="Replay previously captured originals; retain their original capture timestamps")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip()
    if args.live and not branch.startswith("codex/df-"):
        ap.error("Live mutation requires isolated codex/df-* branch, never staging/main")
    os.environ["RADAR_ROOT"] = str(root)
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/Santiago")).date()
    out = root / f"data/audits/df_reconciliation_{today.isoformat().replace('-', '_')}.json"
    prior=json.loads(out.read_text()) if args.reuse_originals and out.exists() else {}
    artifacts = root / "work/df-originals"
    artifacts.mkdir(parents=True, exist_ok=True)
    report = {"at": now.isoformat(), "branch": branch,
              "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "mode": "captured_originals_replay_plus_new_fetches" if args.reuse_originals else "fresh_originals" if args.live else "stored_state_only",
              "status": "in_progress", "originals": {}, "listing_pages": [], "processing": {},
              "coverage": {"complete_30_days": False, "complete_90_days": False,
                           "limitation": "Bounded DF health/tag/Señal DF inventory plus all retained DF queue/history URLs; unenumerated originals remain unverified."}}
    atomic_json(out, report)
    queue = PendingQueue(root / "data/state/pending_queue.json")
    history = load_history(root / "data/history/superintendencia_signals.json")
    titles = {item["raw"]["url"]: item["raw"]["title"] for item in queue.items.values() if item["source"] == "diario_financiero"}
    titles.update({row["source_url"]: row["title"] for row in history if "df.cl/" in row.get("source_url", "")})
    cache = {}
    for url,original in prior.get("originals",{}).items():
        digest=original.get("sha256");path=artifacts/(str(digest)+".html")
        if original.get("fetch")=="ok" and path.exists():
            html=path.read_text()
            if hashlib.sha256(html.encode()).hexdigest()!=digest:raise ValueError("Captured DF HTML hash mismatch")
            cache[url]=html
            # Re-evaluate date/body with current code, preserve capture provenance.
            parsed=parse_df_article(html,url)
            report["originals"][url]={**original,"event_date":parsed["event_date"],
                "evidence":{k:v for k,v in parsed["metadata"].items() if k!="page_text"},"replayed_by_sha":report["code_sha"]}
    deadline = time.monotonic() + args.minutes * 60

    def capture(url):
        if url in cache:
            if isinstance(cache[url], Exception): raise cache[url]
            return cache[url]
        if time.monotonic() > deadline: raise TimeoutError("df_audit_time_bound")
        captured = datetime.now(timezone.utc).isoformat()
        try:
            html = fetch_html(url, timeout=15)
            cache[url] = html
            digest = hashlib.sha256(html.encode()).hexdigest()
            (artifacts / (digest + ".html")).write_text(html)
            parsed = parse_df_article(html, url)
            report["originals"][url] = {"captured_at": captured, "sha256": digest, "fetch": "ok",
                "event_date": parsed["event_date"], "evidence": {k: v for k, v in parsed["metadata"].items() if k != "page_text"},
                "readable_characters": len(parsed["metadata"]["page_text"]), "article_excerpt": parsed["metadata"]["page_text"][:1200]}
            atomic_json(out, report)
            return html
        except Exception as exc:
            cache[url] = exc
            report["originals"][url] = {"captured_at": captured, "fetch": "error", "error_type": type(exc).__name__, "error": str(exc)[:250]}
            atomic_json(out, report)
            raise

    raw_items = []
    if args.live:
        # Use the actual Daily scout, not an alternate parser, for the runtime proof.
        source_scouts.fetch_html = capture
        public_source_pipeline.fetch_html = capture
        try:
            raw_items = DfHealthScout().discover()
            titles.update({raw.url: raw.title for raw in raw_items})
        except Exception as exc:
            report["discovery_blocker"] = {"error_type": type(exc).__name__, "error": str(exc)}
        # Prioritize independently reported omissions, then retained queue/history.
        supplement = json.loads((root / "data/audits/work3_adversarial_2026_10_11_supplement.json").read_text())
        samples = supplement["findings"][0]["evidence"]["samples"]
        ordered = [sample["url"] for sample in samples] + list(titles)
        # Follow observable archive pagination links. Never invent article URLs.
        pages = [*DfHealthScout.PAGES, "https://www.df.cl/senal-df"]
        visited = set()
        while pages and len(visited) < args.max_pages and time.monotonic() < deadline:
            page = pages.pop(0)
            if page in visited: continue
            visited.add(page)
            try:
                html = capture(page)
                parser = _A(); parser.feed(html)
                from urllib.parse import urljoin, urlsplit
                page_articles = []
                for href, title in parser.links:
                    url = urljoin(page, href)
                    parsed = urlsplit(url)
                    if parsed.netloc not in ("df.cl", "www.df.cl"): continue
                    if re.search(r"tagport_161_\d+\.html$", parsed.path):
                        if url not in visited: pages.append(url)
                        continue
                    if len(title) < 18 or parsed.path.count("/") < 3: continue
                    if any(x in parsed.path for x in ("/tag/", "/autor/", "/tax/", "/suscripcion", "/login")): continue
                    if "/salud/" in parsed.path or public_source_pipeline._health_relevance(title, ""):
                        titles.setdefault(url, title); ordered.append(url); page_articles.append(url)
                report["listing_pages"].append({"url": page, "fetch": "ok", "health_candidate_urls": list(dict.fromkeys(page_articles))})
            except Exception as exc:
                report["listing_pages"].append({"url": page, "fetch": "error", "error_type": type(exc).__name__})
        by_url = {article_url(raw.url): raw for raw in raw_items}
        for url in dict.fromkeys(ordered):
            if time.monotonic() > deadline or len(by_url) >= args.max_details: break
            if article_url(url) in by_url and not by_url[article_url(url)].metadata.get("fetch_error"): continue
            try:
                evidence = parse_df_article(capture(url), url)
                by_url[article_url(url)] = RawItem("diario_financiero", titles.get(url, url.rsplit("/", 1)[-1]), url,
                    "Diario Financiero", "press_high_trust", evidence["event_date"], evidence["raw_text"],
                    {**evidence["metadata"], "discovered_from": "df_30_90_reconciliation"})
            except Exception: continue
        raw_items = list(by_url.values())
        if raw_items:
            watermarks = json.loads((root / "data/state/discovery_watermarks.json").read_text())
            queue.discover("diario_financiero", raw_items, now=now, last_discovered_at=watermarks.get("diario_financiero"),
                           published_urls=[row["source_url"] for row in history if row.get("source_url")])
        # Actual core engine, including real AI client and existing budget guardrails.
        # Missing credentials produce retry, never a mocked or skipped live PASS.
        argv = sys.argv
        sys.argv = ["engine_cli", "--source", "diario_financiero", "--limit", str(args.process_limit)]
        try:
            engine_cli.main()
            report["processing"]["engine_executed"] = True
        except Exception as exc:
            report["processing"].update(engine_executed=False, error_type=type(exc).__name__, error=str(exc)[:250])
        finally:
            sys.argv = argv
        report["processing"]["ai_credentials_present"] = bool(os.getenv("OPENAI_API_KEY"))
        queue = PendingQueue(queue.path)
        history = load_history(root / "data/history/superintendencia_signals.json")
    # Curate the real history using the same feed gates, without unrelated fetches.
    spec = importlib.util.spec_from_file_location("df_feed_reconciliation", root / "scripts/export_web_snapshot.py")
    exporter = importlib.util.module_from_spec(spec); spec.loader.exec_module(exporter)
    feed = exporter.curate(history, resolve_external=False)
    history_by_url = {article_url(row["source_url"]): row for row in history if "df.cl/" in row.get("source_url", "")}
    feed_urls = {article_url(row["source_url"]) for row in feed if "df.cl/" in row.get("source_url", "")}
    seen = set(json.loads((root / "data/state/diario_financiero_seen.json").read_text()))
    matrix = []
    for url in dict.fromkeys([*titles, *report["originals"]]):
        normalized = article_url(url)
        if url in DfHealthScout.PAGES or url == "https://www.df.cl/senal-df" or "tagport_" in normalized: continue
        entries = [{"fingerprint": key, "status": row["status"], "lane": row["lane"], "attempts": row["attempts"],
                    "reason": row.get("reason"), "event_date": row["raw"].get("event_date"), "detected_at": row["detected_at"],
                    "seen": key in seen, "assessment": row["raw"].get("metadata", {}).get("editorial_assessment"),
                    "recovered": bool(row.get("recovery_observations"))}
                   for key, row in queue.items.items() if row["source"] == "diario_financiero" and article_url(row["raw"]["url"]) == normalized]
        original = report["originals"].get(url, {})
        date = original.get("event_date") or history_by_url.get(normalized, {}).get("event_date")
        if not date: date = next((e["event_date"] for e in entries if e["event_date"]), None)
        terminal_reject = next((e["reason"] for e in entries if e["status"] == "rejected" and e["reason"] != "processor_rejected"), None)
        if normalized in feed_urls: disposition = "published_in_history_and_feed"
        elif normalized in history_by_url: disposition = "history_present_feed_curator_excluded"
        elif terminal_reject: disposition = "editorial_rejected:" + terminal_reject
        elif any(e["status"] == "retry" for e in entries): disposition = "technical_or_analysis_retry:" + str(next(e["reason"] for e in entries if e["status"] == "retry"))
        elif original.get("fetch") == "error": disposition = "capture_blocked:" + original["error_type"]
        elif any(e["status"] == "pending" for e in entries): disposition = "pending_processing_limit_or_budget; not_editorial_rejection"
        elif entries: disposition = "legacy_generic_rejection_unresolved; no_editorial_verdict_proven"
        else: disposition = "not_in_pipeline; capture_or_evaluation_required"
        matrix.append({"url": url, "title": titles.get(url), "publication_day": date,
                       "original": original or {"fetch": "not_attempted"}, "queue": entries,
                       "history_present": normalized in history_by_url, "feed_present": normalized in feed_urls,
                       "disposition": disposition})
    windows = {}
    for days in (30, 90):
        start = (today - timedelta(days=days - 1)).isoformat()
        rows = [row for row in matrix if row["publication_day"] and start <= row["publication_day"] <= today.isoformat()]
        windows[str(days)] = {"start": start, "end": today.isoformat(), "dated_urls": len(rows),
                             "dispositions": dict(Counter(row["disposition"] for row in rows)),
                             "unknown_date_urls": sum(not row["publication_day"] for row in matrix), "complete": False}
    report.update(status="partial_reconciliation_external_validation_open", matrix=matrix, windows=windows,
                  queue_counts=queue.counts("diario_financiero"),
                  recovered_records=sum(bool(item.get("recovery_observations")) for item in queue.items.values() if item["source"] == "diario_financiero"),
                  originals_ok=sum(row["fetch"] == "ok" for row in report["originals"].values()),
                  originals_failed=sum(row["fetch"] == "error" for row in report["originals"].values()),
                  next_action="Review every omission and date conflict against captured originals; complete archive boundaries; independent Reviewer plus full candidate gates before DF closure.")
    atomic_json(out, report)
    print(json.dumps({"artifact": str(out.relative_to(root)), "status": report["status"], "originals_ok": report["originals_ok"],
                      "originals_failed": report["originals_failed"], "recovered_records": report["recovered_records"], "queue_counts": report["queue_counts"]}))


if __name__ == "__main__": main()
