"""Statistics fichas by family (Dirección, 28-oct-2026): one live ficha per family.

Framework shared by every family (F1 Cartera first; see ``stats_ficha_f1``):

1. Registry      ``config/stats_fichas_v1.json``: formulas, denominators, thresholds, pitfalls,
                  calendar and headline templates per family.
2. Evidence      a deterministic package: every value carries provenance (URL, SHA-256, sheet/cell
                  locator, period, publication date, fetch date) and revision flags. Derived values
                  record their formula and input ids. Nothing is computed by a model.
3. Triggers      new period, threshold crossed, revision (> 0,5 %), late release, and HOLD on a
                  reconciliation failure, an older period or a missing hash.
4. Templates     headline / dek / facts filled by code from the package.
5. Lectura       the only model-written block (≤ 60 words). ``verify_lectura`` traces every figure to
                  the builder's ``lectura_pool`` / ``derived_ratios`` / ``ranks`` (value, unit, sign, entity,
                  period), rejects sentences that only restate what the ficha shows, causal verbs without a
                  causal note, Isapres outside the package and URLs. No budget or a FAIL → the block is
                  omitted and the ficha still publishes (decision 3).
6. Publication   PASS (deterministic verification + reconciliation) replaces the live ficha and
                  archives the previous one (decisions 1 and 2). FAIL → HOLD file, live untouched.
7. Snapshot      ``apply_to_snapshot`` emits live fichas as feed cards and removes the loose cards
                  and legacy pulses they supersede.
"""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import lectura_verifier as lv
from .weekly_freshness import number_traces, numbers_in

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config/stats_fichas_v1.json"
STORE = Path("data/stats_fichas")
SCHEMA = "stats_ficha_v1"
HEX64 = re.compile(r"[0-9a-f]{64}")
REVISION_REPUBLISH_PCT = 0.5

MONTHS_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
             "octubre", "noviembre", "diciembre")
ORDINAL_WORDS = {2: "segundo", 3: "tercer", 4: "cuarto", 5: "quinto", 6: "sexto", 7: "séptimo", 8: "octavo"}


# ---------------------------------------------------------------------------------------------
# Registry and formatting


def load_registry(path: Path | None = None) -> dict:
    return json.loads(Path(path or REGISTRY_PATH).read_text(encoding="utf-8"))


def family_config(family: str, registry: dict | None = None) -> dict:
    return (registry or load_registry())["families"][family]


def fmt_int(n: float) -> str:
    """Chilean thousands separator and typographic minus: −27.355."""
    v = int(round(n))
    return ("−" if v < 0 else "") + f"{abs(v):,}".replace(",", ".")


def fmt_signed(n: float) -> str:
    v = int(round(n))
    return ("+" if v > 0 else "") + fmt_int(v)


def fmt_dec(x: float, digits: int = 1, signed: bool = False) -> str:
    q = round(float(x), digits)
    if q == 0:
        q = 0.0
    text = f"{abs(q):,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    sign = "−" if q < 0 else ("+" if signed and q > 0 else "")
    return sign + text


def period_parts(period: str) -> tuple[int, int]:
    m = re.fullmatch(r"(20\d{2})-(\d{2})", str(period or ""))
    if not m or not 1 <= int(m[2]) <= 12:
        raise ValueError(f"invalid_period:{period}")
    return int(m[1]), int(m[2])


def month_name(period: str) -> str:
    return MONTHS_ES[period_parts(period)[1] - 1]


def month_label(period: str) -> str:
    y, m = period_parts(period)
    return f"{MONTHS_ES[m - 1]} {y}"


def month_short(period: str) -> str:
    return month_name(period)[:3].capitalize()


def shift_period(period: str, months: int) -> str:
    y, m = period_parts(period)
    k = y * 12 + (m - 1) + months
    return f"{k // 12}-{k % 12 + 1:02d}"


def day_label(day: str | date) -> str:
    d = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
    return f"{d.day} {MONTHS_ES[d.month - 1][:3]}"


def ordinal(n: int) -> str:
    return ORDINAL_WORDS.get(n, f"{n}.º")


# ---------------------------------------------------------------------------------------------
# Evidence package


def source_ref(*, url: str, sha256: str, published_at: str | None, fetched_at: str | None, label: str,
               role: str, locator: str) -> dict:
    return {"url": url, "sha256": sha256, "published_at": published_at, "fetched_at": fetched_at,
            "label": label, "role": role, "locator": locator}


def value(vid: str, val: float, *, unit: str, period: str, source: str | None, locator: str | None = None,
          formula: str | None = None, inputs: list[str] | None = None, kind: str = "captured") -> dict:
    """One evidence entry. ``kind`` is 'captured' (read from a file) or 'derived' (formula + inputs)."""
    return {"id": vid, "value": val, "unit": unit, "period": period, "source": source, "locator": locator,
            "formula": formula, "inputs": inputs or [], "kind": kind, "revised": None}


SCOPES = ("system", "open", "closed", "isapres", "public", "private")  # F4: 'isapres' = the Isapre segment; F6: sectors
PERIOD_KINDS = ("month", "ytd", "interval", "stock_at", "quarter", "quarter_yoy")
SCOPE_RX = re.compile(r"insurer:(?:\d+|fonasa)")


def pool_entry(values: dict, vid: str, *, entity: int | None = None, metric: str | None = None,
               signed: bool = True, periods: list[str] | None = None, requires_period: bool = False,
               scope: str | None = None, period_kind: str = "stock_at", trivial: bool = False,
               base: str | None = None) -> dict:
    """One figure the Lectura may cite: a package value with its unit, sign rule, scope and period.

    ``scope`` is 'system', 'open', 'closed' or 'insurer:<code>' (the default when ``entity`` is set): who the figure
    may be credited to. ``period_kind`` is 'month' (a change within one month), 'ytd' (since the base month),
    'interval' (between two cuts) or 'stock_at' (a stock at the end of a month). ``base`` is the denominator of a
    share or rate ('abiertas', 'sistema', 'variacion_sistema', 'stock_base', …; ``lectura_verifier.BASES``).
    """
    v = values[vid]
    per = periods or [p for p in re.split(r"→", str(v.get("period") or "")) if p]
    scope = scope or (f"insurer:{entity}" if entity is not None else "system")
    if scope not in SCOPES and not SCOPE_RX.fullmatch(scope):
        raise ValueError(f"invalid_scope:{scope}")
    if period_kind not in PERIOD_KINDS:
        raise ValueError(f"invalid_period_kind:{period_kind}")
    if base is not None and base not in lv.BASES:
        raise ValueError(f"invalid_base:{base}")
    if base is None and v["unit"] in ("%", "pp"):
        raise ValueError(f"share_or_rate_without_base:{vid}")
    return {"id": vid, "value": v["value"], "unit": v["unit"], "metric": metric, "entity": entity, "signed": signed,
            "periods": per, "requires_period": requires_period, "scope": scope, "period_kind": period_kind,
            "trivial": trivial, "base": base}


def number_pool(package: dict) -> list[float]:
    """Every number a ficha or a Lectura may show: package values, derived values and rule constants."""
    pool: set[float] = set()
    for v in (package.get("values") or {}).values():
        x = v.get("value")
        if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x):
            pool.add(abs(float(x)))
    for x in package.get("constants") or []:
        pool.add(abs(float(x)))
    return sorted(pool)


def text_numbers_trace(text: str, pool: list[float]) -> list[str]:
    """Tokens in ``text`` that do not equal a pool value rounded to the shown precision."""
    return [tok for tok, val, dec in numbers_in(text) if not number_traces(val, dec, pool)]


def release_key(period: str, sha256: str) -> str:
    return f"{period}:{sha256[:16]}"


def detect_revisions(current: dict, previous: dict | None) -> list[dict]:
    """Compare captured values for periods present in both releases (same id)."""
    out = []
    for vid, prev in ((previous or {}).get("values") or {}).items():
        cur = (current.get("values") or {}).get(vid)
        if not cur or prev.get("kind") != "captured" or cur.get("kind") != "captured":
            continue
        a, b = prev.get("value"), cur.get("value")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or a == b:
            continue
        pct = (b - a) / abs(a) * 100 if a else math.inf
        rev = {"id": vid, "period": cur.get("period"), "from": a, "to": b, "pct": round(pct, 4),
               "material": abs(pct) > REVISION_REPUBLISH_PCT, "previous_source": prev.get("source")}
        cur["revised"] = {"from": a, "pct": rev["pct"]}
        current["values"][f"{vid}.previous"] = value(f"{vid}.previous", a, unit=cur.get("unit"), period=cur.get("period"),
                                                     source=prev.get("source"), locator=prev.get("locator"), kind="previous_release")
        out.append(rev)
    return out


# ---------------------------------------------------------------------------------------------
# Triggers (deterministic)


