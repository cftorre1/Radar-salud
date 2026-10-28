"""Bound daily work without deleting the retained historical inventory."""
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

def requested_window_days():
    raw = os.environ.get('RADAR_DAILY_WINDOW_DAYS', '90')
    if raw not in {'30', '60', '90'}:
        raise ValueError('RADAR_DAILY_WINDOW_DAYS must be 30, 60 or 90')
    return int(raw)

def eligible_daily_item(item, *, today=None, days=None):
    days = requested_window_days() if days is None else days
    if days == 90:
        return True  # Preserve the existing historical processing contract.
    today = today or datetime.now(ZoneInfo('America/Santiago')).date()
    published = item_date(item)
    if published is None:
        return False
    return today - timedelta(days=days) <= published <= today


FISCALIZATION_PUBLICATION_LAG_MAX_DAYS = 60


def lagged_publication_date(raw):
    """SIS lists sanctions days or weeks after their emission (IP/7463-7464: emitted 23-sep,
    listed 13-oct). The act became public on the listing day, so the processing window uses
    that day; a gap beyond 60 days is a bulk re-dating of old listings, never news."""
    if not str(raw.get('source_slug') or '').endswith('fiscalizacion'):
        return None
    meta = raw.get('metadata') or {}
    try:
        emitted = date.fromisoformat(str(raw.get('event_date'))[:10])
        published = date.fromisoformat(str(meta.get('publication_date'))[:10])
    except (ValueError, TypeError):
        return None
    if meta.get('date_conflicts'):
        return None
    return published if 0 < (published - emitted).days <= FISCALIZATION_PUBLICATION_LAG_MAX_DAYS else None


def item_date(item):
    """Publication date; items whose source gives no date use the day they were first detected
    (Dirección 27-oct-2026: undated items were left pending forever)."""
    lagged = lagged_publication_date(item.get('raw', {}))
    if lagged:
        return lagged
    for value in (item.get('raw', {}).get('event_date'), item.get('detected_at')):
        try:
            return date.fromisoformat(str(value)[:10])
        except (ValueError, TypeError):
            continue
    return None
