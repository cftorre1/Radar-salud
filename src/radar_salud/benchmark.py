from __future__ import annotations
from collections import defaultdict
from typing import Iterable, Dict
from .models import Signal


def benchmark_signal_activity(signals: Iterable[Signal], strategic_theme: str | None = None) -> Dict[str, dict]:
    """Transparent activity benchmark based on observed public Signals.

    This deliberately measures *visible activity*, not quality or superiority.
    """
    rows = defaultdict(lambda: {"signals": 0, "event_types": defaultdict(int), "themes": defaultdict(int)})
    for s in signals:
        if strategic_theme and strategic_theme.casefold() not in {t.casefold() for t in s.strategic_theme}:
            continue
        for entity in s.entities:
            rows[entity]["signals"] += 1
            rows[entity]["event_types"][s.event_type] += 1
            for theme in s.strategic_theme:
                rows[entity]["themes"][theme] += 1
    return {
        entity: {
            "signals": data["signals"],
            "event_types": dict(data["event_types"]),
            "themes": dict(data["themes"]),
        }
        for entity, data in sorted(rows.items(), key=lambda x: x[1]["signals"], reverse=True)
    }
