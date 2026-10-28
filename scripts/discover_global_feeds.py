"""Licensed Global feed discovery (EMA, FDA, CDC, NIH, ECDC, EC, The Conversation, UK DHSC/MHRA; KFF discovery only): metadata + link only.

No paid AI, no bodies, no publication. Runs after WHO/PAHO discovery with its own
capture directory, budget and ledger, so it can never alter WHO/PAHO coverage contracts.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from radar_salud.global_discovery_common import FEED_HOSTS, CaptureClient
from radar_salud.global_daily_feed import export as export_daily_feed
from radar_salud.global_feed_discovery import collect_feeds, feed_health, validate_feed_config
from radar_salud.pending_queue import atomic_json

HEALTH_FILES = ("data/source_health.json", "web/data/source_health.json", "web/data/product.json")


def mirror_feed_health(root: Path, health: dict) -> None:
    for relative in HEALTH_FILES:
        path = root / relative
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        for source, row in health.items():
            payload.setdefault("sources", {})["global_" + source] = row
        atomic_json(path, payload)


# 28-oct run 40729006243: tools.cdc.gov answered HTTP 406 to the feed-only Accept header. A low-priority
# */* keeps the feed types preferred while letting servers that label RSS differently (or robots.txt as
# text/plain) answer; parse_feed still rejects any body that is not RSS/Atom/RDF.
FEED_ACCEPT = "application/rss+xml,application/atom+xml,application/xml;q=0.9,text/xml;q=0.8,*/*;q=0.1"
ROBOTS_ACCEPT = "text/plain,*/*;q=0.1"


def run(root: Path, captures: Path, as_of: date, run_id: str, client=None) -> dict:
    config = json.loads((root / "config/global_discovery.json").read_text())
    if config["paid_ai_calls"] != 0 or config["content_use"] != "metadata_and_link_only" or config["reuters"]["enabled"]:
        raise ValueError("Global discovery/publication/license contract changed")
    feeds = config.get("feeds", [])
    for feed in feeds:
        validate_feed_config(feed)
        if not set(feed["allowed_link_hosts"]) <= FEED_HOSTS:
            raise ValueError("feed host outside FEED_HOSTS allowlist")
    client = client or CaptureClient(captures / "feeds", cooldown_file=root / "data/global_intelligence/http_cooldowns.json",
                                     live_budget_seconds=config.get("feeds_live_capture_budget_seconds", 300), hosts=FEED_HOSTS,
                                     accept=FEED_ACCEPT, robots_accept=ROBOTS_ACCEPT)
    items, failures, routes = collect_feeds(config, client, as_of)
    generated = datetime.now(timezone.utc).isoformat()
    health = {}
    for feed in feeds:
        if not feed.get("enabled"):
            continue
        fetched = [r["capture"]["fetched_at"] for r in routes.values() if r["source"] == feed["id"] and r.get("capture")]
        health[feed["id"]] = feed_health(feed, items, failures, routes, as_of, max(fetched) if fetched else None)
    payload = {"schema_version": 1, "as_of": as_of.isoformat(), "generated_at": generated, "run_id": run_id,
               "network_requests": client.network_requests, "paid_ai_calls": 0, "publication_count": 0,
               "content_use": "metadata_and_link_only", "body_stored": False,
               "relevance_method": "deterministic_rules_v1_title_and_publisher_categories",
               "source_health": health, "routes": routes, "technical_failures": failures, "items": items,
               "editorial_candidates": [
                   {"item_id": r["item_id"], "source": r["source"], "attribution": r["attribution"], "bylines": r["bylines"],
                    "url": r["url"], "title": r["title"], "published_at": r["published_at"], "segments": r["classification"]["segments"],
                    "priority": r["classification"]["priority"], "status": "pending_editorial", "publication_ready": False,
                    "chile_transfer": "hypothesis_only", "requires": ["verified_business_consequence", "independent_corroboration", "rights_review", "editorial_approval"]}
                   for r in sorted(sorted(items, key=lambda r: r.get("published_at") or "", reverse=True), key=lambda r: -r["classification"]["priority"])
                   if r["classification"]["relevant"] and r["published_at"] and r["status"] == "pending"]}
    atomic_json(root / "data/global_intelligence/feed_discovery.json", payload)
    ledger_path = root / "data/global_intelligence/feed_ledger.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {"runs": []}
    ledger["runs"] = [r for r in ledger["runs"] if r["run_id"] != run_id] + [
        {"run_id": run_id, "generated_at": generated, "as_of": as_of.isoformat(), "network_requests": client.network_requests,
         "sources": {k: {f: v[f] for f in ("checked_at", "technical_status", "counts", "relevant_items", "excluded_items", "technical_failures")} for k, v in health.items()}}]
    atomic_json(ledger_path, ledger)
    mirror_feed_health(root, health)
    # Daily Global headlines (web/data/global_feed.json): feeds + activated WHO/PAHO, rights-gated, no AI.
    daily = export_daily_feed(root, as_of)
    print(json.dumps({"run_id": run_id, "items": len(items), "candidates": len(payload["editorial_candidates"]),
                      "network_requests": client.network_requests, "daily_feed_items": len(daily["items"]),
                      "daily_feed_freshness": daily["freshness"]["status"], "status": {k: v["technical_status"] for k, v in health.items()}}))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--captures", type=Path, default=Path("work/global-runtime-captures"))
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(ZoneInfo("America/Santiago")).date())
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID") or datetime.now(timezone.utc).strftime("local-%Y%m%dT%H%M%SZ"))
    args = parser.parse_args()
    run(args.root, args.captures, args.as_of, args.run_id)
