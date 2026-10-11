from __future__ import annotations
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from .pending_queue import atomic_json

def _path(root:Path)->Path:return root/"data"/"source_health.json"
def _load(root:Path)->dict[str,Any]:
    p=_path(root)
    if not p.exists():return {"sources":{}}
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {"sources":{}}

def record(root:Path,slug:str,*,name:str,discovered:int,new:int,published:int,rows:list[dict]|None=None,
           pending:int=0,deferred:int=0,rejected:int=0,error:str|None=None,live_pending:int|None=None,backfill_pending:int|None=None, observed_rows:list[dict]|None=None,
           surfaces:list[dict]|None=None, published_history:list[dict]|None=None,
           archived:int=0, rejection_reasons:dict|None=None)->None:
    d=_load(root);src=d.setdefault("sources",{});rows=rows or []
    dates=[x.get("event_date") for x in rows if x.get("event_date")]
    prev=src.get(slug) or (src.get("superintendencia_stats",{}) if slug=="superintendencia" else {})
    last_signal=max(dates+[prev.get("last_signal_at") or ""]) if dates else prev.get("last_signal_at")
    fiscal = slug in ("superintendencia_fiscalizacion", "suseso_fiscalizacion")
    if fiscal and published_history is not None:
        last_signal = max((row.get("event_date") or "" for row in published_history), default="") or None
    observed_rows = observed_rows or []
    last_observed = max((row.get("event_date") or "" for row in observed_rows), default="") or None
    publication_dates = [row.get("metadata", {}).get("publication_date") for row in observed_rows
                         if row.get("metadata", {}).get("publication_date")]
    last_observed_publication = max(publication_dates, default=None)
    surface_errors = sum(row.get("status") == "error" for row in surfaces or [])
    surface_success = sum(row.get("status") == "parsed" for row in surfaces or [])
    undated = sum(not row.get("event_date") for row in observed_rows)
    if fiscal:
        coverage = ("blocked" if error or (surface_errors and not surface_success) else
                    "partial" if surface_errors else "gap" if undated else
                    "listed_surface_parsed" if surface_success else "unverified")
        technical = "error" if error else "partial" if surface_errors else "ok"
    else:
        coverage = technical = None
    coverage_gap=error is None and discovered==0 and not last_signal
    status="error" if error else ("warning" if (coverage_gap or (new>0 and published==0 and pending==0)) else "ok")
    if fiscal and coverage != "listed_surface_parsed":
        status = "error" if error else "warning"
    try:
        age=(datetime.now(timezone.utc).date()-date.fromisoformat(str(last_signal)[:10])).days
        freshness="future" if age<0 else ("recent" if age<=7 else "older")
    except (ValueError,TypeError):
        freshness="unknown"
    editorial="not_evaluated" if error else ("published" if published else
        "pending" if pending else "rejected" if rejected else "no_new_signals")
    src[slug]={
        "name":name,"checked_at":datetime.now(timezone.utc).isoformat(),
        "last_signal_at":last_signal,
        "discovered":discovered,"new":new,"published":published,
        "live_pending":live_pending,"backfill_pending":backfill_pending,"pending":pending,"deferred":deferred,"rejected":rejected,
        "status":status,"error":error,
        "technical_status":technical or ("error" if error else "ok"),
        "coverage_status":coverage or ("unverified" if error else ("gap" if coverage_gap else "observed")),
        "content_freshness":freshness,
        "editorial_outcome":editorial,
    }
    if fiscal:
        src[slug].update(
            last_observed_event_at=last_observed, last_observed_publication_at=last_observed_publication,
            surfaces=surfaces or [], undated_observations=undated,
            archived=archived, rejection_reasons=rejection_reasons or {},
            published_total=len(published_history) if published_history is not None else None,
            coverage_reason="listed_documents_only; not site-wide reconciliation" if surface_success else "no_surface_receipt; discovery_count_is_not_coverage",
            counter_semantics={"discovered":"documents in this discovery run, including historical",
                "new":"queue additions this run", "published":"processed to history this run; feed gate is separate",
                "published_total":"persisted source history stock", "pending":"current queue stock",
                "rejected":"queue stock with evaluated rejection", "archived":"queue stock beyond backfill horizon"})
        if not error and not published and not pending and not rejected and published_history:
            src[slug]["editorial_outcome"] = "no_new_publications_existing_history"
    d["generated_at"]=datetime.now(timezone.utc).isoformat()
    atomic_json(_path(root),d)
