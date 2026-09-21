from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreInputs:
    economic_impact: int      # 0..100
    regulatory_impact: int    # 0..100
    scope: int                # 0..100
    novelty: int              # 0..100
    actionability: int        # 0..100
    source_quality: int       # 0..100


def _bounded(value: int) -> int:
    return max(0, min(100, int(value)))


def calculate_radar_score(s: ScoreInputs) -> int:
    """
    Pesos V1:
      económico       25%
      regulatorio     20%
      alcance         15%
      novedad         15%
      accionabilidad  15%
      fuente          10%
    """
    score = (
        0.25 * _bounded(s.economic_impact)
        + 0.20 * _bounded(s.regulatory_impact)
        + 0.15 * _bounded(s.scope)
        + 0.15 * _bounded(s.novelty)
        + 0.15 * _bounded(s.actionability)
        + 0.10 * _bounded(s.source_quality)
    )
    return round(score)


def relevance_band(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 70:
        return "important"
    if score >= 50:
        return "context"
    return "archive"


def confidence_gate(confidence_score: int) -> str:
    if confidence_score >= 90:
        return "publishable"
    if confidence_score >= 75:
        return "cross_check"
    return "hold"