def evaluate_triggers(package: dict, previous_live: dict | None, *, today: date, calendar: dict) -> dict:
    """Return the publication decision for one family run.

    decision: 'HOLD' (never publishes), 'PUBLISH' (replace live) or 'NO_CHANGE' (keep live).
    """
    holds: list[str] = []
    rec = package.get("reconciliation") or {}
    if rec.get("ok") is not True:
        holds.append("HOLD_RECONCILIATION:" + ",".join(rec.get("failures") or ["unknown"]))
    primary = package.get("primary_source") or {}
    if not HEX64.fullmatch(str(primary.get("sha256") or "")):
        holds.append("HOLD_MISSING_HASH")
    prev_period = (previous_live or {}).get("period")
    try:
        if prev_period and period_parts(package["period"]) < period_parts(prev_period):
            holds.append("HOLD_OLDER_PERIOD")
    except (KeyError, ValueError):
        holds.append("HOLD_INVALID_PERIOD")
    triggers: list[str] = []
    material_revisions = [r for r in package.get("revisions") or [] if r.get("material")]
    if not previous_live or previous_live.get("release_key") != package.get("release_key"):
        if not previous_live or prev_period != package.get("period"):
            triggers.append("new_period")
        elif material_revisions:
            triggers.append("revision")
        else:
            triggers.append("new_release_same_period")
    elif material_revisions:
        triggers.append("revision")
    crossed = [f for f in package.get("findings") or [] if f.get("crossed")]
    if crossed:
        triggers.append("threshold_crossed")
    late = late_release(package.get("published_at"), today=today, calendar=calendar)
    if late:
        triggers.append("late_release")
    publishing = {"new_period", "revision", "new_release_same_period"} & set(triggers)
    if late and previous_live and not (previous_live.get("late_release") or {}).get("days_late"):
        publishing = publishing | {"late_release"}
    decision = "HOLD" if holds else ("PUBLISH" if publishing else "NO_CHANGE")
    return {"decision": decision, "holds": holds, "triggers": triggers, "featured": bool(crossed),
            "late_release": late, "material_revisions": material_revisions}


def late_release(published_at: str | None, *, today: date, calendar: dict) -> dict | None:
    try:
        last = date.fromisoformat(str(published_at)[:10])
    except ValueError:
        return None
    expected = last + timedelta(days=int(calendar.get("expected_release_interval_days") or 31))
    days = (today - expected).days
    if days > int(calendar.get("late_tolerance_days") or 21):
        return {"expected_on": expected.isoformat(), "days_late": days}
    return None


# ---------------------------------------------------------------------------------------------
# Lectura Alicanto: verifier and budgeted generation


def _isapre_catalog(root: Path = ROOT) -> list[dict]:
    try:
        return json.loads((root / "data/entities/isapres.json").read_text(encoding="utf-8"))["entities"]
    except (OSError, ValueError, KeyError):
        return []


def _fold(text: str) -> str:
    return str(text or "").casefold().translate(str.maketrans("áéíóúüñ", "aeiouun"))


def _word_rx(pattern: str) -> re.Pattern:
    """A registry pattern (regex over folded text) that must match whole words."""
    return re.compile(r"(?<![a-z0-9])(?:" + pattern + r")(?![a-z0-9])")


def _name_rx(name: str) -> re.Pattern:
    """Insurer name, folded; spaces and hyphens optional ('Vida Tres' = 'VidaTres' = 'vida-tres')."""
    parts = [re.escape(x) for x in re.split(r"[\s-]+", _fold(name)) if x]
    return re.compile(r"(?<![a-z0-9])" + r"[\s-]*".join(parts) + r"(?![a-z0-9])")


def insurer_catalog(registry: dict | None = None, catalog: list[dict] | None = None) -> list[dict]:
    """Every insurer the Lectura could name: the registry list (Fonasa included) plus entity aliases."""
    reg = (registry or load_registry())["lectura"].get("insurers") or []
    out = [{"key": e["key"], "code": e.get("code"), "names": list(e.get("names") or [])} for e in reg]
    by_code = {e["code"]: e for e in out if e["code"] is not None}
    for e in (catalog if catalog is not None else _isapre_catalog()):
        code = int(e.get("official_code"))
        names = [n for n in {e.get("commercial_name"), *(e.get("aliases") or [])} if n]
        if code in by_code:
            by_code[code]["names"] += names
        else:
            out.append({"key": f"code_{code}", "code": code, "names": names})
    for e in out:  # legal suffixes and the 'Isapre' prefix are not part of the matchable name
        e["names"] = sorted({re.sub(r"(?i)^isapre\s+|\s+(s\.a\.|ltda\.|spa)$", "", n).strip() for n in e["names"]} - {""})
    return out


def insurers_mentioned(text: str, catalog: list[dict]) -> set[str]:
    """Keys of the insurers named in ``text``: names, aliases and misspellings (``lectura_verifier.insurer_spans``)."""
    import unicodedata
    return {k for _, _, k in lv.insurer_spans(unicodedata.normalize("NFKC", str(text or "")), catalog, _name_rx)}


def isapres_mentioned(text: str, catalog: list[dict]) -> set[int]:
    """Official codes of the Isapres named in ``text`` (entities catalog format)."""
    cat = insurer_catalog({"lectura": {"insurers": []}}, catalog)
    keys = insurers_mentioned(text, cat)
    return {e["code"] for e in cat if e["key"] in keys and e["code"] is not None}


def lectura_parser(package: dict, cat: list[dict]):
    """Sentence parser bound to the package: insurer masking/catalog, package years and months."""
    periods = list(package.get("periods") or [])
    for e in [*(package.get("lectura_pool") or []), *(package.get("derived_ratios") or []), *(package.get("ranks") or [])]:
        periods += lv.entry_periods(e)
    years = {int(p[:4]) for p in periods if re.match(r"\d{4}", str(p))}
    months = {(int(p[:4]), int(p[5:7])) for p in periods if re.match(r"\d{4}-\d{2}", str(p))}
    by_key = {e["key"]: e["code"] for e in cat}
    # A family may declare its own subject phrases (F4: 'las Isapres' is the Isapre segment, not the system).
    markers = [tuple(m) for m in package.get("group_markers") or []] or None

    def parse(sentence: str) -> dict:
        return lv.parse_sentence(sentence, catalog=cat, name_rx=_name_rx, key_code=by_key, package_years=years,
                                 package_months=months, group_markers=markers)
    return parse


def shown_blocks(ficha: dict | None) -> list[str]:
    """What the reader already sees above the Lectura: headline, dek, KPIs, tab texts and facts."""
    fi = ficha or {}
    out = [fi.get("headline"), fi.get("dek")]
    for k in fi.get("kpis") or []:
        out += [k.get("value"), *(k.get("lines") or [])]
    for tab in fi.get("tabs") or []:
        out += list(tab.get("text") or []) + topic_texts(tab)
    out += list((fi.get("facts") or {}).get("paragraphs") or [])
    return [str(x) for x in out if x]


# Index → topic layout (Dirección 29-oct, option C→B): every topic carries an index line and a sparkline; a topic dek
# and topic KPI cards only when they add something its charts do not show. ``dek: None`` means "no text"; a builder
# that does not set ``dek`` falls back to the tab text in the renderer.
SPARK_FORMS = {"line": "line", "columns_signed": "columns", "diverging": "diverging", "bars": "bars", "dots": "bars"}
INDEX_LINE_MAX = 64


def topic_texts(tab: dict) -> list[str]:
    """Index line, topic dek and topic KPI cards: everything the topic layout shows besides charts and tab text."""
    out = [tab.get("index_line"), tab.get("dek")]
    for k in tab.get("kpis") or []:
        out += [k.get("value"), *(k.get("lines") or [])]
    return [str(x) for x in out if x]


def topic_fields(tab: dict, index_line: str | None = None, kpis: list[dict] | None = None, *,
                 index_refs: list[str] | None = None, text_refs: list[str] | None = None,
                 headline_refs: list[str] | None = None) -> dict:
    """Generic index fields for a family builder: the sparkline mirrors the topic's first chart (its own evidence rows)
    and the index line is the builder's phrase, else the first clause of the tab text, else the first chart headline.

    ``index_refs`` are the evidence ids the builder's own phrase cites; when the line falls back to the tab text or to
    the hero chart headline, it cites ``text_refs`` or ``headline_refs`` (``verify_ficha`` traces every figure of the
    line to those ids only, unit-aware)."""
    charts = tab.get("charts") or []
    hero = charts[0] if charts else None
    tab["spark"] = ({"chart": hero["id"], "form": SPARK_FORMS.get(hero.get("form"), "bars")}
                    if hero and len(hero.get("rows") or []) >= 2 else None)
    refs = index_refs
    if not index_line:
        first = re.split(r"(?<=[.;:])\s+", str((tab.get("text") or [""])[0]).strip())[0].rstrip(".;:")
        if 0 < len(first) <= INDEX_LINE_MAX:
            index_line, refs = first, text_refs
        else:
            index_line, refs = (hero or {}).get("headline"), headline_refs
    tab["index_line"] = index_line
    tab["index_refs"] = list(refs or [])
    if kpis is not None:
        tab["kpis"] = kpis
    return tab


# Figures in index lines and topic deks cite refs like KPI cards do (independent review, 29-oct): a figure must equal
# one of the values the line declares, with a compatible unit ('77%' only matches a % value; '3' never matches a %).


def ref_entries(package: dict) -> dict[str, tuple[float, str]]:
    """Every id a topic line may cite: package values, derived ratios and counts, and ranks → (value, unit)."""
    out: dict[str, tuple[float, str]] = {}
    for vid, v in (package.get("values") or {}).items():
        x = v.get("value")
        if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x):
            out[vid] = (float(x), str(v.get("unit") or ""))
    for e in [*(package.get("derived_ratios") or []), *(package.get("ranks") or [])]:
        x = e.get("value")
        if isinstance(x, (int, float)) and math.isfinite(x):
            out[e["id"]] = (float(x), str(e.get("unit") or ""))
    return out


