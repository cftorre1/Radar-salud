from __future__ import annotations
import os,re
from pathlib import Path
from .models import RawItem
from .pipeline import build_signal
from .document_intelligence import extract_pdf_text, fallback_normative_analysis
from .llm_analysis import analyze_normative_pdf
from .analysis_cache import get_cached, put_cached, needs_upgrade

VALID_SCOPES={"Isapres","Fonasa","Prestadores","Salud pública","Salud laboral","Farma / medicamentos","Healthtech"}

def _refs(raw_refs,own_title):
    ids=[];contexts=[];own=own_title.lower().replace(" ","")
    for item in raw_refs or []:
        if isinstance(item,dict):rid=(item.get("id") or "").strip();rel=(item.get("relationship") or "").strip()
        else:rid=str(item).strip();rel="Antecedente normativo citado por el documento actual."
        if not rid or rid.lower().replace(" ","") in own:continue
        if rid not in ids:ids.append(rid)
        if not any(x["id"]==rid for x in contexts):contexts.append({"id":rid,"relationship":rel})
    return ids[:8],contexts[:8]

def _deterministic_actors(text:str,source_scope:str)->list[str]:
    t=(text or "").lower();out=[]
    if re.search(r"\bisapre(?:s)?\b|instituciones? de salud previsional",t):out.append("Isapres")
    if re.search(r"\bfonasa\b|fondo nacional de salud",t):out.append("Fonasa")
    if re.search(r"\bprestador(?:es)?\b|\bcl[ií]nica(?:s)?\b|\bhospital(?:es)?\b",t):out.append("Prestadores")
    if re.search(r"\bfarmac|\bmedicamento|\blaboratorio",t):out.append("Farma / medicamentos")
    if re.search(r"\bmutual|\borganismos? administradores?\b|\blempleador",t):out.append("Salud laboral")
    if not out and source_scope in VALID_SCOPES:out.append(source_scope)
    return list(dict.fromkeys(out))

def process_superintendencia_normativa(raw:RawItem,source_cfg):
    source_scope=raw.metadata.get("scope","Sistema de salud")
    attachments=raw.metadata.get("attachments",[]) or []
    pdf_url=next((a.get("url") for a in attachments if a.get("url") and ".pdf" in a.get("url","").lower()),None)
    summary=raw.raw_text if raw.raw_text and raw.raw_text!=raw.title else f"La autoridad publicó {raw.title}."
    root=Path(__file__).resolve().parents[2];cached=get_cached(root,pdf_url) if pdf_url else None;intelligent=(cached or {}).get("analysis") if cached else None
    if pdf_url and (not intelligent or needs_upgrade(cached)):
        fresh=analyze_normative_pdf(title=raw.title,pdf_url=pdf_url,source_name=raw.source_name,scope=source_scope,fallback_summary=summary)
        if fresh:
            intelligent=fresh;put_cached(root,pdf_url,intelligent,model=os.getenv("RADAR_DEEP_MODEL","gpt-5.6-terra"))
    if not intelligent:intelligent=fallback_normative_analysis(extract_pdf_text(pdf_url) if pdf_url else "",raw.title,summary)
    refs,contexts=_refs(intelligent.get("references",[]),raw.title);what=(intelligent.get("what_happened") or summary).strip();why=(intelligent.get("why_it_matters") or "").strip()
    actors=[x for x in (intelligent.get("affected_actors") or []) if x in VALID_SCOPES]
    if not actors:actors=_deterministic_actors(" ".join([what,why,raw.title]),source_scope)
    processes=[str(x).strip() for x in (intelligent.get("affected_processes") or []) if str(x).strip()][:3]
    raw.metadata.update({"what_happened":what,"why_it_matters":why,"key_facts":[what],"watch_tags":["normativa"]+[x.lower() for x in actors]+[raw.source_name.lower()],"signal_types":["Normativa"],"scopes":actors or ["Sistema de salud"],"affected_processes":processes,"event_type":"REGULATION","scores":{"economic":55,"regulatory":95,"scope":82,"novelty":85,"actionability":90},"subcategory":"Acto regulatorio","key_points":[x.strip() for x in intelligent.get("key_points",[]) if x and "vigencia" not in x.lower()][:3],"risk_notes":[x.strip() for x in intelligent.get("review_points",[]) if x][:3],"validity_text":intelligent.get("validity_text"),"related_reference_ids":refs,"source_documents":attachments})
    s=build_signal(raw,source_cfg);row=s.to_dict();row["signal_types"]=["Normativa"];row["scopes"]=actors or ["Sistema de salud"];row["affected_processes"]=processes;row["category"]="Regulación & Legal";row["radar_score"]=max(row["radar_score"],82);row["related_reference_ids"]=refs;row["related_reference_contexts"]=contexts;return row
