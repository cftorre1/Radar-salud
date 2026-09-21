from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional

from .models import Signal
from .personalization import UserProfile, personal_relevance


@dataclass
class RankedSignal:
    signal: Signal
    personal_score: int


def merge_signals(batches: Iterable[Iterable[Signal]]) -> List[Signal]:
    """Merge and deduplicate Signals across sources.

    V0 key intentionally conservative: URL when available, otherwise normalized
    title + event date. Cross-source semantic dedup comes later.
    """
    out: List[Signal] = []
    seen = set()
    for batch in batches:
        for signal in batch:
            key = signal.source_url.strip().lower() if signal.source_url else f"{signal.title.casefold()}|{signal.event_date or ''}"
            if key in seen:
                continue
            seen.add(key)
            out.append(signal)
    return out


def rank_for_profile(signals: Iterable[Signal], profile: Optional[UserProfile] = None) -> List[RankedSignal]:
    ranked = [
        RankedSignal(signal=s, personal_score=personal_relevance(s, profile) if profile else s.radar_score)
        for s in signals
        if s.confidence_score >= 75 and s.radar_score >= 50
    ]
    ranked.sort(key=lambda x: (x.personal_score, x.signal.radar_score, x.signal.confidence_score), reverse=True)
    return ranked
