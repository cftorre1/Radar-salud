from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, List, Dict
from .models import Signal, Trend


@dataclass(frozen=True)
class TrendRules:
    min_signals: int = 5
    min_entities: int = 3
    min_confidence: int = 80
    accelerating_growth_pct: float = 50.0


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def detect_trends(signals: Iterable[Signal], as_of: date | None = None, window_days: int = 90, rules: TrendRules = TrendRules()) -> List[Trend]:
    """Find candidate trends using structured strategic_theme tags.

    A trend is not merely a frequently mentioned topic: V2 requires at least
    `min_signals`, `min_entities` and sufficient average confidence. Intensity
    is compared with the immediately preceding window.
    """
    as_of = as_of or date.today()
    current_start = as_of - timedelta(days=window_days - 1)
    previous_start = current_start - timedelta(days=window_days)

    buckets: Dict[str, dict] = defaultdict(lambda: {
        "current": [], "previous": [], "entities": set(), "types": set()
    })

    for signal in signals:
        d = _parse_date(signal.event_date)
        if not d:
            continue
        for theme in signal.strategic_theme:
            key = theme.strip().casefold()
            if not key:
                continue
            if current_start <= d <= as_of:
                buckets[key]["current"].append(signal)
                buckets[key]["entities"].update(signal.entities)
                buckets[key]["types"].update(signal.institution_types)
            elif previous_start <= d < current_start:
                buckets[key]["previous"].append(signal)

    out: List[Trend] = []
    for key, b in buckets.items():
        cur = b["current"]
        prev = b["previous"]
        if len(cur) < rules.min_signals or len(b["entities"]) < rules.min_entities:
            continue
        avg_conf = round(sum(s.confidence_score for s in cur) / len(cur))
        if avg_conf < rules.min_confidence:
            continue
        current_intensity = float(len(cur))
        previous_intensity = float(len(prev))
        growth = None if previous_intensity == 0 else round((current_intensity / previous_intensity - 1) * 100, 1)
        if previous_intensity == 0:
            status = "emerging"
        elif growth is not None and growth >= rules.accelerating_growth_pct:
            status = "accelerating"
        elif growth is not None and growth <= -25:
            status = "cooling"
        else:
            status = "established"
        out.append(Trend(
            trend_key=key,
            title=key.replace("_", " ").title(),
            strategic_theme=key,
            status=status,
            window_days=window_days,
            signal_count=len(cur),
            entity_count=len(b["entities"]),
            current_intensity=current_intensity,
            previous_intensity=previous_intensity,
            growth_pct=growth,
            confidence_score=avg_conf,
            institution_types=sorted(b["types"]),
            entities=sorted(b["entities"]),
            evidence_signal_ids=[],
        ))
    return sorted(out, key=lambda t: (t.status == "accelerating", t.signal_count, t.confidence_score), reverse=True)
