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

def _new(items,store):
    out=[]
    for raw in items:
        h=hashlib.sha256(f"{raw.source_slug}|{raw.url}|{raw.title}".encode()).hexdigest()
        if store.is_seen(h):continue
        store.add_many([h]);out.append(raw)
    return out

def _collect(root,name,items,processor,cfg,reset,limit):
    state=root/"data"/"state"/f"{name}_seen.json"
    if reset and state.exists():state.unlink()
    fresh=_new(items,SeenStore(state));rows=[]
    for raw in fresh[:limit]:
        try:
            row=processor(raw,cfg)
            if row:rows.append(row)
        except Exception as e:print(f"{name}: {raw.title[:70]} :: {e}")
    (root/"data"/"outbox"/f"{name}_signals.json").write_text(json.dumps({"signals":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    health_record(root,name,name=name.replace("_"," ").title(),discovered=len(items),new=len(fresh),published=len(rows),rows=rows)
    print(f"{name}: discovered={len(items)} new={len(fresh)} published={len(rows)}");return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--limit",type=int,default=20);ap.add_argument("--reset-state",action="store_true");args=ap.parse_args()
    root=Path(__file__).resolve().parents[2];cfgs=source_index(load_sources(root/"config"/"sources.json"));(root/"data"/"outbox").mkdir(parents=True,exist_ok=True)
    history_path=root/"data"/"history"/"superintendencia_signals.json";history=load_history(history_path);all_new=[]
    print(f"analysis cache seeded from history: {seed_from_history(root)}")
    state=root/"data"/"state"/"superintendencia_seen.json"
    if args.reset_state and state.exists():state.unlink()
    items=SuperintendenciaStatsScout().discover_new(SeenStore(state));save_raw_items(items,root/"data"/"inbox"/"superintendencia_new.json")
    stats=[]
    for raw in items[:args.limit]:
        try:
            s=process_superintendencia_detail(raw,fetch_html(raw.url),cfgs["superintendencia_salud"]);row=s.to_dict();row["distribution_free"]=choose_distribution(s.radar_score,s.confidence_score,UserPlan("free"),s.watch_tags,());row["distribution_pro"]=choose_distribution(s.radar_score,s.confidence_score,UserPlan("pro"),s.watch_tags,());row["signal_types"]=["Datos"];row["scopes"]=["Isapres"];row["data_insights"]=[];stats.append(row)
        except Exception as e:print("stats:",e)
    health_record(root,"superintendencia_stats",name="Superintendencia estadísticas",discovered=len(items),new=len(items),published=len(stats),rows=stats);all_new+=stats
    reg=_collect(root,"superintendencia_normativa",SuperintendenciaNormativaScout().discover(),process_superintendencia_normativa,cfgs["superintendencia_normativa"],args.reset_state,args.limit*3);all_new+=reg
    mi=_collect(root,"minsal",MinsalNewsScout().discover(),process_minsal,cfgs["minsal"],False,args.limit*2);all_new+=mi
    su=_collect(root,"suseso",SusesoNormativeScout().discover(),process_suseso,cfgs["suseso"],args.reset_state,args.limit*2);all_new+=su
    df=_collect(root,"diario_financiero",DfHealthScout().discover(),process_df,cfgs["diario_financiero"],args.reset_state,args.limit*2);all_new+=df
    do=_collect(root,"diario_oficial",DiarioOficialHealthScout().discover(days_back=90 if args.reset_state else 10),process_diario_oficial,cfgs["diario_oficial"],args.reset_state,args.limit*3);all_new+=do
    history=merge_history(history,all_new);save_history(history_path,history)
    print(f"FINAL Stats={len(stats)} SuperNorm={len(reg)} MINSAL={len(mi)} SUSESO={len(su)} DF={len(df)} DO={len(do)} History={len(history)}");print(f"AI budget status: {ai_budget_status()}")
if __name__=="__main__":main()
