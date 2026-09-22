from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from .scouts import SeenStore,SuperintendenciaStatsScout,SusesoScout,MinsalNewsScout,fetch_html,save_raw_items
from .sources import load_sources,source_index
from .superintendencia_pipeline import process_superintendencia_detail
from .distribution import UserPlan,choose_distribution
from .history import load_history,merge_history,save_history
from .regulatory import SuperintendenciaNormativaScout
from .regulatory_pipeline import process_superintendencia_normativa
from .public_source_pipeline import process_suseso,process_minsal

def _new(items, store):
    out=[]
    for raw in items:
        h=hashlib.sha256(f"{raw.source_slug}|{raw.url}|{raw.title}".encode("utf-8")).hexdigest()
        if store.is_seen(h):continue
        store.add_many([h]);out.append(raw)
    return out

def main():
    ap=argparse.ArgumentParser(description="Radar Salud Engine V0")
    ap.add_argument("--limit",type=int,default=10); ap.add_argument("--reset-state",action="store_true"); args=ap.parse_args()
    root=Path(__file__).resolve().parents[2]; cfgs=source_index(load_sources(root/"config"/"sources.json"))
    history_path=root/"data"/"history"/"superintendencia_signals.json"; history=load_history(history_path); all_new=[]
    outbox=root/"data"/"outbox";outbox.mkdir(parents=True,exist_ok=True)

    # Estadísticas SuperSalud
    state=root/"data"/"state"/"superintendencia_seen.json"
    if args.reset_state and state.exists():state.unlink()
    items=SuperintendenciaStatsScout().discover_new(SeenStore(state)); save_raw_items(items,root/"data"/"inbox"/"superintendencia_new.json")
    stats=[]
    for raw in items[:args.limit]:
        try:
            s=process_superintendencia_detail(raw,fetch_html(raw.url),cfgs["superintendencia_salud"]);row=s.to_dict()
            row["distribution_free"]=choose_distribution(s.radar_score,s.confidence_score,UserPlan("free"),s.watch_tags,())
            row["distribution_pro"]=choose_distribution(s.radar_score,s.confidence_score,UserPlan("pro"),s.watch_tags,())
            row["signal_types"]=["Datos"];row["scopes"]=["Isapres"];stats.append(row)
        except Exception:pass
    (outbox/"superintendencia_signals.json").write_text(json.dumps({"signals":stats},ensure_ascii=False,indent=2),encoding="utf-8");all_new+=stats

    # Normativa SuperSalud
    state=root/"data"/"state"/"superintendencia_normativa_seen.json"
    if args.reset_state and state.exists():state.unlink()
    reg=_new(SuperintendenciaNormativaScout().discover(),SeenStore(state))
    reg_rows=[]
    for raw in reg[:args.limit]:
        try:reg_rows.append(process_superintendencia_normativa(raw,cfgs["superintendencia_normativa"]))
        except Exception:pass
    (outbox/"superintendencia_normativa_signals.json").write_text(json.dumps({"signals":reg_rows},ensure_ascii=False,indent=2),encoding="utf-8");all_new+=reg_rows

    # SUSESO
    state=root/"data"/"state"/"suseso_seen.json"
    if args.reset_state and state.exists():state.unlink()
    su=_new(SusesoScout().discover(),SeenStore(state)); su_rows=[]
    for raw in su[:args.limit]:
        try:su_rows.append(process_suseso(raw,cfgs["suseso"]))
        except Exception:pass
    (outbox/"suseso_signals.json").write_text(json.dumps({"signals":su_rows},ensure_ascii=False,indent=2),encoding="utf-8");all_new+=su_rows

    # MINSAL noticias oficiales
    state=root/"data"/"state"/"minsal_seen.json"
    if args.reset_state and state.exists():state.unlink()
    mi=_new(MinsalNewsScout().discover(),SeenStore(state)); mi_rows=[]
    for raw in mi[:args.limit]:
        try:mi_rows.append(process_minsal(raw,cfgs["minsal"]))
        except Exception:pass
    (outbox/"minsal_signals.json").write_text(json.dumps({"signals":mi_rows},ensure_ascii=False,indent=2),encoding="utf-8");all_new+=mi_rows

    history=merge_history(history,all_new);save_history(history_path,history)
    print(f"Stats={len(stats)} Normativa={len(reg_rows)} SUSESO={len(su_rows)} MINSAL={len(mi_rows)} Historial={len(history)}")

if __name__=="__main__":main()
