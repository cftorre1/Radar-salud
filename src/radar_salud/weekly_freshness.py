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

# Dirección 27-oct-2026: the weekly insight is renewed every MONDAY. A Monday-anchored
# insight is valid from its anchor Monday until (excluding) the next Monday, and may
# analyse evidence published up to MONDAY_EVIDENCE_DAYS before the anchor.
MONDAY_EVIDENCE_DAYS = 14
# Sunset of the Friday→Monday bridge (legacy insights may stretch to the first Monday only).
BRIDGE_SUNSET = date(2026, 11, 2)

def monday_anchor(day=None):
    """The Monday (Chile calendar) that anchors the weekly insight for ``day``."""
    day = day or chile_today()
    return day - timedelta(days=day.weekday())

def monday_freshness_gate(signal, as_of=None):
    today = as_of or chile_today()
    anchor = iso_day(signal.get("freshness_anchor_date"))
    event = iso_day(signal.get("event_date"))
    expiry = iso_day(signal.get("expires_on"))
    valid = bool(anchor and event and expiry and anchor.weekday() == 0
                 and expiry == anchor + timedelta(days=WINDOW_DAYS)
                 and anchor <= today < expiry
                 and 0 <= (anchor - event).days <= MONDAY_EVIDENCE_DAYS)
    return {"eligible": valid, "reason": "fresh" if valid else "monday_window_closed_or_invalid",
            "as_of": today.isoformat(), "timezone": "America/Santiago", "window_days": WINDOW_DAYS,
            "anchor_kind": "monday", "anchor_date": anchor.isoformat() if anchor else None,
            "expires_on": expiry.isoformat() if expiry else None}

def freshness_gate(signal, as_of=None):
    today = as_of or chile_today()
    if not isinstance(signal, dict):
        return {"eligible": False, "reason": "missing_insight"}
    if signal.get("anchor_kind") == "monday":
        return monday_freshness_gate(signal, as_of)
    event = iso_day(signal.get("event_date"))
    anchor = iso_day(signal.get("freshness_anchor_date", signal.get("event_date")))
    expiry = iso_day(signal.get("expires_on")) if "expires_on" in signal else None
    window = WINDOW_DAYS
    # Transition to Monday insights (Dirección 27-oct-2026): a legacy insight may stay valid until the
    # next Monday when its expires_on is that Monday and at most 10 days after the anchor. The bridge
    # is a one-off for the switch: it only applies to insights expiring on or before BRIDGE_SUNSET.
    if (expiry and anchor and expiry <= BRIDGE_SUNSET and expiry.weekday() == 0
            and WINDOW_DAYS < (expiry-anchor).days <= 10):
        window = (expiry-anchor).days
    valid = bool(event and anchor and 0 <= (today-event).days < window
                 and 0 <= (today-anchor).days < window
                 and ("expires_on" not in signal or expiry and today < expiry))
    return {"eligible": valid, "reason": "fresh" if valid else "stale_future_or_unverified_date",
            "as_of": today.isoformat(), "timezone": "America/Santiago", "window_days": WINDOW_DAYS,
            "anchor_date": anchor.isoformat() if anchor else None,
            "expires_on": min(anchor+timedelta(days=window), expiry or date.max).isoformat() if anchor else None}

# Presentation A (Dirección, 27-oct-2026): headline → charts → short essay → watch → notes.
# Cheap deterministic rules from design/insight/panel.md §4; a failing insight stays hidden.
FOOTNOTE = re.compile(r"\[\^(n\d+)\]")
INFERENCE_MARKERS = re.compile(r"\b(sugiere|sugieren|podría|podrían|estimamos|alicanto)\b", re.I)
SAFE_FORMULA = re.compile(r"^[0-9.\s+\-*/()]+$")

# Rule 3 (traceability): every number shown must exist in key_figures, chart rows or a
# declared estimate. Dates, years and normative IDs are not quantities and are removed first.
MONTHS = r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
DATE_PHRASE = re.compile(r"\b\d{1,2}(?:\s*(?:y|al|–|-)\s*\d{1,2})?\s+de\s+" + MONTHS + r"(?:\s+(?:de|del)\s+\d{4})?", re.I)
# Short press dates: "23 oct", "8-9 oct.", "(10 de oct)".
DATE_SHORT = re.compile(r"\b\d{1,2}(?:\s*(?:y|al|–|-)\s*\d{1,2})?\s+(?:de\s+)?"
                        r"(?:ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)\.?(?![a-záéíóúñ])", re.I)
