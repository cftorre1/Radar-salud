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
from .public_source_pipeline import process_suseso,process_minsal,process_df

def _new(items,store):
    out=[]
    for raw in items:
        h=hashlib.sha256(f"{raw.source_slug}|{raw.url}|{raw.title}".encode("utf-8")).hexdigest()
        if store.is_seen(h):continue
        store.add_many([h]);out.append(raw)
    return out

def _collect_generic(root,name,scout,processor,cfg,reset,limit):
    state=root/"data"/"state"/f"{name}_seen.json"
    if reset and state.exists():state.unlink()
    rows=[]
    for raw in _new(scout.discover(),SeenStore(state))[:limit]:
        try:
            row=processor(raw,cfg)
            if row:rows.append(row)
        except Exception:pass
    (root/"data"/"outbox"/f"{name}_signals.json").write_text(json.dumps({"signals":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--limit",type=int,default=12);ap.add_argument("--reset-state",action="store_true");args=ap.parse_args()
    root=Path(__file__).resolve().parents[2];cfgs=source_index(load_sources(root/"config"/"sources.json"))
    (root/"data"/"outbox").mkdir(parents=True,exist_ok=True)
    history_path=root/"data"/"history"/"superintendencia_signals.json";history=load_history(history_path);all_new=[]

    state=root/"data"/"state"/"superintendencia_seen.json"
    if args.reset_state and state.exists():state.unlink()
    items=SuperintendenciaStatsScout().discover_new(SeenStore(state));save_raw_items(items,root/"data"/"inbox"/"superintendencia_new.json")
    stats=[]
    for raw in items[:args.limit]:
        try:
            s=process_superintendencia_detail(raw,fetch_html(raw.url),cfgs["superintendencia_salud"]);row=s.to_dict()
            row["distribution_free"]=choose_distribution(s.radar_score,s.confidence_score,UserPlan("free"),s.watch_tags,())
            row["distribution_pro"]=choose_distribution(s.radar_score,s.confidence_score,UserPlan("pro"),s.watch_tags,())
            row["signal_types"]=["Datos"];row["scopes"]=["Isapres"];stats.append(row)
        except Exception:pass
    (root/"data"/"outbox"/"superintendencia_signals.json").write_text(json.dumps({"signals":stats},ensure_ascii=False,indent=2),encoding="utf-8");all_new+=stats

    reg=_collect_generic(root,"superintendencia_normativa",SuperintendenciaNormativaScout(),process_superintendencia_normativa,cfgs["superintendencia_normativa"],args.reset_state,args.limit*3);all_new+=reg
    mi=_collect_generic(root,"minsal",MinsalNewsScout(),process_minsal,cfgs["minsal"],args.reset_state,args.limit);all_new+=mi
    su=_collect_generic(root,"suseso",SusesoNormativeScout(),process_suseso,cfgs["suseso"],args.reset_state,args.limit);all_new+=su
    df=_collect_generic(root,"diario_financiero",DfHealthScout(),process_df,cfgs["diario_financiero"],args.reset_state,args.limit);all_new+=df

    history=merge_history(history,all_new);save_history(history_path,history)
    print(f"Stats={len(stats)} NormativaSuper={len(reg)} MINSAL={len(mi)} SUSESO={len(su)} DF={len(df)} Historial={len(history)}")

if __name__=="__main__":main()