def _unit_class(unit: str) -> str:
    return {"%": "%", "share": "%", "pp": "pp"}.get(unit, "n")


def numbers_with_units(text: str) -> list[tuple[str, float, int, str]]:
    """``numbers_in`` plus the unit written right after each figure: '%', 'pp' or 'n' (a plain quantity)."""
    out, pos = [], 0
    for tok, val, dec in numbers_in(text):
        m = re.compile(r"(?<![\d.,])" + re.escape(tok) + r"(?!\d|[.,]\d)").search(text, pos)
        unit = "n"
        if m:
            pos = m.end()
            after = re.match(r"\s?(%|pp\b)", text[pos:])
            unit = after.group(1) if after else "n"
        out.append((tok, val, dec, unit))
    return out


def line_ref_errors(text: str | None, refs: list[str] | None, package: dict, where: str) -> list[str]:
    """A topic line traces only to the refs it declares: value + unit, and every Isapre it names is a cited entity."""
    if not text:
        return []
    entries = ref_entries(package)
    refs = list(refs or [])
    errors = [f"topic_ref_missing:{where}:{r}" for r in refs if r not in entries]
    cited = [entries[r] for r in refs if r in entries]
    for tok, val, dec, unit in numbers_with_units(str(text)):
        cands = [x * 100 if u == "share" else x for x, u in cited if _unit_class(u) == unit]
        if not number_traces(val, dec, cands):
            errors.append(f"topic_number_not_in_refs:{where}:{tok}{'' if unit == 'n' else unit}")
    names = {e.get("code"): e.get("name") for e in package.get("entities") or []
             if isinstance(e.get("code"), int) and e.get("name")}
    ref_codes = {int(seg) for r in refs for seg in r.split(".") if seg.isdigit() and int(seg) in names}
    folded = _fold(text)
    for code, name in names.items():
        if code not in ref_codes and _name_rx(name).search(folded):
            errors.append(f"topic_entity_not_in_refs:{where}:{name}")
    return errors


ORDINAL_RX = "|".join(sorted({_fold(w) for w in ORDINAL_WORDS.values()}, key=len, reverse=True))
STREAK_RX = (re.compile(r"\b(suben|subieron|crecen|crecieron|bajan|bajaron|caen|cayeron)\s+por\s+(" + ORDINAL_RX + r")\s+mes"),
             re.compile(r"\b(" + ORDINAL_RX + r")\s+mes\s+(al alza|a la baja)"))


def _mm_series(package: dict, metric: str) -> list[tuple[str, float]] | None:
    """The monthly changes of ``metric`` captured in the package, ending at the ficha's period (None if absent)."""
    values = package.get("values") or {}
    out = []
    for p in (package.get("periods") or [])[1:]:
        v = values.get(f"sistema.{metric}.mm.{p}")
        if v is None:
            return None
        out.append((p, float(v["value"])))
    return out if out and out[-1][0] == package.get("period") else None


def derived_claim_errors(text: str, package: dict, metric_hint: str | None = None) -> list[str]:
    """'Menor baja del año' and 'suben por segundo mes' are recomputed from the package series, never trusted."""
    errors = []
    for sent in re.split(r"(?<=[.;])\s+|\s+·\s+", _fold(text)):
        metric = metric_hint or ("cotizantes" if "cotizant" in sent else "cargas" if "carga" in sent else "beneficiarios")
        if re.search(r"\bmenor (baja|caida)\b", sent):
            s = _mm_series(package, metric)
            last = s[-1][1] if s else None
            negs = [x for _, x in s or [] if x < 0]
            ok = bool(s) and last < 0 and len(negs) >= 2 and all(abs(last) <= abs(x) for x in negs)
            if ok and re.search(r"\bdel ano\b", sent):
                y = period_parts(package["period"])[0]
                ok = (package.get("periods") or [""])[0] == f"{y}-01"
            if not ok:
                errors.append(f"derived_claim_not_in_series:menor_baja:{metric}")
        for i, rx in enumerate(STREAK_RX):
            for m in rx.finditer(sent):
                verb, word = (m.group(1), m.group(2)) if i == 0 else (m.group(2), m.group(1))
                up = verb.startswith(("sub", "crec", "al alza"))
                n = next(k for k, w in ORDINAL_WORDS.items() if _fold(w) == word)
                s = _mm_series(package, metric)
                streak = 0
                if s and s[-1][1] != 0:
                    sign = s[-1][1] > 0
                    for _, x in reversed(s):
                        if x != 0 and (x > 0) == sign:
                            streak += 1
                        else:
                            break
                if not s or s[-1][1] == 0 or (s[-1][1] > 0) != up or streak != n:
                    errors.append(f"derived_claim_not_in_series:racha:{metric}:{word}")
    return errors


def verify_lectura(text: str, package: dict, *, registry: dict | None = None, catalog: list[dict] | None = None,
                   ficha: dict | None = None) -> dict:
    """Deterministic gate for the model-written Lectura (decision 3; figure rule of Dirección 28-oct 15:25).

    Figures: every figure (digits or number words) must trace to the builder's ``lectura_pool`` (digits) or
    ``derived_ratios``/``ranks`` (words) with matching unit, sign, entity and period (``lectura_verifier``).
    Non-redundancy: each sentence adds a figure not shown in the headline/dek/KPIs/tabs/facts, or an implication
    for a named audience in words that do not restate a displayed sentence.
    Insurers: only names in the package AND in the ficha's facts (Fonasa or an unlisted Isapre always fail).
    """
    registry = registry or load_registry()
    cfg = registry["lectura"]
    errors: list[str] = []
    text = str(text or "").strip()
    if not text:
        return {"verdict": "FAIL", "errors": ["empty"]}
    words = len(text.split())
    if words > int(cfg["max_words"]):
        errors.append(f"over_{cfg['max_words']}_words:{words}")
    cat = insurer_catalog(registry, catalog)
    parse = lectura_parser(package, cat)
    pool, ratios, ranks = (list(package.get(k) or []) for k in ("lectura_pool", "derived_ratios", "ranks"))
    displayed = shown_blocks(ficha)
    refs = [r for k in (ficha or {}).get("kpis") or [] for r in k.get("refs") or []]
    shown = lv.shown_ids(displayed, refs, entries=pool + ratios + ranks, parse=parse)
    errors += lv.check(text, pool=pool, ratios=ratios, ranks=ranks, displayed=displayed, shown=shown, parse=parse,
                       implication_terms=audience_terms(registry),
                       jaccard_max=float(cfg.get("jaccard_max", 0.5)))
    if not package.get("causal_note"):
        folded = _fold(text)
        for pat in cfg["causal_patterns"]:
            m = _word_rx(pat).search(folded)
            if m:
                errors.append(f"causal_without_note:{m.group(0)}")
    in_package = {int(c) for c in package.get("entity_codes") or []}
    keys_in_package = set(package.get("entity_keys") or [])  # insurers without an Isapre code (F4: Fonasa)
    facts = " ".join(((ficha or {}).get("facts") or {}).get("paragraphs") or [])
    allowed = ({e["key"] for e in cat if e["code"] in in_package} | keys_in_package) & insurers_mentioned(facts, cat)
    for key in sorted(insurers_mentioned(text, cat)):
        entry = next(e for e in cat if e["key"] == key)
        if entry["code"] not in in_package and key not in keys_in_package:
            errors.append(f"insurer_not_in_package:{key}")
        elif key not in allowed:
            errors.append(f"insurer_not_in_facts:{key}")
    if URL_RX.search(text):
        errors.append("url_in_lectura")
    if not any(a in _fold(text) for a in audience_terms(registry)):
        errors.append("business_lens_no_audience")
    return {"verdict": "PASS" if not errors else "FAIL", "errors": errors, "words": words}


def lectura_material(ficha: dict, package: dict) -> dict:
    """Figures the Lectura may add: the builder's pool minus what the ficha already shows, plus ratios and ranks."""
    cat = insurer_catalog()
    parse = lectura_parser(package, cat)
    pool, ratios, ranks = (list(package.get(k) or []) for k in ("lectura_pool", "derived_ratios", "ranks"))
    refs = [r for k in ficha.get("kpis") or [] for r in k.get("refs") or []]
    shown = lv.shown_ids(shown_blocks(ficha), refs, entries=pool + ratios + ranks, parse=parse)
    names = {e.get("code"): e.get("name") for e in package.get("entities") or []}
    return {"nuevas": [lv.describe(e, names) for e in pool if e["id"] not in shown],
            "razones": [lv.describe(e, names) for e in ratios if e["id"] not in shown],
            "rankings": [lv.describe(e, names) for e in ranks if e["id"] not in shown]}