YEAR = re.compile(r"(?<![\d.,])(?:19|20)\d{2}(?![\d]|,\d)")
NORMATIVE_ID = re.compile(
    r"\b(?:circular(?:es)?|ley(?:es)?|d\.\s?s\.|ds|dfl|decreto(?:\s+supremo)?|resoluci[oó]n(?:\s+exenta)?|res\.\s?ex\.|"
    r"oficio|art(?:\.|[ií]culos?)|inciso|norma\s+t[eé]cnica)\s*(?:n[°º.]?\s*)?(?:(?:IF|SS)/N?[°º]?\s*)?\d+(?:\.\d+)*(?:/\d+)?"
    r"|\b(?:IF|SS)/N?[°º]?\s*\d+(?:\.\d+)*", re.I)
NUMBER = re.compile(r"(?<![\w.,])[-−]?\d{1,3}(?:\.\d{3})+(?:,\d+)?(?![\d])|(?<![\w.,])[-−]?\d+(?:,\d+)?(?![\d])")
RULE_VERBS = re.compile(
    r"\b(?:obliga|obligan|exige|exigen|permite|permiten|proh[ií]be|proh[ií]ben|limita|limitan|fija|fijan|establece|establecen|"
    r"debe|deben|deber[aá]n?|rige|regir[aá]|regula|regulan|crea|ordena|impide|autoriza|restringe|define|dispone|sanciona|"
    r"exime|elimina|reduce|ampl[ií]a|prorroga|posterga|sube|baja)\b", re.I)

def _strip_non_quantities(text):
    text = FOOTNOTE.sub("", str(text or ""))
    text = NORMATIVE_ID.sub(" ", text)
    text = DATE_PHRASE.sub(" ", text)
    text = DATE_SHORT.sub(" ", text)
    return YEAR.sub(" ", text)

def parse_number(token):
    t = token.replace("−", "-").replace(".", "").replace(",", ".")
    return float(t)

def numbers_in(text):
    """Quantities written in Chilean format: 5.155.495 · 12,3 · −22 (dates, years and IDs excluded)."""
    out = []
    for m in NUMBER.finditer(_strip_non_quantities(text)):
        token = m.group(0)
        decimals = len(token.split(",", 1)[1]) if "," in token else 0
        out.append((token, parse_number(token), decimals))
    return out

def _round_half_up(value, decimals):
    from decimal import Decimal, ROUND_HALF_UP
    q = Decimal(1).scaleb(-decimals)
    return float(Decimal(str(abs(value))).quantize(q, rounding=ROUND_HALF_UP))

def number_traces(value, decimals, corpus):
    """A shown number traces when it equals a corpus value rounded to the shown precision."""
    target = abs(value)
    return any(abs(target - _round_half_up(c, decimals)) < 1e-9 for c in corpus)

def trace_corpus(weekly):
    """Declared origins: key_figures, estimate values and estimate formula operands.

    estimates[].inputs and .display are NOT origins (any number written there would otherwise
    trace itself); they are checked against the estimate value and, in ``verify_candidate``,
    against the evidence package."""
    corpus = []
    for fig in weekly.get("key_figures") or []:
        corpus += [n for _, n, _ in numbers_in(fig)]
    for estimate in weekly.get("estimates") or []:
        if not isinstance(estimate, dict):
            continue
        if isinstance(estimate.get("value"), (int, float)):
            corpus.append(float(estimate["value"]))
        formula = str(estimate.get("formula") or "")
        if SAFE_FORMULA.match(formula):
            corpus += [float(t) for t in re.findall(r"\d+(?:\.\d+)?", formula)]
    return corpus

def chart_values(chart):
    for row in chart.get("rows") or []:
        if not isinstance(row, dict):
            continue
        values = row.get("values") if isinstance(row.get("values"), dict) else {"value": row.get("value")}
        for value in values.values():
            if isinstance(value, (int, float)):
                yield row.get("label"), float(value)

def strict_display_scan(weekly):
    """Monday-anchored insights (generated by the pipeline) trace EVERY displayed text field. The
    human-reviewed legacy insight of 23-oct (bridged until 2-nov) keeps the original scope."""
    return isinstance(weekly, dict) and weekly.get("anchor_kind") == "monday"

