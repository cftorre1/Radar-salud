"""Fail-closed weekly publication contract, evaluated in Chile local time."""
import re
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

# Presentation A (Dirección, 27-oct-2026): headline → charts → short essay → watch → notes.
# Cheap deterministic rules from design/insight/panel.md §4; a failing insight stays hidden.
FOOTNOTE = re.compile(r"\[\^(n\d+)\]")
INFERENCE_MARKERS = re.compile(r"\b(sugiere|sugieren|podría|podrían|estimamos|alicanto)\b", re.I)
SAFE_FORMULA = re.compile(r"^[0-9.\s+\-*/()]+$")

def presentation_a(weekly):
    return isinstance(weekly, dict) and isinstance(weekly.get("essay"), dict)

def _words(text):
    return len(FOOTNOTE.sub("", str(text or "")).split())

def _paragraphs(section):
    xs = (section or {}).get("paragraphs") if isinstance(section, dict) else None
    return [str(x) for x in xs] if isinstance(xs, list) else []

def presentation_a_errors(weekly):
    """Return the list of broken presentation-A rules (empty list means PASS)."""
    errors = []
    essay = weekly.get("essay") or {}
    facts, reading = _paragraphs(essay.get("facts")), _paragraphs(essay.get("reading"))
    if not facts or not reading:
        errors.append("essay_facts_and_reading_required")
    if any(INFERENCE_MARKERS.search(FOOTNOTE.sub("", x)) for x in facts):
        errors.append("facts_contain_inference_marker")
    if any(re.match(r"\s*hecho\s*:", x, re.I) for x in reading):
        errors.append("reading_contains_fact_prefix")
    words = sum(_words(x) for x in facts + reading)
    if not 150 <= words <= 250:
        errors.append(f"essay_words_out_of_range:{words}")
    if _words(weekly.get("dek")) > 40:
        errors.append("dek_over_40_words")
    if len(str(weekly.get("headline") or "")) > 140:
        errors.append("headline_over_140_chars")
    notes = weekly.get("notes") if isinstance(weekly.get("notes"), list) else []
    note_ids = [n.get("id") for n in notes if isinstance(n, dict)]
    if len(set(note_ids)) != len(note_ids) or not all(isinstance(n, dict) and n.get("text") for n in notes):
        errors.append("notes_invalid_or_duplicated")
    charts = weekly.get("charts") if isinstance(weekly.get("charts"), list) else []
    estimates = weekly.get("estimates") if isinstance(weekly.get("estimates"), list) else []
    refs = [m for x in facts + reading for m in FOOTNOTE.findall(x)]
    refs += [r for c in charts if isinstance(c, dict) for r in (c.get("note_refs") or [])]
    refs += [e.get("note_ref") for e in estimates if isinstance(e, dict) and e.get("note_ref")]
    if any(r not in note_ids for r in refs):
        errors.append("footnote_ref_unresolved")
    if any(n not in refs for n in note_ids):
        errors.append("note_never_referenced")
    for chart in charts:
        for row in (chart.get("rows") or []) if isinstance(chart, dict) else []:
            if isinstance(row, dict) and row.get("style") == "partial" and not row.get("partial_label"):
                errors.append("partial_row_without_label")
    for item in weekly.get("watch") or []:
        if not isinstance(item, dict) or _words(item.get("explanation")) < 12:
            errors.append("watch_explanation_too_short")
    for estimate in estimates:
        formula = str((estimate or {}).get("formula") or "")
        if formula and SAFE_FORMULA.match(formula):
            try:
                value = eval(formula, {"__builtins__": {}}, {})  # digits and arithmetic only (SAFE_FORMULA)
            except Exception:
                errors.append("estimate_formula_invalid")
                continue
            if abs(value - float(estimate.get("value"))) > 0.05:
                errors.append(f"estimate_mismatch:{estimate.get('id')}")
        elif formula:
            errors.append("estimate_formula_not_deterministic")
    return errors

def reviewed_weekly(payload, as_of=None):
    if not isinstance(payload, dict):
        return None
    audit = payload.get("audit") or {}
    weekly = payload.get("weekly_insight")
    if audit.get("verdict") != "PASS" or audit.get("editorial_business_review_pass") is not True:
        return None
    if not freshness_gate(weekly, as_of)["eligible"]:
        return None
    if presentation_a(weekly):
        if presentation_a_errors(weekly):
            return None
        required = ("headline", "dek", "essay", "notes", "source_refs")
    else:
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
