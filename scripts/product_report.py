"""Generate a public, read-only operations dashboard with no credentials/PII."""
import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from radar_salud.pending_queue import PendingQueue, atomic_json
from radar_salud.isapre_insights import derive as derive_isapre_insights
from radar_salud.pmo import project as project_pmo
from radar_salud.free_value import build_free_value

def read(path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback

FEATURE_LABELS = {
    "global_intelligence": "Global Intelligence",
    "weekly_insight": "Insight Alicanto de la semana",
}
MODELS = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-6-astra")

def aggregate_usage(rows):
    costs=[x.get("cost_usd") for x in rows if x.get("cost_usd") is not None]
    output_ids={x.get("output_id") for x in rows if x.get("output_id")}
    publishable=sum(x.get("publishable") is True for x in rows)
    quality_points=sum(float(x.get("incremental_quality_points") or 0) for x in rows)
    cost=round(sum(costs),6) if rows and len(costs)==len(rows) else None
    return {
        "calls":len(rows) if rows else None,
        "input_tokens":sum(x.get("input_tokens") or 0 for x in rows) if rows else None,
        "output_tokens":sum(x.get("output_tokens") or 0 for x in rows) if rows else None,
        "cost_usd":cost,
        "cost_status":"measured" if cost is not None else "unavailable",
        "traceable_outputs":len(output_ids),
        "cost_per_output":round(cost/len(output_ids),6) if cost is not None and output_ids else None,
        "cost_per_publishable":round(cost/publishable,6) if cost is not None and publishable else None,
        "cost_per_incremental_quality_point":round(cost/quality_points,6) if cost is not None and quality_points else None,
    }

def feature_observability(responses, month, free_value):
    deterministic={
        "global_intelligence":free_value.get("global_teaser"),
        "weekly_insight":free_value.get("weekly_insight"),
    }
    result={}
    for feature,label in FEATURE_LABELS.items():
        rows=[x for x in responses if x.get("feature")==feature]
        monthly=[x for x in rows if str(x.get("at","")).startswith(month)]
        periods={}
        for key,period_rows in (("monthly",monthly),("accumulated",rows)):
            models={}
            for model in MODELS:
                # Attribute once to the actual model, falling back to requested_model.
                model_rows=[x for x in period_rows if (x.get("model") or x.get("requested_model"))==model]
                models[model]=aggregate_usage(model_rows)
            periods[key]={"label":month if key=="monthly" else "Total acumulado",
                          **aggregate_usage(period_rows),"models":models}
        trace=(deterministic.get(feature) or {}).get("model_trace") or {}
        deterministic_output=bool(trace.get("api_call") is False and trace.get("output_id"))
        result[feature]={
            "label":label,"status":"measured" if rows else ("deterministic_no_api_call" if deterministic_output else "not_measured"),
            "periods":periods,"deterministic_outputs":1 if deterministic_output else 0,
            "deterministic_output_id":trace.get("output_id") if deterministic_output else None,
            "model_used":trace.get("model") if rows else None,
            "model_status":"not_applicable_deterministic" if deterministic_output and not rows else ("measured" if rows else "unavailable"),
        }
    return result

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
    free_value = build_free_value(snapshot, read(root / "web/data/global_themes.json", {"themes": []}),
                                  read(root / "data/free_value/history.json", []))
    feature_usage = feature_observability(responses,current_month,free_value)
    fast_failed=usage.get(current_month,{}).get("fast",{}).get("failed",0)
    failure_rows=[x for x in responses if x.get("kind")=="fast" and x.get("success") is False and str(x.get("at","")).startswith(current_month)]
    error_counts=dict(Counter(x.get("error_type") or "unknown" for x in failure_rows))
    diagnostics = []
    excel_validation = read(root / "data/excel/validated_series.json", {"families": {}})
    insight_result = derive_isapre_insights(excel_validation)
    insight_summary = {"status": insight_result["status"], "count": len(insight_result["insights"]),
                       "period": insight_result.get("period"), "anomaly_checks": insight_result["anomaly_checks"]}
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
    scorecard_cfg = read(root / "config/admin_scorecard_v1.json", {"dimensions": [], "display_rules": {}})
    editorial_audit = read(root / "data/editorial_audit_90d_2026_09_26.json", {"items": []})
    audit_counts = dict(Counter((x.get("final_decision") or x.get("decision") or x.get("post_audit_state") or "unknown")
                                for x in editorial_audit.get("items", [])))
    live = [item for item in queue.items.values() if item.get("lane") == "LIVE"]
    selected_evidence = set()
    for row in snapshot.get("signals", []):
        if row.get("ingestion_mode") != "LIVE" or not row.get("detected_at"):
            continue
        selected_evidence.add((row.get("source_url"), row["detected_at"]))
        if row.get("sanction_count"):
            selected_evidence.update((x.get("url"), x.get("detected_at")) for x in row.get("source_alternatives", [])
                if x.get("ingestion_mode") == "LIVE" and x.get("detected_at"))
    coverage_live = dict(
        detected=len(live),
        evaluated=sum(item.get("status") in ("published", "rejected") for item in live),
        selected=sum(item.get("status") == "published" and
                     (item.get("raw", {}).get("url"), item.get("detected_at")) in selected_evidence
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
            historical_tokens_status="not_measured_before_0.9.0", features=feature_usage,
            unassigned_responses=sum(not x.get("feature") for x in responses)),
        excel=diagnostics, excel_validation=excel_validation, excel_insights_v1=insight_summary,
        user_telemetry="local_preferences_only_no_central_collector",
        scorecard={
            "schema_version": scorecard_cfg.get("schema_version"),
            "policy": scorecard_cfg.get("policy"),
            "display_rules": scorecard_cfg.get("display_rules", {}),
            "dimensions": scorecard_cfg.get("dimensions", []),
            "observed": {
                "development": {
                    "deployable_sha": os.environ.get("ALICANTO_CANDIDATE_SHA") or os.environ.get("GITHUB_SHA"),
                    "blocked_task_count": None,
                    "test_pass_count": None,
                },
                "operations": {
                    "source_success_rate": (round(sum((x.get("technical_status") == "ok" or
                        (not x.get("technical_status") and x.get("status") in ("ok","warning"))) for x in sources.values()) /
                        len(sources) * 100, 1) if sources else None),
                    "stale_source_count": sum(x.get("content_freshness") == "stale" for x in sources.values()),
                    "failed_run_count": discovery.get("failed_sources") if discovery else None,
                },
                "editorial_value": {
                    "accepted_signal_count": audit_counts.get("accept"),
                    "degraded_signal_count": audit_counts.get("degrade"),
                    "grouped_signal_count": audit_counts.get("group"),
                    "rejected_signal_count": audit_counts.get("reject"),
                },
                "beta_usage": {"weekly_active_readers": None, "read_rate": None, "share_rate": None},
                "conversion": {"newsletter_opt_in_rate": None, "early_access_opt_in_rate": None},
                "finops": {"monthly_authorized_cost": None, "cost_per_published_signal": None},
            },
        },
        pmo=project_pmo(baseline_path, os.environ.get("ALICANTO_CANDIDATE_SHA") or os.environ.get("GITHUB_SHA")) if baseline_path.exists() else None)
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / "free_value.json", free_value)
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
