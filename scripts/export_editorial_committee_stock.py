"""Export the audited stock into a committee decision artifact without mutating history."""
from __future__ import annotations
import json
from pathlib import Path

def build(audit: dict) -> dict:
    items=[]
    counts={"PASS":0,"REVISE":0,"HOLD":0,"REJECT":0}
    for row in audit.get("items", []):
        decision=str(row.get("decision") or "").lower()
        verdict={"accept":"PASS","degrade":"HOLD","group":"HOLD","reject":"REJECT"}.get(decision,"REVISE")
        counts[verdict]=counts.get(verdict,0)+1
        items.append({
            "id":row.get("id"),
            "snapshot_index":row.get("snapshot_index"),
            "event_date":row.get("event_date"),
            "source":row.get("source"),
            "signal_type":row.get("type"),
            "editorial_decision":decision,
            "committee_verdict":verdict,
            "individual_card_allowed":verdict=="PASS" and row.get("signal_worthy") is True,
            "materiality_score":row.get("materiality_score"),
            "value_category":row.get("value_category"),
            "decision_that_may_change":row.get("decision_that_may_change"),
        })
    return {
        "source_audit_id":audit.get("audit_id"),
        "frozen_snapshot_sha256":audit.get("frozen_snapshot_sha256"),
        "signals_reviewed":len(items),
        "counts":counts,
        "items":items,
    }

if __name__=="__main__":
    root=Path(".")
    audit=json.loads((root/"data/editorial_audit_90d_2026_09_26.json").read_text(encoding="utf-8"))
    target=root/"data/editorial_committee_stock.json"
    target.write_text(json.dumps(build(audit),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
