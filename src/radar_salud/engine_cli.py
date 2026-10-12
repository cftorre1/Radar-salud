from __future__ import annotations
import argparse,hashlib,json
from dataclasses import asdict
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from .scouts import SeenStore,SuperintendenciaStatsScout,fetch_html,save_raw_items,MinsalNewsScout
from .sources import load_sources,source_index
from .superintendencia_pipeline import process_superintendencia_detail
from .distribution import UserPlan,choose_distribution
from .history import load_history,merge_history,save_history
from .df_recovery import published_history_urls
from .regulatory import SuperintendenciaNormativaScout
from .regulatory_pipeline import process_superintendencia_normativa
from .source_scouts import SusesoNormativeScout,SusesoNewsScout,SusesoFiscalizacionScout,DfHealthScout,ClinicasChileScout,CorporateNewsroomScout
from .fonasa_sources import FonasaDataHubScout,FonasaNewsScout
from .isp_sources import IspSurveillanceScout,IspAnamedAlertScout
from .deis_sources import DeisDocumentScout
from .diario_oficial import DiarioOficialHealthScout
from .public_source_pipeline import process_suseso,process_suseso_news,process_suseso_fiscalizacion,process_minsal,process_df,process_diario_oficial,process_fonasa_data_hub,process_fonasa,process_isp_surveillance,process_isp_anamed,process_clinicas_chile,process_corporate_news,process_deis
from .analysis_cache import seed_from_history
from .ai_budget import status as ai_budget_status, has_capacity
from .source_health import record as health_record
from .superintendencia_fiscalizacion import SuperintendenciaFiscalizacionScout, process_fiscalizacion
from .processing import DeferredProcessing, RejectedProcessing, OutsideBackfillHorizon
from .public_source_evidence import failure_details, discovery_diagnostics, HOSTS as PUBLIC_DATA_SOURCES
from .beta_sources import CuratedBetaSourceScout, process_curated_beta_source
from .occupational_sources import SOURCES as OCCUPATIONAL_SOURCES

def _prioritize_pulso_ready(ready):
    """Order publisher dates only inside Pulso's existing scheduling slots.

    Other sources keep their exact positions; LIVE/BACKFILL and attempt groups
    keep the queue's precedence. This changes an execution view, never records.
    """
    ordered = list(ready)
    slots = {}
    for index, (_, item) in enumerate(ordered):
        if item["source"] == "pulso_latercera":
            slots.setdefault((item.get("lane"), item.get("attempts")), []).append(index)

    def publication_priority(pair):
        value = pair[1].get("raw", {}).get("event_date")
        try:
            if not isinstance(value, str) or len(value) != 10:
                return 0
            day = date.fromisoformat(value)
            return day.toordinal() if day.isoformat() == value else 0
        except ValueError:
            return 0

    for indexes in slots.values():
        # Python's stable sort retains ties and unknown-date relative order.
        rows = sorted((ordered[index] for index in indexes),
                      key=publication_priority, reverse=True)
        for index, row in zip(indexes, rows):
            ordered[index] = row
    return ordered

