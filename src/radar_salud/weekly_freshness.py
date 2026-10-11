"""Fail-closed weekly publication contract, evaluated in Chile local time."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

WINDOW_DAYS = 7

def chile_today():
    return datetime.now(ZoneInfo("America/Santiago")).date()

def iso_day(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        return None

def freshness_gate(signal, as_of=None):
    today = as_of or chile_today()
    if not isinstance(signal, dict):
        return {"eligible": False, "reason": "missing_insight"}
    event = iso_day(signal.get("event_date"))
    anchor = iso_day(signal.get("freshness_anchor_date", signal.get("event_date")))
    expiry = iso_day(signal.get("expires_on")) if "expires_on" in signal else None
    valid = bool(event and anchor and 0 <= (today-event).days < WINDOW_DAYS
                 and 0 <= (today-anchor).days < WINDOW_DAYS
                 and ("expires_on" not in signal or expiry and today < expiry))
    return {"eligible": valid, "reason": "fresh" if valid else "stale_future_or_unverified_date",
            "as_of": today.isoformat(), "timezone": "America/Santiago", "window_days": WINDOW_DAYS,
            "anchor_date": anchor.isoformat() if anchor else None,
            "expires_on": min(anchor+timedelta(days=WINDOW_DAYS), expiry or date.max).isoformat() if anchor else None}

def reviewed_weekly(payload, as_of=None):
    if not isinstance(payload, dict):
        return None
    audit = payload.get("audit") or {}
    weekly = payload.get("weekly_insight")
    if audit.get("verdict") != "PASS" or audit.get("editorial_business_review_pass") is not True:
        return None
    if not freshness_gate(weekly, as_of)["eligible"]:
        return None
    required = ("summary", "insight_reading", "decision_use", "what_to_watch", "uncertainties", "source_refs")
    if not all(weekly.get(k) for k in required):
        return None
    refs = weekly["source_refs"]
    if not isinstance(refs, list) or not refs or not all(isinstance(x, str) and x.startswith("https://") for x in refs):
        return None
    return weekly

def reconcile_weekly_publication(generated, approved, as_of=None):
    """Keep one reviewed publication version; retain new attempts separately."""
    from copy import deepcopy
    attempt=deepcopy(generated)
    current=reviewed_weekly(approved, as_of)
    if current:
        result=deepcopy(approved)
        result.update(status="pass",weekly_insight=deepcopy(current),
                      model=deepcopy(approved.get("model") or current.get("model_trace")))
    else:
        result={"status":"hidden_fail_closed","weekly_insight":None,"top3":[],"model":None,
                "audit":{"verdict":"HOLD","editorial_business_review_pass":False,
                         "reason":"no_fresh_reviewed_publication"}}
    result.update(generation_status=attempt.get("status"),generation_attempt=attempt)
    return result
