from __future__ import annotations
import os
from pathlib import Path
from .models import RawItem
from .pipeline import build_signal
from .document_intelligence import extract_pdf_text, fallback_normative_analysis
from .llm_analysis import analyze_normative_pdf
from .analysis_cache import get_cached, put_cached

def process_superintendencia_normativa(raw: RawItem, source_cfg):
    scope=raw.metadata.get("scope","Sistema de salud")
    attachments=raw.metadata.get("attachments",[]) or []
    pdf_url=next((a.get("url") for a in attachments if a.get("url") and ".pdf" in a.get("url","").lower()),None)
    summary=raw.raw_text if raw.raw_text and raw.raw_text!=raw.title else f"La autoridad publicó {raw.title}."
    root=Path(__file__).resolve().parents[2]

    intelligent=get_cached(root,pdf_url) if pdf_url else None
    if intelligent:intelligent=intelligent.get("analysis")
    if not intelligent and pdf_url:
        intelligent=analyze_normative_pdf(title=raw.title,pdf_url=pdf_url,source_name=raw.source_name,scope=scope,fallback_summary=summary)
        if intelligent:
            put_cached(root,pdf_url,intelligent,model=os.getenv("RADAR_DEEP_MODEL","gpt-5.6-terra"))
    if not intelligent:
        intelligent=fallback_normative_analysis(extract_pdf_text(pdf_url) if pdf_url else "",raw.title,summary)

    what=(intelligent.get("what_happened") or summary).strip()
    why=(intelligent.get("why_it_matters") or "").strip()
    key_points=[x.strip() for x in intelligent.get("key_points",[]) if x and "vigencia" not in x.lower()][:3]
    review=[x.strip() for x in intelligent.get("review_points",[]) if x][:3]
    refs=[x.strip() for x in intelligent.get("references",[]) if x][:8]
    raw.metadata.update({
      "what_happened":what,"why_it_matters":why,"key_facts":[what],
      "watch_tags":["normativa",scope.lower(),raw.source_name.lower()],
      "signal_types":["Normativa"],"scopes":[scope],"event_type":"REGULATION",
      "scores":{"economic":55,"regulatory":95,"scope":82,"novelty":85,"actionability":90},
      "subcategory":"Acto regulatorio","key_points":key_points,"risk_notes":review,
      "validity_text":intelligent.get("validity_text"),"related_reference_ids":refs,
      "source_documents":attachments,
    })
    s=build_signal(raw,source_cfg);row=s.to_dict()
    row["signal_types"]=["Normativa"];row["scopes"]=[scope];row["category"]="Regulación & Legal";row["radar_score"]=max(row["radar_score"],82)
    row["related_reference_ids"]=refs
    return row
