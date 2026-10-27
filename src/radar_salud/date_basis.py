"""Explicit date bases for cards whose source exposes no publication date.

Dirección 27-oct-2026 (decision d): Bupa, Clínicas de Chile documents and the
Intendencia de Prestadores bulletins may publish using the day Alicanto first
detected them, always labelled ``date_basis='first_detected'`` ("Detectado el
…" in the UI) and never as a publication date. Items whose first detection is
older than the daily window are not published.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .processing import DeferredProcessing, RejectedProcessing

CHILE = ZoneInfo("America/Santiago")
FIRST_DETECTED = "first_detected"
DATA_RELEASE = "data_release"
# Dirección 27-oct-2026: first-detection dating never reaches beyond 30 days,
# whatever RADAR_DAILY_WINDOW_DAYS says (its default is 90).
FIRST_DETECTED_MAX_DAYS = 30
_UPLOAD_PATH = re.compile(r"/wp-content/uploads/(20\d{2})/(0[1-9]|1[0-2])/")


def chile_day(value):
    """ISO timestamp (UTC or offset) or ISO date -> Chile calendar date."""
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return date.fromisoformat(text)
    stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=ZoneInfo("UTC"))
    return stamp.astimezone(CHILE).date()


def _window_days():
    from .daily_window import requested_window_days
    return requested_window_days()


def upload_path_month(url):
    """WordPress upload folder (YYYY/MM): when the file was uploaded, not published."""
    match = _UPLOAD_PATH.search(str(url or ""))
    return (int(match[1]), int(match[2])) if match else None


# Sources whose discovered stock predates this rule: the first daily discovery
# records every URL already known as a baseline that never publishes by
# detection (otherwise an old article would appear as "detectado hoy").
BASELINE_SOURCES = ("bupa_chile",)


def baseline_path(root, slug):
    from pathlib import Path
    return Path(root) / "data/state" / f"{slug}_first_detection_baseline.json"


def ensure_first_detection_baseline(root, slug, urls):
    """Create the baseline once (idempotent); returns True when it was created now."""
    import json
    path = baseline_path(root, slug)
    if path.exists():
        return False
    from .pending_queue import atomic_json
    atomic_json(path, {"established_at": datetime.now(ZoneInfo("UTC")).isoformat(),
                       "reason": "first_detection_rule_activation_2026_10_27",
                       "urls": sorted(set(urls))})
    return True


def _check_baseline(raw):
    import json
    if raw.source_slug not in BASELINE_SOURCES:
        return
    from .paths import project_root
    path = baseline_path(project_root(), raw.source_slug)
    if not path.exists():
        raise DeferredProcessing("first_detection_baseline_not_established")
    if raw.url in set(json.loads(path.read_text()).get("urls", [])):
        raise RejectedProcessing("first_detection_baseline_existing_item")


def apply_first_detected(raw, *, today=None, window_days=None):
    """Date an undated item by its first detection, or refuse it.

    ``raw.metadata['first_detected_at']`` is the queue's ``detected_at`` for
    this item (set by the engine before processing). Raises
    ``RejectedProcessing`` when the detection is outside the window, and when
    a WordPress upload folder proves the file predates the window (a late
    first detection of an old document is not new information).
    """
    detected = raw.metadata.get("first_detected_at")
    if not detected:
        raise DeferredProcessing("first_detection_timestamp_unavailable")
    _check_baseline(raw)
    day = chile_day(detected)
    today = today or datetime.now(CHILE).date()
    window_days = min(window_days or _window_days(), FIRST_DETECTED_MAX_DAYS)
    start = today - timedelta(days=window_days)
    if day > today:
        raise DeferredProcessing("first_detection_in_future")
    if day < start:
        raise RejectedProcessing("first_detection_outside_daily_window")
    uploaded = upload_path_month(raw.url)
    if uploaded and uploaded < (start.year, start.month):
        raw.metadata["upload_path_month"] = "%04d-%02d" % uploaded
        raise RejectedProcessing("first_detected_but_uploaded_before_window")
    raw.event_date = day.isoformat()
    raw.metadata.update(date_basis=FIRST_DETECTED, first_detected_date=day.isoformat(),
                        publication_date=None, publication_date_source=None,
                        date_label="Detectado el %s (la fuente no informa fecha de publicación)" % day.isoformat())
    return day.isoformat()


def label_first_detected(row, raw):
    """Carry the explicit basis to the public row; never a publication date."""
    row.update(date_basis=FIRST_DETECTED, first_detected_at=raw.metadata.get("first_detected_at"),
               first_detected_date=raw.metadata.get("first_detected_date"),
               publication_date=None, date_label=raw.metadata.get("date_label"))
    return row
