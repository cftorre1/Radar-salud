from __future__ import annotations
from typing import List
from .models import Signal, SignalConnection


def _norm(values):
    return {str(v).strip().casefold() for v in values if str(v).strip()}


def connection_strength(a: Signal, b: Signal) -> int:
    """Deterministic first-pass strength for CONNECT.

    LLM interpretation can later explain a connection, but candidate discovery
    starts with structured overlap to remain cheap and auditable.
    """
    score = 0
    entity_overlap = _norm(a.entities) & _norm(b.entities)
    theme_overlap = _norm(a.strategic_theme) & _norm(b.strategic_theme)
    topic_overlap = _norm(a.topics) & _norm(b.topics)
    institution_overlap = _norm(a.institution_types) & _norm(b.institution_types)

    score += min(55, 45 * len(entity_overlap))
    score += min(30, 25 * len(theme_overlap))
    score += min(15, 5 * len(topic_overlap))
    score += min(10, 5 * len(institution_overlap))
    return min(100, score)


def connect_signals(a_id: str, a: Signal, b_id: str, b: Signal, threshold: int = 40) -> SignalConnection | None:
    strength = connection_strength(a, b)
    if strength < threshold:
        return None
    entities = sorted(_norm(a.entities) & _norm(b.entities))
    themes = sorted(_norm(a.strategic_theme) & _norm(b.strategic_theme))
    if entities:
        rel = "SAME_ENTITY"
    elif themes:
        rel = "SAME_THEME"
    else:
        rel = "RELATED"
    rationale_bits: List[str] = []
    if entities:
        rationale_bits.append("entidades compartidas: " + ", ".join(entities))
    if themes:
        rationale_bits.append("temas estratégicos compartidos: " + ", ".join(themes))
    return SignalConnection(
        signal_a_id=a_id,
        signal_b_id=b_id,
        relationship_type=rel,
        strength_score=strength,
        rationale="; ".join(rationale_bits) or "coincidencia estructurada",
        shared_entities=entities,
        shared_themes=themes,
    )
