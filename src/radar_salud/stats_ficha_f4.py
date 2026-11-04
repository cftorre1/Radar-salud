"""F4 · Casos GES: evidence package, KPIs and ficha (no model numbers).

Inputs (captured by ``stats_capture``; never downloaded here):
- ``data/stats_fichas/captures/ges_quarterly.json``: one entry per SIS release ('… a junio 2026'), parsed by
  ``ges_workbook.parse`` (parser ``ges_ytd_cuts_v5``): the year sheets of the release (t), the previous year and the
  one before are pinned by name; every column read reconciles to the declared total; and the year-to-date column
  equals the cumulative cut minus the previous December cut, per problem and in total;
- ``data/market/isapre_portfolio.json`` (F1): Isapre beneficiaries per month, the only rate denominator captured.

Measure (Dirección, 3-nov-2026: "Ene–jun vs ene–jun"; registry ``F4.measure``):
- the ficha shows cases that entered between January and the month of the cut ("ingresos entre enero y junio de
  2026"), compared with the same months of the previous year. The current year comes from the SIS year-to-date column;
  the previous year's same period is derived from the same workbook: acumulado(t−12) − acumulado(dic del año t−2);
- quarters (trend) are differences of cumulative cuts: T1 = corte de marzo − corte de diciembre del año anterior,
  Tq = corte(q) − corte(q−1). The SIS cumulative counts since July 2005 are never shown: they are only differenced;
- the measure is established by a reviewer in the registry (``measure.confirmed``); the header can only veto;
- problems are matched by their GES number. A problem present in only one of the two periods marks a change of the
  GES list (decree) and is kept out of the ranking;
- rates per 1.000 use beneficiaries of the same insurer (Isapre from F1, mean of the month-end stocks of the same
  months). Fonasa beneficiaries are not captured: its rate is 'no disponible', never estimated. Rates are 'tasa bruta'
  and count cases, not persons.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import ges_workbook as gw
from . import stats_fichas as sf
from .stats_fichas import fmt_dec, fmt_int, value
from .weekly_freshness import numbers_in

FAMILY = "F4"
BUILDER_VERSION = "f4_ytd_v4"
CAPTURE = Path("data/stats_fichas/captures/ges_quarterly.json")
PORTFOLIO = Path("data/market/isapre_portfolio.json")
QWORD = {1: "primer", 2: "segundo", 3: "tercer", 4: "cuarto"}
MAX_PROBLEM_ROWS = 8
INS = ("fonasa", "isapre")
# Evidence kind of the SIS cumulative counts since July 2005: inputs to subtract only. Never a showable figure
# (``sf.number_pool`` skips it), never compared as a revision (``sf.detect_revisions`` compares 'captured' only).
CUMULATIVE = "cumulative_input"


def _load(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fold(text: str) -> str:
    return str(text or "").casefold().translate(str.maketrans("áéíóúüñ", "aeiouun"))


def qof(period: str) -> tuple[int, int]:
    y, m = sf.period_parts(period)
    if m % 3:
        raise ValueError(f"not_a_quarter_end:{period}")
    return y, m // 3


def qid(y: int, q: int) -> str:
    return f"{y}T{q}"


def qend(y: int, q: int) -> str:
    return f"{y}-{3 * q:02d}"


def qlabel(y: int, q: int) -> str:
    return f"{QWORD[q]} trimestre de {y}"


def qshort(y: int, q: int) -> str:
    return f"T{q} {y}"


def qprev(y: int, q: int, n: int = 1) -> tuple[int, int]:
    k = y * 4 + (q - 1) - n
    return k // 4, k % 4 + 1


def months_of(y: int, m: int) -> list[str]:
    return [f"{y}-{k:02d}" for k in range(1, m + 1)]


def mname(m: int) -> str:
    return sf.MONTHS_ES[m - 1]


def span(y: int, m: int) -> str:
    """'enero–junio de 2026' (a year-to-date period)."""
    return f"enero–{mname(m)} de {y}"


def between(y: int, m: int) -> str:
    """'entre enero y junio de 2026'."""
    return f"entre enero y {mname(m)} de {y}"


def short(y: int, m: int) -> str:
    """'ene–jun 2026'."""
    return f"ene–{mname(m)[:3]} {y}"


def cut_label(period: str) -> str:
    y, m = sf.period_parts(period)
    return f"{mname(m)[:3]} {y}"


def half_up(x: float) -> int:
    """Round half up, as the verifier does (``fmt_int`` uses Python's round-half-even: 2.501.808,5 → 2.501.808)."""
    return math.floor(x + 0.5)


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _fold(label)).strip("_")[:48] or "problema"


def pkey(code: int | str) -> str:
    """Problems are matched by their GES number (labels change wording between years)."""
    return f"ps{int(code):02d}"


def short_label(label: str, n: int = 18) -> str:
    label = " ".join(str(label).split())
    return label if len(label) <= n else label[: n - 1].rstrip(" ,;-") + "…"


SINCE_2005 = re.compile(r"desde (?:julio )?(?:de )?2005|2005\s*[-–a]\s*20\d\d|desde el inicio|jul\w*[-\s]*(?:de\s+)?2005\s+(?:a|al|hasta)\b")
# 'acumulado del trimestre' / 'casos del trimestre' declare a quarter, never a year-to-date count.
QUARTER_HEAD = re.compile(r"\btrimestr|\btrim\b")
YTD_HEAD = re.compile(r"acumulad[oa]s?\s+(?:en\s+el\s+|del\s+|al\s+)?(?:ano|anual)\b|acumulad[oa]s?\s+(?:desde\s+)?enero"
                      r"|desde\s+enero|\benero\s*(?:a|al|-|–|hasta)\s*[a-z]{3,}|\bene\w*\s*[-–]\s*[a-z]{3}|year\s*to\s*date|\bytd\b"
                      r"|\bentre\s+ene\w*\.?\s+y\s+[a-z]{3}")


def header_measure(parse: dict) -> str | None:
    """What the captured header text of the measure column declares: 'since_2005' | 'ytd' | 'quarter' | 'ambiguous' |
    None (silent). With the v3 parser the measure column is the year-to-date column ('Ingresos entre Ene y Jun 2026');
    the cumulative cuts (since July 2005) are only differenced and are not the measure.

    A bare 'acumulado' declares nothing (it can be cumulative within the quarter); 'acumulado del trimestre' is a
    quarter. Both a year-to-date and a quarter wording → 'ambiguous'."""
    head = parse.get("header") or {}
    parts = [head["ytd"]] if head.get("ytd") else [head.get("fonasa") or "", head.get("isapre") or "", *(head.get("above") or [])]
    text = _fold(" ".join(parts))
    if SINCE_2005.search(text):
        return "since_2005"
    q, y = bool(QUARTER_HEAD.search(text)), bool(YTD_HEAD.search(text))
    return "ambiguous" if q and y else "quarter" if q else "ytd" if y else None


def measure_of(parse: dict, cfg: dict) -> tuple[str | None, str]:
    """('ytd' | 'quarter' | None, how it was established).

    Only a reviewer establishes the measure: without ``measure.confirmed is True`` (registry F4) the ficha HOLDs,
    whatever the header says. The header can only veto: a header declaring 'since 2005', another measure or both
    wordings keeps the HOLD."""
    m = cfg.get("measure") or {}
    if m.get("confirmed") is not True or m.get("declared") not in ("ytd", "quarter"):
        return None, "unconfirmed"
    head = header_measure(parse)
    if head == "since_2005":
        return None, "source_declares_since_2005"
    if head == "ambiguous":
        return None, "header_ambiguous"
    if head and head != m["declared"]:
        return None, f"header_contradicts_reviewer:{head}"
    how = f"confirmed_by_reviewer:{m.get('confirmed_by') or 'registro'}"
    return m["declared"], how + (";header_agrees" if head else ";header_silent")


def _portfolio_isapre(root: Path) -> dict:
    """Isapre beneficiaries per month from the F1 capture (declared 'Total Sistema'), with its source."""
    data = _load(root / PORTFOLIO) or {}
    obs = data.get("observations") or []
    shas = {o.get("source_sha256") for o in obs}
    urls = {o.get("source_url") for o in obs}
    if len(shas) != 1 or len(urls) != 1:
        return {}
    totals = {c["period"]: c["total_beneficiaries"] for c in data.get("coverage") or []
              if isinstance(c.get("total_beneficiaries"), int) and len(c.get("codes") or []) == 10}
    return {"totals": totals, "sha256": next(iter(shas)), "url": next(iter(urls)), "published_at": data.get("published_at"),
            "fetched_at": max((o.get("fetched_at") or "") for o in obs) or None}


# ---------------------------------------------------------------------------------------------
# Evidence package


