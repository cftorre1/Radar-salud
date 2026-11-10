"""Weekly insight, format A v2: news-style essay (Dirección, 10-nov-2026).

The ~250-word block with fixed sections («Qué pasó», «Lectura Alicanto», «Qué mirar») becomes a
~750-word essay that reads like a news story: lead → context → development → closing. «Qué mirar»
is folded into the closing as prose. This module holds the v2 schema and its deterministic rules;
``weekly_freshness`` and ``weekly_insight_a`` dispatch here when ``schema_version`` is v2.

Schema ``weekly_insight_a_v2`` (authored fields; ids, dates and source_refs are stamped by
``weekly_insight_a.normalize_draft``)::

  kicker            topic line above the headline ("Personas mayores y cuidados")
  headline, dek     same caps as v1: ≤ 140 characters, ≤ 40 words
  body              ordered blocks:
                      {"type": "paragraph", "text"}            the first block is the lead
                      {"type": "subhead", "text"}              narrative h2, never a section label
                      {"type": "quote", "text", "source_ref", "attribution", "context"}
                      {"type": "chart", "chart_ref"}           right after the paragraph that explains it
                      {"type": "key_figures"}                  where the optional box goes
  closing           {"text"}: the end of the story, with what to watch written as prose
  key_figures       optional {"items": [{"label", "value", "text", "universe", "kind", "source_ref",
                      "source_label", "estimate_ref"?, "wide"?}]}: 3–5 cards
  charts            [{"id", "form": "bars|columns|paired_bars", "headline", "subtitle", "unit", "rows",
                      "kind": "oficial|prensa|estimacion", "kind_label"?, "estimate_ref"?, "source"}]
  estimates         [{"id", "label", "value", "unit", "display", "formula", "inputs"}]
  method            {"estimates": [estimate ids], "estimates_note"?, "discarded": [...], "limits": [...]}
  sources           [{"id": "f1", "type": "oficial|prensa", "label", "url", "role"}]
  evidence_figures  figures copied from the evidence package (origin of every displayed number)
  evidence_excerpts [{"source_ref", "text"}]: literal excerpts (origin of every quote)
  notes             optional [{"id": "n1", "kind", "text"}], referenced as [^n1]
  verified_on       date the figures were checked (byline)

Inline markup inside paragraph, closing, chart source and key-figure text:

  [Fiscalía Nacional Económica](f1)   direct link to source f1 + numbered superscript to the list
  [uno de cada tres](est:sin_auto)    Alicanto estimate: dashed underline, formula in the method
  [^n1]                               evidence note (optional)

Nothing here calls a model or the network.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

SCHEMA_V2 = "weekly_insight_a_v2"
# v1 (fixed sections) stays valid for the archive and for anchors before this Monday. From this
# Monday on, a v1 Monday insight fails verification and is never served (Dirección 10-nov-2026).
V2_REQUIRED_FROM = date(2026, 11, 16)

ESSAY_WORDS_MIN, ESSAY_WORDS_MAX = 500, 1000          # hard limits (FAIL)
ESSAY_WORDS_TARGET = (600, 900)                       # target (warning only)
HEADLINE_MAX_CHARS, DEK_MAX_WORDS, KICKER_MAX_CHARS = 140, 40, 60
KEY_FIGURES_MIN, KEY_FIGURES_MAX = 3, 5
CHARTS_MIN, CHARTS_MAX = 1, 3
BLOCK_TYPES = {"paragraph", "subhead", "quote", "chart", "key_figures"}
CHART_FORMS = {"bars", "columns", "paired_bars"}
SOURCE_TYPES = {"oficial", "prensa"}
FIGURE_KINDS = {"oficial", "prensa", "estimacion"}
# The old rigid sections must not come back as subheads.
BANNED_LABELS = ("que paso", "lectura alicanto", "que mirar")
INLINE_QUOTE_MIN_WORDS = 3

SOURCE_ID = r"f\d{1,2}"
EST_ID = r"est:[A-Za-z0-9_-]+"
LINK = re.compile(r"\[([^\]\[^][^\]\[]*)\]\((" + SOURCE_ID + r"|" + EST_ID + r")\)")
NOTE = re.compile(r"\[\^(n\d+)\]")
INLINE_QUOTE = re.compile(r"[“«\"]([^”»\"]+)[”»\"]")
RATIO = re.compile(r"\b(\d{1,2}) de cada (\d{1,2})\b")
ELLIPSIS = re.compile(r"\s*(?:\[…\]|\[\.\.\.\]|\(…\)|\(\.\.\.\))\s*")


def is_v2(weekly: Any) -> bool:
    return isinstance(weekly, dict) and weekly.get("schema_version") == SCHEMA_V2


def is_v2_draft(raw: Any) -> bool:
    """A model draft is v2 when it carries body blocks (the writer does not stamp the schema)."""
    return isinstance(raw, dict) and (raw.get("schema_version") == SCHEMA_V2 or isinstance(raw.get("body"), list))


def v1_retired(weekly: Any) -> bool:
    """A v1 Monday insight anchored on or after the v2 cutover."""
    if not isinstance(weekly, dict) or is_v2(weekly) or weekly.get("anchor_kind") != "monday":
        return False
    try:
        return date.fromisoformat(str(weekly.get("freshness_anchor_date"))[:10]) >= V2_REQUIRED_FROM
    except ValueError:
        return False


# ---------------------------------------------------------------------------------------------
# Text helpers


def plain(text: Any) -> str:
    """Displayed text without markup: links keep their words, note markers disappear."""
    return NOTE.sub("", LINK.sub(lambda m: m.group(1), str(text or "")))


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"\s+", " ", s).strip()


def literal_key(text: Any) -> str:
    """Normalisation for literal matching: case, whitespace and typographic quotes only."""
    s = str(text or "").replace(" ", " ")
    s = re.sub(r"[“”«»\"]", "", s).replace("’", "'")
    return re.sub(r"\s+", " ", s).strip().casefold()


def quote_segments(text: Any) -> list[str]:
    """A quote may skip words with […]; each segment must be literal on its own."""
    parts = [p.strip(" .,;:") for p in ELLIPSIS.split(str(text or ""))]
    return [p for p in parts if p]


def words(text: Any) -> int:
    return len(plain(text).split())


def _blocks(weekly: dict) -> list[dict]:
    return [b for b in weekly.get("body") or [] if isinstance(b, dict)]


def paragraphs(weekly: dict) -> list[str]:
    return [str(b.get("text") or "") for b in _blocks(weekly) if b.get("type") == "paragraph"]


def closing_text(weekly: dict) -> str:
    c = weekly.get("closing")
    return str((c or {}).get("text") or "") if isinstance(c, dict) else str(c or "")


def essay_words(weekly: dict) -> int:
    """Paragraphs + quotes + closing (headline, dek, subheads, boxes and the method are not counted)."""
    texts = paragraphs(weekly) + [str(b.get("text") or "") for b in _blocks(weekly) if b.get("type") == "quote"]
    return sum(words(t) for t in texts + [closing_text(weekly)])


def key_figure_items(weekly: dict) -> list[dict]:
    kf = weekly.get("key_figures")
    items = kf.get("items") if isinstance(kf, dict) else kf if isinstance(kf, list) else []
    return [x for x in items or [] if isinstance(x, dict)]


def _method(weekly: dict) -> dict:
    return weekly.get("method") if isinstance(weekly.get("method"), dict) else {}


def displayed_texts(weekly: dict) -> list[tuple[str, str]]:
    """(where, plain text) for every text a reader sees in v2, markup removed."""
    t: list[tuple[str, Any]] = [("headline", weekly.get("headline")), ("dek", weekly.get("dek")),
                                ("kicker", weekly.get("kicker")), ("title", weekly.get("title")),
                                ("summary", weekly.get("summary")), ("insight_teaser", weekly.get("insight_teaser"))]
    for i, b in enumerate(_blocks(weekly)):
        kind = b.get("type")
        if kind in ("paragraph", "subhead"):
            t.append((f"body[{i}].{kind}", b.get("text")))
        elif kind == "quote":
            t += [(f"body[{i}].quote", b.get("text")), (f"body[{i}].quote.attribution", b.get("attribution")),
                  (f"body[{i}].quote.context", b.get("context"))]
    t.append(("closing", closing_text(weekly)))
    kf = weekly.get("key_figures") if isinstance(weekly.get("key_figures"), dict) else {}
    t.append(("key_figures.heading", kf.get("heading")))
    for i, x in enumerate(key_figure_items(weekly)):
        t += [(f"key_figures[{i}].{k}", x.get(k)) for k in ("label", "value", "text", "source_label")]
    for chart in weekly.get("charts") or []:
        if not isinstance(chart, dict):
            continue
        where = f"chart.{chart.get('id')}"
        t += [(f"{where}.{k}", chart.get(k)) for k in ("headline", "subtitle", "source", "footnote", "kind_label")]
        t += [(f"{where}.series", s.get("label")) for s in chart.get("series") or [] if isinstance(s, dict)]
        for row in chart.get("rows") or []:
            if isinstance(row, dict):
                t += [(f"{where}.row_label", row.get("label")), (f"{where}.partial_label", row.get("partial_label"))]
    m = _method(weekly)
    t.append(("method.estimates_note", m.get("estimates_note")))
    t += [("method.discarded", x) for x in m.get("discarded") or []]
    t += [("method.limits", x) for x in m.get("limits") or []]
    t += [("notes", n.get("text")) for n in weekly.get("notes") or [] if isinstance(n, dict)]
    for s in weekly.get("sources") or []:
        if isinstance(s, dict):
            t += [(f"sources.{k}", s.get(k)) for k in ("label", "role", "short_label", "short_role")]
    for est in weekly.get("estimates") or []:
        if isinstance(est, dict):
            t.append(("estimate.label", est.get("label")))
    return [(w, plain(x)) for w, x in t if x]


def rule_texts(weekly: dict) -> list[tuple[str, str]]:
    """Texts where a normative ID must be explained in the same sentence (quotes are literal: excluded)."""
    t = [("headline", weekly.get("headline")), ("dek", weekly.get("dek"))]
    t += [(f"body[{i}]", b.get("text")) for i, b in enumerate(_blocks(weekly)) if b.get("type") in ("paragraph", "subhead")]
    t.append(("closing", closing_text(weekly)))
    t += [(f"key_figures[{i}]", f"{x.get('value') or ''} {x.get('text') or ''}") for i, x in enumerate(key_figure_items(weekly))]
    m = _method(weekly)
    t += [("method", x) for x in [m.get("estimates_note"), *(m.get("discarded") or []), *(m.get("limits") or [])]]
    return [(w, plain(x)) for w, x in t if x]


def all_markup_texts(weekly: dict) -> list[tuple[str, str]]:
    """Raw texts that may carry inline markup (links, estimates, notes)."""
    t = [(f"body[{i}]", str(b.get("text") or "")) for i, b in enumerate(_blocks(weekly)) if b.get("type") == "paragraph"]
    t.append(("closing", closing_text(weekly)))
    t += [(f"chart.{c.get('id')}.source", str(c.get("source") or "")) for c in weekly.get("charts") or [] if isinstance(c, dict)]
    t += [(f"key_figures[{i}].text", str(x.get("text") or "")) for i, x in enumerate(key_figure_items(weekly))]
    return t


def trace_corpus(weekly: dict) -> list[float]:
    """Declared origins in v2: evidence_figures (copied from the evidence), estimate values and formula operands."""
    from .weekly_freshness import SAFE_FORMULA, numbers_in
    corpus: list[float] = []
    for fig in weekly.get("evidence_figures") or []:
        corpus += [n for _, n, _ in numbers_in(str(fig))]
    for est in weekly.get("estimates") or []:
        if not isinstance(est, dict):
            continue
        if isinstance(est.get("value"), (int, float)):
            corpus.append(float(est["value"]))
        formula = str(est.get("formula") or "")
        if SAFE_FORMULA.match(formula):
            corpus += [float(x) for x in re.findall(r"\d+(?:\.\d+)?", formula)]
    return corpus


def _estimate_values(weekly: dict) -> list[float]:
    return [float(e["value"]) for e in weekly.get("estimates") or []
            if isinstance(e, dict) and isinstance(e.get("value"), (int, float))]


def strip_ratios(text: str, estimates: list[float]) -> str:
    """'8 de cada 10' is a rounded share: it traces when an estimate rounds to that fraction
    (|8/10·100 − estimate| ≤ half a step of 1/10). Traced ratios are removed before the number scan."""
    def repl(m):
        x, n = int(m.group(1)), int(m.group(2))
        if 0 < x <= n <= 10 and any(abs(x / n * 100 - v) <= 50 / n + 1e-9 for v in estimates):
            return " "
        return m.group(0)
    return RATIO.sub(repl, text)


def untraced_numbers(weekly: dict, corpus: list[float] | None = None) -> list[str]:
    from .weekly_freshness import chart_values, number_traces, numbers_in
    corpus = trace_corpus(weekly) if corpus is None else corpus
    ests = _estimate_values(weekly)
    missing = [f"{where}:{tok}" for where, text in displayed_texts(weekly)
               for tok, value, dec in numbers_in(strip_ratios(text, ests)) if not number_traces(value, dec, corpus)]
    for est in weekly.get("estimates") or []:
        if isinstance(est, dict) and est.get("display"):
            own = [float(est["value"])] if isinstance(est.get("value"), (int, float)) else []
            missing += [f"estimate.{est.get('id')}.display:{tok}"
                        for tok, value, dec in numbers_in(strip_ratios(str(est["display"]), ests))
                        if not number_traces(value, dec, own + corpus)]
    for chart in weekly.get("charts") or []:
        if isinstance(chart, dict):
            missing += [f"chart.{chart.get('id')}:{label}={value}" for label, value in chart_values(chart)
                        if not number_traces(value, 1, corpus) and not number_traces(value, 0, corpus)]
    return missing


def unexplained_normative_ids(weekly: dict) -> list[str]:
    from .weekly_freshness import NORMATIVE_ID, _explains_rule, _sentences
    errors = []
    for where, text in rule_texts(weekly):
        for sentence in _sentences(text):
            ids = NORMATIVE_ID.findall(sentence)
            if ids and not _explains_rule(sentence):
                errors += [f"{where}:{x.strip()}" for x in ids]
    return errors


# ---------------------------------------------------------------------------------------------
# Presentation rules (weekly only; also enforced when serving, in ``reviewed_weekly``)


def _excerpts_by_source(weekly: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for x in weekly.get("evidence_excerpts") or []:
        if isinstance(x, dict) and x.get("text"):
            out.setdefault(str(x.get("source_ref")), []).append(literal_key(x["text"]))
    return out


def _literal_in(text: str, pool: list[str]) -> bool:
    segs = quote_segments(text)
    return bool(segs) and all(any(literal_key(s) in p for p in pool) for s in segs)


def presentation_errors(weekly: dict) -> list[str]:
    from .weekly_freshness import SAFE_FORMULA
    errors: list[str] = []
    for key in ("headline", "dek", "body", "closing", "sources", "method", "evidence_figures"):
        if not weekly.get(key):
            errors.append(f"missing:{key}")
    for legacy in ("essay", "watch"):
        if weekly.get(legacy):
            errors.append(f"v1_field_in_v2:{legacy}")
    if len(str(weekly.get("headline") or "")) > HEADLINE_MAX_CHARS:
        errors.append(f"headline_over_{HEADLINE_MAX_CHARS}_chars")
    if words(weekly.get("dek")) > DEK_MAX_WORDS:
        errors.append(f"dek_over_{DEK_MAX_WORDS}_words")
    if len(str(weekly.get("kicker") or "")) > KICKER_MAX_CHARS:
        errors.append(f"kicker_over_{KICKER_MAX_CHARS}_chars")

    blocks = weekly.get("body") if isinstance(weekly.get("body"), list) else []
    if any(not isinstance(b, dict) or b.get("type") not in BLOCK_TYPES for b in blocks):
        errors.append("body_block_invalid")
    blocks = _blocks(weekly)
    if blocks and blocks[0].get("type") != "paragraph":
        errors.append("lead_must_be_a_paragraph")
    for i, b in enumerate(blocks):
        if b.get("type") in ("paragraph", "subhead", "quote") and not str(b.get("text") or "").strip():
            errors.append(f"empty_block:body[{i}]")
        if b.get("type") == "subhead" and fold(plain(b.get("text"))).startswith(BANNED_LABELS):
            errors.append(f"section_label_not_allowed:body[{i}]")
    if not closing_text(weekly).strip():
        errors.append("closing_required")
    n = essay_words(weekly)
    if not ESSAY_WORDS_MIN <= n <= ESSAY_WORDS_MAX:
        errors.append(f"essay_words_out_of_range:{n}")

    # Sources: unique ids, a type badge, an https link; every reference resolves; every source is cited.
    sources = [s for s in weekly.get("sources") or [] if isinstance(s, dict)]
    ids = [s.get("id") for s in sources]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and re.fullmatch(SOURCE_ID, i) for i in ids):
        errors.append("source_ids_invalid_or_duplicated")
    for s in sources:
        if s.get("type") not in SOURCE_TYPES:
            errors.append(f"source_type_invalid:{s.get('id')}")
        if not str(s.get("url") or "").startswith("https://") or not s.get("label"):
            errors.append(f"source_without_link_or_label:{s.get('id')}")
    known = set(ids)
    estimates = {e.get("id"): e for e in weekly.get("estimates") or [] if isinstance(e, dict)}
    cited: set[str] = set()
    marked: set[str] = set()
    note_refs: list[str] = []
    for where, text in all_markup_texts(weekly):
        for _, ref in LINK.findall(text):
            if ref.startswith("est:"):
                marked.add(ref[4:])
                if ref[4:] not in estimates:
                    errors.append(f"estimate_ref_unresolved:{where}:{ref[4:]}")
            else:
                cited.add(ref)
                if ref not in known:
                    errors.append(f"source_ref_unresolved:{where}:{ref}")
        note_refs += NOTE.findall(text)
        if re.search(r"\]\((?!" + SOURCE_ID + r"\)|" + EST_ID + r"\))[^)]*\)", text):
            errors.append(f"inline_markup_invalid:{where}")

    # Quotes: blockquotes with an attributed, resolvable source, literal in the evidence excerpts.
    excerpts = _excerpts_by_source(weekly)
    for x in weekly.get("evidence_excerpts") or []:
        if not isinstance(x, dict) or x.get("source_ref") not in known or not str(x.get("text") or "").strip():
            errors.append("evidence_excerpt_invalid")
    for i, b in enumerate(blocks):
        if b.get("type") != "quote":
            continue
        ref = b.get("source_ref")
        cited.add(str(ref))
        if ref not in known:
            errors.append(f"quote_source_unresolved:body[{i}]")
        if not str(b.get("attribution") or "").strip():
            errors.append(f"quote_without_attribution:body[{i}]")
        if not _literal_in(str(b.get("text") or ""), excerpts.get(str(ref), [])):
            errors.append(f"quote_not_literal_in_evidence:body[{i}]")
    all_excerpts = [p for pool in excerpts.values() for p in pool]
    for where, text in [(w, t) for w, t in all_markup_texts(weekly) if not w.startswith("chart.")]:
        for q in INLINE_QUOTE.findall(plain(text)):
            if len(q.split()) >= INLINE_QUOTE_MIN_WORDS and not _literal_in(q, all_excerpts):
                errors.append(f"inline_quote_not_literal_in_evidence:{where}")

    # Charts: 1–3, each anchored right after the paragraph that explains it.
    charts = [c for c in weekly.get("charts") or [] if isinstance(c, dict)]
    if not CHARTS_MIN <= len(weekly.get("charts") or []) <= CHARTS_MAX:
        errors.append("charts_count_out_of_range")
    chart_ids = [c.get("id") for c in charts]
    placed = [b.get("chart_ref") for b in blocks if b.get("type") == "chart"]
    for cid in chart_ids:
        if placed.count(cid) != 1:
            errors.append(f"chart_not_placed_once:{cid}")
    for i, b in enumerate(blocks):
        if b.get("type") == "chart":
            if b.get("chart_ref") not in chart_ids:
                errors.append(f"chart_ref_unresolved:body[{i}]")
            if i == 0 or blocks[i - 1].get("type") != "paragraph":
                errors.append(f"chart_not_after_paragraph:{b.get('chart_ref')}")
    for c in charts:
        if c.get("form") not in CHART_FORMS:
            errors.append(f"chart_form_invalid:{c.get('id')}")
        elif c.get("form") == "paired_bars" and len(c.get("series") or []) < 2:
            errors.append(f"paired_bars_without_two_series:{c.get('id')}")
        if c.get("kind") not in FIGURE_KINDS:
            errors.append(f"chart_kind_invalid:{c.get('id')}")
        if c.get("kind") == "estimacion":
            if c.get("estimate_ref") not in estimates:
                errors.append(f"estimate_chart_without_estimate:{c.get('id')}")
            else:
                marked.add(c["estimate_ref"])
        if not LINK.search(str(c.get("source") or "")):
            errors.append(f"chart_source_without_link:{c.get('id')}")
        for row in c.get("rows") or []:
            if isinstance(row, dict) and row.get("style") == "partial" and not row.get("partial_label"):
                errors.append("partial_row_without_label")

    # Key figures (optional): 3–5 cards, each with its universe, kind and source; one wide card at most.
    items = key_figure_items(weekly)
    boxes = sum(1 for b in blocks if b.get("type") == "key_figures")
    if weekly.get("key_figures"):
        if not KEY_FIGURES_MIN <= len(items) <= KEY_FIGURES_MAX:
            errors.append(f"key_figures_count_out_of_range:{len(items)}")
        if boxes != 1:
            errors.append("key_figures_box_not_placed_once")
        if sum(1 for x in items if x.get("wide")) > 1:
            errors.append("key_figures_more_than_one_wide")
        for i, x in enumerate(items):
            if not str(x.get("value") or "").strip() or not str(x.get("text") or "").strip():
                errors.append(f"key_figure_without_value_or_text:{i}")
            universe = str(x.get("universe") or "").strip()
            if len(universe.split()) < 2:
                errors.append(f"key_figure_without_universe:{i}")
            elif literal_key(universe) not in literal_key(f"{x.get('value') or ''} {plain(x.get('text'))}"):
                errors.append(f"key_figure_universe_not_shown:{i}")
            if x.get("kind") not in FIGURE_KINDS:
                errors.append(f"key_figure_kind_invalid:{i}")
            if x.get("source_ref") not in known:
                errors.append(f"key_figure_source_unresolved:{i}")
            else:
                cited.add(x["source_ref"])
            if x.get("kind") == "estimacion":
                if x.get("estimate_ref") not in estimates:
                    errors.append(f"key_figure_estimate_unresolved:{i}")
                else:
                    marked.add(x["estimate_ref"])
    elif boxes:
        errors.append("key_figures_box_without_items")

    for s in sources:
        if s.get("id") not in cited:
            errors.append(f"source_never_cited:{s.get('id')}")

    # Estimates: deterministic formula, value recomputed, marked in the text or used by a chart/card,
    # and explained in the method accordion.
    method = _method(weekly)
    listed = set(method.get("estimates") or [])
    for eid, est in estimates.items():
        formula = str(est.get("formula") or "")
        if not formula or not SAFE_FORMULA.match(formula):
            errors.append(f"estimate_formula_not_deterministic:{eid}")
        else:
            try:
                value = eval(formula, {"__builtins__": {}}, {})  # digits and arithmetic only (SAFE_FORMULA)
                if abs(value - float(est.get("value"))) > 0.05:
                    errors.append(f"estimate_mismatch:{eid}")
            except Exception:
                errors.append(f"estimate_formula_invalid:{eid}")
        if eid not in marked:
            errors.append(f"estimate_not_marked:{eid}")
        if eid not in listed:
            errors.append(f"estimate_missing_from_method:{eid}")
    for eid in listed - set(estimates):
        errors.append(f"method_estimate_unresolved:{eid}")
    for key in ("discarded", "limits"):
        if not isinstance(method.get(key), list):
            errors.append(f"method_{key}_missing")
    if not method.get("limits"):
        errors.append("method_limits_empty")

    # Optional evidence notes.
    notes = [x for x in weekly.get("notes") or [] if isinstance(x, dict)]
    nids = [x.get("id") for x in notes]
    if len(set(nids)) != len(nids) or not all(x.get("text") for x in notes):
        errors.append("notes_invalid_or_duplicated")
    if any(r not in nids for r in note_refs):
        errors.append("footnote_ref_unresolved")
    if any(x not in note_refs for x in nids):
        errors.append("note_never_referenced")

    errors += [f"number_untraced:{x}" for x in untraced_numbers(weekly)]
    errors += [f"normative_id_unexplained:{x}" for x in unexplained_normative_ids(weekly)]
    return errors


def warnings(weekly: dict) -> list[str]:
    n = essay_words(weekly)
    lo, hi = ESSAY_WORDS_TARGET
    return [f"essay_words_outside_target:{n}"] if not lo <= n <= hi else []


# ---------------------------------------------------------------------------------------------
# Evidence-level checks (``verify_candidate``)


def _strings(node: Any, out: list[str]) -> None:
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k not in ("numbers", "allowed_urls"):
                _strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _strings(v, out)


def evidence_text_by_url(evidence: dict) -> dict[str, list[str]]:
    """Literal texts of the evidence package grouped by the URL of the item that holds them."""
    out: dict[str, list[str]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            url = node.get("url") or node.get("source_url")
            if isinstance(url, str) and url.startswith("https://"):
                texts: list[str] = []
                _strings({k: v for k, v in node.items() if k not in ("url", "source_url")}, texts)
                out.setdefault(url, []).extend(literal_key(t) for t in texts)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(evidence)
    return out


def evidence_errors(weekly: dict, evidence: dict) -> list[str]:
    """Excerpts are literal in the evidence item of the same source; figures trace to evidence numbers."""
    from .weekly_freshness import number_traces, numbers_in
    errors = []
    by_url = evidence_text_by_url(evidence)
    urls = {s.get("id"): s.get("url") for s in weekly.get("sources") or [] if isinstance(s, dict)}
    for i, x in enumerate(weekly.get("evidence_excerpts") or []):
        if not isinstance(x, dict):
            continue
        pool = by_url.get(str(urls.get(x.get("source_ref"))), [])
        if not _literal_in(str(x.get("text") or ""), pool):
            errors.append(f"excerpt_not_in_evidence:{i}:{x.get('source_ref')}")
    pool = [float(n) for n in evidence.get("numbers") or []]
    for fig in weekly.get("evidence_figures") or []:
        for tok, value, dec in numbers_in(str(fig)):
            if not number_traces(value, dec, pool):
                errors.append(f"evidence_figure_not_in_evidence:{tok}")
    return errors


# ---------------------------------------------------------------------------------------------
# Writer prompt (format and rules; ``weekly_insight_a.draft_prompt`` adds the evidence)

FORMAT_V2 = """Formato A v2, ensayo tipo noticia (aprobado por Dirección el 10-nov-2026; JSON puro, sin texto fuera del JSON):
{"kicker": "tema en ≤60 caracteres (p. ej. «Personas mayores y cuidados»)",
 "headline": "≤140 caracteres; toma posición, sin causalidad no demostrada",
 "dek": "≤40 palabras; hechos",
 "body": [  // entrada → contexto → desarrollo; sin rótulos «Qué pasó», «Lectura Alicanto» ni «Qué mirar»
   {"type":"paragraph","text":"la ENTRADA: el hecho de la semana, quién, qué y cuándo, con la fuente enlazada"},
   {"type":"quote","text":"cita textual, copiada LITERALMENTE de evidence_excerpts (sin comillas)","source_ref":"f1",
    "attribution":"quién la dice","context":"dónde (p. ej. «comunicado del 2 de noviembre»)"},
   {"type":"key_figures"},            // opcional: dónde va el recuadro de cifras
   {"type":"subhead","text":"subtítulo narrativo que afirma algo"},
   {"type":"paragraph","text":"párrafo que explica el gráfico que sigue"},
   {"type":"chart","chart_ref":"id del gráfico"}  // SIEMPRE justo después del párrafo que lo explica
 ],
 "closing": {"text":"CIERRE: remata la tesis e integra en prosa qué mirar (2–3 señales que la confirmarían o desmentirían)"},
 "key_figures": {"items":[{"label":"rótulo corto","value":"cifra grande («250», «1 de cada 3», «1% → 15,3%»)",
     "text":"frase que se entiende sola y CONTIENE el universo","universe":"universo o denominador, literal en value+text (p. ej. «505 de los 1.498 hogares del catastro 2021»)",
     "kind":"oficial|prensa|estimacion","source_ref":"f2","source_label":"nombre corto de la fuente","estimate_ref":"id (solo si kind=estimacion)","wide":false}]},
     // OPCIONAL: inclúyelo solo si aclara la historia; 3 a 5 tarjetas; una idea por tarjeta; nunca mezcles universos; máximo una "wide"
 "charts": [{"id","form":"bars|columns|paired_bars","headline":"titular afirmativo","subtitle":"qué se mide, unidad y período","unit",
             "kind":"oficial|prensa|estimacion","kind_label":"opcional (p. ej. «Prensa con dato oficial»)","estimate_ref":"id si kind=estimacion",
             "series_ref":"id de una serie de EVIDENCIA.series (opcional; sus filas se copian tal cual)",
             "series":[{"key","label","emphasis"}] (solo paired_bars),
             "rows":[{"label","value","strong":bool,"style":"estimate|partial"} | {"label","values":{key:valor}}],
             "source":"Fuente: … con [nombre](fN)"}],   // 1 a 3 gráficos; barras desde cero
 "estimates": [{"id","label","value","unit","display":"cómo aparece en el texto","formula":"solo dígitos y + - * / ( )","inputs":["cifra de la evidencia"]}],
 "method": {"estimates":["id de cada estimación"],"estimates_note":"opcional","discarded":["qué no usamos y por qué"],"limits":["límites de la evidencia"]},
 "sources": [{"id":"f1","type":"oficial|prensa","label":"Medio u organismo · título (fecha)","url":"URL de la EVIDENCIA","role":"qué aporta"}],
 "evidence_figures": ["cifra copiada textualmente de la evidencia, con su fuente y fecha", ...],
 "evidence_excerpts": [{"source_ref":"f1","text":"frase copiada LITERALMENTE de la evidencia de esa fuente"}],
 "insight_teaser": "≤30 palabras para la tarjeta"}
