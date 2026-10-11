"""Capture, inventory and reconcile only the four authorized occupational lanes."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
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


def editorial_input(raw):
    """A capture refresh alone does not invalidate an editorial decision."""
    value = asdict(raw) if isinstance(raw, RawItem) else raw
    meta = value.get("metadata", {})
    fields = {k: value.get(k) for k in ("source_slug", "url", "title", "event_date", "raw_text")}
    fields.update({k: meta.get(k) for k in ("page_text", "market_role", "provider_subtype", "materiality_accepted", "materiality_reason")})
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def refresh_item(item, raw):
    fresh = editorial_input(raw)
    previous = item.get("editorial_input_sha256") or editorial_input(item.get("raw", {}))
    changed = fresh != previous
    if changed:
        item.setdefault("revisions", []).append({"editorial_input_sha256": previous,
            "status": item.get("status"), "reason": item.get("reason"),
            "editorial_assessment": item.get("editorial_assessment"),
            "capture_evidence": item.get("raw", {}).get("metadata", {}).get("capture_evidence")})
        if item.get("status") != "published":
            item.update(status="pending", reason="editorial_input_revision_changed", retry_at=None)
            item.pop("editorial_assessment", None)
    item.update(raw=asdict(raw), editorial_input_sha256=fresh)
    return changed


def reconcile(root, reports, loader, *, apply=False, assessment_state=None):
    queue = PendingQueue(root / "data/state/pending_queue.json")
    baseline = copy.deepcopy(queue.items)
    baseline_by_url = {i["raw"]["url"]: i for i in baseline.values() if i.get("source") in SOURCES}
    configs = {c["slug"]: c for c in json.loads((root / "config/sources.json").read_text())}
    history = json.loads((root / "data/history/superintendencia_signals.json").read_text())
    history_rows = history if isinstance(history, list) else history.get("signals", [])
    history_by_url = {r.get("source_url") or r.get("url"): r for r in history_rows}
    totals = Counter()
    assessment_state = assessment_state if assessment_state is not None else {"failures": 0}
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
            for raw in raw_items:
                refresh_item(queue.items[fingerprint(raw)], raw)
            queue.save()
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
                if previous.get("status") == "published" or url in history_by_url:
                    row.update(alicanto_status="published", processing_reason="previous_publication_preserved",
                               current_capture_gap=row.get("reason"))
                    continue
                row["alicanto_status"] = ("pending" if row.get("status") == "pending" else
                                           "excluded" if row.get("status") == "excluded_role" else
                                           "outside_window" if not row.get("within_90_days") else "rejected")
                row["processing_reason"] = row.get("reason")
                continue
            item = queue.items.get(key, previous)
            changed = bool(previous and editorial_input(previous.get("raw", {})) != editorial_input(raw))
            row["editorial_input_changed"] = changed
            if item.get("status") == "published" or url in history_by_url:
                row.update(alicanto_status="published", processing_reason="already_published")
                continue
            if item.get("status") == "rejected" and not changed:
                row.update(alicanto_status="rejected", processing_reason=item.get("reason"), editorial_score=item.get("editorial_assessment", {}).get("score"))
                continue
            if item.get("status") == "archived" and not changed:
                row.update(alicanto_status="archived", processing_reason=item.get("reason"))
                continue
            if apply and item.get("retry_at") and item["retry_at"] > datetime.now(timezone.utc).isoformat():
                row.update(alicanto_status="deferred", processing_reason=item.get("reason"), retry_at=item["retry_at"])
                continue
            if not apply:
                row.update(alicanto_status="pending_reassessment" if changed else item.get("status", "discovered"),
                           processing_reason="editorial_input_revision_changed" if changed else "read_only_replay")
                continue
            queue.start(key)
            try:
                if assessment_state["failures"] >= 3 and raw.metadata.get("materiality_accepted"):
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
                queue.items[key]["raw"] = asdict(raw)
                queue.save()
            except DeferredProcessing as exc:
                from radar_salud.ai_budget import has_capacity
                reason = str(exc)
                if reason == "curated beta source pending assessment":
                    reason = ("analysis_api_credentials_unavailable" if not os.getenv("OPENAI_API_KEY") else
                              "analysis_budget_capacity_exhausted" if not has_capacity("fast") else reason)
                if str(exc) == "curated beta source pending assessment":
                    assessment_state["failures"] += 1
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
        row = dict(existing, name=CuratedBetaSourceScout.SOURCES[slug]["name"], checked_at=report.get("capture_checked_at") or datetime.now(timezone.utc).isoformat(),
                   recovery_outcome=outcome, status="ok" if outcome == "OPERATIVE_VALIDATED" else "warning",
                   technical_status="error" if not report["rows"] and error_count else "partial" if error_count else "ok", coverage_status="complete" if complete else "partial",
                   coverage_window=report["window"], pages_checked=len(report["pages"]),
                   recent_items=metrics, unique_items=metrics.get("90", {}).get("expected_role", 0), material_items=sum(r.get("status") == "candidate" for r in report["rows"]),
                   published=state.get("published", 0), rejected=state.get("rejected", 0), deferred=state.get("deferred", 0),
                   pending=state.get("pending", 0), technical_failures=report.get("errors", []), coverage_completeness=complete,
                   capture_environment="github_actions", capture_run_id=os.getenv("GITHUB_RUN_ID"),
                   oldest_capture_at=report.get("oldest_capture_at"), latest_capture_at=report.get("capture_checked_at"),
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


def commit_source_checkpoint(root, output, slug):
    if os.getenv("GITHUB_REF") != "refs/heads/codex/e-salud-laboral-20261011":
        raise RuntimeError("Source checkpoint commits require the authorized isolated Actions branch")
    paths = [str(output.resolve().relative_to(root.resolve())), "data/state/pending_queue.json",
             "data/history/superintendencia_signals.json", "data/source_health.json",
             "web/data/source_health.json", "data/ai_usage", "data/telemetry"]
    existing = [p for p in paths if (root / p).exists()]
    for args in (["git", "add", "--", *existing],
                 ["git", "commit", "-m", f"audit({slug}): inventory and reconciliation checkpoint {os.getenv('GITHUB_RUN_ID')}"],
                 ["git", "pull", "--rebase", "origin", "codex/e-salud-laboral-20261011"],
                 ["git", "push", "origin", "HEAD:codex/e-salud-laboral-20261011"]):
        subprocess.run(args, cwd=root, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--sync-budget", help="Read-only staging ledger; preserve the larger counter per metric")
    parser.add_argument("--replay", help="Previous inventory directory: hashes and parser replay, no network")
    parser.add_argument("--capture-cache-latest", action="store_true", help="Reuse hashed detail captures; current origin probes override cached listings")
    parser.add_argument("--as-of", help="Fixed Chile calendar date for deterministic read-only replay")
    parser.add_argument("--apply", action="store_true", help="Reconcile only these lanes into durable branch state")
    parser.add_argument("--checkpoint-commits", action="store_true", help="Persist each completed source on the authorized Actions branch")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.sync_budget:
        from radar_salud.occupational_budget import sync_budget
        upstream = json.loads(Path(args.sync_budget).read_text())
        sync_budget(upstream)
        return
    if not args.output:
        parser.error("--output is required for inventory")
    as_of = args.as_of or chile_today().isoformat()
    if args.replay and not args.as_of:
        prior_report = Path(args.replay) / "inventory.json"
        if prior_report.exists():
            as_of = json.loads(prior_report.read_text())["as_of_chile"]
    if args.apply and as_of != chile_today().isoformat():
        parser.error("Durable processing requires today's real Chile calendar; historical replay is read-only")
    if args.checkpoint_commits and (not args.apply or os.getenv("GITHUB_REF") != "refs/heads/codex/e-salud-laboral-20261011"):
        parser.error("Checkpoint commits require --apply in the isolated branch workflow")
    if args.apply:
        from radar_salud.occupational_budget import remaining_phase_calls
        os.environ["RADAR_FAST_PER_RUN"] = str(min(int(os.getenv("RADAR_FAST_PER_RUN", "30")), remaining_phase_calls()))
    output = Path(args.output)
    cache = None
    if args.capture_cache_latest:
        prior = sorted((root / "data/audits/source_e_recovery/actions").glob("*/inventory/capture_index.json"))
        cache = prior[-1].parent if prior else None
    probe = output.parent / "report.json"
    loader = CaptureLoader(output, replay=args.replay, cache=cache, probe=probe if probe.exists() else None)
    reports = {}
    from radar_salud.ai_budget import status
    before = copy.deepcopy(status())
    totals = Counter()
    assessment_state = {"failures": 0}
    from radar_salud.occupational_recovery import inventory
    for slug in sorted(SOURCES):
        scout = CuratedBetaSourceScout(slug)
        try:
            report = inventory(scout, loader, as_of=as_of)
        except Exception as exc:
            report = {"source_slug": slug, "rows": [], "raw_items": [], "pages": [], "metrics": {},
                      "coverage_complete": False, "stop_reason": "inventory_failed", "errors": [{"url": getattr(exc, "url", scout.cfg["page"]), "code": getattr(exc, "code", type(exc).__name__), "detail": str(exc)}],
                      "window": {"as_of": chile_today().isoformat(), "30": "unknown", "90": "unknown"}}
        reports[slug] = report
        urls = {p["url"] for p in report["pages"]} | {r["url"] for r in report["rows"]}
        stamps = [loader.records[u]["captured_at"] for u in urls if u in loader.records]
        report["capture_checked_at"] = max(stamps, default=None)
        report["oldest_capture_at"] = min(stamps, default=None)
        totals.update(reconcile(root, {slug:report}, loader, apply=args.apply, assessment_state=assessment_state))
        atomic_json(output / (slug + "_inventory_checkpoint.json"), report)
        if args.apply:
            save_health(root, {slug:report})
            from radar_salud.occupational_budget import checkpoint_usage
            checkpoint_usage()
        if args.checkpoint_commits:
            commit_source_checkpoint(root, output, slug)
        print(json.dumps({"source": slug, "items": len(report["rows"]), "complete": report["coverage_complete"], "stop": report.get("stop_reason")}), flush=True)
    result = {"candidate_sha": os.getenv("CANDIDATE_SHA", os.getenv("GITHUB_SHA")), "run_id": os.getenv("GITHUB_RUN_ID"),
              "captured_at": datetime.now(timezone.utc).isoformat(), "as_of_chile": as_of,
              "mode": "runtime_and_branch_reconciliation" if args.apply else "read_only_replay", "sources": reports, "processing": dict(totals)}
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
