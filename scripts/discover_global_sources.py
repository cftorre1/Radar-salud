"""Recurring metadata discovery; has no AI or publication authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from radar_salud.global_discovery_common import CaptureClient
from radar_salud.global_source_discovery import discover, in_window, deduplicate_translations
from radar_salud.pending_queue import atomic_json

def write(root, relative, payload):
    atomic_json(root / relative, payload)

def health_counts(items, as_of):
    return {str(days): sum(row.get("detail_verified", False) and in_window(row["published_at"], as_of, days) for row in items) for days in (30,90)}

def new_identity_count(items, prior_items, source):
    previous={alias for old in prior_items if old["source"]==source for alias in old.get("source_aliases",[old["url"]])}
    return sum(not set(item["source_aliases"]) & previous for item in items)

def window_boundary_verified(route, as_of, days):
    if route.get("date_partitions"):
        slices=sorted(route["date_partitions"],key=lambda s:s["from"])
        return bool(route["archive_complete"] and not route.get("unvisited_partitions") and all(s["archive_complete"] for s in slices)
            and slices[0]["from"]<=(as_of-timedelta(days=days-1)).isoformat() and slices[-1]["to"]>=as_of.isoformat()
            and all(date.fromisoformat(a["to"])+timedelta(days=1)==date.fromisoformat(b["from"]) for a,b in zip(slices,slices[1:])))
    dates=[row["index_published_at"] for row in route["items"]]
    return bool(dates and all(dates) and dates==sorted(dates,reverse=True)
                and min(dates)<(as_of-timedelta(days=days-1)).isoformat())

def cadence_is_valid(ledger, source, checked, run_id, complete, cadence_seconds, replay=False, contract_id=None):
    if replay or not complete or not checked or not contract_id:
        return False
    for row in ledger["runs"]:
        previous = row.get("sources", {}).get(source, {})
        prior = previous.get("checked_at")
        if row["run_id"] != run_id and row.get("mode")=="live_discovery" and row.get("capture_reuse",{}).get("reused_url_count")==0 and previous.get("coverage_completeness") == "complete" and previous.get("coverage_contract_id") == contract_id and prior:
            if (datetime.fromisoformat(checked)-datetime.fromisoformat(prior)).total_seconds() >= cadence_seconds:
                return True
    return False

def mirror_health(root, source_health):
    if set(source_health) != {"who", "paho", "reuters"}:
        raise ValueError("unexpected owned Global health sources")
    for path in ("data/source_health.json", "web/data/source_health.json", "web/data/product.json"):
        health=json.loads((root/path).read_text())
        for source, row in source_health.items(): health["sources"]["global_"+source]=row
        write(root,path,health)

def run(root: Path, captures: Path, as_of: date, run_id: str, replay: Path | None = None, resume: bool = False):
    config = json.loads((root / "config/global_discovery.json").read_text())
    if config["default_window_days"] != 30 or config["maximum_editorial_topics"] != 10 or config["fill_quota"] or config["paid_ai_calls"] != 0 or config["reuters"]["enabled"]:
        raise ValueError("Global discovery/publication/license contract changed")
    client = CaptureClient(captures, replay=replay, cooldown_file=root/"data/global_intelligence/http_cooldowns.json",resume=resume,
                           live_budget_seconds=config['live_capture_budget_seconds'])
    prior_discovery_path = root / "data/global_intelligence/discovery.json"
    prior_items = json.loads(prior_discovery_path.read_text()).get("items",[]) if prior_discovery_path.exists() else []
    routes, language_items, failures = discover(config, client, as_of)
    items=deduplicate_translations(language_items)
    generated = datetime.now(timezone.utc).isoformat()
    evidence = Path("data/audits/global_source_recovery_2026_10_11/runs") / run_id
    source_health = {}
    prior_path = root / "data/global_intelligence/ledger.json"
    ledger = json.loads(prior_path.read_text()) if prior_path.exists() else {"runs": []}
    for source in ("who", "paho"):
        contract_id=hashlib.sha256(json.dumps({"qualification_version":2,"inventory_days":90,"routes":[route for route in config["routes"] if route["source"]==source]},sort_keys=True).encode()).hexdigest()
        source_items = [item for item in items if item["source"] == source]
        source_routes = [route for route in routes if route["route"]["source"] == source]
        technical = [f for f in failures if f["route"]["source"] == source] + [{"url": item["url"], "error": item["technical_error"]} for item in language_items if item["source"] == source and item.get("technical_error")]
        pending_dates = [item for item in source_items if not item["published_at"]]
        complete = len(source_routes) == len([r for r in config["routes"] if r["source"] == source]) and all(r["archive_complete"] and not r["date_pending"] for r in source_routes) and not pending_dates and not technical
        dates = [r["fetched_at"] for r in client.records.values() if ("who.int" if source == "who" else "paho.org") in r["requested_url"]]
        checked = max(dates) if dates else None
        counts = health_counts(source_items, as_of)
        indexed_counts = {str(days): sum(in_window(row["index_published_at"], as_of, days) for row in source_items) for days in (30,90)}
        material = [item for item in source_items if item["classification"]["materiality"] == "candidate" and item["detail_verified"] and item["published_at"]]
        detected_urls={alias for item in source_items for alias in item["source_aliases"]}
        recalls={}
        windows={}
        for days in (30,90):
            control_urls={row["url"] for route in source_routes for page in route["pages"] for row in page.get("native_control",[]) if in_window(row["published_at"],as_of,days)}
            recalls[str(days)]={"basis":"independent_native_index_control_on_declared_surfaces", "inventory_url_count":len(control_urls), "detected":len(control_urls & detected_urls),"omitted_urls":sorted(control_urls-detected_urls),"recall":len(control_urls&detected_urls)/len(control_urls) if control_urls else None,"whole_source_archive_claim":False}
            expected=len([route for route in config["routes"] if route["source"]==source])
            windows[str(days)]="complete_on_declared_surfaces" if len(source_routes)==expected and not technical and not pending_dates and all(window_boundary_verified(route,as_of,days) for route in source_routes) and not control_urls-detected_urls else "incomplete_lower_bound"
            if control_urls-detected_urls:complete=False
        cadence_validated = cadence_is_valid(ledger,source,checked,run_id,complete,config["cadence_seconds"],replay or resume,contract_id)
        source_health[source] = {
            "name": source.upper(), "checked_at": checked, "status": "ok" if complete and cadence_validated else "warning" if source_routes else "error",
            "technical_status": "error" if technical else "ok", "coverage_status": "complete" if complete else "incomplete",
            "outcome": "READY_FOR_INTEGRATION" if complete else "IMPLEMENTED_WITH_DECLARED_COVERAGE_GAPS",
            "operation_mode": "isolated_qualification", "discovery_scope": "global_intelligence", "recurrent_operation_proven": cadence_validated,
            "cadence_seconds": config["cadence_seconds"], "cadence_validation_pending": not cadence_validated,
            "coverage_contract_id":contract_id,
            "next_cadence_validation_not_before": (datetime.fromisoformat(checked)+timedelta(seconds=config["cadence_seconds"])).isoformat() if checked and not cadence_validated else None,
            "coverage_completeness": "complete" if complete else "incomplete", "coverage_window_days": 90,
            "coverage_from": (as_of - timedelta(days=89)).isoformat(), "coverage_to": as_of.isoformat(),
            "pages_checked": sum(len(route["pages"]) for route in source_routes), "recent_items": counts["30"],
            "discovery_recall_30":recalls["30"],"discovery_recall_90":recalls["90"],
            "window_completeness":windows,"unique_language_urls_90":len([row for row in language_items if row["source"]==source and in_window(row["published_at"],as_of,90)]),
            "unique_items": counts["90"], "counts": counts, "indexed_counts": indexed_counts,
            "count_basis": "deduplicated_detail_identity_and_publication_verified_items",
            "material_items": len(material), "published": 0,
            "rejected": sum(item["status"] == "rejected" for item in source_items),
            "deferred": sum(item["status"] == "pending" for item in source_items), "pending_date_items": len(pending_dates),
            "technical_failures": technical, "discovered": len(source_items),
            "new": new_identity_count(source_items,prior_items,source),
            "new_basis": "identities_absent_from_previous_discovery_inventory_not_live_publications",
            "parser_routes": [r["route"]["section"] for r in source_routes],
            "boundary_evidence": [{"section": r["route"]["section"], "stop": r["stop_reason"], "pages": len(r["pages"])} for r in source_routes],
            "evidence_ref": str(evidence / "inventory.json"), "source_quality_disposition": "pass_data" if complete else "hold_external",
            "publication_activation": False, "content_freshness": "recent" if counts["30"] else "no_verified_recent_items",
            "editorial_outcome": "discovery_only_pending_editorial_and_rights_review"}
    reuters_refs = {s["url"]: s for t in json.loads((root / "data/global/themes.json").read_text())["themes"] for s in t["sources"] if s["publisher"] == "Reuters"}
    source_health["reuters"] = {"name": "Reuters", "discovery_scope": "global_intelligence", "checked_at": None, "status": "error", "technical_status": "not_polled_license_hold", "coverage_status": "not_permitted",
        "outcome": config["reuters"]["outcome"], "operation_mode": "manual_curated_only", "recurrent_operation_proven": False,
        "coverage_completeness": "unmeasured_without_permitted_route", "coverage_window_days": 90,
        "counts": {"30": None, "90": None}, "recent_items": None, "unique_items": None, "material_items": None,
        "published": 0, "rejected": 0, "deferred": 0, "discovered": 0, "new": 0, "pages_checked": 0,
        "technical_failures": [{"code": "prior_written_consent_required", "evidence_ref": config["reuters"]["robots_evidence"]}],
        "manual_reference_control": {"total": len(reuters_refs), "30": sum(in_window(s["published_at"],as_of,30) for s in reuters_refs.values()), "90": sum(in_window(s["published_at"],as_of,90) for s in reuters_refs.values()), "collector_recall": None},
        "reason": config["reuters"]["reason"], "publication_activation": False, "editorial_outcome": "rights_hold"}
    selected = sorted([row for row in items if in_window(row["published_at"], as_of, 30) and row["detail_verified"] and row["classification"]["materiality"] == "candidate"], key=lambda row:(-row["classification"]["priority"], -date.fromisoformat(row["published_at"]).toordinal(), row["url"]))
    topics = []
    seen_topics = set()
    for row in selected:
        topic = row.get("event_id") or row["url"]
        if topic in seen_topics: continue
        seen_topics.add(topic)
        topics.append({"topic_id": hashlib.sha256(topic.encode()).hexdigest()[:20], "representative_url": row["url"], "title": row["title"], "published_at": row["published_at"], "priority": row["classification"]["priority"],
                       "related_discovered_urls": [other["url"] for other in selected if (other.get("event_id") or other["url"]) == topic],
                       "selection_basis": "discovery_priority_not_editorial_publication_score", "status": "pending_editorial", "publication_ready": False,
                       "chile_transfer": "hypothesis_only", "independence_groups": ["WHO_UN_SYSTEM"], "requires": ["verified_business_consequence", "independent_corroboration", "rights_review", "editorial_approval"]})
        if len(topics) >= config["maximum_editorial_topics"]: break
    payload = {"schema_version": 1, "as_of": as_of.isoformat(), "generated_at": generated, "run_id": run_id,
               "mode": "projection_replay" if replay else "live_resume" if resume else "live_discovery", "network_requests": client.network_requests,
               "capture_reuse": {"reused_url_count":len(client.reused_urls),"maximum_campaign_capture_age_hours":1,"does_not_prove_cadence":True},
               "paid_ai_calls": 0, "live_capture_budget_seconds":config['live_capture_budget_seconds'], "source_health": source_health, "items": items, "routes": routes, "technical_failures": failures,
               "publication_count": 0, "content_use": "metadata_and_link_only", "default_window_days": 30,
               "maximum_editorial_topics": 10, "editorial_topics": topics, "cadence_is_not_proven_by_back_to_back_runs": True}
    write(root, evidence / "inventory.json", payload)
    write(root, "data/global_intelligence/discovery.json", payload)
    write(root, "data/global_intelligence/source_health.json", {"sources": source_health})
    write(root, "data/global_intelligence/editorial_candidates.json", {"as_of":as_of.isoformat(),"default_window_days":30,"maximum_topics":10,"topics":topics,"publication_count":0})
    with (root / evidence / "inventory.csv").open("w") as handle:
        fields = ["source","section","url","title","index_published_at","published_at","status","reason","detail_verified"]
        writer = csv.DictWriter(handle, fieldnames=fields,extrasaction="ignore");writer.writeheader();writer.writerows(items)
    # Keep only metadata projections publicly. Original bodies are runtime artifacts.
    projection = {}
    for url, record in client.records.items():
        detail = next((item.get("detail_evidence") for item in items if item["url"] == url), None)
        projection[url] = {"capture":record,"metadata":detail["metadata"] if detail else None}
    write(root, evidence / "capture_manifest.json", projection)
    if not replay:
        ledger["runs"] = [entry for entry in ledger["runs"] if entry["run_id"] != run_id] + [{"run_id":run_id,"mode":payload["mode"],"capture_reuse":payload["capture_reuse"],"generated_at":generated,"as_of":as_of.isoformat(),"sources":source_health,"evidence_ref":str(evidence / "inventory.json")}]
        write(root,"data/global_intelligence/ledger.json",ledger)
        # Preserve every unowned source entry; this is discovery health, not Chile publication.
        mirror_health(root,source_health)
    print(json.dumps({"run_id":run_id,"items":len(items),"topics":len(topics),"network_requests":client.network_requests,"outcomes":{source:row["outcome"] for source,row in source_health.items()}},ensure_ascii=False))
    return payload

if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument("--captures",type=Path,default=Path("work/global-runtime-captures"));parser.add_argument("--replay",type=Path);parser.add_argument("--resume-captures",action="store_true");parser.add_argument("--mirror-health",action="store_true");parser.add_argument("--as-of",type=date.fromisoformat,default=datetime.now(ZoneInfo("America/Santiago")).date());parser.add_argument("--run-id",default=os.environ.get("GITHUB_RUN_ID") or datetime.now(timezone.utc).strftime("local-%Y%m%dT%H%M%SZ"));args=parser.parse_args()
    if args.mirror_health:
        mirror_health(args.root,json.loads((args.root/"data/global_intelligence/source_health.json").read_text())["sources"])
    else:
        run(args.root,args.captures,args.as_of,args.run_id,args.replay,args.resume_captures)
