from __future__ import annotations
import json,re
from pathlib import Path
from typing import Any
DEFAULT_CONFIG=Path(__file__).resolve().parents[2]/"config"/"editorial_intelligence_committee_v1.json"

def _load(path:Path|str=DEFAULT_CONFIG)->dict[str,Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _signal_type(signal:dict[str,Any])->str:
    xs=signal.get("signal_types") or []
    return str(xs[0]) if xs else "Noticias"

def _routine_accreditation(signal:dict[str,Any])->bool:
    text=" ".join(str(signal.get(k) or "") for k in ("title","what_happened","why_it_matters")).lower()
    if signal.get("source_name")!="Superintendencia de Salud": return False
    routine=any(x in text for x in ("plan de corrección","mantiene su acreditación","declara acreditado","registro público de prestadores institucionales"))
    systemic=any(x in text for x in ("nuevo estándar","modifica el sistema de acreditación","todos los prestadores"))
    return bool(routine and not systemic)

def weekly_candidate_eligibility(signal:dict[str,Any])->dict[str,Any]:
    decision=str(signal.get("editorial_decision") or signal.get("editorial_source_decision") or "accept").lower()
    if signal.get("feed_visibility") is False:return {"eligible":False,"reason":"not_visible_after_editorial_gate"}
    if decision in {"degrade","group","reject"}:return {"eligible":False,"reason":"editorial_"+decision}
    if _routine_accreditation(signal):return {"eligible":False,"reason":"routine_accreditation_context_only"}
    return {"eligible":True,"reason":"material_signal"}

def build_committee_artifact(signal:dict[str,Any],config:dict[str,Any]|None=None)->dict[str,Any]:
    cfg=config or _load();stype=_signal_type(signal)
    members=list(cfg.get("signal_panels",{}).get(stype) or cfg.get("signal_panels",{}).get("Noticias") or [])
    objections=[];title=str(signal.get("display_title") or signal.get("title") or "")
    decision=str(signal.get("editorial_decision") or signal.get("editorial_source_decision") or "accept").lower()
    if decision=="reject":objections.append("materiality_reject")
    if stype=="Normativa":
        identity=signal.get("normative_document_label") or re.search(r"\b(Resolución(?: Exenta)?|Circular|Oficio|Decreto)\b.*?N[°º]?\s*[\w/.-]+",title,re.I)
        if not identity:objections.append("normative_identity_missing")
    if not signal.get("source_url"):objections.append("source_missing")
    verdict="REJECT" if decision=="reject" else ("REVISE" if objections else "PASS")
    return {"committee_version":cfg.get("version","1.0"),"signal_type":stype,"members":members,"materiality_decision":decision,"public_title":title,"what_happened":signal.get("card_what") or signal.get("what_happened"),"why_it_matters":signal.get("card_why") or signal.get("why_it_matters"),"evidence_map":[{"source":signal.get("source_name"),"url":signal.get("source_url")}] if signal.get("source_url") else [],"uncertainties":signal.get("risk_notes") or [],"value_level":signal.get("statistical_value_level") or signal.get("editorial_value_category"),"publication_decision":decision,"critical_objections":objections,"verdict":verdict,"parser_or_research_debt_if_any":signal.get("parser_debt") or None}


def build_stock_committee_report(signals:list[dict[str,Any]],config:dict[str,Any]|None=None)->dict[str,Any]:
    """Apply the permanent committee gate to a stock snapshot without mutating history."""
    cfg=config or _load()
    items=[]
    counts={"PASS":0,"REVISE":0,"HOLD":0,"REJECT":0}
    for signal in signals:
        artifact=build_committee_artifact(signal,cfg)
        decision=str(signal.get("editorial_decision") or signal.get("editorial_source_decision") or "accept").lower()
        if decision=="group":
            artifact["verdict"]="HOLD"
            artifact["hold_reason"]="group_into_pulse_trend_or_benchmark"
        elif decision=="degrade" and artifact["verdict"]=="PASS":
            artifact["verdict"]="HOLD"
            artifact["hold_reason"]="context_only_after_editorial_audit"
        artifact["signal_id"]=signal.get("id") or signal.get("source_url") or signal.get("title")
        artifact["individual_card_allowed"]=artifact["verdict"]=="PASS" and signal.get("feed_visibility") is not False
        counts[artifact["verdict"]]=counts.get(artifact["verdict"],0)+1
        items.append(artifact)
    return {
        "committee_version":cfg.get("version","1.0"),
        "signals_reviewed":len(items),
        "counts":counts,
        "items":items,
    }
