"""Read-only deterministic Reviewer: independent process, no repair authority."""
import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from radar_salud.editorial_gate import publication_ready
from radar_salud.pending_queue import atomic_json

def review(web, sha):
    findings=[]
    def fail(category, code, path, detail, severity="critical"):
        findings.append(dict(category=category,code=code,path=path,detail=detail,severity=severity))
    try:
        payload=json.loads((web/"data/radar_today.json").read_text())
        signals=payload["signals"]
        if not isinstance(signals,list) or not signals:raise ValueError("Empty/non-list signals")
        generated=datetime.fromisoformat(payload["generated_at"].replace("Z","+00:00"))
        if generated.tzinfo is None:raise ValueError("Missing generated timezone")
        if (datetime.now(timezone.utc)-generated).total_seconds()>7*86400:
            fail("data","stale_snapshot","data/radar_today.json","Snapshot older than seven days")
    except Exception as exc:
        fail("data","invalid_snapshot","data/radar_today.json",str(exc))
        signals=[]
    # Rebuilding a snapshot changes generated_at even when no source was
    # checked. Source health is separate evidence of the last actual poll.
    try:
        health=json.loads((web/"data/source_health.json").read_text())["sources"]
        if not health:raise ValueError("No monitored sources")
        for slug,source in health.items():
            if source.get("status") not in ("ok","warning"):continue
            checked=datetime.fromisoformat(source["checked_at"].replace("Z","+00:00"))
            if checked.tzinfo is None or (datetime.now(timezone.utc)-checked).total_seconds()>7*86400:
                fail("data","stale_source_check",f"data/source_health.json#sources/{slug}","Source was not polled within seven days")
    except (OSError,KeyError,TypeError,ValueError) as exc:
        fail("data","unverified_source_checks","data/source_health.json",str(exc))
    identities=set()
    for index,signal in enumerate(signals):
        path=f"data/radar_today.json#signals/{index}"
        identity=(signal.get("source_url"),signal.get("title"))
        if identity in identities:fail("data","duplicate_identity",path,"Duplicate source/title")
        identities.add(identity)
        if urlparse(signal.get("source_url","")).scheme not in ("http","https"):
            fail("data","unsafe_source",path,"Source must use HTTP(S)")
        try:
            if date.fromisoformat(signal["event_date"][:10])>date.today():raise ValueError("Future publication")
        except (ValueError,KeyError,TypeError) as exc:fail("data","publication_date",path,str(exc))
        try:
            passed,reason,_=publication_ready(dict(signal))
            if not passed:fail("editorial",reason,path,"Existing publication gate rejected signal")
        except Exception as exc:fail("editorial","invalid_fields",path,type(exc).__name__)
        for field in ("related_context","source_alternatives","source_documents"):
            for related in signal.get(field,[]) or []:
                if related.get("url") and urlparse(related["url"]).scheme not in ("http","https"):
                    fail("data","unsafe_link",path+"/"+field,"Link must use HTTP(S)")
    for page in ("index.html","app.js","admin/product.html","admin/product.js","data/product.json"):
        if not (web/page).is_file():fail("ux","missing_asset",page,"Required file missing")
    return dict(reviewer="deterministic-reviewer",candidate_sha=sha,
        reviewed_at=datetime.now(timezone.utc).isoformat(),findings=findings,
        checks={category:not any(f["category"]==category and f["severity"]=="critical" for f in findings)
            for category in ("data","editorial","ux")},
        limitations=["Semantic/legal accuracy is not certified by deterministic checks.",
            "Browser evidence is required separately for desktop/mobile."])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--web",default="web");p.add_argument("--sha",required=True);p.add_argument("--output",default="artifacts/review.json")
    args=p.parse_args();result=review(Path(args.web),args.sha);atomic_json(Path(args.output),result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(1 if any(f["severity"]=="critical" for f in result["findings"]) else 0)
