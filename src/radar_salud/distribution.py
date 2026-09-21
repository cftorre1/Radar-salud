from dataclasses import dataclass
from typing import Iterable

from .scoring import relevance_band, confidence_gate


@dataclass(frozen=True)
class UserPlan:
    name: str  # free | pro


def choose_distribution(
    radar_score: int,
    confidence_score: int,
    plan: UserPlan,
    signal_watch_tags: Iterable[str] = (),
    user_watch_tags: Iterable[str] = (),
) -> str:
    """
    Producto V1:
    - FREE: digest semanal; nunca push normal durante el día.
    - PRO: digest diario; una sola entrega normal por día.
    - WATCH: única excepción; alerta inmediata si hay match explícito,
      relevancia crítica y confianza suficiente.
    """
    band = relevance_band(radar_score)
    gate = confidence_gate(confidence_score)

    signal_tags = set(signal_watch_tags)
    user_tags = set(user_watch_tags)
    watch_match = bool(signal_tags & user_tags)

    if watch_match and band == "critical" and gate == "publishable":
        return "watch_immediate"

    if gate == "hold":
        return "archive"

    if plan.name == "pro":
        if band in {"critical", "important"}:
            return "daily_digest"
        if band == "context":
            return "web"
        return "archive"

    # free
    if band in {"critical", "important", "context"}:
        return "weekly_digest"
    return "archive"
