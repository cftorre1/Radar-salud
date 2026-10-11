from __future__ import annotations
import argparse,hashlib,json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from .scouts import SeenStore,SuperintendenciaStatsScout,fetch_html,save_raw_items,MinsalNewsScout
from .sources import load_sources,source_index
from .superintendencia_pipeline import process_superintendencia_detail
from .distribution import UserPlan,choose_distribution
from .history import load_history,merge_history,save_history
from .regulatory import SuperintendenciaNormativaScout
from .regulatory_pipeline import process_superintendencia_normativa
from .source_scouts import SusesoNormativeScout,SusesoNewsScout,SusesoFiscalizacionScout,DfHealthScout,FonasaDataHubScout,FonasaNewsScout,IspSurveillanceScout,IspAnamedAlertScout,ClinicasChileScout,CorporateNewsroomScout,DeisResourceScout
from .diario_oficial import DiarioOficialHealthScout
from .public_source_pipeline import process_suseso,process_suseso_news,process_suseso_fiscalizacion,process_minsal,process_df,process_diario_oficial,process_fonasa_data_hub,process_fonasa,process_isp_surveillance,process_isp_anamed,process_clinicas_chile,process_corporate_news,process_deis
from .analysis_cache import seed_from_history
from .ai_budget import status as ai_budget_status, has_capacity
from .source_health import record as health_record
from .superintendencia_fiscalizacion import SuperintendenciaFiscalizacionScout, process_fiscalizacion
from .processing import DeferredProcessing
from .beta_sources import CuratedBetaSourceScout, process_curated_beta_source


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
    from .pending_queue import PendingQueue, fingerprint, atomic_json
    from .paths import project_root
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=0,help="Global processing cap; 0 uses AI guardrails only")
    ap.add_argument("--reset-state",action="store_true")
    ap.add_argument("--sources",nargs="+",help="Run selected core source slugs; other queue records remain untouched")
    ap.add_argument("--discovery-only",action="store_true",help="Persist genuine core discovery without consuming analysis or altering processing attempts")
    args=ap.parse_args()
    if args.reset_state:
        ap.error("Reset disabled: backfill must preserve paid analyses and queue state")
    root=project_root()
    cfgs=source_index(load_sources(root/"config"/"sources.json"))
    queue=PendingQueue(root/"data/state/pending_queue.json")
    watermark_path=root/"data/state/discovery_watermarks.json"
    watermarks=json.loads(watermark_path.read_text()) if watermark_path.exists() else {}
    if not isinstance(watermarks,dict):
        raise ValueError("Invalid discovery watermarks; refusing to classify LIVE")
    history_path=root/"data/history/superintendencia_signals.json"
    history=load_history(history_path)
    seed_from_history(root)
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
      ("deis","deis",DeisResourceScout().discover,process_deis),
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
    if args.sources:
        unknown=set(args.sources)-{name for name,_,_,_ in specs}
        if unknown:ap.error("Unknown core sources: "+", ".join(sorted(unknown)))
        specs=[spec for spec in specs if spec[0] in args.sources]
    processors={name:(cfgs[cfg],processor) for name,cfg,_,processor in specs}
    discoveries={}
    discovery_details={}
    # Complete discovery for every source before any budget-consuming processing.
    for name,_,discover,_ in specs:
        try:
            items=discover()
            store=SeenStore(root/"data/state"/f"{name}_seen.json")
            seen={fingerprint(raw) for raw in items if store.is_seen(fingerprint(raw))}
            checked_at=datetime.now(timezone.utc).isoformat()
            added=queue.discover(name,items,seen,last_discovered_at=watermarks.get(name))
            watermarks[name]=checked_at
            atomic_json(watermark_path,watermarks)
            audit=getattr(getattr(discover,"__self__",None),"discovery_audit",[])
            partial=any(x.get("status") in ("detail_error","listing_error") for x in audit)
            discoveries[name]=(len(items),added,"partial_discovery" if partial else None)
        except Exception as exc:
            discoveries[name]=(0,0,type(exc).__name__)
        audit=getattr(getattr(discover,"__self__",None),"discovery_audit",[])
        if audit:discovery_details[name]=audit
    atomic_json(root/"data/state/discovery_run.json",{
        "at":datetime.now(timezone.utc).isoformat(),
        "sources":{name:{"discovered":found,"new":added,"technical_status":"error" if error else "ok","error_type":error}
                   for name,(found,added,error) in discoveries.items()},
        "successful_sources":sum(error is None for _,_,error in discoveries.values()),
        "failed_sources":sum(error is not None for _,_,error in discoveries.values()),
        "source_details":discovery_details,
        "runtime":"daily_core",
        "selected_sources":args.sources,
    })
    produced={name:[] for name in processors}
    queue.enforce_backfill_horizon(sources=args.sources)
    ready=((key,item) for key,item in _prioritize_pulso_ready(queue.ready()) if item["source"] in processors)
    if args.discovery_only:
        ready=iter(())
    processed_count=0
    processing_deferrals={}
    for key,item in ready:
        if args.limit and processed_count>=args.limit:break
        fast_available=has_capacity("fast")
        if item["source"] == "pulso_latercera" and not fast_available:
            # Pulso's editorial processor uses the fast tier. Do not turn an
            # unspent budget stop into a processing attempt and two-hour retry.
            processing_deferrals["pulso_latercera"]={
                "reason":"fast_analysis_capacity_exhausted","required_tier":"fast",
                "before_queue_start":True,
            }
            if set(processors)=={"pulso_latercera"}:break
            continue
        if not fast_available and not has_capacity("deep"):break
        queue.start(key)
        processed_count+=1
        try:
            cfg,processor=processors[item["source"]]
            raw=RawItem(**item["raw"])
            row=processor(raw,cfg)
            if item["source"] == "pulso_latercera":
                item["raw"] = asdict(raw)
            if row:
                row.update(detected_at=item["detected_at"],ingestion_mode=item["lane"])
                # Save output before terminal queue acknowledgement (crash safe replay).
                history=merge_history(history,[row]);save_history(history_path,history)
                produced[item["source"]].append(row)
            reason=raw.metadata.get("rejection_reason") or "processor_rejected"
            queue.finish(key,"published" if row else "rejected",None if row else reason)
            SeenStore(root/"data/state"/f"{item['source']}_seen.json").add_many([key])
        except DeferredProcessing:
            reason="budget_or_analysis_deferred"
            if item["source"] == "pulso_latercera":
                item["raw"] = asdict(raw)
                reason=raw.metadata.get("editorial_assessment",{}).get("reason") or reason
            queue.finish(key,"retry",reason)
        except Exception as exc:
            if item["source"] == "pulso_latercera":
                item["raw"] = asdict(raw)
            queue.finish(key,"retry",type(exc).__name__)
    discovery_run=json.loads((root/"data/state/discovery_run.json").read_text())
    discovery_run.update(processing_deferrals=processing_deferrals,processing_attempts=processed_count)
    atomic_json(root/"data/state/discovery_run.json",discovery_run)
    for name,(discovered,new,error) in discoveries.items():
        counts=queue.counts(name)
        health_name=processors[name][0]["name"] if name=="pulso_latercera" else name.replace("_"," ").title()
        health_record(root,name,name=health_name,discovered=discovered,new=new,
            published=len(produced[name]),pending=counts["live_pending"]+counts["backfill_pending"],
            rejected=counts["rejected"],rows=produced[name],error=error,
            live_pending=counts["live_pending"],backfill_pending=counts["backfill_pending"])
    print({"queue":queue.counts(),"budget":ai_budget_status()})

if __name__=="__main__":main()
