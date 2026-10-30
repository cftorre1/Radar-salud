"""F2 · Resultados financieros de las Isapres (SIS, Estadísticas Financieras 'FEFI'): package, ficha and verification.

Input: ``data/stats_fichas/captures/fefi.json`` (``stats_capture_fefi``): per quarterly release, the workbook's URL,
SHA-256 and the values read through the **reviewed** structure template (``families.F2.parser_template``), with their
sheet!cell locators and the 'Isapres = total sistema' check per column.

The ficha HOLDs (never publishes) unless all of these hold:
- the parser template is reviewed by a person (no ``<<…>>`` placeholder, ``reviewed_by`` and ``reviewed_at`` set) and
  the captured parse was made with that same template (``template_sha256``) and is ``verified``;
- no ``HOLD_COVERAGE_ESENCIAL`` is active in ``config/editorial_rules_v3.json`` (``holds.fefi_*``). While it is, the
  system aggregates and every ranking across Isapres are not even computed (they include Esencial, whose institutional
  rows the coverage note contradicts), and the ficha HOLDs as data/stats_fichas/POLICY.md requires for F2;
- at least three topics are supported by the verified data. Topics are chosen from what the template maps (closed
  item list in ``stats_capture_fefi.ITEMS``); a topic whose items are not mapped and verified is never shown.

Truth rules applied here (data/stats_fichas/PLAYBOOK.md): a result that changes sign gets the absolute change and a
'N/A' percentage; wording follows the sign ('menor', 'mayor', never '−3,2% menos'); the siniestralidad denominator is
the premium income of the same year-to-date period; thresholds are evaluated on the rounded value shown.
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
BUILDER_VERSION = "f2_index_topic_v1"
CAPTURE = fc.STORE
EDITORIAL_RULES = Path("config/editorial_rules_v3.json")
ESENCIAL_HOLD = "HOLD_COVERAGE_ESENCIAL"
# Topic → the (item, period) pairs it needs for every Isapre and the system. Nothing else can become a topic.
TOPICS = {
    "resultados": ("Resultados", (("resultado_ejercicio", "t"), ("resultado_ejercicio", "t_1"))),
    "ingresos_costos": ("Ingresos y costos", (("ingresos_operacionales", "t"), ("ingresos_operacionales", "t_1"),
                                              ("costo_operacional", "t"), ("costo_operacional", "t_1"))),
    "siniestralidad": ("Siniestralidad", (("costo_prestaciones", "t"), ("costo_prestaciones", "t_1"),
                                          ("ingresos_cotizaciones", "t"), ("ingresos_cotizaciones", "t_1"))),
    "patrimonio": ("Patrimonio", (("patrimonio", "t"),)),
}
COSTS = ("costo_operacional", "costo_prestaciones", "costo_sil", "gav")
MM = "MM$"


def esencial_hold(root: Path) -> str | None:
    """The active Esencial coverage HOLD ('fefi_2026_03: HOLD_COVERAGE_ESENCIAL: …'), or None. Fails closed: an
    unreadable rules file counts as an active HOLD."""
    try:
        rules = json.loads((Path(root) / EDITORIAL_RULES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"editorial_rules_unreadable: {ESENCIAL_HOLD} asumido"

    def walk(obj: Any):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).startswith("fefi") and isinstance(v, str) and v.startswith(ESENCIAL_HOLD):
                    yield f"{k}: {v}"
                yield from walk(v)
        elif isinstance(obj, list):
            for x in obj:
                yield from walk(x)
    found = list(walk(rules))
    return found[0] if found else None


def change(prev: float, cur: float, *, result: bool) -> dict:
    """Δ and Δ% with the sign rule: a % only when the base is positive and (for a result) the sign does not change.
    'transition' names what happened, so wording never relies on a signed percentage."""
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
    per = {"t": t, "t_1": t1}
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
    if hold:
        failures.append(f"{ESENCIAL_HOLD}:{hold.split(':')[0]}")
    values: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    package: dict[str, Any] = {
        "family": FAMILY, "period": t, "periods": [t1, t], "published_at": rel.get("published_at"),
        "release_key": sf.release_key(t, doc.get("sha256") or "0" * 16),
        "primary_source": {"url": doc.get("url"), "sha256": doc.get("sha256")}, "sources": sources, "values": values,
        "entities": [], "entity_codes": [], "entity_keys": [], "causal_note": None, "provisional": False,
        "esencial_hold": hold, "parser_template_state": tpl_state,
        # While the Esencial HOLD is active these are never computed (they include Esencial).
        "disabled_by_esencial_hold": ["agregados del sistema", "rankings entre Isapres"] if hold else [],
        "reconciliation": {"ok": False, "failures": failures, "checks": [
            "plantilla de hoja, encabezado, columnas y filas revisada por una persona (sin marcadores <<…>>)",
            "la planilla capturada conserva su SHA-256 y se leyó con esa misma plantilla",
            "cada patrón calza exactamente una vez en el texto normalizado",
            "las Isapres suman el total del sistema en cada columna",
            "los costos quedan con signo positivo tras el signo declarado en la plantilla",
            "sin HOLD_COVERAGE_ESENCIAL activo (agregados y rankings dependen de Esencial)",
            "al menos tres temas con datos verificados"]},
        "lectura_pool": [], "derived_ratios": [], "ranks": [],
    }
    if failures:
        package.update(findings=[], kpis={}, revisions=[], constants=[], topics=[])
        return package

    names = _names(root)
    tables = parse.get("tables") or {}
    have: dict[tuple[str, str], tuple[str, str]] = {}  # (item, period) → (table, column id)
    for tid, tab in tables.items():
        for cid, col in (tab.get("columns") or {}).items():
            key = (col["item"], col["period"])
            if key in have:
                failures.append(f"item_mapped_twice:{col['item']}.{col['period']}")
            have[key] = (tid, cid)
    codes = sorted({c for tab in tables.values() for v in (tab.get("values") or {}).values() for c in v if c != "total"}, key=int)
    missing_names = [c for c in codes if not names.get(c)]
    if missing_names:
        failures.append("entity_name_missing:" + ",".join(missing_names))
    for (item, p), (tid, cid) in sorted(have.items()):
        tab = tables[tid]
        for code, x in tab["values"][cid].items():
            who = "sistema" if code == "total" else code
            values[f"{item}.{who}.{per[p]}"] = value(f"{item}.{who}.{per[p]}", x, unit=MM, period=per[p], source="fefi",
                                                      locator=f"{tab['sheet']}!{tab['cells'][cid][code]}")
            if item in COSTS and x < 0:
                failures.append(f"cost_negative_after_sign:{item}.{who}.{p}")
    topics = [tid for tid, (_, need) in TOPICS.items() if all(k in have for k in need)]
    if len(topics) < 3:
        failures.append(f"topics_under_3:{','.join(topics) or 'ninguno'}")
    package["reconciliation"].update(ok=not failures, failures=failures)
    if failures:
        package.update(findings=[], kpis={}, revisions=[], constants=[], topics=topics)
        return package

    sources["fefi"] = sf.source_ref(url=doc["url"], sha256=doc["sha256"], published_at=rel.get("published_at"),
                                    fetched_at=doc.get("fetched_at"),
                                    label=f"SIS · Estadísticas financieras del sistema Isapre a {sf.month_label(t)} ({doc.get('format')})",
                                    role="valores leídos con la plantilla revisada; Isapres = total del sistema",
                                    locator="hojas: " + ", ".join(sorted({tab["sheet"] for tab in tables.values()})))
    V = lambda vid: values[vid]["value"]  # noqa: E731

    def derived(vid, val, formula, inputs, unit, period=t):
        values[vid] = value(vid, val, unit=unit, period=period, source=None, formula=formula, inputs=inputs, kind="derived")
        return val

    whos = [*codes, "sistema"]
    findings = []
    if "resultados" in topics:
        for w in whos:
            c = change(V(f"resultado_ejercicio.{w}.{t1}"), V(f"resultado_ejercicio.{w}.{t}"), result=True)
            derived(f"resultado_ejercicio.{w}.delta", c["delta"], "resultado(t) − resultado(t−12)",
                    [f"resultado_ejercicio.{w}.{t}", f"resultado_ejercicio.{w}.{t1}"], MM)
            if c["pct"] is not None:
                derived(f"resultado_ejercicio.{w}.pct", c["pct"], "Δ / resultado(t−12) × 100 (solo base y resultado positivos)",
                        [f"resultado_ejercicio.{w}.delta", f"resultado_ejercicio.{w}.{t1}"], "%")
        n_pos = sum(1 for c in codes if V(f"resultado_ejercicio.{c}.{t}") > 0)
        # Counts are evidence too (tied to the claim that cites them: 'n de N Isapres con utilidad').
        derived("conteo.isapres_con_utilidad", n_pos, "Isapres con resultado del ejercicio > 0", [f"resultado_ejercicio.{c}.{t}" for c in codes], "count")
        derived("conteo.isapres", len(codes), "Isapres en la planilla", [], "count")
        package["derived_ratios"] += [
            {"id": "conteo.isapres_con_utilidad", "value": n_pos, "unit": "count", "entity": None, "signed": False,
             "periods": [t], "requires_period": False, "formula": "Isapres con resultado > 0", "inputs": [],
             "scope": "system", "period_kind": "ytd", "trivial": True, "base": None},
            {"id": "conteo.isapres", "value": len(codes), "unit": "count", "entity": None, "signed": False,
             "periods": [t], "requires_period": False, "formula": "Isapres en la planilla", "inputs": [],
             "scope": "system", "period_kind": "ytd", "trivial": True, "base": None}]
        tr = change(V(f"resultado_ejercicio.sistema.{t1}"), V(f"resultado_ejercicio.sistema.{t}"), result=True)["transition"]
        if tr in ("loss_to_profit", "profit_to_loss"):
            findings.append({"type": "sign_change", "kpi": "resultado", "crossed": True, "strength": 1.0})
    if "ingresos_costos" in topics:
        for w in whos:
            for item in ("ingresos_operacionales", "costo_operacional"):
                c = change(V(f"{item}.{w}.{t1}"), V(f"{item}.{w}.{t}"), result=False)
                derived(f"{item}.{w}.delta", c["delta"], f"{item}(t) − {item}(t−12)", [f"{item}.{w}.{t}", f"{item}.{w}.{t1}"], MM)
                if c["pct"] is not None:
                    derived(f"{item}.{w}.pct", c["pct"], "Δ / valor(t−12) × 100", [f"{item}.{w}.delta", f"{item}.{w}.{t1}"], "%")
            for p in (t, t1):
                if V(f"ingresos_operacionales.{w}.{p}") > 0:
                    derived(f"costo_ingresos.{w}.{p}", V(f"costo_operacional.{w}.{p}") / V(f"ingresos_operacionales.{w}.{p}") * 100,
                            "costo operacional / ingresos operacionales × 100", [f"costo_operacional.{w}.{p}", f"ingresos_operacionales.{w}.{p}"], "%", p)
    if "siniestralidad" in topics:
        sil = all(("costo_sil", p) in have for p in ("t", "t_1"))
        levels = (registry["families"][FAMILY]["kpis"]["siniestralidad"]["threshold"] or {}).get("levels_pct") or []
        for w in whos:
            for p in (t, t1):
                num = [f"costo_prestaciones.{w}.{p}"] + ([f"costo_sil.{w}.{p}"] if sil else [])
                den = V(f"ingresos_cotizaciones.{w}.{p}")
                if den <= 0:
                    package["reconciliation"].update(ok=False, failures=[f"siniestralidad_denominator_not_positive:{w}.{p}"])
                    package.update(findings=[], kpis={}, revisions=[], constants=[], topics=topics)
                    return package
                derived(f"siniestralidad.{w}.{p}", sum(V(x) for x in num) / den * 100,
                        ("(costo de prestaciones + costo SIL)" if sil else "costo de prestaciones") + " / ingresos por cotizaciones × 100",
                        num + [f"ingresos_cotizaciones.{w}.{p}"], "%", p)
            derived(f"siniestralidad.{w}.pp", round(V(f"siniestralidad.{w}.{t}"), 1) - round(V(f"siniestralidad.{w}.{t1}"), 1),
                    "redondeo(siniestralidad t, 1) − redondeo(siniestralidad t−12, 1)",
                    [f"siniestralidad.{w}.{t}", f"siniestralidad.{w}.{t1}"], "pp")
        # Threshold on the rounded value the ficha shows (89,96 → '90,0%' crosses 90).
        s_t, s_1 = round(V(f"siniestralidad.sistema.{t}"), 1), round(V(f"siniestralidad.sistema.{t1}"), 1)
        for lvl in levels:
            if (s_t >= lvl) != (s_1 >= lvl):
                findings.append({"type": "threshold_crossed", "kpi": "siniestralidad", "level": lvl, "crossed": True, "strength": 1.0})
        package["siniestralidad_includes_sil"] = sil
    package["entities"] = [{"code": int(c), "name": names[c]} for c in codes]
    package["entity_codes"] = [int(c) for c in codes]
    package.update(findings=findings, topics=topics, revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
                   constants=[100, 12, *((registry["families"][FAMILY]["kpis"]["siniestralidad"].get("threshold") or {}).get("levels_pct") or [])],
                   kpis={"t1": t1, "codes": codes, "names": {c: names[c] for c in codes}},
                   tables_meta={tid: {"sheet": tab["sheet"], "sum_check": tab.get("sum_check")} for tid, tab in tables.items()})
    return package


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    v = package["values"]
    k = package["kpis"]
    t, t1 = package["period"], k["t1"]
    codes, names = k["codes"], k["names"]
    V = lambda vid: v[vid]["value"]  # noqa: E731
    month, mlabel, plabel = sf.month_name(t), sf.month_label(t), sf.month_label(t1)
    ytd = f"enero–{month}"
    topics = package["topics"]
    short = lambda p: f"{sf.month_short(p)} {p[:4]}"  # noqa: E731
    kpis, tabs, paragraphs = [], [], []

    def by_isapre(item: str, p: str) -> list[str]:
        return sorted(codes, key=lambda c: (-V(f"{item}.{c}.{p}"), names[c]))  # ranking (never computed under the Esencial HOLD)

    if "resultados" in topics:
        R, R1 = V(f"resultado_ejercicio.sistema.{t}"), V(f"resultado_ejercicio.sistema.{t1}")
        c = change(R1, R, result=True)
        n_pos = next(int(e["value"]) for e in package["derived_ratios"] if e["id"] == "conteo.isapres_con_utilidad")
        kpis.append({"id": "resultado", "label": f"Resultado del ejercicio ({ytd})", "value": f"{fmt_int(R)} {MM}", "prov": "C",
                     "lines": [f"{plabel}: {fmt_int(R1)} {MM}",
                               f"{sf.fmt_signed(c['delta'])} {MM} · variación % " + ("N/A (cambia de signo)" if c["pct"] is None
                                                                                   else fmt_dec(c["pct"], 1, signed=True) + "%")],
                     "refs": [f"resultado_ejercicio.sistema.{t}", f"resultado_ejercicio.sistema.{t1}", "resultado_ejercicio.sistema.delta"]
                     + (["resultado_ejercicio.sistema.pct"] if c["pct"] is not None else [])})
        c_sys = {"id": "f2-resultado", "form": "diverging", "unit": MM, "headline": "Resultado del ejercicio del sistema",
                 "subtitle": f"Millones de pesos, {ytd} de cada año",
                 "rows": [{"label": short(t1), "value": R1, "ref": f"resultado_ejercicio.sistema.{t1}"},
                          {"label": short(t), "value": R, "ref": f"resultado_ejercicio.sistema.{t}", "emphasis": True}],
                 "table": {"columns": ["Período", f"Resultado ({MM})"],
                           "rows": [[short(t1), fmt_int(R1)], [short(t), fmt_int(R)],
                                    ["Cambio", sf.fmt_signed(c["delta"])], ["Variación %", pct_cell(c["pct"])]]},
                 "source": "SIS, estadísticas financieras (IFRS). La variación % no se calcula si algún período tiene pérdida."}
        order = by_isapre("resultado_ejercicio", t)
        c_isa = {"id": "f2-resultado-isapres", "form": "diverging", "unit": MM, "headline": "Resultado por Isapre",
                 "subtitle": f"Millones de pesos, {ytd} {t[:4]}",
                 "rows": [{"label": names[x], "value": V(f"resultado_ejercicio.{x}.{t}"), "ref": f"resultado_ejercicio.{x}.{t}",
                           "emphasis": V(f"resultado_ejercicio.{x}.{t}") < 0} for x in order],
                 "table": {"columns": ["Isapre", short(t), short(t1), "Cambio", "Variación %"],
                           "rows": [[names[x], fmt_int(V(f"resultado_ejercicio.{x}.{t}")), fmt_int(V(f"resultado_ejercicio.{x}.{t1}")),
                                     sf.fmt_signed(V(f"resultado_ejercicio.{x}.delta")), pct_cell((v.get(f"resultado_ejercicio.{x}.pct") or {}).get("value"))]
                                    for x in order]
                           + [["Sistema", fmt_int(R), fmt_int(R1), sf.fmt_signed(c["delta"]), pct_cell(c["pct"])]]},
                 "source": "SIS. Las Isapres suman el total del sistema en la planilla capturada."}
        tab = {"id": "resultados", "label": "Resultados", "charts": [c_sys, c_isa], "text": [], "dek": None}
        sf.topic_fields(tab, f"{fmt_int(R)} {MM} a {month} · {n_pos} de {len(codes)} Isapres con utilidad",
                        index_refs=[f"resultado_ejercicio.sistema.{t}", "conteo.isapres_con_utilidad", "conteo.isapres"], kpis=[])
        tabs.append(tab)
        paragraphs.append(f"Entre enero y {month} el sistema Isapre registró una {result_phrase(R1, R, plabel)}.")
    if "ingresos_costos" in topics:
        I, I1 = V(f"ingresos_operacionales.sistema.{t}"), V(f"ingresos_operacionales.sistema.{t1}")
        C, C1 = V(f"costo_operacional.sistema.{t}"), V(f"costo_operacional.sistema.{t1}")
        ip = (v.get("ingresos_operacionales.sistema.pct") or {}).get("value")
        kpis.append({"id": "ingresos", "label": f"Ingresos operacionales ({ytd})", "value": f"{fmt_int(I)} {MM}", "prov": "C",
                     "lines": [f"{plabel}: {fmt_int(I1)} {MM}", f"variación % {pct_cell(ip)}"],
                     "refs": [f"ingresos_operacionales.sistema.{t}", f"ingresos_operacionales.sistema.{t1}"]
                     + (["ingresos_operacionales.sistema.pct"] if ip is not None else [])})
        c_ic = {"id": "f2-ingresos-costos", "form": "bars", "unit": MM, "headline": "Ingresos y costos operacionales del sistema",
                "subtitle": f"Millones de pesos, {ytd} de cada año",
                "rows": [{"label": f"Ingresos {short(t1)}", "value": I1, "ref": f"ingresos_operacionales.sistema.{t1}"},
                         {"label": f"Ingresos {short(t)}", "value": I, "ref": f"ingresos_operacionales.sistema.{t}", "emphasis": True},
                         {"label": f"Costos {short(t1)}", "value": C1, "ref": f"costo_operacional.sistema.{t1}"},
                         {"label": f"Costos {short(t)}", "value": C, "ref": f"costo_operacional.sistema.{t}", "emphasis": True}],
                "table": {"columns": ["Concepto", short(t1), short(t), "Variación %"],
                          "rows": [["Ingresos operacionales", fmt_int(I1), fmt_int(I), pct_cell(ip)],
                                   ["Costo operacional", fmt_int(C1), fmt_int(C),
                                    pct_cell((v.get("costo_operacional.sistema.pct") or {}).get("value"))]]},
                "source": "SIS, estadísticas financieras (IFRS). Montos nominales."}
        order = by_isapre("ingresos_operacionales", t)
        c_ii = {"id": "f2-ingresos-isapres", "form": "bars", "unit": MM, "headline": "Ingresos operacionales por Isapre",
                "subtitle": f"Millones de pesos, {ytd} {t[:4]}",
                "rows": [{"label": names[x], "value": V(f"ingresos_operacionales.{x}.{t}"), "ref": f"ingresos_operacionales.{x}.{t}"} for x in order],
                "table": {"columns": ["Isapre", f"Ingresos {short(t)}", f"Costos {short(t)}", f"Ingresos {short(t1)}", f"Costos {short(t1)}"],
                          "rows": [[names[x], fmt_int(V(f"ingresos_operacionales.{x}.{t}")), fmt_int(V(f"costo_operacional.{x}.{t}")),
                                    fmt_int(V(f"ingresos_operacionales.{x}.{t1}")), fmt_int(V(f"costo_operacional.{x}.{t1}"))] for x in order]},
                "source": "SIS. Las Isapres suman el total del sistema en la planilla capturada."}
        tab = {"id": "ingresos_costos", "label": "Ingresos y costos", "charts": [c_ic, c_ii], "text": [], "dek": None}
        line = (f"Ingresos {pct_cell(ip)} vs. {plabel}" if ip is not None else f"Ingresos {fmt_int(I)} {MM} a {month}")
        sf.topic_fields(tab, line, index_refs=(["ingresos_operacionales.sistema.pct"] if ip is not None
                                               else [f"ingresos_operacionales.sistema.{t}"]), kpis=[])
        tabs.append(tab)
        paragraphs.append(f"Los ingresos operacionales sumaron {fmt_int(I)} {MM} y el costo operacional {fmt_int(C)} {MM} entre enero y {month}.")
    if "siniestralidad" in topics:
        S, S1 = V(f"siniestralidad.sistema.{t}"), V(f"siniestralidad.sistema.{t1}")
        pp = V("siniestralidad.sistema.pp")
        kpis.append({"id": "siniestralidad", "label": "Siniestralidad", "value": fmt_dec(S, 1) + "%", "prov": "C",
                     "lines": ["de los ingresos por cotizaciones", f"{plabel}: {fmt_dec(S1, 1)}% ({fmt_dec(pp, 1, signed=True)} pp)"],
                     "refs": [f"siniestralidad.sistema.{t}", f"siniestralidad.sistema.{t1}", "siniestralidad.sistema.pp"]})
        c_s = {"id": "f2-siniestralidad", "form": "bars", "unit": "%", "digits": 1, "headline": "Siniestralidad del sistema",
               "subtitle": f"% de los ingresos por cotizaciones, {ytd} de cada año",
               "rows": [{"label": short(t1), "value": S1, "ref": f"siniestralidad.sistema.{t1}"},
                        {"label": short(t), "value": S, "ref": f"siniestralidad.sistema.{t}", "emphasis": True}],
               "table": {"columns": ["Período", "Costo de prestaciones" + (" + SIL" if package.get("siniestralidad_includes_sil") else ""),
                                     "Ingresos por cotizaciones", "Siniestralidad"],
                         "rows": [[short(p), fmt_int(V(f"costo_prestaciones.sistema.{p}") + (V(f"costo_sil.sistema.{p}") if package.get("siniestralidad_includes_sil") else 0)),
                                   fmt_int(V(f"ingresos_cotizaciones.sistema.{p}")), fmt_dec(V(f"siniestralidad.sistema.{p}"), 1) + "%"]
                                  for p in (t1, t)]},
               "source": "Denominador: ingresos por cotizaciones del mismo período acumulado."}
        order = sorted(codes, key=lambda x: (-V(f"siniestralidad.{x}.{t}"), names[x]))
        c_si = {"id": "f2-siniestralidad-isapres", "form": "bars", "unit": "%", "digits": 1, "headline": "Siniestralidad por Isapre",
                "subtitle": f"% de los ingresos por cotizaciones de cada Isapre, {ytd} {t[:4]}",
                "rows": [{"label": names[x], "value": V(f"siniestralidad.{x}.{t}"), "ref": f"siniestralidad.{x}.{t}"} for x in order],
                "table": {"columns": ["Isapre", short(t), short(t1), "Cambio (pp)"],
                          "rows": [[names[x], fmt_dec(V(f"siniestralidad.{x}.{t}"), 1) + "%", fmt_dec(V(f"siniestralidad.{x}.{t1}"), 1) + "%",
                                    fmt_dec(V(f"siniestralidad.{x}.pp"), 1, signed=True)] for x in order]},
                "source": "Denominador: ingresos por cotizaciones de cada Isapre, mismo período acumulado."}
        tab = {"id": "siniestralidad", "label": "Siniestralidad", "charts": [c_s, c_si], "text": [], "dek": None}
        sf.topic_fields(tab, f"{fmt_dec(S, 1)}% de las cotizaciones · {fmt_dec(pp, 1, signed=True)} pp",
                        index_refs=[f"siniestralidad.sistema.{t}", "siniestralidad.sistema.pp"], kpis=[])
        tabs.append(tab)
        word = "mayor" if pp > 0 else ("menor" if pp < 0 else "igual")
        paragraphs.append(f"La siniestralidad fue {fmt_dec(S, 1)}% de los ingresos por cotizaciones, "
                          f"{word} que el {fmt_dec(S1, 1)}% de {plabel}." if pp else
                          f"La siniestralidad fue {fmt_dec(S, 1)}% de los ingresos por cotizaciones, igual que en {plabel}.")
    if "patrimonio" in topics:
        P = V(f"patrimonio.sistema.{t}")
        kpis.append({"id": "patrimonio", "label": "Patrimonio", "value": f"{fmt_int(P)} {MM}", "prov": "C",
                     "lines": [f"stock al cierre de {mlabel}"], "refs": [f"patrimonio.sistema.{t}"]})
        order = by_isapre("patrimonio", t)
        has1 = all(f"patrimonio.{x}.{t1}" in v for x in codes)
        c_p = {"id": "f2-patrimonio", "form": "diverging", "unit": MM, "headline": "Patrimonio por Isapre",
               "subtitle": f"Millones de pesos al cierre de {mlabel}",
               "rows": [{"label": names[x], "value": V(f"patrimonio.{x}.{t}"), "ref": f"patrimonio.{x}.{t}",
                         "emphasis": V(f"patrimonio.{x}.{t}") < 0} for x in order],
               "table": {"columns": ["Isapre", short(t)] + ([short(t1)] if has1 else []),
                         "rows": [[names[x], fmt_int(V(f"patrimonio.{x}.{t}"))] + ([fmt_int(V(f"patrimonio.{x}.{t1}"))] if has1 else [])
                                  for x in order] + [["Sistema", fmt_int(P)] + ([fmt_int(V(f"patrimonio.sistema.{t1}"))] if has1 else [])]},
               "source": "SIS. Stock al cierre; no se suma entre trimestres."}
        tab = {"id": "patrimonio", "label": "Patrimonio", "charts": [c_p], "text": [], "dek": None}
        sf.topic_fields(tab, f"{fmt_int(P)} {MM} al cierre de {month}", index_refs=[f"patrimonio.sistema.{t}"], kpis=[])
        tabs.append(tab)

    headline = tpl["headline"]["default"].format(
        month_label=mlabel, resultado=result_phrase(V(f"resultado_ejercicio.sistema.{t1}"), V(f"resultado_ejercicio.sistema.{t}"), plabel)
        if "resultados" in topics else "estados financieros del sistema")
    headline = headline[0].upper() + headline[1:]
    # The dek adds what the KPI cards do not show (Dirección 29-oct): the cost/income ratio and the spread across Isapres.
    dek_parts = []
    if "ingresos_costos" in topics and f"costo_ingresos.sistema.{t}" in v and f"costo_ingresos.sistema.{t1}" in v:
        dek_parts.append(f"El costo operacional absorbió el {fmt_dec(V(f'costo_ingresos.sistema.{t}'), 1)}% de los ingresos operacionales "
                         f"({fmt_dec(V(f'costo_ingresos.sistema.{t1}'), 1)}% en {plabel}).")
    if "siniestralidad" in topics:
        lo = min(codes, key=lambda x: (V(f"siniestralidad.{x}.{t}"), names[x]))
        hi = max(codes, key=lambda x: (V(f"siniestralidad.{x}.{t}"), names[x]))
        dek_parts.append(f"Por Isapre, la siniestralidad va de {fmt_dec(V(f'siniestralidad.{lo}.{t}'), 1)}% ({names[lo]}) a "
                         f"{fmt_dec(V(f'siniestralidad.{hi}.{t}'), 1)}% ({names[hi]}).")
    dek = " ".join(dek_parts) or paragraphs[0]
    published = date.fromisoformat(package["published_at"][:10])
    expected = date.fromordinal(published.toordinal() + int(cfg["calendar"]["expected_release_interval_days"]))
    nxt = sf.shift_period(t, 3)
    late = (decision or {}).get("late_release")
    watch = [({"headline": f"Estadísticas financieras a {sf.month_label(nxt)}: publicación atrasada.",
               "explanation": f"Lleva {late['days_late']} días de atraso según el calendario histórico."} if late else
              {"headline": f"Estadísticas financieras a {sf.month_label(nxt)} (la SIS las publicaría hacia el {sf.day_label(expected)}).",
               "explanation": "Un cambio de signo del resultado o un cruce de 90% o 95% de siniestralidad destaca la ficha."})]
    notes = [
        {"id": "n1", "text": f"Resultados, ingresos y costos son flujos acumulados de enero a {month}, no stocks; se comparan con el mismo "
                             "período del año anterior. El patrimonio es un stock al cierre. Montos nominales en millones de pesos; "
                             "el valor real (UF) queda pendiente."},
        {"id": "n2", "text": "Denominadores: la siniestralidad usa los ingresos por cotizaciones del mismo período acumulado; la variación % "
                             "usa el valor del año anterior y no se calcula (N/A) cuando un resultado cambia de signo o parte de una pérdida."},
        {"id": "n3", "text": "Cada cifra se lee de la planilla capturada (hash en Fuentes) con una plantilla de hoja, columnas y filas revisada "
                             "por una persona; en cada columna las Isapres suman el total del sistema."},
        {"id": "n4", "text": "Ningún dato de esta ficha establece por qué cambian los resultados, los costos o la siniestralidad."},
    ]
    sources = [{**src, "key": key} for key, src in package["sources"].items()]
    triggers = (decision or {}).get("triggers") or []
    rule = "nuevo período" if "new_period" in triggers else ("revisión" if "revision" in triggers else "publicación vigente")
    machine = (f"Ficha generada por la regla \"{rule}\" (publicación del {sf.day_label(package['published_at'])}). Las cifras vienen del "
               "paquete de evidencia; solo la Lectura Alicanto puede escribirla un modelo, y pasa por un verificador.")
    return {
        "schema_version": sf.SCHEMA, "id": f"stats-ficha:{FAMILY}:{t}", "family": FAMILY, "family_label": cfg["label"],
        "slug": cfg["slug"], "period": t, "published_at": package["published_at"], "release_key": package["release_key"],
        "kicker": tpl["kicker"].format(label=cfg["label"]),
        "kicker_meta": tpl["kicker_meta"].format(period_label=mlabel, published_label=sf.day_label(package["published_at"]),
                                                 cadence_phrase=cfg["cadence_phrase"]),
        "headline": headline, "headline_type": "default", "dek": dek, "dek_emphasis": None,
        "kpis": kpis[:5], "tabs": tabs,
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs, "rendered_in_tabs": True},
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
