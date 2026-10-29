"""F1 · Cartera y movilidad: evidence package, KPIs and ficha (no model numbers).

Inputs already captured and reconciled by the data lanes:
- ``data/market/isapre_portfolio.json``: cartera mensual por Isapre (10 códigos, release rodante con hash);
- ``data/excel/validated_series.json``: movilidad de cotizantes y suscripciones/desahucios (totales).

Rules from the registry (config/stats_fichas_v1.json, F1):
- each month is a stock: values are never summed across months;
- market share uses only the 7 open Isapres as denominator;
- the year-on-year comparison stays 'pendiente' until monthly 2025 data is captured.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import stats_fichas as sf
from .stats_fichas import fmt_dec, fmt_int, fmt_signed, month_label, month_name, value

FAMILY = "F1"
BUILDER_VERSION = "f1_index_topic_v8"  # a new builder republishes the same release (no archive, no new paid Lectura)
METRIC_COL = {"cotizantes": "C", "cargas": "D", "beneficiarios": "E"}


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _names(root: Path) -> dict[int, str]:
    data = _load(root / "data/entities/isapres.json") or {}
    return {int(e["official_code"]): e.get("commercial_name") or e.get("legal_name") for e in data.get("entities", [])}


def _contiguous(periods: list[str]) -> bool:
    keys = [sf.period_parts(p) for p in periods]
    idx = [y * 12 + m for y, m in keys]
    return all(b - a == 1 for a, b in zip(idx, idx[1:]))


def _regional_release(root: Path, period: str) -> dict | None:
    history = _load(root / "data/history/superintendencia_signals.json") or {}
    best = None
    for sig in history.get("signals") or []:
        title = str(sig.get("title") or "").lower()
        if "cartera" not in title or "regional" not in title or str(sig.get("source_name")) != "Superintendencia de Salud":
            continue
        if month_label(period) not in title:
            continue
        docs = [d.get("url") for d in sig.get("source_documents") or [] if str(d.get("url") or "").startswith("https://")]
        best = {"title": sig.get("title"), "url": sig.get("source_url"), "event_date": sig.get("event_date"), "documents": docs[:2]}
    return best


# ---------------------------------------------------------------------------------------------
# Evidence package


def build_package(root: Path, registry: dict | None = None, previous_live: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    portfolio = _load(root / "data/market/isapre_portfolio.json")
    if not portfolio:
        raise ValueError("portfolio_missing")
    validated = _load(root / "data/excel/validated_series.json") or {"families": {}}
    names = _names(root)
    open_codes, closed_codes = set(cfg["open_codes"]), set(cfg["closed_codes"])
    failures: list[str] = []

    obs = [o for o in portfolio.get("observations", []) if o.get("metric_id") in METRIC_COL]
    shas = {o.get("source_sha256") for o in obs}
    urls = {o.get("source_url") for o in obs}
    if len(shas) != 1 or len(urls) != 1:
        failures.append("mixed_release")
    sha = next(iter(shas)) if shas else ""
    url = next(iter(urls)) if urls else ""
    fetched = max((o.get("fetched_at") or "") for o in obs) if obs else None
    published = portfolio.get("published_at")
    periods = sorted({o["period"] for o in obs})
    if not periods:
        raise ValueError("portfolio_empty")
    if not _contiguous(periods):
        failures.append("non_contiguous_months")
    if portfolio.get("reporting_period") != periods[-1]:
        failures.append("reporting_period_mismatch")

    grid: dict[tuple[str, int], dict] = defaultdict(dict)
    for o in obs:
        grid[(o["period"], int(o["official_code"]))][o["metric_id"]] = o
    declared = {c["period"]: c.get("total_beneficiaries") for c in portfolio.get("coverage", [])}

    values: dict[str, dict] = {}
    primary = "cartera"
    sources = {primary: sf.source_ref(url=url, sha256=sha, published_at=published, fetched_at=fetched,
                                      label="SIS · Estadística mensual de cartera de beneficiarios 2026 (xlsx)",
                                      role=f"beneficiarios, cotizantes y cargas por Isapre, {month_name(periods[0])}–{month_name(periods[-1])}",
                                      locator=f"{grid[(periods[0], 67)].get('beneficiarios', {}).get('sheet', 'Enero')}…"
                                              f"{grid[(periods[-1], 67)].get('beneficiarios', {}).get('sheet', '')}!C8:E19 · fila Total Sistema")}
    totals: dict[str, dict[str, int]] = {}
    for p in periods:
        codes = {c for (pp, c) in grid if pp == p}
        if codes != open_codes | closed_codes:
            failures.append(f"codes_{p}")
        tot = {m: 0 for m in METRIC_COL}
        for c in sorted(codes):
            cell = grid[(p, c)]
            if set(cell) != set(METRIC_COL):
                failures.append(f"metrics_{p}_{c}")
                continue
            for m, o in cell.items():
                v = o["value"]
                if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                    failures.append(f"count_{p}_{c}_{m}")
                    continue
                tot[m] += v
                values[f"cartera.{c}.{m}.{p}"] = value(f"cartera.{c}.{m}.{p}", v, unit="personas", period=p, source=primary,
                                                       locator=f"{o.get('sheet')}!{METRIC_COL[m]}{o.get('source_row')}")
            if all(m in cell for m in METRIC_COL) and cell["cotizantes"]["value"] + cell["cargas"]["value"] != cell["beneficiarios"]["value"]:
                failures.append(f"cot_plus_cargas_{p}_{c}")
        dec = declared.get(p)
        if not isinstance(dec, int) or dec != tot["beneficiarios"]:
            failures.append(f"total_{p}")
        else:
            values[f"cartera.declarado.beneficiarios.{p}"] = value(
                f"cartera.declarado.beneficiarios.{p}", dec, unit="personas", period=p, source=primary,
                locator=f"{grid[(p, 67)]['beneficiarios'].get('sheet')}!E · Total Sistema")
        totals[p] = tot
        for m in METRIC_COL:
            values[f"sistema.{m}.{p}"] = value(f"sistema.{m}.{p}", tot[m], unit="personas", period=p, source=primary,
                                               formula=f"Σ {m} de los 10 códigos", kind="derived",
                                               inputs=[f"cartera.{c}.{m}.{p}" for c in sorted(codes)])
        values[f"abiertas.beneficiarios.{p}"] = value(
            f"abiertas.beneficiarios.{p}", sum(grid[(p, c)]["beneficiarios"]["value"] for c in open_codes if (p, c) in grid),
            unit="personas", period=p, source=primary, formula="Σ beneficiarios de las 7 Isapres abiertas", kind="derived",
            inputs=[f"cartera.{c}.beneficiarios.{p}" for c in sorted(open_codes)])

    t, base = periods[-1], periods[0]
    prev = periods[-2] if len(periods) > 1 else None
    missing_names = sorted(c for c in open_codes | closed_codes if not names.get(c))
    if missing_names:  # never show a code or a placeholder in place of a captured name
        raise ValueError(f"entity_name_missing:{missing_names}")
    entities = [{"code": c, "name": names[c], "group": "abiertas" if c in open_codes else "cerradas"}
                for c in sorted(open_codes | closed_codes)]

    def derived(vid, val, formula, inputs, unit="personas", period=t):
        values[vid] = value(vid, val, unit=unit, period=period, source=primary, formula=formula, inputs=inputs, kind="derived")
        return val

    package: dict[str, Any] = {
        "family": FAMILY, "period": t, "base_period": base, "previous_period": prev, "periods": periods,
        "published_at": published, "release_key": sf.release_key(t, sha or "0" * 16),
        "primary_source": {"url": url, "sha256": sha}, "sources": sources, "values": values,
        "entities": entities, "entity_codes": [e["code"] for e in entities], "causal_note": None, "provisional": True,
        "reconciliation": {"ok": not failures, "failures": failures,
                           "checks": ["10 códigos oficiales por mes", "cotizantes + cargas = beneficiarios por Isapre",
                                      "Σ beneficiarios por Isapre = Total Sistema declarado", "meses contiguos",
                                      "período informado = último mes del archivo", "un solo hash por release"]},
    }
    if failures:
        package.update(findings=[], kpis={}, revisions=[], constants=[])
        return package

    # Beneficiarios: monthly change series (stocks; never summed).
    B = {p: totals[p]["beneficiarios"] for p in periods}
    C = {p: totals[p]["cotizantes"] for p in periods}
    K = {p: totals[p]["cargas"] for p in periods}
    mm = {}
    for a, b in zip(periods, periods[1:]):
        mm[b] = derived(f"sistema.beneficiarios.mm.{b}", B[b] - B[a], "stock(t) − stock(t−1)",
                        [f"sistema.beneficiarios.{b}", f"sistema.beneficiarios.{a}"], period=b)
    cmm = {}
    for a, b in zip(periods, periods[1:]):
        cmm[b] = derived(f"sistema.cotizantes.mm.{b}", C[b] - C[a], "stock(t) − stock(t−1)",
                         [f"sistema.cotizantes.{b}", f"sistema.cotizantes.{a}"], period=b)
    ytd = derived("sistema.beneficiarios.ytd", B[t] - B[base], f"stock({t}) − stock({base})",
                  [f"sistema.beneficiarios.{t}", f"sistema.beneficiarios.{base}"])
    ytd_pct = derived("sistema.beneficiarios.ytd_pct", (B[t] - B[base]) / B[base] * 100, "Δ / stock base × 100",
                      ["sistema.beneficiarios.ytd", f"sistema.beneficiarios.{base}"], unit="%")
    mm_t = mm.get(t)
    mm_pct = derived("sistema.beneficiarios.mm_pct", mm_t / B[prev] * 100, "Δ m/m / stock(t−1) × 100",
                     [f"sistema.beneficiarios.mm.{t}", f"sistema.beneficiarios.{prev}"], unit="%") if prev else None
    cot_ytd = derived("sistema.cotizantes.ytd", C[t] - C[base], f"stock({t}) − stock({base})", [f"sistema.cotizantes.{t}", f"sistema.cotizantes.{base}"])
    cargas_ytd = derived("sistema.cargas.ytd", K[t] - K[base], f"stock({t}) − stock({base})", [f"sistema.cargas.{t}", f"sistema.cargas.{base}"])
    # Topic KPI cards (Dirección 29-oct): cotizantes and cargas since the base month, with their own % change.
    derived("sistema.cotizantes.ytd_pct", cot_ytd / C[base] * 100, "Δ / stock base × 100", ["sistema.cotizantes.ytd", f"sistema.cotizantes.{base}"], unit="%")
    derived("sistema.cargas.ytd_pct", cargas_ytd / K[base] * 100, "Δ / stock base × 100", ["sistema.cargas.ytd", f"sistema.cargas.{base}"], unit="%")
    for p in periods:
        derived(f"mezcla.{p}", K[p] / C[p], "cargas / cotizantes", [f"sistema.cargas.{p}", f"sistema.cotizantes.{p}"], unit="ratio", period=p)
    mix_t = derived(f"mezcla.{t}", K[t] / C[t], "cargas / cotizantes", [f"sistema.cargas.{t}", f"sistema.cotizantes.{t}"], unit="ratio")
    mix_b = derived(f"mezcla.{base}", K[base] / C[base], "cargas / cotizantes", [f"sistema.cargas.{base}", f"sistema.cotizantes.{base}"], unit="ratio", period=base)
    mix_d = derived("mezcla.delta", mix_t - mix_b, "mezcla(t) − mezcla(base)", [f"mezcla.{t}", f"mezcla.{base}"], unit="ratio")
    # Rounded display values are also evidence: 0,603 − 0,615 = −0,012 must trace as shown.
    derived("mezcla.delta_shown", round(mix_t, 3) - round(mix_b, 3), "redondeo(mezcla t, 3) − redondeo(mezcla base, 3)", ["mezcla.delta"], unit="ratio")

    kp = cfg["kpis"]
    th_b, th_mix, th_share, th_con = kp["beneficiarios"]["threshold"], kp["mezcla"]["threshold"], kp["participacion"]["threshold"], kp["contribucion"]["threshold"]
    findings: list[dict] = []
    # Beneficiary events.
    months = [p for p in periods[1:]]
    declines = {p: -mm[p] for p in months if mm[p] < 0}
    if mm_pct is not None and abs(mm_pct) >= th_b["mm_pct"]:
        findings.append({"type": "threshold_crossed", "kpi": "beneficiarios", "crossed": True, "strength": abs(mm_pct) / th_b["mm_pct"]})
    streak_neg = 0
    for p in reversed(months[:-1]):
        if mm[p] < 0:
            streak_neg += 1
        else:
            break
    if mm_t is not None and mm_t > 0 and streak_neg >= 1:
        findings.append({"type": "sign_change", "kpi": "beneficiarios", "crossed": False, "strength": 1.0, "streak": streak_neg})
    peak_month = max(declines, key=declines.get) if declines else None
    if mm_t is not None and mm_t < 0 and len(declines) >= 3:
        if declines[t] == min(declines.values()):
            mild = declines[t] <= 0.25 * declines[peak_month]
            findings.append({"type": "record_low_decline" if mild else "record_low_decline_moderate", "kpi": "beneficiarios",
                             "crossed": False, "strength": 1.0})
        elif declines[t] == max(declines.values()):
            findings.append({"type": "record_high_decline", "kpi": "beneficiarios", "crossed": False, "strength": 1.0})
    shrinking = bool(peak_month) and all(mm[b] > mm[a] for a, b in zip(months, months[1:]) if a >= peak_month) and peak_month != t
    # Cotizantes: sign change sustained N months.
    need = int(kp["cotizantes"]["threshold"]["sign_change_sustained_months"])
    cot_series = [cmm[p] for p in months]
    cot_streak = 0
    for v in reversed(cot_series):
        if v > 0 if cot_series[-1] > 0 else v < 0:
            cot_streak += 1
        else:
            break
    cot_sustained = len(cot_series) > cot_streak >= need and cot_series[-1] != 0
    if cot_sustained:
        findings.append({"type": "sustained_sign_change", "kpi": "cotizantes", "crossed": True, "strength": cot_streak / need,
                         "streak": cot_streak, "direction": "up" if cot_series[-1] > 0 else "down"})
    # Portfolio mix.
    if abs(mix_d) >= th_mix["abs_delta"]:
        findings.append({"type": "threshold_crossed", "kpi": "mezcla", "crossed": True, "strength": abs(mix_d) / th_mix["abs_delta"]})
    # Shares (open only) and per-entity deltas.
    den_t, den_b = values[f"abiertas.beneficiarios.{t}"]["value"], values[f"abiertas.beneficiarios.{base}"]["value"]
    deltas = {}
    for c in sorted(open_codes | closed_codes):
        b0, b1 = grid[(base, c)]["beneficiarios"]["value"], grid[(t, c)]["beneficiarios"]["value"]
        deltas[c] = derived(f"delta.{c}.ytd", b1 - b0, f"stock({t}) − stock({base})", [f"cartera.{c}.beneficiarios.{t}", f"cartera.{c}.beneficiarios.{base}"])
        derived(f"delta.{c}.ytd_pct", (b1 - b0) / b0 * 100, "Δ / stock base × 100", [f"delta.{c}.ytd", f"cartera.{c}.beneficiarios.{base}"], unit="%")
        # The by-Isapre table splits each change into cotizantes and cargas (Dirección 29-oct); both parts must add
        # up to the beneficiary change, from the same captured cells.
        parts = {m: derived(f"delta.{c}.{m}.ytd", grid[(t, c)][m]["value"] - grid[(base, c)][m]["value"], f"stock({t}) − stock({base})",
                            [f"cartera.{c}.{m}.{t}", f"cartera.{c}.{m}.{base}"]) for m in ("cotizantes", "cargas")}
        if parts["cotizantes"] + parts["cargas"] != b1 - b0:
            raise ValueError(f"cot_plus_cargas_delta_{c}")
        if c in open_codes:
            s0 = derived(f"share.{c}.{base}", b0 / den_b * 100, "benef_i / Σ abiertas × 100", [f"cartera.{c}.beneficiarios.{base}", f"abiertas.beneficiarios.{base}"], unit="%", period=base)
            s1 = derived(f"share.{c}.{t}", b1 / den_t * 100, "benef_i / Σ abiertas × 100", [f"cartera.{c}.beneficiarios.{t}", f"abiertas.beneficiarios.{t}"], unit="%")
            d = derived(f"share.{c}.delta_pp", s1 - s0, "share(t) − share(base)", [f"share.{c}.{t}", f"share.{c}.{base}"], unit="pp")
            if abs(d) >= th_share["pp"] and abs(b1 - b0) >= th_share["min_persons"]:
                findings.append({"type": "threshold_crossed", "kpi": "participacion", "entity": c, "crossed": True, "strength": abs(d) / th_share["pp"]})
    closed_b0 = sum(grid[(base, c)]["beneficiarios"]["value"] for c in closed_codes)
    derived(f"cerradas.beneficiarios.{base}", closed_b0, "Σ beneficiarios de las 3 cerradas", [f"cartera.{c}.beneficiarios.{base}" for c in sorted(closed_codes)], period=base)
    derived("delta.cerradas.ytd", sum(deltas[c] for c in closed_codes), "Σ Δ de las 3 cerradas", [f"delta.{c}.ytd" for c in sorted(closed_codes)])
    for m in ("cotizantes", "cargas"):
        derived(f"delta.cerradas.{m}.ytd", sum(values[f"delta.{c}.{m}.ytd"]["value"] for c in closed_codes), f"Σ Δ {m} de las 3 cerradas",
                [f"delta.{c}.{m}.ytd" for c in sorted(closed_codes)])
    if values["delta.cerradas.cotizantes.ytd"]["value"] + values["delta.cerradas.cargas.ytd"]["value"] != values["delta.cerradas.ytd"]["value"]:
        raise ValueError("cot_plus_cargas_delta_cerradas")
    if cot_ytd + cargas_ytd != ytd:
        raise ValueError("cot_plus_cargas_delta_sistema")
    derived("delta.cerradas.ytd_pct", sum(deltas[c] for c in closed_codes) / closed_b0 * 100, "Δ / stock base × 100", ["delta.cerradas.ytd", f"cerradas.beneficiarios.{base}"], unit="%")
    # Contribution to the net change (not computed when |Δ system| < min_system_delta).
    contributions = {}
    if abs(ytd) >= th_con["min_system_delta"]:
        for c in sorted(open_codes):
            contributions[c] = derived(f"contrib.{c}", deltas[c] / ytd * 100, "Δbenef_i / Δbenef_sistema × 100", [f"delta.{c}.ytd", "sistema.beneficiarios.ytd"], unit="%")
        top = max(contributions, key=contributions.get)
        if contributions[top] >= th_con["share_pct"]:
            findings.append({"type": "concentration", "kpi": "contribucion", "entity": top, "crossed": True,
                             "strength": contributions[top] / th_con["share_pct"]})
        derived("cargas.contrib", cargas_ytd / ytd * 100, "Δ cargas / Δ beneficiarios × 100", ["sistema.cargas.ytd", "sistema.beneficiarios.ytd"], unit="%")

    # Mobility and subscriptions: their own period (between cuts / latest validated month).
    fams = validated.get("families") or {}
    mob = fams.get("movilidad") or {}
    if mob.get("status") == "validated" and mob.get("series"):
        m = mob["series"][-1]
        sources["movilidad"] = sf.source_ref(url=mob["source_url"], sha256=mob["sha256"], published_at=None, fetched_at=validated.get("validated_at"),
                                             label="SIS · Movilidad de cotizantes, corte " + month_label(m["period_end"]) + " (xlsx)",
                                             role="entradas y salidas del sistema entre cortes", locator="Nacional!D19, D31, D43")
        for key, loc in (("salidas_intervalo", "Nacional!D19"), ("entradas_intervalo", "Nacional!D31"), ("diferencia_intervalo", "Nacional!D43")):
            values[f"movilidad.{key}"] = value(f"movilidad.{key}", m["metrics"][key], unit="cotizantes", period=f"{m['period_start']}→{m['period_end']}",
                                               source="movilidad", locator=loc)
        package["movilidad"] = {"period_start": m["period_start"], "period_end": m["period_end"]}
    sub = fams.get("suscripciones") or {}
    if sub.get("status") == "validated" and sub.get("series"):
        s = sub["series"][-1]
        sources["suscripciones"] = sf.source_ref(url=sub["source_url"], sha256=sub["sha256"], published_at=None, fetched_at=validated.get("validated_at"),
                                                 label="SIS · Suscripciones y desahucios 2026 (xlsx)", role="contratos suscritos y desahucios voluntarios",
                                                 locator=f"{s['sheet']}!C:D · fila Total Sistema")
        for key in ("contratos_suscritos", "desahucios_voluntarios"):
            values[f"suscripciones.{key}.{s['period']}"] = value(f"suscripciones.{key}.{s['period']}", s["metrics"][key], unit="contratos",
                                                                 period=s["period"], source="suscripciones", locator=f"{s['sheet']}!Total Sistema")
        package["suscripciones"] = {"period": s["period"]}

    # Regional cartera: release captured as metadata only (numbers not extracted yet). The ficha absorbs
    # its card as the 'Regional' tab instead of a separate minimal card.
    package["regional"] = _regional_release(root, t)

    # Revisions against the previous live ficha, or else against the earlier validated release.
    previous_evidence = (previous_live or {}).get("evidence")
    if not previous_evidence:
        car = fams.get("cartera") or {}
        if car.get("status") == "validated" and car.get("sha256") != sha:
            previous_evidence = {"values": {f"cartera.declarado.beneficiarios.{r['period']}": value(
                f"cartera.declarado.beneficiarios.{r['period']}", r["metrics"]["beneficiarios"], unit="personas", period=r["period"],
                source=car.get("sha256")) for r in car.get("series", [])}}
    revisions = sf.detect_revisions(package, previous_evidence)

    constants = [th_b["mm_pct"], th_b["yoy_pct"], th_mix["abs_delta"], th_share["pp"], th_share["min_persons"], th_con["share_pct"],
                 th_con["min_system_delta"], kp["movilidad"]["threshold"]["rate_change_pp"], len(open_codes), len(closed_codes),
                 len(open_codes | closed_codes), 12, cot_streak, streak_neg, need, len(months)]
    _lectura_material(package, values, t=t, base=base, prev=prev, open_codes=open_codes, closed_codes=closed_codes,
                      deltas=deltas, contributions=contributions, declines=declines, peak_month=peak_month,
                      cot_streak=cot_streak)
    package.update(findings=findings, revisions=revisions, constants=constants,
                   kpis={"mm": mm, "cmm": cmm, "declines": declines, "peak_month": peak_month, "shrinking": shrinking,
                         "cot_streak": cot_streak, "cot_sustained": cot_sustained, "streak_neg": streak_neg,
                         "contributions": contributions, "deltas": deltas, "B": B, "C": C, "K": K,
                         "mix": {"t": mix_t, "base": mix_b, "delta": mix_d}})
    return package


def _lectura_material(package: dict, values: dict, *, t, base, prev, open_codes, closed_codes, deltas, contributions,
                      declines, peak_month, cot_streak) -> None:
    """What the Lectura may cite (Dirección 28-oct 15:25: figures allowed if they add something).

    ``lectura_pool``: package values with unit, sign rule, entity and period. ``derived_ratios``: multiples, fractions
    and counts precomputed here (the only values a number word may express). ``ranks``: ordinal positions.
    """
    P = lambda vid, **kw: sf.pool_entry(values, vid, **kw) if vid in values else None  # noqa: E731
    ytd = [base, t]
    # scope: who a figure may be credited to (system / open / closed / insurer:<code>, the default with an entity).
    # period_kind: month (one month's change), ytd (since the base month), interval (between cuts), stock_at.
    Y = {"periods": ytd, "period_kind": "ytd"}
    pool = [P(f"sistema.beneficiarios.{t}", metric="beneficiarios", signed=False, scope="system"),
            P("sistema.beneficiarios.ytd", metric="beneficiarios", scope="system", **Y),
            P("sistema.beneficiarios.ytd_pct", scope="system", base="stock_base", **Y),
            P(f"sistema.cotizantes.{t}", metric="cotizantes", signed=False, scope="system"),
            P("sistema.cotizantes.ytd", metric="cotizantes", scope="system", **Y),
            P("sistema.cargas.ytd", metric="cargas", scope="system", **Y),
            P(f"sistema.cargas.{t}", metric="cargas", signed=False, scope="system"),
            P(f"mezcla.{t}", signed=False, scope="system", base="cotizantes"),
            P(f"mezcla.{base}", signed=False, requires_period=True, scope="system", base="cotizantes"),
            P("mezcla.delta_shown", scope="system", base="cotizantes", **Y),
            P(f"abiertas.beneficiarios.{t}", metric="beneficiarios", signed=False, scope="open"),
            P("delta.cerradas.ytd", metric="beneficiarios", scope="closed", **Y),
            P("delta.cerradas.ytd_pct", scope="closed", base="stock_base", **Y),
            P("cargas.contrib", scope="system", base="variacion_sistema", **Y)]
    if prev:
        M = {"periods": [prev, t], "period_kind": "month", "scope": "system"}
        pool += [P(f"sistema.beneficiarios.mm.{t}", metric="beneficiarios", **M),
                 P("sistema.beneficiarios.mm_pct", base="stock_mes_anterior", **M),
                 P(f"sistema.cotizantes.mm.{t}", metric="cotizantes", **M)]
    for c in sorted(open_codes | closed_codes):
        pool += [P(f"delta.{c}.ytd", entity=c, metric="beneficiarios", **Y), P(f"delta.{c}.ytd_pct", entity=c, base="stock_base", **Y),
                 P(f"cartera.{c}.beneficiarios.{t}", entity=c, metric="beneficiarios", signed=False)]
        if c in open_codes:
            # Shares are among the OPEN Isapres only (benef_i / Σ abiertas): never 'del mercado' or 'del sistema'.
            pool += [P(f"share.{c}.{t}", entity=c, signed=False, base="abiertas"),
                     P(f"share.{c}.{base}", entity=c, signed=False, requires_period=True, base="abiertas"),
                     P(f"share.{c}.delta_pp", entity=c, base="abiertas", **Y),
                     P(f"contrib.{c}", entity=c, base="variacion_sistema", **Y)]
    for key, signed in (("entradas_intervalo", False), ("salidas_intervalo", False), ("diferencia_intervalo", True)):
        pool.append(P(f"movilidad.{key}", metric="cotizantes", signed=signed, scope="system", period_kind="interval"))
    sub = (package.get("suscripciones") or {}).get("period")
    if sub:
        pool += [P(f"suscripciones.contratos_suscritos.{sub}", metric="contratos", signed=False, scope="system", period_kind="month"),
                 P(f"suscripciones.desahucios_voluntarios.{sub}", metric="desahucios", signed=False, scope="system", period_kind="month")]
    package["lectura_pool"] = [e for e in pool if e]

    ratios: list[dict] = []

    def ratio(rid, num, den, unit, formula, inputs, entity=None, periods=None, scope=None, period_kind="ytd", base=None):
        if den:
            ratios.append({"id": rid, "value": num / den, "unit": unit, "entity": entity, "signed": False,
                           "periods": periods or [t], "requires_period": False, "formula": formula, "inputs": inputs,
                           "scope": scope or (f"insurer:{entity}" if entity is not None else "system"),
                           "period_kind": period_kind, "trivial": False, "base": base})

    v = lambda vid: values[vid]["value"] if vid in values else None  # noqa: E731
    if v("movilidad.salidas_intervalo") and v("movilidad.entradas_intervalo"):
        ratio("ratio.salidas_por_entrada", v("movilidad.salidas_intervalo"), v("movilidad.entradas_intervalo"), "x",
              "salidas / entradas", ["movilidad.salidas_intervalo", "movilidad.entradas_intervalo"],
              periods=values["movilidad.salidas_intervalo"]["period"].split("→"), period_kind="interval")
    if sub:
        ratio("ratio.suscritos_por_desahucio", v(f"suscripciones.contratos_suscritos.{sub}"), v(f"suscripciones.desahucios_voluntarios.{sub}"),
              "x", "suscritos / desahucios", [f"suscripciones.contratos_suscritos.{sub}", f"suscripciones.desahucios_voluntarios.{sub}"], periods=[sub],
              period_kind="month")
    if peak_month and declines.get(t):
        ratio("ratio.baja_maxima_vs_actual", declines[peak_month], declines[t], "x", "baja(mes pico) / baja(t)",
              [f"sistema.beneficiarios.mm.{peak_month}", f"sistema.beneficiarios.mm.{t}"], periods=[peak_month, t],
              period_kind="interval")
    losers = sorted((c for c in open_codes if deltas[c] < 0), key=lambda c: deltas[c])
    gainers = sorted((c for c in open_codes if deltas[c] > 0), key=lambda c: -deltas[c])
    if losers and gainers:
        ratio("ratio.mayor_baja_vs_alzas", -deltas[losers[0]], sum(deltas[c] for c in gainers), "x",
              "|Δ mayor baja| / Σ Δ de las abiertas que crecen", [f"delta.{c}.ytd" for c in [losers[0], *gainers]],
              entity=losers[0], periods=[base, t])
    if len(losers) > 1:
        ratio("ratio.mayor_baja_vs_segunda", deltas[losers[0]], deltas[losers[1]], "x", "Δ mayor baja / Δ segunda baja",
              [f"delta.{losers[0]}.ytd", f"delta.{losers[1]}.ytd"], entity=losers[0], periods=[base, t])
    if len(gainers) > 1:
        ratio("ratio.mayor_alza_vs_segunda", deltas[gainers[0]], deltas[gainers[1]], "x", "Δ mayor alza / Δ segunda alza",
              [f"delta.{gainers[0]}.ytd", f"delta.{gainers[1]}.ytd"], entity=gainers[0], periods=[base, t])
    if contributions:
        top = max(contributions, key=contributions.get)
        ratio("fraccion.contribucion_mayor", contributions[top], 100, "share", "contrib / 100", [f"contrib.{top}"],
              entity=top, periods=[base, t], base="variacion_sistema")
    if "cargas.contrib" in values:
        ratio("fraccion.cargas_en_la_baja", values["cargas.contrib"]["value"], 100, "share", "Δ cargas / Δ beneficiarios",
              ["cargas.contrib"], periods=[base, t], base="variacion_sistema")
    # Entity counts are trivial: they never count as new information (Dirección 28-oct: aportar algo más).
    for rid, n, inputs, scope in (("conteo.abiertas", len(open_codes), [], "open"), ("conteo.cerradas", len(closed_codes), [], "closed"),
                                  ("conteo.abiertas_crecen", len(gainers), [f"delta.{c}.ytd" for c in sorted(open_codes)], "open"),
                                  ("conteo.abiertas_caen", len(losers), [f"delta.{c}.ytd" for c in sorted(open_codes)], "open")):
        ratios.append({"id": rid, "value": n, "unit": "count", "entity": None, "signed": False, "periods": [base, t],
                       "requires_period": False, "formula": "conteo", "inputs": inputs, "scope": scope,
                       "period_kind": "ytd", "trivial": True})
    package["derived_ratios"] = ratios

    ranks: list[dict] = []
    size = sorted(open_codes, key=lambda c: -values[f"cartera.{c}.beneficiarios.{t}"]["value"])
    for i, c in enumerate(size, 1):
        ranks.append({"id": f"rank.tamano.{c}", "value": i, "unit": "rank", "entity": c, "signed": False, "periods": [t],
                      "requires_period": False, "formula": "orden por beneficiarios (abiertas)", "ranking": "tamano",
                      "scope": f"insurer:{c}", "period_kind": "stock_at"})
    for i, c in enumerate(losers, 1):
        ranks.append({"id": f"rank.baja.{c}", "value": i, "unit": "rank", "entity": c, "signed": False, "periods": [base, t],
                      "requires_period": False, "formula": "orden por Δ beneficiarios negativo (abiertas)", "ranking": "baja",
                      "scope": f"insurer:{c}", "period_kind": "ytd"})
    for i, c in enumerate(gainers, 1):
        ranks.append({"id": f"rank.alza.{c}", "value": i, "unit": "rank", "entity": c, "signed": False, "periods": [base, t],
                      "requires_period": False, "formula": "orden por Δ beneficiarios positivo (abiertas)", "ranking": "alza",
                      "scope": f"insurer:{c}", "period_kind": "ytd"})
    if cot_streak:
        ranks.append({"id": "rank.racha_cotizantes", "value": cot_streak, "unit": "rank", "entity": None, "signed": False,
                      "periods": [t], "requires_period": False, "formula": "meses consecutivos con el mismo signo",
                      "ranking": "racha", "scope": "system", "period_kind": "month"})
    package["ranks"] = ranks


# ---------------------------------------------------------------------------------------------
# Ficha composition (templates from the registry)


def _pick_headline(findings: list[dict], priority: list[str]) -> dict:
    order = {k: i for i, k in enumerate(priority)}
    order.setdefault("record_low_decline_moderate", order.get("record_low_decline", 1) + 0.5)
    ranked = sorted(findings, key=lambda f: (order.get(f["type"], 99), -float(f.get("strength") or 0)))
    return ranked[0] if ranked else {"type": "no_change"}


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    kp = cfg["kpis"]
    v = package["values"]
    k = package["kpis"]
    t, base, prev = package["period"], package["base_period"], package["previous_period"]
    names = {e["code"]: e["name"] for e in package["entities"]}
    mm_t, ytd, ytd_pct = k["mm"][t], v["sistema.beneficiarios.ytd"]["value"], v["sistema.beneficiarios.ytd_pct"]["value"]
    mm_pct = v["sistema.beneficiarios.mm_pct"]["value"]
    month, base_month, prev_month = month_name(t), month_name(base), month_name(prev)
    conc = next((f for f in package["findings"] if f["type"] == "concentration"), None)
    cot_up = k["cot_sustained"] and k["cmm"][t] > 0

    # Headline
    pick = _pick_headline(package["findings"], cfg["headline_priority"])
    htype = pick["type"]
    head_tpl = tpl["headline"].get(htype) or tpl["headline"]["no_change"]
    kpi_label = kp.get(pick.get("kpi") or "", {}).get("label", "")
    headline = head_tpl.format(month=month, delta_abs=fmt_int(abs(mm_t)), delta_signed=fmt_signed(mm_t), streak=pick.get("streak", ""),
                               entity=names.get(pick.get("entity"), ""), share=fmt_dec(k["contributions"].get(pick.get("entity"), 0), 0),
                               year=sf.period_parts(t)[0], streak_word=sf.ordinal(k["cot_streak"]), kpi_label=kpi_label.lower())
    headline = headline[0].upper() + headline[1:]

    # Dek (≤ 40 words)
    cot_clause = f" Los cotizantes {'subieron' if cot_up else 'cayeron'} por {sf.ordinal(k['cot_streak'])} mes consecutivo" if k["cot_sustained"] else ""
    conc_clause = ""
    if conc:
        word = "baja" if ytd < 0 else "alza"
        piece = f"{names[conc['entity']]} concentra el {fmt_dec(k['contributions'][conc['entity']], 0)}% de la {word} neta."
        conc_clause = (", y " + piece) if cot_clause else (" " + piece)
    if cot_clause and not conc_clause:
        cot_clause += "."
    dek = tpl["dek"].format(month=month, benef=fmt_int(k["B"][t]), delta_ytd_abs=fmt_int(abs(ytd)),
                            more_less="menos" if ytd < 0 else "más", base_month=base_month,
                            cot_clause=cot_clause, concentration_clause=conc_clause)
    dek_emphasis = tpl["dek_emphasis"].format(benef=fmt_int(k["B"][t]))

    # KPI strip
    th_b = kp["beneficiarios"]["threshold"]
    b_crossed = abs(mm_pct) >= th_b["mm_pct"]
    kpis = [{
        "id": "beneficiarios", "label": "Beneficiarios", "value": fmt_int(k["B"][t]), "prov": "C",
        "lines": [f"{fmt_signed(mm_t)} vs. {prev_month} ({fmt_dec(mm_pct, 2, signed=True)}%)",
                  f"{fmt_signed(ytd)} desde {base_month} ({fmt_dec(ytd_pct, 2, signed=True)}%)"],
        "badge": "Cruza umbral (0,25% m/m)" if b_crossed else "Sin umbral cruzado · a/a pendiente",
        "badge_kind": "crossed" if b_crossed else "muted",
        "refs": [f"sistema.beneficiarios.{t}", f"sistema.beneficiarios.mm.{t}", "sistema.beneficiarios.ytd"]}]
    cmm = k["cmm"]
    cot_lines = [f"{fmt_signed(cmm[t])} vs. {prev_month}"]
    if k["cot_sustained"]:
        prior = list(cmm)[-2]
        cot_lines.append(f"{sf.ordinal(k['cot_streak']).capitalize()} mes {'al alza' if cot_up else 'a la baja'} ({month_name(prior)[:3]} {fmt_signed(cmm[prior])})")
    kpis.append({"id": "cotizantes", "label": "Cotizantes", "value": fmt_int(k["C"][t]), "prov": "C", "lines": cot_lines,
                 "badge": "Cambio de signo sostenido" if k["cot_sustained"] else "Sin cambio de signo",
                 "badge_kind": "crossed" if k["cot_sustained"] else "muted", "refs": [f"sistema.cotizantes.{t}", f"sistema.cotizantes.mm.{t}"]})
    mix = k["mix"]
    mix_crossed = abs(mix["delta"]) >= kp["mezcla"]["threshold"]["abs_delta"]
    mix_lines = [f"{base_month}: {fmt_dec(mix['base'], 3)} ({fmt_dec(v['mezcla.delta_shown']['value'], 3, signed=True)})"]
    if "cargas.contrib" in v:
        mix_lines.append(f"Las cargas son el {fmt_dec(v['cargas.contrib']['value'], 0)}% de la {'baja' if ytd < 0 else 'variación'}")
    kpis.append({"id": "mezcla", "label": "Cargas por cotizante", "value": fmt_dec(mix["t"], 3), "prov": "C", "lines": mix_lines,
                 "badge": "Cruza umbral (0,005)" if mix_crossed else "Sin umbral cruzado", "badge_kind": "crossed" if mix_crossed else "muted",
                 "refs": [f"mezcla.{t}", f"mezcla.{base}", "mezcla.delta"]})
    if "movilidad.diferencia_intervalo" in v:
        mob = package["movilidad"]
        stale = mob["period_end"] < t
        kpis.append({"id": "movilidad", "label": "Movilidad neta 12 m", "value": fmt_int(v["movilidad.diferencia_intervalo"]["value"]), "prov": "C",
                     "lines": [f"cotizantes, cortes {month_label(mob['period_start'])} → {month_label(mob['period_end'])}",
                               f"entradas {fmt_int(v['movilidad.entradas_intervalo']['value'])} · salidas {fmt_int(v['movilidad.salidas_intervalo']['value'])}"],
                     "badge": f"Corte de {month} aún no leído" if stale else "Tasa pendiente (sin cotizantes del corte inicial)",
                     "badge_kind": "muted", "refs": ["movilidad.diferencia_intervalo", "movilidad.entradas_intervalo", "movilidad.salidas_intervalo"]})

    # Charts
    months = [p for p in package["periods"][1:]]
    peak = k["peak_month"]
    c1_head = (f"La baja mensual se achica desde {month_name(peak)}" if k["shrinking"] and all(k["mm"][p] < 0 for p in months)
               else "Cambio mensual de beneficiarios")
    chart1 = {"id": "f1-mm", "form": "columns_signed", "headline": c1_head,
              "subtitle": "Cambio mensual de beneficiarios del sistema Isapre (personas)", "unit": "personas",
              "rows": [{"label": sf.month_short(p), "period": p, "value": k["mm"][p], "ref": f"sistema.beneficiarios.mm.{p}", "emphasis": p == t}
                       for p in months],
              "table": {"columns": ["Mes", "Cambio", "Stock final"],
                        "rows": [[sf.month_short(base), "—", fmt_int(k["B"][base])]] +
                                [[sf.month_short(p), fmt_signed(k["mm"][p]), fmt_int(k["B"][p])] for p in months]},
              "source": "SIS, estadística mensual de cartera (datos provisionales). La diferencia mensual la calcula Alicanto."}
    rows2 = [{"label": names[c], "value": k["deltas"][c], "ref": f"delta.{c}.ytd", "base": v[f"cartera.{c}.beneficiarios.{base}"]["value"],
              "pct_ref": f"delta.{c}.ytd_pct", "cot_ref": f"delta.{c}.cotizantes.ytd", "car_ref": f"delta.{c}.cargas.ytd"}
             for c in package["entity_codes"] if c in set(cfg["open_codes"])]
    rows2.append({"label": f"Cerradas ({len(cfg['closed_codes'])})", "value": v["delta.cerradas.ytd"]["value"], "ref": "delta.cerradas.ytd",
                  "base": v[f"cerradas.beneficiarios.{base}"]["value"], "pct_ref": "delta.cerradas.ytd_pct",
                  "cot_ref": "delta.cerradas.cotizantes.ytd", "car_ref": "delta.cerradas.cargas.ytd"})
    for r in rows2:  # Cotizantes + Cargas = Cambio on every row of the table (Dirección 29-oct)
        if v[r["cot_ref"]]["value"] + v[r["car_ref"]]["value"] != r["value"]:
            raise ValueError(f"table_cot_plus_cargas:{r['label']}")
    rows2.sort(key=lambda r: r["value"])
    # The count comes from the data (conteo.abiertas_crecen: every open Isapre with Δ > 0), never from a template.
    n_up = next(int(r["value"]) for r in package["derived_ratios"] if r["id"] == "conteo.abiertas_crecen")
    c2_head = (f"Una Isapre concentra la {'baja' if ytd < 0 else 'variación'}" + (f"; {sf.count_phrase(n_up, 'crece', 'crecen')}" if n_up else "")
               if conc else "Cambio de beneficiarios por Isapre")
    chart2 = {"id": "f1-isapres", "form": "diverging", "headline": c2_head,
              "subtitle": f"Cambio de beneficiarios entre {base_month} y {month}, por Isapre", "unit": "personas",
              "rows": [{**r, "emphasis": r["value"] > 0} for r in rows2],
              "table": {"columns": ["Isapre", "Cambio", "Cotizantes", "Cargas", f"% vs. {base_month}"],
                        "rows": [[r["label"], fmt_signed(r["value"]), fmt_signed(v[r["cot_ref"]]["value"]), fmt_signed(v[r["car_ref"]]["value"]),
                                  fmt_dec(v[r["pct_ref"]]["value"], 2, signed=True) + "%"] for r in rows2]
                                + [["Sistema", fmt_signed(ytd), fmt_signed(v["sistema.cotizantes.ytd"]["value"]), fmt_signed(v["sistema.cargas.ytd"]["value"]),
                                    fmt_dec(ytd_pct, 2, signed=True) + "%"]]},
              "source": "SIS, cartera por Isapre. Las cerradas (Isalud, Fundación, Cruz del Norte) van agrupadas."}

    # Qué muestran los datos (3 sentences)
    ftpl = tpl["facts"]
    peak_clause = ""
    if peak and k["shrinking"]:
        peak_clause = f" La pérdida mensual tocó su máximo en {month_name(peak)} ({fmt_int(k['mm'][peak])}) y desde entonces se redujo en cada mes, hasta {fmt_int(mm_t)} en {month}."
    elif peak:
        peak_clause = f" La mayor pérdida mensual fue en {month_name(peak)} ({fmt_int(k['mm'][peak])})."
    p1 = ftpl["magnitude"].format(base_month=base_month, month=month, ytd_verb="bajó" if ytd < 0 else "subió",
                                  delta_ytd_abs=fmt_int(abs(ytd)), delta_ytd_pct=fmt_dec(ytd_pct, 2, signed=True) + "%", peak_clause=peak_clause)
    paragraphs = [p1]
    if "cargas.contrib" in v:
        paragraphs.append(ftpl["composition"].format(cargas_share=fmt_dec(v["cargas.contrib"]["value"], 0), cargas_delta=fmt_signed(v["sistema.cargas.ytd"]["value"]),
                                                     cot_verb="cayeron" if v["sistema.cotizantes.ytd"]["value"] < 0 else "subieron",
                                                     cot_delta_abs=fmt_int(abs(v["sistema.cotizantes.ytd"]["value"])), month=month,
                                                     cot_mm=fmt_signed(cmm[t]), prev_month=prev_month))
    top = conc["entity"] if conc else min(k["deltas"], key=lambda c: k["deltas"][c] if c in set(cfg["open_codes"]) else 10**12)
    gain_names = [r for r in rows2 if r["value"] >= kp["participacion"]["threshold"]["min_persons"]]
    gainers_clause = ""
    if gain_names:
        listed = " y ".join(f"{r['label']} ({fmt_signed(r['value'])})" for r in reversed(gain_names))
        gainers_clause = f" {listed} {'crecieron' if len(gain_names) > 1 else 'creció'}."
    paragraphs.append(ftpl["entities"].format(top_entity=names[top], top_delta=fmt_signed(k["deltas"][top]), base_month=base_month,
                                              top_share_from=fmt_dec(v[f"share.{top}.{base}"]["value"], 1), top_share_to=fmt_dec(v[f"share.{top}.{t}"]["value"], 1),
                                              gainers_clause=gainers_clause))

    # Tabs (Dirección 28-oct 04:59): each theme gets its own charts, table and a short reading of the data.
    periods_all = package["periods"]
    chart_stock = {"id": "f1-stock", "form": "line", "headline": f"Beneficiarios Isapre, {base_month} a {month}",
                   "subtitle": "Personas al cierre de cada mes", "unit": "personas", "digits": 0,
                   "rows": [{"label": sf.month_short(p), "period": p, "value": k["B"][p], "ref": f"sistema.beneficiarios.{p}", "emphasis": p == t} for p in periods_all],
                   "table": {"columns": ["Mes", "Beneficiarios", "Cotizantes", "Cargas"],
                             "rows": [[sf.month_short(p), fmt_int(k["B"][p]), fmt_int(k["C"][p]), fmt_int(k["K"][p])] for p in periods_all]},
                   "source": "SIS, estadística mensual de cartera."}
    open_rows = sorted(cfg["open_codes"], key=lambda c: -v[f"share.{c}.{t}"]["value"])
    chart_share = {"id": "f1-share", "form": "dots", "headline": "Participación entre las Isapres abiertas",
                   "subtitle": f"% de beneficiarios de las 7 abiertas · punto = {month}, aro = {base_month}", "unit": "%", "digits": 1,
                   "rows": [{"label": names[c], "value": v[f"share.{c}.{t}"]["value"], "ref": f"share.{c}.{t}",
                             "base": v[f"share.{c}.{base}"]["value"], "base_ref": f"share.{c}.{base}"} for c in open_rows],
                   "table": {"columns": ["Isapre", base_month.capitalize(), month.capitalize(), "Δ pp", "Aporte al cambio neto"],
                             "rows": [[names[c], fmt_dec(v[f"share.{c}.{base}"]["value"], 1) + "%", fmt_dec(v[f"share.{c}.{t}"]["value"], 1) + "%",
                                       fmt_dec(v[f"share.{c}.delta_pp"]["value"], 2, signed=True),
                                       (fmt_dec(k["contributions"][c], 0) + "%") if c in k["contributions"] else "no calculado"] for c in open_rows]},
                   "source": "Denominador: solo las 7 Isapres abiertas. El aporte al cambio neto no se calcula si el sistema varía menos de 5.000 personas."}
    chart_cot = {"id": "f1-cot", "form": "columns_signed", "headline": "Cotizantes: cambio mensual",
                 "subtitle": "Personas que cotizan", "unit": "personas",
                 "rows": [{"label": sf.month_short(p), "period": p, "value": cmm[p], "ref": f"sistema.cotizantes.mm.{p}", "emphasis": p == t} for p in months],
                 "table": {"columns": ["Mes", "Cambio", "Cotizantes"], "rows": [[sf.month_short(p), fmt_signed(cmm[p]), fmt_int(k["C"][p])] for p in months]},
                 "source": "SIS, estadística mensual de cartera."}
    chart_mix = {"id": "f1-mix", "form": "line", "headline": "Cargas por cotizante", "subtitle": "Razón cargas / cotizantes del mismo mes",
                 "unit": "razón", "digits": 3,
                 "rows": [{"label": sf.month_short(p), "period": p, "value": v[f"mezcla.{p}"]["value"], "ref": f"mezcla.{p}", "emphasis": p == t} for p in periods_all],
                 "table": {"columns": ["Mes", "Cargas por cotizante"], "rows": [[sf.month_short(p), fmt_dec(v[f"mezcla.{p}"]["value"], 3)] for p in periods_all]},
                 "source": "Denominador: cotizantes del mismo mes."}
    # Index → topic layout (Dirección 29-oct, option C→B). Each topic carries its index line and sparkline; a topic
    # dek or KPI card appears only when it adds something its charts do not show (dek None = no text in topic mode).
    year = sf.period_parts(t)[0]
    whole_year = base == f"{year}-01"
    span = "del año" if whole_year else f"desde {base_month}"
    record_low = htype in {"record_low_decline", "record_low_decline_moderate"} or (
        mm_t < 0 and len(k["declines"]) >= 3 and k["declines"][t] == min(k["declines"].values()))
    total_line = f"{fmt_int(k['B'][t])} beneficiarios · " + (f"menor baja {span}" if record_low and whole_year else f"{fmt_signed(mm_t)} en {month}")
    # Each topic line cites the evidence ids of its figures (verify_ficha traces them unit- and entity-aware).
    total_refs = [f"sistema.beneficiarios.{t}"] + ([] if record_low and whole_year else [f"sistema.beneficiarios.mm.{t}"])
    isapres_refs = ([f"contrib.{conc['entity']}"] + (["conteo.abiertas_crecen"] if n_up else [])) if conc else []
    if conc:
        isapres_line = (f"{names[conc['entity']]}: {fmt_dec(k['contributions'][conc['entity']], 0)}% de la {'baja' if ytd < 0 else 'variación'}"
                        + (f" · {n_up} {'Isapre crece' if n_up == 1 else 'Isapres crecen'}" if n_up else ""))
    else:
        isapres_line = f"Cambio por Isapre desde {base_month}"
    mezcla_line = (f"Cotizantes {'suben' if cot_up else 'bajan'} por {sf.ordinal(k['cot_streak'])} mes" if k["cot_sustained"]
                   else f"Cotizantes {fmt_signed(v['sistema.cotizantes.ytd']['value'])} desde {base_month}")
    mezcla_refs = [] if k["cot_sustained"] else ["sistema.cotizantes.ytd"]
    mezcla_dek, mezcla_kpis = None, []
    contrib_cargas = v.get("cargas.contrib", {}).get("value")
    if contrib_cargas is not None and 0 < contrib_cargas <= 100 and ytd < 0:
        mezcla_dek = f"Las cargas explican el {fmt_dec(contrib_cargas, 0)}% de la baja {span}."
    for metric, label in (("cotizantes", "Cotizantes"), ("cargas", "Cargas")):
        d, pct = v[f"sistema.{metric}.ytd"]["value"], v[f"sistema.{metric}.ytd_pct"]["value"]
        mezcla_kpis.append({"id": f"tema-{metric}", "label": label, "value": fmt_int(v[f"sistema.{metric}.{t}"]["value"]), "prov": "C",
                            "lines": [f"{fmt_signed(d)} desde {base_month} ({fmt_dec(pct, 2, signed=True)}%)"],
                            "refs": [f"sistema.{metric}.{t}", f"sistema.{metric}.ytd", f"sistema.{metric}.ytd_pct"]})
    tabs = [
        {"id": "total", "label": "Cartera total", "charts": [chart_stock, chart1], "text": [],
         "index_line": total_line, "index_refs": total_refs, "spark": {"chart": "f1-stock", "form": "line"}, "dek": None, "kpis": []},
        {"id": "isapres", "label": "Por Isapre", "charts": [chart2, chart_share], "text": [],
         "index_line": isapres_line, "index_refs": isapres_refs, "spark": {"chart": "f1-isapres", "form": "diverging"}, "dek": None, "kpis": []},
        {"id": "mezcla", "label": "Cotizantes y cargas", "charts": [chart_cot, chart_mix], "text": [],
         "index_line": mezcla_line, "index_refs": mezcla_refs, "spark": {"chart": "f1-cot", "form": "columns"}, "dek": mezcla_dek,
         "dek_refs": ["cargas.contrib"] if mezcla_dek else [], "kpis": mezcla_kpis},
    ]
    if "movilidad.diferencia_intervalo" in v or package.get("suscripciones"):
        mov_charts = []
        if "movilidad.diferencia_intervalo" in v:
            mob = package["movilidad"]
            mov_charts.append({"id": "f1-mob", "form": "diverging", "headline": "Entradas y salidas del sistema entre cortes",
                               "subtitle": f"Cotizantes, {month_label(mob['period_start'])} → {month_label(mob['period_end'])}", "unit": "cotizantes",
                               "rows": [{"label": "Entradas", "value": v["movilidad.entradas_intervalo"]["value"], "ref": "movilidad.entradas_intervalo", "emphasis": True},
                                        {"label": "Salidas", "value": -v["movilidad.salidas_intervalo"]["value"], "ref": "movilidad.salidas_intervalo", "sign": -1},
                                        {"label": "Neto", "value": v["movilidad.diferencia_intervalo"]["value"], "ref": "movilidad.diferencia_intervalo"}],
                               "table": {"columns": ["Concepto", "Cotizantes"], "rows": [["Entradas", fmt_int(v["movilidad.entradas_intervalo"]["value"])],
                                                                                          ["Salidas", fmt_int(v["movilidad.salidas_intervalo"]["value"])],
                                                                                          ["Neto", fmt_signed(v["movilidad.diferencia_intervalo"]["value"])]]},
                               "source": "SIS, movilidad de cotizantes (hoja Nacional). Comparación entre dos cortes."})
        if package.get("suscripciones"):
            sp = package["suscripciones"]["period"]
            con, des = v[f"suscripciones.contratos_suscritos.{sp}"]["value"], v[f"suscripciones.desahucios_voluntarios.{sp}"]["value"]
            mov_charts.append({"id": "f1-sub", "form": "bars", "headline": "Contratos suscritos y desahucios voluntarios",
                               "subtitle": f"Contratos en {month_label(sp)}", "unit": "contratos",
                               "rows": [{"label": "Suscritos", "value": con, "ref": f"suscripciones.contratos_suscritos.{sp}", "emphasis": True},
                                        {"label": "Desahucios vol.", "value": des, "ref": f"suscripciones.desahucios_voluntarios.{sp}"}],
                               "table": {"columns": ["Concepto", "Contratos"], "rows": [["Contratos suscritos", fmt_int(con)], ["Desahucios voluntarios", fmt_int(des)]]},
                               "source": "SIS, suscripciones y desahucios. Los desahucios voluntarios no son todas las terminaciones."})
        if "movilidad.diferencia_intervalo" in v:
            mob = package["movilidad"]
            out_more = v["movilidad.salidas_intervalo"]["value"] > v["movilidad.entradas_intervalo"]["value"]
            mov_line = ("Salen más de los que entran" if out_more else "Entran más de los que salen") + (
                f" · dato a {month_name(mob['period_end'])}" if mob["period_end"] < t else "")
        else:
            mov_line = "Contratos suscritos y desahucios voluntarios"
        tabs.append({"id": "movilidad", "label": "Movilidad y desahucios", "charts": mov_charts, "text": [],
                     "index_line": mov_line, "index_refs": [], "spark": {"chart": mov_charts[0]["id"], "form": "diverging" if mov_charts[0]["form"] == "diverging" else "bars"},
                     "dek": None, "kpis": []})
    reg = package.get("regional")
    tabs.append({"id": "regional", "label": "Regional", "charts": [], "status": "pendiente", "spark": None,
                 "index_line": ("Enlace a la SIS · cifras aún no extraídas" if reg else "Cifras aún no extraídas"), "index_refs": [],
                 "text": ["Alicanto aún no extrae las cifras regionales: la publicación queda enlazada y su ficha suelta se absorbe aquí."],
                 "links": ([{"label": reg["title"], "url": reg["url"]}] + [{"label": "Planilla regional (xlsx)", "url": u} for u in reg["documents"]]) if reg else []})

    # Qué mirar
    published = date.fromisoformat(package["published_at"][:10])
    expected = published.toordinal() + int(cfg["calendar"]["expected_release_interval_days"])
    expected_day = date.fromordinal(expected)
    watch = []
    late = (decision or {}).get("late_release")
    nxt = sf.shift_period(t, 1)
    if late:
        watch.append({"headline": f"Cartera a {month_label(nxt)}: publicación atrasada.",
                      "explanation": f"Según el calendario histórico debía publicarse hacia el {sf.day_label(late['expected_on'])}; lleva {late['days_late']} días de atraso."})
    else:
        watch.append({"headline": f"Cartera a {month_label(nxt)} (la SIS la publicaría hacia el {sf.day_label(expected_day)}).",
                      "explanation": f"Si la variación mensual supera 0,25% del stock o los cotizantes cambian de signo, la ficha pasa a destacada."})
    share_to = v[f"share.{top}.{t}"]["value"]
    watch.append({"headline": f"Participación de {names[top]} entre las abiertas ({fmt_dec(share_to, 1)}% en {month}).",
                  "explanation": "Una variación de 0,30 pp o más, con 5.000 personas o más, frente al inicio del año marca un cruce de umbral en esta ficha."})
    watch = watch[:2]  # Dirección 28-oct 08:20: a compact 'Qué mirar'

    # Notas sobre la evidencia (fixed pitfalls + dynamic)
    notes = [
        {"id": "n1", "text": f"Son stocks al cierre de mes y no se suman. Los datos de la SIS son provisionales. La comparación contra {month} del año anterior queda pendiente: Alicanto no tiene capturada la serie mensual del año anterior."},
        {"id": "n2", "text": f"La participación usa como denominador solo las 7 Isapres abiertas ({fmt_int(v[f'abiertas.beneficiarios.{t}']['value'])} en {month}). Las cerradas (Isalud, Fundación, Cruz del Norte) atienden poblaciones cautivas y no compiten. 'Banmédica' es la Isapre, no el grupo controlador."},
    ]
    if "movilidad.diferencia_intervalo" in v:
        notes.append({"id": "n3", "text": "La movilidad compara dos cortes; no equivale a la suma de los movimientos intermedios ni a suscripciones menos desahucios, que incluyen cambios entre Isapres."})
    # Moved from the topic text (Dirección 29-oct: topic text only where it adds to the chart): a method caveat.
    notes.append({"id": "n3b", "text": "Una razón de cargas por cotizante menor no implica menos ingreso: la cotización la paga el cotizante."})
    if record_low and whole_year:
        notes.append({"id": "n4", "text": f"'Menor baja del año' compara los cambios mensuales de {month_name(package['periods'][1])} a {month}; "
                                          f"el de {base_month} no se calcula porque la serie capturada parte en {base_month}."})
    notes.append({"id": "n5", "text": "Ningún dato de esta ficha establece por qué cambia la cartera (precio, ley corta o calidad de servicio)."})
    for i, r in enumerate(sorted(package.get("revisions") or [], key=lambda x: -abs(x["pct"]))[:4], 6):
        parts = r["id"].split(".")
        who = "Total Sistema" if parts[1] == "declarado" else names.get(int(parts[1]), parts[1])
        notes.append({"id": f"n{i}", "text": f"Revisado ({who}, {parts[2]}, {month_label(r['period'])}): {fmt_int(r['from'])} → {fmt_int(r['to'])}."})

    sources = []
    for key, src in package["sources"].items():
        sources.append({**src, "key": key})

    triggers = (decision or {}).get("triggers") or []
    rule = "nuevo período" if "new_period" in triggers else ("revisión" if "revision" in triggers else "publicación vigente")
    machine = (f"Ficha generada por la regla \"{rule}\" (release del {sf.day_label(package['published_at'])}). Las cifras las calcula el código"
               f" desde el paquete de evidencia; solo la Lectura Alicanto puede escribirla un modelo, y pasa por un verificador.")

    period_label = month_label(t)
    return {
        "schema_version": sf.SCHEMA, "id": f"stats-ficha:{FAMILY}:{t}", "family": FAMILY, "family_label": cfg["label"],
        "slug": cfg["slug"], "period": t, "published_at": package["published_at"], "release_key": package["release_key"],
        "kicker": tpl["kicker"].format(label=cfg["label"]),
        "kicker_meta": tpl["kicker_meta"].format(period_label=period_label, published_label=sf.day_label(package["published_at"]), cadence_phrase=cfg["cadence_phrase"]),
        "headline": headline, "headline_type": htype, "dek": dek, "dek_emphasis": dek_emphasis,
        "kpis": kpis, "tabs": tabs,
        # 'Qué muestran los datos' is folded into the tabs (Dirección 28-oct 08:20); kept as data only, for the
        # verifier and the Lectura prompt, and never rendered as its own section.
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs, "rendered_in_tabs": True},
        "watch": watch, "notes": notes, "sources": sources, "machine_note": machine,
        "featured": bool((decision or {}).get("featured")), "triggers": triggers, "late_release": late,
        "revisions": package.get("revisions") or [],
    }


# ---------------------------------------------------------------------------------------------
# Run


def run(root: Path, *, today: date, registry: dict | None = None, llm: bool = True,
        model_call: Callable[..., Any] | None = None, budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    previous = sf.load_live(root, cfg["slug"])
    generated = sf.now_iso()
    base = {"family": FAMILY, "slug": cfg["slug"], "generated_at": generated}
    try:
        package = build_package(root, registry, previous)
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        return {**base, "status": "hold", "period": None, "errors": [f"package_error:{type(exc).__name__}:{exc}"[:200]]}
    decision = sf.evaluate_triggers(package, previous, today=today, calendar=cfg["calendar"])
    base.update(period=package["period"], decision=decision)
    if decision["decision"] == "HOLD":
        return {**base, "status": "hold", "errors": decision["holds"], "candidate": {"reconciliation": package.get("reconciliation")}}
    if decision["decision"] == "NO_CHANGE" and previous and previous.get("builder_version") != BUILDER_VERSION:
        decision = {**decision, "decision": "PUBLISH", "triggers": list(dict.fromkeys([*(previous.get("triggers") or []), "format_update"]))}
        base["decision"] = decision
    retry_lectura = (decision["decision"] == "NO_CHANGE" and previous
                     and (previous.get("lectura") or {}).get("status") in {"not_attempted", "no_budget"} and llm)
    if decision["decision"] == "NO_CHANGE" and not retry_lectura:
        return {**base, "status": "no_change"}
    if decision.get("late_release"):
        package["constants"].append(decision["late_release"]["days_late"])  # shown in 'Qué mirar'
    ficha = compose(package, registry, today=today, decision=decision)
    verification = sf.verify_ficha(ficha, package)
    if verification["verdict"] != "PASS":
        return {**base, "status": "hold", "verification": verification, "errors": verification["errors"], "candidate": ficha}
    reuse = previous and previous.get("release_key") == package["release_key"] and (previous.get("lectura") or {}).get("status") == "pass"
    if reuse:
        lect = previous["lectura"]
    elif previous and previous.get("release_key") == package["release_key"] and (previous.get("lectura") or {}).get("status") not in {"not_attempted", "no_budget", None}:
        lect = previous["lectura"]  # a paid attempt for this release is never repeated automatically
    else:
        lect = sf.generate_lectura(ficha, package, registry=registry, enabled=llm, model_call=model_call, budget=budget)
    ficha["lectura"] = lect
    if lect.get("status") == "pass":
        # Re-run the whole deterministic verification with the Lectura attached (repeated sentences, audience,
        # numbers): a Lectura that breaks it is dropped and the code-written ficha still publishes.
        # A reused Lectura (same release, already paid) is re-checked with the current verifier too.
        again = sf.verify_lectura(lect.get("text"), package, registry=registry, ficha=ficha)
        with_lectura = sf.verify_ficha(ficha, package)
        if with_lectura["verdict"] != "PASS" or again["verdict"] != "PASS":
            lect = {**lect, "status": "verifier_fail", "rejected_text": lect.get("text"), "text": None,
                    "verification": {**(lect.get("verification") or {}), "verdict": "FAIL", "errors": again["errors"],
                                     "ficha_errors": with_lectura["errors"]}}
            ficha["lectura"] = lect
        else:
            # Second-model backstop after the deterministic gates (≤ 1 reviewer call per ficha).
            lect = sf.with_review(lect, ficha, package, registry=registry, enabled=llm, model_call=model_call, budget=budget)
            ficha["lectura"] = lect
    if lect.get("status") == "pass":
        ficha["machine_note"] += f" Costo de IA: USD {lect.get('cost_usd', 0):.4f}."
    else:
        ficha["machine_note"] += " Lectura Alicanto omitida (" + {"not_attempted": "sin modelo en esta corrida", "no_budget": "sin presupuesto",
                                                                  "verifier_fail": "no pasó el verificador", "generation_error": "error del modelo",
                                                                  "review_fail": "no pasó la revisión de un segundo modelo",
                                                                  "review_no_budget": "sin presupuesto para la revisión",
                                                                  "review_error": "error del revisor",
                                                                  "review_not_run": "sin revisión de un segundo modelo"}.get(lect.get("status"), "no disponible") + ")."
    if retry_lectura:
        ficha["triggers"] = previous.get("triggers") or ficha["triggers"]
        ficha["featured"] = previous.get("featured", ficha["featured"])
    ficha.update(status="PASS", generated_at=generated, builder_version=BUILDER_VERSION, verification=verification,
                 reconciliation=package["reconciliation"], evidence={k: package.get(k) for k in ("values", "constants", "entity_codes", "release_key", "period", "lectura_pool", "derived_ratios", "ranks")})
    return {**base, "status": "pass", "ficha": ficha}
