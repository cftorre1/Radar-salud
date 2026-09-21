from __future__ import annotations

from typing import Any, Dict

from .analysis import analyze_superintendencia
from .extraction import extract_superintendencia_detail
from .models import RawItem, Signal
from .pipeline import build_signal
from .validation import validate_official_item


def process_superintendencia_detail(raw: RawItem, html: str, source_cfg: Dict[str, Any]) -> Signal:
    enriched = extract_superintendencia_detail(raw, html)
    validation = validate_official_item(enriched, source_cfg.get("base_confidence", 95))
    analysis = analyze_superintendencia(enriched)

    enriched.metadata.update({
        "what_happened": analysis.what_happened,
        "key_facts": analysis.key_facts,
        "key_numbers": analysis.key_numbers,
        "why_it_matters": analysis.why_it_matters,
        "who_cares": analysis.who_cares,
        "watch_tags": analysis.watch_tags,
        "scores": analysis.scores,
        "subcategory": analysis.subcategory,
        # build_signal adds this to source base confidence.
        "confidence_adjustment": validation.confidence_score - source_cfg.get("base_confidence", 95),
    })

    signal = build_signal(enriched, source_cfg)
    signal.confidence_score = validation.confidence_score
    signal.validation_status = validation.status
    return signal
