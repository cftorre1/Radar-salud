from __future__ import annotations
import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from .pending_queue import atomic_json

def _path(root:Path)->Path:return root/"data"/"source_health.json"

def load_retired_sources(root:Path)->dict[str,str]:
    """Slugs retired from daily capture by an explicit, recorded decision."""
    p=Path(root)/"config"/"retired_sources.json"
    if not p.exists():return {}
    return dict(json.loads(p.read_text(encoding="utf-8")).get("retired") or {})

def mark_retired_sources(root:Path,retired:dict[str,str])->None:
    """Keep history, but stop presenting retired sources as monitored."""
    if not retired:return
    data=_load(Path(root));changed=False
    for slug,reason in retired.items():
        row=data.setdefault("sources",{}).get(slug)
        if row is None or row.get("status")=="retired":continue
        row.update(status="retired",technical_status="retired",retired_reason=reason,
                   retired_at=datetime.now(timezone.utc).isoformat(),error=None)
        changed=True
    if changed:atomic_json(_path(Path(root)),data)
def _load(root:Path)->dict[str,Any]:
    p=_path(root)
    if not p.exists():return {"sources":{}}
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {"sources":{}}

def record_data_adapter(root: Path, slug: str, evidence: dict) -> None:
    """Data coverage is independent of news publication and transport success."""
    required = {'pages_checked', 'items_discovered', 'unique_items', 'items_recent',
                'items_material', 'published', 'rejected', 'deferred', 'parse_errors',
                'coverage_complete', 'coverage_reason'}
    if not required <= evidence.keys(): raise ValueError('Incomplete adapter health evidence')
    d = _load(root)
    d.setdefault('sources', {})[slug] = {
        **evidence, 'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'error' if evidence['parse_errors'] else 'ok' if evidence['coverage_complete'] else 'warning',
        'technical_status': evidence.get('technical_status', 'unverified'),
        'coverage_status': 'validated_declared_perimeter' if evidence['coverage_complete'] else 'partial',
        'editorial_outcome': evidence.get('editorial_outcome', 'data_snapshot_no_news_quota'),
    }
    d['generated_at'] = datetime.now(timezone.utc).isoformat()
    atomic_json(_path(root), d)



def _pulso_published_body_bound(row, raw):
    """Bind current primary bytes to the persisted assessment/review body."""
    from .llm_analysis import news_analysis_input
    from .pulso_source import liveblog_analysis_text
    metadata = raw.get("metadata", {})
    body = metadata.get("page_text")
    body_sha = metadata.get("article_body_sha256")
    pins = []
    if "analysis_base_article_body_sha256" in metadata:
        pins.append(metadata["analysis_base_article_body_sha256"])
    for review in (row.get("editorial_review"), metadata.get("editorial_review")):
        if isinstance(review, dict) and "original_body_sha256" in review:
            pins.append(review["original_body_sha256"])
    validation = metadata.get("pulso_editorial_proof_validation")
    if isinstance(validation, dict) and "primary_article_body_sha256" in validation:
        pins.append(validation["primary_article_body_sha256"])
    if not pins or any(pin != body_sha for pin in pins):
        return False
    if ("analysis_base_article_body_characters" in metadata
            and metadata["analysis_base_article_body_characters"] != len(body)):
        return False
    try:
        # Live blogs have an augmented, verified timeline request. Its input
        # hash must match that full request, never the plain base body hash.
        text = liveblog_analysis_text(metadata) if metadata.get("publisher_document_type") == "liveblog" else body
        request = news_analysis_input(title=raw["title"], text=text, source_name=raw["source_name"], full_text=True)
        text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        request_sha = hashlib.sha256(request.encode("utf-8")).hexdigest()
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
    for field, expected in (("analysis_input_body_sha256", text_sha),
                            ("analysis_request_input_sha256", request_sha)):
        if field in metadata and metadata[field] != expected:
            return False
    ai = metadata.get("analysis_model_output")
    model_binding = ai.get("_pulso_analysis_meta") if isinstance(ai, dict) else None
    if isinstance(model_binding, dict) and (model_binding.get("analysis_text_sha256") != text_sha
            or model_binding.get("request_input_sha256") != request_sha):
        return False
    return True

