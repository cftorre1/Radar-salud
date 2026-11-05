"""F2 · Resultados financieros de las Isapres (SIS, Estadísticas Financieras 'FEFI'): package, ficha and verification.

Input: ``data/stats_fichas/captures/fefi.json`` (``stats_capture_fefi``): per quarterly release, the workbook's URL,
SHA-256 and the values read through the **reviewed** template (``families.F2.parser_template``): only the sheets
'Ctas. de Resultados I. Abierta' and '… I. Cerradas' (en miles de $, converted to millions by the parser), with their
sheet!cell locators and the 'Isapres = total' check per account (Dirección, 1-nov-2026).

Esencial (Dirección, 1-nov-2026; ``config/editorial_rules_v3.json`` → ``rules.fefi_esencial_exclusion``, which
supersedes the blanket ``holds.fefi_2026_03`` for F2): the ficha shows the other 9 Isapres, every system total is
'sistema sin Esencial' recomputed here from those 9, a note quotes Notas Explicativas!A18 verbatim, and no Esencial
figure enters the package. The rule is conditional on A18: if the latest workbook's note no longer says that Esencial's
figures are under review, the ficha HOLDs so a person re-decides. An Esencial HOLD with no rule still HOLDs everything.

The ficha HOLDs (never publishes) unless the template is reviewed, the parse was made with it and is ``verified``, the
Esencial rule applies and at least three topics are supported. Topics come from a closed list (resultados, ingresos,
costo de ventas, siniestralidad) and appear only when their accounts were read. Year-on-year comparisons need the
workbook of the same quarter one year earlier, captured and verified with the same template; without it the ficha
shows the latest levels only, never an estimated comparison.

Truth rules (data/stats_fichas/PLAYBOOK.md): a result that changes sign gets the absolute change and a 'N/A'
percentage; wording follows the sign; thresholds use the rounded value shown; denominators are stated; decompositions
add up (checked by the parser); counts are evidence cited by the line that uses them.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import figure_templates as ft
from . import stats_capture as cap
from . import stats_capture_fefi as fc
from . import stats_fichas as sf
from .stats_fichas import fmt_dec, fmt_int, value

FAMILY = "F2"
BUILDER_VERSION = "f2_index_topic_v6"  # v5 (3-nov-2026): siniestralidad separada, SIL / cotizaciones, Isapres con pérdida
# v6 (4-nov-2026): margen operacional por beneficiario (denominador: cartera F1 de las mismas Isapres y los mismos meses).
CAPTURE = fc.STORE
EDITORIAL_RULES = Path("config/editorial_rules_v3.json")
ESENCIAL_HOLD = "HOLD_COVERAGE_ESENCIAL"
SYSTEM = "sistema sin Esencial"
TOPICS = {  # topic → accounts it needs (latest period) for every published Isapre
    "resultados": ("Resultados", ("resultado_ejercicio",)),
    "ingresos": ("Ingresos", ("ingresos_operacionales",)),
    "costos": ("Costo de ventas", ("costo_prestaciones", "costo_sil")),
    "gastos": ("Gastos de administración", ("gav", "ingresos_operacionales")),
    "siniestralidad": ("Siniestralidad", ("costo_prestaciones", "costo_sil", "ingresos_operacionales")),
    "sil": ("Licencias (SIL)", ("costo_sil", "cotizacion_legal", "cotizacion_adicional", "ingresos_operacionales")),
}
# Siniestralidad separada (F2 v5, 3-nov-2026): S = S_prest + S_SIL over the same denominator. The split must equal the
# total before any rounding (only float noise allowed), else HOLD.
SPLIT = (("siniestralidad_prest", "costo_prestaciones"), ("siniestralidad_sil", "costo_sil"))
SPLIT_TOL = 1e-9  # percentage points; a/d + b/d vs (a + b)/d in binary floating point
# SIL / cotizaciones: the denominator is fixed and labelled (business review 3-nov-2026): cotización legal (7%) + cotización
# adicional voluntaria of the same accumulated period. Aporte adicional, fondo de compensación and otros are not cotizaciones.
COTIZACIONES = ("cotizacion_legal", "cotizacion_adicional")
# Independent total (review of #136, 4-nov-2026): the sheet's own 'Total costo de ventas' minus its other components must
# equal prestaciones + SIL, per Isapre and period, within 1 miles (0,001 MM$). A template that mapped SIL (or
# prestaciones) to the wrong row would otherwise still pass S_prest + S_SIL = S, which is built from the same two rows.
COSTO_OTHER = ("prestaciones_no_liquidadas", "prestaciones_litigio", "egresos_fondo_compensacion", "otros_costos_operacion")
COSTO_TOL_MM = 0.001 + 1e-9  # 1 miles de $ in MM$, plus float noise
INGRESOS_PARTS = (("cotizacion_legal", "Cotización legal"), ("cotizacion_adicional", "Cot. adicional"),
                  ("aporte_adicional", "Aporte adicional"), ("fondo_compensacion", "Fondo compens."), ("ingresos_otros", "Otros"))
COSTO_PARTS = (("costo_prestaciones", "Prestaciones"), ("costo_sil", "SIL"),
               ("prestaciones_no_liquidadas", "Ocurridas no liq."), ("prestaciones_litigio", "En litigio"),
               ("egresos_fondo_compensacion", "Egresos fondo"), ("otros_costos_operacion", "Otros costos oper."))
GAV_PARTS = (("gav_remuneraciones", "Remuneraciones"), ("gav_remuneraciones_ventas", "Remun. ventas"),
             ("gav_publicidad", "Publicidad"), ("gav_deterioro_cotizaciones", "Deterioro cotiz."),
             ("gav_deterioro_prestamos", "Deter. préstamos"), ("gav_otros", "Otros"))
BRIDGE = (("ganancia_bruta", "Ganancia bruta", 1), ("resultado_antes_impuestos", "Antes de impuestos", 1),
          ("gasto_impuestos", "Impuestos", -1), ("resultado_ejercicio", "Ganancia", 1))
MM = "MM$"
# Result items (Dirección, 2-nov-2026): never a % variation, whatever the base; both levels are shown instead. A small
# positive base makes a valid % misleading ('2.707,6% más' on 1.215 MM$). Ingresos and costos keep their % (positive base).
RESULT_ITEMS = frozenset({"resultado_ejercicio", "resultado_antes_impuestos", "ganancia_bruta"})
MM_DIGITS = 0  # MM$ are displayed as whole numbers (charts: 'digits'; tables: fmt_int); the evidence keeps full precision
# Margen operacional por beneficiario (F2 v6, roadmap increment 4): (ganancia bruta − gastos de administración y otros
# gastos por función) / beneficiarios promedio, in pesos, for the same accumulated months. The denominator is the simple
# mean of the month-end stocks January…t of the same Isapre, read from the F1 cartera capture (one hash, reconciled).
# A period or perimeter that cannot be matched exactly holds that figure (never approximated); the ficha still publishes.
PORTFOLIO = Path("data/market/isapre_portfolio.json")
PRIOR_PORTFOLIO = "data/market/isapre_portfolio_{year}.json"  # previous-year workbooks (market_sources.collect_prior_portfolio)
CARTERA_METRICS = ("beneficiarios", "cotizantes", "cargas")
MARGIN_ITEMS = ("ganancia_bruta", "gav")
GB_TOL_MM = 0.001 + 1e-9  # ganancia bruta = ingresos − costo de ventas, ≤ 1 miles (the parser's own cross-check)


def _rules(root: Path) -> dict | None:
    try:
        return json.loads((Path(root) / EDITORIAL_RULES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def esencial_hold(root: Path) -> str | None:
    """An Esencial coverage HOLD that no F2 rule resolves ('fefi_2026_03: HOLD_COVERAGE_ESENCIAL: …'), or None.
    Fails closed: an unreadable rules file counts as an unresolved HOLD."""
    rules = _rules(root)
    if rules is None:
        return f"editorial_rules_unreadable: {ESENCIAL_HOLD} asumido"
    resolved = {k for k, v in (rules.get("hold_resolutions") or {}).items()
                if isinstance(v, dict) and ((rules.get("rules") or {}).get(v.get("by_rule")) or {}).get("family") == FAMILY}
    for k, v in (rules.get("holds") or {}).items():
        if str(k).startswith("fefi") and isinstance(v, str) and v.startswith(ESENCIAL_HOLD) and k not in resolved:
            return f"{k}: {v}"
    return None


def exclusion_rule(root: Path) -> tuple[str | None, dict | None]:
    for rid, r in ((_rules(root) or {}).get("rules") or {}).items():
        if isinstance(r, dict) and r.get("family") == FAMILY and r.get("action") == "exclude_entity":
            return rid, r
    return None, None


def exclusion_applies(rule: dict, note: dict | None, period: str) -> bool:
    """The rule holds only while the latest workbook's coverage note, at the decided locator, still says what Dirección
    decided on (Esencial's figures under review for that period)."""
    cond = rule.get("condition") or {}
    rx, _ = ft.compile_pattern(cond.get("text_pattern"), subs=ft.period_subs(period))
    if not rx or not note:
        return False
    loc = f"{str(note.get('sheet') or '').strip()}!{note.get('cell')}"
    return ft.normalize_text(loc) == ft.normalize_text(cond.get("locator")) and bool(rx.fullmatch(ft.normalize_text(note.get("text"))))


def change(prev: float, cur: float, *, result: bool) -> dict:
    """Δ and Δ%: a % only for a non-result item with a positive base; a result never gets a % (``RESULT_ITEMS``)."""
    delta = cur - prev
    if result:
        if prev < 0 <= cur:
            kind = "loss_to_profit"
        elif prev >= 0 > cur:
            kind = "profit_to_loss"
        elif prev < 0 and cur < 0:
            kind = "loss_smaller" if abs(cur) < abs(prev) else ("loss_larger" if abs(cur) > abs(prev) else "same")
        else:
            kind = "profit_up" if cur > prev else ("profit_down" if cur < prev else "same")
        pct = None
    else:
        kind = "up" if delta > 0 else ("down" if delta < 0 else "same")
        pct = delta / prev * 100 if prev > 0 else None
    return {"delta": delta, "pct": pct, "transition": kind}


def level_phrase(cur: float) -> str:
    return f"utilidad de {fmt_int(cur)} {MM}" if cur >= 0 else f"pérdida de {fmt_int(abs(cur))} {MM}"


def result_phrase(prev: float, cur: float, when_prev: str) -> str:
    """'utilidad de 34.091 MM$, tras una pérdida de 273 MM$ en marzo 2025': sign-aware, both levels, never a %."""
    c = change(prev, cur, result=True)
    k = c["transition"]
    if k == "loss_to_profit":
        return f"utilidad de {fmt_int(cur)} {MM}, tras una pérdida de {fmt_int(abs(prev))} {MM} en {when_prev}"
    if k == "profit_to_loss":
        return f"pérdida de {fmt_int(abs(cur))} {MM}, tras una utilidad de {fmt_int(prev)} {MM} en {when_prev}"
    if cur < 0:
        word = {"loss_smaller": "menor que", "loss_larger": "mayor que", "same": "igual a"}[k]
        return f"pérdida de {fmt_int(abs(cur))} {MM}, {word} la de {fmt_int(abs(prev))} {MM} en {when_prev}"
    return f"utilidad de {fmt_int(cur)} {MM} frente a {fmt_int(prev)} {MM} en {when_prev}"


def headline_lead(prev: float | None, cur: float, span: str) -> str:
    """Natural, sign-aware headline (Dirección, 2-nov-2026): both levels, never a %, no 'sin Esencial' (that is the
    footnote's job). 'Las Isapres ganan 34.120 MM$ en enero–marzo 2026, frente a 1.215 MM$ un año antes'."""
    verb = f"Las Isapres ganan {fmt_int(cur)} {MM}" if cur >= 0 else f"Las Isapres pierden {fmt_int(abs(cur))} {MM}"
    head = f"{verb} en {span}"
    if prev is None:
        return head
    k = change(prev, cur, result=True)["transition"]
    if k == "loss_to_profit":
        return f"{head}, tras perder {fmt_int(abs(prev))} {MM} un año antes"
    if k == "profit_to_loss":
        return f"{head}, tras ganar {fmt_int(prev)} {MM} un año antes"
    if cur < 0:
        word = {"loss_smaller": "menos que", "loss_larger": "más que", "same": "lo mismo que"}[k]
        return f"{head}, {word} los {fmt_int(abs(prev))} {MM} de un año antes"
    return f"{head}, frente a {fmt_int(prev)} {MM} un año antes"


def loss_phrase(n: int) -> str:
    """'2 Isapres con pérdida' (the count ``sf.COUNT_CLAIM`` checks against ``conteo.isapres_con_perdida``)."""
    return "ninguna Isapre con pérdida" if n == 0 else f"{n} Isapre{'s' if n != 1 else ''} con pérdida"


def scope_note(cell: str, period_label: str, n: int) -> str:
    """The one always-visible footnote on Esencial (Dirección, 2-nov-2026), paraphrasing the A18 note the rule matched."""
    return (f"Cifras del sistema sin Isapre Esencial: según la SIS (nota {cell}), sus cifras a {period_label} están en "
            f"revisión. Los totales suman las otras {n} Isapres.")


def pct_cell(pct: float | None) -> str:
    return "N/A" if pct is None else fmt_dec(pct, 1, signed=True) + "%"


def _closed(root: Path) -> set[str]:
    """Official codes of the closed Isapres (``isapre_type: closed`` in the entity catalog)."""
    try:
        data = json.loads((Path(root) / "data/entities/isapres.json").read_text(encoding="utf-8"))
        return {str(int(e["official_code"])) for e in data["entities"] if e.get("isapre_type") == "closed"}
    except (OSError, ValueError, KeyError):
        return set()


def _names(root: Path) -> dict[str, str]:
    try:
        data = json.loads((Path(root) / "data/entities/isapres.json").read_text(encoding="utf-8"))
        return {str(int(e["official_code"])): e.get("commercial_name") or e.get("legal_name") for e in data["entities"]}
    except (OSError, ValueError, KeyError):
        return {}


def _collect(parse: dict) -> tuple[dict[str, dict[str, tuple[float, str]]], list[str]]:
    """item → code → (value in MM$, 'sheet!cell') across the template's tables (an Isapre appears in one table only).
    The tables' declared 'total' columns are not used: they include Esencial."""
    out: dict[str, dict[str, tuple[float, str]]] = {}
    errs = []
    for tab in (parse.get("tables") or {}).values():
        for fid, f in (tab.get("columns") or {}).items():
            if f.get("period") != "t":
                continue
            for code, x in (tab.get("values") or {}).get(fid, {}).items():
                if code == "total":
                    continue
                if code in out.setdefault(f["item"], {}):
                    errs.append(f"isapre_in_two_tables:{f['item']}:{code}")
                out[f["item"]][code] = (x, f"{tab['sheet'].strip()}!{tab['cells'][fid][code]}")
    return out, errs


def _pct(num: float, den: float) -> float:
    """num / den × 100, at full precision (rounding happens only in the view)."""
    return num / den * 100


def costo_identity_failures(values: dict, codes: list[str], periods: list[str], tol: float = COSTO_TOL_MM) -> list[str]:
    """costo_operacional (the sheet's 'Total costo de ventas' row) − (no liquidadas + litigio + egresos fondo + otros
    costos) == costo de prestaciones + SIL, per Isapre and period. Uses the captured cells only, never a derived total;
    a missing cell is a failure."""
    out = []
    for c in codes:
        for p in periods:
            need = ["costo_operacional", *COSTO_OTHER, "costo_prestaciones", "costo_sil"]
            if any(f"{i}.{c}.{p}" not in values for i in need):
                out.append(f"costo_total_missing:{c}.{p}")
                continue
            V = lambda i: values[f"{i}.{c}.{p}"]["value"]  # noqa: E731
            rest = V("costo_operacional") - sum(V(i) for i in COSTO_OTHER)
            if abs(rest - (V("costo_prestaciones") + V("costo_sil"))) > tol:
                out.append(f"costo_split_mismatch:{c}.{p}")
    return out


def split_identity_failures(values: dict, whos: list[str], periods: list[str], tol: float = SPLIT_TOL) -> list[str]:
    """S_prest + S_SIL must equal the total siniestralidad before rounding, for every Isapre, the system and period.
    The total is recomputed here from its own inputs (costo de prestaciones + SIL over ingresos), not taken from the
    parts. A missing value is a failure too."""
    out = []
    for w in whos:
        for p in periods:
            ids = [f"{k}.{w}.{p}" for k, _ in SPLIT] + [f"siniestralidad.{w}.{p}", f"costo_prestaciones.{w}.{p}",
                                                      f"costo_sil.{w}.{p}", f"ingresos_operacionales.{w}.{p}"]
            if any(i not in values for i in ids):
                out.append(f"siniestralidad_split_missing:{w}.{p}")
                continue
            parts = sum(values[f"{k}.{w}.{p}"]["value"] for k, _ in SPLIT)
            den = values[f"ingresos_operacionales.{w}.{p}"]["value"]
            recomputed = (values[f"costo_prestaciones.{w}.{p}"]["value"] + values[f"costo_sil.{w}.{p}"]["value"]) / den * 100
            if abs(parts - values[f"siniestralidad.{w}.{p}"]["value"]) > tol or abs(parts - recomputed) > tol:
                out.append(f"siniestralidad_split_mismatch:{w}.{p}")
    return out


def average_beneficiaries(root: Path, codes: list[str], period: str) -> tuple[dict | None, str | None]:
    """Month-end beneficiaries January…``period`` of each Isapre in ``codes``, from the F1 cartera capture of that year
    (the current file, else ``isapre_portfolio_<año>.json``), or (None, reason). Exact match only: one https URL and one
    SHA-256; every month present with the 10 official codes, integer counts, cotizantes + cargas = beneficiarios and
    Σ Isapres = the declared 'Total Sistema'; every Isapre of the ficha present in every month."""
    year, month = sf.period_parts(period)
    months = [f"{year}-{m:02d}" for m in range(1, month + 1)]
    for path in (PORTFOLIO, Path(PRIOR_PORTFOLIO.format(year=year))):
        port = cap._load(Path(root) / path, None)
        if not port:
            continue
        obs = [o for o in port.get("observations") or [] if o.get("metric_id") in CARTERA_METRICS]
        if not any(str(o.get("period") or "").startswith(f"{year}-") for o in obs):
            continue
        shas, urls = {o.get("source_sha256") for o in obs}, {o.get("source_url") for o in obs}
        if len(shas) != 1 or len(urls) != 1:
            return None, "cartera_mixed_release"
        sha, url = next(iter(shas)), next(iter(urls))
        if not sf.HEX64.fullmatch(str(sha or "")) or not str(url or "").startswith("https://"):
            return None, "cartera_sin_hash"
        grid: dict[tuple[str, str], dict[str, dict]] = {}
        for o in obs:
            grid.setdefault((o["period"], str(int(o["official_code"]))), {})[o["metric_id"]] = o
        declared = {c.get("period"): c.get("total_beneficiaries") for c in port.get("coverage") or []}
        cells: dict[str, dict[str, tuple[int, str]]] = {c: {} for c in codes}
        for m in months:
            here = {c for (p, c) in grid if p == m}
            if not here:
                return None, f"cartera_sin_mes:{m}"
            if len(here) != 10:
                return None, f"cartera_codigos:{m}"
            if set(codes) - here:
                return None, f"perimetro_distinto:{m}:{','.join(sorted(set(codes) - here, key=int))}"
            total = 0
            for c in here:
                cell = grid[(m, c)]
                vals = {k: (cell.get(k) or {}).get("value") for k in CARTERA_METRICS}
                if any(not isinstance(x, int) or isinstance(x, bool) or x < 0 for x in vals.values()):
                    return None, f"cartera_conteo:{m}:{c}"
                if vals["cotizantes"] + vals["cargas"] != vals["beneficiarios"]:
                    return None, f"cartera_cot_mas_cargas:{m}:{c}"
                total += vals["beneficiarios"]
                if c in cells:
                    o = cell["beneficiarios"]
                    cells[c][m] = (vals["beneficiarios"], f"{o.get('sheet')}!E{o.get('source_row')}")
            if declared.get(m) != total:
                return None, f"cartera_total:{m}"
        return {"url": url, "sha256": sha, "published_at": port.get("published_at"), "months": months, "cells": cells,
                "fetched_at": max((o.get("fetched_at") or "") for o in obs) or None, "year": year}, None
    return None, f"cartera_{year}_no_capturada"


def money(x: float) -> str:
    """Pesos, whole, sign-aware: '$48.120', '−$3.210'."""
    return ("−" if round(x) < 0 else "") + "$" + fmt_int(abs(x))


def _hold(package: dict, failures: list[str], topics: list[str] | None = None) -> dict:
    package["reconciliation"].update(ok=False, failures=failures)
    package.update(findings=[], kpis={}, revisions=[], constants=[], topics=topics or [])
    return package


def build_package(root: Path, registry: dict | None = None, previous_live: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    root = Path(root)
    store = cap._load(root / CAPTURE, None)
    if not store or not store.get("releases"):
        raise ValueError("fefi_capture_missing")
    template = cfg.get("parser_template") or {}
    tpl_state = ft.review_state(template)
    tpl_sha = ft.templates_sha256(template)
    rel = max(store["releases"], key=lambda r: r["period"])
    doc = rel.get("document") or {}
    parse = doc.get("parse") or {}
    t = rel["period"]
    t1 = sf.shift_period(t, -12)
    failures: list[str] = []
    if tpl_state != "ok":
        failures.append(f"parser_template_{tpl_state}")
    if doc.get("status") == "hash_mismatch":
        failures.append("sha256_mismatch_on_recheck")
    elif doc.get("status") != "captured" or not sf.HEX64.fullmatch(str(doc.get("sha256") or "")):
        failures.append(f"not_captured:{doc.get('status')}")
    elif parse.get("status") != "verified":
        failures.append(f"parse_{parse.get('status')}")
    elif parse.get("template_sha256") != tpl_sha:
        failures.append("parse_made_with_another_template")
    hold = esencial_hold(root)
    rule_id, rule = exclusion_rule(root)
    excluded: set[str] = set()
    if hold:
        failures.append(f"{ESENCIAL_HOLD}:{hold.split(':')[0]}")
    elif rule:
        excluded = {str(rule.get("entity_code"))}
        if not failures and not exclusion_applies(rule, parse.get("coverage_note"), t):
            failures.append(f"esencial_exclusion_condition_not_met:{(rule.get('condition') or {}).get('locator')}")
    values: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    package: dict[str, Any] = {
        "family": FAMILY, "period": t, "periods": [t], "published_at": rel.get("published_at"),
        "release_key": sf.release_key(t, doc.get("sha256") or "0" * 16),
        "primary_source": {"url": doc.get("url"), "sha256": doc.get("sha256")}, "sources": sources, "values": values,
        "entities": [], "entity_codes": [], "entity_keys": [], "causal_note": None, "provisional": False,
        "esencial_hold": hold, "exclusion_rule": rule_id if rule and not hold else None, "excluded_codes": sorted(excluded),
        "parser_template_state": tpl_state,
        "reconciliation": {"ok": False, "failures": failures, "checks": [
            "plantilla de hojas, encabezado, columnas de Isapre y cuentas revisada por una persona (sin marcadores <<…>>)",
            "solo hojas 'en miles de $'; una hoja 'en millones de $' o con magnitudes mezcladas (> ×100) se rechaza",
            "la planilla capturada conserva su SHA-256 y se leyó con esa misma plantilla",
            "cada patrón calza exactamente una vez en el texto normalizado",
            "en cada cuenta las Isapres suman la columna total (tolerancia ≤ 1 miles) y los componentes suman su total",
            "Esencial: excluida por regla de Dirección mientras la nota A18 diga que sus cifras están en revisión; si no, HOLD",
            "comparación a/a solo con la planilla del año anterior verificada con la misma plantilla",
            "al menos tres temas con datos verificados",
            "siniestralidad separada: prestaciones/ingresos + SIL/ingresos = siniestralidad total antes de redondear; si no, HOLD",
            "prestaciones + SIL = total costo de ventas de la hoja − (no liquidadas + litigio + egresos fondo + otros costos), "
            "por Isapre y período, ≤ 1 miles; si no, HOLD",
            "denominadores > 0 (ingresos; cotización legal + adicional para SIL / cotizaciones); si no, HOLD"]},
        "lectura_pool": [], "derived_ratios": [], "ranks": [],
    }
    if failures:
        return _hold(package, failures)

    names = _names(root)
    cur, errs = _collect(parse)
    failures += errs
    codes = sorted({c for by in cur.values() for c in by} - excluded, key=int)
    missing = [c for c in codes if not names.get(c)]
    if missing:
        failures.append("entity_name_missing:" + ",".join(missing))
    # Year on year: the same quarter one year earlier, verified with the same template (never estimated).
    prev_rel = next((r for r in store["releases"] if r["period"] == t1), None)
    pdoc = (prev_rel or {}).get("document") or {}
    pparse = pdoc.get("parse") or {}
    prev: dict = {}
    if (pdoc.get("status") == "captured" and pparse.get("status") == "verified" and pparse.get("template_sha256") == tpl_sha
            and sf.HEX64.fullmatch(str(pdoc.get("sha256") or ""))):
        prev, perrs = _collect(pparse)
        prev = {} if perrs else prev
    complete = {item for item, by in cur.items() if all(c in by for c in codes)}
    yoy = {item for item, by in prev.items() if item in complete and all(c in by for c in codes)}
    for item in complete:
        for code in codes:
            x, loc = cur[item][code]
            values[f"{item}.{code}.{t}"] = value(f"{item}.{code}.{t}", x, unit=MM, period=t, source="fefi", locator=loc)
    for item in yoy:
        for code in codes:
            x, loc = prev[item][code]
            values[f"{item}.{code}.{t1}"] = value(f"{item}.{code}.{t1}", x, unit=MM, period=t1, source="fefi_prev", locator=loc)
    topics = [tid for tid, (_, need) in TOPICS.items() if all(i in complete for i in need)]
    if len(topics) < 3:
        failures.append(f"topics_under_3:{','.join(topics) or 'ninguno'}")
    if failures:
        return _hold(package, failures, topics)
    package["reconciliation"].update(ok=True, failures=[])

    sheets = sorted({tab["sheet"].strip() for tab in (parse.get("tables") or {}).values()})
    sources["fefi"] = sf.source_ref(url=doc["url"], sha256=doc["sha256"], published_at=rel.get("published_at"),
                                    fetched_at=doc.get("fetched_at"),
                                    label=f"SIS · Estadísticas financieras del sistema Isapre a {sf.month_label(t)} ({doc.get('format')})",
                                    role="hojas en miles de $ leídas con la plantilla revisada; Isapres = total por cuenta",
                                    locator="hojas: " + ", ".join(sheets))
    if yoy:
        sources["fefi_prev"] = sf.source_ref(url=pdoc["url"], sha256=pdoc["sha256"], published_at=prev_rel.get("published_at"),
                                             fetched_at=pdoc.get("fetched_at"),
                                             label=f"SIS · Estadísticas financieras del sistema Isapre a {sf.month_label(t1)} ({pdoc.get('format')})",
                                             role="mismo trimestre del año anterior, misma plantilla", locator="hojas: " + ", ".join(sheets))
    V = lambda vid: values[vid]["value"]  # noqa: E731

    def derived(vid, val, formula, inputs, unit, period=t):
        values[vid] = value(vid, val, unit=unit, period=period, source=None, formula=formula, inputs=inputs, kind="derived")
        return val

    def periods_for(items) -> list[str]:
        return [t, t1] if set(items) <= yoy else [t]

    for item in sorted(complete):
        for p in periods_for([item]):
            ids = [f"{item}.{c}.{p}" for c in codes]
            derived(f"{item}.sistema.{p}", sum(V(i) for i in ids), f"Σ de las {len(codes)} Isapres publicadas"
                    + (f" ({SYSTEM})" if excluded else ""), ids, MM, p)
    whos = [*codes, "sistema"]
    derived("conteo.isapres", len(codes), "Isapres publicadas", [], "count")
    findings = []
    salud = ("costo_prestaciones", "costo_sil")
    if set(salud) <= complete:
        for w in whos:
            for p in periods_for(salud):
                derived(f"costo_salud.{w}.{p}", V(f"costo_prestaciones.{w}.{p}") + V(f"costo_sil.{w}.{p}"),
                        "costo de prestaciones + SIL", [f"costo_prestaciones.{w}.{p}", f"costo_sil.{w}.{p}"], MM, p)
    if "siniestralidad" in topics:
        s_pers = periods_for([*salud, "ingresos_operacionales"])
        costo_errs = costo_identity_failures(values, codes, s_pers)
        if costo_errs:
            return _hold(package, costo_errs, topics)
        for w in whos:
            for p in s_pers:
                den = V(f"ingresos_operacionales.{w}.{p}")
                if den <= 0:
                    return _hold(package, [f"siniestralidad_denominator_not_positive:{w}.{p}"], topics)
                derived(f"siniestralidad.{w}.{p}", _pct(V(f"costo_salud.{w}.{p}"), den),
                        "(costo de prestaciones + SIL) / total ingresos de actividades ordinarias × 100",
                        [f"costo_salud.{w}.{p}", f"ingresos_operacionales.{w}.{p}"], "%", p)
                for key, item in SPLIT:
                    derived(f"{key}.{w}.{p}", _pct(V(f"{item}.{w}.{p}"), den),
                            f"{item} / total ingresos de actividades ordinarias × 100",
                            [f"{item}.{w}.{p}", f"ingresos_operacionales.{w}.{p}"], "%", p)
            if t1 in s_pers:
                for key in ("siniestralidad", *(k for k, _ in SPLIT)):
                    derived(f"{key}.{w}.pp", round(V(f"{key}.{w}.{t}"), 1) - round(V(f"{key}.{w}.{t1}"), 1),
                            f"redondeo({key} t, 1) − redondeo({key} t−12, 1)", [f"{key}.{w}.{t}", f"{key}.{w}.{t1}"], "pp")
        split_errs = split_identity_failures(values, whos, s_pers)
        if split_errs:
            return _hold(package, split_errs, topics)
        if t1 in s_pers:  # threshold on the rounded value shown (89,96 → '90,0%' crosses 90); needs the previous year
            levels = (cfg["kpis"]["siniestralidad"].get("threshold") or {}).get("levels_pct") or []
            s_t, s_1 = round(V(f"siniestralidad.sistema.{t}"), 1), round(V(f"siniestralidad.sistema.{t1}"), 1)
            for lvl in levels:
                if (s_t >= lvl) != (s_1 >= lvl):
                    findings.append({"type": "threshold_crossed", "kpi": "siniestralidad", "level": lvl, "crossed": True, "strength": 1.0})
    if "sil" in topics:
        c_pers = periods_for(["costo_sil", *COTIZACIONES])
        for w in whos:
            for p in c_pers:
                ids = [f"{i}.{w}.{p}" for i in COTIZACIONES]
                cot = derived(f"cotizaciones.{w}.{p}", sum(V(i) for i in ids), "cotización legal + cotización adicional voluntaria",
                              ids, MM, p)
                if cot <= 0:
                    return _hold(package, [f"sil_cotizaciones_denominator_not_positive:{w}.{p}"], topics)
                if "aporte_adicional" in complete and p == t:
                    derived(f"aporte_share.{w}.{p}", _pct(V(f"aporte_adicional.{w}.{p}"), V(f"ingresos_operacionales.{w}.{p}")),
                            "aporte adicional / total ingresos de actividades ordinarias × 100",
                            [f"aporte_adicional.{w}.{p}", f"ingresos_operacionales.{w}.{p}"], "%", p)
                derived(f"sil_cotizaciones.{w}.{p}", _pct(V(f"costo_sil.{w}.{p}"), cot),
                        "subsidios por incapacidad laboral / (cotización legal + cotización adicional voluntaria) × 100",
                        [f"costo_sil.{w}.{p}", f"cotizaciones.{w}.{p}"], "%", p)
            if t1 in c_pers:
                derived(f"sil_cotizaciones.{w}.pp", round(V(f"sil_cotizaciones.{w}.{t}"), 1) - round(V(f"sil_cotizaciones.{w}.{t1}"), 1),
                        "redondeo(sil_cotizaciones t, 1) − redondeo(sil_cotizaciones t−12, 1)",
                        [f"sil_cotizaciones.{w}.{t}", f"sil_cotizaciones.{w}.{t1}"], "pp")
    if "gastos" in topics:
        for w in whos:
            derived(f"gav_pct.{w}.{t}", V(f"gav.{w}.{t}") / V(f"ingresos_operacionales.{w}.{t}") * 100,
                    "gastos de administración / total ingresos de actividades ordinarias × 100",
                    [f"gav.{w}.{t}", f"ingresos_operacionales.{w}.{t}"], "%")
    if "ingresos" in topics and "cotizacion_legal" in complete:
        derived("cotizacion_legal.sistema.share", V(f"cotizacion_legal.sistema.{t}") / V(f"ingresos_operacionales.sistema.{t}") * 100,
                "cotización legal / total ingresos de actividades ordinarias × 100",
                [f"cotizacion_legal.sistema.{t}", f"ingresos_operacionales.sistema.{t}"], "%")
    for item in sorted(yoy & {"ingresos_operacionales", "resultado_ejercicio"}):
        res = item in RESULT_ITEMS
        for w in whos:
            c = change(V(f"{item}.{w}.{t1}"), V(f"{item}.{w}.{t}"), result=res)
            derived(f"{item}.{w}.delta", c["delta"], f"{item}(t) − {item}(t−12)", [f"{item}.{w}.{t}", f"{item}.{w}.{t1}"], MM)
            if c["pct"] is not None:
                derived(f"{item}.{w}.pct", c["pct"], "Δ / valor(t−12) × 100 (solo base positiva; nunca para un resultado)",
                        [f"{item}.{w}.delta", f"{item}.{w}.{t1}"], "%")
        if res and change(V(f"{item}.sistema.{t1}"), V(f"{item}.sistema.{t}"), result=True)["transition"] in ("loss_to_profit", "profit_to_loss"):
            findings.append({"type": "sign_change", "kpi": "resultado", "crossed": True, "strength": 1.0})
    if "resultados" in topics:
        derived("conteo.isapres_con_utilidad", sum(1 for c in codes if V(f"resultado_ejercicio.{c}.{t}") > 0),
                "Isapres con resultado > 0", [f"resultado_ejercicio.{c}.{t}" for c in codes], "count")
        derived("conteo.isapres_con_perdida", sum(1 for c in codes if V(f"resultado_ejercicio.{c}.{t}") < 0),
                "Isapres con resultado del ejercicio < 0 (pérdida), acumulado del año", [f"resultado_ejercicio.{c}.{t}" for c in codes], "count")
    for vid in ("conteo.isapres", "conteo.isapres_con_utilidad", "conteo.isapres_con_perdida"):
        if vid in values:
            package["derived_ratios"].append({"id": vid, "value": V(vid), "unit": "count", "entity": None, "signed": False,
                                              "periods": [t], "requires_period": False, "formula": values[vid]["formula"],
                                              "inputs": [], "scope": "system", "period_kind": "ytd", "trivial": True, "base": None})
    # Margen operacional por beneficiario (v6): numerator from this workbook, denominator from the F1 cartera capture.
    margin_periods, margin_holds = [], []
    if "resultados" in topics and set(MARGIN_ITEMS) <= complete:
        for p in periods_for(MARGIN_ITEMS):
            base, why = average_beneficiaries(root, codes, p)
            gb_errs = [c for c in codes if not all(f"{i}.{c}.{p}" in values for i in ("ingresos_operacionales", "costo_operacional"))
                       or abs(V(f"ganancia_bruta.{c}.{p}") - (V(f"ingresos_operacionales.{c}.{p}") - V(f"costo_operacional.{c}.{p}"))) > GB_TOL_MM]
            if not base or gb_errs:
                margin_holds.append({"period": p, "reason": why or f"ganancia_bruta_no_cuadra:{','.join(gb_errs)}"})
                continue
            key = "cartera" if p == t else "cartera_prev"
            sources[key] = sf.source_ref(url=base["url"], sha256=base["sha256"], published_at=base["published_at"],
                                         fetched_at=base["fetched_at"],
                                         label=f"SIS · Estadística mensual de cartera de beneficiarios {base['year']} (xlsx)",
                                         role=f"denominador del margen por beneficiario: beneficiarios a fin de mes, "
                                              f"enero–{sf.month_name(p)} {p[:4]}",
                                         locator="hojas mensuales!E · fila de cada Isapre")
            for c in codes:
                for m in base["months"]:
                    x, loc = base["cells"][c][m]
                    values[f"cartera.{c}.beneficiarios.{m}"] = value(f"cartera.{c}.beneficiarios.{m}", x, unit="personas", period=m,
                                                                     source=key, locator=loc)
                ids = [f"cartera.{c}.beneficiarios.{m}" for m in base["months"]]
                derived(f"benef_prom.{c}.{p}", sum(V(i) for i in ids) / len(ids),
                        f"promedio simple de los stocks a fin de mes, enero–{sf.month_name(p)}", ids, "personas", p)
            derived(f"benef_prom.sistema.{p}", sum(V(f"benef_prom.{c}.{p}") for c in codes),
                    f"Σ beneficiarios promedio de las {len(codes)} Isapres publicadas", [f"benef_prom.{c}.{p}" for c in codes], "personas", p)
            for w in whos:
                if V(f"benef_prom.{w}.{p}") <= 0:
                    return _hold(package, [f"margen_denominator_not_positive:{w}.{p}"], topics)
                op = derived(f"resultado_operacional.{w}.{p}", V(f"ganancia_bruta.{w}.{p}") - V(f"gav.{w}.{p}"),
                             "ganancia bruta − gastos de administración y otros gastos por función",
                             [f"ganancia_bruta.{w}.{p}", f"gav.{w}.{p}"], MM, p)
                derived(f"margen_beneficiario.{w}.{p}", op * 1_000_000 / V(f"benef_prom.{w}.{p}"),
                        "resultado operacional (MM$ × 1.000.000) / beneficiarios promedio del mismo período",
                        [f"resultado_operacional.{w}.{p}", f"benef_prom.{w}.{p}"], "$", p)
            margin_periods.append(p)
        if margin_periods:
            package["reconciliation"]["checks"].append(
                "margen por beneficiario: mismas Isapres y mismos meses (enero–t) en la cartera F1 (un hash; 10 códigos; "
                "cotizantes + cargas = beneficiarios; Σ = Total Sistema); ganancia bruta = ingresos − costo de ventas (≤ 1 miles); "
                "si no calza, esa cifra se retiene")
        if t in margin_periods and t1 in margin_periods:
            for w in whos:
                derived(f"margen_beneficiario.{w}.delta", V(f"margen_beneficiario.{w}.{t}") - V(f"margen_beneficiario.{w}.{t1}"),
                        "margen(t) − margen(t−12) (sin variación %: es un resultado)",
                        [f"margen_beneficiario.{w}.{t}", f"margen_beneficiario.{w}.{t1}"], "$")
    package["margin"] = {"periods": margin_periods, "holds": margin_holds}
    note = parse.get("coverage_note") or {}
    package["entities"] = [{"code": int(c), "name": names[c]} for c in codes]
    package["entity_codes"] = [int(c) for c in codes]
    package.update(findings=findings, topics=topics, periods=[t1, t] if yoy else [t],
                   revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
                   constants=[100, 12, *((cfg["kpis"]["siniestralidad"].get("threshold") or {}).get("levels_pct") or [])],
                   kpis={"t1": t1, "yoy": sorted(yoy), "codes": codes, "names": {c: names[c] for c in codes},
                         "closed": sorted(set(codes) & _closed(root), key=int),
                         "complete": sorted(complete), "excluded": sorted(excluded),
                         "coverage_note": ({"locator": f"{str(note.get('sheet') or '').strip()}!{note.get('cell')}", "text": note.get("text")}
                                           if excluded else None),
                         "rule": rule if excluded else None})
    return package


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    v = package["values"]
    k = package["kpis"]
    t, t1 = package["period"], k["t1"]
    codes, names, yoy, complete = k["codes"], k["names"], set(k["yoy"]), set(k["complete"])
    closed = set(k.get("closed") or [])
    V = lambda vid: v[vid]["value"]  # noqa: E731
    has = lambda vid: vid in v  # noqa: E731
    month, mlabel, plabel = sf.month_name(t), sf.month_label(t), sf.month_label(t1)
    ytd = f"enero–{month}"
    short = lambda p: f"{sf.month_short(p)} {p[:4]}"  # noqa: E731
    topics = package["topics"]
    excl = bool(k["excluded"])
    sys_row = "Sistema sin Esencial" if excl else "Sistema"  # 'Ver datos' total row: names what it sums
    sin = ", sin Esencial" if excl else ""  # chart subtitles where a system total is drawn; nowhere else (Dirección, 2-nov)
    # KPI labels and index lines carry no Esencial label: the footnote (scope_note) covers the whole ficha.
    kpis, tabs, paragraphs = [], [], []

    def order(item: str) -> list[str]:
        return sorted(codes, key=lambda c: (-V(f"{item}.{c}.{t}"), names[c]))

    def cmp_line(item: str) -> str:
        if item not in yoy:
            return f"{ytd} {t[:4]}; sin comparación a/a"
        prev_level = f"{plabel}: {fmt_int(V(f'{item}.sistema.{t1}'))} {MM}"
        if item in RESULT_ITEMS:  # both levels, never a %
            return prev_level
        c = change(V(f"{item}.sistema.{t1}"), V(f"{item}.sistema.{t}"), result=False)
        return f"{prev_level} · variación % " + (pct_cell(c["pct"]) if c["pct"] is not None else "N/A (base no positiva)")

    def cmp_refs(item: str) -> list[str]:
        if item not in yoy:
            return []
        return [f"{item}.sistema.{t1}"] + ([f"{item}.sistema.pct"] if has(f"{item}.sistema.pct") else [])

    if "resultados" in topics:
        R = V(f"resultado_ejercicio.sistema.{t}")
        n_loss = int(V("conteo.isapres_con_perdida"))
        ry = "resultado_ejercicio" in yoy
        kpis.append({"id": "resultado", "label": "Resultado del ejercicio", "value": f"{fmt_int(R)} {MM}", "prov": "C",
                     "lines": [cmp_line("resultado_ejercicio")],
                     "refs": [f"resultado_ejercicio.sistema.{t}"] + cmp_refs("resultado_ejercicio")})
        charts = []
        bridge = [(i, lab, sg) for i, lab, sg in BRIDGE if i in complete]
        if not ry and len(bridge) == len(BRIDGE):  # levels only: from ganancia bruta to the result, same period
            charts.append({"id": "f2-resultado-puente", "form": "diverging", "unit": MM, "digits": MM_DIGITS, "headline": "De la ganancia bruta al resultado",
                           "subtitle": f"Millones de pesos, {ytd} {t[:4]}{sin}",
                           "rows": [{"label": lab, "value": sg * V(f"{i}.sistema.{t}"), "ref": f"{i}.sistema.{t}", "sign": sg,
                                     "emphasis": i == "resultado_ejercicio"} for i, lab, sg in bridge],
                           "table": {"columns": ["Concepto", MM],
                                     "rows": [[lab, fmt_int(sg * V(f"{i}.sistema.{t}"))] for i, lab, sg in bridge]},
                           "source": "SIS, estado de resultados por función (miles de $ convertidos a millones). El tramo entre ganancia bruta y "
                                     "resultado antes de impuestos incluye gastos de administración y otros ítems."})
        if ry:
            R1 = V(f"resultado_ejercicio.sistema.{t1}")
            charts.append({"id": "f2-resultado", "form": "diverging", "unit": MM, "digits": MM_DIGITS, "headline": "Resultado del ejercicio de las Isapres",
                           "subtitle": f"Millones de pesos, {ytd} de cada año{sin}",
                           "rows": [{"label": short(t1), "value": R1, "ref": f"resultado_ejercicio.sistema.{t1}"},
                                    {"label": short(t), "value": R, "ref": f"resultado_ejercicio.sistema.{t}", "emphasis": True}],
                           "table": {"columns": ["Período", f"Resultado ({MM})"],
                                     "rows": [[short(t1), fmt_int(R1)], [short(t), fmt_int(R)],
                                              ["Cambio", sf.fmt_signed(V("resultado_ejercicio.sistema.delta"))]]},
                           "source": "SIS. Los resultados se comparan por niveles y cambio absoluto, sin variación %."})

        mg = has(f"margen_beneficiario.sistema.{t}")

        def rrow(w, lab):
            out = [lab, fmt_int(V(f"resultado_ejercicio.{w}.{t}"))]
            if ry:
                out += [fmt_int(V(f"resultado_ejercicio.{w}.{t1}")), sf.fmt_signed(V(f"resultado_ejercicio.{w}.delta"))]
            if mg:  # margen operacional por beneficiario (v6), same months, in «Ver datos»
                out += [fmt_int(V(f"resultado_operacional.{w}.{t}")), fmt_int(V(f"benef_prom.{w}.{t}")),
                        money(V(f"margen_beneficiario.{w}.{t}"))]
            return out
        ordr = order("resultado_ejercicio")
        charts.append({"id": "f2-resultado-isapres", "form": "diverging", "unit": MM, "digits": MM_DIGITS, "headline": "Resultado por Isapre",
                       "subtitle": f"Millones de pesos, {ytd} {t[:4]}",
                       "rows": [{"label": names[c], "value": V(f"resultado_ejercicio.{c}.{t}"), "ref": f"resultado_ejercicio.{c}.{t}",
                                 "emphasis": V(f"resultado_ejercicio.{c}.{t}") < 0} for c in ordr],
                       "table": {"columns": ["Isapre", short(t)] + ([short(t1), "Cambio"] if ry else [])
                                 + ([f"Res. operacional ({MM})", "Benef. promedio", "$ por benef."] if mg else []),
                                 "rows": [rrow(c, names[c]) for c in ordr] + [rrow("sistema", sys_row)]},
                       "source": "SIS. Totales calculados por Alicanto con las Isapres publicadas."
                                 + (" Margen por beneficiario: resultado operacional / beneficiarios promedio (cartera SIS)." if mg else "")})
        tab = {"id": "resultados", "label": "Resultados", "charts": charts, "text": [], "dek": None}
        topic_kpis = []
        if mg:
            M, BP = V(f"margen_beneficiario.sistema.{t}"), V(f"benef_prom.sistema.{t}")
            m_yoy = has(f"margen_beneficiario.sistema.{t1}")
            m_lines = [f"{ytd} {t[:4]}; {fmt_int(BP)} beneficiarios promedio"]
            m_refs = [f"margen_beneficiario.sistema.{t}", f"benef_prom.sistema.{t}"]
            if m_yoy:
                m_lines.append(f"{plabel}: {money(V(f'margen_beneficiario.sistema.{t1}'))}")
                m_refs.append(f"margen_beneficiario.sistema.{t1}")
            elif ry:  # the workbook a year earlier is verified, its denominator is not: never estimated
                m_lines.append("a/a pendiente")
            topic_kpis.append({"id": "tema-margen", "label": "Margen por beneficiario", "value": money(M), "prov": "C",
                               "lines": m_lines, "refs": m_refs})
        sf.topic_fields(tab, f"{fmt_int(R)} {MM} · {loss_phrase(n_loss)}",
                        index_refs=[f"resultado_ejercicio.sistema.{t}", "conteo.isapres_con_perdida"], kpis=topic_kpis)
        tabs.append(tab)
        paragraphs.append(f"Entre enero y {month}, las Isapres registraron una "
                          + (result_phrase(V(f"resultado_ejercicio.sistema.{t1}"), R, plabel) if ry else level_phrase(R)) + ".")
    if "ingresos" in topics:
        I = V(f"ingresos_operacionales.sistema.{t}")
        kpis.append({"id": "ingresos", "label": "Ingresos", "value": f"{fmt_int(I)} {MM}", "prov": "C",
                     "lines": [cmp_line("ingresos_operacionales")],
                     "refs": [f"ingresos_operacionales.sistema.{t}"] + cmp_refs("ingresos_operacionales")})
        parts = [(i, lab) for i, lab in INGRESOS_PARTS if i in complete]
        charts = []
        comp_rows = [{"label": lab, "value": V(f"{i}.sistema.{t}"), "ref": f"{i}.sistema.{t}", "emphasis": i == "cotizacion_legal"}
                     for i, lab in parts if V(f"{i}.sistema.{t}") != 0]
        if len(comp_rows) >= 2:  # stock of the period first: where the income comes from
            charts.append({"id": "f2-ingresos-composicion", "form": "bars", "unit": MM, "digits": MM_DIGITS, "headline": "De dónde vienen los ingresos",
                           "subtitle": f"Millones de pesos, {ytd} {t[:4]}{sin}", "rows": comp_rows,
                           "table": {"columns": ["Componente", MM],
                                     "rows": [[lab, fmt_int(V(f"{i}.sistema.{t}"))] for i, lab in parts] + [["Total ingresos", fmt_int(I)]]},
                           "source": "SIS, apertura de cuentas de resultados (miles de $ convertidos a millones). Los componentes suman el total."})
        ordr = order("ingresos_operacionales")
        charts.append({"id": "f2-ingresos-isapres", "form": "bars", "unit": MM, "digits": MM_DIGITS, "headline": "Ingresos por Isapre",
                       "subtitle": f"Total ingresos de actividades ordinarias, millones de pesos, {ytd} {t[:4]}",
                       "rows": [{"label": names[c], "value": V(f"ingresos_operacionales.{c}.{t}"), "ref": f"ingresos_operacionales.{c}.{t}"} for c in ordr],
                       "table": {"columns": ["Isapre", "Total"] + [lab for _, lab in parts],
                                 "rows": [[names[c], fmt_int(V(f"ingresos_operacionales.{c}.{t}"))] + [fmt_int(V(f"{i}.{c}.{t}")) for i, _ in parts]
                                          for c in ordr]
                                 + [[sys_row, fmt_int(I)] + [fmt_int(V(f"{i}.sistema.{t}")) for i, _ in parts]]},
                       "source": "SIS. Totales calculados por Alicanto con las Isapres publicadas."})
        tab = {"id": "ingresos", "label": "Ingresos", "charts": charts, "text": [], "dek": None}
        pct = has("ingresos_operacionales.sistema.pct")
        line = (f"{fmt_int(I)} {MM} · {pct_cell(V('ingresos_operacionales.sistema.pct'))} vs. {plabel}" if pct
                else f"{fmt_int(I)} {MM} entre enero y {month}")
        sf.topic_fields(tab, line, index_refs=[f"ingresos_operacionales.sistema.{t}"] + (["ingresos_operacionales.sistema.pct"] if pct else []),
                        kpis=[])
        tabs.append(tab)
    if "costos" in topics:
        CS = V(f"costo_salud.sistema.{t}")
        kpis.append({"id": "costo_salud", "label": "Prestaciones y SIL", "value": f"{fmt_int(CS)} {MM}", "prov": "C",
                     "lines": [f"prestaciones {fmt_int(V(f'costo_prestaciones.sistema.{t}'))} · SIL {fmt_int(V(f'costo_sil.sistema.{t}'))}"],
                     "refs": [f"costo_salud.sistema.{t}", f"costo_prestaciones.sistema.{t}", f"costo_sil.sistema.{t}"]})
        parts = [(i, lab) for i, lab in COSTO_PARTS if i in complete]
        signed = any(V(f"{i}.sistema.{t}") < 0 for i, _ in parts)
        ordr = order("costo_salud")
        charts = [{"id": "f2-costos-composicion", "form": "diverging" if signed else "bars", "unit": MM, "digits": MM_DIGITS,
                   "headline": "Costo de ventas por componente", "subtitle": f"Millones de pesos, {ytd} {t[:4]}{sin}",
                   "rows": [{"label": lab, "value": V(f"{i}.sistema.{t}"), "ref": f"{i}.sistema.{t}", "emphasis": i == "costo_prestaciones"}
                            for i, lab in parts],
                   "table": {"columns": ["Componente", MM], "rows": [[lab, fmt_int(V(f"{i}.sistema.{t}"))] for i, lab in parts]
                             + ([["Total costo de ventas", fmt_int(V(f"costo_operacional.sistema.{t}"))]] if "costo_operacional" in complete else [])},
                   "source": "SIS, apertura de cuentas de resultados. Los componentes suman el total del costo de ventas."},
                  {"id": "f2-costos-isapres", "form": "bars", "unit": MM, "digits": MM_DIGITS, "headline": "Prestaciones y SIL por Isapre",
                   "subtitle": f"Millones de pesos, {ytd} {t[:4]}",
                   "rows": [{"label": names[c], "value": V(f"costo_salud.{c}.{t}"), "ref": f"costo_salud.{c}.{t}"} for c in ordr],
                   "table": {"columns": ["Isapre"] + [lab for _, lab in parts],
                             "rows": [[names[c]] + [fmt_int(V(f"{i}.{c}.{t}")) for i, _ in parts] for c in ordr]
                             + [[sys_row] + [fmt_int(V(f"{i}.sistema.{t}")) for i, _ in parts]]},
                   "source": "SIS. Totales calculados por Alicanto con las Isapres publicadas."}]
        tab = {"id": "costos", "label": "Costo de ventas", "charts": charts, "text": [], "dek": None}
        sf.topic_fields(tab, f"Prestaciones y SIL: {fmt_int(CS)} {MM}", index_refs=[f"costo_salud.sistema.{t}"], kpis=[])
        tabs.append(tab)
    if "gastos" in topics:
        G, GP = V(f"gav.sistema.{t}"), V(f"gav_pct.sistema.{t}")
        kpis.append({"id": "gav", "label": "Gastos de administración", "value": f"{fmt_int(G)} {MM}", "prov": "C",
                     "lines": [f"{fmt_dec(GP, 1)}% de los ingresos"], "refs": [f"gav.sistema.{t}", f"gav_pct.sistema.{t}"]})
        parts = [(i, lab) for i, lab in GAV_PARTS if i in complete]
        ordr = sorted(codes, key=lambda c: (-V(f"gav_pct.{c}.{t}"), names[c]))
        charts = []
        if len(parts) >= 2:
            charts.append({"id": "f2-gastos-composicion", "form": "diverging" if any(V(f"{i}.sistema.{t}") < 0 for i, _ in parts) else "bars",
                           "unit": MM, "digits": MM_DIGITS, "headline": "Gastos de administración por componente",
                           "subtitle": f"Millones de pesos, {ytd} {t[:4]}{sin}",
                           "rows": [{"label": lab, "value": V(f"{i}.sistema.{t}"), "ref": f"{i}.sistema.{t}"} for i, lab in parts],
                           "table": {"columns": ["Componente", MM],
                                     "rows": [[lab, fmt_int(V(f"{i}.sistema.{t}"))] for i, lab in parts] + [["Total", fmt_int(G)]]},
                           "source": "SIS, apertura de cuentas de resultados. Los componentes suman el total."})
        charts.append({"id": "f2-gastos-isapres", "form": "bars", "unit": "%", "digits": 1, "headline": "Gastos de administración por Isapre",
                       "subtitle": f"% de los ingresos de cada Isapre, {ytd} {t[:4]}",
                       "rows": [{"label": names[c], "value": V(f"gav_pct.{c}.{t}"), "ref": f"gav_pct.{c}.{t}"} for c in ordr],
                       "table": {"columns": ["Isapre", f"Gastos ({MM})", f"Ingresos ({MM})", "% de los ingresos"],
                                 "rows": [[names[w] if w != "sistema" else sys_row, fmt_int(V(f"gav.{w}.{t}")),
                                           fmt_int(V(f"ingresos_operacionales.{w}.{t}")), fmt_dec(V(f"gav_pct.{w}.{t}"), 1) + "%"]
                                          for w in [*ordr, "sistema"]]},
                       "source": "Denominador: total ingresos de actividades ordinarias de cada Isapre, mismo período."})
        tab = {"id": "gastos", "label": "Gastos de administración", "charts": charts, "text": [], "dek": None}
        sf.topic_fields(tab, f"{fmt_int(G)} {MM} · {fmt_dec(GP, 1)}% de los ingresos",
                        index_refs=[f"gav.sistema.{t}", f"gav_pct.sistema.{t}"], kpis=[])
        tabs.append(tab)
    if "siniestralidad" in topics:
        S = V(f"siniestralidad.sistema.{t}")
        SP, SS = V(f"siniestralidad_prest.sistema.{t}"), V(f"siniestralidad_sil.sistema.{t}")
        s_yoy = has(f"siniestralidad.sistema.{t1}")
        pp = V("siniestralidad.sistema.pp") if s_yoy else None
        kpis.append({"id": "siniestralidad", "label": "Siniestralidad", "value": fmt_dec(S, 1) + "%", "prov": "C",
                     "lines": [f"prestaciones {fmt_dec(SP, 1)}% · SIL {fmt_dec(SS, 1)}%"]
                     + ([f"{plabel}: {fmt_dec(V(f'siniestralidad.sistema.{t1}'), 1)}% ({fmt_dec(pp, 1, signed=True)} pp)"] if s_yoy else []),
                     "refs": [f"siniestralidad.sistema.{t}", f"siniestralidad_prest.sistema.{t}", f"siniestralidad_sil.sistema.{t}"]
                     + ([f"siniestralidad.sistema.{t1}", "siniestralidad.sistema.pp"] if s_yoy else [])})
        comps = (("siniestralidad_prest", "Prestaciones"), ("siniestralidad_sil", "SIL"), ("siniestralidad", "Total"))
        if s_yoy:  # the two parts side by side, this year (dot) against the same months a year earlier (ring)
            hero = {"id": "f2-siniestralidad-componentes", "form": "dots", "unit": "%", "digits": 1,
                    "headline": "Siniestralidad por componente",
                    "subtitle": f"% de los ingresos, {ytd} {t[:4]} (punto) y {t1[:4]} (aro){sin}",
                    "rows": [{"label": lab, "value": V(f"{key}.sistema.{t}"), "ref": f"{key}.sistema.{t}",
                              "base": V(f"{key}.sistema.{t1}"), "base_ref": f"{key}.sistema.{t1}"} for key, lab in comps],
                    "table": {"columns": ["Componente", short(t1), short(t), "Cambio (pp)"],
                              "rows": [[lab, fmt_dec(V(f"{key}.sistema.{t1}"), 1) + "%", fmt_dec(V(f"{key}.sistema.{t}"), 1) + "%",
                                        fmt_dec(V(f"{key}.sistema.pp"), 1, signed=True)] for key, lab in comps]}}
        else:
            hero = {"id": "f2-siniestralidad-componentes", "form": "bars", "unit": "%", "digits": 1,
                    "headline": "Siniestralidad por componente", "subtitle": f"% de los ingresos, {ytd} {t[:4]}{sin}",
                    "rows": [{"label": lab, "value": V(f"{key}.sistema.{t}"), "ref": f"{key}.sistema.{t}",
                              "emphasis": key == "siniestralidad"} for key, lab in comps],
                    "table": {"columns": ["Componente", short(t)],
                              "rows": [[lab, fmt_dec(V(f"{key}.sistema.{t}"), 1) + "%"] for key, lab in comps]}}
        hero["source"] = ("Prestaciones = costos por prestaciones de salud; SIL = subsidios por incapacidad laboral; ambos sobre el "
                          "total de ingresos de actividades ordinarias del mismo período acumulado. Las partes suman el total antes de redondear.")
        ordr = sorted(codes, key=lambda c: (-V(f"siniestralidad.{c}.{t}"), names[c]))
        charts = [hero, {"id": "f2-siniestralidad-isapres", "form": "bars", "unit": "%", "digits": 1, "headline": "Siniestralidad por Isapre",
                         "subtitle": f"Prestaciones y SIL, % de los ingresos de cada Isapre, {ytd} {t[:4]}",
                         "rows": [{"label": names[c], "value": V(f"siniestralidad.{c}.{t}"), "ref": f"siniestralidad.{c}.{t}"} for c in ordr],
                         "table": {"columns": ["Isapre", "Prestaciones", "SIL", "Total", f"Ingresos ({MM})"],
                                   "rows": [[names[w] if w != "sistema" else sys_row, fmt_dec(V(f"siniestralidad_prest.{w}.{t}"), 1) + "%",
                                             fmt_dec(V(f"siniestralidad_sil.{w}.{t}"), 1) + "%", fmt_dec(V(f"siniestralidad.{w}.{t}"), 1) + "%",
                                             fmt_int(V(f"ingresos_operacionales.{w}.{t}"))] for w in [*ordr, "sistema"]]},
                         "source": "Denominador: total ingresos de actividades ordinarias de cada Isapre, mismo período acumulado. "
                                   "Prestaciones y SIL se muestran lado a lado en «Ver datos»."}]
        tab = {"id": "siniestralidad", "label": "Siniestralidad", "charts": charts, "text": [], "dek": None}
        if s_yoy:
            line = (f"{fmt_dec(S, 1)}% · prestaciones {fmt_dec(V('siniestralidad_prest.sistema.pp'), 1, signed=True)} pp · "
                    f"SIL {fmt_dec(V('siniestralidad_sil.sistema.pp'), 1, signed=True)} pp")
            refs = [f"siniestralidad.sistema.{t}", "siniestralidad_prest.sistema.pp", "siniestralidad_sil.sistema.pp"]
        else:
            line = f"{fmt_dec(S, 1)}% de los ingresos: prestaciones {fmt_dec(SP, 1)}%, SIL {fmt_dec(SS, 1)}%"
            refs = [f"siniestralidad.sistema.{t}", f"siniestralidad_prest.sistema.{t}", f"siniestralidad_sil.sistema.{t}"]
        sf.topic_fields(tab, line, index_refs=refs, kpis=[])
        tabs.append(tab)
        paragraphs.append(f"La siniestralidad de las Isapres (prestaciones y SIL sobre ingresos) fue {fmt_dec(S, 1)}% entre enero y {month}: "
                          f"{fmt_dec(SP, 1)}% por prestaciones de salud y {fmt_dec(SS, 1)}% por SIL.")
    if "sil" in topics:
        SS = V(f"siniestralidad_sil.sistema.{t}")
        SC = V(f"sil_cotizaciones.sistema.{t}")
        c_yoy = has(f"sil_cotizaciones.sistema.{t1}")
        ordr = sorted(codes, key=lambda c: (-V(f"siniestralidad_sil.{c}.{t}"), names[c]))
        if has(f"siniestralidad_sil.sistema.{t1}"):
            hero = {"id": "f2-sil-isapres", "form": "dots", "unit": "%", "digits": 1, "headline": "SIL sobre ingresos por Isapre",
                    "subtitle": f"% de los ingresos de cada Isapre, {ytd} {t[:4]} (punto) y {t1[:4]} (aro)",
                    "rows": [{"label": names[c], "value": V(f"siniestralidad_sil.{c}.{t}"), "ref": f"siniestralidad_sil.{c}.{t}",
                              "base": V(f"siniestralidad_sil.{c}.{t1}"), "base_ref": f"siniestralidad_sil.{c}.{t1}"} for c in ordr],
                    "table": {"columns": ["Isapre", short(t1), short(t), "Cambio (pp)"],
                              "rows": [[names[w] if w != "sistema" else sys_row, fmt_dec(V(f"siniestralidad_sil.{w}.{t1}"), 1) + "%",
                                        fmt_dec(V(f"siniestralidad_sil.{w}.{t}"), 1) + "%",
                                        fmt_dec(V(f"siniestralidad_sil.{w}.pp"), 1, signed=True)] for w in [*ordr, "sistema"]]}}
        else:
            hero = {"id": "f2-sil-isapres", "form": "bars", "unit": "%", "digits": 1, "headline": "SIL sobre ingresos por Isapre",
                    "subtitle": f"% de los ingresos de cada Isapre, {ytd} {t[:4]}",
                    "rows": [{"label": names[c], "value": V(f"siniestralidad_sil.{c}.{t}"), "ref": f"siniestralidad_sil.{c}.{t}"} for c in ordr],
                    "table": {"columns": ["Isapre", f"SIL ({MM})", f"Ingresos ({MM})", "SIL / ingresos"],
                              "rows": [[names[w] if w != "sistema" else sys_row, fmt_int(V(f"costo_sil.{w}.{t}")),
                                        fmt_int(V(f"ingresos_operacionales.{w}.{t}")), fmt_dec(V(f"siniestralidad_sil.{w}.{t}"), 1) + "%"]
                                       for w in [*ordr, "sistema"]]}}
        hero["source"] = "SIL = subsidios por incapacidad laboral. Denominador: total ingresos de actividades ordinarias de cada Isapre."
        # Open Isapres first, then the closed ones, each group by value (review of #136): a closed Isapre whose income is
        # largely aporte adicional never tops the chart unmarked.
        ordc = sorted(codes, key=lambda c: (c in closed, -V(f"sil_cotizaciones.{c}.{t}"), names[c]))
        aporte = has(f"aporte_share.sistema.{t}")
        label = lambda w: sys_row if w == "sistema" else names[w] + (" (cerrada)" if w in closed else "")  # noqa: E731
        charts = [hero, {"id": "f2-sil-cotizaciones", "form": "bars", "unit": "%", "digits": 1, "headline": "SIL sobre cotizaciones por Isapre",
                         "subtitle": f"Costo SIL, % de la cotización legal y adicional de cada Isapre, {ytd} {t[:4]}"
                                     + ("; abiertas primero, luego cerradas" if closed else ""),
                         "rows": [{"label": names[c], "value": V(f"sil_cotizaciones.{c}.{t}"), "ref": f"sil_cotizaciones.{c}.{t}",
                                   **({"tag": "cerrada", "muted": True} if c in closed else {})} for c in ordc],
                         "table": {"columns": ["Isapre", f"SIL ({MM})", f"Cotizaciones ({MM})", short(t)] + ([short(t1)] if c_yoy else [])
                                   + (["Aporte adicional (% ingresos)"] if aporte else []),
                                   "rows": [[label(w), fmt_int(V(f"costo_sil.{w}.{t}")),
                                             fmt_int(V(f"cotizaciones.{w}.{t}")), fmt_dec(V(f"sil_cotizaciones.{w}.{t}"), 1) + "%"]
                                            + ([fmt_dec(V(f"sil_cotizaciones.{w}.{t1}"), 1) + "%"] if c_yoy else [])
                                            + ([fmt_dec(V(f"aporte_share.{w}.{t}"), 1) + "%"] if aporte else [])
                                            for w in [*ordc, "sistema"]]},
                         "source": "Cotizaciones = cotización legal más cotización adicional voluntaria, mismo período acumulado. "
                                   "No incluye aporte adicional, fondo de compensación ni otros ingresos."
                                   + (" En las Isapres cerradas el aporte adicional pesa mucho más en los ingresos que en las abiertas "
                                      "(última columna de «Ver datos»), así que su razón no es comparable con la de las abiertas." if closed else "")}]
        tab = {"id": "sil", "label": TOPICS["sil"][0], "charts": charts, "text": [], "dek": None}
        sf.topic_fields(tab, f"{fmt_dec(SS, 1)}% de los ingresos · {fmt_dec(SC, 1)}% de las cotizaciones",
                        index_refs=[f"siniestralidad_sil.sistema.{t}", f"sil_cotizaciones.sistema.{t}"], kpis=[])
        tabs.append(tab)
        paragraphs.append(f"El costo SIL equivale al {fmt_dec(SC, 1)}% de la cotización legal y adicional entre enero y {month}.")

    span = f"{ytd} {t[:4]}"  # 'enero–marzo 2026', the same span as the chart subtitles
    if "resultados" in topics:
        lead = headline_lead(V(f"resultado_ejercicio.sistema.{t1}") if "resultado_ejercicio" in yoy else None,
                             V(f"resultado_ejercicio.sistema.{t}"), span)
    elif "siniestralidad" in topics:
        lead = f"La siniestralidad de las Isapres es {fmt_dec(V(f'siniestralidad.sistema.{t}'), 1)}% de los ingresos en {span}"
    else:
        lead = f"Las Isapres ingresan {fmt_int(V(f'ingresos_operacionales.sistema.{t}'))} {MM} en {span}"
    headline = tpl["headline"]["default"].format(month_label=mlabel, lead=lead)
    # The dek adds what the KPI cards do not show: where income comes from and the spread across Isapres.
    dek_parts = []
    if has("cotizacion_legal.sistema.share"):
        dek_parts.append(f"La cotización legal aporta el {fmt_dec(V('cotizacion_legal.sistema.share'), 1)}% de los ingresos.")
    if "siniestralidad" in topics:
        lo = min(codes, key=lambda x: (V(f"siniestralidad.{x}.{t}"), names[x]))
        hi = max(codes, key=lambda x: (V(f"siniestralidad.{x}.{t}"), names[x]))
        dek_parts.append(f"Por Isapre, la siniestralidad va de {fmt_dec(V(f'siniestralidad.{lo}.{t}'), 1)}% ({names[lo]}) a "
                         f"{fmt_dec(V(f'siniestralidad.{hi}.{t}'), 1)}% ({names[hi]}).")
    dek = " ".join(dek_parts) or (paragraphs[0] if paragraphs else "")
    published = date.fromisoformat(package["published_at"][:10])
    expected = date.fromordinal(published.toordinal() + int(cfg["calendar"]["expected_release_interval_days"]))
    nxt = sf.shift_period(t, 3)
    late = (decision or {}).get("late_release")
    watch = [({"headline": f"Estadísticas financieras a {sf.month_label(nxt)}: publicación atrasada.",
               "explanation": f"Lleva {late['days_late']} días de atraso según el calendario histórico."} if late else
              {"headline": f"Estadísticas financieras a {sf.month_label(nxt)} (la SIS las publicaría hacia el {sf.day_label(expected)}).",
               "explanation": ("Si la nota de cobertura deja de decir que Esencial está en revisión, la ficha se retiene hasta una nueva decisión."
                               if excl else "Un cambio de signo del resultado destaca la ficha.")})]
    notes = []
    if excl:
        cn, r = k["coverage_note"], k["rule"]
        notes.append({"id": "n0", "text": f"Esencial queda fuera por decisión de Dirección del {sf.day_label(r['decided_at'])} {r['decided_at'][:4]}. "
                                          f"La SIS indica en {cn['locator']}: \"{str(cn['text']).strip()}\" "
                                          f"Los totales del {SYSTEM} los calcula Alicanto con las otras {len(codes)} Isapres."})
    notes += [
        {"id": "n1", "text": f"Ingresos, costos y resultados son flujos acumulados de enero a {month}, no stocks. Montos nominales: la SIS "
                             "los publica en miles de pesos y Alicanto los convierte a millones; el valor real (UF) queda pendiente."},
        {"id": "n2", "text": "Denominadores: la siniestralidad divide prestaciones y SIL por el total de ingresos de actividades ordinarias "
                             "del mismo período, igual que los gastos de administración. La variación % de ingresos usa el valor del año anterior "
                             "como base; los resultados no llevan variación % y se comparan por sus niveles y el cambio absoluto."},
        {"id": "n2b", "text": "Siniestralidad separada: prestaciones (costos por prestaciones de salud / ingresos) más SIL (subsidios por "
                              "incapacidad laboral / ingresos) igualan la siniestralidad total antes de redondear; si no calzan, la ficha se "
                              "retiene. Por redondeo, las partes mostradas pueden diferir en una décima del total. El costo SIL sobre "
                              "cotizaciones usa como denominador la cotización legal más la cotización adicional voluntaria del mismo período, "
                              "sin aporte adicional, fondo de compensación ni otros ingresos; difiere de la siniestralidad sobre ingresos. "
                              "Se compara enero–" + month + " con los mismos meses del año anterior, nunca con un año completo: el SIL "
                              "tiene estacionalidad."},
        {"id": "n3", "text": "Cada cifra se lee de las hojas de apertura de cuentas de resultados "
                             "y del estado de resultados por función (en miles de $) de la planilla capturada (hash en Fuentes), con una plantilla "
                             "revisada por una persona; en cada cuenta las Isapres suman la columna total y los componentes su total; ingresos menos "
                             "costo de ventas igualan la ganancia bruta. Las hojas en millones no se usan: mezclan escalas."},
    ]
    margin = package.get("margin") or {}
    if t in (margin.get("periods") or []):
        notes.append({"id": "n4", "text": f"Margen por beneficiario = resultado operacional / beneficiarios promedio, en pesos, acumulado de "
                                          f"enero a {month}. Resultado operacional = ganancia bruta − gastos de administración y otros "
                                          f"gastos por función (no incluye otros ingresos, resultado financiero ni impuestos). "
                                          f"Denominador: promedio simple de los stocks de beneficiarios a fin de mes, de enero a {month}, de "
                                          f"la misma Isapre, según la estadística mensual de cartera de la SIS (datos provisionales; hash en "
                                          f"Fuentes); el sistema suma las mismas Isapres de la ficha."})
    held = [h for h in margin.get("holds") or [] if h["period"] in (t, t1)]
    if held:
        notes.append({"id": "n4b", "text": "Margen por beneficiario retenido para " + " y ".join(sf.month_label(h["period"]) for h in held)
                                           + ": no hay cartera mensual capturada y cuadrada para las mismas Isapres y los mismos meses. "
                                           "Alicanto no lo aproxima."})
    opn = [c for c in codes if c not in closed]
    if ("sil" in topics and closed and opn and has(f"aporte_share.sistema.{t}")
            and min(V(f"aporte_share.{c}.{t}") for c in closed) > max(V(f"aporte_share.{c}.{t}") for c in opn)):
        notes.append({"id": "n2d", "text": "Isapres cerradas: en cada una, el aporte adicional pesa más en los ingresos que en cualquier "
                                           "Isapre abierta. Como no es cotización, no entra al denominador de SIL sobre cotizaciones; por eso "
                                           "esa razón de las cerradas va marcada «cerrada», después de las abiertas, y no es comparable con "
                                           "la de las abiertas."})
    if not yoy:
        notes.append({"id": "n5", "text": f"Sin comparación con {plabel}: esa planilla no está capturada y verificada con la misma plantilla. "
                                          "La ficha muestra solo los niveles del período."})
    notes.append({"id": "n6", "text": "Ningún dato de esta ficha establece por qué cambian los ingresos, los costos o la siniestralidad; "
                                      "prestaciones y SIL se muestran lado a lado y ninguna de las dos explica a la otra."})
    sources = [{**src, "key": key} for key, src in package["sources"].items()]
    footnote = (scope_note(str(k["coverage_note"]["locator"]).rsplit("!", 1)[-1], mlabel, len(codes)) if excl else None)
    triggers = (decision or {}).get("triggers") or []
    rule = "nuevo período" if "new_period" in triggers else ("revisión" if "revision" in triggers else "publicación vigente")
    machine = (f"Ficha generada por la regla \"{rule}\" (publicación del {sf.day_label(package['published_at'])}). Las cifras vienen del "
               "paquete de evidencia; solo la Lectura Alicanto puede escribirla un modelo, y pasa por un verificador.")
    return {
        "schema_version": sf.SCHEMA, "id": f"stats-ficha:{FAMILY}:{t}", "family": FAMILY, "family_label": cfg["label"],
        "slug": cfg["slug"], "period": t, "published_at": package["published_at"], "release_key": package["release_key"],
        "kicker": tpl["kicker"].format(label=cfg["label"], period_label=mlabel),  # 'Estados financieros Isapres · marzo 2026'
        "kicker_meta": tpl["kicker_meta"].format(period_label=mlabel, published_label=sf.day_label(package["published_at"]),
                                                 cadence_phrase=cfg["cadence_phrase"]),
        "headline": headline[0].upper() + headline[1:], "headline_type": "default", "dek": dek, "dek_emphasis": None,
        "scope_note": footnote,
        "kpis": kpis[:5], "tabs": tabs,
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs or [dek], "rendered_in_tabs": True},
        "watch": watch, "notes": notes, "sources": sources, "machine_note": machine,
        "featured": bool((decision or {}).get("featured")), "triggers": triggers, "late_release": late,
        "revisions": package.get("revisions") or [],
    }


def run(root: Path, *, today: date, registry: dict | None = None, llm: bool = True,
        model_call: Callable[..., Any] | None = None, budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    """The Lectura stays off for F2 (no paid call) until Dirección sets ``families.F2.lectura_enabled``."""
    registry = registry or sf.load_registry()
    llm = llm and registry["families"][FAMILY].get("lectura_enabled") is True
    return sf.run_family(FAMILY, builder_version=BUILDER_VERSION, build_package=build_package, compose=compose, root=Path(root),
                         today=today, registry=registry, llm=llm, model_call=model_call, budget=budget)
