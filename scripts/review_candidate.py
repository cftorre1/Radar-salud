"""Read-only deterministic Reviewer: independent process, no repair authority."""
import argparse
import importlib.util
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from radar_salud.editorial_gate import publication_ready
from radar_salud.pending_queue import atomic_json
_statistics_spec=importlib.util.spec_from_file_location("statistics_reviewer",Path(__file__).with_name("statistics_reviewer.py"))
_statistics_module=importlib.util.module_from_spec(_statistics_spec)
_statistics_spec.loader.exec_module(_statistics_module)
review_statistics=_statistics_module.review_statistics

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
        if not any(source.get("status") in ("ok","warning") for source in health.values()):
            fail("data","no_healthy_sources","data/source_health.json","No source has a successful or partial poll")
        policy=json.loads((Path(__file__).resolve().parents[1]/"config/source_freshness_policy.json").read_text())
        max_age=int(policy["daily_max_age_days"])*86400
        non_daily_modes=set(policy.get("non_daily_operation_modes") or [])
        non_daily=set(policy.get("non_daily_sources") or {})
        root=Path(__file__).resolve().parents[1]
        # Sources of the daily capture are never exempted, whatever mode a
        # published health record declares.
        daily={s.get("slug") for name in ("config/sources.json","config/beta_source_configs.json")
               for s in json.loads((root/name).read_text()) if isinstance(s,dict)}
        for slug,source in health.items():
            if source.get("status") not in ("ok","warning"):continue
            checked=datetime.fromisoformat(source["checked_at"].replace("Z","+00:00"))
            age=(datetime.now(timezone.utc)-checked).total_seconds() if checked.tzinfo else float("inf")
            if age < -300:
                fail("data","future_source_check",f"data/source_health.json#sources/{slug}","Source poll timestamp is in the future")
            elif age>max_age:
                activated=[k[len("activated_daily_"):] for k,v in policy.items()
                           if k.startswith("activated_daily_") and isinstance(v,list) and slug in v]
                pending_first_poll=False
                # A naive (offset-less) poll timestamp cannot be compared: no grace, it blocks.
                for day in (activated if checked.tzinfo else []):
                    try:
                        start=datetime.fromisoformat(day.replace("_","-")).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    since=(datetime.now(timezone.utc)-start).total_seconds()
                    # Newly activated daily sources get 3 days for their first daily poll; then they block.
                    # A future activation date never grants grace.
                    if checked<start and 0<=since<=3*86400:
                        pending_first_poll=True
                if pending_first_poll:
                    fail("data","awaiting_first_daily_poll",f"data/source_health.json#sources/{slug}","Source activated for the daily capture; first daily poll pending",severity="warning")
                elif slug not in daily and (slug in non_daily or source.get("operation_mode") in non_daily_modes):
                    # Outside the daily capture by explicit policy: visible, non-blocking.
                    fail("data","stale_non_daily_source",f"data/source_health.json#sources/{slug}","Non-daily source not polled within seven days",severity="warning")
                else:
                    fail("data","stale_source_check",f"data/source_health.json#sources/{slug}","Source was not polled within seven days")
    except (OSError,KeyError,TypeError,ValueError) as exc:
        fail("data","unverified_source_checks","data/source_health.json",str(exc))
    try:
        from radar_salud.normative_autorecord import merged_config
        contract=merged_config(Path(__file__).resolve().parents[1],json.loads((Path(__file__).resolve().parents[1]/"config/normative_editorial_v2.json").read_text()))
        for index,signal in enumerate(signals):
            is_normative=signal.get("event_type")=="REGULATION" or "Normativa" in (signal.get("signal_types") or [])
            if not is_normative:
                continue
            path=f"data/radar_today.json#signals/{index}"
            number="".join(ch for ch in str(signal.get("normative_document_number") or signal.get("normative_document_label") or "") if ch.isdigit())
            record=contract.get("source_records",{}).get(signal.get("source_url")) or contract.get("records",{}).get(number,{})
            title=str(signal.get("display_title") or signal.get("title") or "")
            identity=str(signal.get("normative_document_label") or signal.get("legal_identity") or "")
            context=str(signal.get("normative_context") or "")
            if signal.get("normative_minimal"):
                # Opción A (Dirección 26-oct-2026): verifiable listing facts only + badge + fixed disclaimer.
                from radar_salud.normative_minimal import BADGE, DISCLAIMER, INTERPRETIVE_FIELDS, ISSUERS, _official
                issuer=str(signal.get("source_name") or "")
                short="SUSESO" if "SUSESO" in issuer else "Superintendencia de Salud"
                expected_context=f"Emitida por {issuer} con fecha {signal.get('event_date')}. Asunto oficial: "
                problems=[]
                if record:problems.append("has an approved V2.1 record; must use it")
                if signal.get("editorial_badge")!=BADGE or signal.get("normative_act_scope")!="general":problems.append("badge/scope")
                if issuer not in ISSUERS or not _official(signal.get("source_url"),issuer):problems.append("issuer/official link")
                if not identity or not title.startswith(f"{identity} · {short}: "):problems.append("title template")
                if not context.startswith(expected_context):problems.append("context template")
                if not (signal.get("card_what")==context==signal.get("what_happened")):problems.append("card copy")
                if not (signal.get("why_it_matters")==DISCLAIMER==signal.get("card_why")):problems.append("disclaimer")
                leaked=[f for f in INTERPRETIVE_FIELDS if signal.get(f)]
                if leaked:problems.append("interpretive fields: "+",".join(leaked))
                if problems:
                    fail("editorial","normative_minimal_contract",path,"Minimal normative card: "+"; ".join(problems))
                continue
            if not record or signal.get("normative_title_review_required"):
                fail("editorial","normative_title_needs_review",path,"Normative act has no approved V2.1 editorial record")
            elif (not identity or identity.casefold() not in title.casefold()
                  or not context or context.casefold() in title.casefold()
                  or not any(str(term).casefold() in title.casefold() for term in record.get("subject_terms",[]))
                  or not any(str(term).casefold() in title.casefold() for term in record.get("action_terms",[]))):
                fail("editorial","normative_v21_contract",path,"Headline must contain act identity, subject and action; context must add information")
            elif record.get("resolution_review") and any(
                    not any(str(term).casefold() in title.casefold()
                            for term in record["resolution_review"].get(group,[]))
                    for group in ("decision_terms","affected_act_terms","effect_terms")):
                fail("editorial","normative_resolution_effect",path,"Resolution headline must distinguish its decision, affected prior act and effect")

    except (OSError,ValueError,TypeError) as exc:
        fail("editorial","normative_contract_unavailable","config/normative_editorial_v2.json",str(exc))
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
    for finding in review_statistics(signals):
        findings.append(finding)
    for page in ("index.html","app.js","admin/product.html","admin/product.js","data/product.json"):
        if not (web/page).is_file():fail("ux","missing_asset",page,"Required file missing")
    return dict(reviewer="deterministic-reviewer",candidate_sha=sha,
        reviewed_at=datetime.now(timezone.utc).isoformat(),findings=findings,
        checks={category:not any(f["category"]==category and f["severity"]=="critical" for f in findings)
            for category in ("data","editorial","statistics","ux")},
        limitations=["Semantic/legal accuracy is not certified by deterministic checks.",
            "Browser evidence is required separately for desktop/mobile.",
            "Statistics checks validate declared schema, units, denominators and traceability; they do not replace subject-matter validation of source publications."])

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--web",default="web");p.add_argument("--sha",required=True);p.add_argument("--output",default="artifacts/review.json")
    args=p.parse_args();result=review(Path(args.web),args.sha);atomic_json(Path(args.output),result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(1 if any(f["severity"]=="critical" for f in result["findings"]) else 0)