def _effective_pulso_history(history, source_queue):
    """Current published stock, bound to the same verified primary and gate."""
    from .editorial_gate import publication_ready
    from .pulso_source import article_url, complete_article_body
    queue_by_url = {}
    for item in source_queue or []:
        if item.get("source") == "pulso_latercera":
            raw = item.get("raw", {})
            url = article_url(raw.get("url", ""))
            if url:
                queue_by_url.setdefault(url, []).append(item)
    effective = {}
    for row in history or []:
        review = row.get("editorial_review")
        if (row.get("source_name") != "Pulso / La Tercera"
                or row.get("source_type") != "press_high_trust"
                or row.get("source_quality_gate") != "passed"
                or row.get("evidence_maturity") != "media_reported"
                or row.get("feed_visibility") is False
                or row.get("editorial_decision") in {"reject", "group"}
                or (isinstance(review, dict) and review.get("decision") in {"reject", "group"})):
            continue
        try:
            if isinstance(row.get("editorial_relevance"), bool) or int(row.get("editorial_relevance") or 0) < 72:
                continue
            day = row.get("event_date")
            if (not isinstance(day, str) or date.fromisoformat(day).isoformat() != day
                    or row.get("publication_date") != day):
                continue
        except (ValueError, TypeError):
            continue
        url = article_url(row.get("source_url", ""))
        if not url or url != row.get("source_url") or not publication_ready(deepcopy(row))[0]:
            continue
        for item in queue_by_url.get(url, []):
            raw = item.get("raw", {})
            metadata = raw.get("metadata", {})
            binding = metadata.get("primary_item_binding")
            assessment = metadata.get("editorial_assessment")
            validation = metadata.get("pulso_editorial_proof_validation")
            if (item.get("status") != "published" or raw.get("event_date") != day
                    or raw.get("source_slug") != "pulso_latercera"
                    or raw.get("source_name") != "Pulso / La Tercera" or raw.get("source_type") != "press_high_trust"
                    or not isinstance(assessment, dict) or assessment.get("decision") != "published"
                    or metadata.get("editorial_hold") or metadata.get("analysis_input_complete") is False
                    or (isinstance(validation, dict) and validation.get("decision") == "deferred")
                    or metadata.get("canonical_url") != url or metadata.get("publication_date") != day
                    or any(metadata.get(flag) is not True for flag in (
                        "article_verified", "primary_identity_verified", "publication_date_verified"))
                    or metadata.get("source_quality_gate") != "passed"
                    or metadata.get("article_body_complete") is False or not complete_article_body(metadata)
                    or (isinstance(binding, dict) and binding.get("verified") is False)):
                continue
            if not _pulso_published_body_bound(row, raw):
                continue
            effective[url] = row
            break
    return list(effective.values())

