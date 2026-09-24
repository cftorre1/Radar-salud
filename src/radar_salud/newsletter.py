from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Mapping, Sequence


def _date(value: object) -> date | None:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def weekly_material(
    signals: Iterable[Mapping[str, object]],
    as_of: str | date | None = None,
    *,
    days: int = 7,
) -> list[Mapping[str, object]]:
    """Return auditable weekly material; BACKFILL is never treated as new mail."""
    end = as_of if isinstance(as_of, date) else _date(as_of) or date.today()
    start = end - timedelta(days=days - 1)
    eligible = []
    for signal in signals:
        published = _date(signal.get("event_date"))
        if not published or not start <= published <= end:
            continue
        if signal.get("ingestion_mode") != "LIVE":
            continue
        if int(signal.get("radar_score") or 0) < 70:
            continue
        if int(signal.get("confidence_score") or 0) < 75:
            continue
        if not signal.get("source_url"):
            continue
        eligible.append(signal)
    return sorted(
        eligible,
        key=lambda s: (int(s.get("radar_score") or 0), str(s.get("event_date") or "")),
        reverse=True,
    )


def _matches(signal: Mapping[str, object], preferences: Sequence[str]) -> bool:
    if not preferences:
        return True
    tags = {
        str(x).casefold()
        for key in ("signal_types", "scopes", "watch_tags")
        for x in (signal.get(key) or [])
    }
    return bool(tags.intersection(x.casefold() for x in preferences))


def render_free_weekly(signals: Sequence[Mapping[str, object]], as_of: str) -> tuple[str, str] | None:
    selected = list(signals[:5])
    if not selected:
        return None
    lines = ["# Alicanto Salud · Resumen semanal", "", f"{len(selected)} cambios relevantes esta semana.", ""]
    for index, signal in enumerate(selected, 1):
        lines += [
            f"**{index}. {signal.get('title', '')}**",
            str(signal.get("what_happened") or "").strip(),
            f"[Fuente original]({signal['source_url']})",
            "",
        ]
    lines += ["—", "Alicanto Salud · Encuentra lo que importa."]
    return f"Alicanto Salud · Lo que cambió · {as_of}", "\n".join(lines)


def render_premium_weekly(
    signals: Sequence[Mapping[str, object]],
    as_of: str,
    preferences: Sequence[str] = (),
) -> tuple[str, str] | None:
    selected = [signal for signal in signals if _matches(signal, preferences)][:8]
    if not selected:
        return None
    lines = ["# Alicanto Salud PREMIUM · Tu resumen semanal", "", f"{len(selected)} señales para revisar.", ""]
    for index, signal in enumerate(selected, 1):
        lines += [
            f"## {index}. {signal.get('title', '')}",
            f"Qué ocurrió: {signal.get('what_happened', '')}",
            f"Por qué importa: {signal.get('why_it_matters', '')}",
            f"Fuente: {signal.get('source_name', '')} · {signal['source_url']}",
            "",
        ]
    return f"Alicanto Salud PREMIUM · Tu semana · {as_of}", "\n".join(lines)
