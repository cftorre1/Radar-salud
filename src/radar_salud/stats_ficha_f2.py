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
BUILDER_VERSION = "f2_index_topic_v3"
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
}
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
    """Δ and Δ% with the sign rule: a % only when the base is positive and (for a result) the sign does not change."""
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
        pct = delta / prev * 100 if prev > 0 and cur >= 0 else None
    else:
        kind = "up" if delta > 0 else ("down" if delta < 0 else "same")
        pct = delta / prev * 100 if prev > 0 else None
    return {"delta": delta, "pct": pct, "transition": kind}


def level_phrase(cur: float) -> str:
    return f"utilidad de {fmt_int(cur)} {MM}" if cur >= 0 else f"pérdida de {fmt_int(abs(cur))} {MM}"


def result_phrase(prev: float, cur: float, when_prev: str) -> str:
    """'utilidad de 34.091 MM$, tras una pérdida de 273 MM$ en marzo 2025': sign-aware, no signed percentage."""
    c = change(prev, cur, result=True)
    k = c["transition"]
    if k == "loss_to_profit":
        return f"utilidad de {fmt_int(cur)} {MM}, tras una pérdida de {fmt_int(abs(prev))} {MM} en {when_prev}"
    if k == "profit_to_loss":
        return f"pérdida de {fmt_int(abs(cur))} {MM}, tras una utilidad de {fmt_int(prev)} {MM} en {when_prev}"
    if cur < 0:
        word = {"loss_smaller": "menor que", "loss_larger": "mayor que", "same": "igual a"}[k]
        return f"pérdida de {fmt_int(abs(cur))} {MM}, {word} la de {fmt_int(abs(prev))} {MM} en {when_prev}"
    if c["pct"] is None:
        return f"utilidad de {fmt_int(cur)} {MM} ({fmt_int(prev)} {MM} en {when_prev})"
    word = "más" if c["delta"] > 0 else "menos"
    return f"utilidad de {fmt_int(cur)} {MM}, {fmt_dec(abs(c['pct']), 1)}% {word} que en {when_prev}"


