from __future__ import annotations

import json
from datetime import datetime, timezone

from .beta_sources import PrestadoresDataScout, media_gate_accepts
from .beta_sources_fast import FastCuratedBetaSourceScout
from .history import load_history, save_history
from .paths import project_root
from .source_health import record as health_record


def _cfgs(root):
    rows=json.loads((root/"config/beta_source_configs.json").read_text(encoding="utf-8"))
    return {x["slug"]:x for x in rows}


def _apply_media_gate(history):
    changed=0
    for row in history:
        url=str(row.get("source_url") or "")
        if "df.cl/" not in url:
            continue
        body=" ".join(str(row.get(k) or "") for k in ("title","what_happened","why_it_matters"))
        if media_gate_accepts(row.get("title",""),body):
            row["evidence_maturity"]="media_reported"
            row["confirmation_policy"]="upgrade_same_signal_when_company_or_official_source_confirms"
        else:
            row["feed_visibility"]=False
            row["publication_gate_reason"]="media_early_signal_gate"
        changed+=1
    return changed


def main():
    root=project_root();cfgs=_cfgs(root)
    history_path=root/"data/history/superintendencia_signals.json"
    history=load_history(history_path)
    audit={"generated_at":datetime.now(timezone.utc).isoformat(),"sources":{},"media_gate_df_rows":0}
    specs=[("prestadores_data",PrestadoresDataScout().discover)]
    specs += [(slug,FastCuratedBetaSourceScout(slug).discover) for slug in
              ("red_davila","andes_salud","clinicas_achs_salud","achs_seguro_laboral","mutual_seguridad","ist","pulso_latercera")]
    for slug,discover in specs:
        found=[];error=None
        try:
            found=discover()
        except Exception as exc:
            error=type(exc).__name__
        health_record(root,slug,name=cfgs[slug]["name"],discovered=len(found),new=0,published=0,
                      rows=[],pending=0,rejected=0,error=error,live_pending=0,backfill_pending=0)
        audit["sources"][slug]={
            "discovered":len(found),"published":0,
            "technical_status":"error" if error else "ok","error":error,
            "newest_event_date":max([x.event_date for x in found if x.event_date],default=None)
        }
    audit["media_gate_df_rows"]=_apply_media_gate(history)
    save_history(history_path,history)
    out=root/"data/state/beta_source_validation.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False))


if __name__=="__main__":
    main()
