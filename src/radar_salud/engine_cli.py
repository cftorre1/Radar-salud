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
from .source_scouts import SusesoNormativeScout,DfHealthScout
from .diario_oficial import DiarioOficialHealthScout
from .public_source_pipeline import process_suseso,process_minsal,process_df,process_diario_oficial
from .analysis_cache import seed_from_history
from .ai_budget import status as ai_budget_status, has_capacity
from .source_health import record as health_record
from .superintendencia_fiscalizacion import SuperintendenciaFiscalizacionScout, process_fiscalizacion
from .processing import DeferredProcessing

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
      ("suseso","suseso",SusesoNormativeScout().discover,process_suseso),
      ("diario_financiero","diario_financiero",DfHealthScout().discover,process_df),
      ("diario_oficial","diario_oficial",lambda:DiarioOficialHealthScout().discover(days_back=10),process_diario_oficial)]
    processors={name:(cfgs[cfg],processor) for name,cfg,_,processor in specs}
    discoveries={}
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
            discoveries[name]=(len(items),added,None)
        except Exception as exc:
            discoveries[name]=(0,0,type(exc).__name__)
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
        except DeferredProcessing:
            queue.finish(key,"retry","budget_or_analysis_deferred")
        except Exception as exc:
            queue.finish(key,"retry",type(exc).__name__)
    for name,(discovered,new,error) in discoveries.items():
        counts=queue.counts(name)
        health_record(root,name,name=name.replace("_"," ").title(),discovered=discovered,new=new,
            published=len(produced[name]),pending=counts["live_pending"]+counts["backfill_pending"],
            rejected=counts["rejected"],rows=produced[name],error=error,
            live_pending=counts["live_pending"],backfill_pending=counts["backfill_pending"])
    print({"queue":queue.counts(),"budget":ai_budget_status()})

if __name__=="__main__":main()
