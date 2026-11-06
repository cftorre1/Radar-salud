"""F13 · Licencias médicas en Isapres (SIS, datos abiertos): package, ficha and checks.

Input: ``data/sis_open_data_aggregates/<quarter>/licencias_<q>.json`` only (``sis_open_data.load_quarter``), the latest
quarter and the one before, aggregated in GitHub Actions from the SIS quarterly ZIP "Licencias Médicas". Nothing is
downloaded here. The aggregates exist only by Isapre, diagnosis group (CIE-10 chapter of the principal diagnosis),
industry (actividad laboral), region and tipo de profesional, plus the two-way cell Isapre × diagnosis group, each
with at least 10 licences (Dirección 5-nov-2026). There is never a breakdown by physician, worker or employer.

What the ficha shows: % rechazadas and % reducidas (over licences resolved in the file), días autorizados / días
solicitados, subsidio líquido por licencia, by Isapre, diagnosis group, industry, region and tipo de profesional; the
mental-health (F00–F99) vs. respiratory (J00–J99) contrast. Reception and resolution dates come only as quarters
('2026t2'): no "days to resolve" is computed; the share resolved in the quarter of reception is shown instead.

Reconciliation (any failure → HOLD): the files of both quarters match their receipts (``sis_open_data``); every shown
cell has ≥ 10 licences (re-checked here); in each breakdown the published cells plus the suppressed ones add up to the
total; rejected + reduced + authorised + extended ≤ 100 % and ≥ 99 % in every row; every Isapre code has a name.

First publication: like F4/F7, a PASS waits in ``hold/`` (``awaiting_first_review``, previewed on staging) until
``families.F13.first_review`` records ``reviewed_by`` and ``reviewed_sha256`` = the ficha's ``evidence_sha256``. The
Lectura stays off (``lectura_enabled: false``): no model call.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import sis_open_data as so
from . import stats_fichas as sf
from .stats_ficha_f12 import fmt, money
from .stats_fichas import value

FAMILY = "F13"
BUILDER_VERSION = "f13_licencias_v1"
DATASET = "Licencias Medicas"
MIN_CELL = 10
DIMS = {"isapre": "isapre", "diagnostico": "diag", "actividad_laboral": "act", "region": "region", "tipo_profesional": "prof"}
MENTAL, RESP = "F00-F99", "J00-J99"
# CIE-10 chapters (principal diagnosis group as the SIS file writes it) → short labels (≤ 18 characters).
DIAG = {"A00-B99": "Infecciosas", "C00-D48": "Tumores", "D50-D89": "Sangre", "E00-E90": "Endocrinas", "F00-F99": "Salud mental",
        "G00-G99": "Sistema nervioso", "H00-H59": "Ojo", "H60-H95": "Oído", "I00-I99": "Circulatorias", "J00-J99": "Respiratorias",
        "K00-K93": "Digestivas", "L00-L99": "Piel", "M00-M99": "Osteomusculares", "N00-N99": "Genitourinarias",
        "O00-O99": "Embarazo y parto", "P00-P96": "Perinatales", "Q00-Q99": "Congénitas", "R00-R99": "Síntomas (R)",
        "S00-T98": "Traumatismos", "U00-U99": "Códigos U", "V01-Y98": "Causas externas", "Z00-Z99": "Factores (Z)",
        "(vacío)": "Sin diagnóstico"}
ACT = {"Electricidad,gas,agua": "Electricidad/agua", "Mineria": "Minería", "Construccion": "Construcción"}
PROF = {"Medico": "Médico", "Matrona": "Matrona", "Dentista": "Dentista"}
METRICS = {"licencias": ("licencias", "licencias"), "pct_rechazadas": ("pct_rech", "%"), "pct_reducidas": ("pct_red", "%"),
           "pct_autorizadas": ("pct_aut", "%"), "ratio_autorizados_solicitados_pct": ("dias_ratio", "%"),
           "dias_solicitados": ("dias_sol", "días"), "dias_autorizados": ("dias_aut", "días"),
           "subsidio_total": ("subsidio_mm", "MM$"), "subsidio_por_licencia": ("subsidio_lic", "$"),
           "subsidio_por_licencia_con_pago": ("subsidio_pago", "$"), "pct_con_subsidio": ("pct_subsidio", "%"),
           "pct_resuelta_mismo_trimestre_recepcion": ("pct_mismo_trim", "%")}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", sf._fold(text)).strip("_") or "vacio"


def label(dim: str, key: str) -> str:
    """Short label (≤ 18 characters, chart rule); an unknown group keeps the SIS text, shortened."""
    out = {"diagnostico": DIAG, "actividad_laboral": ACT, "tipo_profesional": PROF, "region": so.REGIONS}.get(dim, {}).get(key, key)
    return out if len(out) <= 18 else out[:17] + "…"


def row_failures(row: dict, tag: str) -> list[str]:
    f = []
    n = row.get("licencias")
    if not isinstance(n, int) or n < MIN_CELL:
        f.append(f"cell_under_min:{tag}")
    s = sum(row.get(k) or 0 for k in ("pct_rechazadas", "pct_reducidas", "pct_autorizadas", "pct_ampliadas"))
    if not 99.0 <= s <= 100.05:
        f.append(f"resolution_shares_do_not_add:{tag}:{round(s, 2)}")
    return f


def _quarter(root: Path, q: str, names: dict[str, str]) -> tuple[dict, list[str]]:
    data, failures = so.load_quarter(root, q, DATASET)
    if failures:
        return data, failures
    lic = data["files"][f"licencias_{q}.json"]
    tot = lic.get("total") or {}
    failures += row_failures(tot, f"{q}:total")
    if tot.get("licencias") != data["receipt"]["parse"]["rows_ok"]:
        failures.append(f"total_not_rows:{q}")
    if lic.get("regla_celda_minima") != MIN_CELL:
        failures.append(f"min_cell_rule:{q}:{lic.get('regla_celda_minima')}")
    bd = lic.get("breakdowns") or {}
    for dim in DIMS:
        b = bd.get(dim)
        if not b:
            failures.append(f"breakdown_missing:{q}:{dim}")
            continue
        rows = b.get("filas") or []
        if sum(r.get("licencias") or 0 for r in rows) + (b.get("licencias_en_celdas_suprimidas") or 0) != tot.get("licencias"):
            failures.append(f"breakdown_does_not_add:{q}:{dim}")
        for r in rows:
            failures += row_failures(r, f"{q}:{dim}:{r.get('grupo')}")
            if dim == "isapre" and str(r.get("grupo")) not in names:
                failures.append(f"isapre_without_name:{r.get('grupo')}")
    cross = ((lic.get("cruces") or {}).get("isapre_x_diagnostico") or {})
    for r in cross.get("filas") or []:
        failures += row_failures(r, f"{q}:xd:{r.get('grupo')}")
    if sum(r.get("licencias") or 0 for r in cross.get("filas") or []) + (cross.get("licencias_en_celdas_suprimidas") or 0) != tot.get("licencias"):
        failures.append(f"cross_does_not_add:{q}")
    data["lic"] = lic
    return data, sorted(set(failures))


def _hold(package: dict, failures: list[str]) -> dict:
    package["reconciliation"].update(ok=False, failures=failures)
    package.update(findings=[], kpis={}, revisions=[], constants=[])
    return package


def build_package(root: Path, registry: dict | None = None, previous_live: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    root = Path(root)
    names = so.isapre_names(root)
    qs = []
    for q in so.quarters(root):
        rec = so.load_json(root / so.AGG_ROOT / q / f"receipts_{q}.json") or {}
        if rec.get("script_version") == so.SCRIPT_VERSION and any(f.get("dataset") == DATASET for f in rec.get("files") or []):
            qs.append(q)
    package: dict[str, Any] = {
        "family": FAMILY, "period": None, "periods": [], "published_at": None, "date_basis": "first_detected",
        "release_key": None, "primary_source": {}, "sources": {}, "values": {}, "entities": [], "entity_codes": [],
        "entity_keys": [], "causal_note": None, "provisional": False,
        "reconciliation": {"ok": False, "failures": [], "checks": [
            "cada archivo agregado nombra el trimestre, la versión del script y el SHA-256 del ZIP de su recibo",
            "licencias agregadas = filas leídas del ZIP; ≤ 0,1 % de filas malformadas; ZIP ≤ 1 GiB desde datos.superdesalud.gob.cl",
            "cada celda mostrada tiene ≥ 10 licencias; celdas publicadas + suprimidas = total, en cada desglose y en el cruce",
            "rechazadas + reducidas + autorizadas + ampliadas entre 99 % y 100 % en cada fila",
            "toda Isapre con nombre en data/entities/isapres.json"]},
        "lectura_pool": [], "derived_ratios": [], "ranks": [],
    }
    if not qs:
        package["reconciliation"]["failures"] = ["no_quarter_aggregated"]
        return package
    q = qs[-1]
    package["period"] = so.period_of(q)
    cur, failures = _quarter(root, q, names)
    pq = so.previous_quarter(q)
    prev = None
    if pq in qs:
        prev, pf = _quarter(root, pq, names)
        failures += [f"previous:{x}" for x in pf]
    if failures:
        return _hold(package, failures)

    values: dict[str, dict] = {}
    sources: dict[str, dict] = {}

    def src(data: dict, qq: str) -> str:
        key = "lic_" + qq
        if key not in sources:
            e = data["receipt"]
            sources[key] = so.source_for(e, label=f"SIS · Licencias médicas {so.quarter_label(qq)} (datos abiertos)",
                                         role="ZIP trimestral; agregados de Alicanto por Isapre, diagnóstico, industria, región y tipo de profesional",
                                         locator=f"{(e.get('parse') or {}).get('rows_ok')} licencias; agregación en GitHub Actions",
                                         detected=str(data.get("generated_at") or "")[:10] or None)
        return key

    def put_row(prefix: str, row: dict, qq: str, data: dict, loc: str) -> None:
        for key, (vid, unit) in METRICS.items():
            x = row.get(key)
            if x is None:
                continue
            if key == "subsidio_total":
                x = round(x / 1e6, 3)
            values[f"{prefix}.{vid}"] = value(f"{prefix}.{vid}", x, unit=unit, period=so.period_of(qq), source=src(data, qq), locator=loc)

    keys: dict[str, list[str]] = {}
    for qq, data in ((q, cur), (pq, prev)):
        if not data:
            continue
        lic = data["lic"]
        put_row(f"lic.{qq}.total", lic["total"], qq, data, f"licencias_{qq}.json · total")
        for dim, short in DIMS.items():
            for r in lic["breakdowns"][dim]["filas"]:
                g = str(r["grupo"])
                put_row(f"lic.{qq}.{short}.{slug(g) if dim != 'isapre' else g}", r, qq, data, f"licencias_{qq}.json · {dim} · {g}")
                if qq == q:
                    keys.setdefault(dim, []).append(g)
        if qq == q:
            for r in (lic.get("cruces") or {}).get("isapre_x_diagnostico", {}).get("filas") or []:
                put_row(f"lic.{qq}.xd.{r['isapre']}.{slug(r['diagnostico'])}", r, qq, data,
                        f"licencias_{qq}.json · isapre × diagnóstico · {r['isapre']} · {r['diagnostico']}")
        for dim in DIMS:
            b = lic["breakdowns"][dim]
            values[f"lic.{qq}.{DIMS[dim]}.suprimidas"] = value(f"lic.{qq}.{DIMS[dim]}.suprimidas", b.get("licencias_en_celdas_suprimidas") or 0,
                                                              unit="licencias", period=so.period_of(qq), source=src(data, qq),
                                                              locator=f"licencias_{qq}.json · {dim} · celdas < 10")
    ratio = None
    m, r_ = f"lic.{q}.diag.{slug(MENTAL)}.pct_rech", f"lic.{q}.diag.{slug(RESP)}.pct_rech"
    if m in values and r_ in values and values[r_]["value"] > 0:
        ratio = values[m]["value"] / values[r_]["value"]
        values["ratio.mental_resp"] = value("ratio.mental_resp", ratio, unit="veces", period=so.period_of(q), source=None,
                                            formula="% rechazo F00–F99 / % rechazo J00–J99", inputs=[m, r_], kind="derived")
    min_head = int(cfg.get("headline_min_licencias") or 1000)
    big = [c for c in keys.get("isapre", []) if values[f"lic.{q}.isapre.{c}.licencias"]["value"] >= min_head]
    big = sorted(big, key=lambda c: -values[f"lic.{q}.isapre.{c}.pct_rech"]["value"])
    ev = so.evidence_sha256(sources)
    detected = str(cur.get("generated_at") or "")[:10] or None
    package.update(
        period=so.period_of(q), periods=[so.period_of(x) for x in (pq, q) if x == q or prev],
        published_at=detected, date_basis="first_detected", release_key=sf.release_key(so.period_of(q), ev),
        evidence_sha256=ev, primary_source={"url": cur["receipt"]["url"], "sha256": cur["receipt"]["sha256"]},
        sources=sources, values=values, findings=[],
        entities=[{"code": int(c), "name": names[c]} for c in keys.get("isapre", []) if c.isdigit()],
        entity_codes=[int(c) for c in keys.get("isapre", []) if c.isdigit()],
        revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
        constants=[0, 1, 2, 3, 4, 10, 100, 256, min_head],
        kpis={"q": q, "pq": pq if prev else None, "keys": keys, "ratio": ratio, "big": big},
    )
    package["reconciliation"].update(ok=True, failures=[])
    return package


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    v = package["values"]
    k = package["kpis"]
    q, pq = k["q"], k["pq"]
    V = lambda vid: v[vid]["value"]  # noqa: E731
    pc = lambda vid: fmt(V(vid), 1) + "%"  # noqa: E731
    names = {str(e["code"]): e["name"] for e in package["entities"]}
    ql = so.quarter_label(q)
    T = f"lic.{q}.total"
    keys = k["keys"]

    def vid(dim: str, g: str, metric: str, qq: str = q) -> str:
        return f"lic.{qq}.{DIMS[dim]}.{g if dim == 'isapre' else slug(g)}.{metric}"

    def lab(dim: str, g: str) -> str:
        return names[g] if dim == "isapre" else label(dim, g)

    def bars(cid: str, dim: str, metric: str, headline: str, subtitle: str, groups: list[str], source: str, unit: str = "%",
             digits: int = 1, table: dict | None = None) -> dict:
        rows = [{"label": lab(dim, g), "value": V(vid(dim, g, metric)), "ref": vid(dim, g, metric)}
                for g in groups if vid(dim, g, metric) in v][:12]
        return {"id": cid, "form": "bars", "unit": unit, "digits": digits, "headline": headline, "subtitle": subtitle,
                "rows": rows, "table": table or {"columns": ["Grupo", "Valor"], "rows": [[r["label"], fmt(r["value"], digits)] for r in rows]},
                "source": source}

    def full_table(dim: str, groups: list[str]) -> dict:
        cols = ["Grupo", "Licencias", "Rechazadas", "Reducidas", "Días autorizados / solicitados", "Subsidio por licencia",
                "Resueltas en el trimestre de recepción"]
        if pq:
            cols.append(f"Rechazadas {so.quarter_tag(pq)}")
        rows = []
        for g in groups:
            r = [lab(dim, g), fmt(V(vid(dim, g, "licencias")), 0), pc(vid(dim, g, "pct_rech")), pc(vid(dim, g, "pct_red")),
                 pc(vid(dim, g, "dias_ratio")), money(V(vid(dim, g, "subsidio_lic"))) if vid(dim, g, "subsidio_lic") in v else "",
                 pc(vid(dim, g, "pct_mismo_trim")) if vid(dim, g, "pct_mismo_trim") in v else ""]
            if pq:
                r.append(pc(vid(dim, g, "pct_rech", pq)) if vid(dim, g, "pct_rech", pq) in v else "sin dato")
            rows.append(r)
        sup = V(f"lic.{q}.{DIMS[dim]}.suprimidas")
        if sup:
            rows.append(["Celdas con menos de 10 licencias (sin desglose)", fmt(sup, 0), "", "", "", "", ""] + ([""] if pq else []))
        return {"columns": cols, "rows": rows}

    src = "SIS, datos abiertos de licencias médicas (ZIP trimestral); agregados de Alicanto con celda mínima de 10 licencias."
    by_rech = lambda dim, gs: sorted(gs, key=lambda g: -V(vid(dim, g, "pct_rech")))  # noqa: E731
    by_n = lambda dim, gs: sorted(gs, key=lambda g: -V(vid(dim, g, "licencias")))  # noqa: E731
    tabs, paragraphs = [], []

    # Topic 1: by Isapre.
    iss = by_rech("isapre", keys["isapre"])
    charts = [bars("f13-rechazo-isapre", "isapre", "pct_rech", "Licencias rechazadas, por Isapre",
                   f"% de las licencias resueltas en {ql}", iss, src, table=full_table("isapre", by_n("isapre", keys["isapre"]))),
              bars("f13-reduccion-isapre", "isapre", "pct_red", "Licencias reducidas, por Isapre",
                   f"% de las licencias resueltas en {ql} con menos días que los pedidos",
                   sorted(keys["isapre"], key=lambda g: -V(vid("isapre", g, "pct_red"))), src)]
    tab = {"id": "isapres", "label": "Por Isapre", "charts": charts, "text": [], "dek": None}
    big = k["big"]
    if len(big) >= 2:
        hi, lo = big[0], big[-1]
        sf.topic_fields(tab, f"Rechazo: {names[lo]} {pc(vid('isapre', lo, 'pct_rech'))} a {names[hi]} {pc(vid('isapre', hi, 'pct_rech'))}",
                        index_refs=[vid("isapre", lo, "pct_rech"), vid("isapre", hi, "pct_rech")], kpis=[])
        paragraphs.append(f"Entre las Isapres con más de {fmt(cfg.get('headline_min_licencias') or 1000, 0)} licencias, el rechazo va de "
                          f"{pc(vid('isapre', lo, 'pct_rech'))} ({names[lo]}) a {pc(vid('isapre', hi, 'pct_rech'))} ({names[hi]}).")
    else:
        sf.topic_fields(tab, None, kpis=[])
    tabs.append(tab)

    # Topic 2: by diagnosis group, and mental health by Isapre.
    dg = [g for g in by_n("diagnostico", keys["diagnostico"])][:12]
    charts = [bars("f13-rechazo-diagnostico", "diagnostico", "pct_rech", "Rechazo por grupo de diagnóstico",
                   f"% de licencias rechazadas, 12 grupos CIE-10 con más licencias, {ql}", by_rech("diagnostico", dg), src,
                   table=full_table("diagnostico", by_n("diagnostico", keys["diagnostico"])))]
    xm = [c for c in keys["isapre"] if f"lic.{q}.xd.{c}.{slug(MENTAL)}.pct_rech" in v]
    if len(xm) >= 2:
        xm = sorted(xm, key=lambda c: -V(f"lic.{q}.xd.{c}.{slug(MENTAL)}.pct_rech"))
        charts.append({"id": "f13-mental-isapre", "form": "bars", "unit": "%", "digits": 1,
                       "headline": "Salud mental: rechazo por Isapre",
                       "subtitle": f"% de licencias F00–F99 rechazadas, {ql}; Isapres con ≥ 10 licencias en el grupo",
                       "rows": [{"label": names[c], "value": V(f"lic.{q}.xd.{c}.{slug(MENTAL)}.pct_rech"),
                                 "ref": f"lic.{q}.xd.{c}.{slug(MENTAL)}.pct_rech"} for c in xm[:12]],
                       "table": {"columns": ["Isapre", "Licencias F00–F99", "Rechazadas F00–F99", "Rechazadas J00–J99"],
                                 "rows": [[names[c], fmt(V(f"lic.{q}.xd.{c}.{slug(MENTAL)}.licencias"), 0),
                                           pc(f"lic.{q}.xd.{c}.{slug(MENTAL)}.pct_rech"),
                                           pc(f"lic.{q}.xd.{c}.{slug(RESP)}.pct_rech") if f"lic.{q}.xd.{c}.{slug(RESP)}.pct_rech" in v else "sin dato"]
                                          for c in xm]},
                       "source": src})
    tab = {"id": "diagnostico", "label": "Diagnóstico", "charts": charts, "text": [], "dek": None}
    has_mr = k["ratio"] is not None
    if has_mr:
        sf.topic_fields(tab, f"Salud mental {pc(vid('diagnostico', MENTAL, 'pct_rech'))} · respiratorias {pc(vid('diagnostico', RESP, 'pct_rech'))}",
                        index_refs=[vid("diagnostico", MENTAL, "pct_rech"), vid("diagnostico", RESP, "pct_rech")], kpis=[])
        paragraphs.append(f"Las licencias de salud mental (F00–F99) se rechazan {fmt(V('ratio.mental_resp'), 1)} veces más que las "
                          "respiratorias (J00–J99).")
    else:
        sf.topic_fields(tab, None, kpis=[])
    tabs.append(tab)

    # Topic 3: industry and tipo de profesional.
    act = by_rech("actividad_laboral", keys["actividad_laboral"])
    charts = [bars("f13-rechazo-industria", "actividad_laboral", "pct_rech", "Rechazo por actividad laboral",
                   f"% de licencias rechazadas según la actividad del trabajador, {ql}", act, src,
                   table=full_table("actividad_laboral", by_n("actividad_laboral", keys["actividad_laboral"])))]
    if len(keys.get("tipo_profesional", [])) >= 2:
        charts.append(bars("f13-rechazo-profesional", "tipo_profesional", "pct_rech", "Rechazo según quien emite",
                           f"% de licencias rechazadas por tipo de profesional emisor, {ql}",
                           by_rech("tipo_profesional", keys["tipo_profesional"]), src,
                           table=full_table("tipo_profesional", by_n("tipo_profesional", keys["tipo_profesional"]))))
    tab = {"id": "industria", "label": "Industria y emisor", "charts": charts, "text": [], "dek": None}
    a0, a1 = act[0], act[-1]
    sf.topic_fields(tab, f"{label('actividad_laboral', a0)} {pc(vid('actividad_laboral', a0, 'pct_rech'))} · "
                         f"{label('actividad_laboral', a1)} {pc(vid('actividad_laboral', a1, 'pct_rech'))}",
                    index_refs=[vid("actividad_laboral", a0, "pct_rech"), vid("actividad_laboral", a1, "pct_rech")], kpis=[])
    tabs.append(tab)

    # Topic 4: region.
    regs = [g for g in keys["region"] if g != "0"]
    top_regs = by_rech("region", by_n("region", regs)[:12])
    charts = [bars("f13-rechazo-region", "region", "pct_rech", "Rechazo por región",
                   f"% de licencias rechazadas, 12 regiones con más licencias, {ql}", top_regs, src,
                   table=full_table("region", by_n("region", keys["region"])))]
    tab = {"id": "region", "label": "Región", "charts": charts, "text": [], "dek": None}
    r0, r1 = top_regs[0], top_regs[-1]
    sf.topic_fields(tab, f"{label('region', r1)} {pc(vid('region', r1, 'pct_rech'))} a {label('region', r0)} {pc(vid('region', r0, 'pct_rech'))}",
                    index_refs=[vid("region", r1, "pct_rech"), vid("region", r0, "pct_rech")], kpis=[])
    tabs.append(tab)

    # Topic 5: days requested vs authorised.
    charts = [bars("f13-dias-isapre", "isapre", "dias_ratio", "Días autorizados sobre días solicitados",
                   f"% de los días pedidos que la Isapre autorizó, {ql}",
                   sorted(keys["isapre"], key=lambda g: V(vid("isapre", g, "dias_ratio"))), src,
                   table={"columns": ["Isapre", "Días solicitados", "Días autorizados", "Autorizados / solicitados"],
                          "rows": [[names[g], fmt(V(vid("isapre", g, "dias_sol")), 0), fmt(V(vid("isapre", g, "dias_aut")), 0),
                                    pc(vid("isapre", g, "dias_ratio"))] for g in by_n("isapre", keys["isapre"])]}),
              bars("f13-dias-diagnostico", "diagnostico", "dias_ratio", "Días autorizados por grupo de diagnóstico",
                   f"% de los días pedidos que se autorizaron, {ql}", sorted(dg, key=lambda g: V(vid("diagnostico", g, "dias_ratio"))), src,
                   table={"columns": ["Grupo", "Días solicitados", "Días autorizados", "Autorizados / solicitados"],
                          "rows": [[label("diagnostico", g), fmt(V(vid("diagnostico", g, "dias_sol")), 0),
                                    fmt(V(vid("diagnostico", g, "dias_aut")), 0), pc(vid("diagnostico", g, "dias_ratio"))] for g in dg]})]
    tab = {"id": "dias", "label": "Días autorizados", "charts": charts, "text": [], "dek": None}
    sf.topic_fields(tab, f"Sistema: {pc(f'{T}.dias_ratio')} de los días pedidos", index_refs=[f"{T}.dias_ratio"], kpis=[])
    tabs.append(tab)
    paragraphs.append(f"Las Isapres autorizaron el {pc(f'{T}.dias_ratio')} de los días de licencia solicitados en {ql}.")

    # Topic 6: subsidy.
    sub = [g for g in keys["isapre"] if vid("isapre", g, "subsidio_lic") in v]
    charts = [bars("f13-subsidio-isapre", "isapre", "subsidio_lic", "Subsidio pagado por licencia",
                   f"$ líquidos por licencia (todas las licencias del archivo), {ql}",
                   sorted(sub, key=lambda g: -V(vid("isapre", g, "subsidio_lic"))), src, unit="$", digits=0,
                   table={"columns": ["Isapre", "Subsidio total (MM$)", "Por licencia", "Por licencia con pago", "Con subsidio"],
                          "rows": [[names[g], fmt(V(vid("isapre", g, "subsidio_mm")), 0), money(V(vid("isapre", g, "subsidio_lic"))),
                                    money(V(vid("isapre", g, "subsidio_pago"))) if vid("isapre", g, "subsidio_pago") in v else "",
                                    pc(vid("isapre", g, "pct_subsidio"))] for g in by_n("isapre", sub)]}),
              bars("f13-con-subsidio-isapre", "isapre", "pct_subsidio", "Licencias con subsidio pagado",
                   f"% de licencias con subsidio líquido mayor que cero, {ql}",
                   sorted(sub, key=lambda g: -V(vid("isapre", g, "pct_subsidio"))), src)]
    tab = {"id": "subsidio", "label": "Subsidio", "charts": charts, "text": [], "dek": None}
    sf.topic_fields(tab, f"{money(V(f'{T}.subsidio_lic'))} por licencia; {money(V(f'{T}.subsidio_pago'))} con pago",
                    index_refs=[f"{T}.subsidio_lic", f"{T}.subsidio_pago"], kpis=[])
    tabs.append(tab)

    # KPI cards.
    def prev_line(metric: str) -> tuple[list[str], list[str]]:
        p = f"lic.{pq}.total.{metric}" if pq else None
        return ([f"{so.quarter_tag(pq)}: {pc(p)}"], [p]) if p and p in v else ([], [])
    pl, pr = prev_line("pct_rech")
    kpis = [{"id": "rechazo", "label": "Licencias rechazadas", "value": pc(f"{T}.pct_rech"), "prov": "C",
             "lines": [f"de {fmt(V(f'{T}.licencias'), 0)} licencias, {ql}", *pl], "refs": [f"{T}.pct_rech", f"{T}.licencias", *pr]}]
    pl, pr = prev_line("pct_red")
    kpis.append({"id": "reduccion", "label": "Licencias reducidas", "value": pc(f"{T}.pct_red"), "prov": "C",
                 "lines": ["con menos días que los pedidos", *pl], "refs": [f"{T}.pct_red", *pr]})
    kpis.append({"id": "dias", "label": "Días autorizados / solicitados", "value": pc(f"{T}.dias_ratio"), "prov": "C",
                 "lines": [f"{fmt(V(f'{T}.dias_aut'), 0)} de {fmt(V(f'{T}.dias_sol'), 0)} días"],
                 "refs": [f"{T}.dias_ratio", f"{T}.dias_aut", f"{T}.dias_sol"]})
    kpis.append({"id": "subsidio", "label": "Subsidio por licencia", "value": money(V(f"{T}.subsidio_lic")), "prov": "C",
                 "lines": [f"{money(V(f'{T}.subsidio_pago'))} por licencia con pago", f"{pc(f'{T}.pct_subsidio')} con subsidio"],
                 "refs": [f"{T}.subsidio_lic", f"{T}.subsidio_pago", f"{T}.pct_subsidio"]})
    if has_mr:
        kpis.append({"id": "salud_mental", "label": "Rechazo salud mental vs. respiratorias", "value": f"{fmt(V('ratio.mental_resp'), 1)} veces",
                     "prov": "C", "lines": [f"{pc(vid('diagnostico', MENTAL, 'pct_rech'))} frente a {pc(vid('diagnostico', RESP, 'pct_rech'))}"],
                     "refs": ["ratio.mental_resp", vid("diagnostico", MENTAL, "pct_rech"), vid("diagnostico", RESP, "pct_rech")]})

    # Headline from the configured priority.
    lead = None
    for cand in cfg.get("headline_priority") or []:
        if cand == "salud_mental_vs_respiratorias" and has_mr:
            lead = (f"Las Isapres rechazan el {pc(vid('diagnostico', MENTAL, 'pct_rech'))} de las licencias de salud mental y el "
                    f"{pc(vid('diagnostico', RESP, 'pct_rech'))} de las respiratorias en {ql}")
        elif cand == "rechazo_por_isapre" and len(big) >= 2:
            lead = (f"El rechazo de licencias va de {pc(vid('isapre', big[-1], 'pct_rech'))} en {names[big[-1]]} a "
                    f"{pc(vid('isapre', big[0], 'pct_rech'))} en {names[big[0]]} en {ql}")
        if lead and len(lead) <= 140:
            break
        lead = None
    headline = lead or f"Licencias médicas en Isapres, {ql}"
    dek = (f"De {fmt(V(f'{T}.licencias'), 0)} licencias, las Isapres rechazaron el {pc(f'{T}.pct_rech')} y redujeron el "
           f"{pc(f'{T}.pct_red')}; autorizaron el {pc(f'{T}.dias_ratio')} de los días pedidos.")

    notes = [
        {"id": "n1", "text": f"Base trimestral: licencias del archivo de {ql}; cada cifra es un flujo del trimestre, no un stock, y los "
                             "trimestres no se suman." + (f" La comparación con el {so.quarter_tag(pq)} no está ajustada por estacionalidad "
                                                           "(invierno)." if pq else "")},
        {"id": "n2", "text": "Denominador: los % de rechazo y de reducción dividen por las licencias del archivo; días autorizados / días "
                             "solicitados divide por los días pedidos; el subsidio por licencia divide el subsidio líquido por todas las "
                             "licencias, y «con pago» solo por las que tienen subsidio mayor que cero."},
        {"id": "n3", "text": "Fechas: la SIS publica la recepción y la resolución solo como trimestre (p. ej. 2.º trimestre), por eso no se "
                             "calculan días hasta la resolución; se informa el % resuelto en el mismo trimestre de recepción."},
        {"id": "n4", "text": "Privacidad: solo agregados por Isapre, grupo de diagnóstico, actividad laboral, región y tipo de profesional, "
                             "con un mínimo de 10 licencias por celda. Nunca hay desglose por médico, trabajador ni empleador, y los RUT "
                             "cifrados de la SIS no se intentan revertir."},
        {"id": "n5", "text": "El diagnóstico es el capítulo CIE-10 del diagnóstico principal. Las diferencias entre Isapres no ajustan por "
                             "mezcla de diagnósticos, tipo de trabajador ni licencias de continuación."},
        {"id": "n6", "text": "Subsidio líquido según el archivo: cuando paga el empleador (p. ej. sector público), el monto viene en cero."},
        {"id": "n7", "text": "Archivo: ZIP trimestral de datos abiertos de la SIS. Su huella SHA-256 está en Fuentes; cada agregado nombra "
                             "esa misma huella y, si no calza, la ficha queda retenida."},
    ]
    nq = so.next_quarter(q)
    late = (decision or {}).get("late_release")
    watch = [{"headline": f"Datos de {so.quarter_label(nq)}.",
              "explanation": "La SIS publica un ZIP de licencias por trimestre; Alicanto lo agrega cuando aparece en datos abiertos."}]
    if late:
        watch = [{"headline": f"Datos de {so.quarter_label(nq)}: sin archivo nuevo.",
                  "explanation": f"Lleva {late['days_late']} días más allá del intervalo esperado."}]
    triggers = (decision or {}).get("triggers") or []
    rule = "nuevo período" if "new_period" in triggers else ("revisión" if "revision" in triggers else "publicación vigente")
    machine = (f"Ficha generada por la regla \"{rule}\" (agregados calculados por Alicanto el {sf.day_label(package['published_at'])}). "
               "Las cifras vienen del paquete de evidencia, sin descargas en este paso; la Lectura Alicanto está desactivada.")
    prim = package["primary_source"]["url"]
    sources = sorted(({**s, "key": key} for key, s in package["sources"].items()), key=lambda x: (x.get("url") != prim, x["key"]))
    return {
        "schema_version": sf.SCHEMA, "id": f"stats-ficha:{FAMILY}:{package['period']}", "family": FAMILY,
        "family_label": cfg["label"], "slug": cfg["slug"], "period": package["period"], "published_at": package["published_at"],
        "release_key": package["release_key"], "evidence_sha256": package["evidence_sha256"],
        "kicker": tpl["kicker"].format(label=cfg["label"], quarter_label=ql),
        "kicker_meta": tpl["kicker_meta"].format(quarter_label=ql, published_label=sf.day_label(package["published_at"])),
        "date_basis": "first_detected", "headline": headline, "headline_type": "default", "dek": dek, "dek_emphasis": None,
        "kpis": kpis[:5], "tabs": tabs,
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs, "rendered_in_tabs": True},
        "watch": watch[:2], "notes": notes, "sources": sources, "machine_note": machine,
        "featured": bool((decision or {}).get("featured")), "triggers": triggers, "late_release": late,
        "revisions": package.get("revisions") or [],
    }


def run(root: Path, *, today: date, registry: dict | None = None, llm: bool = True,
        model_call: Callable[..., Any] | None = None, budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    """The Lectura stays off for F13 (no paid call) until Dirección sets ``families.F13.lectura_enabled``."""
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    llm = llm and cfg.get("lectura_enabled") is True
    out = sf.run_family(FAMILY, builder_version=BUILDER_VERSION, build_package=build_package, compose=compose, root=Path(root),
                        today=today, registry=registry, llm=llm, model_call=model_call, budget=budget)
    return so.first_review_gate(out, cfg, Path(root), FAMILY, "f13_")
