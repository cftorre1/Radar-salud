from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime, timezone
from pathlib import Path
from .scouts import SeenStore,SuperintendenciaStatsScout,fetch_html,save_raw_items,MinsalNewsScout
from .sources import load_sources,source_index
from .superintendencia_pipeline import process_superintendencia_detail
from .distribution import UserPlan,choose_distribution
from .history import load_history,merge_history,save_history
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
from .processing import DeferredProcessing
from .public_source_evidence import failure_details, discovery_diagnostics, HOSTS as PUBLIC_DATA_SOURCES
from .beta_sources import CuratedBetaSourceScout, process_curated_beta_source

def main():
    from .models import RawItem
    from .pending_queue import PendingQueue, fingerprint, atomic_json
    from .paths import project_root
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=0,help="Global processing cap; 0 uses AI guardrails only")
    ap.add_argument("--reset-state",action="store_true")
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
    processors={name:(cfgs[cfg],processor) for name,cfg,_,processor in specs}
    discoveries={}
    discovery_details={}
    # Complete discovery for every source before any budget-consuming processing.
    for name,_,discover,_ in specs:
        try:
            items=discover()
            scout=getattr(discover,"__self__",None)
            if name == "deis" and scout.catalog is not None:
                atomic_json(root/"data/state/deis_catalog.json", scout.catalog)
            if name in PUBLIC_DATA_SOURCES:
                discovery_details[name]={"diagnostics":discovery_diagnostics(scout,items)}
                discovery_details[name]["diagnostics"]["poll_mode"]="daily_engine"
            store=SeenStore(root/"data/state"/f"{name}_seen.json")
            seen={fingerprint(raw) for raw in items if store.is_seen(fingerprint(raw))}
            checked_at=datetime.now(timezone.utc).isoformat()
            added=queue.discover(name,items,seen,last_discovered_at=watermarks.get(name))
            watermarks[name]=checked_at
            atomic_json(watermark_path,watermarks)
            discoveries[name]=(len(items),added,None)
        except Exception as exc:
            discoveries[name]=(0,0,type(exc).__name__)
            if name in PUBLIC_DATA_SOURCES:
                scout=getattr(discover,"__self__",None)
                if name == "deis" and scout.catalog is not None:
                    atomic_json(root/"data/state/deis_catalog.json", scout.catalog)
                discovery_details[name]={"error_details":failure_details(exc),
                                         "diagnostics":discovery_diagnostics(scout)}
                discovery_details[name]["diagnostics"]["poll_mode"]="daily_engine"
    atomic_json(root/"data/state/discovery_run.json",{
        "at":datetime.now(timezone.utc).isoformat(),
        "sources":{name:{"discovered":found,"new":added,"technical_status":"error" if error else "degraded" if (discovery_details.get(name,{}).get("diagnostics") or {}).get("partial_failure") else "ok","error_type":error,
                         **{k:v for k,v in discovery_details.get(name,{}).items() if v}}
                   for name,(found,added,error) in discoveries.items()},
        "successful_sources":sum(error is None for _,_,error in discoveries.values()),
        "failed_sources":sum(error is not None for _,_,error in discoveries.values()),
    })
    produced={name:[] for name in processors}
    queue.enforce_backfill_horizon()
    for index,(key,item) in enumerate(queue.ready()):
        if args.limit and index>=args.limit:break
        if not has_capacity("fast") and not has_capacity("deep"):break
        queue.start(key)
        try:
            cfg,processor=processors[item["source"]]
            row=processor(RawItem(**item["raw"]),cfg)
            if row:
                row.update(detected_at=item["detected_at"],ingestion_mode=item["lane"])
                # Save output before terminal queue acknowledgement (crash safe replay).
                history=merge_history(history,[row]);save_history(history_path,history)
                produced[item["source"]].append(row)
            queue.finish(key,"published" if row else "rejected",None if row else "processor_rejected")
            SeenStore(root/"data/state"/f"{item['source']}_seen.json").add_many([key])
        except DeferredProcessing as exc:
            source=item["source"]
            if source in PUBLIC_DATA_SOURCES:
                reason=str(exc)[:250]
                diagnostics=discovery_details.setdefault(source,{}).setdefault("diagnostics",{})
                diagnostics.setdefault("processing_deferred",[]).append({"reason":reason,**failure_details(exc)})
                if exc.__cause__ is not None or any(term in reason.lower() for term in ("pdf","capture","contenido","readable","documento")):
                    diagnostics["partial_failure"]=True
                    diagnostics["evidence_status"]="capture_pending"
                queue.finish(key,"retry",reason)
            else:
                queue.finish(key,"retry","budget_or_analysis_deferred")
        except Exception as exc:
            queue.finish(key,"retry",type(exc).__name__)
    for name,(discovered,new,error) in discoveries.items():
        counts=queue.counts(name)
        health_record(root,name,name=name.replace("_"," ").title(),discovered=discovered,new=new,
            published=len(produced[name]),pending=counts["live_pending"]+counts["backfill_pending"],
            rejected=counts["rejected"],rows=produced[name],error=error,
            live_pending=counts["live_pending"],backfill_pending=counts["backfill_pending"],
            **{k:v for k,v in discovery_details.get(name,{}).items() if v})
    print({"queue":queue.counts(),"budget":ai_budget_status()})

if __name__=="__main__":main()
