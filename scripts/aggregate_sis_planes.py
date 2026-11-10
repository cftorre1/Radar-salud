"""Aggregates of SIS open data on health plans (Planes de Salud, Cobertura Planes) for ficha F9 (Benchmark de planes).

Runs in GitHub Actions (the sandbox cannot reach datos.superdesalud.gob.cl). It reuses the network logic of
``scripts/aggregate_sis_open_data.py`` (probe User-Agent, robots.txt fail-closed, 1 GiB cap per file, ZIP streamed to
the runner's temp dir and deleted after parsing) and writes ONLY aggregate JSON plus receipts (URL, bytes, SHA-256,
rows). Plan identifiers, plan names and plan lines are used only in memory (join of Cobertura with Planes) and are
never written; the column profile keeps only their lengths.

Months (all from the links of the SIS open-data page; nothing is guessed): the newest month ``t`` of Planes de Salud,
the month before (``t-1``) and the same month a year earlier (``t-12``); Cobertura Planes for ``t`` and ``t-12`` (or,
when the page has no Cobertura for a month, nothing for it). Tabla Factores is not read: the SIS stopped it in
Aug-2024 (Ley 21.674, single table of factors).

Layout (SIS Compendio de Archivos Maestros, cap. II, Título III and Título IV; probe receipt 41958591396):
- Planes de Salud, 38 fields: 1 periodo, 2 isapre, 3 plan id, 4 nombre, 5 línea, 6 fecha inicio, 7 grupo objetivo,
  8 grupo socioeconómico, 9 comercialización, 10 regiones, 11 tipo (Individual/Grupal), 12 modalidad de atención,
  13 amplitud, 14 prestaciones restringidas, 15 modalidad del precio, 16 precio base (UF), 17 tabla de factores,
  18-23 adecuación, 24 precio base final, 25 arancel, 26 modalidad arancel, 27 % bonificación ambulatoria,
  28 % bonificación hospitalaria, 29 copago fijo, 30 modalidad tope anual, 31 tope anual, 32 cotizantes,
  33 cargas (open-data columns beyond the master file; their meaning is confirmed by reconciliation against the SIS
  monthly cartera workbook in the ficha builder), 34-38 blank.
- Cobertura Planes, 16 fields: 1 isapre, 2 periodo, 3 plan id, 4 % LE ambulatoria, 5 tope amb (Con/Sin Tope),
  6-8 tope amb ($, UF, veces), 9 % LE hospitalaria, 10 tope hosp, 11-13 tope hosp, 14 código Fonasa, 15-16 not used.

Minimum cells: a price or coverage distribution (median, quartiles, mean) is published only with >= 5 plans; a
cotizante-weighted statistic only with >= 5 plans that have cotizantes and >= 30 cotizantes. Counts are always
published (a count of plans or of cotizantes per Isapre is not about a person).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, unquote

_SPEC = importlib.util.spec_from_file_location("aggregate_sis_open_data", Path(__file__).resolve().with_name("aggregate_sis_open_data.py"))
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

SCRIPT_VERSION = "sis_planes_agg_v1"
FILE_HOST = base.FILE_HOST
MAX_FILE_BYTES = base.MAX_FILE_BYTES
PLANES = "Planes de Salud"
COBERTURA = "Cobertura Planes"
FILE_RX = {PLANES: re.compile(r"/Planes_de_Salud_(\d{4})(\d{2})\.zip$", re.I),
           COBERTURA: re.compile(r"/Cobertura_Planes_Salud_(\d{4})(\d{2})\.zip$", re.I)}
FILE_NAME = {PLANES: "Planes_de_Salud_{m}.zip", COBERTURA: "Cobertura_Planes_Salud_{m}.zip"}
PLAN_N = 38
COB_N = 16
MIN_PLANS = 5
MIN_W_PLANS = 5
MIN_W_COT = 30
ENTITIES = Path(__file__).resolve().parents[1] / "data" / "entities" / "isapres.json"
# Fields (0-based) of Planes de Salud.
P_PER, P_ISA, P_ID, P_NAME, P_LINE, P_START = 0, 1, 2, 3, 4, 5
P_COMER, P_TIPO, P_MOD, P_MODPRECIO, P_PRECIO, P_TABLA, P_PRECIO_FINAL = 8, 10, 11, 14, 15, 16, 23
P_BONIF_AMB, P_BONIF_HOSP, P_COT, P_CARGAS = 26, 27, 31, 32
PLAN_NAMES = ["periodo", "codigo_isapre", "id_plan", "nombre_plan", "linea_plan", "fecha_inicio", "grupo_objetivo",
              "grupo_socioeconomico", "comercializacion", "regiones", "tipo_plan", "modalidad_atencion", "amplitud",
              "prestaciones_restringidas", "modalidad_precio", "precio_base", "tabla_factores", "fecha_adecuacion",
              "tipo_adecuacion", "variacion_precio", "aplicacion_variacion", "reajuste", "fecha_reajuste",
              "precio_base_final", "arancel", "modalidad_arancel", "bonif_amb", "bonif_hosp", "copago_fijo",
              "modalidad_tope", "tope_anual", "campo_32", "campo_33", "campo_34", "campo_35", "campo_36", "campo_37",
              "campo_38"]
PLAN_SENSITIVE = {P_ID, P_NAME, P_LINE}  # plan identifiers: lengths only, never values
# Fields (0-based) of Cobertura Planes.
C_ISA, C_PER, C_ID, C_AMB, C_TOPE_AMB, C_HOSP, C_TOPE_HOSP, C_CODE = 0, 1, 2, 3, 4, 8, 9, 13
COB_NAMES = ["codigo_isapre", "periodo", "id_plan", "pct_amb", "tope_amb", "tope_amb_pesos", "tope_amb_uf",
             "tope_amb_veces", "pct_hosp", "tope_hosp", "tope_hosp_pesos", "tope_hosp_uf", "tope_hosp_veces",
             "codigo_prestacion", "campo_15", "campo_16"]
COB_SENSITIVE = {C_ID}
# Standard basket (FONASA MLE 2026 codes; data/reference/fonasa_mle_2026.json). Ambulatory codes read field 4,
# hospital codes field 9 (Libre Elección coverage).
CANASTA = {
    "amb": {"0101001": "Consulta medicina general", "0301045": "Hemograma", "0302075": "Perfil bioquímico",
            "0404003": "Ecografía abdominal", "0902001": "Consulta psicólogo"},
    "hosp": {"0201001": "Día cama básico", "0201101": "Día cama medio", "2004003": "Parto",
             "2004006": "Cesárea", "1802081": "Colecistectomía VLP"},
}
CANASTA_CODES = {c: w for w, d in CANASTA.items() for c in d}


# ---------------------------------------------------------------- helpers
def norm(s: str) -> str:
    return base.norm(s)


def fnum(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        try:
            return float(s.replace(".", "").replace(",", ".")) if "," in s else None
        except ValueError:
            return None


def inum(s: str) -> int | None:
    x = fnum(s)
    return int(x) if x is not None and x == int(x) and x >= 0 else None


def comer_flag(s: str) -> str:
    n = norm(s)
    if n.startswith("no"):
        return "N"
    if "comer" in n or n in ("s", "si"):
        return "S"
    return "?"


def modalidad(s: str) -> str:
    n = norm(s)
    return "LE" if "libre" in n else "PP" if "preferente" in n else "PC" if "cerrado" in n else "otra"


def tipo_plan(s: str) -> str:
    n = norm(s)
    return "I" if n.startswith("indiv") else "G" if n.startswith("grup") else "otro"


def modalidad_precio(s: str) -> str:
    n = norm(s).replace(" ", "")
    return "UF" if n == "uf" else "7%" if "7" in n else "$" if n in ("$", "pesos", "peso") else "otra"


def r(x: float | None, nd: int = 2) -> float | None:
    return None if x is None else round(x, nd)


def quantile(vals: list[float], q: float) -> float | None:
    return base.quantile(sorted(vals), q)


def wquantile(pairs: list[tuple[float, float]], q: float) -> float | None:
    """Weighted lower quantile: the first value (ascending) at which the cumulative weight reaches q of the total."""
    pairs = sorted((v, w) for v, w in pairs if w > 0)
    tot = sum(w for _, w in pairs)
    if not tot:
        return None
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= q * tot - 1e-9:
            return v
    return pairs[-1][0]


def dist(vals: list[float], weights: list[float] | None = None) -> dict:
    """Distribution of a plan-level value; None where the minimum cell is not met."""
    out: dict = {"n": len(vals)}
    if len(vals) >= MIN_PLANS:
        out.update(mediana=r(quantile(vals, 0.5), 4), p25=r(quantile(vals, 0.25), 4), p75=r(quantile(vals, 0.75), 4),
                   media=r(sum(vals) / len(vals), 4))
    else:
        out.update(mediana=None, p25=None, p75=None, media=None, suprimido=f"<{MIN_PLANS} planes")
    if weights is not None:
        pw = [(v, w) for v, w in zip(vals, weights) if w > 0]
        tw = sum(w for _, w in pw)
        out["n_con_peso"], out["peso"] = len(pw), int(tw)
        if len(pw) >= MIN_W_PLANS and tw >= MIN_W_COT:
            out.update(mediana_pond=r(wquantile(pw, 0.5), 4), media_pond=r(sum(v * w for v, w in pw) / tw, 4))
        else:
            out.update(mediana_pond=None, media_pond=None)
    return out


# ---------------------------------------------------------------- Planes de Salud
class PlanesAgg:
    """Plan-level rows kept in memory (a month has ~30k plans); only aggregates leave this object."""

    def __init__(self, types: dict[str, str]):
        self.types = types
        self.plans: dict[tuple[str, str], dict] = {}
        self.periods: Counter = Counter()
        self.dup = 0
        self.raw: dict[str, Counter] = {k: Counter() for k in ("comercializacion", "tipo_plan", "modalidad_atencion", "modalidad_precio", "tabla_factores")}
        self.bad_num: Counter = Counter()
        self.extra_nonblank = 0
        self.profile = base.Profiler(PLAN_NAMES, PLAN_SENSITIVE)
        self.rows = 0

    def add(self, f: list[str]) -> None:
        self.rows += 1
        self.profile.add(f)
        self.periods[f[P_PER].strip()] += 1
        for k, i in (("comercializacion", P_COMER), ("tipo_plan", P_TIPO), ("modalidad_atencion", P_MOD),
                     ("modalidad_precio", P_MODPRECIO), ("tabla_factores", P_TABLA)):
            self.raw[k][f[i].strip()] += 1
        if any(x.strip() for x in f[33:]):
            self.extra_nonblank += 1
        cot, car = inum(f[P_COT]), inum(f[P_CARGAS])
        for name, x in (("campo_32", cot), ("campo_33", car)):
            if x is None:
                self.bad_num[name] += 1
        precio = fnum(f[P_PRECIO])
        if precio is None:
            self.bad_num["precio_base"] += 1
        key = (f[P_ISA].strip(), f[P_ID].strip())
        if key in self.plans:
            self.dup += 1
            return
        self.plans[key] = {"isapre": key[0], "comer": comer_flag(f[P_COMER]), "tipo": tipo_plan(f[P_TIPO]),
                           "mod": modalidad(f[P_MOD]), "mprecio": modalidad_precio(f[P_MODPRECIO]),
                           "precio": precio, "precio_final": fnum(f[P_PRECIO_FINAL]),
                           "bonif_amb": fnum(f[P_BONIF_AMB]), "bonif_hosp": fnum(f[P_BONIF_HOSP]),
                           "cot": cot or 0, "cargas": car or 0, "inicio": f[P_START].strip()[:4]}

    def groups(self) -> dict[str, list[dict]]:
        g: dict[str, list[dict]] = defaultdict(list)
        for p in self.plans.values():
            g["sistema"].append(p)
            t = self.types.get(p["isapre"])
            if t in ("open", "closed"):
                g["abiertas" if t == "open" else "cerradas"].append(p)
            g[f"isapre:{p['isapre']}"].append(p)
        return g

    @staticmethod
    def cell(ps: list[dict]) -> dict:
        priced = [p for p in ps if p["mprecio"] in ("UF", "$") and (p["precio"] or 0) > 0]
        out = {"planes": len(ps), "cotizantes": sum(p["cot"] for p in ps), "cargas": sum(p["cargas"] for p in ps),
               "planes_con_cotizantes": sum(1 for p in ps if p["cot"] > 0),
               "precio_uf": dist([p["precio"] for p in priced], [p["cot"] for p in priced]),
               "precio_7pct": {"planes": sum(1 for p in ps if p["mprecio"] == "7%"),
                               "cotizantes": sum(p["cot"] for p in ps if p["mprecio"] == "7%")},
               "bonif_amb": dist([p["bonif_amb"] for p in ps if p["bonif_amb"] is not None],
                                 [p["cot"] for p in ps if p["bonif_amb"] is not None]),
               "bonif_hosp": dist([p["bonif_hosp"] for p in ps if p["bonif_hosp"] is not None],
                                  [p["cot"] for p in ps if p["bonif_hosp"] is not None])}
        for dim in ("mod", "tipo"):
            c: dict = {}
            for p in ps:
                d = c.setdefault(p[dim], {"planes": 0, "cotizantes": 0})
                d["planes"] += 1
                d["cotizantes"] += p["cot"]
            out[{"mod": "por_modalidad", "tipo": "por_tipo"}[dim]] = dict(sorted(c.items()))
        return out

    def result(self) -> dict:
        sets = {"todos": lambda p: True, "venta": lambda p: p["comer"] == "S", "no_venta": lambda p: p["comer"] == "N",
                "vigentes": lambda p: p["cot"] > 0, "cerrados_con_cotizantes": lambda p: p["comer"] == "N" and p["cot"] > 0,
                "venta_individual": lambda p: p["comer"] == "S" and p["tipo"] == "I",
                "vigentes_individual": lambda p: p["cot"] > 0 and p["tipo"] == "I"}
        out: dict = {}
        for key, ps in sorted(self.groups().items()):
            out[key] = {name: self.cell([p for p in ps if fn(p)]) for name, fn in sets.items()}
        return {"grupos": out, "conjuntos": {
            "todos": "todas las filas del archivo (planes vigentes y/o en comercialización)",
            "venta": "comercialización = S (a la venta en el mes)",
            "no_venta": "comercialización = N (cerrados a venta)",
            "vigentes": "planes con al menos un cotizante (campo 32 > 0)",
            "cerrados_con_cotizantes": "comercialización = N y cotizantes > 0",
            "venta_individual": "a la venta y tipo Individual", "vigentes_individual": "con cotizantes y tipo Individual"},
            "regla_celda_minima": {"planes": MIN_PLANS, "planes_con_peso": MIN_W_PLANS, "cotizantes_peso": MIN_W_COT},
            "precio": "precio base (campo 16, UF) de planes con modalidad de precio UF o $; los planes al 7 % se cuentan aparte",
            "planes_unicos": len(self.plans), "filas_duplicadas_isapre_plan": self.dup,
            "filas_con_campos_34_38_no_vacios": self.extra_nonblank, "errores_numericos": dict(self.bad_num),
            "periodos_en_archivo": dict(self.periods.most_common(5)),
            "valores_columnas": {k: dict(v.most_common(12)) for k, v in self.raw.items()},
            "precio_base_igual_final": sum(1 for p in self.plans.values() if p["precio"] == p["precio_final"]),
            "isapres_sin_tipo": sorted({p["isapre"] for p in self.plans.values() if self.types.get(p["isapre"]) not in ("open", "closed")})}


# ---------------------------------------------------------------- Cobertura Planes
class CoberturaAgg:
    """Standard-basket coverage per plan, joined in memory with the Planes de Salud rows of the same month."""

    def __init__(self, plans: dict[tuple[str, str], dict] | None, types: dict[str, str]):
        self.plans, self.types = plans or {}, types
        self.cov: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)  # (isapre, plan) -> code -> max %
        self.tope: dict[tuple[str, str], dict[str, bool]] = defaultdict(dict)
        self.multi: Counter = Counter()
        self.rows = self.rows_canasta = self.bad = 0
        self.periods: Counter = Counter()
        self.codes_seen: Counter = Counter()
        self.plans_seen: set = set()
        self.profile = base.Profiler(COB_NAMES, COB_SENSITIVE)

    def add(self, f: list[str]) -> None:
        self.rows += 1
        self.profile.add(f)
        self.periods[f[C_PER].strip()] += 1
        key = (f[C_ISA].strip(), f[C_ID].strip())
        self.plans_seen.add(key)
        code = f[C_CODE].strip().zfill(7)
        world = CANASTA_CODES.get(code)
        if not world:
            return
        self.rows_canasta += 1
        self.codes_seen[code] += 1
        x = fnum(f[C_AMB if world == "amb" else C_HOSP])
        if x is None or not 0 <= x <= 100:
            self.bad += 1
            return
        t = norm(f[C_TOPE_AMB if world == "amb" else C_TOPE_HOSP]).startswith("con")
        d = self.cov[key]
        if code in d:
            self.multi[code] += 1
            if x <= d[code]:
                return
        d[code] = x
        self.tope[key][code] = t

    def result(self) -> dict:
        joined = {k: self.plans.get(k) for k in self.cov}
        groups: dict[str, list] = defaultdict(list)
        for k, p in joined.items():
            if p is None:
                continue
            groups["sistema"].append(k)
            t = self.types.get(k[0])
            if t in ("open", "closed"):
                groups["abiertas" if t == "open" else "cerradas"].append(k)
            groups[f"isapre:{k[0]}"].append(k)
        out: dict = {}
        for g, keys in sorted(groups.items()):
            cell: dict = {"planes": len(keys), "codigos": {}, "canasta": {}}
            for code, world in CANASTA_CODES.items():
                ks = [k for k in keys if code in self.cov[k]]
                cell["codigos"][code] = {**dist([self.cov[k][code] for k in ks], [joined[k]["cot"] for k in ks]),
                                         "con_tope": sum(1 for k in ks if self.tope[k].get(code)), "mundo": world}
            for world, codes in CANASTA.items():
                ks = [k for k in keys if all(c in self.cov[k] for c in codes)]
                vals = [sum(self.cov[k][c] for c in codes) / len(codes) for k in ks]
                cell["canasta"][world] = dist(vals, [joined[k]["cot"] for k in ks])
            out[g] = cell
        return {"grupos": out, "canasta": CANASTA, "filas_canasta": self.rows_canasta, "valores_invalidos": self.bad,
                "registros_multiples_por_plan_codigo": dict(self.multi), "regla_registros_multiples": "se toma el % más alto",
                "codigos_en_archivo": dict(self.codes_seen), "periodos_en_archivo": dict(self.periods.most_common(5)),
                "planes_en_archivo": len(self.plans_seen),
                "planes_sin_fila_en_planes_de_salud": sum(1 for k in self.plans_seen if k not in self.plans),
                "planes_canasta_unidos": sum(1 for p in joined.values() if p is not None),
                "planes_canasta_unidos_a_venta": sum(1 for p in joined.values() if p is not None and p["comer"] == "S"),
                "planes_canasta_unidos_individuales": sum(1 for p in joined.values() if p is not None and p["tipo"] == "I"),
                "regla_celda_minima": {"planes": MIN_PLANS, "planes_con_peso": MIN_W_PLANS, "cotizantes_peso": MIN_W_COT},
                "nota": "cobertura de libre elección (archivo maestro Título IV: planes individuales en comercialización); "
                        "la cobertura preferente no se informa en este archivo"}


# ---------------------------------------------------------------- discovery
def month_add(m: str, k: int) -> str:
    y, mm = int(m[:4]), int(m[4:])
    n = y * 12 + mm - 1 + k
    return f"{n // 12}{n % 12 + 1:02d}"


def months_linked(links: list[str], dataset: str) -> dict[str, str]:
    out = {}
    for u in links:
        m = FILE_RX[dataset].search(unquote(u))
        if m:
            out[m.group(1) + m.group(2)] = u
    return out


def plan_months(links: list[str], period: str = "latest") -> tuple[str | None, list[str]]:
    linked = months_linked(links, PLANES)
    if not linked:
        return None, []
    t = max(linked) if period == "latest" else period
    return t, [m for m in (t, month_add(t, -1), month_add(t, -12)) if m in linked]


def url_for(dataset: str, month: str, links: list[str]) -> str:
    hit = months_linked(links, dataset).get(month)
    return hit or f"https://{FILE_HOST}/archivos/{quote(dataset)}/{month[:4]}/{FILE_NAME[dataset].format(m=month)}"


def load_types(path: Path = ENTITIES) -> dict[str, str]:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(e.get("official_code")): str(e.get("isapre_type")) for e in d.get("entities") or [] if e.get("official_code") is not None}


def aggregate_month(month: str, out: Path, fetch, drop, types: dict[str, str], cobertura: bool) -> dict:
    receipts: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "script_version": SCRIPT_VERSION,
                      "user_agent": base.UA, "max_file_bytes": MAX_FILE_BYTES,
                      "github_run_id": os.environ.get("GITHUB_RUN_ID"), "github_sha": os.environ.get("GITHUB_SHA"),
                      "period": month, "files": []}
    pa = PlanesAgg(types)
    p, rec = fetch(PLANES, month)
    if p:
        base.process_zip(p, PLAN_N, pa.add, rec)
        drop(p)
    receipts["files"].append(rec)
    if p:
        meta = {"periodo": month, "script_version": SCRIPT_VERSION, "sha256_archivo": rec["sha256"], "filas": pa.rows}
        base.write_json(out / f"planes_{month}.json", {**meta, **pa.result(), "perfil_columnas": pa.profile.result()})
    if cobertura and p:
        ca = CoberturaAgg(pa.plans, types)
        cp, crec = fetch(COBERTURA, month)
        if cp:
            base.process_zip(cp, COB_N, ca.add, crec)
            drop(cp)
            base.write_json(out / f"cobertura_{month}.json", {
                "periodo": month, "script_version": SCRIPT_VERSION, "sha256_archivo": crec["sha256"], "filas": ca.rows,
                "sha256_planes": rec["sha256"], **ca.result(), "perfil_columnas": ca.profile.result()})
        receipts["files"].append(crec)
    receipts["finished_at"] = datetime.now(timezone.utc).isoformat()
    base.write_json(out / f"receipts_{month}.json", receipts)
    return receipts


def run(t: str, months: list[str], out_root: Path, links: list[str] | None, local: dict[str, Path] | None = None,
        types: dict[str, str] | None = None) -> dict:
    """``months`` = [t, t-1, t-12] as linked; Cobertura for t and t-12 only."""
    types = types if types is not None else load_types()
    tmp = Path(tempfile.mkdtemp(prefix="sis_planes_"))

    def fetch(dataset: str, month: str) -> tuple[Path | None, dict]:
        if local is not None:
            p = local.get(f"{dataset}:{month}")
            if p is None:
                return None, {"dataset": dataset, "period": month, "error": "local_missing"}
            data = p.read_bytes()
            return p, {"dataset": dataset, "period": month, "url": f"local:{p.name}", "bytes": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}
        url = url_for(dataset, month, links or [])
        dest = tmp / f"{dataset.replace(' ', '_')}_{month}.zip"
        rec = {"dataset": dataset, "period": month, **base.download(url, dest, MAX_FILE_BYTES)}
        if "sha256" not in rec and dest.exists():
            dest.unlink()
        return (dest if "sha256" in rec else None), rec

    def drop(p: Path) -> None:
        if local is None and p.exists():
            p.unlink()

    out: dict = {}
    try:
        for m in months:
            out[m] = aggregate_month(m, out_root / m, fetch, drop, types, cobertura=m in (t, month_add(t, -12)))
    finally:
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="latest", help="'latest' (newest month linked on the SIS page) or yyyymm")
    ap.add_argument("--output-root", required=True, help="months are written to <output-root>/<yyyymm>/")
    a = ap.parse_args()
    links = base.page_links()
    t, months = plan_months(links, a.period)
    if not t or t not in months:
        raise SystemExit("no Planes de Salud month linked on the SIS page (robots, network or layout): nothing is guessed")
    cob = months_linked(links, COBERTURA)
    recs = run(t, months, Path(a.output_root), links)
    print(json.dumps({"t": t, "months": months, "cobertura_linked_latest": max(cob) if cob else None,
                      "files": {m: [{k: f.get(k) for k in ("dataset", "period", "status", "bytes", "sha256", "error")}
                                    | {"rows_ok": (f.get("parse") or {}).get("rows_ok"),
                                       "malformed": (f.get("parse") or {}).get("rows_malformed"),
                                       "fields": (f.get("parse") or {}).get("field_count_histogram")}
                                    for f in rec["files"]] for m, rec in recs.items()}}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
