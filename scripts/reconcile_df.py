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
from radar_salud.df_recovery import published_history_urls, resume_withdrawn_reassessments
from radar_salud.history import load_history, save_history
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, atomic_json
from radar_salud.scouts import fetch_html
from radar_salud.source_scouts import DfHealthScout, _A
from radar_salud.df_inventory import DfListing


def read_captured_html(path, expected_sha256):
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=expected_sha256:
        raise ValueError("Captured DF HTML hash mismatch")
    return payload.decode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--process-limit", type=int, default=30)
    ap.add_argument("--max-details", type=int, default=260)
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--minutes", type=int, default=12)
    ap.add_argument("--reuse-originals", action="store_true",help="Replay previously captured originals; retain their original capture timestamps")
    ap.add_argument("--capture-fixtures", action="store_true",help="Save publisher markup samples for date/body regressions")
    ap.add_argument("--capture-only",action="store_true",help="Reconcile/capture without consuming an AI processing slot")
    ap.add_argument("--repair-contaminated-bodies",action="store_true",help="Trace and re-evaluate old decisions based on unrelated recommendation text")
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
    queue = PendingQueue(root / "data/state/pending_queue.json")
    history = load_history(root / "data/history/superintendencia_signals.json")
    titles = {item["raw"]["url"]: item["raw"]["title"] for item in queue.items.values() if item["source"] == "diario_financiero"}
    titles.update({row["source_url"]: row["title"] for row in history if "df.cl/" in row.get("source_url", "")})
    cache = {}
    for url,original in prior.get("originals",{}).items():
        digest=original.get("sha256");path=artifacts/(str(digest)+".html")
        if original.get("fetch")=="ok" and path.exists():
            html=read_captured_html(path,digest)
            cache[url]=html
            # Re-evaluate date/body with current code, preserve capture provenance.
            parsed=parse_df_article(html,url)
            report["originals"][url]={**original,"event_date":parsed["event_date"],
                "evidence":{k:v for k,v in parsed["metadata"].items() if k!="page_text"},"replayed_by_sha":report["code_sha"],
                "readable_characters":len(parsed["metadata"]["page_text"]),"article_excerpt":parsed["metadata"]["page_text"][:1200]}
    atomic_json(out, report)
    if args.capture_fixtures:
        samples={"df_san_carlos_real":"aluvion-en-las-condes-obliga-a-cerrar-por-semanas-la-clinica-san-carlos",
                 "df_catastrofe_real":"kast-decreta-estado-de-catastrofe-tras-aluvion-en-las-condes-que-deja-al",
                 "df_ricarte_real":"recortes-a-la-ley-ricarte-soto-es-un-ahorro-mal-entendido",
                 "df_biometria_real":"super-de-salud-cuando-no-se-reconoce-la-huella-digital-la-isapre-debera",
                 "df_health_listing_real":"/empresas/dfsalud",
                 "df_health_tag_real":"/tagport_161_1.html"}
        fixture_manifest={}
        for name,suffix in samples.items():
            for url,html in cache.items():
                if url.endswith(suffix):
                    # Retain original meta/JSON-LD/article markup; omit executable
                    # scripts/styles/comments. These are marked as source excerpts.
                    excerpt=re.sub(r"<script\b(?![^>]*application/ld\+json)[^>]*>.*?</script>","",html,flags=re.I|re.S)
                    excerpt=re.sub(r"<style\b[^>]*>.*?</style>|<!--.*?-->","",excerpt,flags=re.I|re.S)
                    path=root/"tests/fixtures"/(name+".html");path.write_bytes(excerpt.encode())
                    fixture_manifest[name]={"url":url,"original_sha256":report["originals"][url]["sha256"],
                         "captured_at":report["originals"][url]["captured_at"],"excerpt_sha256":hashlib.sha256(excerpt.encode()).hexdigest(),
                         "transformation":"Removed non-JSON-LD scripts/styles/comments; retained source article/navigation/recommendation markup"}
        atomic_json(root/"tests/fixtures/df_original_manifest.json",fixture_manifest)
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
        # Additional health tags must be observed on an original page, not
        # guessed URLs. These surfaces may expose archive navigation absent
        # from the current health landing page.
        from urllib.parse import urljoin, urlsplit, urldefrag
        for parent,html in list(cache.items()):
            if not isinstance(html,str):continue
            links=_A();links.feed(html)
            for href,label in links.links:
                url=urldefrag(urljoin(parent,href))[0]
                path=urlsplit(url).path
                if urlsplit(url).netloc in ('df.cl','www.df.cl') and ('/tags/' in path or '/tag/' in path) and re.fullmatch(r'\s*(salud|isapres?|fonasa|clínicas?|clinicas?|df salud)\s*',label,re.I):
                    if url not in pages:pages.append(url)
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
                listing=DfListing();listing.feed(html)
                links=[*listing.primary_links,*listing.pagination] if listing.has_primary_layout else parser.links
                for href, title in links:
                    url = urldefrag(urljoin(page, href))[0]
                    parsed = urlsplit(url)
                    if parsed.netloc not in ("df.cl", "www.df.cl"): continue
                    if re.search(r"tagport_(161|121|2150)_\d+\.html$", parsed.path) or re.search(r'/tags/(salud|isapres?|fonasa)/p/\d+/?$',parsed.path):
                        if url not in visited: pages.append(url)
                        continue
                    if len(title) < 18 or parsed.path.count("/") < 3 or re.search(r"/p/\d+/?$",parsed.path): continue
                    if any(x in parsed.path for x in ("/tag/", "/autor/", "/tax/", "/suscripcion", "/login")): continue
                    health_surface=bool(re.search(r'/tags/(salud|isapres?|fonasa)(?:/|$)|tagport_(161|121|2150)_',urlsplit(page).path)) or page==DfHealthScout.PAGES[0]
                    if health_surface or "/salud/" in parsed.path or public_source_pipeline._health_relevance(title, ""):
                        titles.setdefault(url, title); ordered.append(url); page_articles.append(url)
                controls=[m[0][:700] for m in re.finditer(r'<(?:button|a|div)\b[^>]*(?:pagin|cargar|load.more|ver.mas)[^>]*>',html,re.I)]
                scripts=re.findall(r'<script\b[^>]*src=["\']([^"\']+)',html,re.I)
                report["listing_pages"].append({"url": page, "fetch": "ok", "health_candidate_urls": list(dict.fromkeys(page_articles)),
                    "observed_archive_controls":controls[:12],"observed_script_urls":[urljoin(page,s) for s in scripts if 'df.cl' in urljoin(page,s)]})
                # Follow adjacent archive pages before the footer's jump to page
                # 25; both are observable links, but the former covers the gap.
                def page_number(u):
                    m=re.search(r'(?:/p/|tagport_\d+_)(\d+)(?:\.html)?$',urlsplit(u).path)
                    return int(m[1]) if m else 1
                pages.sort(key=page_number)
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
        for raw in raw_items:
            original=report["originals"].get(raw.url,{})
            raw.metadata.update(original_sha256=original.get("sha256"),original_captured_at=original.get("captured_at"))
        if args.repair_contaminated_bodies:
            from radar_salud.df_recovery import repair_contaminated_evidence
            report["withdrawn_reassessment_recovery"]=resume_withdrawn_reassessments(queue,history,now)
            report["body_reaudit"]=repair_contaminated_evidence(queue,raw_items,history,now)
            save_history(root/"data/history/superintendencia_signals.json",history)
            atomic_json(out,report)
        watermarks = json.loads((root / "data/state/discovery_watermarks.json").read_text())
        if raw_items:
            queue.discover("diario_financiero", raw_items, now=now, last_discovered_at=watermarks.get("diario_financiero"),
                           published_urls=published_history_urls(history))
        # Actual core engine, including real AI client and existing budget guardrails.
        # Missing credentials produce retry, never a mocked or skipped live PASS.
        argv = sys.argv
        sys.argv = ["engine_cli", "--source", "diario_financiero", "--limit", str(args.process_limit)]
        try:
            if args.capture_only:
                report["processing"].update(engine_executed=False,reason="explicit_capture_only; prior actual processing outcomes retained")
            else:
                engine_cli.main()
                report["processing"]["engine_executed"] = True
        except Exception as exc:
            report["processing"].update(engine_executed=False, error_type=type(exc).__name__, error=str(exc)[:250])
        finally:
            sys.argv = argv
        report["processing"]["ai_credentials_present"] = bool(os.getenv("OPENAI_API_KEY"))
        if args.reuse_originals:
            # A cache replay is processing evidence, not a fresh publisher poll.
            # Preserve actual original capture times in the public health facet.
            health_path=root/"data/source_health.json"
            health=json.loads(health_path.read_text())
            facet=health['sources']['diario_financiero']
            polls=[report['originals'].get(url,{}).get('captured_at') for url in DfHealthScout.PAGES]
            polls=[stamp for stamp in polls if stamp]
            facet.update(runtime_checked_at=facet.get('checked_at'),source_poll_mode=report['mode'],
                         original_listing_capture_times={url:report['originals'].get(url,{}).get('captured_at') for url in DfHealthScout.PAGES},
                         coverage_complete_30_days=False,coverage_complete_90_days=False)
            if polls:facet['checked_at']=max(polls)
            atomic_json(health_path,health)
            watermark_path=root/'data/state/discovery_watermarks.json'
            after=json.loads(watermark_path.read_text())
            if 'diario_financiero' in watermarks:after['diario_financiero']=watermarks['diario_financiero']
            atomic_json(watermark_path,after)
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
        if url in DfHealthScout.PAGES or url == "https://www.df.cl/senal-df" or "tagport_" in normalized or url in {p['url'] for p in report['listing_pages']}: continue
        entries = [{"fingerprint": key, "status": row["status"], "lane": row["lane"], "attempts": row["attempts"],
                    "reason": row.get("reason"), "event_date": row["raw"].get("event_date"), "detected_at": row["detected_at"],
                    "seen": key in seen, "assessment": row["raw"].get("metadata", {}).get("editorial_assessment"),
                    "recovered": bool(row.get("recovery_observations"))}
                   for key, row in queue.items.items() if row["source"] == "diario_financiero" and article_url(row["raw"]["url"]) == normalized]
        original = report["originals"].get(url, {})
        date = original.get("event_date") or history_by_url.get(normalized, {}).get("event_date")
        if not date: date = next((e["event_date"] for e in entries if e["event_date"]), None)
        terminal_reject = next((e["reason"] for e in entries if e["status"] == "rejected" and e["reason"] != "processor_rejected"), None)
        reviewed=history_by_url.get(normalized,{})
        if reviewed.get("df_body_reaudit_status") and reviewed.get("editorial_decision")=="reject":
            disposition="withdrawn_capture_defect:"+str(reviewed.get("df_body_reaudit_reason"))
        elif normalized in feed_urls: disposition = "published_in_history_and_feed"
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
