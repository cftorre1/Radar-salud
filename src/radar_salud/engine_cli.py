from __future__ import annotations
import argparse,hashlib,json
from dataclasses import asdict
from datetime import datetime, timezone
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

def main():
    from .models import RawItem
    from .pending_queue import PendingQueue, fingerprint, atomic_json
    from .paths import project_root
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=0,help="Global processing cap; 0 uses AI guardrails only")
    ap.add_argument("--source",action="append",help="Process only the named source(s); default is all core sources")
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
    if args.source:
        unknown=set(args.source)-{name for name,_,_,_ in specs}
        if unknown:ap.error("Unknown source(s): "+", ".join(sorted(unknown)))
        specs=[spec for spec in specs if spec[0] in args.source]
    processors={name:(cfgs[cfg],processor) for name,cfg,_,processor in specs}
    discoveries={}
    discovery_evidence={}
    # Complete discovery for every source before any budget-consuming processing.
    for name,_,discover,_ in specs:
        try:
            items=discover()
            store=SeenStore(root/"data/state"/f"{name}_seen.json")
            seen={fingerprint(raw) for raw in items if store.is_seen(fingerprint(raw))}
            checked_at=datetime.now(timezone.utc).isoformat()
            added=queue.discover(name,items,seen,last_discovered_at=watermarks.get(name),
                                 published_urls=[row["source_url"] for row in history if row.get("source_url")])
            watermarks[name]=checked_at
            atomic_json(watermark_path,watermarks)
            discoveries[name]=(len(items),added,None)
            if name=="diario_financiero":
                discovery_evidence[name]={"dated":sum(bool(raw.event_date) for raw in items),
                    "undated":sum(not raw.event_date for raw in items),
                    "detail_errors":sum(bool(raw.metadata.get("fetch_error")) for raw in items),
                    "newest_event_date":max([raw.event_date for raw in items if raw.event_date],default=None)}
        except Exception as exc:
            discoveries[name]=(0,0,type(exc).__name__)
    run_path=root/"data/state/discovery_run.json"
    previous_run=json.loads(run_path.read_text()) if args.source and run_path.exists() else {}
    run_sources=previous_run.get("sources",{})
    run_sources.update({name:{"discovered":found,"new":added,"technical_status":"error" if error else "ok","error_type":error,
                             "checked_at":datetime.now(timezone.utc).isoformat(),**discovery_evidence.get(name,{})}
                        for name,(found,added,error) in discoveries.items()})
    atomic_json(run_path,{
        "at":datetime.now(timezone.utc).isoformat(),
        "sources":run_sources,
        "run_scope":list(processors),
        "successful_sources":sum(row.get("technical_status")!="error" for row in run_sources.values()),
        "failed_sources":sum(row.get("technical_status")=="error" for row in run_sources.values()),
    })
    produced={name:[] for name in processors}
    queue.enforce_backfill_horizon(sources=set(processors) if args.source else None)
    ready=[(key,item) for key,item in queue.ready() if item["source"] in processors]
    for index,(key,item) in enumerate(ready):
        if args.limit and index>=args.limit:break
        if not has_capacity("fast") and not has_capacity("deep"):break
        queue.start(key)
        processing_raw=RawItem(**item["raw"])
        try:
            cfg,processor=processors[item["source"]]
            row=processor(processing_raw,cfg)
            if row:
                row.update(detected_at=item["detected_at"],ingestion_mode=item["lane"])
                # Save output before terminal queue acknowledgement (crash safe replay).
                history=merge_history(history,[row]);save_history(history_path,history)
                produced[item["source"]].append(row)
            item["raw"]=asdict(processing_raw)
            queue.finish(key,"published" if row else "rejected",None if row else processing_raw.metadata.get("rejection_reason","processor_rejected"))
            SeenStore(root/"data/state"/f"{item['source']}_seen.json").add_many([key])
        except DeferredProcessing as exc:
            item["raw"]=asdict(processing_raw)
            queue.finish(key,"retry",exc.reason or "budget_or_analysis_deferred")
        except Exception as exc:
            queue.finish(key,"retry",type(exc).__name__)
    for name,(discovered,new,error) in discoveries.items():
        counts=queue.counts(name)
        df_evidence=({**discovery_evidence.get(name,{}),
            "last_published_event_at":max([row.get("event_date") for row in history
                if row.get("source_name")=="Diario Financiero" and row.get("event_date")],default=None)}
            if name=="diario_financiero" else None)
        health_record(root,name,name="Diario Financiero" if name=="diario_financiero" else name.replace("_"," ").title(),discovered=discovered,new=new,
            published=len(produced[name]),pending=counts["live_pending"]+counts["backfill_pending"],
            rejected=counts["rejected"],rows=produced[name],error=error,
            live_pending=counts["live_pending"],backfill_pending=counts["backfill_pending"],discovery_evidence=df_evidence)
    print({"queue":queue.counts(),"budget":ai_budget_status()})

if __name__=="__main__":main()