def lectura_prompt(ficha: dict, package: dict) -> str:
    facts = " ".join(ficha.get("facts", {}).get("paragraphs") or [])
    tabs = [{"tema": t.get("label"), "lectura": t.get("text")} for t in ficha.get("tabs") or []]
    kpis = [{"kpi": k.get("label"), "valor": k.get("value"), "detalle": k.get("lines")} for k in ficha.get("kpis") or []]
    facts_cat = insurer_catalog()
    named = insurers_mentioned(facts, facts_cat)
    names = sorted({e.get("name") for e in package.get("entities") or [] if e.get("name")
                    and any(c["key"] in named and (c["code"] == e.get("code") if e.get("code") is not None else c["key"] == e.get("key"))
                            for c in facts_cat)})
    material = lectura_material(ficha, package)
    return (
        "Escribe la 'Lectura Alicanto' de una ficha estadística de Alicanto Salud (inteligencia de negocios de salud en Chile). "
        "Debe aportar algo más que lo que la ficha ya muestra: una implicancia, una comparación o una cifra derivada. "
        "Nunca repitas el titular, la bajada, los KPI ni 'Qué muestran los datos'.\n"
        "Aplica a la vez cuatro miradas expertas:\n"
        "- Negocio de salud: qué significa para aseguradores, prestadores o inversionistas (ingresos, competencia, riesgo).\n"
        "- Analítica de datos: respeta denominadores y períodos; un stock no se suma; no confundas correlación con causa.\n"
        "- Editorial: directo, sin repetir lo que ya se muestra, sin relleno.\n"
        "- UI/UX: dos o tres frases cortas que se lean en el celular de un vistazo.\n"
        "Reglas que se verifican de forma automática (si fallas, el texto se descarta):\n"
        "1. Breve: dos o tres frases, máximo 60 palabras, en español de Chile, sin títulos ni viñetas.\n"
        "2. Cifras: solo las de 'Material nuevo' (lectura_pool, razones y rankings), redondeadas como se muestran, con su "
        "unidad (%, pp, beneficiarios, cotizantes, veces), su signo, su ámbito, su denominador y su período. Denominador: "
        "una participación o tasa nombra su base junto a la cifra, la del campo 'denominador' (una participación entre "
        "abiertas se escribe 'entre las abiertas', nunca 'del mercado' ni 'del sistema'). Ámbito: una cifra de una "
        "Isapre se atribuye a esa Isapre; una del sistema, a 'el sistema' o 'las Isapres'; una de las abiertas, a 'las "
        "abiertas'; una de las cerradas, a 'las cerradas'. Período: 'mes' se escribe con su mes ('en agosto'); 'desde "
        "enero' exige esas palabras ('desde enero', 'en lo que va del año'); 'entre cortes' no lleva un mes suelto. 'Más "
        "de', 'menos de', 'casi' y 'cerca de' deben ser verdaderos para el valor exacto. Una razón puede escribirse en "
        "palabras (el doble, la mitad, uno de cada cuatro) solo si calza con una razón de la lista; un ranking como "
        "ordinal (la segunda) solo con su ranking y su Isapre. Los conteos marcados 'trivial' (cuántas Isapres hay) no "
        "aportan nada. Ninguna otra cifra, año, trimestre ni palabra numérica.\n"
        "3. Cada frase aporta algo: o cita una cifra de 'Material nuevo', o dice en palabras propias qué implica para un "
        "actor (aseguradoras, Isapres, prestadores, inversionistas, regulador, competencia, precios, cartera). Una frase "
        "que solo repite una cifra ya mostrada se descarta.\n"
        "4. No afirmes causas: no uses 'debido a', 'explica', 'provoca', 'impulsa', 'genera', 'lleva a', 'se traduce', "
        "'responde a', 'porque', 'gracias a', 'producto de', 'se debe', 'conlleva', 'incide', 'influye', 'repercute', "
        "'contribuye', 'gatilla', 'desencadena', 'propicia', 'conduce a', 'da lugar a', 'por lo que', 'así que', "
        "'de modo que', 'de manera que', 'hizo que', 'nace de', 'viene de', 'en razón de', 'por ende', 'en "
        "consecuencia' ni sus conjugaciones.\n"
        + (f"5. Solo puedes nombrar estas Isapres: {', '.join(names)}. No nombres Fonasa ni otras Isapres; no uses las palabras "
           "'esencial' ni 'fundación' salvo como nombre de esas Isapres.\n" if not package.get("prompt_rules") else
           f"5. Solo puedes nombrar estos aseguradores: {', '.join(names) or 'ninguno'}; ninguna Isapre por su nombre. "
           f"{package['prompt_rules']}\n") +
        "6. No inventes hechos, fechas ni fuentes, ni enlaces.\n"
        'Devuelve solo JSON: {"lectura": "..."}\n\n'
        f"Ya mostrado — Titular: {ficha.get('headline')}\nBajada: {ficha.get('dek')}\nQué muestran los datos: {facts}\n"
        f"Temas: {json.dumps(tabs, ensure_ascii=False)}\nKPI: {json.dumps(kpis, ensure_ascii=False)}\n"
        f"Material nuevo (puedes citarlo): {json.dumps(material, ensure_ascii=False)}\n"
    )


def _default_model_call(prompt: str, **kw):
    from . import openai_runtime as rt  # lazy: only live runs need the openai package
    return rt.call_json(prompt, **kw)


def _default_budget(worst_usd: float) -> tuple[bool, str]:
    """Shared AI budget machinery: run/month counters (ai_budget) and the paced monthly budget.

    The weekly cap is enforced again inside ``openai_runtime.call_json``.
    """
    try:
        from .ai_budget import allow_call, has_capacity
        from .ai_pricing import month_spend_usd, paced_budget_usd
        if not has_capacity("fast"):
            return False, "no_capacity"
        if month_spend_usd(ROOT) + worst_usd > paced_budget_usd():
            return False, "paced_budget_would_be_exceeded"
        return (True, "ok") if allow_call("fast") else (False, "budget_deferred")
    except Exception as exc:  # unreadable ledger blocks spend
        return False, f"budget_unreadable:{type(exc).__name__}"


def _record(success: bool) -> None:
    try:
        from .ai_budget import record_result
        record_result("fast", success)
    except Exception:
        pass


def _route_model(route: str) -> str:
    try:
        cfg = json.loads((ROOT / "config/model_routing_v1.json").read_text(encoding="utf-8"))
        return cfg["routes"][route]["model"]
    except (OSError, ValueError, KeyError):
        return "gpt-5.6-luna"


def generate_lectura(ficha: dict, package: dict, *, registry: dict | None = None, enabled: bool = True,
                     model_call: Callable[..., Any] | None = None,
                     budget: Callable[[float], tuple[bool, str]] | None = None,
                     catalog: list[dict] | None = None) -> dict:
    """One cheap call per ficha; any failure omits the block (the ficha still publishes)."""
    registry = registry or load_registry()
    cfg = registry["lectura"]
    if not enabled:
        return {"status": "not_attempted", "text": None, "cost_usd": 0.0}
    prompt = lectura_prompt(ficha, package)
    model = _route_model(cfg.get("route", "luna"))
    try:
        from .ai_pricing import estimate as price_estimate
        worst = price_estimate(model, math.ceil(len(prompt) / 3.2), int(cfg["max_output_tokens"]))
    except Exception:
        worst = float(cfg.get("max_run_usd", 0.05))
    # The run cap covers the writer and the reviewer together: never pay a draft that cannot be reviewed.
    if worst + review_worst_usd(ficha, package, registry) > float(cfg.get("max_run_usd", 0.05)):
        return {"status": "no_budget", "reason": "run_cap_would_be_exceeded", "text": None, "cost_usd": 0.0}
    ok, reason = (budget or _default_budget)(worst)
    if not ok:
        return {"status": "no_budget", "reason": reason, "text": None, "cost_usd": 0.0}
    try:
        result = (model_call or _default_model_call)(prompt, feature="stats_ficha_lectura", preferred_model=model,
                                                     allow_luna_fallback=False, max_output_tokens=int(cfg["max_output_tokens"]))
    except Exception as exc:
        _record(False)
        return {"status": "generation_error", "reason": f"{type(exc).__name__}:{exc}"[:200], "text": None,
                "cost_usd": float(getattr(exc, "estimated_cost_usd", 0) or 0)}
    output = getattr(result, "output", None) or {}
    text = str(output.get("lectura") or "").strip() if isinstance(output, dict) else ""
    cost = float(getattr(result, "estimated_cost_usd", 0) or 0)
    verification = verify_lectura(text, package, registry=registry, catalog=catalog, ficha=ficha)
    _record(verification["verdict"] == "PASS")
    base = {"model": getattr(result, "model", model), "response_id": getattr(result, "response_id", None),
            "cost_usd": round(cost, 6), "verification": verification}
    if verification["verdict"] != "PASS":
        return {**base, "status": "verifier_fail", "text": None, "rejected_text": text}
    return {**base, "status": "pass", "text": text}