def record(root:Path,slug:str,*,name:str,discovered:int,new:int,published:int,rows:list[dict]|None=None,
           pending:int=0,deferred:int=0,rejected:int=0,error:str|None=None,live_pending:int|None=None,backfill_pending:int|None=None,
           discovery_evidence:dict|None=None, observed_rows:list[dict]|None=None,
           surfaces:list[dict]|None=None, published_history:list[dict]|None=None,
           archived:int=0, rejection_reasons:dict|None=None, source_queue:list[dict]|None=None, error_detail:dict|None=None,inventory:dict|None=None,error_details:dict|None=None,diagnostics:dict|None=None,evaluation_performed:bool=True,latest_original_at:str|None=None,processed_rejections:int=0,history_last_signal:str|None=None)->None:
    d=_load(root);src=d.setdefault("sources",{});rows=rows or []
    dates=[x.get("event_date") for x in rows if x.get("event_date")]
    prev=src.get(slug) or (src.get("superintendencia_stats",{}) if slug=="superintendencia" else {})
    last_signal=max(dates+[prev.get("last_signal_at") or ""]) if dates else prev.get("last_signal_at")
    latest_original_at=latest_original_at or prev.get('latest_original_at')
    # Items published by hourly/batch queue runs never pass through this source's own run:
    # the newest published card in history is the truthful freshness (audit 27-oct-2026).
    if history_last_signal:
        last_signal=max(filter(None,[last_signal,history_last_signal]))
        latest_original_at=max(filter(None,[latest_original_at,history_last_signal]))
    provider_stale=False
    if slug in ('redsalud','bupa_chile','indisa','red_davila','andes_salud','clinicas_chile','pfizer_chile','clinicas_achs_salud') and latest_original_at:
        try:provider_stale=(datetime.now(timezone.utc).date()-date.fromisoformat(latest_original_at[:10])).days>90
        except (ValueError,TypeError):pass
    audited_coverage=prev.get('provider_coverage')
    incomplete=bool(audited_coverage and audited_coverage.get('coverage_complete') is not True)
    degraded=bool(audited_coverage and audited_coverage.get('outcome')=='OPERATIVE_DEGRADED')
    fiscal = slug in ("superintendencia_fiscalizacion", "suseso_fiscalizacion")
    pulso_history = (_effective_pulso_history(published_history, source_queue)
                     if slug == "pulso_latercera" and published_history is not None else None)
    if pulso_history is not None:
        # Editorial withdrawals can move the latest effective publication
        # backwards. Neither an old health snapshot nor this-run-only rows
        # may keep a removed signal's date alive.
        last_signal = max((row["event_date"] for row in pulso_history), default=None)
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
    if diagnostics and (diagnostics.get("coverage_status")=="no_verifiable_documents"
                        or diagnostics.get("verified_publications")==0):
        coverage_gap=True
    status="error" if error else ("warning" if (incomplete or degraded or provider_stale or not evaluation_performed or coverage_gap or (new>0 and published==0 and pending==0)) else "ok")
    # Parsed tables prove an observation, not reconciled 30/90-day coverage.
    # Keep the public health warning until independent reconciliation exists.
    if fiscal:
        status = "error" if error else "warning"
    partial=bool(diagnostics and diagnostics.get("partial_failure"))
    if partial and not error:status="warning"
    try:
        age=(datetime.now(timezone.utc).date()-date.fromisoformat(str(last_signal)[:10])).days
        freshness="future" if age<0 else ("recent" if age<=7 else "older")
    except (ValueError,TypeError):
        freshness="unknown"
    editorial="published" if published else "not_evaluated" if error or not evaluation_performed else (
        "rejected" if processed_rejections else "pending" if pending else "no_new_signals")
    if diagnostics and diagnostics.get("poll_mode")=="discovery_and_document_verification_only":
        editorial="not_evaluated"
    src[slug]={
        "name":name,"checked_at":datetime.now(timezone.utc).isoformat(),
        "last_signal_at":last_signal,
        "discovered":discovered,"new":new,"published":published,
        "live_pending":live_pending,"backfill_pending":backfill_pending,"pending":pending,"deferred":deferred,"rejected":rejected,
        "status":status,"error":error,
        "technical_status":technical or ("error" if error else "degraded" if partial else "ok"),
        "coverage_status":coverage or ("unverified" if error or incomplete else ("partial" if partial else "gap" if coverage_gap or provider_stale else "observed")),
        "content_freshness":"stale_external_surface" if provider_stale else freshness,
        "latest_original_at":latest_original_at,
        "editorial_outcome":editorial,
        "evaluation_performed":evaluation_performed,
        "processed_rejections":processed_rejections,
        "counts_scope":{"discovered":"this_run","new":"this_run","published":"this_run",
                        "processed_rejections":"this_run","rejected":"cumulative_queue"},
    }
    if pulso_history is not None:
        src[slug].update(published_total=len(pulso_history),
                         last_signal_at_basis="effective_verified_published_history")
        src[slug]["counts_scope"]["published_total"] = "effective_persisted_source_history"
    if discovery_evidence is not None:
        row=src[slug]
        row.update(discovery_evidence)
        row["counts_scope"]={"discovered":"this_run","new":"this_run","published":"this_run",
                             "pending":"cumulative_queue","deferred":"cumulative_queue","rejected":"cumulative_queue"}
        row["coverage_status"]="unverified" if error else "partial_inventory"
        # An all-undated inventory cannot be healthy merely because HTTP worked.
        if not error and (discovery_evidence.get("undated",0) or discovery_evidence.get("detail_errors",0)):
            row.update(status="warning",technical_status="partial",coverage_status="date_or_detail_gap")
        elif not error and discovery_evidence.get("insufficient_evidence",0):
            row.update(status="warning",technical_status="partial",coverage_status="format_gap")
        row["last_signal_at"]=discovery_evidence.get("last_published_event_at")
        row["last_discovered_event_at"]=discovery_evidence.get("newest_event_date")
        try:
            published_day=date.fromisoformat(str(row["last_signal_at"])[:10])
            age=(datetime.now(timezone.utc).date()-published_day).days
            row["content_freshness"]="future" if age<0 else "recent" if age<=7 else "older"
        except (TypeError,ValueError):row["content_freshness"]="unknown"
        row["editorial_outcome"]=editorial
        row["coverage_complete"]=False
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
        if not error and not published and not pending and not processed_rejections and published_history:
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
            technical_failures=(inventory.get("errors", []) or inventory.get("coverage_gaps", [])
                                or ([error_detail] if error_detail else [])),
            coverage_status="complete" if complete else "partial", coverage_completeness=complete,
            recovery_outcome=outcome, status="ok" if outcome == "OPERATIVE_VALIDATED" else "warning" if discovered or not error else "error")
    if error_details:src[slug]["error_details"]=error_details
    if diagnostics:src[slug]["discovery_diagnostics"]=diagnostics
    if diagnostics and diagnostics.get("poll_mode"):
        src[slug]["engine_checked_at"]=(src[slug]["checked_at"] if diagnostics["poll_mode"]=="daily_engine"
                                        else prev.get("engine_checked_at",prev.get("checked_at")))
        src[slug]["poll_mode"]=diagnostics["poll_mode"]
    if diagnostics and "latest_verified_publication_date" in diagnostics:
        src[slug]["latest_verified_publication_at"]=diagnostics["latest_verified_publication_date"]
    for field in ('provider_audit','audited_assessment','provider_coverage'):
        if field in prev:src[slug][field]=prev[field]
    d["generated_at"]=datetime.now(timezone.utc).isoformat()
    atomic_json(_path(root),d)
