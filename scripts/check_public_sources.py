"""Replay only the five public-source discoveries without AI or queue writes.

Use --record-health after an actual live poll to update these five health rows.
Captures do not change ingestion watermarks, seen state, history or publication.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from radar_salud.fonasa_sources import FonasaNewsScout, FonasaDataHubScout
from radar_salud.isp_sources import IspAnamedAlertScout, IspSurveillanceScout
from radar_salud.deis_sources import DeisDocumentScout
from radar_salud.public_source_evidence import discovery_diagnostics, failure_details
from radar_salud.public_source_transport import extract_public_source_pdf
from radar_salud.pending_queue import atomic_json
from radar_salud.source_health import record


SCOUTS = (FonasaNewsScout, FonasaDataHubScout, IspAnamedAlertScout, IspSurveillanceScout, DeisDocumentScout)
DEFAULT_OUTPUT = "data/audits/public_sources_c_20261011/runtime_capture.json"


def check(root: Path, *, record_health=False, factories=SCOUTS):
    existing_path=root/"data/source_health.json"
    existing=json.loads(existing_path.read_text()) if existing_path.exists() else {"sources":{}}
    result={"checked_at":datetime.now(timezone.utc).isoformat(),"mode":"discovery_and_document_verification_only",
            "sources":{},"ai_calls":0,"ingestion_state_mutated":False}
    for factory in factories:
        scout=factory();items=[];error=None;details=None
        try:items=scout.discover()
        except Exception as exc:
            error=type(exc).__name__;details=failure_details(exc)
        diagnostics=discovery_diagnostics(scout,items if error is None else None)
        diagnostics["poll_mode"]="discovery_and_document_verification_only"
        document_checks=[]
        for item in items:
            if not item.url.lower().split("?",1)[0].endswith(".pdf"):
                continue
            capture={}
            try:
                text=extract_public_source_pdf(item.url,item.source_slug,max_pages=12,capture_metadata=capture)
                if len(text)<350:raise ValueError("Official PDF has insufficient readable content")
                item.raw_text=text[:9000]
                item.metadata.update(document_verification="readable_pdf",capture_evidence=capture)
                document_checks.append({"url":item.url,"status":"captured",**capture})
            except Exception as exc:
                diagnostics["partial_failure"]=True
                document_checks.append({"url":item.url,"status":"blocked",**failure_details(exc)})
        diagnostics["document_checks"]=document_checks
        verified=diagnostics.get("verified_publications",0)>0
        readable_documents=sum(row["status"]=="captured" for row in document_checks)
        validated=error is None and not diagnostics.get("partial_failure") and verified
        degraded=error is None and verified and bool(diagnostics.get("partial_failure")) and readable_documents>0
        diagnostics["evidence_status"]="capture_pending" if error or diagnostics.get("partial_failure") else "captured" if verified else "publication_unverified"
        result["sources"][scout.SOURCE_SLUG]={
            "checked_at":datetime.now(timezone.utc).isoformat(),
            "technical_status":"error" if error else "degraded" if diagnostics.get("partial_failure") else "ok",
            "discovery_verified":error is None and verified,
            "operational":validated,
            "operative_degraded":degraded,
            "runtime_outcome":"OPERATIVE_VALIDATED" if validated else "OPERATIVE_DEGRADED" if degraded else "not_validated_by_this_runtime",
            "discovered":len(items),"error":error,"error_details":details,"diagnostics":diagnostics,
            "items":[asdict(item) for item in items]}
        if record_health:
            old=existing.get("sources",{}).get(scout.SOURCE_SLUG,{})
            record(root,scout.SOURCE_SLUG,name=scout.SOURCE_NAME,discovered=len(items),new=0,published=0,
                pending=old.get("pending",0),deferred=0,rejected=old.get("rejected",0),rows=[],error=error,
                live_pending=old.get("live_pending"),backfill_pending=old.get("backfill_pending"),
                error_details=details,diagnostics=diagnostics)
    result["operational_sources"]=sum(row["operational"] for row in result["sources"].values())
    result["operative_degraded_sources"]=sum(row["operative_degraded"] for row in result["sources"].values())
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output",default=DEFAULT_OUTPUT)
    parser.add_argument("--record-health",action="store_true")
    args=parser.parse_args();result=check(args.root,record_health=args.record_health)
    output=args.root/args.output;atomic_json(output,result)
    print(json.dumps({"evidence":str(output),"operational_sources":result["operational_sources"],
        "sources":{slug:{"technical_status":row["technical_status"],"discovered":row["discovered"],
                          "failure_signature":(row["error_details"] or {}).get("failure_signature")}
            for slug,row in result["sources"].items()}},ensure_ascii=False,indent=2))
    return 0 if result["operational_sources"]==len(result["sources"]) else 2


if __name__=="__main__":raise SystemExit(main())
