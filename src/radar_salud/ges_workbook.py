"""SIS 'Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema Isapre' workbook parser (F4).

Layout of the SIS workbook (seen in the text receipt of the June 2026 file, sha256 5a84c70c…): one sheet per year
('Año 2005' … 'Año 2026'). Each year sheet has a two-row header: the first row carries 'N°', 'PROBLEMA DE SALUD' and,
over each pair of columns, a group title; the second row carries 'FONASA' / 'ISAPRE' under each group.

- 'Número de casos acumulados Jul-2005 a <Mar|Jun|Sep|Dic>-<YYYY>': cumulative count **since July 2005** at that cut.
  Never a figure to show: it is only differenced.
- 'Ingresos entre Ene y <mes> <YYYY>': year-to-date flow (cases that entered between January and the cut).

Dirección, 3-nov-2026 ("Ene–jun vs ene–jun"): the F4 measure is year-to-date; quarters are differences of cumulative
cuts, and Q1 is the March cut minus the December cut of the previous year (never the March cut alone).

What this parser reads for a release whose period is ``YYYY-MM`` (MM ∈ 03, 06, 09, 12), each sheet pinned by name:
- 'Año YYYY': the cumulative cuts up to MM and the year-to-date column of MM;
- 'Año YYYY−1': its four cumulative cuts and its January–December year-to-date column;
- 'Año YYYY−2': its December cumulative cut (to derive the previous year's year-to-date by difference).

Reconciliation (any failure → HOLD with the reason, no figure):
- in every pinned sheet and every column read, the problem rows add up to the declared 'Total' row, Fonasa and Isapre;
- year-to-date identity, per problem and in total, per insurer: ingresos(ene..t) = acumulado(t) − acumulado(dic del
  año anterior), for the reporting year and for the previous year's December column. A problem absent from the
  previous year's sheet (new decree) enters with 0; the total identity runs over the problems of the sheet (a problem
  dropped from the list keeps its December cumulative in the previous total but has no flow).

The workbook binary is never stored; only these values, their rows and the header texts.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

GES_PARSER = "ges_ytd_cuts_v4"  # mirrored in stats_fichas.GES_PARSER and data_insights.GES_PARSER
MONTHS = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9,
          "oct": 10, "nov": 11, "dic": 12}
MONTH_NAMES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
               "noviembre", "diciembre")
CUT_RX = re.compile(r"acumulad[oa]s?\s+(?:desde\s+)?jul\w*\.?[\s-]*(?:de\s+)?2005\s+(?:a|al|hasta)\s+"
                    r"(?P<m>[a-z]{3})\w*\.?[\s-]*(?:de\s+)?(?P<y>20\d{2})")
YTD_RX = re.compile(r"ingresos\s+entre\s+ene\w*\.?\s+y\s+(?P<m>[a-z]{3})\w*\.?\s+(?:de\s+)?(?P<y>20\d{2})")
CODE_HEAD = re.compile(r"^n\s*\W?\s*[°ºo]?\.?$")
MISSING = {"", "nd", "n/d", "-", "s/i", "--"}
FOOTNOTE = re.compile(r"(?:\s*\(\d{1,2}\))+\s*$")
# Real SIS workbooks (2025-03 … 2026-06) carry one un-numbered row of cases with no health problem informed just above
# the Total. It is part of the declared total: kept apart (never a problem, never ranked) and reconciled with the rows.
UNASSIGNED = re.compile(r"^sin problema de salud informado$")
MAX_ROWS = 700


class GesHold(Exception):
    """A HOLD with its reason code; ``extra`` (never a key named ``reason``: use ``detail``) is recorded with it."""

    def __init__(self, reason: str, **extra):
        super().__init__(reason)
        self.reason, self.extra = reason, extra


REGISTRY = Path(__file__).resolve().parents[2] / "config/stats_fichas_v1.json"
DEFAULT_MIN_PROBLEMS = 80


def min_problems() -> int:
    """Minimum problem rows per year sheet (registry ``families.F4.capture.min_problems``): the GES list has had 80+
    problems since 2013 (85 in 2019, 87 in 2022); a sheet with fewer was cut short or is not the GES table."""
    try:
        cfg = json.loads(REGISTRY.read_text(encoding="utf-8"))["families"]["F4"]["capture"]
        n = int(cfg.get("min_problems") or DEFAULT_MIN_PROBLEMS)
    except (OSError, ValueError, KeyError, TypeError):
        n = DEFAULT_MIN_PROBLEMS
    return max(n, 3)


def fold(v: Any) -> str:
    s = " ".join(str(v if v is not None else "").replace("\n", " ").split()).casefold()
    return s.translate(str.maketrans("áéíóúüñ", "aeiouun"))


def norm(v: Any) -> str:
    return " ".join(str(v if v is not None else "").replace("\n", " ").split()).strip()


def title_period(title: str) -> str | None:
    m = re.search(r"(" + "|".join(MONTH_NAMES) + r")\s+(20\d{2})", fold(title))
    return f"{m[2]}-{MONTH_NAMES.index(m[1]) + 1:02d}" if m else None


def _period(m: re.Match) -> str | None:
    month = MONTHS.get(m["m"])
    return f"{m['y']}-{month:02d}" if month else None


def _count(v: Any, where: str) -> int | None:
    """A case count, or None for an empty / 'ND' cell (problem not in force or not available at that cut)."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise GesHold("HOLD_GES_INVALID_COUNT", at=where)
    if isinstance(v, (int, float)):
        if v < 0 or v != int(v):
            raise GesHold("HOLD_GES_INVALID_COUNT", at=where, value=repr(v)[:20])
        return int(v)
    s = fold(v)
    if s in MISSING:
        return None
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+|\d+", s):
        return int(s.replace(".", ""))
    raise GesHold("HOLD_GES_INVALID_COUNT", at=where, value=norm(v)[:20])


