"""Human-reviewed, anchored templates for figures read from official documents (PDF text, spreadsheets).

Decided by Dirección on 29-oct-2026, after two independent reviews broke the generic text heuristics (context windows,
"find the number near a word"). Shared by every statistics family that reads a document:

- F6 Boletín IP (PDF): per-figure templates (PR #112 keeps its own copy in ``stats_capture`` with the same semantics;
  once #112 is merged, ``stats_capture`` imports these helpers instead).
- F2 FEFI (xls/xlsx): sheet / header / row / column templates (``stats_capture_fefi``).

Rules, the same for every family:

1. A template lives in ``config/stats_fichas_v1.json`` and is written from the **real** text of the document, as CI
   prints it in check-run annotations (this sandbox cannot reach the SIS).
2. It is used only when a person reviewed it: ``reviewed_by`` set (not '', 'pendiente', 'pending', 'todo') and
   ``reviewed_at`` set. A ``<<…>>`` placeholder anywhere in it, or no review, means HOLD.
3. Patterns run on **normalized** text (``normalize_text``): case and accents folded, thousands dots removed, all
   whitespace collapsed. A pattern must match **exactly once** in the units it is applied to (cited pages, the
   rows of one sheet…); zero or several matches mean HOLD.
4. ``templates_sha256`` is recorded with every parse, so a change in a template triggers one hash-bound re-check of
   the captured document (the bytes must hash to the recorded SHA-256; the previous parse is kept).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

PLACEHOLDER = re.compile(r"<<[^>]*>>")
UNREVIEWED = frozenset({"", "pendiente", "pending", "todo", "none", "null"})


def fold(text: Any) -> str:
    return str("" if text is None else text).casefold().translate(str.maketrans("áéíóúüñ", "aeiouun"))


def normalize_text(text: Any) -> str:
    """Template text: case and accents folded, thousands dots removed ('1.004.982' → '1004982'), all whitespace
    (newlines included) collapsed to single spaces. Same normalization as F6 checker v2 (PR #112)."""
    t = fold(text)
    t = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", t)
    return re.sub(r"\s+", " ", t).strip()


def has_placeholder(obj: Any) -> bool:
    """A ``<<…>>`` marker in any string of the template (keys included), at any depth."""
    if isinstance(obj, str):
        return bool(PLACEHOLDER.search(obj))
    if isinstance(obj, dict):
        return any(has_placeholder(k) or has_placeholder(v) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return any(has_placeholder(x) for x in obj)
    return False


def reviewed(tpl: dict | None) -> bool:
    tpl = tpl or {}
    return (str(tpl.get("reviewed_by") or "").strip().casefold() not in UNREVIEWED
            and str(tpl.get("reviewed_at") or "").strip().casefold() not in UNREVIEWED)


def review_state(tpl: dict | None) -> str:
    """'not_configured', 'placeholder' or 'unreviewed' (all HOLD), else 'ok'. Documentation keys ('_doc', 'source',
    'source_quote') may describe placeholders without counting as one."""
    if not tpl:
        return "not_configured"
    if has_placeholder({k: v for k, v in tpl.items() if not str(k).startswith("_") and k not in ("source", "source_quote")}):
        return "placeholder"
    if not reviewed(tpl):
        return "unreviewed"
    return "ok"


def templates_sha256(templates: Any) -> str | None:
    if not templates:
        return None
    return hashlib.sha256(json.dumps(templates, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def period_subs(period: str | None) -> dict[str, str]:
    """Tokens a template may use instead of a literal date, so a reviewed template keeps working next quarter:
    {t_year}, {t_month} (Spanish month, folded) and {t1_year} (the year before) of the release period 'YYYY-MM'."""
    m = re.fullmatch(r"(20\d{2})-(\d{2})", str(period or ""))
    if not m or not 1 <= int(m[2]) <= 12:
        return {}
    months = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
              "noviembre", "diciembre")
    return {"t_year": m[1], "t1_year": str(int(m[1]) - 1), "t_month": months[int(m[2]) - 1]}


def compile_pattern(raw: Any, groups: int | None = None, subs: dict[str, str] | None = None) -> tuple[re.Pattern | None, str]:
    """Compile one pattern of a reviewed template: 'placeholder', 'invalid' (bad regex or wrong group count) or 'ok'.
    ``subs`` replaces ``{token}`` by its escaped literal (``period_subs``); a token left without a value is 'invalid'."""
    raw = str(raw or "")
    if not raw or PLACEHOLDER.search(raw):
        return None, "placeholder"
    for key, val in (subs or {}).items():
        raw = raw.replace("{" + key + "}", re.escape(val))
    if re.search(r"\{(?:t_year|t1_year|t_month)\}", raw):
        return None, "invalid"
    try:
        pat = re.compile(raw)
    except re.error:
        return None, "invalid"
    if groups is not None and pat.groups != groups:
        return None, "invalid"
    return pat, "ok"


def match_once(pattern: re.Pattern, units: Iterable[tuple[Any, str]], *, full: bool = False) -> tuple[Any, re.Match | None, str]:
    """Apply ``pattern`` to each (key, normalized text) unit: exactly one match across all units is required.

    ``full=True`` requires the whole unit to match (a cell or a sheet name), otherwise ``search``/``finditer``.
    Returns (key, match, 'ok') or (None, None, 'no_match' | 'multiple_matches:N')."""
    hits = []
    for key, text in units:
        if full:
            m = pattern.fullmatch(text)
            if m:
                hits.append((key, m))
        else:
            hits += [(key, m) for m in pattern.finditer(text)]
    if len(hits) != 1:
        return None, None, "no_match" if not hits else f"multiple_matches:{len(hits)}"
    return hits[0][0], hits[0][1], "ok"
