from __future__ import annotations

from datetime import date
from typing import Iterable, List

from .models import Signal


def _priority_icon(score: int) -> str:
    if score >= 85:
        return "🔴"
    if score >= 70:
        return "🟠"
    return "🟡"


def build_daily_digest(signals: Iterable[Signal], digest_date: str | None = None, max_items: int = 5) -> str:
    """Render the Pro daily digest. No immediate alerts are emitted here.

    WATCH remains a separate distribution path by design.
    """
    digest_date = digest_date or date.today().isoformat()
    eligible: List[Signal] = [
        s for s in signals
        if s.radar_score >= 50 and s.confidence_score >= 75
    ]
    eligible.sort(key=lambda s: (s.radar_score, s.confidence_score), reverse=True)
    selected = eligible[:max_items]

    lines = [f"RADAR SALUD · {digest_date}", "", f"{len(selected)} señales para mirar hoy", ""]
    for idx, s in enumerate(selected, 1):
        lines.append(f"{_priority_icon(s.radar_score)} {idx}. {s.title}")
        if s.why_it_matters:
            lines.append(f"Por qué importa: {s.why_it_matters}")
        lines.append(f"Radar Score {s.radar_score} · Confianza {s.confidence_score}")
        lines.append(f"Fuente: {s.source_name}")
        lines.append("")
    if not selected:
        lines.append("No hay señales suficientemente relevantes y confiables para hoy.")
    return "\n".join(lines).rstrip() + "\n"