Marcado dentro de paragraph, closing, charts[].source y key_figures[].text:
  [Fiscalía Nacional Económica](f1) → enlace directo al documento + superíndice numerado a la lista de fuentes.
  [uno de cada tres](est:sin_autorizacion) → estimación Alicanto (subrayado punteado; la fórmula va en el método)."""

RULES_V2 = """Reglas (se verifican de forma determinista; si fallas, no se publica):
1. Usa EXCLUSIVAMENTE la EVIDENCIA. Cada número de cualquier campo visible (titular, bajada, cuerpo, cierre, recuadro de
   cifras, gráficos, método, fuentes) debe estar en evidence_figures (copiado de la evidencia) o ser una estimación
   declarada con fórmula. «8 de cada 10» vale solo si una estimación redondea a esa fracción.
2. Ensayo (párrafos + citas + cierre) de 600 a 900 palabras; mínimo 500 y tope duro de 1.000. Estructura de noticia:
   entrada, contexto, desarrollo y cierre. Prohibidos los subtítulos «Qué pasó», «Lectura Alicanto» y «Qué mirar».
3. Cada fuente que nombres en el texto va con enlace [nombre](fN); toda fuente de sources se cita al menos una vez.
   type: "oficial" (organismo público, ley, estudio oficial) o "prensa" (medio de comunicación).
4. Citas: solo en bloques "quote" con atribución, y cada cita (y cada frase entre comillas de 3 o más palabras) debe estar
   LITERALMENTE en evidence_excerpts de esa fuente, que a su vez se copia literal de la evidencia. Puedes omitir palabras
   con […]. Prefiere citas de fuentes oficiales; de la prensa de pago usa solo título y bajada públicos.
5. Toda cifra derivada es una estimación: márcala en el texto con [texto](est:id) o úsala en un gráfico o tarjeta de tipo
   estimacion, y lístala en method.estimates. Un gráfico de estimación lleva kind="estimacion" y estimate_ref.
6. Recuadro de cifras: opcional; 3–5 tarjetas; cada una con universo (literal en su texto), kind y fuente; una idea por tarjeta.
7. Si nombras una Circular, Ley, DS, artículo o Resolución, la MISMA frase explica en lenguaje llano qué exige o permite.
8. El método (method) dice qué descartaste y por qué, y los límites de la evidencia (de qué año es el dato, qué universo
   cubre, qué no está verificado). No inventes causalidad. Español de Chile, formato 12,3% y 5.155.495."""
