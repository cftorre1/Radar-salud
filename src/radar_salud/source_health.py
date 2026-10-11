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
           evaluation_performed:bool=True,latest_original_at:str|None=None)->None:
    d=_load(root);src=d.setdefault("sources",{});rows=rows or []
    dates=[x.get("event_date") for x in rows if x.get("event_date")]
    prev=src.get(slug) or (src.get("superintendencia_stats",{}) if slug=="superintendencia" else {})
    last_signal=max(dates+[prev.get("last_signal_at") or ""]) if dates else prev.get("last_signal_at")
    latest_original_at=latest_original_at or prev.get('latest_original_at')
    provider_stale=False
    if slug in ('redsalud','bupa_chile','indisa','red_davila','andes_salud','clinicas_chile','pfizer_chile','clinicas_achs_salud') and latest_original_at:
        try:provider_stale=(datetime.now(timezone.utc).date()-date.fromisoformat(latest_original_at[:10])).days>90
        except (ValueError,TypeError):pass
    coverage_gap=error is None and discovered==0 and not last_signal
    audited_coverage=prev.get('provider_coverage')
    incomplete=bool(audited_coverage and audited_coverage.get('coverage_complete') is not True)
    degraded=bool(audited_coverage and audited_coverage.get('outcome')=='OPERATIVE_DEGRADED')
    status="error" if error else ("warning" if (incomplete or degraded or provider_stale or not evaluation_performed or coverage_gap or (new>0 and published==0 and pending==0)) else "ok")
    try:
        age=(datetime.now(timezone.utc).date()-date.fromisoformat(str(last_signal)[:10])).days
        freshness="future" if age<0 else ("recent" if age<=7 else "older")
    except (ValueError,TypeError):
        freshness="unknown"
    editorial="published" if published else "not_evaluated" if error or not evaluation_performed else (
        "pending" if pending else "rejected" if rejected else "no_new_signals")
    src[slug]={
        "name":name,"checked_at":datetime.now(timezone.utc).isoformat(),
        "last_signal_at":last_signal,
        "discovered":discovered,"new":new,"published":published,
        "live_pending":live_pending,"backfill_pending":backfill_pending,"pending":pending,"deferred":deferred,"rejected":rejected,
        "status":status,"error":error,
        "technical_status":"error" if error else "ok",
        "coverage_status":"unverified" if error or incomplete else ("gap" if coverage_gap or provider_stale else "observed"),
        "content_freshness":"stale_external_surface" if provider_stale else freshness,
        "latest_original_at":latest_original_at,
        "editorial_outcome":editorial,
        "evaluation_performed":evaluation_performed,
    }
    for field in ('provider_audit','audited_assessment','provider_coverage'):
        if field in prev:src[slug][field]=prev[field]
    d["generated_at"]=datetime.now(timezone.utc).isoformat()
    atomic_json(_path(root),d)
