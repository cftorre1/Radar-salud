"""Aggregates of SIS open data: Prestaciones Bonificadas and Licencias Médicas (Dirección 5-nov-2026).

Runs in GitHub Actions (the sandbox cannot reach datos.superdesalud.gob.cl). It downloads the quarterly ZIP files
with the probe's User-Agent and robots.txt logic (fail closed), stream-processes the pipe-delimited TXT member line
by line, and writes ONLY aggregate JSON plus receipts (URL, bytes, SHA-256, row counts). No raw file, row-level data
or encrypted identifier value is ever written.

Owner rules enforced here (mandatory):
- encrypted IDs (RUN/RUT/folios) are used only as opaque grouping keys in memory; never reversed, never written;
- Licencias: aggregates only by Isapre, diagnosis group, industry, region and tipo profesional; cells < 10 records
  are suppressed;
- Prestaciones: providers only as pseudonymous keys inside aggregates; region x prestación prices are publishable
  only with >= 3 distinct providers AND >= 30 frecuencia; with 1-2 providers only a concentration flag (n providers,
  share), no price, marked "revisión Dirección".
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import tempfile
import time
import unicodedata
import urllib.robotparser
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import IO, Iterable, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

PAGE = "https://www.superdesalud.gob.cl/tax-biblioteca-digital/datos-abiertos-de-isapres-6988/"
FILE_HOST = "datos.superdesalud.gob.cl"
UA = "AlicantoSaludBot/1.0 (+https://alicantosalud.cl; datos abiertos SIS, lectura acotada)"
# Prestaciones: Dirección allowed "~400 MB"; run 41962408457 showed the 2026t2 ZIP is 458,865,683 bytes
# (Content-Length), so the bound is 460 MiB (482 MB). Integration owner to confirm or revert.
MAX_BYTES = {"Prestaciones Bonificadas": 460 * 1024 * 1024, "Licencias Medicas": 60 * 1024 * 1024,
             "Arancel Isapre": 20 * 1024 * 1024}
ROBOTS: dict[str, urllib.robotparser.RobotFileParser | None] = {}

PRICE_MIN_PROVIDERS = 3
PRICE_MIN_FREQ = 30
LIC_MIN_CELL = 10
NO_PROVIDER = ("", "0")

# ---------------------------------------------------------------- layouts (official dictionaries, 1-based -> 0-based)
PREST_N = 30
P_ISAPRE, P_PERIODO, P_TIPO_REG, P_RUN_BEN, P_SEXO, P_EDAD, P_TIPO_BEN, P_PRESTADOR, P_REGION, P_PREFERENTE = range(10)
P_FOLIOS = (10, 11, 12, 13)
(P_CODIGO, P_PERTENENCIA, P_COBERTURA, P_FECHA_BONIF, P_TIPO_PRESTADOR, P_TIPO_ATENCION, P_FREC, P_FACT, P_BONIF,
 P_COPAGO, P_BONIF_RESTR, P_TIPO_PLAN, P_MOD_IQ, P_LEY_URG, P_GPP, P_GES) = range(14, 30)
PREST_NAMES = ["codigo_aseguradora", "periodo", "tipo_registro", "run_beneficiario_enc", "sexo", "edad_tramo",
               "tipo_beneficiario", "rut_prestador_enc", "region_prestador", "prestador_preferente", "folio_1_enc",
               "folio_2_enc", "folio_3_enc", "folio_4_enc", "codigo_prestacion", "pertenencia_codigo",
               "cobertura_financiamiento", "fecha_bonificacion", "tipo_prestador", "tipo_atencion", "frecuencia",
               "valor_facturado", "valor_bonificado", "monto_copago", "bonificacion_restringida", "tipo_plan",
               "modalidad_iq", "ley_urgencia", "codigo_gpp", "id_ges"]
PREST_SENSITIVE = {P_RUN_BEN, P_PRESTADOR, *P_FOLIOS, P_GES}  # id GES is a case identifier: lengths only

LIC_N = 44
(L_ISAPRE, L_FECHA_INFO, L_RUN_TRAB, L_FECHA_EMISION, L_DIAS, L_INICIO, L_EDAD, L_SEXO, L_ACTIVIDAD, L_OCUPACION,
 L_TIPO_LIC, L_CARACT, L_RUN_PROF, L_TIPO_PROF, L_TIPO_CONTRALORIA, L_DIAS_AUT, L_DIAG, L_RESOL, L_PERIODO,
 L_REPOSO_AUT, L_DERECHO, L_REC_ISAPRE, L_RES_ISAPRE, L_REC_EMPL, L_REGION, L_CALIDAD, L_PAGADORA, L_DIAS_PAGAR,
 L_SUBSIDIO, L_APORTE_PREV, L_INICIO_PAGO, L_RECUP, L_CONCEPCION, L_APORTE_PENS, L_OTROS_DIAG, L_RUN_HIJO,
 L_LUGAR, L_CAUSA, L_DIAS_PREVIOS, L_PRIMERA_AFIL, L_CONTRATO, L_BASE_CALCULO, L_RUT_EMPL, L_NAC_HIJO) = range(44)
LIC_NAMES = ["codigo_isapre", "fecha_informacion", "run_trabajador_enc", "fecha_emision", "numero_dias",
             "fecha_inicio_reposo", "edad", "sexo", "actividad_laboral", "ocupacion", "tipo_licencia",
             "caracteristicas_reposo", "run_profesional_enc", "tipo_profesional", "tipo_licencia_contraloria",
             "dias_autorizados", "diagnostico_principal", "tipo_resolucion", "periodo", "reposo_autorizado",
             "derecho_subsidio", "fecha_recepcion_isapre", "fecha_resolucion_isapre", "fecha_recepcion_empleador",
             "region", "calidad_trabajador", "entidad_pagadora", "dias_a_pagar", "monto_subsidio_liquido",
             "aporte_previsional_isapre", "fecha_inicio_pago", "recuperabilidad", "fecha_concepcion",
             "aporte_pensiones", "otros_diagnosticos", "run_hijo_enc", "lugar_reposo", "causa_rechazo_modificacion",
             "dias_previos_autorizados", "fecha_primera_afiliacion", "fecha_contrato", "monto_base_calculo",
             "rut_empleador_enc", "fecha_nacimiento_hijo"]
LIC_SENSITIVE = {L_RUN_TRAB, L_RUN_PROF, L_RUN_HIJO, L_RUT_EMPL, L_CONCEPCION, L_NAC_HIJO, L_OTROS_DIAG}
LIC_DIMENSIONS = {"isapre": L_ISAPRE, "diagnostico": L_DIAG, "actividad_laboral": L_ACTIVIDAD, "region": L_REGION,
                  "tipo_profesional": L_TIPO_PROF}


# ---------------------------------------------------------------- helpers
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def num(s: str, errors: Counter, field: str) -> float:
    s = s.strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        try:
            return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s.replace(" ", ""))
        except ValueError:
            errors[field] += 1
            return 0.0


def quantile(sorted_vals: list[float], q: float) -> float | None:
    """Linear interpolation (numpy default) on an already sorted list."""
    if not sorted_vals:
        return None
    pos = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def hist_quantile(hist: Counter, q: float) -> float | None:
    """Lower quantile from a value->count histogram."""
    total = sum(hist.values())
    if not total:
        return None
    target, acc = q * (total - 1), 0
    for k in sorted(hist):
        acc += hist[k]
        if acc - 1 >= target:
            return float(k)
    return float(max(hist))


def r(x: float | None, nd: int = 2) -> float | None:
    return None if x is None else round(x, nd)


def pct(a: float, b: float) -> float | None:
    return round(100.0 * a / b, 2) if b else None


class RowReader:
    """Streams pipe-delimited rows from a binary file object; counts malformed rows instead of yielding them."""

    def __init__(self, n_fields: int):
        self.n = n_fields
        self.lines = self.ok = self.blank = self.malformed = 0
        self.field_hist: Counter = Counter()
        self.enc: Counter = Counter()
        self.header: list[str] | None = None

    def rows(self, stream: IO[bytes]) -> Iterator[list[str]]:
        first = True
        for raw in stream:
            self.lines += 1
            line = raw.rstrip(b"\r\n")
            if not line.strip():
                self.blank += 1
                continue
            try:
                s = line.decode("utf-8")
                self.enc["utf-8"] += 1
            except UnicodeDecodeError:
                s = line.decode("latin-1")
                self.enc["latin-1"] += 1
            f = s.split("|")
            if len(f) == self.n + 1 and f[-1].strip() == "":
                f.pop()  # trailing delimiter, as in the real files
            self.field_hist[len(f)] += 1
            if first:
                first = False
                if not f[0].strip().isdigit():  # a header line with column names (the 2026 files have none)
                    self.header = [x.strip()[:60] for x in f]
                    continue
            if len(f) != self.n:
                self.malformed += 1
                continue
            self.ok += 1
            yield f

    def receipt(self) -> dict:
        return {"lines_read": self.lines, "rows_ok": self.ok, "rows_malformed": self.malformed,
                "blank_lines": self.blank, "expected_fields": self.n,
                "field_count_histogram": {str(k): v for k, v in sorted(self.field_hist.items())},
                "header_row_detected": self.header is not None, "header": self.header,
                "line_encoding": dict(self.enc)}


class Profiler:
    """Per-column profile to verify order against the dictionary; never stores values of sensitive columns."""

    def __init__(self, names: list[str], sensitive: set[int], top: int = 8, cap: int = 5000,
                 max_rows: int = 3_000_000):
        self.names, self.sensitive, self.top, self.cap, self.max_rows = names, sensitive, top, cap, max_rows
        self.values = [Counter() for _ in names]
        self.overflow = [False] * len(names)
        self.numeric = [0] * len(names)
        self.empty = [0] * len(names)
        self.lengths = [Counter() for _ in names]
        self.n = 0

    def add(self, f: list[str]) -> None:
        if self.n >= self.max_rows:  # profile is a layout check; the first rows are enough and keep it cheap
            return
        self.n += 1
        for i, v in enumerate(f):
            v = v.strip()
            if not v:
                self.empty[i] += 1
                continue
            if v.replace(".", "", 1).replace("-", "", 1).isdigit():
                self.numeric[i] += 1
            if i in self.sensitive:
                self.lengths[i][len(v)] += 1
                continue
            c = self.values[i]
            if v in c or len(c) < self.cap:
                c[v] += 1
            else:
                self.overflow[i] = True

    def result(self) -> list[dict]:
        out = []
        for i, name in enumerate(self.names):
            d = {"pos": i + 1, "name": name, "filas_perfiladas": self.n, "pct_empty": pct(self.empty[i], self.n),
                 "pct_numeric": pct(self.numeric[i], self.n)}
            if i in self.sensitive:
                d["sensitive"] = True
                d["value_length_hist"] = {str(k): v for k, v in sorted(self.lengths[i].most_common(6))}
            else:
                d["distinct_values"] = f">{self.cap}" if self.overflow[i] else len(self.values[i])
                d["top_values"] = self.values[i].most_common(self.top)
            out.append(d)
        return out


# ---------------------------------------------------------------- Prestaciones
def is_fonasa(pertenencia: str) -> bool:
    return "fonasa" in norm(pertenencia)


class PrestacionesAgg:
    def __init__(self, ids_only: bool = False, focus: Iterable[str] = ()):
        self.ids_only = ids_only
        self.focus = set(focus)
        self.focus_cells: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0])  # (cod, reg, prov)
        self.focus_isapre: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0.0])        # (cod, reg, prov, isapre)
        self.focus_meta: dict[str, Counter] = defaultdict(Counter)
        self.err: Counter = Counter()
        self.prov_isapres: dict[str, set] = defaultdict(set)
        self.prov_fact: dict[str, float] = defaultdict(float)
        self.prov_rows: Counter = Counter()
        self.empty_prov = 0
        self.rows = 0
        if ids_only:
            return
        self.profile = Profiler(PREST_NAMES, PREST_SENSITIVE)
        self.isapre_atencion: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0])
        self.price: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])          # (codigo, region, prov)
        self.cross: dict[tuple, dict] = defaultdict(dict)                         # (prov, codigo) -> isapre
        self.region_prov: dict[tuple, float] = defaultdict(float)
        self.region_tipo: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0])
        self.fonasa_rows = 0
        self.periods: Counter = Counter()

    def add(self, f: list[str]) -> None:
        self.rows += 1
        isapre, prov = f[P_ISAPRE].strip(), f[P_PRESTADOR].strip()
        fact = num(f[P_FACT], self.err, "valor_facturado")
        if prov in NO_PROVIDER:
            self.empty_prov += 1
        else:
            self.prov_isapres[prov].add(isapre)
            self.prov_fact[prov] += fact
            self.prov_rows[prov] += 1
        if self.ids_only:
            return
        self.profile.add(f)
        self.periods[f[P_PERIODO].strip()] += 1
        freq = num(f[P_FREC], self.err, "frecuencia")
        bonif = num(f[P_BONIF], self.err, "valor_bonificado")
        copago = num(f[P_COPAGO], self.err, "monto_copago")
        region, atencion = f[P_REGION].strip() or "(vacío)", f[P_TIPO_ATENCION].strip() or "(vacío)"
        a = self.isapre_atencion[(isapre, atencion)]
        a[0] += freq; a[1] += fact; a[2] += bonif; a[3] += copago; a[4] += 1
        t = self.region_tipo[(region, f[P_TIPO_PRESTADOR].strip() or "(vacío)")]
        t[0] += fact; t[1] += freq; t[2] += 1
        if prov in NO_PROVIDER:
            return
        self.region_prov[(region, prov)] += fact
        if self.focus and f[P_CODIGO].strip() in self.focus:
            codigo = f[P_CODIGO].strip()
            fc = self.focus_cells[(codigo, region, prov)]
            fc[0] += fact; fc[1] += bonif; fc[2] += copago; fc[3] += freq; fc[4] += 1
            fi = self.focus_isapre[(codigo, region, prov, isapre)]
            fi[0] += bonif; fi[1] += fact; fi[2] += freq
            self.focus_meta[codigo]["pertenencia=" + f[P_PERTENENCIA].strip()] += 1
            self.focus_meta[codigo]["tipo_atencion=" + atencion] += 1
        if is_fonasa(f[P_PERTENENCIA]):
            self.fonasa_rows += 1
            codigo = f[P_CODIGO].strip()
            p = self.price[(codigo, region, prov)]
            p[0] += fact; p[1] += freq
            c = self.cross[(prov, codigo)].setdefault(isapre, [0.0, 0.0, 0.0])
            c[0] += bonif; c[1] += fact; c[2] += freq

    # -- outputs
    def isapre_table(self) -> list[dict]:
        tot: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0])
        rows = []
        for (isapre, at), v in sorted(self.isapre_atencion.items()):
            for k in range(5):
                tot[isapre][k] += v[k]
            rows.append(self._isapre_row(isapre, at, v))
        rows += [self._isapre_row(i, "TOTAL", v) for i, v in sorted(tot.items())]
        return rows

    @staticmethod
    def _isapre_row(isapre: str, at: str, v: list) -> dict:
        return {"isapre": isapre, "tipo_atencion": at, "registros": v[4], "frecuencia": round(v[0]),
                "facturado": round(v[1]), "bonificado": round(v[2]), "copago": round(v[3]),
                "pct_bonificado": pct(v[2], v[1]), "pct_copago": pct(v[3], v[1])}

    def price_table(self) -> dict:
        cells: dict[tuple, list] = defaultdict(list)
        nat: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])
        for (codigo, region, prov), (fact, freq) in self.price.items():
            if freq > 0 and fact > 0:
                cells[(codigo, region)].append((fact / freq, freq, fact))
            n = nat[(codigo, prov)]
            n[0] += fact; n[1] += freq
        for (codigo, prov), (fact, freq) in nat.items():
            if freq > 0 and fact > 0:
                cells[(codigo, "NACIONAL")].append((fact / freq, freq, fact))
        cols = ["codigo_prestacion", "region", "estado", "n_prestadores", "frecuencia", "facturado",
                "precio_mediana", "precio_p25", "precio_p75", "share_prestador_mayor_pct"]
        rows, status = [], Counter()
        for (codigo, region), lst in sorted(cells.items()):
            n, freq, fact = len(lst), sum(x[1] for x in lst), sum(x[2] for x in lst)
            top_share = pct(max(x[1] for x in lst), freq)
            if n >= PRICE_MIN_PROVIDERS and freq >= PRICE_MIN_FREQ:
                u = sorted(x[0] for x in lst)
                row = [codigo, region, "publicable", n, round(freq), round(fact), r(quantile(u, .5), 0),
                       r(quantile(u, .25), 0), r(quantile(u, .75), 0), top_share]
            elif n <= 2:
                row = [codigo, region, "concentracion_revision_direccion", n, round(freq), None, None, None, None,
                       top_share]
            else:
                row = [codigo, region, "suprimido_frecuencia_menor_30", n, round(freq), None, None, None, None, None]
            status[(row[2], region == "NACIONAL")] += 1
            rows.append(row)
        return {"regla": {"publicable": f">= {PRICE_MIN_PROVIDERS} prestadores distintos Y >= {PRICE_MIN_FREQ} "
                                        "frecuencia; precio unitario = facturado/frecuencia por prestador; "
                                        "mediana/p25/p75 entre prestadores (no ponderado)",
                          "concentracion": "1-2 prestadores: sin precio; n prestadores y share de frecuencia del "
                                           "mayor; marcar 'revisión Dirección'",
                          "filtro": "pertenencia del código = Fonasa; prestadores con frecuencia>0 y facturado>0"},
                "conteo_estados": [{"estado": k[0], "nacional": k[1], "celdas": v} for k, v in sorted(status.items())],
                "columns": cols, "rows": rows}

    def cross_isapre(self) -> dict:
        per_isapre: dict[str, dict] = defaultdict(lambda: {"bonif": [], "fact": [], "w": []})
        per_code_isapre: dict[tuple, list] = defaultdict(list)
        code_freq: Counter = Counter()
        n_cells = n_cells_multi = 0
        for (prov, codigo), by in self.cross.items():
            valid = {i: v for i, v in by.items() if v[2] > 0}
            n_cells += 1
            if len(valid) < 2:
                continue
            n_cells_multi += 1
            mb = sum(v[0] / v[2] for v in valid.values()) / len(valid)
            mf = sum(v[1] / v[2] for v in valid.values()) / len(valid)
            for i, v in valid.items():
                ib = (v[0] / v[2] / mb - 1) * 100 if mb > 0 else None
                ifa = (v[1] / v[2] / mf - 1) * 100 if mf > 0 else None
                d = per_isapre[i]
                if ib is not None:
                    d["bonif"].append(ib); d["w"].append(v[2])
                if ifa is not None:
                    d["fact"].append(ifa)
                per_code_isapre[(codigo, i)].append((ib, v[2], prov))
                code_freq[codigo] += v[2]
        summary = []
        for i, d in sorted(per_isapre.items()):
            b, fa = sorted(d["bonif"]), sorted(d["fact"])
            wmean = sum(x * w for x, w in zip(d["bonif"], d["w"])) / sum(d["w"]) if d["w"] else None
            summary.append({"isapre": i, "celdas_prestador_prestacion": len(b),
                            "indice_bonif_unit_mediana_pct": r(quantile(b, .5)), "p25": r(quantile(b, .25)),
                            "p75": r(quantile(b, .75)), "indice_bonif_unit_media_ponderada_frec_pct": r(wmean),
                            "indice_facturado_unit_mediana_pct": r(quantile(fa, .5)),
                            "indice_facturado_unit_p25": r(quantile(fa, .25)),
                            "indice_facturado_unit_p75": r(quantile(fa, .75))})
        top_codes = {c for c, _ in code_freq.most_common(40)}
        by_code = []
        for (codigo, i), lst in sorted(per_code_isapre.items()):
            if codigo not in top_codes:
                continue
            provs = {x[2] for x in lst}
            if len(provs) < PRICE_MIN_PROVIDERS:
                continue
            vals = sorted(x[0] for x in lst if x[0] is not None)
            by_code.append({"codigo_prestacion": codigo, "isapre": i, "n_prestadores": len(provs),
                            "frecuencia": round(sum(x[1] for x in lst)),
                            "indice_bonif_unit_mediana_pct": r(quantile(vals, .5))})
        return {"definicion": "Por celda prestador(seudónimo) x código Fonasa atendida por >=2 Isapres: índice = "
                              "(bonificado/frecuencia de la Isapre) / (media no ponderada entre Isapres de la celda) - 1,"
                              " en %. Análogo para facturado/frecuencia. Detalle por código sólo con >=3 prestadores.",
                "celdas_prestador_prestacion": n_cells, "celdas_con_2_o_mas_isapres": n_cells_multi,
                "resumen_por_isapre": summary,
                "por_prestacion_top40_frecuencia": by_code}

    def concentration(self) -> dict:
        byreg: dict[str, list] = defaultdict(list)
        nat: dict[str, float] = defaultdict(float)
        for (region, prov), fact in self.region_prov.items():
            if fact > 0:
                byreg[region].append(fact)
                nat[prov] += fact
        byreg["NACIONAL"] = list(nat.values())
        out = []
        for region, vals in sorted(byreg.items()):
            tot = sum(vals)
            vals.sort(reverse=True)
            hhi = sum((v / tot * 100) ** 2 for v in vals) if tot else None
            tipo: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0])
            for (reg, t), v in self.region_tipo.items():
                if region == "NACIONAL" or reg == region:
                    for k in range(3):
                        tipo[t][k] += v[k]
            tf = sum(v[0] for v in tipo.values())
            out.append({"region": region, "n_prestadores": len(vals), "facturado": round(tot), "hhi": r(hhi, 0),
                        "share_top5_pct": pct(sum(vals[:5]), tot), "share_top1_pct": pct(vals[0], tot) if vals else None,
                        "split_tipo_prestador": {t: {"facturado": round(v[0]), "share_facturado_pct": pct(v[0], tf),
                                                     "frecuencia": round(v[1])} for t, v in sorted(tipo.items())}})
        return {"definicion": "HHI sobre facturado entre prestadores (seudónimos) de la región del prestador, escala "
                              "0-10000; top5/top1 share de facturado. NACIONAL suma cada prestador entre regiones.",
                "regiones": out}

    def focus_report(self) -> dict:
        """Worked example per focus code: national and by region, disclosure rule applied (Dirección 5-nov)."""
        out = {}
        for codigo in sorted(self.focus):
            provs: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0])
            for (c, reg, prov), v in self.focus_cells.items():
                if c != codigo:
                    continue
                for key in ((reg, prov), ("NACIONAL", prov)):
                    for k in range(5):
                        provs[key][k] += v[k]
            isap: dict[tuple, dict] = defaultdict(dict)
            for (c, reg, prov, i), v in self.focus_isapre.items():
                if c != codigo:
                    continue
                for key in ((reg, prov), ("NACIONAL", prov)):
                    t = isap[key].setdefault(i, [0.0, 0.0, 0.0])
                    for k in range(3):
                        t[k] += v[k]
            regions = sorted({k[0] for k in provs}, key=lambda x: (x != "NACIONAL", x))
            rows = []
            for reg in regions:
                cell = [(prov, v) for (rg, prov), v in provs.items() if rg == reg and v[3] > 0 and v[0] > 0]
                n, freq = len(cell), sum(v[3] for _, v in cell)
                fact, bonif, cop = (sum(v[k] for _, v in cell) for k in range(3))
                row: dict = {"region": reg, "n_prestadores": n, "frecuencia": round(freq)}
                if n >= PRICE_MIN_PROVIDERS and freq >= PRICE_MIN_FREQ:
                    u = sorted(v[0] / v[3] for _, v in cell)
                    row.update(estado="publicable", precio_mediana=r(quantile(u, .5), 0),
                               precio_p25=r(quantile(u, .25), 0), precio_p75=r(quantile(u, .75), 0),
                               facturado=round(fact), pct_bonificado=pct(bonif, fact), pct_copago=pct(cop, fact))
                    # same pseudonymous provider, >=2 Isapres: index of each Isapre's bonificado/frecuencia
                    idx: dict[str, list] = defaultdict(list)
                    for prov, _ in cell:
                        by = {i: v for i, v in isap[(reg, prov)].items() if v[2] > 0}
                        if len(by) < 2:
                            continue
                        mb = sum(v[0] / v[2] for v in by.values()) / len(by)
                        if mb <= 0:
                            continue
                        for i, v in by.items():
                            idx[i].append((v[0] / v[2] / mb - 1) * 100)
                    row["indice_isapre_mismo_prestador"] = [
                        {"isapre": i, "n_prestadores": len(v), "indice_bonif_unit_mediana_pct": r(quantile(sorted(v), .5))}
                        for i, v in sorted(idx.items()) if len(v) >= PRICE_MIN_PROVIDERS]
                elif n <= 2:
                    row.update(estado="concentracion_revision_direccion",
                               share_prestador_mayor_pct=pct(max(v[3] for _, v in cell), freq) if cell else None)
                else:
                    row["estado"] = "suprimido_frecuencia_menor_30"
                rows.append(row)
            out[codigo] = {"perfil_filas": dict(self.focus_meta[codigo].most_common(12)), "filas": rows}
        return out

    def id_summary(self) -> dict:
        n = len(self.prov_isapres)
        multi = [p for p, s in self.prov_isapres.items() if len(s) >= 2]
        tf = sum(self.prov_fact.values())
        hist = Counter(min(len(s), 6) for s in self.prov_isapres.values())
        top_rows = self.prov_rows.most_common(1)[0][1] if self.prov_rows else 0
        return {"filas": self.rows, "codigos_prestador_distintos": n, "codigos_en_2_o_mas_isapres": len(multi),
                "pct_codigos_en_2_o_mas_isapres": pct(len(multi), n),
                "pct_facturado_de_codigos_en_2_o_mas_isapres": pct(sum(self.prov_fact[p] for p in multi), tf),
                "histograma_n_isapres_por_codigo": {("6+" if k == 6 else str(k)): v for k, v in sorted(hist.items())},
                "filas_sin_codigo_prestador": self.empty_prov,
                "pct_filas_del_codigo_mas_frecuente": pct(top_rows, self.rows)}


def id_consistency(cur: PrestacionesAgg, prev: PrestacionesAgg | None) -> dict:
    out: dict = {"trimestre_actual": cur.id_summary()}
    if prev is not None:
        out["trimestre_anterior"] = prev.id_summary()
        a, b = set(prev.prov_isapres), set(cur.prov_isapres)
        inter = a & b
        tf = sum(cur.prov_fact.values())
        out["entre_trimestres"] = {
            "codigos_anterior": len(a), "codigos_actual": len(b), "codigos_en_ambos": len(inter),
            "pct_overlap_sobre_actual": pct(len(inter), len(b)), "pct_overlap_sobre_anterior": pct(len(inter), len(a)),
            "pct_facturado_actual_de_codigos_en_ambos": pct(sum(cur.prov_fact[p] for p in inter), tf),
            "pct_codigos_en_ambos_con_mismo_conjunto_isapres": pct(
                sum(1 for p in inter if cur.prov_isapres[p] == prev.prov_isapres[p]), len(inter))}
    s = out["trimestre_actual"]
    across = out.get("entre_trimestres", {})
    out["veredicto"] = {
        "cross_isapre_valido": (s["pct_facturado_de_codigos_en_2_o_mas_isapres"] or 0) >= 20,
        "temporal_valido": ((across.get("pct_facturado_actual_de_codigos_en_ambos") or 0) >= 60) if across else None,
        "criterio": "cross-Isapre válido si >=20% del facturado proviene de códigos vistos en >=2 Isapres (un cifrado "
                    "por Isapre daría ~0%); temporal válido si >=60% del facturado del trimestre actual proviene de "
                    "códigos presentes en el anterior (un cifrado por trimestre daría ~0%)."}
    return out


# ---------------------------------------------------------------- Licencias
DATE_PATTERNS = [(re.compile(r"^(\d{4})-(\d{2})-(\d{2})"), (1, 2, 3)), (re.compile(r"^(\d{2})/(\d{2})/(\d{4})"), (3, 2, 1)),
                 (re.compile(r"^(\d{4})(\d{2})(\d{2})$"), (1, 2, 3))]
QUARTER = re.compile(r"^(\d{4})t([1-4])$", re.I)


def parse_when(s: str) -> tuple[str, object] | None:
    s = s.strip()
    m = QUARTER.match(s)
    if m:
        y = int(m.group(1))
        return ("q", y * 4 + int(m.group(2)) - 1) if y > 1900 else None
    for pat, (yi, mi, di) in DATE_PATTERNS:
        m = pat.match(s)
        if m:
            try:
                d = date(int(m.group(yi)), int(m.group(mi)), int(m.group(di)))
            except ValueError:
                return None
            return ("d", d) if d.year > 1900 else None
    return None


def resolution_kind(s: str) -> str:
    n = norm(s)
    for k, pref in (("rechazada", ("rechaz", "rechac")), ("reducida", ("reduc",)), ("ampliada", ("ampl",)),
                    ("autorizada", ("autor",))):
        if n.startswith(pref):
            return k
    return "otra"


class LicGroup:
    __slots__ = ("n", "kinds", "dias_sol", "dias_aut", "subsidio", "n_subsidio", "lag_days", "lag_q", "no_date")

    def __init__(self):
        self.n = 0
        self.kinds: Counter = Counter()
        self.dias_sol = self.dias_aut = self.subsidio = 0.0
        self.n_subsidio = self.no_date = 0
        self.lag_days: Counter = Counter()
        self.lag_q: Counter = Counter()


class LicenciasAgg:
    def __init__(self):
        self.err: Counter = Counter()
        self.profile = Profiler(LIC_NAMES, LIC_SENSITIVE)
        self.groups: dict[str, dict[str, LicGroup]] = {d: defaultdict(LicGroup) for d in LIC_DIMENSIONS}
        self.total = LicGroup()
        self.date_kinds: Counter = Counter()

    def add(self, f: list[str]) -> None:
        self.profile.add(f)
        kind = resolution_kind(f[L_RESOL])
        ds = num(f[L_DIAS], self.err, "numero_dias")
        da = num(f[L_DIAS_AUT], self.err, "dias_autorizados")
        sub = num(f[L_SUBSIDIO], self.err, "monto_subsidio_liquido")
        rec, res = parse_when(f[L_REC_ISAPRE]), parse_when(f[L_RES_ISAPRE])
        lag_d = lag_q = None
        if rec and res and rec[0] == res[0]:
            self.date_kinds[rec[0]] += 1
            if rec[0] == "d":
                lag_d = (res[1] - rec[1]).days
            else:
                lag_q = res[1] - rec[1]
        else:
            self.date_kinds["no_parse"] += 1
        groups = [self.total] + [self.groups[d][f[i].strip() or "(vacío)"] for d, i in LIC_DIMENSIONS.items()]
        for g in groups:
            g.n += 1
            g.kinds[kind] += 1
            g.dias_sol += ds
            g.dias_aut += da
            g.subsidio += sub
            if sub > 0:
                g.n_subsidio += 1
            if lag_d is not None:
                g.lag_days[lag_d] += 1
            elif lag_q is not None:
                g.lag_q[lag_q] += 1
            else:
                g.no_date += 1

    @staticmethod
    def row(key: str, g: LicGroup) -> dict:
        d = {"grupo": key, "licencias": g.n, "pct_rechazadas": pct(g.kinds["rechazada"], g.n),
             "pct_reducidas": pct(g.kinds["reducida"], g.n), "pct_autorizadas": pct(g.kinds["autorizada"], g.n),
             "pct_ampliadas": pct(g.kinds["ampliada"], g.n), "dias_solicitados": round(g.dias_sol),
             "dias_autorizados": round(g.dias_aut), "ratio_autorizados_solicitados_pct": pct(g.dias_aut, g.dias_sol),
             "dias_solicitados_por_licencia": r(g.dias_sol / g.n) if g.n else None,
             "subsidio_total": round(g.subsidio), "subsidio_por_licencia": r(g.subsidio / g.n, 0) if g.n else None,
             "subsidio_por_licencia_con_pago": r(g.subsidio / g.n_subsidio, 0) if g.n_subsidio else None,
             "pct_con_subsidio": pct(g.n_subsidio, g.n)}
        if g.lag_days:
            d["mediana_dias_recepcion_resolucion"] = hist_quantile(g.lag_days, .5)
        if g.lag_q:
            d["pct_resuelta_mismo_trimestre_recepcion"] = pct(g.lag_q.get(0, 0), sum(g.lag_q.values()))
        return d

    def result(self) -> dict:
        out: dict = {"regla_celda_minima": LIC_MIN_CELL, "total": self.row("TOTAL", self.total), "breakdowns": {}}
        for dim, groups in self.groups.items():
            rows = [self.row(k, g) for k, g in sorted(groups.items(), key=lambda kv: -kv[1].n) if g.n >= LIC_MIN_CELL]
            sup = [g for g in groups.values() if g.n < LIC_MIN_CELL]
            out["breakdowns"][dim] = {"filas": rows, "celdas_suprimidas_menor_10": len(sup),
                                      "licencias_en_celdas_suprimidas": sum(g.n for g in sup)}
        if self.date_kinds.get("d"):
            out["nota_fechas"] = "Fechas de recepción/resolución con día: mediana en días calculada."
        else:
            out["nota_fechas"] = ("Las fechas de recepción y resolución Isapre vienen sólo con granularidad trimestral "
                                  "(p.ej. '2026t2'); la mediana de días recepción->resolución NO es calculable. Se "
                                  "reporta el % resuelto en el mismo trimestre de recepción.")
        out["tipos_fecha"] = dict(self.date_kinds)
        return out


# ---------------------------------------------------------------- network (probe logic)
def get(url: str, limit: int, timeout: int = 120) -> tuple[int, bytes, dict]:
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read(limit + 1)
            if len(data) > limit:
                raise ValueError(f"over_limit:{limit}")
            return resp.status, data, dict(resp.headers)
    except HTTPError as e:
        return e.code, b"", dict(e.headers or {})


def allowed(url: str) -> tuple[bool, str]:
    host = urlparse(url).netloc
    if host not in ROBOTS:
        try:
            status, body, _ = get(f"https://{host}/robots.txt", limit=512 * 1024, timeout=30)
        except (URLError, OSError, ValueError) as e:
            ROBOTS[host] = None
            return False, f"robots_unreachable:{type(e).__name__}"
        if status == 404:
            ROBOTS[host] = urllib.robotparser.RobotFileParser()
            ROBOTS[host].parse([])
        elif status != 200:
            ROBOTS[host] = None
            return False, f"robots_status:{status}"
        else:
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(body.decode("utf-8", "replace").splitlines())
            ROBOTS[host] = rp
    rp = ROBOTS[host]
    if rp is None:
        return False, "robots_unavailable"
    ok = rp.can_fetch(UA, url)
    return ok, "robots_ok" if ok else "robots_disallow"


def discover(dataset: str, period: str) -> str:
    """URL from the SIS page links; falls back to the probe-observed pattern."""
    fname = f"{dataset.replace(' ', '_')}_{period}.zip"
    try:
        ok, _ = allowed(PAGE)
        if ok:
            st, body, _ = get(PAGE, limit=8 * 1024 * 1024, timeout=60)
            if st == 200:
                for m in re.findall(r'href=["\']([^"\']+)["\']', body.decode("utf-8", "replace")):
                    u = urljoin(PAGE, html.unescape(m))
                    if urlparse(u).netloc == FILE_HOST and unquote(u).lower().endswith("/" + fname.lower()):
                        return u
    except (URLError, OSError, ValueError):
        pass
    return f"https://{FILE_HOST}/archivos/{quote(dataset)}/{period[:4]}/{fname}"


def download(url: str, dest: Path, limit: int) -> dict:
    ok, why = allowed(url)
    rec: dict = {"url": url, "robots": why}
    if not ok:
        rec["error"] = "robots_blocked"
        return rec
    t0, h, n = time.time(), hashlib.sha256(), 0
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=300) as resp, open(dest, "wb") as out:
            rec.update(status=resp.status, content_length=resp.headers.get("Content-Length"),
                       last_modified=resp.headers.get("Last-Modified"), limit_bytes=limit)
            if (rec["content_length"] or "").isdigit() and int(rec["content_length"]) > limit:
                raise ValueError(f"over_limit_by_content_length:{limit}")  # fail fast, no wasted download
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                n += len(chunk)
                if n > limit:
                    raise ValueError(f"over_limit:{limit}")
                h.update(chunk)
                out.write(chunk)
    except HTTPError as e:
        rec.update(status=e.code, error=f"http_{e.code}")
        return rec
    except (URLError, OSError, ValueError) as e:
        rec["error"] = f"{type(e).__name__}:{e}"[:200]
        return rec
    rec.update(bytes=n, sha256=h.hexdigest(), download_seconds=round(time.time() - t0, 1))
    return rec


def process_zip(path: Path, n_fields: int, sink, rec: dict) -> None:
    """Streams every .txt/.csv member line by line (never materialises the text)."""
    t0 = time.time()
    with zipfile.ZipFile(path) as zf:
        rec["zip_members"] = [{"name": i.filename, "size": i.file_size} for i in zf.infolist()]
        reader = RowReader(n_fields)
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith((".txt", ".csv")):
                continue
            with zf.open(info) as stream:
                for f in reader.rows(stream):
                    sink(f)
    rec["parse"] = reader.receipt()
    rec["parse_seconds"] = round(time.time() - t0, 1)


# ---------------------------------------------------------------- main
def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def arancel_descriptions(path: Path, codes: set[str], rec: dict) -> dict:
    """Verbatim descriptions of focus codes from the Arancel Isapre file (code = field 6, description = field 8,
    as seen in the probe header line). Nothing is inferred."""
    found: dict[str, Counter] = defaultdict(Counter)
    reader = RowReader(17)
    with zipfile.ZipFile(path) as zf:
        rec["zip_members"] = [{"name": i.filename, "size": i.file_size} for i in zf.infolist()]
        for info in zf.infolist():
            if info.is_dir():
                continue
            with zf.open(info) as stream:
                for raw in stream:
                    reader.lines += 1
                    try:
                        line = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        line = raw.decode("latin-1")
                    f = line.rstrip("\r\n").split("|")
                    reader.field_hist[len(f)] += 1
                    if len(f) > 8 and f[5].strip() in codes:
                        found[f[5].strip()][(f[7].strip(), f[8].strip())] += 1
    rec["parse"] = {"lines_read": reader.lines, "field_count_histogram": dict(reader.field_hist.most_common(5))}
    return {c: [{"descripcion": d, "clasificacion": k, "filas_isapre_plan": n} for (d, k), n in found[c].most_common(5)]
            for c in sorted(codes)}


def run(period: str, prev: str | None, out: Path, local: dict[str, Path] | None = None,
        which: Iterable[str] = ("prestaciones", "licencias"), focus: Iterable[str] = ("0405001",),
        arancel_year: str = "2026") -> dict:
    receipts: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "user_agent": UA,
                      "github_run_id": os.environ.get("GITHUB_RUN_ID"), "github_sha": os.environ.get("GITHUB_SHA"),
                      "period": period, "previous_period": prev, "files": []}
    tmp = Path(tempfile.mkdtemp(prefix="sis_agg_"))
    which = set(which)

    def fetch(dataset: str, per: str, key: str) -> tuple[Path | None, dict]:
        if local is not None:
            p = local.get(key)
            if p is None:
                return None, {"dataset": dataset, "period": per, "error": "local_missing"}
            data = p.read_bytes()
            return p, {"dataset": dataset, "period": per, "url": f"local:{p.name}", "bytes": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}
        url = discover(dataset, per)
        dest = tmp / f"{key}.zip"
        rec = {"dataset": dataset, "period": per, **download(url, dest, MAX_BYTES[dataset])}
        return (dest if "sha256" in rec else None), rec

    def drop(p: Path) -> None:
        if local is None and p.exists():
            p.unlink()

    try:
        if "prestaciones" in which:
            cur = PrestacionesAgg(focus=focus)
            p, rec = fetch("Prestaciones Bonificadas", period, f"prest_{period}")
            if p:
                process_zip(p, PREST_N, cur.add, rec)
                rec["numeric_parse_errors"] = dict(cur.err)
                drop(p)
            receipts["files"].append(rec)
            prev_agg = None
            if prev and p:
                prev_agg = PrestacionesAgg(ids_only=True)
                pp, prec = fetch("Prestaciones Bonificadas", prev, f"prest_{prev}")
                if pp:
                    process_zip(pp, PREST_N, prev_agg.add, prec)
                    drop(pp)
                else:
                    prev_agg = None
                receipts["files"].append(prec)
            if p:
                meta = {"periodo": period, "sha256_archivo": rec["sha256"], "filas": cur.rows}
                write_json(out / f"prestaciones_{period}_resumen.json", {
                    **meta, "periodos_en_archivo": dict(cur.periods.most_common(10)),
                    "filas_pertenencia_fonasa": cur.fonasa_rows,
                    "por_isapre_tipo_atencion": cur.isapre_table(), "concentracion": cur.concentration(),
                    "perfil_columnas": cur.profile.result()})
                write_json(out / f"prestaciones_{period}_precios_fonasa_region.json", {**meta, **cur.price_table()})
                write_json(out / f"prestaciones_{period}_indice_isapre_mismo_prestador.json",
                           {**meta, **cur.cross_isapre()})
                fx: dict = {**meta, "codigos": cur.focus_report()}
                ap, arec = fetch("Arancel Isapre", arancel_year, f"arancel_{arancel_year}")
                if ap:
                    fx["descripcion_arancel_isapre"] = arancel_descriptions(ap, set(focus), arec)
                    fx["sha256_arancel"] = arec["sha256"]
                    drop(ap)
                receipts["files"].append(arec)
                write_json(out / f"prestaciones_{period}_ejemplo_codigos.json", fx)
                write_json(out / f"prestaciones_{period}_consistencia_ids.json",
                           {**meta, "periodo_anterior": prev,
                            **({"sha256_archivo_anterior": prec.get("sha256")} if prev_agg else {}),
                            **id_consistency(cur, prev_agg)})
            del cur, prev_agg
        if "licencias" in which:
            lic = LicenciasAgg()
            p, rec = fetch("Licencias Medicas", period, f"lic_{period}")
            if p:
                process_zip(p, LIC_N, lic.add, rec)
                rec["numeric_parse_errors"] = dict(lic.err)
                write_json(out / f"licencias_{period}.json", {"periodo": period, "sha256_archivo": rec["sha256"],
                                                              **lic.result(), "perfil_columnas": lic.profile.result()})
                drop(p)
            receipts["files"].append(rec)
    finally:
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()
    receipts["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(out / f"receipts_{period}_{'+'.join(sorted(which))}.json", receipts)
    return receipts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="2026t2")
    ap.add_argument("--previous", default="2026t1")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--only", choices=["prestaciones", "licencias"], action="append")
    a = ap.parse_args()
    rec = run(a.period, a.previous or None, Path(a.output_dir), which=a.only or ("prestaciones", "licencias"))
    print(json.dumps([{k: f.get(k) for k in ("dataset", "period", "status", "bytes", "sha256", "error")}
                      | {"rows_ok": f.get("parse", {}).get("rows_ok"),
                         "malformed": f.get("parse", {}).get("rows_malformed")}
                      for f in rec["files"]], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
