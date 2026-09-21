from __future__ import annotations

from datetime import date
from typing import Iterable

from .models import Signal
from .multisource import rank_for_profile
from .personalization import UserProfile


def _icon(score: int) -> str:
    if score >= 90:
        return "🔴"
    if score >= 75:
        return "🟠"
    return "🟡"


def build_personal_daily_digest(
    signals: Iterable[Signal],
    profile: UserProfile,
    digest_date: str | None = None,
    max_items: int = 5,
) -> str:
    digest_date = digest_date or date.today().isoformat()
    ranked = rank_for_profile(signals, profile)[:max_items]
    lines = [
        f"RADAR SALUD · {digest_date}",
        f"Perfil: {profile.label}",
        "",
        f"{len(ranked)} señales para mirar hoy",
        "",
    ]
    for idx, rs in enumerate(ranked, 1):
        s = rs.signal
        lines.append(f"{_icon(rs.personal_score)} {idx}. {s.title}")
        if s.why_it_matters:
            lines.append(f"Por qué importa: {s.why_it_matters}")
        lines.append(
            f"Para ti {rs.personal_score} · Radar {s.radar_score} · Confianza {s.confidence_score}"
        )
        lines.append(f"{s.category} · {s.source_name}")
        lines.append("")
    if not ranked:
        lines.append("No hay señales suficientemente relevantes y confiables para tu perfil hoy.")
    return "\n".join(lines).rstrip() + "\n"