# Second-model backstop (as in the weekly insight): after the deterministic verifier passes, one cheaper reviewer
# call per ficha checks the Lectura against the evidence package. FAIL, no budget or an error omit the Lectura.


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def review_prompt(ficha: dict, package: dict, text: str) -> str:
    names = {e.get("code"): e.get("name") for e in package.get("entities") or []}
    evidence = {"cifras": [lv.describe(e, names) for e in package.get("lectura_pool") or []],
                "razones": [lv.describe(e, names) for e in package.get("derived_ratios") or []],
                "rankings": [lv.describe(e, names) for e in package.get("ranks") or []]}
    shown = shown_blocks(ficha)
    return (
        "Eres el revisor independiente de la 'Lectura Alicanto' de una ficha estadística de Alicanto Salud. No la "
        "reescribas: decide si se publica.\n"
        "FAIL si cualquiera de estas cosas ocurre:\n"
        "1. Una cifra, comparación, orden o hecho no está respaldado por la evidencia (valor, unidad, signo, ámbito: "
        "sistema, abiertas, cerradas o una Isapre, y período: mes, desde enero, entre cortes o stock al cierre).\n"
        "1b. Una participación o tasa se presenta con otro denominador que el del campo 'denominador' (p. ej. una "
        "participación entre Isapres abiertas escrita como 'del mercado' o 'del sistema'), o sin nombrarlo.\n"
        "1c. Un superlativo ('la que más crece', 'la mayor baja') no calza con el ranking de la evidencia.\n"
        "2. Atribuye a una Isapre una cifra del sistema, de las abiertas o de las cerradas, o al revés.\n"
        "3. 'Más de', 'menos de', 'casi', 'cerca de' no calzan con el valor verdadero.\n"
        "4. Afirma una causa, una tendencia futura o un hecho que no está en la evidencia.\n"
        "5. Solo repite lo que la ficha ya muestra, o aporta solo conteos triviales (cuántas Isapres hay).\n"
        "6. Nombra una aseguradora, fuente, fecha o enlace que no está en la evidencia.\n"
        "Si todo está respaldado y aporta algo nuevo, PASS.\n"
        'Devuelve solo JSON: {"verdict": "PASS" | "FAIL", "claim": "la afirmación que objetas, textual, o vacío"}\n\n'
        f"Lectura: {text}\n"
        f"Ya mostrado en la ficha: {json.dumps(shown, ensure_ascii=False)}\n"
        f"Evidencia: {json.dumps(evidence, ensure_ascii=False)}\n"
        f"Período de la ficha: {package.get('period')}; base: {package.get('base_period')}\n"
    )


def review_worst_usd(ficha: dict, package: dict, registry: dict | None = None) -> float:
    cfg = (registry or load_registry())["lectura"]
    model = _route_model(cfg.get("review_route", "luna"))
    try:
        from .ai_pricing import estimate as price_estimate
        # the prompt plus a 60-word Lectura (≈ 400 characters)
        return price_estimate(model, math.ceil((len(review_prompt(ficha, package, "x" * 400))) / 3.2),
                              int(cfg.get("review_max_output_tokens", 200)))
    except Exception:
        return float(cfg.get("max_run_usd", 0.05)) / 2


