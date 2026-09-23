from __future__ import annotations
from typing import Any, Dict
from .analysis import analyze_superintendencia
from .extraction import extract_superintendencia_detail
from .models import RawItem, Signal
from .pipeline import build_signal
from .validation import validate_official_item
from .quality import publication_ready
from .data_insights import source_specific_insights, family_from_title

def _xlsx(attachments):
    for a in attachments or []:
        u=(a.get("url") or "")
        if u.lower().endswith((".xlsx",".xls")):return u
    return None

def process_superintendencia_detail(raw: RawItem, html: str, source_cfg: Dict[str, Any]) -> Signal:
    enriched=extract_superintendencia_detail(raw,html)
    validation=validate_official_item(enriched,source_cfg.get("base_confidence",95))
    analysis=analyze_superintendencia(enriched)

    data_insights=[]
    insight_meta={"status":"not_applicable"}
    file_url=_xlsx(enriched.metadata.get("attachments"))
    fam=family_from_title(enriched.title)
    if file_url and fam:
        insight_meta=source_specific_insights(file_url,enriched.title)
        data_insights=insight_meta.get("insights") or []

    enriched.metadata.update({
        "what_happened":analysis.what_happened,
        "key_facts":analysis.key_facts,
        "key_numbers":analysis.key_numbers,
        "why_it_matters":analysis.why_it_matters,
        "who_cares":analysis.who_cares,
        "watch_tags":analysis.watch_tags,
        "scores":analysis.scores,
        "subcategory":analysis.subcategory,
        "confidence_adjustment":validation.confidence_score-source_cfg.get("base_confidence",95),
        "key_points":[],
        "risk_notes":[],
        "data_insights":data_insights,
        "data_insight_meta":insight_meta,
        "validity_text":None,
    })
    signal=build_signal(enriched,source_cfg)
    signal.confidence_score=validation.confidence_score
    signal.validation_status=validation.status
    signal.data_insights=data_insights
    if not publication_ready([signal.title,signal.what_happened,signal.why_it_matters]):
        signal.validation_status="human_review_required"
        signal.distribution="archive"
        signal.confidence_score=min(signal.confidence_score,74)
    row=signal
    return row
