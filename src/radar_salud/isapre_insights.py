"""Deterministic insights from the reconciled, official Isapre workbook series."""
from __future__ import annotations

from statistics import median
from urllib.parse import urlparse
import re


PERIODS = [f"2026-{month:02d}" for month in range(1, 8)]
METRICS = {
    "cartera": ("cotizantes", "cargas", "beneficiarios"),
    "suscripciones": ("contratos_suscritos", "desahucios_voluntarios"),
}


def _count(value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("Non-reconciled count")
    return value


def _family(families, name):
    item = families[name]
    schema = "national_comparison_totals_v2" if name == "movilidad" else "monthly_isapre_totals_v2"
    source = urlparse(item["source_url"])
    if (item["status"] != "validated" or item["schema"] != schema
            or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
            or source.scheme != "https" or source.netloc != "www.superdesalud.gob.cl"
            or not source.path.endswith(".xlsx")):
        raise ValueError("Unvalidated workbook evidence")
    series = item["series"]
    if name == "movilidad":
        if len(series) != 1 or series[0]["period_type"] != "comparison_between_july_cuts" or series[0]["period_start"] != "2025-07" or series[0]["period_end"] != PERIODS[-1]:
            raise ValueError("Incomparable mobility interval")
        measures = series[0]["metrics"]
        if _count(measures["entradas_intervalo"]) - _count(measures["salidas_intervalo"]) != measures["diferencia_intervalo"]:
            raise ValueError("Mobility totals do not reconcile")
    else:
        if len(series) != len(PERIODS) or [row["period"] for row in series] != PERIODS:
            raise ValueError("Missing or incomparable months")
        for row in series:
            if not isinstance(row["isapres"], int) or row["isapres"] < 7:
                raise ValueError("Insufficient Isapre rows")
            for metric in METRICS[name]:
                _count(row["metrics"][metric])
            if name == "cartera" and row["metrics"]["cotizantes"] + row["metrics"]["cargas"] != row["metrics"]["beneficiarios"]:
                raise ValueError("Beneficiaries do not reconcile")
    return item


def _label(value):
    return f"{value:,}".replace(",", ".")


def _record(text, formula, family, period, sheet):
    return {"text": text, "formula": formula, "family": family["family"], "period": period,
            "sheet": sheet["sheet"], "source_url": family["source_url"],
            "sha256": family["sha256"]}


def _anomaly_check(values):
    """Flag only large robust deviations of monthly changes; zero MAD fails closed."""
    changes = [b - a for a, b in zip(values, values[1:])]
    center = median(changes)
    mad = median(abs(value - center) for value in changes)
    flagged = [] if mad == 0 else [PERIODS[i + 1] for i, value in enumerate(changes)
                                  if abs(value - center) * 0.6745 / mad > 3.5]
    return {"status": "no_baseline_variance" if mad == 0 else "evaluated",
            "formula": "abs(delta - median(delta)) * 0.6745 / MAD(delta) > 3.5",
            "observations": len(changes), "flagged_periods": flagged}


def derive(validation):
    """Return no findings if any of the three family schemas or intervals fail."""
    try:
        families = validation["families"]
        car, sub, mob = (_family(families, name) for name in ("cartera", "suscripciones", "movilidad"))
        c, s = car["series"], sub["series"]
        if c[-1]["period"] != s[-1]["period"] or len({row["isapres"] for row in c + s}) != 1:
            raise ValueError("Incomparable Isapre population")
        records = []
        for family, series, metric, label in (
            (car, c, "beneficiarios", "beneficiarios"),
            (sub, s, "contratos_suscritos", "contratos suscritos"),
            (sub, s, "desahucios_voluntarios", "desahucios voluntarios"),
        ):
            previous, current = (row["metrics"][metric] for row in series[-2:])
            if previous == 0:
                raise ValueError("Missing comparison denominator")
            difference = current - previous
            pct = difference / previous * 100
            records.append(_record(
                f"{label.capitalize()}: {_label(previous)} en junio y {_label(current)} en julio de 2026; variación {difference:+,} ({pct:+.2f}%).".replace(",", "."),
                f"({current} - {previous}) / {previous} * 100 = {pct:+.4f}%",
                family, "2026-06 → 2026-07", series[-1]))
        first, last = c[0]["metrics"]["beneficiarios"], c[-1]["metrics"]["beneficiarios"]
        records.append(_record(
            f"La cartera registra {_label(last - first)} beneficiarios entre enero y julio de 2026 (diferencia de stock, no suma mensual).",
            f"{last} - {first} = {last - first}", car, "2026-01 → 2026-07", c[-1]))
        for metric, label in (("contratos_suscritos", "contratos suscritos"), ("desahucios_voluntarios", "desahucios voluntarios")):
            values = [row["metrics"][metric] for row in s]
            total = sum(values)
            records.append(_record(
                f"Enero–julio 2026: {_label(total)} {label} acumulados como eventos mensuales; no equivalen a cambio neto de cartera.",
                " + ".join(map(str, values)) + f" = {total}", sub, "2026-01 → 2026-07", s[-1]))
        values = [row["metrics"]["beneficiarios"] for row in c]
        streak = 0
        for previous, current in reversed(list(zip(values, values[1:]))):
            if current < previous:
                streak += 1
            else:
                break
        if streak >= 2:
            records.append(_record(
                f"La cartera de beneficiarios cae en {streak} comparaciones mensuales consecutivas hasta julio de 2026; no se infiere causa.",
                " and ".join(f"{a}>{b}" for a, b in list(zip(values, values[1:]))[-streak:]),
                car, f"{PERIODS[-streak-1]} → 2026-07", c[-1]))
        movement = mob["series"][0]["metrics"]
        records.append(_record(
            f"Movilidad entre cortes julio 2025 y julio 2026: {_label(movement['entradas_intervalo'])} entradas y {_label(movement['salidas_intervalo'])} salidas; diferencia {_label(movement['diferencia_intervalo'])}. No es variación mensual.",
            f"{movement['entradas_intervalo']} - {movement['salidas_intervalo']} = {movement['diferencia_intervalo']}",
            mob, "2025-07 → 2026-07", mob["series"][0]))
        checks = {metric: _anomaly_check([row["metrics"][metric] for row in series])
                  for series, metric in ((c, "beneficiarios"), (s, "contratos_suscritos"), (s, "desahucios_voluntarios"))}
        return {"status": "validated", "period": PERIODS[-1], "insights": records, "anomaly_checks": checks,
                "sources": {name: {"url": item["source_url"], "sha256": item["sha256"]} for name, item in families.items()}}
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        return {"status": "schema_or_denominator_not_validated", "insights": [], "anomaly_checks": {}}
