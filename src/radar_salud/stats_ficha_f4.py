"""F4 · Casos GES por trimestre: evidence package, KPIs and ficha (no model numbers).

Inputs (captured by ``stats_capture``; never downloaded here):
- ``data/stats_fichas/captures/ges_quarterly.json``: one entry per SIS release ('… a junio 2026'), parsed with the
  corrected GES parser (``data_insights.parse_ges_workbook``): the sheet of the reporting year is pinned and the
  problem rows add up to the declared total for Fonasa and for Isapre;
- ``data/market/isapre_portfolio.json`` (F1): Isapre beneficiaries per month, the only rate denominator captured.

Rules (registry F4):
- the pinned year sheet is a year-to-date count ('measure'); the quarter is the difference between two cuts of the
  same year (Q1 = the March cut). The measure must be declared by the source's header text or confirmed by a reviewer
  in the registry, otherwise HOLD. A cut lower than the previous cut of the same year is a reconciliation failure;
- year-on-year compares the same quarter one year earlier; problems are matched by their label. Labels present in only
  one of the two quarters mark a change of the GES list (decree) and are excluded from the problem ranking;
- rates per 1.000 use beneficiaries of the same insurer (Isapre from F1, mean of the quarter's three month-end stocks).
  Fonasa beneficiaries are not captured: its rate is 'no disponible', never estimated. Rates are 'tasa bruta'.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import stats_fichas as sf
from .stats_fichas import fmt_dec, fmt_int, fmt_signed, value
from .weekly_freshness import numbers_in

FAMILY = "F4"
BUILDER_VERSION = "f4_index_topic_v3"
CAPTURE = Path("data/stats_fichas/captures/ges_quarterly.json")
PORTFOLIO = Path("data/market/isapre_portfolio.json")
QWORD = {1: "primer", 2: "segundo", 3: "tercer", 4: "cuarto"}
MAX_PROBLEM_ROWS = 8


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


def qmonths(y: int, q: int) -> list[str]:
    return [f"{y}-{m:02d}" for m in range(3 * q - 2, 3 * q + 1)]


def qlabel(y: int, q: int) -> str:
    return f"{QWORD[q]} trimestre de {y}"


def qshort(y: int, q: int) -> str:
    return f"T{q} {y}"


def qprev(y: int, q: int, n: int = 1) -> tuple[int, int]:
    k = y * 4 + (q - 1) - n
    return k // 4, k % 4 + 1


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _fold(label)).strip("_")[:48] or "problema"


def short_label(label: str, n: int = 18) -> str:
    label = " ".join(str(label).split())
    return label if len(label) <= n else label[: n - 1].rstrip(" ,;-") + "…"


SINCE_2005 = re.compile(r"desde (?:julio )?(?:de )?2005|2005\s*[-–a]\s*20\d\d|desde el inicio")
# 'acumulado del trimestre' / 'casos del trimestre' declare a quarter, never a year-to-date count.
QUARTER_HEAD = re.compile(r"\btrimestr|\btrim\b")
YTD_HEAD = re.compile(r"acumulad[oa]s?\s+(?:en\s+el\s+|del\s+|al\s+)?(?:ano|anual)\b|acumulad[oa]s?\s+(?:desde\s+)?enero"
                      r"|desde\s+enero|\benero\s*(?:a|al|-|–|hasta)\s*[a-z]{3,}|\bene\w*\s*[-–]\s*[a-z]{3}|year\s*to\s*date|\bytd\b")


def header_measure(parse: dict) -> str | None:
    """What the captured header text declares: 'since_2005' | 'ytd' | 'quarter' | 'ambiguous' | None (silent).

    A bare 'acumulado' declares nothing (it can be cumulative within the quarter); 'acumulado del trimestre' is a
    quarter. Both a year-to-date and a quarter wording → 'ambiguous'."""
    head = parse.get("header") or {}
    text = _fold(" ".join([head.get("fonasa") or "", head.get("isapre") or "", *(head.get("above") or [])]))
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


def build_package(root: Path, registry: dict | None = None, previous_live: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    root = Path(root)
    store = _load(root / CAPTURE)
    if not store or not store.get("releases"):
        raise ValueError("ges_capture_missing")
    failures: list[str] = []
    cuts: dict[str, dict] = {}
    measures = set()
    for rel in store["releases"]:
        doc = rel.get("document") or {}
        parse = doc.get("parse") or {}
        period = rel.get("period")
        if doc.get("status") != "captured" or parse.get("status") != "validated" or parse.get("parser") != sf.GES_PARSER \
                or (parse.get("reconciliation") or {}).get("ok") is not True:
            cuts[period] = {"invalid": parse.get("hold_reason") or parse.get("status") or doc.get("status") or "missing"}
            continue
        if parse.get("period") != period or str(parse.get("sheet") or "").find(period[:4]) < 0:
            cuts[period] = {"invalid": "sheet_or_period_mismatch"}
            continue
        measure, how = measure_of(parse, cfg)
        if measure is None:
            cuts[period] = {"invalid": f"measure_{how}"}
            continue
        measures.add(measure)
        rows = {}
        for o in parse.get("observations") or []:
            key = slug(o["label"])
            if key in rows:
                cuts[period] = {"invalid": f"duplicate_label:{key}"}
                break
            rows[key] = o
        else:
            cuts[period] = {"period": period, "measure": measure, "measure_how": how, "rows": rows,
                            "fonasa": parse["reconciliation"]["declared_total"][0],
                            "isapre": parse["reconciliation"]["declared_total"][1], "sheet": parse.get("sheet"),
                            "url": doc.get("url"), "sha256": doc.get("sha256"), "fetched_at": doc.get("fetched_at"),
                            "published_at": rel.get("published_at"), "release_url": rel.get("release_url"),
                            "total_row": parse["reconciliation"].get("total_row")}
    valid = {p: c for p, c in cuts.items() if "invalid" not in c}
    latest = max(cuts) if cuts else None
    if not latest:
        raise ValueError("ges_capture_empty")
    if latest not in valid:
        failures.append(f"latest_release_not_valid:{latest}:{cuts[latest]['invalid']}")
    if len(measures) > 1:
        failures.append("mixed_measures")
    for p in cuts:
        try:
            qof(p)
        except ValueError:
            failures.append(f"not_a_quarter_end:{p}")

    def quarter(y: int, q: int) -> dict | None:
        """Flow of one quarter: per insurer and per problem (labels matched between the two cuts)."""
        cur = valid.get(qend(y, q))
        if not cur:
            return None
        if cur["measure"] == "quarter":
            return {"fonasa": cur["fonasa"], "isapre": cur["isapre"],
                    "rows": {k: (o["label"], o["fonasa"], o["isapre"]) for k, o in cur["rows"].items()},
                    "cuts": [cur["period"]], "dropped": [], "added": []}
        if q == 1:
            return {"fonasa": cur["fonasa"], "isapre": cur["isapre"],
                    "rows": {k: (o["label"], o["fonasa"], o["isapre"]) for k, o in cur["rows"].items()},
                    "cuts": [cur["period"]], "dropped": [], "added": []}
        prev = valid.get(qend(y, q - 1))
        if not prev:
            return None
        return {"fonasa": cur["fonasa"] - prev["fonasa"], "isapre": cur["isapre"] - prev["isapre"],
                "rows": {k: (o["label"], o["fonasa"] - prev["rows"][k]["fonasa"], o["isapre"] - prev["rows"][k]["isapre"])
                         for k, o in cur["rows"].items() if k in prev["rows"]},
                "cuts": [prev["period"], cur["period"]],
                "added": sorted(k for k in cur["rows"] if k not in prev["rows"]),
                "dropped": sorted(k for k in prev["rows"] if k not in cur["rows"])}

    # Year-to-date cuts never decrease within a year (a lower cut means the sheet is not what we think: HOLD).
    for p, c in sorted(valid.items()):
        try:
            y, q = qof(p)
        except ValueError:
            continue
        prev = valid.get(qend(y, q - 1)) if q > 1 else None
        if c["measure"] == "ytd" and prev:
            if c["fonasa"] < prev["fonasa"] or c["isapre"] < prev["isapre"]:
                failures.append(f"ytd_total_decreases:{p}")
            bad = [k for k, o in c["rows"].items() if k in prev["rows"]
                   and (o["fonasa"] < prev["rows"][k]["fonasa"] or o["isapre"] < prev["rows"][k]["isapre"])]
            if bad:
                failures.append(f"ytd_row_decreases:{p}:{bad[0]}")
            if c["rows"].keys() != prev["rows"].keys():
                failures.append(f"problem_list_changed_within_year:{p}")
    t = latest
    ty, tq = qof(t) if latest and not any(f.startswith("not_a_quarter_end") for f in failures) else (0, 0)
    cur_q = quarter(ty, tq) if ty else None
    if ty and cur_q is None and not failures:
        failures.append(f"quarter_not_derivable:{qid(ty, tq)}")

    sources: dict[str, dict] = {}
    values: dict[str, dict] = {}
    published = (valid.get(t) or {}).get("published_at") or (store["releases"][-1].get("published_at"))
    primary = valid.get(t) or {}
    package: dict[str, Any] = {
        "family": FAMILY, "period": t, "published_at": published,
        "release_key": sf.release_key(t, primary.get("sha256") or "0" * 16),
        "primary_source": {"url": primary.get("url"), "sha256": primary.get("sha256")}, "sources": sources,
        "values": values, "entities": [{"code": None, "key": "fonasa", "name": "Fonasa"}], "entity_codes": [],
        "entity_keys": ["fonasa"], "causal_note": None, "provisional": False,
        "reconciliation": {"ok": not failures, "failures": failures,
                           "checks": ["hoja del año del corte fijada (nunca otra hoja)",
                                      "Σ filas por problema = total declarado, Fonasa e Isapre",
                                      "medida declarada por el encabezado de la fuente o confirmada por un revisor",
                                      "cortes acumulados del mismo año nunca bajan",
                                      "un solo archivo y hash por release", "trimestre derivable del último corte"]},
        "group_markers": [
            [r"(?:las |a las |de las |en las |entre las )?isapres?|(?:el )?sistema isapre", "isapres"],
            [r"(?:el|al|del) sistema|(?:el|al|del) total|ambos seguros|(?:el|al|del) ges(?! [a-z])", "system"]],
        "prompt_rules": ("Fonasa es un seguro y 'las Isapres' (en conjunto) el otro; 'el total' o 'ambos seguros' es la "
                         "suma. Las cifras son casos de un trimestre: nombra el trimestre en palabras ('el segundo "
                         "trimestre'); una variación anual lleva 'frente al mismo trimestre' del año anterior. La tasa "
                         "es bruta y por cada mil beneficiarios del mismo seguro; Fonasa no tiene tasa."),
    }
    if failures:
        package.update(findings=[], kpis={}, revisions=[], constants=[], periods=[t])
        return package

    def src_key(c: dict) -> str:
        return f"ges_{c['period']}"

    def add_cut_source(c: dict) -> str:
        key = src_key(c)
        y, q = qof(c["period"])
        sources.setdefault(key, sf.source_ref(
            url=c["url"], sha256=c["sha256"], published_at=c["published_at"], fetched_at=c["fetched_at"],
            label=f"SIS · Casos GES de Fonasa e Isapres a {sf.month_label(c['period'])} (xlsx)",
            role=f"casos {'acumulados del año' if c['measure'] == 'ytd' else 'del trimestre'} por problema y seguro",
            locator=f"{c['sheet']}!fila Total {c.get('total_row')}"))
        for ins in ("fonasa", "isapre"):
            vid = f"ges.cut.{c['period']}.{ins}"
            values[vid] = value(vid, c[ins], unit="casos", period=c["period"], source=key,
                                locator=f"{c['sheet']}!Total {ins.capitalize()}")
        return key

    def derived(vid: str, val: float, formula: str, inputs: list[str], unit: str, period: str, src: str | None = None) -> float:
        values[vid] = value(vid, val, unit=unit, period=period, source=src, formula=formula, inputs=inputs, kind="derived")
        return val

    # Every derivable quarter (trend), from the oldest captured cut to t.
    quarters: dict[tuple[int, int], dict] = {}
    for p in sorted(valid):
        y, q = qof(p)
        flow = quarter(y, q)
        if flow is None:
            continue
        for c in flow["cuts"]:
            add_cut_source(valid[c])
        quarters[(y, q)] = flow
        k = qid(y, q)
        ins = [f"ges.cut.{c}.{{}}" for c in flow["cuts"]]
        formula = "corte(t) − corte(t−1) del mismo año" if len(flow["cuts"]) == 2 else (
            "corte de marzo (primer trimestre)" if valid[flow["cuts"][0]]["measure"] == "ytd" else "casos del trimestre declarados")
        f = derived(f"ges.q.{k}.fonasa", flow["fonasa"], formula, [i.format("fonasa") for i in ins], "casos", qend(y, q))
        i_ = derived(f"ges.q.{k}.isapre", flow["isapre"], formula, [i.format("isapre") for i in ins], "casos", qend(y, q))
        derived(f"ges.q.{k}.total", f + i_, "Fonasa + Isapre", [f"ges.q.{k}.fonasa", f"ges.q.{k}.isapre"], "casos", qend(y, q))
        derived(f"ges.q.{k}.isapre_share", i_ / (f + i_) * 100 if f + i_ else 0.0, "Isapre / (Fonasa + Isapre) × 100",
                [f"ges.q.{k}.isapre", f"ges.q.{k}.total"], "%", qend(y, q))
    if (ty, tq) not in quarters:
        raise ValueError("ges_latest_quarter_missing")
    t_key = qid(ty, tq)
    by, bq = qprev(ty, tq, 4)
    b_key = qid(by, bq)
    has_yoy = (by, bq) in quarters
    kpcfg = cfg["kpis"]
    findings: list[dict] = []
    added = dropped = []
    if has_yoy:
        cur, base = quarters[(ty, tq)], quarters[(by, bq)]
        for ins in ("fonasa", "isapre", "total"):
            a, b = values[f"ges.q.{b_key}.{ins}"]["value"], values[f"ges.q.{t_key}.{ins}"]["value"]
            derived(f"ges.yoy.{ins}", b - a, "casos(t) − casos(mismo trimestre t−1)", [f"ges.q.{t_key}.{ins}", f"ges.q.{b_key}.{ins}"], "casos", t)
            derived(f"ges.yoy.{ins}_pct", (b - a) / a * 100 if a else 0.0, "Δ / casos del mismo trimestre t−1 × 100",
                    [f"ges.yoy.{ins}", f"ges.q.{b_key}.{ins}"], "%", t)
        derived("ges.yoy.isapre_share_pp", values[f"ges.q.{t_key}.isapre_share"]["value"] - values[f"ges.q.{b_key}.isapre_share"]["value"],
                "participación(t) − participación(t−4)", [f"ges.q.{t_key}.isapre_share", f"ges.q.{b_key}.isapre_share"], "pp", t)
        # Decree changes: labels in one quarter only (list of problems changed between the two quarters).
        added = sorted(set(cur["rows"]) - set(base["rows"]))
        dropped = sorted(set(base["rows"]) - set(cur["rows"]))
        common = sorted(set(cur["rows"]) & set(base["rows"]))
        cf = sum(cur["rows"][k][1] + cur["rows"][k][2] for k in common)
        cb = sum(base["rows"][k][1] + base["rows"][k][2] for k in common)
        derived(f"ges.q.{t_key}.total_comparable", cf, "Σ casos de los problemas presentes en ambos trimestres", [f"ges.q.{t_key}.total"], "casos", t)
        derived(f"ges.q.{b_key}.total_comparable", cb, "Σ casos de los problemas presentes en ambos trimestres", [f"ges.q.{b_key}.total"], "casos", qend(by, bq))
        derived("ges.yoy.total_comparable_pct", (cf - cb) / cb * 100 if cb else 0.0, "Δ comparable / base comparable × 100",
                [f"ges.q.{t_key}.total_comparable", f"ges.q.{b_key}.total_comparable"], "%", t)
        derived("ges.list.added", len(added), "problemas solo en el trimestre actual", [], "count", t)
        derived("ges.list.dropped", len(dropped), "problemas solo en el trimestre base", [], "count", t)
        th = kpcfg["casos_ges"]["threshold"]["yoy_pct"]
        if abs(values["ges.yoy.total_pct"]["value"]) >= th:
            findings.append({"type": "threshold_crossed", "kpi": "casos_ges", "crossed": True,
                             "strength": abs(values["ges.yoy.total_pct"]["value"]) / th})
    # Problems: quarter t, and year-on-year growth for those with a comparable base.
    cur = quarters[(ty, tq)]
    tp = kpcfg["top_problemas"]["threshold"]
    problems = []
    def problem_inputs(flow: dict, k: str) -> list[str]:
        """Captured problem rows (sheet!row) the quarter flow of problem ``k`` is computed from."""
        ids = []
        for c in flow["cuts"]:
            cut = valid[c]
            o = cut["rows"][k]
            for ins in ("fonasa", "isapre"):
                vid = f"ges.cut.{c}.p.{k}.{ins}"
                values[vid] = value(vid, o[ins], unit="casos", period=c, source=src_key(cut),
                                    locator=f"{cut['sheet']}!fila {o.get('row')} ({o['label']}) · {ins.capitalize()}")
                ids.append(vid)
        return ids

    p_formula = lambda flow: ("Fonasa + Isapre del problema: corte(t) − corte(t−1) del mismo año"  # noqa: E731
                              if len(flow["cuts"]) == 2 else "Fonasa + Isapre del problema")
    for k, (label, f, i) in cur["rows"].items():
        derived(f"ges.p.{k}.{t_key}", f + i, p_formula(cur), problem_inputs(cur, k), "casos", t)
        row = {"key": k, "label": label, "t": f + i}
        if has_yoy and k in quarters[(by, bq)]["rows"]:
            base_flow = quarters[(by, bq)]
            _, bf, bi = base_flow["rows"][k]
            derived(f"ges.p.{k}.{b_key}", bf + bi, p_formula(base_flow), problem_inputs(base_flow, k), "casos", qend(by, bq))
            row["base"] = bf + bi
            if bf + bi >= tp["min_cases"]:
                # rounded to one decimal: the chart shows exactly this value
                row["pct"] = derived(f"ges.p.{k}.yoy_pct", round((f + i - bf - bi) / (bf + bi) * 100, 1),
                                     "redondeo(Δ / casos del mismo trimestre t−1 × 100, 1)",
                                     [f"ges.p.{k}.{t_key}", f"ges.p.{k}.{b_key}"], "%", t)
        problems.append(row)
    ranked = sorted((r for r in problems if "pct" in r), key=lambda r: (-r["pct"], r["label"]))
    crossing = [r for r in ranked if r["pct"] >= tp["pct"]]
    derived("conteo.problemas_sobre_umbral", len(crossing), "problemas con Δ a/a ≥ umbral y base ≥ mínimo", [], "count", t)
    derived("conteo.problemas_bajan", sum(1 for r in ranked if r["pct"] < 0), "problemas comparables con Δ a/a < 0", [], "count", t)
    if crossing:
        findings.append({"type": "problem_growth", "kpi": "top_problemas", "crossed": True, "strength": len(crossing)})

    # Crude rates per 1.000 beneficiaries of the same insurer: Isapre from F1; Fonasa not captured.
    port = _portfolio_isapre(root)
    rates = {}
    for (y, q) in quarters:
        months = qmonths(y, q)
        if port and all(m in port["totals"] for m in months):
            k = qid(y, q)
            sources.setdefault("cartera", sf.source_ref(
                url=port["url"], sha256=port["sha256"], published_at=port["published_at"], fetched_at=port["fetched_at"],
                label="SIS · Cartera mensual de beneficiarios Isapre (xlsx), ficha F1",
                role="denominador de la tasa Isapre: beneficiarios al cierre de cada mes", locator="fila Total Sistema"))
            for m in months:
                values[f"cartera.isapre.{m}"] = value(f"cartera.isapre.{m}", port["totals"][m], unit="beneficiarios",
                                                      period=m, source="cartera", locator="Total Sistema")
            avg = derived(f"benef.isapre.avg.{k}", sum(port["totals"][m] for m in months) / 3,
                          "promedio de los 3 stocks de cierre de mes", [f"cartera.isapre.{m}" for m in months], "beneficiarios", qend(y, q))
            rates[(y, q)] = derived(f"ges.q.{k}.isapre_rate", values[f"ges.q.{k}.isapre"]["value"] / avg * 1000,
                                    "casos Isapre del trimestre / beneficiarios Isapre promedio × 1.000",
                                    [f"ges.q.{k}.isapre", f"benef.isapre.avg.{k}"], "per_1000", qend(y, q))
    # Label digits ('Diabetes Mellitus Tipo 2') are captured text, not figures: they may be shown.
    label_numbers = sorted({abs(v) for r in problems for _, v, _ in numbers_in(r["label"])})
    constants = [1000, kpcfg["casos_ges"]["threshold"]["yoy_pct"], tp["pct"], tp["min_cases"], 3, len(quarters), *label_numbers]
    months_all = sorted({m for (y, q) in quarters for m in qmonths(y, q)})
    # Figures the topic index lines cite (verify_ficha traces each line to its own refs): the registry threshold and the
    # number of derivable quarters, as evidence ids instead of loose constants.
    values["regla.top_problemas.pct"] = value("regla.top_problemas.pct", tp["pct"], unit="%", period=t, source=None,
                                              formula="umbral del registro (top_problemas)", kind="rule")
    values["conteo.trimestres"] = value("conteo.trimestres", len(quarters), unit="trimestres", period=t, source=None,
                                        formula="conteo de trimestres derivables", kind="derived")
    package.update(period=t, periods=months_all, base_period=qend(by, bq) if has_yoy else None, findings=findings,
                   revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
                   constants=constants,
                   kpis={"t": (ty, tq), "b": (by, bq), "has_yoy": has_yoy, "quarters": sorted(quarters), "rates": rates,
                         "problems": problems, "ranked": ranked, "crossing": crossing, "added": added, "dropped": dropped,
                         "measure": valid[t]["measure"], "measure_how": valid[t]["measure_how"],
                         "invalid": {p: c["invalid"] for p, c in cuts.items() if "invalid" in c}})
    _lectura_material(package, values)
    return package


def _lectura_material(package: dict, values: dict) -> None:
    k = package["kpis"]
    (ty, tq), (by, bq) = k["t"], k["b"]
    tk, bk = qid(ty, tq), qid(by, bq)
    Q = {"periods": qmonths(ty, tq), "period_kind": "quarter", "requires_period": True}
    P = lambda vid, **kw: sf.pool_entry(values, vid, **kw) if vid in values else None  # noqa: E731
    pool = [P(f"ges.q.{tk}.total", metric="casos", signed=False, scope="system", **Q),
            P(f"ges.q.{tk}.fonasa", metric="casos", signed=False, scope="insurer:fonasa", **Q),
            P(f"ges.q.{tk}.isapre", metric="casos", signed=False, scope="isapres", **Q),
            P(f"ges.q.{tk}.isapre_share", signed=False, scope="isapres", base="casos_ambos_seguros", **Q),
            P(f"ges.q.{tk}.isapre_rate", signed=False, scope="isapres", base="beneficiarios_mismo_seguro", **Q)]
    if k["has_yoy"]:
        YY = {"periods": qmonths(by, bq) + qmonths(ty, tq), "period_kind": "quarter_yoy"}
        pool += [P(f"ges.yoy.{ins}", metric="casos", scope=sc, **YY) for ins, sc in
                 (("total", "system"), ("fonasa", "insurer:fonasa"), ("isapre", "isapres"))]
        pool += [P(f"ges.yoy.{ins}_pct", scope=sc, base="casos_mismo_trimestre_anio_anterior", **YY) for ins, sc in
                 (("total", "system"), ("fonasa", "insurer:fonasa"), ("isapre", "isapres"))]
        pool += [P("ges.yoy.isapre_share_pp", scope="isapres", base="casos_ambos_seguros", **YY),
                 P(f"ges.q.{bk}.total", metric="casos", signed=False, scope="system",
                   periods=qmonths(by, bq), period_kind="quarter", requires_period=True)]
    package["lectura_pool"] = [e for e in pool if e]
    ratios = []
    f, i = values[f"ges.q.{tk}.fonasa"]["value"], values[f"ges.q.{tk}.isapre"]["value"]
    if i:
        ratios.append({"id": "ratio.fonasa_por_isapre", "value": f / i, "unit": "x", "entity": None, "signed": False,
                       "periods": qmonths(ty, tq), "requires_period": False, "formula": "casos Fonasa / casos Isapre",
                       "inputs": [f"ges.q.{tk}.fonasa", f"ges.q.{tk}.isapre"], "scope": "insurer:fonasa",
                       "period_kind": "quarter", "trivial": False, "base": None})
    ratios.append({"id": "conteo.problemas_sobre_umbral", "value": len(k["crossing"]), "unit": "count", "entity": None,
                   "signed": False, "periods": qmonths(ty, tq), "requires_period": False, "formula": "conteo",
                   "inputs": [], "scope": "system", "period_kind": "quarter", "trivial": True})
    package["derived_ratios"] = ratios
    package["ranks"] = []


# ---------------------------------------------------------------------------------------------
# Ficha composition


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    v = package["values"]
    k = package["kpis"]
    (ty, tq), (by, bq) = k["t"], k["b"]
    tk, bk = qid(ty, tq), qid(by, bq)
    val = lambda vid: v[vid]["value"]  # noqa: E731
    total, fon, isa = val(f"ges.q.{tk}.total"), val(f"ges.q.{tk}.fonasa"), val(f"ges.q.{tk}.isapre")
    share = val(f"ges.q.{tk}.isapre_share")
    rate = k["rates"].get((ty, tq))
    pct = lambda vid: fmt_dec(val(vid), 1, signed=True) + "%"  # noqa: E731
    yoy = k["has_yoy"]
    list_changed = bool(k["added"] or k["dropped"])
    yoy_th = fmt_dec(cfg["kpis"]["casos_ges"]["threshold"]["yoy_pct"], 0)  # registry threshold, never hard-coded

    head_type = "yoy" if yoy else "no_yoy"
    headline = tpl["headline"][head_type].format(qlabel=qlabel(ty, tq), total=fmt_int(total),
                                                  yoy=pct("ges.yoy.total_pct") if yoy else "")
    rate_clause = (f" La tasa bruta Isapre fue {fmt_dec(rate, 1)} casos por 1.000 beneficiarios; la de Fonasa no está disponible."
                   if rate is not None else " Las tasas por beneficiario no están disponibles para este trimestre.")
    dek = tpl["dek"].format(fonasa=fmt_int(fon), isapre=fmt_int(isa), share=fmt_dec(share, 1), rate_clause=rate_clause)

    kpis = [{"id": "casos", "label": "Casos GES", "value": fmt_int(total), "prov": "C",
             "lines": ([f"{pct('ges.yoy.total_pct')} vs. {qshort(by, bq)}"] if yoy else ["a/a no disponible"])
             + ([f"{pct('ges.yoy.total_comparable_pct')} solo problemas comparables"] if yoy and list_changed else []),
             "badge": (f"Cruza umbral ({yoy_th}% a/a)" if any(f["kpi"] == "casos_ges" for f in package["findings"]) else "Sin umbral cruzado")
             if yoy else "Sin base a/a capturada", "badge_kind": "crossed" if any(f["kpi"] == "casos_ges" for f in package["findings"]) else "muted",
             "refs": [f"ges.q.{tk}.total"] + (["ges.yoy.total_pct"] if yoy else [])},
            {"id": "fonasa", "label": "Fonasa", "value": fmt_int(fon), "prov": "C",
             "lines": [f"{pct('ges.yoy.fonasa_pct')} vs. {qshort(by, bq)}" if yoy else "a/a no disponible",
                       "tasa no disponible (sin beneficiarios capturados)"],
             "refs": [f"ges.q.{tk}.fonasa"]},
            {"id": "isapre", "label": "Isapres", "value": fmt_int(isa), "prov": "C",
             "lines": [f"{pct('ges.yoy.isapre_pct')} vs. {qshort(by, bq)}" if yoy else "a/a no disponible",
                       f"{fmt_dec(share, 1)}% de los casos de ambos seguros"],
             "refs": [f"ges.q.{tk}.isapre", f"ges.q.{tk}.isapre_share"]},
            {"id": "tasa", "label": "Tasa bruta Isapre", "value": fmt_dec(rate, 1) if rate is not None else "no disponible",
             "prov": "C" if rate is not None else None,
             "lines": (["casos por 1.000 beneficiarios Isapre", "tasa a/a no disponible" if (by, bq) not in k["rates"] else
                        f"{qshort(by, bq)}: {fmt_dec(k['rates'][(by, bq)], 1)}"] if rate is not None
                       else ["sin beneficiarios del trimestre capturados"]),
             "refs": [f"ges.q.{tk}.isapre_rate"] if rate is not None else []}]

    # Tab 1 · Totales
    tabs = []
    if yoy:
        rows = [{"label": lab, "value": val(f"ges.q.{tk}.{ins}"), "ref": f"ges.q.{tk}.{ins}",
                 "base": val(f"ges.q.{bk}.{ins}"), "base_ref": f"ges.q.{bk}.{ins}"}
                for lab, ins in (("Total", "total"), ("Fonasa", "fonasa"), ("Isapres", "isapre"))]
        c_tot = {"id": "f4-totales", "form": "dots", "digits": 0, "unit": "casos",
                 "headline": f"Casos del {qshort(ty, tq)} frente al {qshort(by, bq)}",
                 "subtitle": f"Casos GES por seguro · punto = {qshort(ty, tq)}, aro = {qshort(by, bq)}", "rows": rows,
                 "table": {"columns": ["Seguro", qshort(by, bq), qshort(ty, tq), "a/a"],
                           "rows": [[r["label"], fmt_int(r["base"]), fmt_int(r["value"]),
                                     pct(f"ges.yoy.{ins}_pct")] for r, ins in zip(rows, ("total", "fonasa", "isapre"))]},
                 "source": "SIS, casos GES por trimestre: diferencia entre cortes acumulados del mismo año."}
        tot_text = [f"En el {qlabel(ty, tq)} Fonasa e Isapres informaron {fmt_int(total)} casos GES, "
                    f"{fmt_int(abs(val('ges.yoy.total')))} {'más' if val('ges.yoy.total') >= 0 else 'menos'} que en el {qlabel(by, bq)} "
                    f"({pct('ges.yoy.total_pct')})."]
        if list_changed:
            tot_text.append(f"Con solo los problemas presentes en ambos trimestres la variación es {pct('ges.yoy.total_comparable_pct')}: "
                            "la lista de problemas cambió entre ambos trimestres (posible cambio de decreto GES).")
    else:
        rows = [{"label": lab, "value": val(f"ges.q.{tk}.{ins}"), "ref": f"ges.q.{tk}.{ins}", "emphasis": ins == "total"}
                for lab, ins in (("Total", "total"), ("Fonasa", "fonasa"), ("Isapres", "isapre"))]
        c_tot = {"id": "f4-totales", "form": "bars", "unit": "casos", "headline": f"Casos del {qshort(ty, tq)} por seguro",
                 "subtitle": "Casos GES por seguro", "rows": rows,
                 "table": {"columns": ["Seguro", qshort(ty, tq)], "rows": [[r["label"], fmt_int(r["value"])] for r in rows]},
                 "source": "SIS, casos GES por trimestre."}
        tot_text = [f"En el {qlabel(ty, tq)} Fonasa e Isapres informaron {fmt_int(total)} casos GES; la comparación con el mismo "
                    "trimestre del año anterior no está disponible porque Alicanto no tiene esos cortes capturados."]
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
                 "subtitle": f"Problemas que crecen: variación a/a de casos · base ≥ {fmt_int(tp['min_cases'])} casos en el {qshort(by, bq)}",
                 "rows": [{"label": short_label(r["label"]), "value": r["pct"], "ref": f"ges.p.{r['key']}.yoy_pct",
                           "emphasis": r["pct"] >= tp["pct"]} for r in ranked],
                 "table": {"columns": ["Problema de salud", qshort(by, bq), qshort(ty, tq), "a/a"],
                           "rows": [[r["label"], fmt_int(r["base"]), fmt_int(r["t"]), fmt_dec(r["pct"], 1, signed=True) + "%"] for r in ranked]},
                 "source": "SIS, casos GES por problema (Fonasa + Isapre). Solo problemas presentes en ambos trimestres."}
        top_text = [f"Se ordenan los problemas que crecen, con al menos {fmt_int(tp['min_cases'])} casos en el {qlabel(by, bq)}; "
                    f"cruzan el umbral los que crecen {fmt_dec(tp['pct'], 0)}% o más."]
        if declining:
            top_text.append(("Un problema comparable bajó" if len(declining) == 1 else
                             sf.count_phrase(len(declining), "", "problemas comparables bajaron").strip().capitalize())
                            + f" frente al {qshort(by, bq)}; no se grafican en este ranking de crecimiento.")
    else:
        biggest = sorted(k["problems"], key=lambda r: (-r["t"], r["label"]))[:MAX_PROBLEM_ROWS]
        c_top = {"id": "f4-top", "form": "bars", "unit": "casos", "headline": "Problemas con más casos en el trimestre",
                 "subtitle": f"Casos GES por problema, {qshort(ty, tq)} (Fonasa + Isapre)",
                 "rows": [{"label": short_label(r["label"]), "value": r["t"], "ref": f"ges.p.{r['key']}.{tk}"} for r in biggest],
                 "table": {"columns": ["Problema de salud", qshort(ty, tq)], "rows": [[r["label"], fmt_int(r["t"])] for r in biggest]},
                 "source": "SIS, casos GES por problema."}
        top_text = ["El ranking por crecimiento necesita el mismo trimestre del año anterior; mientras no esté capturado se "
                    "muestran los problemas con más casos."]
    if k["added"] or k["dropped"]:
        top_text.append(f"La lista de problemas cambió entre el {qshort(by, bq)} y el {qshort(ty, tq)} (posible cambio de decreto "
                        f"GES). Problemas sin base comparable: {fmt_int(len(k['added']))}; que ya no aparecen: "
                        f"{fmt_int(len(k['dropped']))}. No entran al ranking.")
    tabs.append({"id": "problemas", "label": "Top problemas", "charts": [c_top], "text": top_text})

    # Tab 3 · Fonasa vs Isapre
    qs = k["quarters"]
    c_share = {"id": "f4-share", "form": "line", "unit": "%", "digits": 1, "headline": "Parte Isapre de los casos GES",
               "subtitle": "% de los casos informados por Fonasa e Isapres, por trimestre",
               "rows": [{"label": qshort(y, q), "value": val(f"ges.q.{qid(y, q)}.isapre_share"), "ref": f"ges.q.{qid(y, q)}.isapre_share",
                         "emphasis": (y, q) == (ty, tq)} for (y, q) in qs[-12:]],
               "table": {"columns": ["Trimestre", "Fonasa", "Isapres", "% Isapre"],
                         "rows": [[qshort(y, q), fmt_int(val(f"ges.q.{qid(y, q)}.fonasa")), fmt_int(val(f"ges.q.{qid(y, q)}.isapre")),
                                   fmt_dec(val(f"ges.q.{qid(y, q)}.isapre_share"), 1) + "%"] for (y, q) in qs[-12:]]},
               "source": "Denominador: casos de ambos seguros del mismo trimestre. No es participación de beneficiarios."}
    ins_charts = [c_share] if len(qs) >= 2 else []
    if k["rates"]:
        rq = sorted(k["rates"])
        ins_charts.append({"id": "f4-tasa", "form": "bars", "unit": "por 1.000", "digits": 1,
                           "headline": "Tasa bruta Isapre por trimestre",
                           "subtitle": "Casos Isapre por 1.000 beneficiarios Isapre (promedio de los 3 cierres de mes)",
                           "rows": [{"label": qshort(y, q), "value": k["rates"][(y, q)], "ref": f"ges.q.{qid(y, q)}.isapre_rate",
                                     "emphasis": (y, q) == (ty, tq)} for (y, q) in rq],
                           "table": {"columns": ["Trimestre", "Casos Isapre", "Beneficiarios promedio", "Tasa bruta"],
                                     "rows": [[qshort(y, q), fmt_int(val(f"ges.q.{qid(y, q)}.isapre")),
                                               fmt_int(val(f"benef.isapre.avg.{qid(y, q)}")), fmt_dec(k["rates"][(y, q)], 1)] for (y, q) in rq]},
                           "source": "Beneficiarios: cartera mensual Isapre (ficha F1). Tasa bruta: sin ajuste por edad ni sexo."})
    ins_text = [f"Las Isapres informaron el {fmt_dec(share, 1)}% de los casos del {qlabel(ty, tq)}; es una parte de los casos, "
                "no de la población."]
    ins_text.append(f"Tasa bruta Isapre del trimestre: {fmt_dec(rate, 1)} casos por 1.000 beneficiarios Isapre. Fonasa: tasa no "
                    "disponible, porque Alicanto no tiene capturados sus beneficiarios." if rate is not None else
                    "Tasa por beneficiario no disponible: faltan los beneficiarios del trimestre (Isapre) y Alicanto no captura los de Fonasa.")
    tabs.append({"id": "seguros", "label": "Fonasa vs Isapre", "charts": ins_charts[:2], "text": ins_text})

    # Tab 4 · Tendencia trimestral
    c_trend = {"id": "f4-trend", "form": "line", "unit": "casos", "digits": 0, "headline": "Casos GES por trimestre",
               "subtitle": "Fonasa + Isapre, casos de cada trimestre",
               "rows": [{"label": qshort(y, q), "value": val(f"ges.q.{qid(y, q)}.total"), "ref": f"ges.q.{qid(y, q)}.total",
                         "emphasis": (y, q) == (ty, tq)} for (y, q) in qs[-12:]],
               "table": {"columns": ["Trimestre", "Casos", "Cortes usados"],
                         "rows": [[qshort(y, q), fmt_int(val(f"ges.q.{qid(y, q)}.total")),
                                   " − ".join(sf.month_label(c) for c in reversed(_cuts_of(v, qid(y, q))))] for (y, q) in qs[-12:]]},
               "source": "SIS, casos GES. Alicanto calcula cada trimestre desde los cortes acumulados."}
    trend_text = [f"La serie tiene {fmt_int(len(qs))} trimestres derivables de los cortes capturados."
                  + (" Faltan cortes para completar el resto." if k["invalid"] else "")]
    tabs.append({"id": "tendencia", "label": "Tendencia trimestral", "charts": [c_trend] if len(qs) >= 2 else [],
                 "text": trend_text})
    if len(qs) < 2:  # a one-point trend is not a chart
        tabs[-1]["text"].append("La tendencia se dibuja desde el segundo trimestre capturado.")

    # Index → topic layout (Dirección 29-oct): generic index fields; the topic dek falls back to the tab text.
    index_refs = {"problemas": ["regla.top_problemas.pct"], "tendencia": ["conteo.trimestres"],
                  "seguros": [f"ges.q.{tk}.isapre_share"], "totales": [f"ges.q.{tk}.total", "ges.yoy.total"] if yoy else [f"ges.q.{tk}.total"]}
    for tab in tabs:
        refs = index_refs.get(tab["id"], [])
        sf.topic_fields(tab, text_refs=refs, headline_refs=refs)
    paragraphs = [tot_text[0], ins_text[0], top_text[0]]

    # Qué mirar
    published = date.fromisoformat(package["published_at"][:10])
    expected = date.fromordinal(published.toordinal() + int(cfg["calendar"]["expected_release_interval_days"]))
    ny, nq = qprev(ty, tq, -1)
    late = (decision or {}).get("late_release")
    watch = [{"headline": f"Casos GES a {sf.month_label(qend(ny, nq))}: publicación atrasada." if late else
              f"Casos GES a {sf.month_label(qend(ny, nq))} (la SIS la publicaría hacia el {sf.day_label(expected)}).",
              "explanation": (f"Lleva {late['days_late']} días de atraso según el calendario histórico." if late else
                              f"Una variación de {yoy_th}% o más frente al mismo trimestre del año anterior marca la ficha como destacada.")}]
    if k["crossing"]:
        r = k["crossing"][0]
        watch.append({"headline": f"{short_label(r['label'], 60)}: {fmt_dec(r['pct'], 1, signed=True)}% a/a.",
                      "explanation": "Un salto en un problema puede venir de un cambio de decreto o de registro; la ficha no infiere la causa."})
    else:
        watch.append({"headline": "Tasa Fonasa por beneficiario.",
                      "explanation": "Se calculará cuando Alicanto capture los beneficiarios de Fonasa del mismo trimestre."})

    notes = [
        {"id": "n1", "text": ("Los casos GES son un flujo, no un stock: la hoja del año del corte (fijada; nunca la de otro año) "
                              "acumula casos desde enero, y el trimestre es la diferencia entre dos cortes del mismo año. "
                              "Los cortes no se suman." if k["measure"] == "ytd" else
                              "Los casos GES son un flujo del trimestre, no un stock; los trimestres no se suman a un stock.")},
        {"id": "n2", "text": ("Tasa bruta: casos del seguro / beneficiarios promedio del mismo seguro en el trimestre × 1.000. "
                              "El denominador Isapre viene de la cartera mensual (F1); Fonasa no tiene denominador capturado y su "
                              "tasa no está disponible. Sin ajuste por edad: no compara riesgo entre seguros.")},
        {"id": "n3", "text": (f"Top problemas: variación frente al mismo trimestre del año anterior; entran los problemas con al menos "
                              f"{fmt_int(tp['min_cases'])} casos en la base y cruzan el umbral los que crecen {fmt_dec(tp['pct'], 0)}% o más.")},
        {"id": "n4", "text": "Ningún dato de esta ficha establece por qué cambian los casos (demanda, decreto, registro o acceso)."},
    ]
    if k["invalid"]:
        notes.append({"id": "n5", "text": "Cortes no usados por no pasar el parser corregido: " +
                      "; ".join(f"{sf.month_label(p)} ({why})" for p, why in sorted(k["invalid"].items())) + "."})
    for d in cfg.get("decree_changes") or []:
        notes.append({"id": f"d{len(notes) + 1}", "text": str(d.get("note"))})

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
        "kicker_meta": tpl["kicker_meta"].format(period_label=qlabel(ty, tq), published_label=sf.day_label(package["published_at"]),
                                                 cadence_phrase=cfg["cadence_phrase"]),
        "headline": headline, "headline_type": head_type, "dek": dek, "dek_emphasis": f"{fmt_int(fon)} casos",
        "kpis": kpis, "tabs": tabs,
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs, "rendered_in_tabs": True},
        "watch": watch[:2], "notes": notes, "sources": sources, "machine_note": machine,
        "featured": bool((decision or {}).get("featured")), "triggers": triggers, "late_release": late,
        "revisions": package.get("revisions") or [],
    }


def _cuts_of(values: dict, key: str) -> list[str]:
    ins = values[f"ges.q.{key}.fonasa"]["inputs"]
    return [i.split(".")[2] for i in ins]


def run(root: Path, *, today: date, registry: dict | None = None, llm: bool = True,
        model_call: Callable[..., Any] | None = None, budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    return sf.run_family(FAMILY, builder_version=BUILDER_VERSION, build_package=build_package, compose=compose, root=Path(root),
                         today=today, registry=registry, llm=llm, model_call=model_call, budget=budget)