def main():
    from .models import RawItem
    from .pending_queue import PendingQueue, fingerprint, legacy_fingerprint, FISCALIZATION_SOURCES, atomic_json
    from .paths import project_root
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=0,help="Global processing cap; 0 uses AI guardrails only")
    ap.add_argument("--source","--only-source",dest="source",action="append",help="Process only the named source(s); default is all core sources")
    ap.add_argument("--reset-state",action="store_true")
    ap.add_argument("--sources",nargs="+",help="Run selected core source slugs; other queue records remain untouched")
    ap.add_argument("--discovery-only",action="store_true",help="Persist genuine core discovery without consuming analysis or altering processing attempts")
    ap.add_argument("--queue-selection",type=Path,help="Process only canonical URLs already present in the selected Pulso queue; discovery remains complete")
    args=ap.parse_args()
    if args.sources and args.source:
        ap.error("Use either --sources or --source, not both")
    selected_sources=args.sources or args.source
    if args.reset_state:
        ap.error("Reset disabled: backfill must preserve paid analyses and queue state")
    selection=None
    if args.queue_selection:
        from .queue_selection import load_queue_selection
        try:
            selection=load_queue_selection(args.queue_selection,selected_sources)
        except (OSError,ValueError) as exc:
            ap.error(str(exc))
    root=project_root()
    cfgs=source_index(load_sources(root/"config"/"sources.json"))
    queue=PendingQueue(root/"data/state/pending_queue.json")
    watermark_path=root/"data/state/discovery_watermarks.json"
    watermarks=json.loads(watermark_path.read_text()) if watermark_path.exists() else {}
    if not isinstance(watermarks,dict):
        raise ValueError("Invalid discovery watermarks; refusing to classify LIVE")
    history_path=root/"data/history/superintendencia_signals.json"
    history=load_history(history_path)
    def stats(raw,cfg):
        signal=process_superintendencia_detail(raw,fetch_html(raw.url),cfg)
        row=signal.to_dict()
        for plan in ("free","pro"):
            row["distribution_"+plan]=choose_distribution(signal.radar_score,signal.confidence_score,UserPlan(plan),signal.watch_tags,())
        row.update(signal_types=["Datos"],scopes=["Isapres"])
        return row
    specs=[
      ("superintendencia","superintendencia_salud",SuperintendenciaStatsScout().discover,stats),
      ("superintendencia_normativa","superintendencia_normativa",SuperintendenciaNormativaScout().discover,process_superintendencia_normativa),
      ("superintendencia_fiscalizacion","superintendencia_fiscalizacion",SuperintendenciaFiscalizacionScout().discover,process_fiscalizacion),
      ("minsal","minsal",MinsalNewsScout().discover,process_minsal),
      ("fonasa","fonasa",FonasaNewsScout().discover,process_fonasa),
      ("fonasa_datos_abiertos","fonasa_datos_abiertos",FonasaDataHubScout().discover,process_fonasa_data_hub),
      ("isp_anamed","isp_anamed",IspAnamedAlertScout().discover,process_isp_anamed),
      ("isp_surveillance","isp_surveillance",IspSurveillanceScout().discover,process_isp_surveillance),
      ("pfizer_chile","pfizer_chile",CorporateNewsroomScout("pfizer_chile").discover,process_corporate_news),
      ("deis","deis",DeisDocumentScout().discover,process_deis),
      ("redsalud","redsalud",CorporateNewsroomScout("redsalud").discover,process_corporate_news),
      ("bupa_chile","bupa_chile",CorporateNewsroomScout("bupa_chile").discover,process_corporate_news),
      ("indisa","indisa",CorporateNewsroomScout("indisa").discover,process_corporate_news),
      ("clinicas_chile","clinicas_chile",ClinicasChileScout().discover,process_clinicas_chile),
      ("suseso","suseso",SusesoNormativeScout().discover,process_suseso),
      ("suseso_news","suseso_news",SusesoNewsScout().discover,process_suseso_news),
      ("suseso_fiscalizacion","suseso_fiscalizacion",SusesoFiscalizacionScout().discover,process_suseso_fiscalizacion),
      ("diario_financiero","diario_financiero",DfHealthScout().discover,process_df),
      ("pulso_latercera","pulso_latercera",CuratedBetaSourceScout("pulso_latercera").discover,process_curated_beta_source),
      ("diario_oficial","diario_oficial",lambda:DiarioOficialHealthScout().discover(days_back=10),process_diario_oficial)]
    specs += [(slug,slug,CuratedBetaSourceScout(slug).discover,process_curated_beta_source)
              for slug in sorted(OCCUPATIONAL_SOURCES) if not selected_sources or slug in selected_sources]
    specs.extend((slug,slug,CuratedBetaSourceScout(slug).discover,process_curated_beta_source)
                 for slug in ("red_davila","andes_salud")
                 if slug in cfgs and (not selected_sources or slug in selected_sources))
    if selected_sources:
        unknown=set(selected_sources)-{name for name,_,_,_ in specs}
        if unknown:ap.error("Unknown source(s): "+", ".join(sorted(unknown)))
        specs=[spec for spec in specs if spec[0] in selected_sources]
    processors={name:(cfgs[cfg],processor) for name,cfg,_,processor in specs}
    if 'suseso_fiscalizacion' in processors:
        processors.setdefault('suseso',(cfgs['suseso'],process_suseso))
    discoveries={}
    discovery_details={}
    discovery_evidence={}
    observed={}
    surfaces={}
    occupational_audit={}
    original_dates={}
    # Complete discovery for every source before any budget-consuming processing.
    for name,_,discover,_ in specs:
        owner=getattr(discover,"__self__",None)
        try:
            items=discover()
            observed[name]=[dict(url=raw.url,event_date=raw.event_date,metadata=raw.metadata) for raw in items]
            surfaces[name]=getattr(getattr(discover,"__self__",None),"surface_results",None)
            scout=getattr(discover,"__self__",None)
            if name == "deis" and getattr(scout, "catalog", None) is not None:
                atomic_json(root/"data/state/deis_catalog.json", scout.catalog)
            if name in PUBLIC_DATA_SOURCES:
                discovery_details[name]={"diagnostics":discovery_diagnostics(scout,items)}
                discovery_details[name]["diagnostics"]["poll_mode"]="daily_engine"
            original_dates[name]=max([raw.event_date for raw in items if raw.event_date] or ['']) or None
            partial_errors=getattr(getattr(discover,"__self__",None),"discovery_errors",[])
            store=SeenStore(root/"data/state"/f"{name}_seen.json")
            from .superintendencia_fiscalizacion import canonical_url
            published_urls={canonical_url(row.get("source_url", "")) for row in history
                if name in FISCALIZATION_SOURCES and "Fiscalización" in (row.get("signal_types") or []) and not row.get('source_record_id')}
            published_records={(canonical_url(row.get('source_url','')), row['source_record_id']) for row in history
                if name in FISCALIZATION_SOURCES and 'Fiscalización' in (row.get('signal_types') or []) and row.get('source_record_id')}
            seen={fingerprint(raw) for raw in items if store.is_seen(fingerprint(raw)) or
                (name in FISCALIZATION_SOURCES and (store.is_seen(legacy_fingerprint(raw)) or
                    (not raw.metadata.get('source_record_id') and canonical_url(raw.url) in published_urls) or
                    (canonical_url(raw.url), raw.metadata.get('source_record_id')) in published_records))}
            checked_at=datetime.now(timezone.utc).isoformat()
            added=queue.discover(name,items,seen,last_discovered_at=watermarks.get(name),
                                 published_urls=published_history_urls(history))
            if name=="suseso_fiscalizacion":
                from .suseso_fiscalizacion import reviewed_normative_candidate
                routed=[candidate for raw in items if (candidate:=reviewed_normative_candidate(raw))]
                # Existing normative history guards cross-channel rediscovery.
                routed_seen={fingerprint(raw) for raw in routed if any(row.get("source_url")==raw.url for row in history)}
                queue.discover("suseso",routed,routed_seen,last_discovered_at=watermarks.get("suseso"))
            audit=getattr(owner,"discovery_audit",[])
            partial=any(x.get("status") in ("detail_error","listing_error") for x in audit)
            if not partial_errors and not partial:
                watermarks[name]=checked_at
                atomic_json(watermark_path,watermarks)
            error=("partial_discovery: "+"; ".join(partial_errors) if partial_errors
                   else "partial_discovery" if partial else None)
            discoveries[name]=(len(items),added,error)
            if name=="diario_financiero":
                discovery_evidence[name]={"dated":sum(bool(raw.event_date) for raw in items),
                    "undated":sum(not raw.event_date for raw in items),
                    "detail_errors":sum(bool(raw.metadata.get("fetch_error")) for raw in items),
                    "insufficient_evidence":sum(len(raw.metadata.get("page_text", ""))<160 for raw in items),
                    "textual_candidates":sum(len(raw.metadata.get('page_text',''))>=160 for raw in items),
                    "nontextual_candidates_known":sum(len(raw.metadata.get('page_text',''))<160 and bool(raw.metadata.get('primary_image_urls') or raw.metadata.get('primary_media_urls')) for raw in items),
                    "textual_capture_status":"partial" if any(raw.metadata.get('fetch_error') or (len(raw.metadata.get('page_text',''))>=160 and not raw.event_date) for raw in items) else "verified",
                    "format_capability":{"text":"runtime_verified","images":"requires_ocr","audio_video":"requires_official_text"},
                    "newest_event_date":max([raw.event_date for raw in items if raw.event_date],default=None)}
            if name in OCCUPATIONAL_SOURCES:
                inventory = getattr(owner, "inventory", {})
                occupational_audit[name]={"technical_status":"ok","checked_at":checked_at,
                    "decisions":getattr(owner,"decisions",[]),"discovered":len(items),
                    "inventory_complete":inventory.get("coverage_complete", False),
                    "inventory":{k:v for k,v in inventory.items() if k != "raw_items"}}
        except Exception as exc:
            surfaces[name]=getattr(owner,"surface_results",None)
            partial = getattr(exc, "partial_items", []) if name in OCCUPATIONAL_SOURCES else []
            added = queue.discover(name, partial, last_discovered_at=watermarks.get(name)) if partial else 0
            discoveries[name]=(len(partial),added,type(exc).__name__)
            if name in OCCUPATIONAL_SOURCES:
                inventory = getattr(owner, "inventory", {})
                occupational_audit[name]={"technical_status":"partial" if partial else "error","checked_at":datetime.now(timezone.utc).isoformat(),
                    "error":{"code":getattr(exc,"code",type(exc).__name__),"url":getattr(exc,"url",None),"message":str(exc)},
                    "decisions":getattr(owner,"decisions",[]),"inventory_complete":False,
                    "diagnostics":getattr(exc,"diagnostics", []), "discovered":len(partial),
                    "inventory":{k:v for k,v in inventory.items() if k != "raw_items"}}
            if name in PUBLIC_DATA_SOURCES:
                scout=getattr(discover,"__self__",None)
                if name == "deis" and getattr(scout, "catalog", None) is not None:
                    atomic_json(root/"data/state/deis_catalog.json", scout.catalog)
                discovery_details[name]={"error_details":failure_details(exc),
                    "diagnostics":discovery_diagnostics(scout)}
                discovery_details[name]["diagnostics"]["poll_mode"]="daily_engine"
        if name not in PUBLIC_DATA_SOURCES:
            # Pulso/DF retain their complete list of per-URL source traces;
            # public data sources retain the structured native diagnostics.
            discovery_details[name]=getattr(owner,"discovery_audit",[])
    if occupational_audit:
        audit_path=root/'data/state/occupational_source_discovery.json'
        previous_audit=json.loads(audit_path.read_text()) if audit_path.exists() else {}
        previous_audit.update(occupational_audit)
        atomic_json(audit_path,previous_audit)
    run_path=root/"data/state/discovery_run.json"
    previous_run=json.loads(run_path.read_text()) if selected_sources and run_path.exists() else {}
    run_sources=previous_run.get("sources",{})
    diagnostic_details={name:details for name,details in discovery_details.items() if isinstance(details,dict)}
    run_sources.update({name:{"discovered":found,"new":added,"technical_status":"error" if error else "degraded" if (diagnostic_details.get(name,{}).get("diagnostics") or {}).get("partial_failure") else "ok","error_type":error,
                             "checked_at":datetime.now(timezone.utc).isoformat(),**discovery_evidence.get(name,{}),**diagnostic_details.get(name,{})}
                        for name,(found,added,error) in discoveries.items()})
    run_details=previous_run.get("source_details",{})
    run_details.update(discovery_details)
    atomic_json(run_path,{
        "at":datetime.now(timezone.utc).isoformat(),
        "sources":run_sources,
        "run_scope":list(processors),
        "source_details":run_details,
        "runtime":"daily_core",
        "selected_sources":selected_sources,
        "successful_sources":sum(row.get("technical_status")!="error" for row in run_sources.values()),
        "failed_sources":sum(row.get("technical_status")=="error" for row in run_sources.values()),
    })
    produced={name:[] for name in processors}
    processed_rejections={name:0 for name in processors}
    queue.enforce_backfill_horizon(sources=set(selected_sources) if selected_sources else None)
    from .daily_window import eligible_daily_item
    ready=((key,item) for key,item in _prioritize_pulso_ready(queue.ready())
           if item['source'] in processors and eligible_daily_item(item) and
           (not selected_sources or item['source'] in selected_sources or
            ('suseso_fiscalizacion' in selected_sources and item['raw'].get('metadata',{}).get('routed_from')=='suseso_fiscalizacion')))
    if selection is not None:
        from .queue_selection import select_ready
        discovery_run=json.loads((root/"data/state/discovery_run.json").read_text())
        try:
            ready,selection_audit=select_ready(selection,queue.items,ready)
        except ValueError as exc:
            discovery_run.update(processing_attempts=0,processing_selection=dict(
                source="pulso_latercera",path=selection.path,sha256=selection.sha256,
                file_sha256=selection.sha256,selected_urls=list(selection.urls),
                selected_url_count=len(selection.urls),validation_error=str(exc),
                reason="explicit_queue_selection_invalid"))
            atomic_json(root/"data/state/discovery_run.json",discovery_run)
            ap.error(str(exc))
        discovery_run["processing_selection"]=selection_audit
        atomic_json(root/"data/state/discovery_run.json",discovery_run)
    if args.discovery_only:
        ready=iter(())
    evaluated={name:0 for name in processors}
    processed_count=0
    processing_deferrals={}
    for key,item in ready:
        if args.limit and processed_count>=args.limit:break
        fast_available=has_capacity("fast")
        if item["source"] == "pulso_latercera" and not fast_available:
            # Pulso uses fast analysis; capacity exhaustion is not an attempt.
            processing_deferrals["pulso_latercera"]={
                "reason":"fast_analysis_capacity_exhausted","required_tier":"fast",
                "before_queue_start":True,
            }
            if set(processors)=={"pulso_latercera"}:break
            continue
        deterministic = item["source"] in FISCALIZATION_SOURCES or item["raw"].get("metadata",{}).get("reviewed_normative")
        if not deterministic and not fast_available and not has_capacity("deep"):continue
        queue.start(key)
        processed_count+=1
        processing_raw=RawItem(**deepcopy(item["raw"]))
        prior_assessment=deepcopy(processing_raw.metadata.get('editorial_assessment'))
        try:
            cfg,processor=processors[item["source"]]
            row=processor(processing_raw,cfg)
            if row or (processing_raw.metadata.get('editorial_assessment') and processing_raw.metadata['editorial_assessment']!=prior_assessment):
                evaluated[item['source']]+=1
            if row:
                row.update(detected_at=item["detected_at"],ingestion_mode=item["lane"])
                if item["source"]=="diario_financiero":
                    previous=next((s for s in history if s.get("source_url")==row.get("source_url")),{})
                    if previous.get("df_body_reaudit_observations"):
                        row.update(df_body_reaudit_observations=previous["df_body_reaudit_observations"],
                                   df_body_reaudit_status="published_after_primary_body_reassessment",
                                   editorial_decision="accept")
                # Save output before terminal queue acknowledgement (crash safe replay).
                history=merge_history(history,[row]);save_history(history_path,history)
                produced[item["source"]].append(row)
            item["raw"]=asdict(processing_raw)
            if not row and item['source']=='diario_financiero':
                previous=next((s for s in history if s.get('source_url')==processing_raw.url),None)
                if previous and previous.get('df_body_reaudit_observations'):
                    previous.update(df_body_reaudit_status='rejected_after_primary_body_reassessment',
                                    df_body_reaudit_reason=processing_raw.metadata.get('rejection_reason'),
                                    df_body_reaudit_latest_assessment=processing_raw.metadata.get('editorial_assessment'),
                                    editorial_decision='reject',feed_visibility=False)
                    save_history(history_path,history)
            from .provider_assessment import rejection_reason
            queue.finish(key,"published" if row else "rejected",None if row else processing_raw.metadata.get("rejection_reason") or processing_raw.metadata.get("publication_rejection_reason") or (rejection_reason(processing_raw) if item["source"] in ("redsalud","bupa_chile","indisa","red_davila","andes_salud","clinicas_chile","pfizer_chile") else "processor_rejected"))
            if not row:processed_rejections[item['source']]+=1
            SeenStore(root/"data/state"/f"{item['source']}_seen.json").add_many([key])
        except RejectedProcessing as exc:
            item["raw"]=asdict(processing_raw)
            queue.finish(key,"rejected",str(exc))
            processed_rejections[item['source']]+=1
            SeenStore(root/"data/state"/f"{item['source']}_seen.json").add_many([key])
        except OutsideBackfillHorizon as exc:
            processing_raw.event_date=str(exc)
            item["raw"]=asdict(processing_raw)
            queue.finish(key,"archived","outside_90_day_backfill")
        except DeferredProcessing as exc:
            item["deferred_detail"]=str(exc)
            item["raw"]=asdict(processing_raw)
            if item['source']=='diario_financiero':
                previous=next((s for s in history if s.get('source_url')==processing_raw.url),None)
                if previous and previous.get('df_body_reaudit_observations'):
                    previous.update(df_body_reaudit_status='retry_after_primary_body_reassessment',
                                    df_body_reaudit_reason=exc.reason,editorial_decision='reject',feed_visibility=False)
                    save_history(history_path,history)
            from .df_resolution import defer_format
            source=item["source"]
            if source in PUBLIC_DATA_SOURCES:
                reason=str(exc)[:250]
                diagnostics=discovery_details.setdefault(source,{}).setdefault("diagnostics",{})
                diagnostics.setdefault("processing_deferred",[]).append({"reason":reason,**failure_details(exc)})
                if exc.__cause__ is not None or any(term in reason.lower() for term in ("pdf","capture","contenido","readable","documento")):
                    diagnostics["partial_failure"]=True
                    diagnostics["evidence_status"]="capture_pending"
                queue.finish(key,"retry",reason)
            elif item['source']=='diario_financiero' and defer_format(item, exc.reason, datetime.now(timezone.utc)):
                queue.save()
            else:
                reason=exc.reason or str(exc) or "budget_or_analysis_deferred"
                if item["source"] == "pulso_latercera":
                    reason=processing_raw.metadata.get("editorial_assessment",{}).get("reason") or reason
                queue.finish(key,"retry",reason)
        except Exception as exc:
            if item["source"] == "pulso_latercera":
                item["raw"]=asdict(processing_raw)
            queue.finish(key,"retry",type(exc).__name__)
        finally:
            item['raw']=asdict(processing_raw)
            queue.save()
    discovery_run=json.loads(run_path.read_text())
    discovery_run.update(processing_deferrals=processing_deferrals,processing_attempts=processed_count)
    atomic_json(run_path,discovery_run)
    for name,(discovered,new,error) in discoveries.items():
        counts=queue.counts(name)
        df_evidence=({**discovery_evidence.get(name,{}),
            "deferred_multimedia":sum(i.get('source')==name and i['status']=='deferred' and
                i.get('df_resolution',{}).get('state')=='DEFERRED_MULTIMEDIA' for i in queue.items.values()),
            "unverifiable_date_dispositions":sum(i.get('source')==name and i['status']=='deferred' and
                i.get('df_resolution',{}).get('state')=='RESOLVED_NO_VERIFIABLE_DATE' for i in queue.items.values()),
            "last_published_event_at":max([row.get("event_date") for row in history
                if row.get("source_name")=="Diario Financiero" and row.get("event_date") and row.get("editorial_decision")!="reject"],default=None)}
            if name=="diario_financiero" else None)
        from collections import Counter
        fiscal_history=[row for row in history if "Fiscalización" in (row.get("signal_types") or []) and
            ((name=="superintendencia_fiscalizacion" and "superdesalud.gob.cl" in row.get("source_url", "")) or
             (name=="suseso_fiscalizacion" and "suseso.gob.cl" in row.get("source_url", "")))]
        source_items=[item for item in queue.items.values() if item.get("source")==name]
        source_cfg=processors[name][0]
        label=source_cfg.get("name",name) if isinstance(source_cfg,dict) else name
        health_record(root,name,name=label,discovered=discovered,new=new,
            published=len(produced[name]),pending=counts["live_pending"]+counts["backfill_pending"],
            processed_rejections=processed_rejections[name],
            deferred=sum(i.get('source')==name and i['status'] in ('retry','deferred') for i in queue.items.values()),
            rejected=counts["rejected"],rows=produced[name],error=error,
            live_pending=counts["live_pending"],backfill_pending=counts["backfill_pending"], discovery_evidence=df_evidence, observed_rows=observed.get(name),surfaces=surfaces.get(name),
            published_history=(history if name == "pulso_latercera"
                               else fiscal_history if name in FISCALIZATION_SOURCES else None),
            source_queue=source_items if name in FISCALIZATION_SOURCES or name == "pulso_latercera" else None,
            archived=sum(item.get("status")=="archived" for item in source_items),
            rejection_reasons=dict(Counter(item.get("reason") for item in source_items if item.get("status")=="rejected")),
            **({"error_detail":occupational_audit[name].get("error"), "inventory":occupational_audit[name].get("inventory", {})} if name in OCCUPATIONAL_SOURCES else {}),
            **{k:v for k,v in diagnostic_details.get(name,{}).items() if v},
            latest_original_at=original_dates.get(name),evaluation_performed=evaluated[name]>0)
    print({"queue":queue.counts(),"budget":ai_budget_status()})

if __name__=="__main__":main()