def _code(v: Any) -> int | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)) and v == int(v) and v > 0:
        return int(v)
    s = norm(v)
    return int(s) if s.isdigit() and int(s) > 0 else None


def pin_sheet(wb, year: int):
    """The one sheet whose name carries ``year`` (and no other year); never another year's sheet."""
    hits = [ws for ws in wb.worksheets if re.search(rf"(?<!\d){year}(?!\d)", ws.title)]
    if len(hits) != 1:
        raise GesHold("HOLD_GES_SHEET_NOT_PINNED", year=year, sheets=[ws.title for ws in wb.worksheets][:40])
    return hits[0]


def read_year_sheet(ws, year: int, *, cuts: list[str], ytd: list[str], min_rows: int | None = None) -> dict:
    """Read the columns ``cuts`` (cumulative since Jul-2005) and ``ytd`` (ingresos entre ene y …) of one year sheet.

    The table is: problem rows numbered 1…n with no gap or repeat (n ≥ ``min_rows``), optional 'Subtotal' rows, and
    one 'Total' row that is the last labelled row of the sheet. A 'Total…' row followed by more rows (e.g. a decree
    total labelled 'Total Decreto…' in the middle of the table) is a HOLD, never a short table."""
    min_rows = min_problems() if min_rows is None else min_rows
    sheet = ws.title
    rows = [list(r[:40]) for r in ws.iter_rows(min_row=1, max_row=MAX_ROWS, values_only=True)]
    head = None
    for hi, row in enumerate(rows[:60]):
        f = [fold(v) for v in row]
        name_col = next((i for i, x in enumerate(f) if "problema" in x), None)
        if name_col is None:
            continue
        groups: dict[tuple[str, str], int] = {}
        titles: dict[tuple[str, str], str] = {}
        for c, x in enumerate(f):
            for kind, rx in (("cut", CUT_RX), ("ytd", YTD_RX)):
                m = rx.search(x)
                if m:
                    per = _period(m)
                    if not per or (kind, per) in groups:
                        raise GesHold("HOLD_GES_HEADER_NOT_VALIDATED", sheet=sheet, column=c + 1, title=norm(row[c])[:80])
                    groups[(kind, per)] = c
                    titles[(kind, per)] = norm(row[c])
        if groups:
            head = (hi, name_col, groups, titles)
            break
    if head is None:
        raise GesHold("HOLD_GES_SCHEMA_NOT_VALIDATED", sheet=sheet)
    hi, name_col, groups, titles = head
    code_col = name_col - 1
    if code_col < 0 or not CODE_HEAD.match(fold(rows[hi][code_col])):
        raise GesHold("HOLD_GES_SCHEMA_NOT_VALIDATED", sheet=sheet, detail="no_code_column")
    if hi + 1 >= len(rows):
        raise GesHold("HOLD_GES_SCHEMA_NOT_VALIDATED", sheet=sheet, detail="no_subheader")
    sub = rows[hi + 1]
    want = [("cut", p) for p in cuts] + [("ytd", p) for p in ytd]
    for key in want:
        if key not in groups:
            raise GesHold("HOLD_GES_COLUMN_MISSING", sheet=sheet, column=f"{key[0]}:{key[1]}")
        if not key[1].startswith(f"{year}-"):
            raise GesHold("HOLD_GES_HEADER_NOT_VALIDATED", sheet=sheet, column=f"{key[0]}:{key[1]}")
        c = groups[key]
        if c + 1 >= len(sub) or "fonasa" not in fold(sub[c]) or "isapre" not in fold(sub[c + 1]):
            raise GesHold("HOLD_GES_HEADER_NOT_VALIDATED", sheet=sheet, column=f"{key[0]}:{key[1]}", detail="fonasa_isapre")
    problems: dict[str, dict] = {}
    unassigned = None
    total = None
    subtotals = []
    for offset, data in enumerate(rows[hi + 2:], hi + 3):
        data = data + [None] * (40 - len(data))
        label = norm(data[name_col])
        lab = fold(label)
        code = _code(data[code_col])
        if lab.startswith("subtotal"):
            subtotals.append(offset)
            continue
        if lab.startswith("total"):
            total = (offset, data)
            # Nothing labelled or numbered may follow the Total row: an early 'Total Decreto…' would cut the table.
            for after, rest in enumerate(rows[offset:], offset + 1):
                rest = rest + [None] * (40 - len(rest))
                if norm(rest[name_col]) or norm(rest[code_col]):
                    raise GesHold("HOLD_GES_ROWS_AFTER_TOTAL", sheet=sheet, total_row=offset, row=after,
                                  label=norm(rest[name_col])[:40])
            break
        if code is None:
            if not label and not norm(data[code_col]):
                continue  # blank line, or the line of cut dates under the header (no code, no label)
            if UNASSIGNED.match(FOOTNOTE.sub("", lab).strip()) and not norm(data[code_col]):
                if unassigned is not None:
                    raise GesHold("HOLD_GES_DUPLICATE_PROBLEM", sheet=sheet, row=offset, code="sin_problema")
                unassigned = {"label": FOOTNOTE.sub("", label).strip(), "row": offset}
                for kind, per in want:
                    c = groups[(kind, per)]
                    pair = [_count(data[c], f"{sheet}!{offset}"), _count(data[c + 1], f"{sheet}!{offset}")]
                    unassigned.setdefault(kind, {})[per] = None if pair == [None, None] else pair
                continue
            raise GesHold("HOLD_GES_ROW_UNRECOGNIZED", sheet=sheet, row=offset, label=label[:40])
        if not re.search(r"[a-záéíóúñ]", label, re.I):
            raise GesHold("HOLD_GES_LABEL_NOT_TEXT", sheet=sheet, row=offset, label=label[:40])
        key = str(code)
        if key in problems:
            raise GesHold("HOLD_GES_DUPLICATE_PROBLEM", sheet=sheet, row=offset, code=code)
        rec = {"code": code, "label": FOOTNOTE.sub("", label).strip(), "row": offset}
        for kind, per in want:
            c = groups[(kind, per)]
            pair = [_count(data[c], f"{sheet}!{offset}"), _count(data[c + 1], f"{sheet}!{offset}")]
            rec.setdefault(kind, {})[per] = None if pair == [None, None] else pair
        problems[key] = rec
    if total is None:
        raise GesHold("HOLD_GES_TOTAL_MISSING", sheet=sheet, header_row=hi + 1)
    codes = sorted(int(k) for k in problems)
    if codes != list(range(1, len(codes) + 1)):
        missing = sorted(set(range(1, (codes[-1] if codes else 0) + 1)) - set(codes))
        raise GesHold("HOLD_GES_PROBLEM_NUMBERS_NOT_CONTIGUOUS", sheet=sheet, missing=missing[:12],
                      first=codes[0] if codes else None)
    if len(problems) < min_rows:
        raise GesHold("HOLD_GES_TOO_FEW_PROBLEMS", sheet=sheet, problems=len(problems), min_problems=min_rows)
    total_row, data = total
    totals: dict[str, dict] = {"cut": {}, "ytd": {}}
    sums = []
    for kind, per in want:
        c = groups[(kind, per)]
        declared = [_count(data[c], f"{sheet}!{total_row}"), _count(data[c + 1], f"{sheet}!{total_row}")]
        if None in declared:
            raise GesHold("HOLD_GES_TOTAL_MISSING", sheet=sheet, row=total_row, column=f"{kind}:{per}")
        rows_ = list(problems.values()) + ([unassigned] if unassigned else [])
        got = [sum(((p.get(kind) or {}).get(per) or [0, 0])[i] or 0 for p in rows_) for i in (0, 1)]
        if got != declared:
            raise GesHold("HOLD_GES_RECONCILIATION", sheet=sheet, column=f"{kind}:{per}",
                          reconciliation={"ok": False, "rows_sum": got, "declared_total": declared, "total_row": total_row})
        totals[kind][per] = declared
        sums.append({"column": f"{kind}:{per}", "rows_sum": got, "declared_total": declared})
    return {"sheet": sheet, "header_row": hi + 1, "total_row": total_row, "subtotal_rows": subtotals,
            "columns": {f"{k}:{p}": [groups[(k, p)] + 1, groups[(k, p)] + 2] for k, p in want},
            "titles": {f"{k}:{p}": titles[(k, p)] for k, p in want}, "problems": problems, "unassigned": unassigned,
            "totals": totals, "sums": sums}