def displayed_texts(weekly, strict=True):
    """(where, text) for every text a reader sees. Non-strict keeps the legacy scope
    (headline, dek, essay, watch) used by the human-reviewed Friday insights."""
    essay = weekly.get("essay") or {}
    texts = [("headline", weekly.get("headline")), ("dek", weekly.get("dek"))]
    texts += [("essay.facts", x) for x in _paragraphs(essay.get("facts"))]
    texts += [("essay.reading", x) for x in _paragraphs(essay.get("reading"))]
    for item in weekly.get("watch") or []:
        if isinstance(item, dict):
            texts += [("watch", item.get("headline")), ("watch", item.get("explanation"))]
    if not strict:
        return texts
    texts += [("insight_teaser", weekly.get("insight_teaser")), ("title", weekly.get("title")),
              ("summary", weekly.get("summary")), ("watch_heading", weekly.get("watch_heading"))]
    for key in ("facts", "reading"):
        if isinstance(essay.get(key), dict):
            texts.append((f"essay.{key}.heading", essay[key].get("heading")))
    for chart in weekly.get("charts") or []:
        if not isinstance(chart, dict):
            continue
        where = f"chart.{chart.get('id')}"
        texts += [(f"{where}.{k}", chart.get(k)) for k in ("headline", "subtitle", "source", "footnote")]
        texts += [(f"{where}.series", s.get("label")) for s in chart.get("series") or [] if isinstance(s, dict)]
        for row in chart.get("rows") or []:
            if isinstance(row, dict):
                texts += [(f"{where}.row_label", row.get("label")), (f"{where}.partial_label", row.get("partial_label"))]
    texts += [("notes", n.get("text")) for n in weekly.get("notes") or [] if isinstance(n, dict)]
    for source in weekly.get("sources") or []:
        if isinstance(source, dict):
            texts += [(f"sources.{k}", source.get(k)) for k in ("label", "role", "short_label", "short_role")]
    for est in weekly.get("estimates") or []:
        if isinstance(est, dict):
            texts.append(("estimate.label", est.get("label")))
    return [(w, t) for w, t in texts if t]

def untraced_numbers(weekly, corpus=None, strict=None):
    """Rule 3: numbers shown without a declared origin (key_figures, estimate value or formula)."""
    corpus = trace_corpus(weekly) if corpus is None else corpus
    strict = strict_display_scan(weekly) if strict is None else strict
    texts = displayed_texts(weekly, strict)
    missing = [f"{where}:{token}" for where, text in texts for token, value, decimals in numbers_in(text)
               if not number_traces(value, decimals, corpus)]
    for est in weekly.get("estimates") or []:
        if not isinstance(est, dict) or not est.get("display"):
            continue
        own = [float(est["value"])] if isinstance(est.get("value"), (int, float)) else []
        missing += [f"estimate.{est.get('id')}.display:{token}" for token, value, decimals in numbers_in(est["display"])
                    if not number_traces(value, decimals, own + corpus)]
    for chart in weekly.get("charts") or []:
        if isinstance(chart, dict):
            missing += [f"chart.{chart.get('id')}:{label}={value}" for label, value in chart_values(chart)
                        if not number_traces(value, 1, corpus) and not number_traces(value, 0, corpus)]
    return missing

def chart_repetition_warnings(weekly):
    """Rule 3 (warning only): a chart value repeated in essay.facts is redundant with the chart."""
    shown = {round(abs(v), 1) for c in weekly.get("charts") or [] if isinstance(c, dict) for _, v in chart_values(c)}
    facts = _paragraphs((weekly.get("essay") or {}).get("facts"))
    return sorted({f"chart_value_repeated_in_facts:{t}" for x in facts for t, v, _ in numbers_in(x) if round(abs(v), 1) in shown})

def _sentences(text):
    return [x for x in re.split(r"(?<=[.;:!?])\s+", FOOTNOTE.sub("", str(text or ""))) if x.strip()]

def _explains_rule(text):
    plain = NORMATIVE_ID.sub(" ", text)
    return bool(RULE_VERBS.search(plain)) and len(plain.split()) >= 8

def unexplained_normative_ids(weekly):
    """Rule 5: a normative ID (Circular, Ley, DS, art., Resolución…) is accepted only when the
    same watch item, or the same sentence elsewhere, says in plain words what the rule does."""
    errors = []
    for i, item in enumerate(weekly.get("watch") or []):
        if not isinstance(item, dict):
            continue
        ids = NORMATIVE_ID.findall(f"{item.get('headline') or ''} {item.get('explanation') or ''}")
        if ids and not _explains_rule(str(item.get("explanation") or "")):
            errors += [f"watch[{i}]:{x.strip()}" for x in ids]
    essay = weekly.get("essay") or {}
    texts = [("headline", weekly.get("headline")), ("dek", weekly.get("dek"))]
    texts += [("essay", x) for x in _paragraphs(essay.get("facts")) + _paragraphs(essay.get("reading"))]
    for where, text in texts:
        for sentence in _sentences(text):
            ids = NORMATIVE_ID.findall(sentence)
            if ids and not _explains_rule(sentence):
                errors += [f"{where}:{x.strip()}" for x in ids]
    return errors

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
    for item in untraced_numbers(weekly):
        errors.append(f"number_untraced:{item}")
    for item in unexplained_normative_ids(weekly):
        errors.append(f"normative_id_unexplained:{item}")
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