def _release_state(rel: dict) -> tuple[dict | None, str | None]:
    """(parse, None) for a release whose capture is usable, else (None, why)."""
    doc = rel.get("document") or {}
    parse = doc.get("parse") or {}
    period = rel.get("period")
    if doc.get("status") != "captured":
        return None, doc.get("status") or "missing"
    if parse.get("parser") != sf.GES_PARSER:
        # Parsed by an older parser: the daily capture re-reads the same file once (hash-checked) with the current one.
        return None, f"parser_outdated:{parse.get('parser')}:recheck_pending"
    if parse.get("status") != "validated" or (parse.get("reconciliation") or {}).get("ok") is not True:
        return None, parse.get("hold_reason") or parse.get("status") or "missing"
    if parse.get("period") != period or str(parse.get("sheet") or "").find(period[:4]) < 0:
        return None, "sheet_or_period_mismatch"
    return parse, None


def build_package(root: Path, registry: dict | None = None, previous_live: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    root = Path(root)
    store = _load(root / CAPTURE)
    if not store or not store.get("releases"):
        raise ValueError("ges_capture_missing")
    releases = {r.get("period"): r for r in store["releases"] if r.get("period")}
    if not releases:
        raise ValueError("ges_capture_empty")
    t = max(releases)
    rel = releases[t]
    doc = rel.get("document") or {}
    failures: list[str] = []
    invalid = {}
    for p, r in releases.items():
        _, why = _release_state(r)
        if why:
            invalid[p] = why
    parse, why = _release_state(rel)
    measure, how = (None, None)
    try:
        ty, tq = qof(t)
    except ValueError:
        failures.append(f"not_a_quarter_end:{t}")
        ty, tq = 0, 0
    if why:
        failures.append(f"latest_release_not_valid:{t}:{why}")
    else:
        measure, how = measure_of(parse, cfg)
        if measure is None:
            failures.append(f"latest_release_not_valid:{t}:measure_{how}")
        elif measure != "ytd":
            failures.append(f"measure_not_ytd:{measure}")  # Dirección 3-nov-2026: year-to-date only
    published = rel.get("published_at")
    package: dict[str, Any] = {
        "family": FAMILY, "period": t, "published_at": published,
        # The captured file's hash is recorded even when its parse HOLDs: the hold names the parse, not a missing hash.
        "release_key": sf.release_key(t, doc.get("sha256") or "0" * 16),
        "primary_source": {"url": doc.get("url"), "sha256": doc.get("sha256") if doc.get("status") == "captured" else None},
        "sources": {}, "values": {}, "entities": [{"code": None, "key": "fonasa", "name": "Fonasa"}], "entity_codes": [],
        "entity_keys": ["fonasa"], "causal_note": None, "provisional": False,
        "reconciliation": {"ok": not failures, "failures": failures, "checks": [
            "hojas del año del corte, del año anterior y del previo fijadas por nombre (nunca otra hoja)",
            "Σ filas por problema = total declarado en cada columna leída, Fonasa e Isapre",
            "ingresos ene–mes (columna SIS) = acumulado(t) − acumulado(dic del año anterior), por problema y en total",
            "medida confirmada por un revisor en el registro (acumulado del año, Dirección 3-nov-2026)",
            "cortes acumulados nunca bajan (dic del año anterior ≤ mar ≤ … ≤ t)",
            "un solo archivo y hash por release"]},
        "group_markers": [
            [r"(?:las |a las |de las |en las |entre las )?isapres?|(?:el )?sistema isapre", "isapres"],
            [r"(?:el|al|del) sistema|(?:el|al|del) total|ambos seguros|(?:el|al|del) ges(?! [a-z])", "system"]],
        "prompt_rules": ("Fonasa es un seguro y 'las Isapres' (en conjunto) el otro; 'el total' o 'ambos seguros' es la "
                         "suma. Las cifras son casos ingresados entre enero y el mes del corte: nombra el período "
                         "('entre enero y junio de 2026'); una variación anual se compara con los mismos meses del año "
                         "anterior ('frente a enero–junio de 2025'). Nunca cites acumulados desde 2005. La tasa es bruta "
                         "y por cada mil beneficiarios del mismo seguro; cuenta casos, no personas; Fonasa no tiene tasa."),
    }
    if failures:
        package.update(findings=[], kpis={"invalid": invalid}, revisions=[], constants=[], periods=[t])
        return package
    return _fill(package, parse, cfg, root, ty, tq, invalid, how, releases, previous_live)


def _fill(package: dict, parse: dict, cfg: dict, root: Path, ty: int, tq: int, invalid: dict, how: str,
          releases: dict, previous_live: dict | None) -> dict:
    t = package["period"]
    tm = 3 * tq
    by = ty - 1
    b = f"{by}-{tm:02d}"
    dec1, dec2 = f"{ty - 1}-12", f"{ty - 2}-12"
    years = {k: gw.expand_sheet(v) for k, v in parse["years"].items()}
    failures = package["reconciliation"]["failures"]
    values: dict[str, dict] = package["values"]
    sources: dict[str, dict] = package["sources"]
    doc = releases[t]["document"]
    src = "ges_" + t
    sources[src] = sf.source_ref(
        url=doc["url"], sha256=doc["sha256"], published_at=releases[t].get("published_at"),
        fetched_at=doc.get("rechecked_at") or doc.get("fetched_at"),  # a re-read with the current parser dates the bytes
        label=f"SIS · Casos GES de Fonasa e Isapres a {sf.month_label(t)} (xlsx)",
        role="casos ingresados entre enero y el corte (columna 'Ingresos entre Ene y …') y cortes acumulados por problema y seguro",
        locator=f"{parse['sheet']}!fila Total {years[str(ty)]['total_row']}")

    def sheet_of(per: str) -> dict:
        return years[per[:4]]

    def cut_pair(per: str, key: str | None = None) -> list | None:
        sh = sheet_of(per)
        if key is None:
            return sh["totals"]["cut"].get(per)
        p = sh["problems"].get(key)
        return ((p or {}).get("cut") or {}).get(per)

    def derived(vid: str, val: float, formula: str, inputs: list[str], unit: str, period: str) -> float:
        values[vid] = value(vid, val, unit=unit, period=period, source=None, formula=formula, inputs=inputs, kind="derived")
        return val

    def add_cut(per: str) -> list[str]:
        """Captured cumulative totals (since July 2005) of one cut: evidence only, never shown."""
        sh = sheet_of(per)
        ids = []
        for i, ins in enumerate(INS):
            vid = f"ges.cut.{per}.{ins}"
            values[vid] = value(vid, sh["totals"]["cut"][per][i], unit="casos acumulados desde jul-2005", period=per, source=src,
                                locator=f"{sh['sheet']}!fila {sh['total_row']} (Total) · {sh['titles']['cut:' + per]} · {ins.capitalize()}",
                                kind=CUMULATIVE)
            ids.append(vid)
        return ids

    def add_problem_cut(per: str, code: str) -> list[str]:
        sh = sheet_of(per)
        p = sh["problems"][code]
        ids = []
        for i, ins in enumerate(INS):
            vid = f"ges.cut.{per}.p.{pkey(code)}.{ins}"
            values[vid] = value(vid, (p["cut"][per] or [0, 0])[i] or 0, unit="casos acumulados desde jul-2005", period=per,
                                source=src, locator=f"{sh['sheet']}!fila {p['row']} (problema N°{p['code']}) · "
                                                    f"{sh['titles']['cut:' + per]} · {ins.capitalize()}", kind=CUMULATIVE)
            ids.append(vid)
        return ids

    def unassigned_cut(per: str) -> list:
        """The un-numbered 'Sin problema de salud informado' row: part of the declared total, never a problem."""
        return list((((sheet_of(per).get("unassigned") or {}).get("cut") or {}).get(per)) or [0, 0])

    def add_unassigned_cut(per: str) -> list[str]:
        sh = sheet_of(per)
        u = sh.get("unassigned")
        if not u or not (u.get("cut") or {}).get(per):
            return []
        ids = []
        for i, ins in enumerate(INS):
            vid = f"ges.cut.{per}.sin_problema.{ins}"
            values[vid] = value(vid, unassigned_cut(per)[i] or 0, unit="casos acumulados desde jul-2005", period=per,
                                source=src, locator=f"{sh['sheet']}!fila {u['row']} (sin problema de salud informado) · "
                                                    f"{sh['titles']['cut:' + per]} · {ins.capitalize()}", kind=CUMULATIVE)
            ids.append(vid)
        return ids

    def dec_base(dec: str, year: int) -> list[str]:
        """Evidence ids of the December cut ``dec`` as the base of ``year``: the declared total when the problem list
        did not change, else the sum over the problems of ``year`` (a dropped problem keeps its cumulative in the
        December total but has no flow; a new one enters with 0)."""
        codes = years[str(year)]["problems"]
        own = [sum(((cut_pair(dec, c) or [0, 0])[i] or 0) for c in codes) + (unassigned_cut(dec)[i] or 0)
               for i in (0, 1)]
        if own == list(cut_pair(dec)):
            return add_cut(dec)
        ids = []
        for i, ins in enumerate(INS):
            parts = [x for c in codes if cut_pair(dec, c) is not None for x in add_problem_cut(dec, c) if x.endswith("." + ins)]
            parts += [x for x in add_unassigned_cut(dec) if x.endswith("." + ins)]
            ids.append(f"ges.cut.{dec}.base_{year}.{ins}")
            values[ids[-1]] = value(ids[-1], own[i], unit="casos acumulados desde jul-2005", period=dec, source=None,
                                    formula=f"Σ acumulado a {cut_label(dec)} de los problemas presentes en {year}"
                                            " y de los casos sin problema de salud informado",
                                    inputs=parts, kind=CUMULATIVE)
        return ids

    # Cuts never decrease: dic(t−2) ≤ mar(t−1) ≤ … ≤ dic(t−1) ≤ mar(t) ≤ … ≤ t (totals within a year; problems across).
    chain = [dec2] + [f"{ty - 1}-{m:02d}" for m in (3, 6, 9, 12)] + [f"{ty}-{m:02d}" for m in range(3, tm + 1, 3)]
    for a, c in zip(chain, chain[1:]):
        if a[:4] == c[:4]:
            ta, tc = cut_pair(a), cut_pair(c)
            if any(tc[i] < ta[i] for i in (0, 1)):
                failures.append(f"ytd_total_decreases:{c}")
        for code in sheet_of(c)["problems"]:
            pa, pc = cut_pair(a, code), cut_pair(c, code)
            if pa and pc and any((pc[i] or 0) < (pa[i] or 0) for i in (0, 1)):
                failures.append(f"ytd_row_decreases:{c}:{pkey(code)}")
                break
    # Year-to-date identity on the totals (defence in depth; the parser checks it per problem too).
    cur_sheet = years[str(ty)]
    ytd_t = cur_sheet["totals"]["ytd"][t]
    base_dec = [sum(((cut_pair(dec1, k) or [0, 0])[i] or 0) for k in cur_sheet["problems"])
                + (unassigned_cut(dec1)[i] or 0) for i in (0, 1)]
    if [cut_pair(t)[i] - base_dec[i] for i in (0, 1)] != list(ytd_t):
        failures.append(f"ytd_identity:{t}")
    if failures:
        package["reconciliation"]["ok"] = False
        package.update(findings=[], kpis={"invalid": invalid}, revisions=[], constants=[], periods=[t])
        return package

    # Year-to-date, current year: the SIS column 'Ingresos entre Ene y <mes> <año>'.
    for i, ins in enumerate(INS):
        vid = f"ges.ytd.{t}.{ins}"
        values[vid] = value(vid, ytd_t[i], unit="casos", period=t, source=src,
                            locator=f"{cur_sheet['sheet']}!fila {cur_sheet['total_row']} (Total) · {cur_sheet['titles']['ytd:' + t]} · {ins.capitalize()}")
    # Same months one year earlier, from the same workbook: acumulado(b) − acumulado(dic del año anterior a b).
    ins_b = add_cut(b), dec_base(dec2, by)
    for i, ins in enumerate(INS):
        derived(f"ges.ytd.{b}.{ins}", cut_pair(b)[i] - values[ins_b[1][i]]["value"],
                f"acumulado jul-2005 a {cut_label(b)} − acumulado jul-2005 a {cut_label(dec2)}",
                [ins_b[0][i], ins_b[1][i]], "casos", b)
    for per in (t, b):
        f, i_ = values[f"ges.ytd.{per}.fonasa"]["value"], values[f"ges.ytd.{per}.isapre"]["value"]
        derived(f"ges.ytd.{per}.total", f + i_, "Fonasa + Isapre", [f"ges.ytd.{per}.fonasa", f"ges.ytd.{per}.isapre"], "casos", per)
        derived(f"ges.ytd.{per}.isapre_share", i_ / (f + i_) * 100 if f + i_ else 0.0, "Isapre / (Fonasa + Isapre) × 100",
                [f"ges.ytd.{per}.isapre", f"ges.ytd.{per}.total"], "%", per)
    for ins in ("fonasa", "isapre", "total"):
        a, c = values[f"ges.ytd.{b}.{ins}"]["value"], values[f"ges.ytd.{t}.{ins}"]["value"]
        derived(f"ges.yoy.{ins}", c - a, "casos(ene–t) − casos(mismos meses del año anterior)", [f"ges.ytd.{t}.{ins}", f"ges.ytd.{b}.{ins}"], "casos", t)
        derived(f"ges.yoy.{ins}_pct", (c - a) / a * 100 if a else 0.0, "Δ / casos de los mismos meses del año anterior × 100",
                [f"ges.yoy.{ins}", f"ges.ytd.{b}.{ins}"], "%", t)
    derived("ges.yoy.isapre_share_pp", values[f"ges.ytd.{t}.isapre_share"]["value"] - values[f"ges.ytd.{b}.isapre_share"]["value"],
            "participación(t) − participación(mismos meses del año anterior)", [f"ges.ytd.{t}.isapre_share", f"ges.ytd.{b}.isapre_share"], "pp", t)

    # Quarters (trend): differences of cumulative cuts; T1 against December of the previous year.
    quarters: dict[tuple[int, int], dict] = {}
    for (y, q) in [(ty - 1, k) for k in (1, 2, 3, 4)] + [(ty, k) for k in range(1, tq + 1)]:
        cur, prv = qend(y, q), (f"{y - 1}-12" if q == 1 else qend(y, q - 1))
        ic, ip = add_cut(cur), (dec_base(prv, y) if q == 1 else add_cut(prv))
        k = qid(y, q)
        formula = f"acumulado a {cut_label(cur)} − acumulado a {cut_label(prv)}" + (" (T1: contra diciembre del año anterior)" if q == 1 else "")
        fl = [derived(f"ges.q.{k}.{ins}", cut_pair(cur)[i] - values[ip[i]]["value"], formula, [ic[i], ip[i]], "casos", cur)
              for i, ins in enumerate(INS)]
        derived(f"ges.q.{k}.total", fl[0] + fl[1], "Fonasa + Isapre", [f"ges.q.{k}.fonasa", f"ges.q.{k}.isapre"], "casos", cur)
        derived(f"ges.q.{k}.isapre_share", fl[1] / sum(fl) * 100 if sum(fl) else 0.0, "Isapre / (Fonasa + Isapre) × 100",
                [f"ges.q.{k}.isapre", f"ges.q.{k}.total"], "%", cur)
        quarters[(y, q)] = {"cuts": [prv, cur]}

    # Atypical quarters (Dirección 4-nov-2026): one insurer's quarter at ``ratio``× or more, or at 1/``ratio`` or less,
    # the median of its other quarters. The figures are the SIS's and stay in the charts; the SIS gives no reason, so
    # the ficha says so and never headlines a year-on-year comparison whose window contains one.
    aq = cfg["kpis"]["casos_ges"].get("atypical_quarter") or {}
    ratio_th = float(aq.get("ratio") or 0)
    qkeys = sorted(quarters)
    atypical: list[dict] = []
    if ratio_th > 1 and len(qkeys) >= int(aq.get("min_quarters") or 5):
        for ins in INS:
            for (y, q) in qkeys:
                rest = [(yy, qq) for (yy, qq) in qkeys if (yy, qq) != (y, q)]
                med = statistics.median(values[f"ges.q.{qid(yy, qq)}.{ins}"]["value"] for (yy, qq) in rest)
                x = values[f"ges.q.{qid(y, q)}.{ins}"]["value"]
                if med <= 0 or not (x >= ratio_th * med or x * ratio_th <= med):
                    continue
                k_ = qid(y, q)
                derived(f"ges.q.{k_}.{ins}.mediana_otros", med, "mediana de los casos de los demás trimestres del mismo seguro",
                        [f"ges.q.{qid(yy, qq)}.{ins}" for (yy, qq) in rest], "casos", qend(y, q))
                derived(f"ges.q.{k_}.{ins}.veces_mediana", x / med, "casos del trimestre / mediana de los demás trimestres",
                        [f"ges.q.{k_}.{ins}", f"ges.q.{k_}.{ins}.mediana_otros"], "x", qend(y, q))
                atypical.append({"y": y, "q": q, "ins": ins, "value": x, "median": med,
                                 "in_window": y in (by, ty) and q <= tq})
    contaminated = sorted({a["ins"] for a in atypical if a["in_window"]})

    # Problems: year-to-date t (SIS column) vs the same months one year earlier (difference of cuts).
    kpcfg = cfg["kpis"]
    tp = kpcfg["top_problemas"]["threshold"]
    cur_p, prev_sheet = cur_sheet["problems"], years[str(ty - 1)]["problems"]
    problems, added, dropped = [], [], []
    for code, p in cur_p.items():
        y_ = p["ytd"].get(t)
        if y_ is None:
            continue
        k = pkey(code)
        ids = []
        for i, ins in enumerate(INS):
            vid = f"ges.ytd.{t}.p.{k}.{ins}"
            values[vid] = value(vid, y_[i] or 0, unit="casos", period=t, source=src,
                                locator=f"{cur_sheet['sheet']}!fila {p['row']} (problema N°{p['code']}) · {cur_sheet['titles']['ytd:' + t]} · {ins.capitalize()}")
            ids.append(vid)
        row = {"key": k, "code": p["code"], "label": p["label"], "t": derived(f"ges.p.{k}.ytd.{t}", (y_[0] or 0) + (y_[1] or 0),
                                                                              "Fonasa + Isapre del problema (columna de ingresos del año)", ids, "casos", t)}
        if cut_pair(b, code) is not None:
            base_in = add_problem_cut(b, code) + (add_problem_cut(dec2, code) if cut_pair(dec2, code) is not None else [])
            bv = sum(((cut_pair(b, code)[i] or 0) - ((cut_pair(dec2, code) or [0, 0])[i] or 0)) for i in (0, 1))
            row["base"] = derived(f"ges.p.{k}.ytd.{b}", bv, f"Fonasa + Isapre del problema: acumulado a {cut_label(b)} − acumulado a "
                                  f"{cut_label(dec2)} (0 si el problema no existía)", base_in, "casos", b)
            if bv >= tp["min_cases"]:
                # rounded to one decimal: the chart shows exactly this value
                row["pct"] = derived(f"ges.p.{k}.yoy_pct", round((row["t"] - bv) / bv * 100, 1),
                                     "redondeo(Δ / casos de los mismos meses del año anterior × 100, 1)",
                                     [f"ges.p.{k}.ytd.{t}", f"ges.p.{k}.ytd.{b}"], "%", t)
        else:
            added.append(k)
        problems.append(row)
    dropped = sorted(pkey(c) for c in prev_sheet if c not in cur_p and cut_pair(b, c) is not None)
    added = sorted(added)
    comp = [r for r in problems if "base" in r]
    # Cases with no health problem informed are in both periods' totals: they belong to the comparable total too, so
    # the gap to the total is only the decree's added / dropped problems (as the dek says).
    ua_t = sum((unassigned_cut(t)[i] or 0) - (unassigned_cut(dec1)[i] or 0) for i in (0, 1))
    ua_b = sum((unassigned_cut(b)[i] or 0) - (unassigned_cut(dec2)[i] or 0) for i in (0, 1))
    cf, cb = sum(r["t"] for r in comp) + ua_t, sum(r["base"] for r in comp) + ua_b
    comp_f = "Σ casos de los problemas presentes en ambos períodos + casos sin problema de salud informado"
    derived(f"ges.ytd.{t}.total_comparable", cf, comp_f, [f"ges.ytd.{t}.total"], "casos", t)
    derived(f"ges.ytd.{b}.total_comparable", cb, comp_f, [f"ges.ytd.{b}.total"], "casos", b)
    derived("ges.yoy.total_comparable_pct", (cf - cb) / cb * 100 if cb else 0.0, "Δ comparable / base comparable × 100",
            [f"ges.ytd.{t}.total_comparable", f"ges.ytd.{b}.total_comparable"], "%", t)
    derived("ges.list.added", len(added), "problemas solo en el período actual", [], "count", t)
    derived("ges.list.dropped", len(dropped), "problemas solo en el período base", [], "count", t)
    findings: list[dict] = []
    th = kpcfg["casos_ges"]["threshold"]["yoy_pct"]
    if abs(values["ges.yoy.total_pct"]["value"]) >= th and not contaminated:
        findings.append({"type": "threshold_crossed", "kpi": "casos_ges", "crossed": True,
                         "strength": abs(values["ges.yoy.total_pct"]["value"]) / th})
    ranked = sorted((r for r in problems if "pct" in r), key=lambda r: (-r["pct"], r["label"]))
    crossing = [r for r in ranked if r["pct"] >= tp["pct"]]
    derived("conteo.problemas_sobre_umbral", len(crossing), "problemas con Δ a/a ≥ umbral y base ≥ mínimo", [], "count", t)
    derived("conteo.problemas_bajan", sum(1 for r in ranked if r["pct"] < 0), "problemas comparables con Δ a/a < 0", [], "count", t)
    lead = None
    if contaminated and problems:
        r = sorted(problems, key=lambda r: (-r["t"], r["label"]))[0]
        tot_t = values[f"ges.ytd.{t}.total"]["value"]
        derived(f"ges.p.{r['key']}.share_ytd.{t}", r["t"] / tot_t * 100 if tot_t else 0.0,
                "casos del problema / casos GES totales del período × 100", [f"ges.p.{r['key']}.ytd.{t}", f"ges.ytd.{t}.total"], "%", t)
        lead = {"key": r["key"], "label": r["label"], "share_id": f"ges.p.{r['key']}.share_ytd.{t}"}
    if crossing:
        findings.append({"type": "problem_growth", "kpi": "top_problemas", "crossed": True, "strength": len(crossing)})

    # Crude rates per 1.000 beneficiaries of the same insurer over the same months: Isapre from F1; Fonasa not captured.
    port = _portfolio_isapre(root)
    rates = {}
    for per in (b, t):
        y, m = sf.period_parts(per)
        months = months_of(y, m)
        if not (port and all(x in port["totals"] for x in months)):
            continue
        sources.setdefault("cartera", sf.source_ref(
            url=port["url"], sha256=port["sha256"], published_at=port["published_at"], fetched_at=port["fetched_at"],
            label="SIS · Cartera mensual de beneficiarios Isapre (xlsx), ficha F1",
            role="denominador de la tasa Isapre: beneficiarios al cierre de cada mes", locator="fila Total Sistema"))
        for x in months:
            values[f"cartera.isapre.{x}"] = value(f"cartera.isapre.{x}", port["totals"][x], unit="beneficiarios",
                                                  period=x, source="cartera", locator="Total Sistema")
        avg = derived(f"benef.isapre.avg.ytd.{per}", sum(port["totals"][x] for x in months) / len(months),
                      f"promedio de los {len(months)} stocks de cierre de mes de enero a {mname(m)}",
                      [f"cartera.isapre.{x}" for x in months], "beneficiarios", per)
        rates[per] = derived(f"ges.ytd.{per}.isapre_rate", values[f"ges.ytd.{per}.isapre"]["value"] / avg * 1000,
                             "casos Isapre de enero al corte / beneficiarios Isapre promedio del mismo período × 1.000",
                             [f"ges.ytd.{per}.isapre", f"benef.isapre.avg.ytd.{per}"], "per_1000", per)

    # The same months one year earlier as published in that year's own release (its YTD column), if captured: a
    # cross-check only (the SIS revises late registrations); the ficha uses the newest workbook.
    cross = None
    old, why = _release_state(releases.get(b) or {})
    if old and not why:
        col = gw.expand_sheet(old["years"][str(by)])["totals"]["ytd"].get(b)
        if col:
            cross = {"release": b, "equal": list(col) == [values[f"ges.ytd.{b}.{ins}"]["value"] for ins in INS]}
    package["reconciliation"]["cross_release"] = cross

    # Label digits ('Diabetes Mellitus Tipo 2') are captured text, not figures: they may be shown.
    label_numbers = sorted({abs(v) for r in problems for _, v, _ in numbers_in(r["label"])})
    # An atypical quarter inside the current period makes the period's own figures (and any headline on them)
    # suspect; with no alternative headline the comparison would lead. Either way a human decides (HOLD).
    failures += atypical_holds(atypical, ty, lead)
    if failures:
        package["reconciliation"]["ok"] = False
    # Problem numbers quoted from the SIS 'Notas' sheet (n5) are captured text, like label digits.
    note_numbers = sorted({abs(v) for text in sis_notes_said(parse.get("notes") or []) for _, v, _ in numbers_in(text)})
    constants = ([1000, th, tp["pct"], tp["min_cases"], len(quarters), *label_numbers, *note_numbers]
                 + ([ratio_th] if atypical else []))
    values["regla.top_problemas.pct"] = value("regla.top_problemas.pct", tp["pct"], unit="%", period=t, source=None,
                                              formula="umbral del registro (top_problemas)", kind="rule")
    values["conteo.trimestres"] = value("conteo.trimestres", len(quarters), unit="trimestres", period=t, source=None,
                                        formula="conteo de trimestres derivables", kind="derived")
    package.update(period=t, periods=sorted(set(months_of(by, tm) + months_of(ty, tm))), base_period=b, findings=findings,
                   revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
                   constants=constants,
                   kpis={"t": (ty, tm), "b": (by, tm), "tq": (ty, tq), "quarters": sorted(quarters),
                         "quarter_cuts": {qid(*k): v["cuts"] for k, v in quarters.items()}, "rates": rates,
                         "problems": problems, "ranked": ranked, "crossing": crossing, "added": added, "dropped": dropped,
                         "measure": "ytd", "measure_how": how, "invalid": invalid, "sis_notes": parse.get("notes") or [],
                         "cross_release": cross, "atypical": atypical, "yoy_contaminated": contaminated,
                         "atypical_ratio": ratio_th, "lead": lead})
    _lectura_material(package, values)
    return package


def _lectura_material(package: dict, values: dict) -> None:
    k = package["kpis"]
    (ty, tm), (by, _) = k["t"], k["b"]
    t, b = f"{ty}-{tm:02d}", f"{by}-{tm:02d}"
    Y = {"periods": months_of(ty, tm), "period_kind": "ytd", "requires_period": True}
    P = lambda vid, **kw: sf.pool_entry(values, vid, **kw) if vid in values else None  # noqa: E731
    pool = [P(f"ges.ytd.{t}.total", metric="casos", signed=False, scope="system", **Y),
            P(f"ges.ytd.{t}.fonasa", metric="casos", signed=False, scope="insurer:fonasa", **Y),
            P(f"ges.ytd.{t}.isapre", metric="casos", signed=False, scope="isapres", **Y),
            P(f"ges.ytd.{t}.isapre_share", signed=False, scope="isapres", base="casos_ambos_seguros", **Y),
            P(f"ges.ytd.{t}.isapre_rate", signed=False, scope="isapres", base="beneficiarios_mismo_seguro", **Y)]
    YY = {"periods": months_of(by, tm) + months_of(ty, tm), "period_kind": "ytd", "requires_period": True}
    pool += [P(f"ges.yoy.{ins}", metric="casos", scope=sc, **YY) for ins, sc in
             (("total", "system"), ("fonasa", "insurer:fonasa"), ("isapre", "isapres"))]
    pool += [P(f"ges.yoy.{ins}_pct", scope=sc, base="casos_mismo_periodo_anio_anterior", **YY) for ins, sc in
             (("total", "system"), ("fonasa", "insurer:fonasa"), ("isapre", "isapres"))]
    pool += [P("ges.yoy.isapre_share_pp", scope="isapres", base="casos_ambos_seguros", **YY),
             P(f"ges.ytd.{b}.total", metric="casos", signed=False, scope="system", periods=months_of(by, tm),
               period_kind="ytd", requires_period=True)]
    bad = k.get("yoy_contaminated") or []
    if bad:  # a comparison whose window holds an atypical quarter is never offered to the Lectura
        drop = {f"ges.yoy.{x}" for x in ("total", "isapre_share_pp", *bad)} | {f"ges.yoy.{x}_pct" for x in ("total", *bad)}
        drop.add(f"ges.ytd.{b}.total")
        pool = [e for e in pool if e and e["id"] not in drop]
    package["lectura_pool"] = [e for e in pool if e]
    ratios = []
    f, i = values[f"ges.ytd.{t}.fonasa"]["value"], values[f"ges.ytd.{t}.isapre"]["value"]
    if i:
        ratios.append({"id": "ratio.fonasa_por_isapre", "value": f / i, "unit": "x", "entity": None, "signed": False,
                       "periods": months_of(ty, tm), "requires_period": False, "formula": "casos Fonasa / casos Isapre",
                       "inputs": [f"ges.ytd.{t}.fonasa", f"ges.ytd.{t}.isapre"], "scope": "insurer:fonasa",
                       "period_kind": "ytd", "trivial": False, "base": None})
    ratios.append({"id": "conteo.problemas_sobre_umbral", "value": len(k["crossing"]), "unit": "count", "entity": None,
                   "signed": False, "periods": months_of(ty, tm), "requires_period": False, "formula": "conteo",
                   "inputs": [], "scope": "system", "period_kind": "ytd", "trivial": True})
    package["derived_ratios"] = ratios
    package["ranks"] = []


# ---------------------------------------------------------------------------------------------
# Ficha composition


SIS_NOTE_RULES = (  # (pattern in the captured 'Notas' sheet, the ficha's paraphrase, group); shown only when the note
    # is there, and only the first matching rule of each group. Dirección 4-nov-2026: the deletion note names the
    # problems (and years) it covers, so it is never read as explaining other changes.
    (r"solicitudes de acceso", "desde julio de 2012 la fuente es el archivo de solicitudes de acceso a las GES", "fuente"),
    (r"no incorpora casos de vih", "Fonasa no informa casos de VIH anteriores a 2014", "vih"),
    (r"a partir del ano 2021,? las diferencias en el problema 57,? se deben a la eliminacion de casos",
     "desde 2021, las diferencias en el problema 57 se deben a que una Isapre eliminó casos del archivo", "p57"),
    (r"problema 57,? se deben a la eliminacion de casos",
     "las diferencias en el problema 57 se deben a que una Isapre eliminó casos del archivo", "p57"),
    (r"problema 11,? para diciembre del 2022,? se deben a la eliminacion de casos",
     "las del problema 11 en diciembre de 2022 también se deben a que una Isapre eliminó casos del archivo", "p11"),
    # A reworded deletion note that no rule above reads keeps the generic paraphrase (never silently dropped).
    (r"eliminacion de casos", "algunas diferencias en problemas de salud puntuales se deben a que una Isapre eliminó casos del "
                              "archivo", "elim"),
)


def atypical_holds(atypical: list[dict], ty: int, lead: dict | None) -> list[str]:
    """HOLD reasons from the atypical quarters: one inside the current period makes the period's own figures (and any
    headline on them) suspect; a contaminated comparison with no alternative headline would lead. A human decides."""
    cur = [a for a in atypical if a["in_window"] and a["y"] == ty]
    if cur:
        return ["atypical_quarter_current_period:" + ",".join(f"{qid(a['y'], a['q'])}.{a['ins']}" for a in cur)]
    if any(a["in_window"] for a in atypical) and lead is None:
        return ["atypical_quarter_no_alternative_headline"]
    return []


def sis_notes_said(notes: list[str]) -> list[str]:
    folded = _fold(" ".join(notes or []))
    taken: dict[str, str] = {}
    for rx, text, group in SIS_NOTE_RULES:
        if group in taken:
            continue
        if group == "elim":
            # Only when the note has more deletion sentences than the specific rules read (a new problem named).
            if len(re.findall(rx, folded)) <= len({"p57", "p11"} & set(taken)):
                continue
        if re.search(rx, folded):
            taken[group] = text
    return list(taken.values())


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    v = package["values"]
    k = package["kpis"]
    (ty, tm), (by, _) = k["t"], k["b"]
    t, b = f"{ty}-{tm:02d}", f"{by}-{tm:02d}"
    val = lambda vid: v[vid]["value"]  # noqa: E731
    total, fon, isa = val(f"ges.ytd.{t}.total"), val(f"ges.ytd.{t}.fonasa"), val(f"ges.ytd.{t}.isapre")
    share = val(f"ges.ytd.{t}.isapre_share")
    rate = k["rates"].get(t)
    pct = lambda vid: fmt_dec(val(vid), 1, signed=True) + "%"  # noqa: E731
    list_changed = bool(k["added"] or k["dropped"])
    yoy_th = fmt_dec(cfg["kpis"]["casos_ges"]["threshold"]["yoy_pct"], 0)  # registry threshold, never hard-coded
    st, sb = short(ty, tm), short(by, tm)
    words = {"mes": mname(tm), "anio": ty, "anio_base": by, "periodo": span(ty, tm), "periodo_base": span(by, tm),
             "entre": between(ty, tm), "entre_base": between(by, tm), "corto": st, "corto_base": sb}

    bad = k.get("yoy_contaminated") or []
    atyp = [a for a in k.get("atypical") or [] if a["in_window"]]
    alt = next(i for i in INS if i not in bad) if len(bad) == 1 else None
    insw = {"fonasa": "Fonasa", "isapre": "Isapres"}
    if bad and k.get("lead"):
        # Dirección 4-nov-2026: with an atypical quarter in the comparison window the headline is another finding.
        lead = k["lead"]
        headline = tpl["headline_atypical"].format(problema=lead["label"], share=fmt_dec(val(lead["share_id"]), 1),
                                                   total=fmt_int(total), **words)
        headline_type = "ytd_lead_problem"
    else:
        headline = tpl["headline"].format(total=fmt_int(total), yoy=pct("ges.yoy.total_pct"), **words)
        headline_type = "ytd_yoy"
    who = lambda a: "Fonasa" if a["ins"] == "fonasa" else "las Isapres"  # noqa: E731
    join = lambda xs: ", ".join(xs[:-1]) + " y " + xs[-1] if len(xs) > 1 else (xs[0] if xs else "")  # noqa: E731
    atyp_ref = join([f"el {qlabel(a['y'], a['q'])} de {who(a)}" for a in atyp])
    atyp_short = join([f"el {qshort(a['y'], a['q'])} de {who(a)}" for a in atyp])
    es_atipico = "es atípico" if len(atyp) == 1 else "son atípicos"
    # Fonasa has no rate (no beneficiaries captured): said in its KPI card and in the notes, not in the 40-word dek.
    rate_clause = (f" Tasa bruta Isapre: {fmt_dec(rate, 1)} casos de enero a {mname(tm)} de {ty} por 1.000 beneficiarios."
                   if rate is not None else " Sin tasas por beneficiario para este período.")
    na, nd = len(k["added"]), len(k["dropped"])
    pl = lambda n, one, many: f"{fmt_int(n)} {one if n == 1 else many}"  # noqa: E731
    comparable = pct("ges.yoy.total_comparable_pct")
    decree_clause = ("" if not (na or nd) else
                     f" La variación incluye {pl(na, 'problema nuevo', 'problemas nuevos')} por decreto; comparable: {comparable}."
                     if na and not nd else
                     # A dropped problem has no flow this year but stays in last year's base (review of #129).
                     f" La base de {span(by, tm)} incluye {pl(nd, 'problema retirado', 'problemas retirados')}; "
                     f"comparable: {comparable}."
                     if nd and not na else
                     f" Cambio de decreto: {pl(na, 'problema nuevo', 'problemas nuevos')}; la base {by} incluye "
                     f"{pl(nd, 'retirado', 'retirados')}; comparable: {comparable}.")
    if bad:
        # The rate stays in its topic: the dek keeps to 40 words.
        rate_clause = ""
        lead_in = (f" {atyp_short[0].upper() + atyp_short[1:]} {es_atipico}" if len(atyp) == 1 else
                   " Hay trimestres atípicos" + (" de ambos seguros" if len(bad) == 2 else ""))  # dek ≤ 40 words
        decree_clause = (f"{lead_in} en los datos SIS"
                         + (f"; {insw[alt]}: {pct(f'ges.yoy.{alt}_pct')} a/a." if alt else "."))
        if headline_type == "ytd_lead_problem" and re.search(SIS_NOTE_RULES[0][0], _fold(" ".join(k.get("sis_notes") or []))):
            # The SIS counts access requests (its own note): a reader must not read the lead problem as diagnoses.
            decree_clause += " Cada caso es una solicitud de acceso a la GES."
    dek = tpl["dek"].format(fonasa=fmt_int(fon), isapre=fmt_int(isa), share=fmt_dec(share, 1), rate_clause=rate_clause,
                            decree_clause=decree_clause, **words)
    crossed = any(f["kpi"] == "casos_ges" for f in package["findings"])

    kpis = [{"id": "casos", "label": tpl["kpi_label"].format(**words), "value": fmt_int(total), "prov": "C",
             "lines": [f"{pct('ges.yoy.total_pct')} vs. {sb}"]
             + ([f"{pct('ges.yoy.total_comparable_pct')} solo problemas comparables"] if list_changed else []),
             "badge": ("Comparación con un trimestre atípico" if bad else
                       f"Cruza umbral ({yoy_th}% a/a)" if crossed else "Sin umbral cruzado"),
             "badge_kind": "crossed" if crossed else "muted",
             "refs": [f"ges.ytd.{t}.total", "ges.yoy.total_pct"]},
            {"id": "fonasa", "label": f"Fonasa {st}", "value": fmt_int(fon), "prov": "C",
             "lines": [f"{pct('ges.yoy.fonasa_pct')} vs. {sb}", "tasa no disponible (sin beneficiarios capturados)"],
             **({"badge": "Comparación con un trimestre atípico", "badge_kind": "muted"} if "fonasa" in bad else {}),
             "refs": [f"ges.ytd.{t}.fonasa"]},
            {"id": "isapre", "label": f"Isapres {st}", "value": fmt_int(isa), "prov": "C",
             "lines": [f"{pct('ges.yoy.isapre_pct')} vs. {sb}", f"{fmt_dec(share, 1)}% de los casos de ambos seguros"],
             **({"badge": "Comparación con un trimestre atípico", "badge_kind": "muted"} if "isapre" in bad else {}),
             "refs": [f"ges.ytd.{t}.isapre", f"ges.ytd.{t}.isapre_share"]},
            {"id": "tasa", "label": "Tasa bruta Isapre", "value": fmt_dec(rate, 1) if rate is not None else "no disponible",
             "prov": "C" if rate is not None else None,
             "lines": ([f"casos {st} por 1.000 beneficiarios Isapre", "tasa a/a no disponible" if b not in k["rates"] else
                        f"{sb}: {fmt_dec(k['rates'][b], 1)}"] if rate is not None
                       else ["sin beneficiarios del período capturados"]),
             "refs": [f"ges.ytd.{t}.isapre_rate"] if rate is not None else []}]

    # Tab 1 · Totales (year-to-date vs the same months one year earlier)
    tabs = []
    rows = [{"label": lab, "value": val(f"ges.ytd.{t}.{ins}"), "ref": f"ges.ytd.{t}.{ins}",
             "base": val(f"ges.ytd.{b}.{ins}"), "base_ref": f"ges.ytd.{b}.{ins}"}
            for lab, ins in (("Total", "total"), ("Fonasa", "fonasa"), ("Isapres", "isapre"))]
    c_tot = {"id": "f4-totales", "form": "dots", "digits": 0, "unit": "casos",
             "headline": f"Casos de {st} frente a {sb}",
             "subtitle": f"Casos GES ingresados por seguro · punto = {st}, aro = {sb}", "rows": rows,
             "table": {"columns": ["Seguro", sb, st, "a/a"],
                       "rows": [[r["label"], fmt_int(r["base"]), fmt_int(r["value"]),
                                 pct(f"ges.yoy.{ins}_pct")] for r, ins in zip(rows, ("total", "fonasa", "isapre"))]},
             "source": (f"SIS, casos GES ingresados {between(ty, tm)} (columna de ingresos del año); {span(by, tm)}, por "
                        "diferencia entre cortes acumulados de la misma planilla.")}
    d = val("ges.yoy.total")
    tot_text = [f"{between(ty, tm).capitalize()} Fonasa e Isapres informaron {fmt_int(total)} casos GES, "
                f"{fmt_int(abs(d))} {'más' if d >= 0 else 'menos'} que {between(by, tm)} ({pct('ges.yoy.total_pct')})."]
    if list_changed:
        tot_text.append(f"Con solo los problemas presentes en ambos períodos la variación es {pct('ges.yoy.total_comparable_pct')}: "
                        "la lista de problemas cambió entre ambos años (posible cambio de decreto GES).")
    atyp_sentences = []
    for a in atyp:
        kq = qid(a["y"], a["q"])
        ratio_id = f"ges.q.{kq}.{a['ins']}.veces_mediana"
        win = span(by, tm) if a["y"] == by else span(ty, tm)
        tot_text.append(f"El período {win} incluye el {qlabel(a['y'], a['q'])} de {'Fonasa' if a['ins'] == 'fonasa' else 'las Isapres'}, "
                        f"atípico en los datos SIS: {fmt_int(a['value'])} casos, "
                        f"{fmt_dec(val(ratio_id), 1)} veces la mediana de los demás trimestres "
                        f"({fmt_int(half_up(a['median']))}).")
        atyp_sentences.append(tot_text[-1])
    if atyp:
        tot_text[-1] += " La SIS no informa el motivo."
        atyp_sentences[-1] = tot_text[-1]
    if alt:
        tot_text.append(f"Solo {insw[alt]}: {pct(f'ges.yoy.{alt}_pct')} frente a {span(by, tm)}.")
    tabs.append({"id": "totales", "label": "Totales", "charts": [c_tot], "text": tot_text})

    # Tab 2 · Top problemas
    tp = cfg["kpis"]["top_problemas"]["threshold"]
    # The 'crecen' ranking shows growth only: a decline is never drawn as a positive bar (it is counted in the text).
    growing = [r for r in k["ranked"] if r["pct"] > 0]
    declining = [r for r in k["ranked"] if r["pct"] < 0]
    ranked = growing[:MAX_PROBLEM_ROWS]
    if ranked:
        n = len(k["crossing"])
        # The count word comes from the data (conteo.problemas_sobre_umbral), never from a template.
        phrase = "Un problema supera" if n == 1 else sf.count_phrase(n, "", "problemas superan").strip().capitalize()
        head = f"{phrase} {fmt_dec(tp['pct'], 0)}% a/a" if n else "Ningún problema supera el umbral de crecimiento"
        c_top = {"id": "f4-top", "form": "bars", "unit": "%", "digits": 1, "headline": head,
                 "subtitle": f"Problemas que crecen: variación de {st} frente a {sb} · base ≥ {fmt_int(tp['min_cases'])} casos en {sb}",
                 "rows": [{"label": short_label(r["label"]), "value": r["pct"], "ref": f"ges.p.{r['key']}.yoy_pct",
                           "emphasis": r["pct"] >= tp["pct"]} for r in ranked],
                 "table": {"columns": ["Problema de salud", sb, st, "a/a"],
                           "rows": [[r["label"], fmt_int(r["base"]), fmt_int(r["t"]), fmt_dec(r["pct"], 1, signed=True) + "%"] for r in ranked]},
                 "source": "SIS, casos GES por problema (Fonasa + Isapre). Solo problemas presentes en ambos períodos."}
        top_text = [f"Se ordenan los problemas que crecen, con al menos {fmt_int(tp['min_cases'])} casos {between(by, tm)}; "
                    f"cruzan el umbral los que crecen {fmt_dec(tp['pct'], 0)}% o más."]
        if declining:
            top_text.append(("Un problema comparable bajó" if len(declining) == 1 else
                             sf.count_phrase(len(declining), "", "problemas comparables bajaron").strip().capitalize())
                            + f" frente a {sb}; no se grafican en este ranking de crecimiento.")
    else:
        biggest = sorted(k["problems"], key=lambda r: (-r["t"], r["label"]))[:MAX_PROBLEM_ROWS]
        c_top = {"id": "f4-top", "form": "bars", "unit": "casos", "headline": f"Problemas con más casos en {st}",
                 "subtitle": f"Casos GES por problema, {st} (Fonasa + Isapre)",
                 "rows": [{"label": short_label(r["label"]), "value": r["t"], "ref": f"ges.p.{r['key']}.ytd.{t}"} for r in biggest],
                 "table": {"columns": ["Problema de salud", st], "rows": [[r["label"], fmt_int(r["t"])] for r in biggest]},
                 "source": "SIS, casos GES por problema."}
        top_text = [f"Ningún problema comparable crece frente a {sb}; se muestran los problemas con más casos."]
    if list_changed:
        top_text.append(f"La lista de problemas cambió entre {sb} y {st} (posible cambio de decreto GES). Problemas sin base "
                        f"comparable: {fmt_int(len(k['added']))}; que ya no aparecen: {fmt_int(len(k['dropped']))}. No entran al ranking.")
    if bad and ranked:
        top_text.append(f"La base por problema incluye {atyp_ref}, {'atípico' if len(atyp) == 1 else 'atípicos'} en los "
                        "datos SIS: las variaciones por problema pueden estar distorsionadas.")
    tabs.append({"id": "problemas", "label": "Top problemas", "charts": [c_top], "text": top_text})

    # Tab 3 · Fonasa vs Isapre
    qs = k["quarters"]
    c_share = {"id": "f4-share", "form": "line", "unit": "%", "digits": 1, "headline": "Parte Isapre de los casos GES por trimestre",
               "subtitle": "% de los casos informados por Fonasa e Isapres en cada trimestre",
               "rows": [{"label": qshort(y, q), "value": val(f"ges.q.{qid(y, q)}.isapre_share"), "ref": f"ges.q.{qid(y, q)}.isapre_share",
                         "emphasis": (y, q) == tuple(k["tq"])} for (y, q) in qs[-12:]],
               "table": {"columns": ["Trimestre", "Fonasa", "Isapres", "% Isapre"],
                         "rows": [[qshort(y, q), fmt_int(val(f"ges.q.{qid(y, q)}.fonasa")), fmt_int(val(f"ges.q.{qid(y, q)}.isapre")),
                                   fmt_dec(val(f"ges.q.{qid(y, q)}.isapre_share"), 1) + "%"] for (y, q) in qs[-12:]]},
               "source": "Denominador: casos de ambos seguros del mismo trimestre. No es participación de beneficiarios."}
    ins_charts = [c_share] if len(qs) >= 2 else []
    if k["rates"]:
        rp = sorted(k["rates"])
        ins_charts.append({"id": "f4-tasa", "form": "bars", "unit": "por 1.000", "digits": 1,
                           "headline": f"Tasa bruta Isapre, {span(ty, tm).split(' de ')[0]}",
                           "subtitle": "Casos Isapre por 1.000 beneficiarios Isapre (promedio de los cierres de mes del período)",
                           "rows": [{"label": short(*sf.period_parts(p)), "value": k["rates"][p], "ref": f"ges.ytd.{p}.isapre_rate",
                                     "emphasis": p == t} for p in rp],
                           "table": {"columns": ["Período", "Casos Isapre", "Beneficiarios promedio", "Tasa bruta"],
                                     "rows": [[short(*sf.period_parts(p)), fmt_int(val(f"ges.ytd.{p}.isapre")),
                                               fmt_int(half_up(val(f"benef.isapre.avg.ytd.{p}"))), fmt_dec(k["rates"][p], 1)] for p in rp]},
                           "source": "Beneficiarios: cartera mensual Isapre (ficha F1). Tasa bruta: sin ajuste por edad ni sexo; cuenta casos, no personas."})
    ins_text = [f"Las Isapres informaron el {fmt_dec(share, 1)}% de los casos {between(ty, tm)}; es una parte de los casos, "
                "no de la población."]
    ins_text.append(f"Tasa bruta Isapre {between(ty, tm)}: {fmt_dec(rate, 1)} casos por 1.000 beneficiarios Isapre. Fonasa: tasa no "
                    "disponible, porque Alicanto no tiene capturados sus beneficiarios." if rate is not None else
                    "Tasa por beneficiario no disponible: faltan los beneficiarios Isapre del período y Alicanto no captura los de Fonasa.")
    for a in k.get("atypical") or []:
        ins_text.append(f"El {qshort(a['y'], a['q'])} de {who(a)} es atípico en los datos SIS (ver Totales).")
    tabs.append({"id": "seguros", "label": "Fonasa vs Isapre", "charts": ins_charts[:2], "text": ins_text})

    # Tab 4 · Tendencia trimestral (quarters by difference of cumulative cuts)
    cuts = k["quarter_cuts"]
    c_trend = {"id": "f4-trend", "form": "line", "unit": "casos", "digits": 0, "headline": "Casos GES por trimestre",
               "subtitle": "Fonasa + Isapre, casos de cada trimestre",
               "rows": [{"label": qshort(y, q), "value": val(f"ges.q.{qid(y, q)}.total"), "ref": f"ges.q.{qid(y, q)}.total",
                         "emphasis": (y, q) == tuple(k["tq"])} for (y, q) in qs[-12:]],
               "table": {"columns": ["Trimestre", "Casos", "Cortes usados"],
                         "rows": [[qshort(y, q), fmt_int(val(f"ges.q.{qid(y, q)}.total")),
                                   " − ".join(cut_label(c) for c in reversed(cuts[qid(y, q)]))] for (y, q) in qs[-12:]]},
               "source": "SIS, casos GES. Cada trimestre es la diferencia entre dos cortes acumulados; el primero, contra diciembre del año anterior."}
    trend_text = [f"La serie tiene {fmt_int(len(qs))} trimestres, calculados por diferencia entre cortes acumulados de la planilla."]
    tabs.append({"id": "tendencia", "label": "Tendencia trimestral", "charts": [c_trend], "text": trend_text})

    # Index → topic layout (Dirección 29-oct): generic index fields; the topic dek falls back to the tab text.
    index_refs = {"problemas": ["regla.top_problemas.pct"], "tendencia": ["conteo.trimestres"],
                  "seguros": [f"ges.ytd.{t}.isapre_share"], "totales": [f"ges.ytd.{t}.total", "ges.yoy.total"]}
    for tab in tabs:
        refs = index_refs.get(tab["id"], [])
        sf.topic_fields(tab, text_refs=refs, headline_refs=refs)
    paragraphs = [" ".join([tot_text[0], *atyp_sentences]), ins_text[0], top_text[0]]

    # Qué mirar
    published = date.fromisoformat(package["published_at"][:10])
    expected = date.fromordinal(published.toordinal() + int(cfg["calendar"]["expected_release_interval_days"]))
    ny, nq = qprev(*k["tq"], -1)
    late = (decision or {}).get("late_release")
    watch = [{"headline": f"Casos GES a {sf.month_label(qend(ny, nq))}: publicación atrasada." if late else
              f"Casos GES a {sf.month_label(qend(ny, nq))} (la SIS la publicaría hacia el {sf.day_label(expected)}).",
              "explanation": (f"Lleva {late['days_late']} días de atraso según el calendario histórico." if late else
                              f"Una variación de {yoy_th}% o más frente a los mismos meses del año anterior marca la ficha como destacada.")}]
    if k["crossing"]:
        r = k["crossing"][0]
        watch.append({"headline": f"{short_label(r['label'], 60)}: {fmt_dec(r['pct'], 1, signed=True)}% a/a.",
                      "explanation": ("La base incluye un trimestre atípico de los datos SIS: la variación puede estar distorsionada."
                                      if bad else "Un salto en un problema puede venir de un cambio de decreto o de registro; "
                                      "la ficha no infiere la causa.")})
    else:
        watch.append({"headline": "Tasa Fonasa por beneficiario.",
                      "explanation": "Se calculará cuando Alicanto capture los beneficiarios de Fonasa del mismo período."})

    notes = [
        {"id": "n1", "text": ("Medida (definida por Dirección): casos GES ingresados entre enero y el mes del corte, frente a los "
                              "mismos meses del año anterior. Es un flujo, no un stock: los cortes no se suman. La planilla SIS "
                              "también informa casos acumulados desde julio de 2005; esa cifra no se muestra, solo se resta: "
                              "los mismos meses del año anterior y cada trimestre son la diferencia entre dos cortes acumulados "
                              "(el primer trimestre, contra diciembre del año anterior).")},
        {"id": "n2", "text": ("Tasa bruta: casos del seguro entre enero y el corte / beneficiarios promedio del mismo seguro en esos "
                              "meses × 1.000. Cuenta casos, no personas: una persona puede tener más de un caso GES. El denominador "
                              "Isapre viene de la cartera mensual (F1); Fonasa no tiene denominador capturado y su tasa no está "
                              "disponible. Sin ajuste por edad: no compara riesgo entre seguros.")},
        {"id": "n3", "text": (f"Top problemas: variación frente a los mismos meses del año anterior; entran los problemas con al menos "
                              f"{fmt_int(tp['min_cases'])} casos en la base y cruzan el umbral los que crecen {fmt_dec(tp['pct'], 0)}% o más. "
                              "Los problemas se comparan por su número GES.")},
        {"id": "n4", "text": "Ningún dato de esta ficha establece por qué cambian los casos (demanda, decreto, registro o acceso)."},
    ]
    said = sis_notes_said(k.get("sis_notes") or [])
    if said:
        notes.append({"id": "n5", "text": "Según las notas de la SIS: " + "; ".join(said) + "."})
    if k.get("cross_release") is not None:
        notes.append({"id": "n6", "text": (f"{span(by, tm).capitalize()} se calcula con la planilla más reciente. "
                                           + ("Coincide con lo publicado en la planilla de ese período." if k["cross_release"]["equal"] else
                                              "Difiere de lo publicado en la planilla de ese período: la SIS revisa sus datos."))})
    if k.get("atypical"):
        notes.append({"id": "n8", "text": (
            f"Trimestre atípico (regla del registro): un trimestre de un seguro con {fmt_dec(k['atypical_ratio'], 0)} veces o más, "
            "o la mitad o menos, la mediana de sus demás trimestres. Se muestran los datos tal como los publica la SIS, que no "
            "informa el motivo: " + "; ".join(
                f"{'Fonasa' if a['ins'] == 'fonasa' else 'Isapres'} {qshort(a['y'], a['q'])}: {fmt_int(a['value'])} casos, mediana "
                f"de los demás {fmt_int(half_up(a['median']))}" for a in k["atypical"])
            + (". Por eso el titular no usa la comparación con " + span(by, tm) + "." if headline_type == "ytd_lead_problem" else "."))})
    if k["invalid"]:
        notes.append({"id": "n7", "text": "Planillas anteriores no usadas por no pasar el parser vigente: " +
                      "; ".join(f"{sf.month_label(p)} ({why})" for p, why in sorted(k["invalid"].items())) + "."})
    for dc in cfg.get("decree_changes") or []:
        notes.append({"id": f"d{len(notes) + 1}", "text": str(dc.get("note"))})

    sources = [{**src, "key": key} for key, src in package["sources"].items()]
    triggers = (decision or {}).get("triggers") or []
    rule = "nuevo período" if "new_period" in triggers else ("revisión" if "revision" in triggers else "publicación vigente")
    machine = (f"Ficha generada por la regla \"{rule}\" (release del {sf.day_label(package['published_at'])}). Las cifras las "
               "calcula el código desde el paquete de evidencia; solo la Lectura Alicanto puede escribirla un modelo, y pasa "
               "por un verificador.")
    return {
        "schema_version": sf.SCHEMA, "id": f"stats-ficha:{FAMILY}:{package['period']}", "family": FAMILY,
        "family_label": cfg["label"], "slug": cfg["slug"], "period": package["period"], "published_at": package["published_at"],
        "release_key": package["release_key"], "kicker": tpl["kicker"].format(label=cfg["label"]),
        "kicker_meta": tpl["kicker_meta"].format(period_label=span(ty, tm), published_label=sf.day_label(package["published_at"]),
                                                 cadence_phrase=cfg["cadence_phrase"]),
        "headline": headline, "headline_type": headline_type, "dek": dek, "dek_emphasis": f"{fmt_int(fon)} casos",
        "kpis": kpis, "tabs": tabs,
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs, "rendered_in_tabs": True},
        "watch": watch[:2], "notes": notes, "sources": sources, "machine_note": machine,
        "featured": bool((decision or {}).get("featured")), "triggers": triggers, "late_release": late,
        "revisions": package.get("revisions") or [],
    }