def ytd_identity(cur: dict, prev: dict, ytd_period: str, dec_prev: str) -> list[str]:
    """ingresos(ene..t) = acumulado(t) − acumulado(dic año anterior), per problem and in total, per insurer."""
    bad = []
    t = ytd_period
    for key, p in cur["problems"].items():
        y, c = (p.get("ytd") or {}).get(t), (p.get("cut") or {}).get(t)
        if y is None and c is None:
            continue
        base = ((prev["problems"].get(key) or {}).get("cut") or {}).get(dec_prev) or [0, 0]
        for i, ins in enumerate(("fonasa", "isapre")):
            if y is None or c is None or y[i] is None or c[i] is None or y[i] != c[i] - (base[i] or 0):
                bad.append(f"{t}:ps{key}:{ins}")
    # In total: over the problems of this sheet (a problem dropped from the GES list stays in the previous December
    # total but has no year-to-date flow; it is not a mismatch). Equals the previous December total when none dropped.
    yt, ct = cur["totals"]["ytd"][t], cur["totals"]["cut"][t]
    bt = [sum((((prev["problems"].get(k) or {}).get("cut") or {}).get(dec_prev) or [0, 0])[i] or 0 for k in cur["problems"])
          + ((((prev.get("unassigned") or {}).get("cut") or {}).get(dec_prev) or [0, 0])[i] or 0) for i in (0, 1)]
    for i, ins in enumerate(("fonasa", "isapre")):
        if yt[i] != ct[i] - bt[i]:
            bad.append(f"{t}:total:{ins}")
    return bad


