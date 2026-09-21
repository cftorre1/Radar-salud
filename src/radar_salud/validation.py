from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .models import RawItem


@dataclass
class ValidationResult:
    confidence_score: int
    status: str
    reasons: List[str] = field(default_factory=list)


def validate_official_item(raw: RawItem, base_confidence: int = 95) -> ValidationResult:
    """Deterministic V1 gate for official sources.

    Confidence measures evidence completeness, not importance.
    """
    score = base_confidence
    reasons: List[str] = []

    if not raw.url.startswith("https://"):
        score -= 15
        reasons.append("source URL is not HTTPS")
    if not raw.event_date:
        score -= 8
        reasons.append("publication date missing")
    if len(raw.raw_text.strip()) < 80:
        score -= 15
        reasons.append("description too short")
    if not raw.metadata.get("attachments"):
        score -= 3
        reasons.append("no downloadable attachment detected")

    score = max(0, min(100, score))
    if score >= 90:
        status = "automatic"
    elif score >= 75:
        status = "cross_checked"
    else:
        status = "human_review_required"
    return ValidationResult(score, status, reasons)