def review_lectura(ficha: dict, package: dict, text: str, *, registry: dict | None = None,
                   model_call: Callable[..., Any] | None = None,
                   budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    """One reviewer call (route ``lectura.review_route``, same budget machinery). PASS/FAIL with the contested claim."""
    registry = registry or load_registry()
    cfg = registry["lectura"]
    model = _route_model(cfg.get("review_route", "luna"))
    prompt = review_prompt(ficha, package, text)
    try:
        from .ai_pricing import estimate as price_estimate
        worst = price_estimate(model, math.ceil(len(prompt) / 3.2), int(cfg.get("review_max_output_tokens", 200)))
    except Exception:
        worst = float(cfg.get("max_run_usd", 0.05)) / 2
    base = {"text_sha256": _sha(text), "route": cfg.get("review_route", "luna"), "cost_usd": 0.0}
    if worst > float(cfg.get("max_run_usd", 0.05)):
        return {**base, "verdict": "NO_BUDGET", "reason": "run_cap_would_be_exceeded"}
    ok, reason = (budget or _default_budget)(worst)
    if not ok:
        return {**base, "verdict": "NO_BUDGET", "reason": reason}
    try:
        result = (model_call or _default_model_call)(prompt, feature="stats_ficha_lectura_review", preferred_model=model,
                                                     allow_luna_fallback=False,
                                                     max_output_tokens=int(cfg.get("review_max_output_tokens", 200)))
    except Exception as exc:
        _record(False)
        return {**base, "verdict": "ERROR", "reason": f"{type(exc).__name__}:{exc}"[:200],
                "cost_usd": float(getattr(exc, "estimated_cost_usd", 0) or 0)}
    output = getattr(result, "output", None)
    output = output if isinstance(output, dict) else {}
    verdict = "PASS" if str(output.get("verdict") or "").strip().upper() == "PASS" else "FAIL"
    _record(True)
    return {**base, "verdict": verdict, "claim": str(output.get("claim") or "")[:300] or None,
            "model": getattr(result, "model", model), "response_id": getattr(result, "response_id", None),
            "cost_usd": round(float(getattr(result, "estimated_cost_usd", 0) or 0), 6)}


def with_review(lect: dict, ficha: dict, package: dict, *, registry: dict | None = None, enabled: bool = True,
                model_call: Callable[..., Any] | None = None,
                budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    """Keep a deterministic-PASS Lectura only if the reviewer passes this exact text (≤ 1 reviewer call per ficha)."""
    if lect.get("status") != "pass":
        return lect
    text = lect.get("text")
    prior = lect.get("review") or {}
    if prior.get("verdict") == "PASS" and prior.get("text_sha256") == _sha(text):
        return lect  # already reviewed (same release, same text): never paid twice
    review = (review_lectura(ficha, package, text, registry=registry, model_call=model_call, budget=budget) if enabled
              else {"text_sha256": _sha(text), "verdict": "NOT_RUN", "reason": "sin modelo en esta corrida", "cost_usd": 0.0})
    cost = round(float(lect.get("cost_usd") or 0) + float(review.get("cost_usd") or 0), 6)
    if review["verdict"] == "PASS":
        return {**lect, "review": review, "cost_usd": cost}
    status = {"FAIL": "review_fail", "NO_BUDGET": "review_no_budget", "ERROR": "review_error"}.get(review["verdict"], "review_not_run")
    return {**lect, "status": status, "text": None, "rejected_text": text, "review": review, "cost_usd": cost}


# ---------------------------------------------------------------------------------------------
# Deterministic verification of the code-written ficha


def all_charts(ficha: dict) -> list[dict]:
    return [c for tab in ficha.get("tabs") or [] for c in tab.get("charts") or []] + list(ficha.get("charts") or [])


def displayed_texts(ficha: dict, include_lectura: bool = True) -> list[str]:
    out = [ficha.get("headline"), ficha.get("dek")]
    for k in ficha.get("kpis") or []:
        out += [k.get("value"), *(k.get("lines") or []), k.get("badge")]
    out += list((ficha.get("facts") or {}).get("paragraphs") or [])
    for w in ficha.get("watch") or []:
        out += [w.get("headline"), w.get("explanation")]
    for tab in ficha.get("tabs") or []:
        out += [tab.get("label"), *(tab.get("text") or []), *topic_texts(tab)]
    for c in all_charts(ficha):
        out += [c.get("headline"), c.get("subtitle"), c.get("legend"), c.get("source")]
        for row in (c.get("table") or {}).get("rows") or []:
            out += [str(cell) for cell in row]
    out += [n.get("text") for n in ficha.get("notes") or []]
    lect = ficha.get("lectura") or {}
    if include_lectura and lect.get("status") == "pass":
        out.append(lect.get("text"))
    return [str(x) for x in out if x]


def audience_terms(registry: dict | None = None) -> list[str]:
    """One list for the audience/implication rule: the registry's ``lectura.implication_terms`` (folded)."""
    terms = (registry or load_registry())["lectura"].get("implication_terms") or []
    return [_fold(t) for t in terms]


# Links and bare domains ('www.x.cl', 'superdesalud.gob.cl', 'example.com/x').
URL_RX = re.compile(r"https?://|\bwww\.|\b[\w-]+(?:\.[\w-]+)*\.(?:cl|com|org|gob|gov|net|io|edu|info|es|ar|pe|co|mx|br|"
                    r"uk|eu|int|app|ai|me|ly|us)\b(?!\.?\d)", re.I)


COUNT_WORDS = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}


COUNT_CLAIM = re.compile(r"\b(\d+|una?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez) isapres? (crecen?|caen?)\b")


def count_phrase(n: int, singular: str, plural: str) -> str:
    """'una crece', 'tres crecen': a count word derived from data, never hard-coded."""
    if n == 1:
        return f"una {singular}"
    word = next((w for w, v in COUNT_WORDS.items() if v == n), str(n))
    return f"{word} {plural}"


def _sentences(text: str) -> list[str]:
    return [_fold(x).strip(" .") for x in re.split(r"(?<=[.;])\s+", str(text or "")) if len(x.split()) >= 6]


def lens_checks(ficha: dict, package: dict) -> dict:
    """Four lenses (Dirección 28-oct 04:59) as deterministic checks; numbers already trace separately.

    - data: KPI refs exist in the package; share/ratio denominators are stated; stocks are labelled.
    - editorial: headline ≤ 140, dek ≤ 40 words, no sentence repeated across blocks.
    - ui: 3–5 KPIs, 2–6 tabs, ≤ 2 charts per tab, ≤ 12 rows per chart, every chart has a data table,
      subtitle and short labels.
    - business: 'Qué mirar' has 1–2 items with the next release; the Lectura (if any) names an audience.
    """
    values = package.get("values") or {}
    out = {"data": [], "editorial": [], "ui": [], "business": []}
    for k in ficha.get("kpis") or []:
        for ref in k.get("refs") or []:
            if ref not in values:
                out["data"].append(f"kpi_ref_missing:{k.get('id')}:{ref}")
    notes = " ".join(n.get("text", "") for n in ficha.get("notes") or []).casefold()
    if "denominador" not in notes:
        out["data"].append("denominator_not_stated")
    if "stock" not in notes:
        out["data"].append("stock_rule_not_stated")
    if len(str(ficha.get("headline") or "")) > 140:
        out["editorial"].append("headline_over_140")
    if len(str(ficha.get("dek") or "").split()) > 40:
        out["editorial"].append("dek_over_40_words")
    facts = (ficha.get("facts") or {})
    blocks = [ficha.get("dek"), *([] if facts.get("rendered_in_tabs") else (facts.get("paragraphs") or [])),
              *[x for tab in ficha.get("tabs") or [] for x in [*(tab.get("text") or []), tab.get("dek")] if x],
              *[n.get("text") for n in ficha.get("notes") or []]]
    lect = ficha.get("lectura") or {}
    if lect.get("status") == "pass":
        blocks.append(lect.get("text"))
    seen: set[str] = set()
    for block in blocks:
        for sent in _sentences(block):
            if sent in seen:
                out["editorial"].append(f"repeated_sentence:{sent[:40]}")
            seen.add(sent)
    if not 3 <= len(ficha.get("kpis") or []) <= 5:
        out["ui"].append("kpis_out_of_range")
    tabs = ficha.get("tabs") or []
    if tabs and not 2 <= len(tabs) <= 6:
        out["ui"].append("tabs_out_of_range")
    for tab in tabs:
        if len(tab.get("charts") or []) > 2:
            out["ui"].append(f"tab_over_2_charts:{tab.get('id')}")
        if len(str(tab.get("label") or "")) > 24:
            out["ui"].append(f"tab_label_long:{tab.get('id')}")
        if not tab.get("charts") and not tab.get("text"):
            out["ui"].append(f"tab_empty:{tab.get('id')}")
        if len(str(tab.get("index_line") or "")) > INDEX_LINE_MAX:
            out["ui"].append(f"index_line_long:{tab.get('id')}")
        if len(str(tab.get("dek") or "").split()) > 30:
            out["editorial"].append(f"topic_dek_over_30_words:{tab.get('id')}")
        if len(tab.get("kpis") or []) > 2:
            out["ui"].append(f"topic_over_2_kpis:{tab.get('id')}")
    if len(all_charts(ficha)) < 2:
        out["ui"].append("charts_under_2")
    for c in all_charts(ficha):
        rows = c.get("rows") or []
        if not rows or len(rows) > 12:
            out["ui"].append(f"chart_rows_out_of_range:{c.get('id')}")
        if not (c.get("table") or {}).get("rows") or not c.get("subtitle"):
            out["ui"].append(f"chart_without_table_or_subtitle:{c.get('id')}")
        if any(len(str(r.get("label") or "")) > 18 for r in rows):
            out["ui"].append(f"chart_label_long:{c.get('id')}")
    # A count word in a chart headline ('tres crecen') must equal a count the builder derived from the data.
    counts = {float(e.get("value")) for e in package.get("derived_ratios") or [] if e.get("unit") == "count"}
    for c in all_charts(ficha):
        for w in re.findall(r"[a-z]+", _fold(c.get("headline"))):
            if w in COUNT_WORDS and float(COUNT_WORDS[w]) not in counts:
                out["data"].append(f"chart_headline_count_not_in_evidence:{c.get('id')}:{w}")
    watch = ficha.get("watch") or []
    if not 1 <= len(watch) <= 2:  # Dirección 28-oct 08:20: compact Qué mirar
        out["business"].append("watch_out_of_range")
    if lect.get("status") == "pass" and not any(a in _fold(lect.get("text")) for a in audience_terms()):
        out["business"].append("lectura_without_audience")
    return out


def verify_ficha(ficha: dict, package: dict) -> dict:
    errors: list[str] = []
    for key in ("headline", "dek", "kpis", "facts", "sources"):
        if not ficha.get(key):
            errors.append(f"missing:{key}")
    pool = number_pool(package)
    # Derived counts ('3 Isapres crecen') are not in this pool: a count traces only through the line that cites it.
    # The Lectura's figures are traced by verify_lectura (pool, unit, sign, entity, period), not by value alone.
    for text in displayed_texts(ficha, include_lectura=False):
        for tok in text_numbers_trace(text, pool):
            errors.append(f"number_not_in_evidence:{tok}")
    # Derived claims ('menor baja del año', 'suben por segundo mes') are recomputed from the series.
    claim_blocks = [(ficha.get("headline"), None), (ficha.get("dek"), None)]
    for k in ficha.get("kpis") or []:
        hint = k.get("id") if k.get("id") in ("beneficiarios", "cotizantes", "cargas") else None
        claim_blocks += [(x, hint) for x in [k.get("value"), *(k.get("lines") or [])]]
    for tab in ficha.get("tabs") or []:
        claim_blocks += [(tab.get("index_line"), None), (tab.get("dek"), None)]
        for k in tab.get("kpis") or []:
            kid = str(k.get("id") or "").removeprefix("tema-")
            hint = kid if kid in ("beneficiarios", "cotizantes", "cargas") else None
            claim_blocks += [(x, hint) for x in [k.get("value"), *(k.get("lines") or [])]]
    for text, hint in claim_blocks:
        if text:
            errors += derived_claim_errors(str(text), package, hint)
    values = package.get("values") or {}
    # Topic KPI cards: every figure on a card traces to the values that card cites (not to any value of the package),
    # and the sparkline draws one of the topic's own charts.
    for tab in ficha.get("tabs") or []:
        for k in tab.get("kpis") or []:
            refs = k.get("refs") or []
            missing = [r for r in refs if r not in values]
            if not refs or missing:
                errors.append(f"topic_kpi_ref_missing:{tab.get('id')}:{k.get('id')}")
                continue
            own = sorted({abs(float(values[r]["value"])) for r in refs})
            for text in [k.get("value"), *(k.get("lines") or [])]:
                for tok in text_numbers_trace(str(text or ""), own):
                    errors.append(f"topic_kpi_number_not_in_refs:{tab.get('id')}:{k.get('id')}:{tok}")
        # Index line and topic dek: each figure traces to the refs the line declares (unit- and entity-aware).
        errors += line_ref_errors(tab.get("index_line"), tab.get("index_refs"), package, f"{tab.get('id')}:index")
        if tab.get("dek"):
            errors += line_ref_errors(tab.get("dek"), tab.get("dek_refs"), package, f"{tab.get('id')}:dek")
        # A count of entities in a topic line ('3 Isapres crecen') must equal the count the builder derived for it.
        derived_counts = {e["id"]: e["value"] for e in package.get("derived_ratios") or [] if e.get("unit") == "count"}
        for text in (tab.get("index_line"), tab.get("dek")):
            for n, verb in COUNT_CLAIM.findall(_fold(text or "")):
                want = derived_counts.get(f"conteo.abiertas_{'crecen' if verb.startswith('crece') else 'caen'}")
                got = int(n) if n.isdigit() else (1 if n in {"una", "un"} else COUNT_WORDS.get(n))
                if want is None or got != want:
                    errors.append(f"count_not_in_evidence:{tab.get('id')}:{n} {verb}")
        spark = tab.get("spark")
        if spark and (spark.get("chart") not in {c.get("id") for c in tab.get("charts") or []}
                      or spark.get("form") not in set(SPARK_FORMS.values())):
            errors.append(f"spark_not_a_topic_chart:{tab.get('id')}")
    for chart in all_charts(ficha):
        for row in chart.get("rows") or []:
            for key, ref_key in (("value", "ref"), ("base", "base_ref")):
                ref = row.get(ref_key)
                if ref_key == "base_ref" and ref is None:
                    continue
                if ref not in values or values[ref]["value"] * row.get("sign", 1) != row.get(key):
                    errors.append(f"chart_row_not_in_evidence:{chart.get('id')}:{row.get('label')}")
    captured = {s.get("url"): s.get("sha256") for s in (package.get("sources") or {}).values()}
    for src in ficha.get("sources") or []:
        if not str(src.get("url") or "").startswith("https://") or not HEX64.fullmatch(str(src.get("sha256") or "")):
            errors.append(f"source_without_hash:{src.get('label')}")
        elif captured.get(src.get("url")) != src.get("sha256"):
            errors.append(f"source_not_captured:{src.get('label')}")  # never invent a source
    reg = package.get("regional") or {}
    captured_links = {reg.get("url"), *(reg.get("documents") or [])} - {None}
    for tab in ficha.get("tabs") or []:
        for link in tab.get("links") or []:
            if link.get("url") not in captured_links:
                errors.append(f"link_not_captured:{tab.get('id')}")
    for text in displayed_texts(ficha):
        if re.search(r"\{[a-z_]+\}|lorem ipsum|placeholder|ejemplo ilustrativo|dato ilustrativo|\bn/d\b", text, re.I):
            errors.append(f"template_placeholder:{text[:40]}")
    lenses = lens_checks(ficha, package)
    for lens, errs in lenses.items():
        errors += [f"{lens}:{e}" for e in errs]
    return {"verdict": "PASS" if not errors else "FAIL", "errors": errors,
            "lenses": {k: ("PASS" if not v else "FAIL") for k, v in lenses.items()}}


# ---------------------------------------------------------------------------------------------
# Storage: one live ficha per family, archive and HOLD


def paths(root: Path, slug: str) -> dict:
    base = Path(root) / STORE
    return {"live": base / "live" / f"{slug}.json", "archive": base / "archive" / slug, "hold": base / "hold"}


def load_live(root: Path, slug: str) -> dict | None:
    try:
        return json.loads(paths(root, slug)["live"].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publish(result: dict, root: Path) -> dict:
    """PASS replaces the live ficha (the previous one goes to the archive); HOLD never publishes."""
    slug = result["slug"]
    p = paths(root, slug)
    if result.get("status") == "pass" and result.get("ficha"):
        previous = load_live(root, slug)
        archived = None
        if previous and previous.get("release_key") != result["ficha"].get("release_key"):
            key = re.sub(r"[^0-9A-Za-z_-]+", "-", f"{previous.get('period')}-{previous.get('release_key', '')}")
            archived = p["archive"] / f"{key}.json"
            if not archived.exists():
                _write(archived, previous)
        _write(p["live"], result["ficha"])
        return {"published": True, "live": str(p["live"]), "archived": str(archived) if archived else None}
    if result.get("status") == "hold":
        out = p["hold"] / f"{slug}-{result.get('period') or 'unknown'}.json"
        _write(out, {k: result.get(k) for k in ("status", "family", "period", "generated_at", "decision",
                                                "verification", "errors", "candidate")})
        return {"published": False, "hold": str(out)}
    return {"published": False}


# ---------------------------------------------------------------------------------------------
# Web snapshot


PUBLIC_KEYS = ("schema_version", "id", "family", "family_label", "period", "published_at", "generated_at",
               "release_key", "featured", "triggers", "kicker", "kicker_meta", "headline", "headline_type", "dek",
               "dek_emphasis", "kpis", "tabs", "charts", "facts", "lectura", "watch", "notes", "sources", "machine_note",
               "status", "late_release", "revisions")


def live_fichas(root: Path = Path("."), registry: dict | None = None) -> list[dict]:
    registry = registry or load_registry()
    out = []
    for fam, cfg in registry["families"].items():
        if cfg.get("status") != "active":
            continue
        live = load_live(Path(root), cfg["slug"])
        if live and live.get("status") == "PASS" and live.get("family") == fam:
            out.append(live)
    return out


def public_ficha(ficha: dict) -> dict:
    pub = {k: deepcopy(ficha.get(k)) for k in PUBLIC_KEYS if k in ficha}
    lect = pub.get("lectura") or {}
    pub["lectura"] = {"status": lect.get("status"), "text": lect.get("text")} if lect.get("status") == "pass" and lect.get("text") else None
    return pub


def ficha_card(ficha: dict, cfg: dict) -> dict:
    from .editorial_committee import build_committee_artifact
    pub = public_ficha(ficha)
    card = {
        "piece_id": f"stats-ficha:{ficha['family']}:{ficha['period']}",
        "title": ficha["headline"], "display_title": ficha["headline"],
        "source_name": cfg.get("source_name") or "Superintendencia de Salud", "source_type": "official",
            # Only a captured source (URL + SHA-256 in the evidence package) may back the card link.
        "source_url": (ficha.get("sources") or [{}])[0].get("url"),
        "event_date": ficha["published_at"], "publication_date": ficha["published_at"],
        "validation_date": str(ficha.get("generated_at") or "")[:10] or None,
        "data_period": ficha["period"], "event_type": "DATA_PULSE", "category": "Datos sectoriales",
        "signal_types": ["Datos"], "scopes": list(cfg.get("scopes") or ["Isapres"]), "ingestion_mode": "BACKFILL",
        "distribution": "archive",
        "radar_score": 86 if ficha.get("featured") else 72, "confidence_score": 100,
        "what_happened": ficha["dek"], "card_what": ficha["dek"], "card_why_optional": True, "why_it_matters": "",
        "statistical_value_level": "stats_ficha", "feed_visibility": True, "editorial_decision": "accept",
        "publication_gate_reason": "stats_ficha_pass", "publication_ready_score": 100,
        "stats_ficha": pub,
        # Stable per-family share page with OG preview; it redirects to the current ficha.
        "share_url": f"data/fichas/{cfg['slug']}.html",
    }
    card["editorial_committee"] = build_committee_artifact(card)
    return card


def _stat_family(s: dict) -> str | None:
    if s.get("source_name") != "Superintendencia de Salud" or "Datos" not in (s.get("signal_types") or []):
        return None
    t = str(s.get("title") or "").lower()
    if "movilidad" in t:
        return "movilidad"
    if "cartera" in t and "regional" in t:
        return "cartera_regional"
    if "cartera" in t:
        return "cartera_total"
    if "suscripciones" in t or "desahucios" in t:
        return "suscripciones"
    if "casos ges" in t:  # F4: 'Estadística Trimestral de Casos GES (AUGE) … – a junio 2026'
        return "ges"
    if "boletín estadístico informativo ip" in t or "boletin estadistico informativo ip" in t:  # F6
        return "boletin_ip"
    return None


def loose_card_period(card: dict) -> str | None:
    """Data period of a loose SIS statistics card: '… – Agosto 2026' → '2026-08'; None for yearly files."""
    if card.get("data_period"):
        try:
            period_parts(card["data_period"])
            return card["data_period"]
        except ValueError:
            pass
    m = re.search(r"[–-]\s*(?:a\s+)?([a-záéíóú]+)\s+(20\d{2})\s*$", _fold(card.get("title")))
    if m and m[1] in MONTHS_ES:
        return f"{m[2]}-{MONTHS_ES.index(m[1]) + 1:02d}"
    return None


def ficha_covers(card: dict, ficha: dict) -> bool:
    """A loose card is absorbed only when the ficha already covers its release.

    Monthly cards ('… – Agosto 2026'): absorbed when their period ≤ the ficha's data period. Cards without a
    month (cumulative '– año 2026' books): absorbed when published on or before the ficha's release, as in the
    pulse rule of #84 (commit 6099d0d8). A newer release (e.g. September) stays visible until the ficha updates.
    """
    period = loose_card_period(card)
    if period:
        return period_parts(period) <= period_parts(ficha["period"])
    day = str(card.get("event_date") or card.get("publication_date") or "")[:10]
    return bool(day) and day <= str(ficha.get("published_at") or "")[:10]


def apply_to_snapshot(cards: list[dict], fichas: list[dict], registry: dict | None = None) -> list[dict]:
    """One live ficha per family: add its card and drop the pulses and loose cards whose release it covers."""
    registry = registry or load_registry()
    out = list(cards)
    for ficha in fichas:
        cfg = registry["families"][ficha["family"]]
        sup = cfg.get("supersedes") or {}
        prefixes = tuple(sup.get("event_titles_prefix") or ())
        fams = set(sup.get("stat_families") or ())

        def superseded(c: dict) -> bool:
            if str(c.get("piece_id") or "").startswith(f"stats-ficha:{ficha['family']}:"):
                return True
            if prefixes and str(c.get("title") or "").startswith(prefixes) and c.get("event_type") == "DATA_PULSE":
                return True
            return _stat_family(c) in fams and ficha_covers(c, ficha)

        out = [c for c in out if not superseded(c)]
        out.append(ficha_card(ficha, cfg))
    return out


SITE_URL = "https://cftorre1.github.io/Radar-salud/"
OG_IMAGE = SITE_URL + "assets/alicanto-logo-header.png"


def share_page(card: dict) -> str:
    """Static page for 'Compartir informe': OG title/description/image, then a redirect to the ficha."""
    import base64
    from html import escape
    ficha = card["stats_ficha"]
    target_id = "sig-" + (card.get("piece_id") or base64.b64encode(str(card.get("source_url")).encode()).decode())
    # '?abrir=1' makes the app open the ficha detail, not just scroll to its row.
    target = "../../index.html?abrir=1#" + target_id
    page_url = SITE_URL + card["share_url"]
    title = escape(f"{ficha['headline']} · Alicanto Salud", quote=True)
    desc = escape(ficha.get("dek") or "", quote=True)
    return (
        "<!doctype html>\n<html lang=\"es\"><head><meta charset=\"utf-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
        f"<title>{title}</title><meta name=\"description\" content=\"{desc}\"/>"
        f"<link rel=\"canonical\" href=\"{escape(page_url, quote=True)}\"/>"
        "<meta property=\"og:type\" content=\"article\"/><meta property=\"og:site_name\" content=\"Alicanto Salud\"/>"
        f"<meta property=\"og:title\" content=\"{title}\"/><meta property=\"og:description\" content=\"{desc}\"/>"
        f"<meta property=\"og:url\" content=\"{escape(page_url, quote=True)}\"/><meta property=\"og:image\" content=\"{OG_IMAGE}\"/>"
        "<meta name=\"twitter:card\" content=\"summary\"/>"  # no real preview image: the logo is a small square
        f"<meta http-equiv=\"refresh\" content=\"0; url={escape(target, quote=True)}\"/>"
        "<style>body{margin:0;padding:24px 16px;background:#FAF9F5;color:#1D3345;font-family:Inter,ui-sans-serif,system-ui,sans-serif}"
        "h1{font:400 26px/1.2 Georgia,serif;max-width:28ch}a{color:#1D3345;text-decoration-color:#C37C37}</style></head><body>"
        f"<p>{escape(ficha.get('kicker') or '')}</p><h1>{escape(ficha['headline'])}</h1><p>{desc}</p>"
        f"<p><a href=\"{escape(target, quote=True)}\">Abrir la ficha en Alicanto Salud</a></p></body></html>\n")


def write_share_pages(cards: list[dict], web_data_dir: Path) -> list[str]:
    out = []
    for card in cards:
        if card.get("stats_ficha") and card.get("share_url"):
            path = Path(web_data_dir) / "fichas" / Path(card["share_url"]).name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(share_page(card), encoding="utf-8")
            out.append(str(path))
    return out


# ---------------------------------------------------------------------------------------------
# GES card (F4 interim): a finding is shown only when the corrected parser reconciled it


GES_PARSER = "ges_pinned_year_reconciled_v2"
GES_HOLD_REASON = "HOLD_GES_UNPINNED_OR_UNRECONCILED"


def ges_finding_valid(meta: dict | None) -> bool:
    meta = meta or {}
    return (meta.get("family") == "ges" and meta.get("status") == "validated" and meta.get("parser") == GES_PARSER
            and (meta.get("reconciliation") or {}).get("ok") is True)


GES_CORRECTION_DATE = "2026-10-28"
GES_LEGACY_PARSER = "ges_first_sheet_v1"  # the parser that read the first sheet without pinning the year


def correction_label(corrected_at: str) -> str:
    """'28 oct': the same short date on the row tag and in the detail note."""
    d = date.fromisoformat(corrected_at[:10])
    return f"{d.day} {MONTHS_ES[d.month - 1][:3]}"


def correction_record(corrected_at: str) -> dict:
    return {"corrected_at": corrected_at, "label": correction_label(corrected_at), "text": _ges_correction_note(corrected_at)}


def _ges_correction_note(corrected_at: str) -> str:
    return (f"Corregido el {correction_label(corrected_at)}: se retiró un hallazgo automático que leía la hoja "
            "de otro año de la planilla y no conciliaba con el total declarado; vuelve con la ficha GES.")


def sanitize_ges_signal(signal: dict, *, corrected_at: str = GES_CORRECTION_DATE) -> dict:
    """Old GES findings (e.g. sheet 'Año 2005' → '21 presenta el mayor volumen…') go to HOLD.

    History is preserved (CLAUDE.md rule 6): the withdrawn sentences stay verbatim in ``superseded_meta`` with
    ``corrected_at``, ``reason`` and the parser versions, and the card shows a short public correction note.
    """
    meta = signal.get("data_insight_meta") or {}
    if meta.get("family") != "ges" or ges_finding_valid(meta):
        return signal
    if meta.get("status") == "HOLD" and not signal.get("data_insights"):
        done_at = (meta.get("superseded_meta") or {}).get("corrected_at")
        view = signal.get("statistical_view") or {}
        if done_at and view.get("correction"):
            if view["correction"] == correction_record(done_at):
                return signal
            return {**signal, "statistical_view": {**view, "correction": correction_record(done_at)}}  # label refresh
        if not meta.get("superseded_meta"):
            return signal  # a HOLD from the corrected parser itself: nothing was withdrawn
    r = dict(signal)
    prior = meta.get("superseded_meta") if meta.get("status") == "HOLD" else meta
    prior = dict(prior or {})
    withdrawn = list(prior.pop("withdrawn_insight_texts", None) or prior.get("insights") or [])
    withdrawn_cards = list(prior.pop("withdrawn_data_insights", None) or signal.get("data_insights") or [])
    sheet = prior.get("sheet")
    superseded = {k: v for k, v in prior.items() if k not in ("insights", "withdrawn_insights")}
    superseded.update(
        withdrawn_insight_texts=withdrawn, withdrawn_data_insights=withdrawn_cards,
        withdrawn_insights=len(withdrawn) if withdrawn else prior.get("withdrawn_insights", 0),
        corrected_at=prior.get("corrected_at") or corrected_at,
        reason=prior.get("reason") or (f"parser leía hoja {sheet}" if sheet else "parser sin hoja del año fijada ni total conciliado"),
        superseded_parser=prior.get("superseded_parser") or prior.get("parser") or GES_LEGACY_PARSER,
        corrected_by_parser=GES_PARSER)
    held = {"family": "ges", "status": "HOLD", "hold_reason": GES_HOLD_REASON, "parser": GES_PARSER,
            "superseded_meta": superseded}
    r["data_insights"] = []
    r["data_insight_meta"] = held
    r["statistical_view"] = {
        "family": "ges", "publication_status": "HOLD", "hold_reason": GES_HOLD_REASON,
        "limitations": ["La lectura automática de la planilla GES no fijó la hoja del año en curso ni concilió la suma "
                        "con el total declarado; el hallazgo queda retenido hasta la ficha GES (F4)."],
        "correction": correction_record(superseded["corrected_at"]),
        "source_url": r.get("source_url")}
    return r


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------------------------
# Generic family run (F4, F6): same publication contract as F1's run


LECTURA_OMITTED = {"not_attempted": "sin modelo en esta corrida", "no_budget": "sin presupuesto",
                   "verifier_fail": "no pasó el verificador", "generation_error": "error del modelo",
                   "review_fail": "no pasó la revisión de un segundo modelo",
                   "review_no_budget": "sin presupuesto para la revisión", "review_error": "error del revisor",
                   "review_not_run": "sin revisión de un segundo modelo"}


def run_family(family: str, *, builder_version: str, build_package: Callable[..., dict], compose: Callable[..., dict],
               root: Path, today: date, registry: dict | None = None, llm: bool = True,
               model_call: Callable[..., Any] | None = None,
               budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    """Package → triggers → HOLD or compose → deterministic verification → Lectura (verifier + reviewer) → PASS.

    HOLD never publishes (reconciliation, hash, older period, verification). A new builder version republishes the
    same release without a new paid Lectura; a paid attempt for one release is never repeated automatically.
    """
    registry = registry or load_registry()
    cfg = registry["families"][family]
    previous = load_live(root, cfg["slug"])
    generated = now_iso()
    base = {"family": family, "slug": cfg["slug"], "generated_at": generated}
    try:
        package = build_package(root, registry, previous)
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        return {**base, "status": "hold", "period": None, "errors": [f"package_error:{type(exc).__name__}:{exc}"[:200]]}
    decision = evaluate_triggers(package, previous, today=today, calendar=cfg["calendar"])
    base.update(period=package.get("period"), decision=decision)
    if decision["decision"] == "HOLD":
        return {**base, "status": "hold", "errors": decision["holds"],
                "candidate": {"reconciliation": package.get("reconciliation")}}
    if decision["decision"] == "NO_CHANGE" and previous and previous.get("builder_version") != builder_version:
        decision = {**decision, "decision": "PUBLISH", "triggers": list(dict.fromkeys([*(previous.get("triggers") or []), "format_update"]))}
        base["decision"] = decision
    retry = (decision["decision"] == "NO_CHANGE" and previous and llm
             and (previous.get("lectura") or {}).get("status") in {"not_attempted", "no_budget"})
    if decision["decision"] == "NO_CHANGE" and not retry:
        return {**base, "status": "no_change"}
    if decision.get("late_release"):
        package["constants"].append(decision["late_release"]["days_late"])
    ficha = compose(package, registry, today=today, decision=decision)
    verification = verify_ficha(ficha, package)
    if verification["verdict"] != "PASS":
        return {**base, "status": "hold", "verification": verification, "errors": verification["errors"], "candidate": ficha}
    same = previous and previous.get("release_key") == package["release_key"]
    prev_lect = (previous or {}).get("lectura") or {}
    if same and prev_lect.get("status") not in {"not_attempted", "no_budget", None}:
        lect = prev_lect  # never pay twice for one release
    else:
        lect = generate_lectura(ficha, package, registry=registry, enabled=llm, model_call=model_call, budget=budget)
    ficha["lectura"] = lect
    if lect.get("status") == "pass":
        again = verify_lectura(lect.get("text"), package, registry=registry, ficha=ficha)
        with_lectura = verify_ficha(ficha, package)
        if with_lectura["verdict"] != "PASS" or again["verdict"] != "PASS":
            lect = {**lect, "status": "verifier_fail", "rejected_text": lect.get("text"), "text": None,
                    "verification": {**(lect.get("verification") or {}), "verdict": "FAIL", "errors": again["errors"],
                                     "ficha_errors": with_lectura["errors"]}}
        else:
            lect = with_review(lect, ficha, package, registry=registry, enabled=llm, model_call=model_call, budget=budget)
        ficha["lectura"] = lect
    if lect.get("status") == "pass":
        ficha["machine_note"] += f" Costo de IA: USD {lect.get('cost_usd', 0):.4f}."
    else:
        ficha["machine_note"] += " Lectura Alicanto omitida (" + LECTURA_OMITTED.get(lect.get("status"), "no disponible") + ")."
    if retry:
        ficha["triggers"] = previous.get("triggers") or ficha["triggers"]
        ficha["featured"] = previous.get("featured", ficha["featured"])
    ficha.update(status="PASS", generated_at=generated, builder_version=builder_version, verification=verification,
                 reconciliation=package["reconciliation"],
                 evidence={k: package.get(k) for k in ("values", "constants", "entity_codes", "entity_keys", "release_key",
                                                        "period", "lectura_pool", "derived_ratios", "ranks")})
    return {**base, "status": "pass", "ficha": ficha}
