"""Deterministic executor for source audit issue #5."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUDIT_IDS={
"superintendencia_normativa","superintendencia","superintendencia_fiscalizacion","minsal",
"suseso","suseso_news","suseso_fiscalizacion","diario_oficial","fonasa","fonasa_datos_abiertos",
"deis","isp_anamed","isp_surveillance","prestadores_data","diario_financiero","pulso_latercera",
"redsalud","bupa_chile","indisa","red_davila","andes_salud","clinicas_achs_salud","clinicas_chile",
"pfizer_chile","achs_seguro_laboral","mutual_seguridad","ist"
}
P0=["diario_financiero","pulso_latercera","fonasa","fonasa_datos_abiertos","isp_anamed","isp_surveillance",
"deis","superintendencia_fiscalizacion","suseso_fiscalizacion","clinicas_achs_salud","achs_seguro_laboral","mutual_seguridad"]

def load(path, fallback):
    p=ROOT/path
    if not p.exists(): return fallback
    return json.loads(p.read_text(encoding="utf-8"))

def classify(slug, row):
    technical=row.get("technical_status") or row.get("status")
    discovered=row.get("discovered")
    published=row.get("published")
    last=row.get("last_signal_at") or row.get("newest_event_date")
    error=row.get("error")
    if technical in {"error","failed"} or error:
        return "technical_error"
    if discovered==0 and not last:
        return "coverage_gap"
    if (discovered or 0)>0 and (published or 0)==0:
        return "discovery_without_publication"
    if last and str(last)[:4] < "2026":
        return "stale_content"
    if technical in {"ok","warning"}:
        return "operational_unverified"
    return "unknown"

def main():
    health=load(Path("data/source_health.json"),{}).get("sources",{})
    beta=load(Path("data/state/beta_source_validation.json"),{})
    beta_rows=beta.get("sources") if isinstance(beta,dict) else {}
    if isinstance(beta_rows,list):
        beta_rows={x.get("source") or x.get("slug"):x for x in beta_rows if isinstance(x,dict)}
    beta_rows=beta_rows or {}
    rows=[]
    for slug in sorted(AUDIT_IDS):
        merged={}
        merged.update(health.get(slug) or {})
        merged.update(beta_rows.get(slug) or {})
        rows.append({
            "slug":slug,
            "priority":"P0" if slug in P0 else "P1",
            "classification":classify(slug,merged),
            "technical_status":merged.get("technical_status") or merged.get("status"),
            "discovered":merged.get("discovered"),
            "published":merged.get("published"),
            "pending":merged.get("pending"),
            "rejected":merged.get("rejected"),
            "last_signal_at":merged.get("last_signal_at") or merged.get("newest_event_date"),
            "checked_at":merged.get("checked_at"),
            "error":merged.get("error"),
        })
    unresolved=[r for r in rows if r["classification"]!="operational_unverified"]
    p0=[r for r in rows if r["priority"]=="P0" and r["classification"]!="operational_unverified"]
    report={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "task_id":"source_audit_issue5_iteration1_recovery_2026_10_09",
        "status":"in_progress",
        "connectors_expected":27,
        "connectors_observed":len(rows),
        "unresolved_count":len(unresolved),
        "p0_unresolved_count":len(p0),
        "next_source":p0[0]["slug"] if p0 else (unresolved[0]["slug"] if unresolved else None),
        "sources":rows,
        "acceptance":{
            "inventory_complete":len(rows)==27,
            "p0_closed":not p0,
            "coverage_effective_validated":False,
            "external_reconciliation_required":True
        }
    }
    out=ROOT/"artifacts/source_audit_executor.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":
    main()