def sis_notes(wb) -> list[str]:
    """The numbered lines of the 'Notas' sheet (source, HIV, deleted cases…), capped: notes for the ficha, no figures."""
    out = []
    for ws in wb.worksheets:
        if fold(ws.title) != "notas":
            continue
        for r in ws.iter_rows(min_row=1, max_row=80, values_only=True):
            line = " ".join(norm(v) for v in list(r)[:8] if norm(v))
            if re.match(r"^\d{1,2}\s", line):
                out.append(line[:600])
        break
    return out[:12]


def compact_sheet(sh: dict, *, labels: bool) -> dict:
    """Stored form of one read sheet: one flat list per problem ([row, f, i, f, i, …] in ``cols`` order) so the
    committed store stays small (~90 problems × 3 sheets × 6 releases); labels only for the reporting year."""
    cols = list(sh["titles"])
    pair = lambda rec, col: (rec.get(col.split(":")[0]) or {}).get(col.split(":", 1)[1]) or [None, None]  # noqa: E731
    out = {"sheet": sh["sheet"], "header_row": sh["header_row"], "total_row": sh["total_row"],
           "subtotal_rows": sh["subtotal_rows"], "cols": cols, "titles": [sh["titles"][c] for c in cols],
           "columns": [sh["columns"][c] for c in cols],
           "totals": [x for c in cols for x in sh["totals"][c.split(":")[0]][c.split(":", 1)[1]]],
           "rows": {k: [p["row"], *(x for c in cols for x in pair(p, c))] for k, p in sh["problems"].items()}}
    if labels:
        out["labels"] = {k: p["label"] for k, p in sh["problems"].items()}
    if sh.get("unassigned"):
        out["unassigned"] = [sh["unassigned"]["row"], *(x for c in cols for x in pair(sh["unassigned"], c))]
    return out


