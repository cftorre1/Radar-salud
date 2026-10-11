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
           pending:int=0,deferred:int=0,rejected:int=0,error:str|None=None,live_pending:int|None=None,backfill_pending:int|None=None,
           discovery_evidence:dict|None=None)->None:
    d=_load(root);src=d.setdefault("sources",{});rows=rows or []
    dates=[x.get("event_date") for x in rows if x.get("event_date")]
    prev=src.get(slug) or (src.get("superintendencia_stats",{}) if slug=="superintendencia" else {})
    last_signal=max(dates+[prev.get("last_signal_at") or ""]) if dates else prev.get("last_signal_at")
    coverage_gap=error is None and discovered==0 and not last_signal
    status="error" if error else ("warning" if (coverage_gap or (new>0 and published==0 and pending==0)) else "ok")
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
        "technical_status":"error" if error else "ok",
        "coverage_status":"unverified" if error else ("gap" if coverage_gap else "observed"),
        "content_freshness":freshness,
        "editorial_outcome":editorial,
    }
    if discovery_evidence is not None:
        row=src[slug]
        row.update(discovery_evidence)
        row["counts_scope"]={"discovered":"this_run","new":"this_run","published":"this_run",
                             "pending":"cumulative_queue","rejected":"cumulative_queue"}
        row["coverage_status"]="unverified" if error else "partial_inventory"
        # An all-undated inventory cannot be healthy merely because HTTP worked.
        if not error and (discovery_evidence.get("undated",0) or discovery_evidence.get("detail_errors",0)
                          or discovery_evidence.get("insufficient_evidence",0)):
            row.update(status="warning",technical_status="partial",coverage_status="date_or_detail_gap")
        row["last_signal_at"]=discovery_evidence.get("last_published_event_at")
        row["last_discovered_event_at"]=discovery_evidence.get("newest_event_date")
        try:
            published_day=date.fromisoformat(str(row["last_signal_at"])[:10])
            age=(datetime.now(timezone.utc).date()-published_day).days
            row["content_freshness"]="future" if age<0 else "recent" if age<=7 else "older"
        except (TypeError,ValueError):row["content_freshness"]="unknown"
        if error:row["editorial_outcome"]="not_evaluated"
    d["generated_at"]=datetime.now(timezone.utc).isoformat()
    atomic_json(_path(root),d)
