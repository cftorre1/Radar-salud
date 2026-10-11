"""Capture, inventory and reconcile only the four authorized occupational lanes."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from radar_salud.occupational_capture import CaptureLoader

from radar_salud.beta_sources import CuratedBetaSourceScout, process_curated_beta_source
from radar_salud.models import RawItem
from radar_salud.occupational_sources import SOURCES, SourceDiscoveryError, chile_today, valid_date
from radar_salud.pending_queue import PendingQueue, atomic_json, fingerprint
from radar_salud.processing import DeferredProcessing



def reconcile(root, reports, loader, *, apply=False):
    queue = PendingQueue(root / "data/state/pending_queue.json")
    baseline = copy.deepcopy(queue.items)
    baseline_by_url = {i["raw"]["url"]: i for i in baseline.values() if i.get("source") in SOURCES}
    configs = {c["slug"]: c for c in json.loads((root / "config/sources.json").read_text())}
    history = json.loads((root / "data/history/superintendencia_signals.json").read_text())
    history_rows = history if isinstance(history, list) else history.get("signals", [])
    history_by_url = {r.get("source_url") or r.get("url"): r for r in history_rows}
    totals = Counter()
    assessment_failures = 0
    for slug, report in reports.items():
        raw_items = report.pop("raw_items", [])
        raw_by_url = {raw.url: raw for raw in raw_items}
        for raw in raw_items:
            if raw.url in loader.records:
                raw.metadata["capture_evidence"] = loader.evidence(raw.url)
            listing_url = raw.metadata.get("discovered_from")
            if listing_url in loader.records:
                raw.metadata["listing_capture_evidence"] = loader.evidence(listing_url)
        added = 0
        if apply:
            added = queue.discover(slug, raw_items)
        report["newly_discovered"] = added
        for row in report["rows"]:
            url = row.get("url")
            raw = raw_by_url.get(url)
            key = fingerprint(raw) if raw else None
            previous = baseline.get(key, baseline_by_url.get(url, {}))
            row["alicanto_before"] = previous.get("status", "not_detected")
            in_scope = row.get("within_90_days") and row.get("status") != "excluded_role"
            row["omitted_before"] = bool(in_scope and not previous and url not in history_by_url)
            row["ingestion_mode"] = "BACKFILL" if raw else None
            row["editorial_score"] = None
            if not raw:
                row["alicanto_status"] = ("pending" if row.get("status") == "pending" else
                                           "excluded" if row.get("status") == "excluded_role" else
                                           "outside_window" if not row.get("within_90_days") else "rejected")
                row["processing_reason"] = row.get("reason")
                continue
            item = queue.items.get(key, previous)
            if item.get("status") == "published" or url in history_by_url:
                row.update(alicanto_status="published", processing_reason="already_published")
                continue
            if item.get("status") == "rejected":
                row.update(alicanto_status="rejected", processing_reason=item.get("reason"), editorial_score=item.get("editorial_assessment", {}).get("score"))
                continue
            if item.get("status") == "archived":
                row.update(alicanto_status="archived", processing_reason=item.get("reason"))
                continue
            if apply and item.get("retry_at") and item["retry_at"] > datetime.now(timezone.utc).isoformat():
                row.update(alicanto_status="deferred", processing_reason=item.get("reason"), retry_at=item["retry_at"])
                continue
            if not apply:
                row.update(alicanto_status=item.get("status", "discovered"), processing_reason="read_only_replay")
                continue
            queue.start(key)
            try:
                if assessment_failures >= 3 and raw.metadata.get("materiality_accepted"):
                    raise DeferredProcessing("analysis_failure_limit_reached_after_three_attempts")
                result = process_curated_beta_source(raw, configs[slug])
                if raw.metadata.get("editorial_assessment"):
                    row["editorial_score"] = raw.metadata["editorial_assessment"]["score"]
                    queue.items[key]["editorial_assessment"] = raw.metadata["editorial_assessment"]
                if result:
                    from radar_salud.history import merge_history, save_history
                    result.update(detected_at=item["detected_at"], ingestion_mode=item["lane"])
                    history_rows = merge_history(history_rows, [result])
                    save_history(root / "data/history/superintendencia_signals.json", history_rows)
                    queue.finish(key, "published")
                    row.update(alicanto_status="published", editorial_score=result.get("editorial_relevance"), processing_reason="editorially_accepted")
                else:
                    reason = raw.metadata.get("publication_rejection_reason", "processor_rejected")
                    queue.finish(key, "rejected", reason)
                    row.update(alicanto_status="rejected", processing_reason=reason)
            except DeferredProcessing as exc:
                from radar_salud.ai_budget import has_capacity
                reason = str(exc)
                if reason == "curated beta source pending assessment":
                    reason = ("analysis_api_credentials_unavailable" if not os.getenv("OPENAI_API_KEY") else
                              "analysis_budget_capacity_exhausted" if not has_capacity("fast") else reason)
                if str(exc) == "curated beta source pending assessment":
                    assessment_failures += 1
                queue.finish(key, "retry", reason)
                row.update(alicanto_status="deferred", processing_reason=reason)
            except Exception as exc:
                queue.finish(key, "retry", type(exc).__name__)
                row.update(alicanto_status="deferred", processing_reason=str(exc))
            totals[row["alicanto_status"]] += 1
        report["reconciliation"] = {
            "omitted_before": sum(bool(r.get("omitted_before")) for r in report["rows"]),
            "material_omitted_before": sum(bool(r.get("omitted_before")) and r.get("status") == "candidate" for r in report["rows"]),
            "states": dict(Counter(r["alicanto_status"] for r in report["rows"])),
            "detected_before": sum(bool(r.get("within_90_days")) and r.get("status") != "excluded_role" and r["alicanto_before"] != "not_detected" for r in report["rows"]),
        }
        report["raw_items"] = [asdict(raw) for raw in raw_items]
    return dict(totals)


def save_health(root, reports):
    backend = json.loads((root / "data/source_health.json").read_text())
    web = json.loads((root / "web/data/source_health.json").read_text())
    for slug, report in reports.items():
        existing = backend.setdefault("sources", {}).get(slug, {})
        metrics = report.get("metrics", {})
        state = report["reconciliation"]["states"]
        complete = report.get("coverage_complete", False)
        error_count = len(report.get("errors", []))
        outcome = "OPERATIVE_VALIDATED" if complete and not error_count and not state.get("deferred") else "OPERATIVE_DEGRADED"
        if not report["rows"] and error_count:
            outcome = "VALIDATION_PENDING"
        row = dict(existing, name=CuratedBetaSourceScout.SOURCES[slug]["name"], checked_at=datetime.now(timezone.utc).isoformat(),
                   recovery_outcome=outcome, status="ok" if outcome == "OPERATIVE_VALIDATED" else "warning",
                   technical_status="error" if not report["rows"] and error_count else "partial" if error_count else "ok", coverage_status="complete" if complete else "partial",
                   coverage_window=report["window"], pages_checked=len(report["pages"]),
                   recent_items=metrics, unique_items=metrics.get("90", {}).get("expected_role", 0), material_items=sum(r.get("status") == "candidate" for r in report["rows"]),
                   published=state.get("published", 0), rejected=state.get("rejected", 0), deferred=state.get("deferred", 0),
                   pending=state.get("pending", 0), technical_failures=report.get("errors", []), coverage_completeness=complete,
                   capture_environment="github_actions", capture_run_id=os.getenv("GITHUB_RUN_ID"),
                   discovered=len(report.get("raw_items", [])), new=report.get("newly_discovered", 0),
                   count_basis="unique source items in rolling 90 days; published includes previously reconciled items",
                   error=report.get("errors") or None,
                   latest_detected_at=max((r.get("publication_date") or r.get("event_date") or "" for r in report["rows"] if r.get("status") != "excluded_role"), default=None),
                   last_signal_at=max((r.get("publication_date") or r.get("event_date") or "" for r in report["rows"] if r.get("alicanto_status") == "published"), default=None),
                   editorial_outcome="pending" if state.get("deferred") else "published" if state.get("published") else "rejected")
        backend["sources"][slug] = row
        web.setdefault("sources", {})[slug] = row
    backend["occupational_sources_checked_at"] = web["occupational_sources_checked_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(root / "data/source_health.json", backend)
    atomic_json(root / "web/data/source_health.json", web)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--sync-budget", help="Read-only staging ledger; preserve the larger counter per metric")
    parser.add_argument("--replay", help="Previous inventory directory: hashes and parser replay, no network")
    parser.add_argument("--apply", action="store_true", help="Reconcile only these lanes into durable branch state")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.sync_budget:
        from radar_salud.ai_budget import _load, _save
        upstream = json.loads(Path(args.sync_budget).read_text())
        local = _load()
        for kind in ("fast", "deep"):
            if not isinstance(upstream.get(kind), dict):
                raise ValueError("Upstream AI ledger invalid; no processing authorized")
            for metric in ("attempted", "successful", "failed"):
                local[kind][metric] = max(local[kind][metric], int(upstream[kind][metric]))
        _save(local)
        return
    if not args.output:
        parser.error("--output is required for inventory")
    output = Path(args.output)
    loader = CaptureLoader(output, replay=args.replay)
    reports = {}
    from radar_salud.occupational_inventory import discover_inventory
    from radar_salud.mutual_sources import MutualNewsScout
    for slug in sorted(SOURCES):
        scout = CuratedBetaSourceScout(slug)
        try:
            report = (MutualNewsScout(fetcher=loader).discover_inventory() if slug == "mutual_seguridad"
                      else discover_inventory(scout, loader))
        except Exception as exc:
            report = {"source_slug": slug, "rows": [], "raw_items": [], "pages": [], "metrics": {},
                      "coverage_complete": False, "stop_reason": "inventory_failed", "errors": [{"url": getattr(exc, "url", scout.cfg["page"]), "code": getattr(exc, "code", type(exc).__name__), "detail": str(exc)}],
                      "window": {"as_of": chile_today().isoformat(), "30": "unknown", "90": "unknown"}}
        reports[slug] = report
        if slug == "clinicas_achs_salud":
            report["newsroom_coverage_complete"] = report["coverage_complete"]
            report["coverage_complete"] = False
            report["errors"].append({"code": "additional_clinical_surfaces_pending", "url": "https://www.achssalud.cl/blog",
                                     "detail": "Clinical newsroom inventory alone does not validate the separately hosted blog or clinic portal"})
        if slug == "ist":
            report["newsroom_coverage_complete"] = report["coverage_complete"]
            report["coverage_complete"] = False
            report["errors"].append({"code": "official_api_reconciliation_pending", "url": "https://ist.cl/wp-json/wp/v2/posts",
                                     "detail": "REST lists an additional dated sustainability report outside the news archive"})
        print(json.dumps({"source": slug, "items": len(report["rows"]), "complete": report["coverage_complete"], "stop": report.get("stop_reason")}), flush=True)
    from radar_salud.ai_budget import status
    before = copy.deepcopy(status())
    totals = reconcile(root, reports, loader, apply=args.apply)
    result = {"candidate_sha": os.getenv("GITHUB_SHA"), "run_id": os.getenv("GITHUB_RUN_ID"),
              "captured_at": datetime.now(timezone.utc).isoformat(), "as_of_chile": chile_today().isoformat(),
              "mode": "runtime_and_branch_reconciliation" if args.apply else "read_only_replay", "sources": reports, "processing": totals}
    result["editorial_runtime"] = {"credentials_available": bool(os.getenv("OPENAI_API_KEY")),
                                   "model": os.getenv("RADAR_FAST_MODEL", "gpt-5.6-luna"), "budget_before": before,
                                   "budget_after": status(), "same_failure_limit": 3}
    atomic_json(output / "inventory.json", result)
    if args.apply:
        atomic_json(root / "data/state/occupational_source_discovery.json", result)
        save_health(root, reports)
    print(json.dumps({"sources": {s: {"metrics": r["metrics"], "reconciliation": r["reconciliation"], "coverage_complete": r["coverage_complete"]} for s, r in reports.items()}, "processing": totals}), flush=True)


if __name__ == "__main__":
    main()
