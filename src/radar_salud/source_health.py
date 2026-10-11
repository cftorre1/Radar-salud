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
           archived:int=0, rejection_reasons:dict|None=None, source_queue:list[dict]|None=None, discovery_evidence:dict|None=None, error_detail:dict|None=None,inventory:dict|None=None)->None:
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
    # Parsed tables prove an observation, not reconciled 30/90-day coverage.
    # Keep the public health warning until independent reconciliation exists.
    if fiscal:
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
    if discovery_evidence is not None:
        row=src[slug]
        row.update(discovery_evidence)
        row["counts_scope"]={"discovered":"this_run","new":"this_run","published":"this_run",
                             "pending":"cumulative_queue","deferred":"cumulative_queue","rejected":"cumulative_queue"}
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
    if fiscal:
        from .superintendencia_fiscalizacion import canonical_url
        def identity(row):
            meta=row.get('metadata', {})
            return (canonical_url(row.get('url') or row.get('source_url') or ''),
                    meta.get('source_record_id') or row.get('source_record_id'))
        def recent(row, days):
            meta=row.get('metadata', {})
            # Modifications and suspension dates never rejuvenate an old act.
            for value in (meta.get('publication_date'),meta.get('emission_date'),row.get('event_date')):
                try:
                    if 0 <= (datetime.now(timezone.utc).date()-date.fromisoformat(value)).days <= days:
                        return True
                except (ValueError,TypeError):
                    pass
            return False
        observed={identity(row):row for row in observed_rows}
        published_ids={identity(row) for row in published_history or []}
        queue_by_id={identity(item['raw']):item for item in source_queue or []}
        windows={}
        for days in (30,90):
            current={key:row for key,row in observed.items() if recent(row,days)}
            related={key for key,row in current.items() if row.get('metadata', {}).get('document_class')=='related_normative'}
            news={key for key,row in current.items() if row.get('metadata', {}).get('document_class')=='official_news'}
            windows[str(days)]=dict(items_recent=len(current),enforcement_recent=len(set(current)-related-news)+len(news&published_ids),
                official_news_recent=len(news),
                related_normative_recent=len(related),published=len(set(current)&published_ids),
                rejected=sum(queue_by_id.get(key,{}).get('status')=='rejected' for key in current),
                deferred=sum(queue_by_id.get(key,{}).get('status') in ('retry','processing','pending') for key in current),
                items_material=len(set(current)&published_ids),
                unaccounted=sum(key not in published_ids and key not in queue_by_id for key in current))
        src[slug].update(
            last_observed_event_at=last_observed, last_observed_publication_at=last_observed_publication,
            surfaces=surfaces or [], undated_observations=undated,
            coverage_complete=False,
            archived=archived, rejection_reasons=rejection_reasons or {},
            published_total=len(published_history) if published_history is not None else None,
            final_state='OPERATIVE_DEGRADED',
            pages_checked=len(surfaces or []),items_discovered=discovered,unique_items=len(observed),
            surface_rows_discovered=sum(row.get('documents',0) for row in surfaces or [] if row.get('status')=='parsed'),
            items_recent=windows['90']['items_recent'],items_material=windows['90']['items_material'],
            items_recent_enforcement=windows['90']['enforcement_recent'],
            parse_errors=sum(row.get('error') in ('ValueError','ParseError','HTMLParseError') for row in surfaces or []),
            surface_errors=surface_errors,windows=windows,
            coverage_reason="listed_documents_only; not site-wide reconciliation" if surface_success else "no_surface_receipt; discovery_count_is_not_coverage",
            counter_semantics={"discovered":"documents in this discovery run, including historical",
                "new":"queue additions this run", "published":"processed to history this run; feed gate is separate",
                "published_total":"persisted source history stock", "pending":"current queue stock",
                "rejected":"queue stock with evaluated rejection", "archived":"queue stock beyond backfill horizon"})
        if not error and not published:
            src[slug]['zero_published_reason'] = ('pending_or_deferred_candidates' if pending else
                'evaluated_rejections_or_existing_published_history' if rejected or published_history else
                'no_recent_material_signal_verified; coverage_not_certified')
        if not error and not published and not pending and not rejected and published_history:
            src[slug]['editorial_outcome']='no_new_publications_existing_history'
    if error_detail:
        src[slug]["error_detail"]=error_detail
    if inventory is not None:
        complete = inventory.get("coverage_complete", False)
        row = src[slug]
        outcome = "OPERATIVE_VALIDATED" if complete and not error and not pending else "OPERATIVE_DEGRADED"
        row.update(coverage_window=inventory.get("window"), pages_checked=len(inventory.get("pages", [])),
            recent_items=inventory.get("metrics", {}), unique_items=inventory.get("metrics", {}).get("90", {}).get("expected_role", 0),
            material_items=sum(r.get("status") == "candidate" for r in inventory.get("rows", [])),
            technical_status="partial" if error and discovered else "error" if error else "ok",
            technical_failures=inventory.get("errors", []) or ([error_detail] if error_detail else []),
            coverage_status="complete" if complete else "partial", coverage_completeness=complete,
            recovery_outcome=outcome, status="ok" if outcome == "OPERATIVE_VALIDATED" else "warning" if discovered or not error else "error")
    d["generated_at"]=datetime.now(timezone.utc).isoformat()
    atomic_json(_path(root),d)