def pct_cell(pct: float | None) -> str:
    return "N/A" if pct is None else fmt_dec(pct, 1, signed=True) + "%"


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
            "al menos tres temas con datos verificados"]},
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
        for w in whos:
            for p in s_pers:
                den = V(f"ingresos_operacionales.{w}.{p}")
                if den <= 0:
                    return _hold(package, [f"siniestralidad_denominator_not_positive:{w}.{p}"], topics)
                derived(f"siniestralidad.{w}.{p}", V(f"costo_salud.{w}.{p}") / den * 100,
                        "(costo de prestaciones + SIL) / total ingresos de actividades ordinarias × 100",
                        [f"costo_salud.{w}.{p}", f"ingresos_operacionales.{w}.{p}"], "%", p)
            if t1 in s_pers:
                derived(f"siniestralidad.{w}.pp", round(V(f"siniestralidad.{w}.{t}"), 1) - round(V(f"siniestralidad.{w}.{t1}"), 1),
                        "redondeo(siniestralidad t, 1) − redondeo(siniestralidad t−12, 1)",
                        [f"siniestralidad.{w}.{t}", f"siniestralidad.{w}.{t1}"], "pp")
        if t1 in s_pers:  # threshold on the rounded value shown (89,96 → '90,0%' crosses 90); needs the previous year
            levels = (cfg["kpis"]["siniestralidad"].get("threshold") or {}).get("levels_pct") or []
            s_t, s_1 = round(V(f"siniestralidad.sistema.{t}"), 1), round(V(f"siniestralidad.sistema.{t1}"), 1)
            for lvl in levels:
                if (s_t >= lvl) != (s_1 >= lvl):
                    findings.append({"type": "threshold_crossed", "kpi": "siniestralidad", "level": lvl, "crossed": True, "strength": 1.0})
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
        res = item == "resultado_ejercicio"
        for w in whos:
            c = change(V(f"{item}.{w}.{t1}"), V(f"{item}.{w}.{t}"), result=res)
            derived(f"{item}.{w}.delta", c["delta"], f"{item}(t) − {item}(t−12)", [f"{item}.{w}.{t}", f"{item}.{w}.{t1}"], MM)
            if c["pct"] is not None:
                derived(f"{item}.{w}.pct", c["pct"], "Δ / valor(t−12) × 100 (solo base positiva y sin cambio de signo)",
                        [f"{item}.{w}.delta", f"{item}.{w}.{t1}"], "%")
        if res and change(V(f"{item}.sistema.{t1}"), V(f"{item}.sistema.{t}"), result=True)["transition"] in ("loss_to_profit", "profit_to_loss"):
            findings.append({"type": "sign_change", "kpi": "resultado", "crossed": True, "strength": 1.0})
    if "resultados" in topics:
        derived("conteo.isapres_con_utilidad", sum(1 for c in codes if V(f"resultado_ejercicio.{c}.{t}") > 0),
                "Isapres con resultado > 0", [f"resultado_ejercicio.{c}.{t}" for c in codes], "count")
    for vid in ("conteo.isapres", "conteo.isapres_con_utilidad"):
        if vid in values:
            package["derived_ratios"].append({"id": vid, "value": V(vid), "unit": "count", "entity": None, "signed": False,
                                              "periods": [t], "requires_period": False, "formula": values[vid]["formula"],
                                              "inputs": [], "scope": "system", "period_kind": "ytd", "trivial": True, "base": None})
    note = parse.get("coverage_note") or {}
    package["entities"] = [{"code": int(c), "name": names[c]} for c in codes]
    package["entity_codes"] = [int(c) for c in codes]
    package.update(findings=findings, topics=topics, periods=[t1, t] if yoy else [t],
                   revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
                   constants=[100, 12, *((cfg["kpis"]["siniestralidad"].get("threshold") or {}).get("levels_pct") or [])],
                   kpis={"t1": t1, "yoy": sorted(yoy), "codes": codes, "names": {c: names[c] for c in codes},
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
    V = lambda vid: v[vid]["value"]  # noqa: E731
    has = lambda vid: vid in v  # noqa: E731
    month, mlabel, plabel = sf.month_name(t), sf.month_label(t), sf.month_label(t1)
    ytd = f"enero–{month}"
    short = lambda p: f"{sf.month_short(p)} {p[:4]}"  # noqa: E731
    topics = package["topics"]
    excl = bool(k["excluded"])
    sys_row = "Sistema sin Esencial" if excl else "Sistema"
    sys_phrase = SYSTEM if excl else "sistema"
    scope = f" ({SYSTEM})" if excl else ""
    kpis, tabs, paragraphs = [], [], []

    def order(item: str) -> list[str]:
        return sorted(codes, key=lambda c: (-V(f"{item}.{c}.{t}"), names[c]))

    def cmp_line(item: str, res: bool = False) -> str:
        if item not in yoy:
            return f"{ytd} {t[:4]}; sin comparación a/a"
        c = change(V(f"{item}.sistema.{t1}"), V(f"{item}.sistema.{t}"), result=res)
        return f"{plabel}: {fmt_int(V(f'{item}.sistema.{t1}'))} {MM} · variación % " + (
            "N/A (cambia de signo)" if c["pct"] is None and res else pct_cell(c["pct"]))

    def cmp_refs(item: str) -> list[str]:
        if item not in yoy:
            return []
        return [f"{item}.sistema.{t1}"] + ([f"{item}.sistema.pct"] if has(f"{item}.sistema.pct") else [])

    if "resultados" in topics:
        R = V(f"resultado_ejercicio.sistema.{t}")
        n_pos, n = int(V("conteo.isapres_con_utilidad")), int(V("conteo.isapres"))
        ry = "resultado_ejercicio" in yoy
        kpis.append({"id": "resultado", "label": f"Resultado del ejercicio{scope}", "value": f"{fmt_int(R)} {MM}", "prov": "C",
                     "lines": [cmp_line("resultado_ejercicio", True)],
                     "refs": [f"resultado_ejercicio.sistema.{t}"] + cmp_refs("resultado_ejercicio")})
        charts = []
        bridge = [(i, lab, sg) for i, lab, sg in BRIDGE if i in complete]
        if not ry and len(bridge) == len(BRIDGE):  # levels only: from ganancia bruta to the result, same period
            charts.append({"id": "f2-resultado-puente", "form": "diverging", "unit": MM, "headline": "De la ganancia bruta al resultado",
                           "subtitle": f"Millones de pesos, {ytd} {t[:4]}, {sys_phrase}",
                           "rows": [{"label": lab, "value": sg * V(f"{i}.sistema.{t}"), "ref": f"{i}.sistema.{t}", "sign": sg,
                                     "emphasis": i == "resultado_ejercicio"} for i, lab, sg in bridge],
                           "table": {"columns": ["Concepto", MM],
                                     "rows": [[lab, fmt_int(sg * V(f"{i}.sistema.{t}"))] for i, lab, sg in bridge]},
                           "source": "SIS, estado de resultados por función (miles de $ convertidos a millones). El tramo entre ganancia bruta y "
                                     "resultado antes de impuestos incluye gastos de administración y otros ítems."})
        if ry:
            R1 = V(f"resultado_ejercicio.sistema.{t1}")
            charts.append({"id": "f2-resultado", "form": "diverging", "unit": MM, "headline": f"Resultado del ejercicio, {sys_phrase}",
                           "subtitle": f"Millones de pesos, {ytd} de cada año",
                           "rows": [{"label": short(t1), "value": R1, "ref": f"resultado_ejercicio.sistema.{t1}"},
                                    {"label": short(t), "value": R, "ref": f"resultado_ejercicio.sistema.{t}", "emphasis": True}],
                           "table": {"columns": ["Período", f"Resultado ({MM})"],
                                     "rows": [[short(t1), fmt_int(R1)], [short(t), fmt_int(R)],
                                              ["Cambio", sf.fmt_signed(V("resultado_ejercicio.sistema.delta"))],
                                              ["Variación %", pct_cell((v.get("resultado_ejercicio.sistema.pct") or {}).get("value"))]]},
                           "source": "SIS. La variación % no se calcula si algún período tiene pérdida."})

        def rrow(w, lab):
            out = [lab, fmt_int(V(f"resultado_ejercicio.{w}.{t}"))]
            if ry:
                out += [fmt_int(V(f"resultado_ejercicio.{w}.{t1}")), sf.fmt_signed(V(f"resultado_ejercicio.{w}.delta")),
                        pct_cell((v.get(f"resultado_ejercicio.{w}.pct") or {}).get("value"))]
            return out
        ordr = order("resultado_ejercicio")
        charts.append({"id": "f2-resultado-isapres", "form": "diverging", "unit": MM, "headline": "Resultado por Isapre",
                       "subtitle": f"Millones de pesos, {ytd} {t[:4]}",
                       "rows": [{"label": names[c], "value": V(f"resultado_ejercicio.{c}.{t}"), "ref": f"resultado_ejercicio.{c}.{t}",
                                 "emphasis": V(f"resultado_ejercicio.{c}.{t}") < 0} for c in ordr],
                       "table": {"columns": ["Isapre", short(t)] + ([short(t1), "Cambio", "Variación %"] if ry else []),
                                 "rows": [rrow(c, names[c]) for c in ordr] + [rrow("sistema", sys_row)]},
                       "source": "SIS. Totales calculados por Alicanto con las Isapres publicadas."})
        tab = {"id": "resultados", "label": "Resultados", "charts": charts, "text": [], "dek": None}
        sf.topic_fields(tab, f"{fmt_int(R)} {MM} · {n_pos} de {n} Isapres con utilidad",
                        index_refs=[f"resultado_ejercicio.sistema.{t}", "conteo.isapres_con_utilidad", "conteo.isapres"], kpis=[])
        tabs.append(tab)
        paragraphs.append(f"Entre enero y {month}, el {sys_phrase} registró una "
                          + (result_phrase(V(f"resultado_ejercicio.sistema.{t1}"), R, plabel) if ry else level_phrase(R)) + ".")
    if "ingresos" in topics:
        I = V(f"ingresos_operacionales.sistema.{t}")
        kpis.append({"id": "ingresos", "label": f"Ingresos{scope}", "value": f"{fmt_int(I)} {MM}", "prov": "C",
                     "lines": [cmp_line("ingresos_operacionales")],
                     "refs": [f"ingresos_operacionales.sistema.{t}"] + cmp_refs("ingresos_operacionales")})
        parts = [(i, lab) for i, lab in INGRESOS_PARTS if i in complete]
        charts = []
        comp_rows = [{"label": lab, "value": V(f"{i}.sistema.{t}"), "ref": f"{i}.sistema.{t}", "emphasis": i == "cotizacion_legal"}
                     for i, lab in parts if V(f"{i}.sistema.{t}") != 0]
        if len(comp_rows) >= 2:  # stock of the period first: where the income comes from
            charts.append({"id": "f2-ingresos-composicion", "form": "bars", "unit": MM, "headline": "De dónde vienen los ingresos",
                           "subtitle": f"Millones de pesos, {ytd} {t[:4]}, {sys_phrase}", "rows": comp_rows,
                           "table": {"columns": ["Componente", MM],
                                     "rows": [[lab, fmt_int(V(f"{i}.sistema.{t}"))] for i, lab in parts] + [["Total ingresos", fmt_int(I)]]},
                           "source": "SIS, apertura de cuentas de resultados (miles de $ convertidos a millones). Los componentes suman el total."})
        ordr = order("ingresos_operacionales")
        charts.append({"id": "f2-ingresos-isapres", "form": "bars", "unit": MM, "headline": "Ingresos por Isapre",
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
        kpis.append({"id": "costo_salud", "label": f"Prestaciones y SIL{scope}", "value": f"{fmt_int(CS)} {MM}", "prov": "C",
                     "lines": [f"prestaciones {fmt_int(V(f'costo_prestaciones.sistema.{t}'))} · SIL {fmt_int(V(f'costo_sil.sistema.{t}'))}"],
                     "refs": [f"costo_salud.sistema.{t}", f"costo_prestaciones.sistema.{t}", f"costo_sil.sistema.{t}"]})
        parts = [(i, lab) for i, lab in COSTO_PARTS if i in complete]
        signed = any(V(f"{i}.sistema.{t}") < 0 for i, _ in parts)
        ordr = order("costo_salud")
        charts = [{"id": "f2-costos-composicion", "form": "diverging" if signed else "bars", "unit": MM,
                   "headline": "Costo de ventas por componente", "subtitle": f"Millones de pesos, {ytd} {t[:4]}, {sys_phrase}",
                   "rows": [{"label": lab, "value": V(f"{i}.sistema.{t}"), "ref": f"{i}.sistema.{t}", "emphasis": i == "costo_prestaciones"}
                            for i, lab in parts],
                   "table": {"columns": ["Componente", MM], "rows": [[lab, fmt_int(V(f"{i}.sistema.{t}"))] for i, lab in parts]
                             + ([["Total costo de ventas", fmt_int(V(f"costo_operacional.sistema.{t}"))]] if "costo_operacional" in complete else [])},
                   "source": "SIS, apertura de cuentas de resultados. Los componentes suman el total del costo de ventas."},
                  {"id": "f2-costos-isapres", "form": "bars", "unit": MM, "headline": "Prestaciones y SIL por Isapre",
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
        kpis.append({"id": "gav", "label": f"Gastos de administración{scope}", "value": f"{fmt_int(G)} {MM}", "prov": "C",
                     "lines": [f"{fmt_dec(GP, 1)}% de los ingresos"], "refs": [f"gav.sistema.{t}", f"gav_pct.sistema.{t}"]})
        parts = [(i, lab) for i, lab in GAV_PARTS if i in complete]
        ordr = sorted(codes, key=lambda c: (-V(f"gav_pct.{c}.{t}"), names[c]))
        charts = []
        if len(parts) >= 2:
            charts.append({"id": "f2-gastos-composicion", "form": "diverging" if any(V(f"{i}.sistema.{t}") < 0 for i, _ in parts) else "bars",
                           "unit": MM, "headline": "Gastos de administración por componente",
                           "subtitle": f"Millones de pesos, {ytd} {t[:4]}, {sys_phrase}",
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
        pp = (v.get("siniestralidad.sistema.pp") or {}).get("value")
        kpis.append({"id": "siniestralidad", "label": f"Siniestralidad{scope}", "value": fmt_dec(S, 1) + "%", "prov": "C",
                     "lines": ["prestaciones y SIL sobre ingresos"]
                     + ([f"{plabel}: {fmt_dec(V(f'siniestralidad.sistema.{t1}'), 1)}% ({fmt_dec(pp, 1, signed=True)} pp)"] if pp is not None else []),
                     "refs": [f"siniestralidad.sistema.{t}"] + ([f"siniestralidad.sistema.{t1}", "siniestralidad.sistema.pp"] if pp is not None else [])})
        ordr = sorted(codes, key=lambda c: (-V(f"siniestralidad.{c}.{t}"), names[c]))
        charts = [{"id": "f2-siniestralidad-isapres", "form": "bars", "unit": "%", "digits": 1, "headline": "Siniestralidad por Isapre",
                   "subtitle": f"Prestaciones y SIL, % de los ingresos de cada Isapre, {ytd} {t[:4]}",
                   "rows": [{"label": names[c], "value": V(f"siniestralidad.{c}.{t}"), "ref": f"siniestralidad.{c}.{t}"} for c in ordr],
                   "table": {"columns": ["Isapre", "Prestaciones y SIL", "Ingresos", "Siniestralidad"],
                             "rows": [[names[w] if w != "sistema" else sys_row, fmt_int(V(f"costo_salud.{w}.{t}")),
                                       fmt_int(V(f"ingresos_operacionales.{w}.{t}")), fmt_dec(V(f"siniestralidad.{w}.{t}"), 1) + "%"]
                                      for w in [*ordr, "sistema"]]},
                   "source": "Denominador: total ingresos de actividades ordinarias de cada Isapre, mismo período acumulado."}]
        if pp is not None:
            charts.insert(0, {"id": "f2-siniestralidad", "form": "bars", "unit": "%", "digits": 1, "headline": f"Siniestralidad, {sys_phrase}",
                              "subtitle": f"% de los ingresos, {ytd} de cada año",
                              "rows": [{"label": short(t1), "value": V(f"siniestralidad.sistema.{t1}"), "ref": f"siniestralidad.sistema.{t1}"},
                                       {"label": short(t), "value": S, "ref": f"siniestralidad.sistema.{t}", "emphasis": True}],
                              "table": {"columns": ["Período", "Siniestralidad"],
                                        "rows": [[short(p), fmt_dec(V(f"siniestralidad.sistema.{p}"), 1) + "%"] for p in (t1, t)]},
                              "source": "Denominador: total ingresos de actividades ordinarias del mismo período acumulado."})
        tab = {"id": "siniestralidad", "label": "Siniestralidad", "charts": charts, "text": [], "dek": None}
        line = f"{fmt_dec(S, 1)}% de los ingresos" + (f" · {fmt_dec(pp, 1, signed=True)} pp" if pp is not None else "")
        sf.topic_fields(tab, line, index_refs=[f"siniestralidad.sistema.{t}"] + (["siniestralidad.sistema.pp"] if pp is not None else []), kpis=[])
        tabs.append(tab)
        paragraphs.append(f"La siniestralidad del {sys_phrase} (prestaciones y SIL sobre ingresos) fue {fmt_dec(S, 1)}% entre enero y {month}.")

    if "resultados" in topics:
        lead = (result_phrase(V(f"resultado_ejercicio.sistema.{t1}"), V(f"resultado_ejercicio.sistema.{t}"), plabel)
                if "resultado_ejercicio" in yoy else level_phrase(V(f"resultado_ejercicio.sistema.{t}")) + f" entre enero y {month}")
    elif "siniestralidad" in topics:
        lead = f"siniestralidad de {fmt_dec(V(f'siniestralidad.sistema.{t}'), 1)}% de los ingresos entre enero y {month}"
    else:
        lead = f"ingresos de {fmt_int(V(f'ingresos_operacionales.sistema.{t}'))} {MM} entre enero y {month}"
    headline = tpl["headline"]["default"].format(month_label=mlabel, lead=lead)
    if not excl:
        headline = headline.replace("Isapres sin Esencial", "Isapres")
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
                             "del mismo período, igual que los gastos de administración; la variación % usa el valor del año anterior y no se calcula (N/A) si un resultado cambia de signo."},
        {"id": "n3", "text": "Cada cifra se lee de las hojas de apertura de cuentas de resultados "
                             "y del estado de resultados por función (en miles de $) de la planilla capturada (hash en Fuentes), con una plantilla "
                             "revisada por una persona; en cada cuenta las Isapres suman la columna total y los componentes su total; ingresos menos "
                             "costo de ventas igualan la ganancia bruta. Las hojas en millones no se usan: mezclan escalas."},
    ]
    if not yoy:
        notes.append({"id": "n5", "text": f"Sin comparación con {plabel}: esa planilla no está capturada y verificada con la misma plantilla. "
                                          "La ficha muestra solo los niveles del período."})
    notes.append({"id": "n6", "text": "Ningún dato de esta ficha establece por qué cambian los ingresos, los costos o la siniestralidad."})
    sources = [{**src, "key": key} for key, src in package["sources"].items()]
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
