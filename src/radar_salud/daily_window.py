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
    value = item.get('raw', {}).get('event_date')
    try:
        published = date.fromisoformat(value)
    except (ValueError, TypeError):
        return False
    return today - timedelta(days=days) <= published <= today
