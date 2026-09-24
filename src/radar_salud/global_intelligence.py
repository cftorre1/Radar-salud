from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse


ALLOWED_PUBLISHERS = {
    "Reuters": {"reuters.com"},
    "CB Insights": {"cbinsights.com"},
    "McKinsey": {"mckinsey.com"},
    "Deloitte": {"deloitte.com"},
    "PwC": {"pwc.com"},
    "WHO": {"who.int"},
    "PAHO": {"paho.org"},
    "BCG": {"bcg.com"},
}
MATERIAL_TYPES = {"research", "outlook", "report", "high_trust_press"}
TREND_STATES = {"not_established", "candidate", "established"}


def _required(value, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"missing {label}")
    return text


def _iso_day(value, label: str) -> date:
    text = _required(value, label)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid {label}") from exc
    return date.fromisoformat(text)


def _trusted_source(source: dict, generated_day: date) -> None:
    publisher = _required(source.get("publisher"), "source publisher")
    if publisher not in ALLOWED_PUBLISHERS:
        raise ValueError("publisher outside approved Global Intelligence sources")
    url = _required(source.get("url"), "source url")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(host == d or host.endswith("." + d) for d in ALLOWED_PUBLISHERS[publisher]):
        raise ValueError("source publisher/domain mismatch")
    _required(source.get("title"), "source title")
    _required(source.get("evidence"), "source evidence")
    published = _iso_day(source.get("published_at"), "source published_at")
    captured = _iso_day(source.get("captured_at"), "source captured_at")
    if not published <= captured <= generated_day:
        raise ValueError("source dates must satisfy published_at <= captured_at <= generated_at")
    if source.get("material_type") not in MATERIAL_TYPES:
        raise ValueError("source is not approved research/outlook/report material")


def validate(payload: dict) -> dict:
    if payload.get("access_tier") != "PREMIUM":
        raise ValueError("Global Intelligence must remain PREMIUM")
    try:
        generated = datetime.fromisoformat(str(payload.get("generated_at") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid generated_at") from exc
    generated_day = generated.date()
    if generated_day > date.today():
        raise ValueError("generated_at cannot be in the future")
    themes = payload.get("themes")
    if not isinstance(themes, list) or not themes:
        raise ValueError("at least one Global Theme is required")
    seen = set()
    for theme in themes:
        theme_id = _required(theme.get("id"), "theme id")
        if theme_id in seen:
            raise ValueError("duplicate Global Theme")
        seen.add(theme_id)
        if theme.get("kind") != "global_theme":
            raise ValueError("global finding must be labelled global_theme")
        for key in ("title", "global_finding", "why_it_matters"):
            _required(theme.get(key), key)
        sources = theme.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("Global Theme requires traceable sources")
        for source in sources:
            _trusted_source(source, generated_day)
        watch = theme.get("chile_watch") or {}
        if watch.get("kind") != "hypothesis":
            raise ValueError("Qué mirar en Chile must be explicitly hypothetical")
        _required(watch.get("text"), "Chile hypothesis")
        state = watch.get("trend_chile_status")
        if state not in TREND_STATES:
            raise ValueError("invalid Trend Chile state")
        local = watch.get("compatible_local_signals")
        if not isinstance(local, list):
            raise ValueError("compatible local signals must be explicit")
        # Lite has no canonical Chile-evidence pipeline yet. Fail closed instead of
        # trusting arbitrary URLs or a caller-provided `verified` boolean.
        if state != "not_established" or local:
            raise ValueError("Trend Chile promotion requires the canonical Chile evidence pipeline")
    return payload


def load(path: str | Path) -> dict:
    return validate(json.loads(Path(path).read_text(encoding="utf-8")))


def export(source: str | Path, destination: str | Path) -> None:
    payload = load(source)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
