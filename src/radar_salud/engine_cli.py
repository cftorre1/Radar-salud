from __future__ import annotations
import argparse,hashlib,json
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
from .ai_budget import status as ai_budget_status
from .source_health import record as health_record
from .superintendencia_fiscalizacion import SuperintendenciaFiscalizacionScout, process_fiscalizacion
from .processing import DeferredProcessing

def _fp(raw):
    return hashlib.sha256(f"{raw.source_slug}|{raw.url}|{raw.title}".encode()).hexdigest()

def _fresh(items,store):
    return [raw for raw in items if not store.is_seen(_fp(raw))]

def _collect(root,name,items,processor,cfg,reset,limit):
    state=root/"data"/"state"/f"{name}_seen.json"
    if reset and state.exists():state.unlink()
    store=SeenStore(state)
    fresh=_fresh(items,store)
    fresh.sort(key=lambda x:x.event_date or "",reverse=True)  # LIVE first
    rows=[];deferred=0;rejected=0;attempted=0
    for raw in fresh[:limit]:
        attempted+=1
        try:
            row=processor(raw,cfg)
            store.add_many([_fp(raw)])
            if row:rows.append(row)
            else:rejected+=1
        except DeferredProcessing as e:
            deferred+=1
            print(f"{name}: deferred :: {raw.title[:70]} :: {e}")
        except Exception as e:
            # Technical errors are retryable: do not mark seen.
            deferred+=1;print(f"{name}: retryable error :: {raw.title[:70]} :: {e}")
    pending=max(0,len(fresh)-attempted)+deferred
    (root/"data"/"outbox"/f"{name}_signals.json").write_text(json.dumps({"signals":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    health_record(root,name,name=name.replace("_"," ").title(),discovered=len(items),new=len(fresh),published=len(rows),
                  pending=pending,deferred=deferred,rejected=rejected,rows=rows)
    print(f"{name}: discovered={len(items)} new={len(fresh)} published={len(rows)} pending={pending} deferred={deferred} rejected={rejected}")
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--limit",type=int,default=20);ap.add_argument("--reset-state",action="store_true");args=ap.parse_args()
    root=Path(__file__).resolve().parents[2];cfgs=source_index(load_sources(root/"config"/"sources.json"));(root/"data"/"outbox").mkdir(parents=True,exist_ok=True)
    history_path=root/"data"/"history"/"superintendencia_signals.json";history=load_history(history_path);all_new=[]
    print(f"analysis cache seeded from history: {seed_from_history(root)}")

    state=root/"data"/"state"/"superintendencia_seen.json"
    if args.reset_state and state.exists():state.unlink()
    stats_store=SeenStore(state);items=SuperintendenciaStatsScout().discover();fresh=_fresh(items,stats_store)
    fresh.sort(key=lambda x:x.event_date or "",reverse=True);save_raw_items(fresh,root/"data"/"inbox"/"superintendencia_new.json")
    stats=[];stats_rejected=0
    for raw in fresh[:args.limit]:
        try:
            s=process_superintendencia_detail(raw,fetch_html(raw.url),cfgs["superintendencia_salud"])
            row=s.to_dict();row["distribution_free"]=choose_distribution(s.radar_score,s.confidence_score,UserPlan("free"),s.watch_tags,())
            row["distribution_pro"]=choose_distribution(s.radar_score,s.confidence_score,UserPlan("pro"),s.watch_tags,())
            row["signal_types"]=["Datos"];row["scopes"]=["Isapres"];stats.append(row);stats_store.add_many([_fp(raw)])
        except Exception as e:print("stats retryable:",e)
    health_record(root,"superintendencia_stats",name="Superintendencia estadísticas",discovered=len(items),new=len(fresh),
                  published=len(stats),pending=max(0,len(fresh)-len(stats)),rows=stats);all_new+=stats

    reg=_collect(root,"superintendencia_normativa",SuperintendenciaNormativaScout().discover(),
                 process_superintendencia_normativa,cfgs["superintendencia_normativa"],False,args.limit*3);all_new+=reg
    fis=_collect(root,"superintendencia_fiscalizacion",SuperintendenciaFiscalizacionScout().discover(),
                 process_fiscalizacion,cfgs["superintendencia_fiscalizacion"],False,args.limit*3);all_new+=fis
    mi=_collect(root,"minsal",MinsalNewsScout().discover(),process_minsal,cfgs["minsal"],False,args.limit*2);all_new+=mi
    su=_collect(root,"suseso",SusesoNormativeScout().discover(),process_suseso,cfgs["suseso"],False,args.limit*2);all_new+=su
    df=_collect(root,"diario_financiero",DfHealthScout().discover(),process_df,cfgs["diario_financiero"],False,args.limit*3);all_new+=df
    do=_collect(root,"diario_oficial",DiarioOficialHealthScout().discover(days_back=90 if args.reset_state else 10),
                process_diario_oficial,cfgs["diario_oficial"],False,args.limit*3);all_new+=do

    history=merge_history(history,all_new);save_history(history_path,history)
    print(f"FINAL Stats={len(stats)} SuperNorm={len(reg)} Fiscalizacion={len(fis)} MINSAL={len(mi)} SUSESO={len(su)} DF={len(df)} DO={len(do)} History={len(history)}")
    print(f"AI budget status: {ai_budget_status()}")
if __name__=="__main__":main()
