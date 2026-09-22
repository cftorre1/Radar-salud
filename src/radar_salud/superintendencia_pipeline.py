from __future__ import annotations
from typing import Any, Dict
from .analysis import analyze_superintendencia
from .extraction import extract_superintendencia_detail
from .models import RawItem, Signal
from .pipeline import build_signal
from .validation import validate_official_item
from .quality import publication_ready
from .document_intelligence import analyze_attachments

def process_superintendencia_detail(raw: RawItem, html: str, source_cfg: Dict[str, Any]) -> Signal:
    enriched=extract_superintendencia_detail(raw,html)
    validation=validate_official_item(enriched,source_cfg.get("base_confidence",95))
    analysis=analyze_superintendencia(enriched)
    intel=analyze_attachments(enriched.metadata.get("attachments",[]))
    enriched.metadata.update({
        "what_happened":analysis.what_happened,"key_facts":analysis.key_facts,
        "key_numbers":analysis.key_numbers,"why_it_matters":analysis.why_it_matters,
        "who_cares":analysis.who_cares,"watch_tags":analysis.watch_tags,"scores":analysis.scores,
        "subcategory":analysis.subcategory,
        "confidence_adjustment":validation.confidence_score-source_cfg.get("base_confidence",95),
        "key_points":intel.get("key_points",[]),"risk_notes":intel.get("risk_notes",[]),
        "data_insights":intel.get("data_insights",[]),"validity_text":intel.get("validity_text"),
    })
    signal=build_signal(enriched,source_cfg);signal.confidence_score=validation.confidence_score;signal.validation_status=validation.status
    if not publication_ready([signal.title,signal.what_happened,signal.why_it_matters]):
        signal.validation_status="human_review_required";signal.distribution="archive";signal.confidence_score=min(signal.confidence_score,74)
    return signal