FIRST_REVIEW_HOLD = "HOLD_FIRST_REVIEW:awaiting_first_review"


def _gate_open(cfg: dict, root: Path, sha: str | None) -> bool:
    if not cfg.get("first_pass_requires_review"):
        return True
    live = sf.load_live(Path(root), cfg["slug"]) or {}
    if str(live.get("builder_version") or "").startswith("f4_ytd") and live.get("status") == "PASS":
        return True  # the first year-to-date ficha was reviewed and published: later releases follow the policy
    review = cfg.get("first_review") or {}
    return bool(review.get("reviewed_by") and sha and review.get("reviewed_sha256") == sha)


def _latest_sha(root: Path) -> str | None:
    store = _load(Path(root) / CAPTURE) or {}
    rels = sorted((r for r in store.get("releases") or [] if r.get("period")), key=lambda r: r["period"])
    doc = (rels[-1].get("document") or {}) if rels else {}
    return doc.get("sha256") if doc.get("status") == "captured" else None


def first_review_gate(result: dict, cfg: dict, root: Path) -> dict:
    """First publication of the year-to-date ficha on real data needs a human look (review of PR #129, 3-nov-2026).

    While ``first_pass_requires_review`` is true and no year-to-date F4 ficha is live, a PASS is written as HOLD
    (``awaiting_first_review``) with the full rendered ficha in the hold file. It publishes only once the registry
    records ``first_review.reviewed_by`` and ``first_review.reviewed_sha256`` equal to the release's workbook SHA-256."""
    if result.get("status") != "pass":
        return result
    ficha = result["ficha"]
    sha = next((s.get("sha256") for s in ficha.get("sources") or [] if s.get("key") == f"ges_{ficha.get('period')}"), None)
    if _gate_open(cfg, root, sha):
        return result
    decision = {**(result.get("decision") or {}), "decision": "HOLD",
                "holds": [*((result.get("decision") or {}).get("holds") or []), FIRST_REVIEW_HOLD]}
    candidate = {**ficha, "status": "AWAITING_FIRST_REVIEW", "review_request": {
        "release_sha256": sha, "period": ficha.get("period"),
        "to_publish": "registro families.F4.first_review: reviewed_by, reviewed_at y reviewed_sha256 = release_sha256"}}
    return {**{k: v for k, v in result.items() if k != "ficha"}, "status": "hold", "decision": decision,
            "errors": [FIRST_REVIEW_HOLD], "candidate": candidate}


def run(root: Path, *, today: date, registry: dict | None = None, llm: bool = True,
        model_call: Callable[..., Any] | None = None, budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    # While the first-review gate is closed for the newest captured file, no model is called: a gated ficha never
    # publishes, so a paid Lectura would be wasted (review of #129).
    gated = not _gate_open(cfg, Path(root), _latest_sha(root))
    out = sf.run_family(FAMILY, builder_version=BUILDER_VERSION, build_package=build_package, compose=compose, root=Path(root),
                        today=today, registry=registry, llm=llm and not gated, model_call=model_call, budget=budget)
    return first_review_gate(out, registry["families"][FAMILY], Path(root))
