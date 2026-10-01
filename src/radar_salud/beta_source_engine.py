from __future__ import annotations

import json
from datetime import date, datetime, timezone

from .beta_sources import CuratedBetaSourceScout, PrestadoresDataScout, process_curated_beta_source, process_prestadores_data, media_gate_accepts
from .history import load_history, merge_history, save_history
from .paths import project_root
from .source_health import record as health_record


def _cfgs(root):
    rows=json.loads((root/"config/beta_source_configs.json").read_text(encoding="utf-8"))
    return {x["slug"]:x for x in rows}


def _lane(event_date):
    try:
        age=(date.today()-date.fromisoformat(event_date)).days
        return "LIVE" if 0<=age<=7 else "BACKFILL"
    except Exception:
        return "BACKFILL"


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
    root=project_root()
    cfgs=_cfgs(root)
    history_path=root/"data/history/superintendencia_signals.json"
    history=load_history(history_path)
    audit={"generated_at":datetime.now(timezone.utc).isoformat(),"sources":{},"media_gate_df_rows":0}
    specs=[
        ("prestadores_data",PrestadoresDataScout().discover,process_prestadores_data),
        *[(slug,CuratedBetaSourceScout(slug).discover,process_curated_beta_source)
          for slug in ("red_davila","andes_salud","clinicas_achs_salud","achs_seguro_laboral","mutual_seguridad","ist","pulso_latercera")]
    ]
    for slug,discover,processor in specs:
        rows=[];rejected=0;error=None;found=[]
        try:
            found=discover()
            for raw in found[:3]:
                try:
                    row=processor(raw,cfgs[slug])
                    if row:
                        row["detected_at"]=datetime.now(timezone.utc).isoformat()
                        row["ingestion_mode"]=_lane(row.get("event_date"))
                        rows.append(row)
                    else:
                        rejected+=1
                except Exception:
                    rejected+=1
        except Exception as exc:
            error=type(exc).__name__
        if rows:
            history=merge_history(history,rows)
        health_record(root,slug,name=cfgs[slug]["name"],discovered=len(found),new=0,published=len(rows),
                      rows=rows,pending=0,rejected=rejected,error=error,live_pending=0,backfill_pending=0)
        audit["sources"][slug]={
            "discovered":len(found),"published":len(rows),"rejected_sample":rejected,
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