def expand_sheet(st: dict) -> dict:
    """Inverse of ``compact_sheet``: {'sheet', 'total_row', 'titles': {col: title}, 'totals': {'cut': {per: [f, i]},
    'ytd': {…}}, 'problems': {code: {'code', 'row', 'label', 'cut': {per: [f, i] | None}, 'ytd': {…}}}}."""
    cols = st["cols"]
    totals: dict[str, dict] = {"cut": {}, "ytd": {}}
    for j, c in enumerate(cols):
        kind, per = c.split(":", 1)
        totals[kind][per] = st["totals"][2 * j:2 * j + 2]
    problems = {}
    for k, vals in st["rows"].items():
        rec = {"code": int(k), "row": vals[0], "label": (st.get("labels") or {}).get(k)}
        for j, c in enumerate(cols):
            kind, per = c.split(":", 1)
            pr = vals[1 + 2 * j:3 + 2 * j]
            rec.setdefault(kind, {})[per] = None if pr == [None, None] else pr
        problems[k] = rec
    unassigned = None
    if st.get("unassigned"):
        vals = st["unassigned"]
        unassigned = {"row": vals[0], "label": "Sin problema de salud informado"}
        for j, c in enumerate(cols):
            kind, per = c.split(":", 1)
            pr = vals[1 + 2 * j:3 + 2 * j]
            unassigned.setdefault(kind, {})[per] = None if pr == [None, None] else pr
    return {"sheet": st["sheet"], "header_row": st.get("header_row"), "total_row": st["total_row"],
            "titles": dict(zip(cols, st["titles"])), "totals": totals, "problems": problems, "unassigned": unassigned}


