from __future__ import annotations
import argparse,json
from pathlib import Path
from .scouts import SeenStore,SuperintendenciaStatsScout,fetch_html,save_raw_items
from .sources import load_sources,source_index
from .superintendencia_pipeline import process_superintendencia_detail
from .distribution import UserPlan,choose_distribution
from .history import load_history,merge_history,save_history
from .regulatory import SuperintendenciaNormativaScout
from .regulatory_pipeline import process_superintendencia_normativa

def main():
    parser=argparse.ArgumentParser(description="Radar Salud Engine V0")
    parser.add_argument("--limit",type=int,default=10)
    parser.add_argument("--reset-state",action="store_true")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    cfgs=source_index(load_sources(root/"config"/"sources.json"))
    history_path=root/"data"/"history"/"superintendencia_signals.json"
    history=load_history(history_path)
    all_new=[]

    # Estadísticas
    cfg=cfgs["superintendencia_salud"]; state=root/"data"/"state"/"superintendencia_seen.json"
    if args.reset_state and state.exists(): state.unlink()
    scout=SuperintendenciaStatsScout();store=SeenStore(state);items=scout.discover_new(store)
    save_raw_items(items,root/"data"/"inbox"/"superintendencia_new.json")
    stats=[]
    for raw in items[:args.limit]:
        try:
            signal=process_superintendencia_detail(raw,fetch_html(raw.url),cfg)
            row=signal.to_dict()
            row["distribution_free"]=choose_distribution(signal.radar_score,signal.confidence_score,UserPlan("free"),signal.watch_tags,())
            row["distribution_pro"]=choose_distribution(signal.radar_score,signal.confidence_score,UserPlan("pro"),signal.watch_tags,())
            row.setdefault("signal_types",["Datos"]);row.setdefault("scopes",["Isapres"])
            stats.append(row)
        except Exception: pass
    (root/"data"/"outbox").mkdir(parents=True,exist_ok=True)
    (root/"data"/"outbox"/"superintendencia_signals.json").write_text(json.dumps({"signals":stats},ensure_ascii=False,indent=2),encoding="utf-8")
    all_new.extend(stats)

    # Normativa Isapres: Circulares + Oficios Circulares
    reg_state=root/"data"/"state"/"superintendencia_normativa_seen.json"
    if args.reset_state and reg_state.exists(): reg_state.unlink()
    reg_store=SeenStore(reg_state);reg_items=SuperintendenciaNormativaScout().discover()
    reg_new=[]
    for raw in reg_items:
        fp=f"{raw.source_slug}|{raw.url}|{raw.title}"
        import hashlib
        h=hashlib.sha256(fp.encode("utf-8")).hexdigest()
        if reg_store.is_seen(h): continue
        reg_store.add_many([h])
        try: reg_new.append(process_superintendencia_normativa(raw,cfgs["superintendencia_normativa"]))
        except Exception: pass
    (root/"data"/"outbox"/"superintendencia_normativa_signals.json").write_text(json.dumps({"signals":reg_new},ensure_ascii=False,indent=2),encoding="utf-8")
    all_new.extend(reg_new)

    history=merge_history(history,all_new);save_history(history_path,history)
    print(f"Stats nuevos: {len(stats)} | Normativa nueva: {len(reg_new)} | Historial: {len(history)}")

if __name__=="__main__":main()
