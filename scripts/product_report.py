"""Generate a public, read-only operations dashboard with no credentials/PII."""
import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from radar_salud.pending_queue import PendingQueue, atomic_json
from radar_salud.pmo import project as project_pmo

def read(path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback

def build(root, output):
    queue_path = root / "data/state/pending_queue.json"
    queue = PendingQueue(queue_path)
    discovery = read(root / "data/state/discovery_run.json", {})
    try:
        discovered_at=datetime.fromisoformat(discovery["at"].replace("Z","+00:00"))
        age=(datetime.now(timezone.utc)-discovered_at).total_seconds()
        current=discovered_at.tzinfo is not None and -300<=age<=36*3600
    except (KeyError,TypeError,ValueError):
        current=False
    measured=queue_path.exists() and current and discovery.get("successful_sources",0)>0
    health = read(root / "data/source_health.json", {"sources": {}})
    sources=dict(health.get("sources", {}))
    # Retain the legacy poll in raw evidence, but never count the renamed
    # statistics collector twice once the global collector has run.
    if "superintendencia" in sources:
        sources.pop("superintendencia_stats", None)
    snapshot = read(root / "web/data/radar_today.json", {"signals": []})
    history = read(root / "data/history/superintendencia_signals.json", {"signals": []})
    history = history.get("signals", []) if isinstance(history, dict) else history
    responses_path = root / "data/ai_usage/responses.jsonl"
    responses = [json.loads(line) for line in responses_path.read_text().splitlines() if line] if responses_path.exists() else []
    usage = {p.stem: read(p, {}) for p in (root / "data/ai_usage").glob("*.json")}
    current_month=datetime.now(timezone.utc).strftime("%Y-%m")
    fast_failed=usage.get(current_month,{}).get("fast",{}).get("failed",0)
    failure_rows=[x for x in responses if x.get("kind")=="fast" and x.get("success") is False and str(x.get("at","")).startswith(current_month)]
    error_counts=dict(Counter(x.get("error_type") or "unknown" for x in failure_rows))
    diagnostics = []
    excel_validation = read(root / "data/excel/validated_series.json", {"families": {}})
    for row in history:
        if "Datos" not in row.get("signal_types", []) and not row.get("data_insight_meta"):
            continue
        meta = row.get("data_insight_meta") or {}
        diagnostics.append({"title": row.get("title"), "source_url": row.get("source_url"),
            "status": meta.get("status", "not_recorded_legacy"), "family": meta.get("family"),
            "sheet": meta.get("sheet"), "period": meta.get("period"),
            "insights": len(row.get("data_insights") or [])})
    ledger = read(root / "data/autopilot/ledger.json", {"iterations": []})
    baseline_path = root / "config/pmo_baseline.json"
    live = [item for item in queue.items.values() if item.get("lane") == "LIVE"]
    selected_urls = set()
    for row in snapshot.get("signals", []):
        if row.get("ingestion_mode") != "LIVE":
            continue
        selected_urls.add(row.get("source_url"))
        if row.get("sanction_count"):
            selected_urls.update(x.get("url") for x in row.get("source_alternatives", []))
    coverage_live = dict(
        detected=len(live),
        evaluated=sum(item.get("status") in ("published", "rejected") for item in live),
        selected=sum(item.get("status") == "published" and item.get("raw", {}).get("url") in selected_urls
                     for item in live),
    ) if measured else None
    report = dict(version="0.9.0", generated_at=datetime.now(timezone.utc).isoformat(),
        snapshot_at=snapshot.get("generated_at"), published=len(snapshot.get("signals", [])),
        queue=queue.counts() if measured else None,
        queue_status="measured" if measured else "awaiting_successful_global_discovery",
        discovery=discovery,
        coverage_live=coverage_live,
        legacy_pending=sum(x.get("pending", 0) for x in sources.values()),
        sources=sources, iterations=ledger["iterations"],
        usage=dict(calls=usage, measured_responses=len(responses),
            input_tokens=sum(x.get("input_tokens") or 0 for x in responses),
            output_tokens=sum(x.get("output_tokens") or 0 for x in responses),
            models=dict(Counter(x.get("model") or "unknown" for x in responses)),
            errors=error_counts, fast_failed=fast_failed,
            fast_unclassified=max(0,fast_failed-len(failure_rows)),
            cost_usd=None, cost_status="unavailable_without_approved_rates",
            historical_tokens_status="not_measured_before_0.9.0"),
        excel=diagnostics, excel_validation=excel_validation, user_telemetry="local_preferences_only_no_central_collector",
        pmo=project_pmo(baseline_path, os.environ.get("ALICANTO_CANDIDATE_SHA") or os.environ.get("GITHUB_SHA")) if baseline_path.exists() else None)
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / "product.json", report)
    # Same canonical validation records shown in the dashboard. Historical
    # publication diagnostics live in product.json and must not masquerade as
    # the current workbook validation in this CSV.
    with (output / "excel_diagnostics.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        cols=["family", "status", "source_url", "sha256", "periods", "period_start", "period_end", "period_type", "error"]
        writer=csv.DictWriter(stream, fieldnames=cols)
        writer.writeheader()
        for family, row in sorted(excel_validation.get("families", {}).items()):
            series=row.get("series") or []
            last=series[-1] if series else {}
            entry={"family":family,"status":row.get("status"),"source_url":row.get("source_url"),
                   "sha256":row.get("sha256"),"periods":len(series),
                   "period_start":last.get("period_start") or (series[0].get("period") if series else None),
                   "period_end":last.get("period_end") or last.get("period"),
                   "period_type":last.get("period_type") or ("monthly_series" if series else None),
                   "error":row.get("error")}
            writer.writerow({k: "'"+v if isinstance(v,str) and v.startswith(("=","+","-","@")) else v for k,v in entry.items()})
    return report

if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",default=".");parser.add_argument("--output",default="web/data")
    args=parser.parse_args();build(Path(args.root),Path(args.output))