def parse(book_bytes: bytes, title: str, *, min_rows: int | None = None) -> dict:
    """``min_rows``: minimum problems per sheet (default: registry ``F4.capture.min_problems``; tests of an excerpt
    pass a smaller one explicitly)."""
    period = title_period(title)
    if not period:
        return {"family": "ges", "status": "period_not_validated", "parser": GES_PARSER, "insights": []}
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(book_bytes), read_only=True, data_only=True)
    except Exception as exc:
        return {"family": "ges", "status": "download_or_open_failed", "parser": GES_PARSER, "insights": [],
                "error": str(exc)[:180]}
    y, m = int(period[:4]), int(period[5:7])
    try:
        if m % 3:
            raise GesHold("HOLD_GES_PERIOD_NOT_QUARTER_END")
        q_cuts = lambda yy, mm: [f"{yy}-{k:02d}" for k in range(3, mm + 1, 3)]  # noqa: E731
        n = min_problems() if min_rows is None else min_rows
        cur = read_year_sheet(pin_sheet(wb, y), y, cuts=q_cuts(y, m), ytd=[period], min_rows=n)
        prev = read_year_sheet(pin_sheet(wb, y - 1), y - 1, cuts=q_cuts(y - 1, 12), ytd=[f"{y - 1}-12"], min_rows=n)
        prev2 = read_year_sheet(pin_sheet(wb, y - 2), y - 2, cuts=[f"{y - 2}-12"], ytd=[], min_rows=n)
        bad = ytd_identity(cur, prev, period, f"{y - 1}-12") + ytd_identity(prev, prev2, f"{y - 1}-12", f"{y - 2}-12")
        if bad:
            raise GesHold("HOLD_GES_YTD_IDENTITY", mismatches=bad[:12], n=len(bad))
        notes = sis_notes(wb)
    except GesHold as h:
        return {"family": "ges", "status": "HOLD", "hold_reason": h.reason, "parser": GES_PARSER, "period": period,
                "insights": [], **h.extra}
    finally:
        try:
            wb.close()
        except Exception:
            pass
    years = {str(y): cur, str(y - 1): prev, str(y - 2): prev2}
    ytd_rows = [(p["label"], sum(x or 0 for x in p["ytd"][period] or [0, 0])) for p in cur["problems"].values()]
    largest = max(ytd_rows, key=lambda r: r[1])
    mlabel = f"{MONTH_NAMES[0]} y {MONTH_NAMES[m - 1]} de {y}"
    return {
        "family": "ges", "status": "validated", "parser": GES_PARSER, "period": period, "sheet": cur["sheet"],
        "rows": len(cur["problems"]), "measure_columns": {"ytd": "ingresos entre enero y el mes del corte",
                                                         "cut": "acumulado desde julio de 2005 (solo para restar)"},
        "header": {"label": "problema de salud", "ytd": cur["titles"][f"ytd:{period}"],
                   "cuts": {k.split(":", 1)[1]: v for k, v in cur["titles"].items() if k.startswith("cut:")}},
        "reconciliation": {"ok": True, "declared_total": cur["totals"]["ytd"][period], "rows_sum": cur["totals"]["ytd"][period],
                           "total_row": cur["total_row"],
                           "columns_reconciled": {s: [x["column"] for x in years[s]["sums"]] for s in years},
                           "ytd_identity": [f"{period} = acumulado {period} − acumulado {y - 1}-12",
                                            f"{y - 1}-12 = acumulado {y - 1}-12 − acumulado {y - 2}-12"]},
        "years": {s: compact_sheet(d, labels=s == str(y)) for s, d in years.items()},
        "notes": notes,
        "insights": [f"{largest[0]} registra el mayor número de casos GES ingresados entre {mlabel} (Fonasa e Isapres); "
                     "no se infiere prevalencia ni causalidad."],
    }
