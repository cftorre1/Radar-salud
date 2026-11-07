"""Aggregates of SIS open data: Prestaciones Bonificadas and Licencias Médicas (Dirección 5-nov-2026).

Runs in GitHub Actions (the sandbox cannot reach datos.superdesalud.gob.cl). It downloads the quarterly ZIP files
with the probe's User-Agent and robots.txt logic (fail closed), stream-processes the pipe-delimited TXT member line
by line, and writes ONLY aggregate JSON plus receipts (URL, bytes, SHA-256, row counts). No raw file, row-level data
or encrypted identifier value is ever written.

Owner rules enforced here (mandatory):
- encrypted IDs (RUN/RUT/folios) are used only as opaque grouping keys in memory; never reversed, never written;
- Licencias: aggregates only by Isapre, diagnosis group, industry, region and tipo profesional; cells < 10 records
  are suppressed;
- Prestaciones: providers only as pseudonymous keys inside aggregates. Disclosure rule (Dirección 5-nov-2026, v2):
  a region x prestación price (Fonasa-arancel codes only) is published when the cell has >= 2 distinct providers AND
  >= 30 frecuencia: the median, plus p25-p75 only with >= 3 providers. With exactly 1 provider: NO price and no
  facturado, only a concentration flag. Every provider still counts in the NATIONAL aggregate. The top provider's
  share of frecuencia is always reported as information;
- download cap 1 GiB per file; robots.txt honoured with the probe's User-Agent; ZIPs are streamed to the runner's
  temp dir and deleted after parsing.

Layout per quarter (``--period latest`` discovers the newest quarter on the SIS page; the previous quarter is always
aggregated too): ``<output-root>/<quarter>/`` with ``receipts_<q>.json`` (URL, bytes, SHA-256, rows per file) and the
aggregate JSON files. ``--skip-unchanged`` re-downloads nothing when every remote file still has the Content-Length
and Last-Modified recorded in the committed receipts (cheap daily call).
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
# Dirección 5-nov-2026: download cap 1 GiB per file (the 2026t2 Prestaciones ZIP is 458,865,683 bytes).
MAX_FILE_BYTES = 1 << 30
MAX_BYTES = {"Prestaciones Bonificadas": MAX_FILE_BYTES, "Licencias Medicas": MAX_FILE_BYTES,
             "Arancel Isapre": MAX_FILE_BYTES}
ROBOTS: dict[str, urllib.robotparser.RobotFileParser | None] = {}
SCRIPT_VERSION = "sis_open_data_agg_v11"

PRICE_MIN_PROVIDERS = 2   # a price (median) needs >= 2 distinct providers ...
PRICE_MIN_FREQ = 30       # ... and >= 30 frecuencia in the cell
IQR_MIN_PROVIDERS = 4     # p25-p75 only with >= 4 providers (with 3, p25/median/p75 reveal all three prices)
CROSS_CODE_MIN_PROVIDERS = 3  # per-code detail of the same-provider index
CROSS_MIN_FREQ = 10       # same-provider index: an Isapre enters a provider x code cell only with >= 10 frecuencia
TOP_CODES = 100           # most-billed Fonasa codes (national frecuencia) with totals and Arancel Isapre description
CHANGE_MIN_PROVIDERS = 4  # same-provider price change of a code x region: >= 4 providers present in both quarters
FUNNEL_MIN_PROVIDERS = 3  # funnel cell: >= 3 providers and >= 30 frecuencia, else folded into "otros"
TIPO_MIN_PROVIDERS = 3    # public/private price cell: >= 3 providers in the group (review of PR #152) and >= 30 frecuencia
LIC_MIN_CELL = 10
PROFILE_MIN_COUNT = 10    # a profile value is listed only when it appears in >= 10 rows
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
                # Only values seen in >= PROFILE_MIN_COUNT rows: the profile is a layout check, never a row listing.
                d["top_values"] = [[v, c] for v, c in self.values[i].most_common(self.top) if c >= PROFILE_MIN_COUNT]
            out.append(d)
        return out


# ---------------------------------------------------------------- Prestaciones
def is_fonasa(pertenencia: str) -> bool:
    return "fonasa" in norm(pertenencia)


def share_band(share: float | None) -> str | None:
    """Top-provider share of a 2-provider cell as a band (it is always >= 50)."""
    if share is None:
        return None
    return "50-60" if share <= 60 else "60-80" if share <= 80 else ">80"


def complementary_suppression(cells: dict, groups: list[list]) -> set:
    """Cells to suppress so no remainder of fewer than LIC_MIN_CELL licences can be recovered by subtraction.

    ``cells`` maps a key to its licence count; ``groups`` lists the key sets whose total is published (each
    dimension, or each row and column of a two-way table). A cell under the minimum is suppressed; then, while the
    suppressed total of a group is > 0 and < LIC_MIN_CELL, the next-smallest published cell of that group is also
    suppressed. Repeats until stable (rows and columns interact). Days and subsidy sums of the suppressed cells are
    never published, and their remainder then always covers >= LIC_MIN_CELL licences."""
    sup = {k for k, n in cells.items() if n < LIC_MIN_CELL}
    changed = True
    while changed:
        changed = False
        for g in groups:
            hidden = sum(cells[k] for k in g if k in sup)
            while 0 < hidden < LIC_MIN_CELL:
                rest = sorted((cells[k], str(k)) for k in g if k not in sup)
                if not rest:
                    break
                key = next(k for k in g if str(k) == rest[0][1] and k not in sup)
                sup.add(key)
                hidden += cells[key]
                changed = True
    return sup


def suppressed_count(n: int) -> dict:
    """A suppressed total is published only when >= LIC_MIN_CELL; otherwise '<10'."""
    if 0 < n < LIC_MIN_CELL:
        return {"licencias_en_celdas_suprimidas": None, "licencias_en_celdas_suprimidas_texto": f"<{LIC_MIN_CELL}"}
    return {"licencias_en_celdas_suprimidas": n}


MONEY_FIELDS = ("facturado", "pct_bonificado", "pct_copago")


def complementary_money(children: dict, freq: dict) -> set:
    """Children (keys) whose money fields must also be hidden so that no hidden child can be recovered as parent total
    minus the published siblings (review of PR #152). ``children`` maps key → True when its money is hidden. While
    exactly one child is hidden and another is published, the published child with the least frecuencia is hidden too."""
    extra: set = set()
    hidden = {k for k, h in children.items() if h}
    while len(hidden) == 1 and len(hidden) < len(children):
        pick = min((k for k in children if k not in hidden), key=lambda k: (freq[k], str(k)))
        hidden.add(pick)
        extra.add(pick)
    return extra


def recoverable_money(price_cols: list, price_rows: list, att_cols: list | None = None, att_rows: list | None = None) -> list[str]:
    """Leak check (review of PR #152): a hidden money cell is recoverable when it is the only hidden child of a
    published total. Region cells → the code's NACIONAL row; atencion_codigo rows → the code's NACIONAL facturado.
    Returns one entry per recoverable cell."""
    out = []
    by: dict[str, dict] = defaultdict(dict)
    for raw in price_rows:
        d = dict(zip(price_cols, raw))
        by[d["codigo_prestacion"]][d["region"]] = d
    for code, regs in by.items():
        nat = regs.get("NACIONAL")
        if not nat or nat.get("facturado") is None:
            continue
        kids = [r for r in regs if r != "NACIONAL"]
        hidden = [r for r in kids if regs[r].get("facturado") is None]
        if len(hidden) == 1 and len(kids) > 1:
            out.append(f"region:{code}:{hidden[0]}")
    if att_rows is not None:
        ab: dict[str, list] = defaultdict(list)
        for raw in att_rows:
            d = dict(zip(att_cols, raw))
            ab[d["codigo_prestacion"]].append(d)
        for code, kids in ab.items():
            hidden = [k for k in kids if k.get("facturado") is None]
            # The code total is published as soon as any total of the code is (NACIONAL price row, top codes): treat
            # every code as having a published parent, so one hidden row alone is always a leak.
            if len(hidden) == 1 and len(kids) > 1:
                out.append(f"atencion:{code}:{hidden[0]['tipo_atencion']}:{hidden[0]['tipo_prestador']}")
    return out


class PrestacionesAgg:
    def __init__(self, ids_only: bool = False, mle_codes: Iterable[str] | None = None):
        self.ids_only = ids_only
        self.mle_codes = set(mle_codes) if mle_codes is not None else None
        self.funnel: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])  # (pertenencia, atencion, en_mle, grupo)
        self.funnel_prov: dict[tuple, set] = defaultdict(set)
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
        self.price: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])  # (codigo, region, prov)
        self.cross: dict[tuple, dict] = defaultdict(dict)                         # (prov, codigo) -> isapre
        self.region_prov: dict[tuple, float] = defaultdict(float)
        self.tipo_price: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])      # (codigo, region, tipo, prov)
        self.fonasa_tot = [0.0, 0.0]                                              # facturado, frecuencia
        self.code_att: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])        # (codigo, atencion, tipo, prov)
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
        if self.mle_codes is not None:
            code = f[P_CODIGO].strip()
            inm = code in self.mle_codes
            grupo = ("pabellon" if code.startswith("00000") else code[:2]) if inm else None
            key = (f[P_PERTENENCIA].strip() or "(vacío)", atencion, inm, grupo)
            fu = self.funnel[key]
            self.funnel_prov[key].add(prov)
            fu[0] += fact; fu[1] += freq
        if prov in NO_PROVIDER:
            return
        self.region_prov[(region, prov)] += fact
        if is_fonasa(f[P_PERTENENCIA]):
            self.fonasa_rows += 1
            codigo = f[P_CODIGO].strip()
            p = self.price[(codigo, region, prov)]
            p[0] += fact; p[1] += freq; p[2] += bonif; p[3] += copago
            tp = self.tipo_price[(codigo, region, f[P_TIPO_PRESTADOR].strip() or "(vacío)", prov)]
            tp[0] += fact; tp[1] += freq
            ca = self.code_att[(codigo, atencion, f[P_TIPO_PRESTADOR].strip() or "(vacío)", prov)]
            ca[0] += freq; ca[1] += fact
            self.fonasa_tot[0] += fact; self.fonasa_tot[1] += freq
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

    def _cells(self) -> dict[tuple, list]:
        """(codigo, region|NACIONAL) -> [(unit price, freq, fact, bonif, copago)] per pseudonymous provider with
        frecuencia > 0 and facturado > 0. NACIONAL sums each provider across regions: every provider counts there,
        including the ones that are alone in their region (Dirección 5-nov-2026)."""
        cells: dict[tuple, list] = defaultdict(list)
        nat: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
        for (codigo, region, prov), v in self.price.items():
            if v[1] > 0 and v[0] > 0:
                cells[(codigo, region)].append((v[0] / v[1], v[1], v[0], v[2], v[3]))
            n = nat[(codigo, prov)]
            for k in range(4):
                n[k] += v[k]
        for (codigo, prov), v in nat.items():
            if v[1] > 0 and v[0] > 0:
                cells[(codigo, "NACIONAL")].append((v[0] / v[1], v[1], v[0], v[2], v[3]))
        return cells

    @staticmethod
    def disclose(lst: list) -> dict:
        """The disclosure rule for one region x prestación cell (Dirección 5-nov-2026, v2; review of PR #152, v3).

        With exactly 2 providers the median is published (Dirección) but facturado, % bonificado and % copago are
        null and the top share is a band ("50-60", "60-80", ">80"): median + facturado + frecuencia + exact share
        would let anyone solve both unit prices. National cells follow the same rule; system totals are untouched."""
        n, freq = len(lst), sum(x[1] for x in lst)
        out = {"n_prestadores": n, "frecuencia": round(freq),
               "share_prestador_mayor_pct": pct(max(x[1] for x in lst), freq) if lst else None}
        if n == 2:
            out["share_prestador_mayor_pct"] = share_band(out["share_prestador_mayor_pct"])
        if n >= PRICE_MIN_PROVIDERS and freq >= PRICE_MIN_FREQ:
            u = sorted(x[0] for x in lst)
            fact, bonif, cop = (sum(x[k] for x in lst) for k in (2, 3, 4))
            out.update(estado="publicable", precio_mediana=r(quantile(u, .5), 0),
                       precio_p25=r(quantile(u, .25), 0) if n >= IQR_MIN_PROVIDERS else None,
                       precio_p75=r(quantile(u, .75), 0) if n >= IQR_MIN_PROVIDERS else None,
                       facturado=round(fact) if n > 2 else None, pct_bonificado=pct(bonif, fact) if n > 2 else None,
                       pct_copago=pct(cop, fact) if n > 2 else None)
        elif n == 1:
            out.update(estado="concentracion_un_prestador", precio_mediana=None, precio_p25=None, precio_p75=None,
                       facturado=None, pct_bonificado=None, pct_copago=None)
        else:
            out.update(estado="suprimido_frecuencia_menor_30", precio_mediana=None, precio_p25=None, precio_p75=None,
                       facturado=None, pct_bonificado=None, pct_copago=None)
        return out

    PRICE_COLS = ["codigo_prestacion", "region", "estado", "n_prestadores", "frecuencia", "facturado",
                  "precio_mediana", "precio_p25", "precio_p75", "share_prestador_mayor_pct", "pct_bonificado",
                  "pct_copago", "suprimido_complementario"]

    def price_table(self) -> dict:
        rows, status, status_freq = [], Counter(), Counter()
        by_code: dict[str, dict] = defaultdict(dict)
        for (codigo, region), lst in self._cells().items():
            by_code[codigo][region] = {**self.disclose(lst), "suprimido_complementario": False}
        # Complementary suppression region → NACIONAL: national money is the sum of the regions, so a single hidden
        # regional cell would be national minus the published others (review of PR #152).
        for codigo, regs in by_code.items():
            if (regs.get("NACIONAL") or {}).get("facturado") is None:
                continue
            kids = {rg: d["facturado"] is None for rg, d in regs.items() if rg != "NACIONAL"}
            for rg in complementary_money(kids, {x: regs[x]["frecuencia"] for x in kids}):
                regs[rg].update({f: None for f in MONEY_FIELDS}, suprimido_complementario=True)
        for codigo in sorted(by_code):
            for region in sorted(by_code[codigo]):
                d = by_code[codigo][region]
                rows.append([codigo, region] + [d[c] for c in self.PRICE_COLS[2:]])
                key = (d["estado"], region == "NACIONAL")
                status[key] += 1
                status_freq[key] += d["frecuencia"]
        return {"regla": {"version": "precio_v5_complementaria",
                          "complementaria": "si en un código queda una sola celda regional sin montos, también se ocultan "
                                            "los montos de la celda publicada con menos frecuencia (suprimido_complementario)",
                          "publicable": f">= {PRICE_MIN_PROVIDERS} prestadores distintos Y >= {PRICE_MIN_FREQ} "
                                        "frecuencia: mediana del precio unitario (facturado/frecuencia por prestador, "
                                        f"no ponderada); p25-p75 sólo con >= {IQR_MIN_PROVIDERS} prestadores",
                          "concentracion": "1 prestador: sin precio ni facturado; sólo bandera de concentración",
                          "dos_prestadores": "2 prestadores: mediana sí; facturado, % bonificado y % copago nulos; share "
                                             "del mayor en banda 50-60 / 60-80 / >80",
                          "suprimido": f">= 2 prestadores con frecuencia < {PRICE_MIN_FREQ}: sin precio",
                          "nacional": "NACIONAL suma cada prestador entre regiones: todos cuentan, también los que "
                                      "están solos en su región",
                          "share": "share_prestador_mayor_pct = frecuencia del mayor prestador / frecuencia de la "
                                   "celda; se informa siempre",
                          "filtro": "pertenencia del código = Fonasa; prestadores con frecuencia>0 y facturado>0"},
                "conteo_estados": [{"estado": k[0], "nacional": k[1], "celdas": v, "frecuencia": status_freq[k]}
                                   for k, v in sorted(status.items())],
                "columns": self.PRICE_COLS, "rows": rows}

    def top_codes(self, n: int = TOP_CODES) -> list[dict]:
        """The n Fonasa codes with the most national frecuencia, with their national totals (all providers)."""
        tot: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
        for (codigo, _region, _prov), v in self.price.items():
            for k in range(4):
                tot[codigo][k] += v[k]
        ranked = sorted(tot.items(), key=lambda kv: (-kv[1][1], kv[0]))[:n]
        return [{"rank": i + 1, "codigo_prestacion": c, "frecuencia": round(v[1]), "facturado": round(v[0]),
                 "bonificado": round(v[2]), "copago": round(v[3]), "pct_bonificado": pct(v[2], v[0]),
                 "pct_copago": pct(v[3], v[0])} for i, (c, v) in enumerate(ranked)]

    def cross_isapre(self) -> dict:
        per_isapre: dict[str, dict] = defaultdict(lambda: {"bonif": [], "fact": [], "w": []})
        per_code_isapre: dict[tuple, list] = defaultdict(list)
        code_freq: Counter = Counter()
        n_cells = n_cells_multi = 0
        for (prov, codigo), by in self.cross.items():
            valid = {i: v for i, v in by.items() if v[2] >= CROSS_MIN_FREQ}
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
            if len(provs) < CROSS_CODE_MIN_PROVIDERS:
                continue
            vals = sorted(x[0] for x in lst if x[0] is not None)
            by_code.append({"codigo_prestacion": codigo, "isapre": i, "n_prestadores": len(provs),
                            "frecuencia": round(sum(x[1] for x in lst)),
                            "indice_bonif_unit_mediana_pct": r(quantile(vals, .5))})
        return {"definicion": "Por celda prestador(seudónimo) x código Fonasa atendida por >=2 Isapres: índice = "
                              "(bonificado/frecuencia de la Isapre) / (media no ponderada entre Isapres de la celda) - 1,"
                              " en %. Análogo para facturado/frecuencia. Una Isapre entra a la celda sólo con >= "
                              f"{CROSS_MIN_FREQ} de frecuencia. Detalle por código sólo con >=3 prestadores.",
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
                        "share_top3_pct": pct(sum(vals[:3]), tot), "share_top10_pct": pct(sum(vals[:10]), tot),
                        "share_top50_pct": pct(sum(vals[:50]), tot),
                        "split_tipo_prestador": {t: {"facturado": round(v[0]), "share_facturado_pct": pct(v[0], tf),
                                                     "frecuencia": round(v[1])} for t, v in sorted(tipo.items())}})
        return {"definicion": "HHI sobre facturado entre prestadores (seudónimos) de la región del prestador, escala "
                              "0-10000; top1/top3/top5/top10/top50 share de facturado. NACIONAL suma cada prestador entre regiones.",
                "regiones": out}

    def funnel_table(self) -> dict | None:
        """Coverage funnel (Dirección 6-nov-2026 20:13): all Isapre facturado and frecuencia by the SIS 'pertenencia'
        flag × tipo de atención × whether the code is in FONASA's official MLE 2026 code list (and its MLE group).
        Cells below the disclosure thresholds (< 3 providers or < 30 frecuencia) are folded into "otros", first the
        group, then the pertenencia, then into the largest cell of the same atención × en_mle; totals stay intact
        (review of PR #152, round 3)."""
        if self.mle_codes is None:
            return None
        cells = {k: [v[0], v[1], set(self.funnel_prov[k])] for k, v in self.funnel.items()}
        small = lambda c: len(c[2]) < FUNNEL_MIN_PROVIDERS or c[1] < PRICE_MIN_FREQ  # noqa: E731

        def fold(key_of) -> None:
            for k in [k for k, c in cells.items() if small(c)]:
                nk = key_of(k)
                if nk == k or k not in cells:
                    continue
                c = cells.pop(k)
                t = cells.setdefault(nk, [0.0, 0.0, set()])
                t[0] += c[0]; t[1] += c[1]; t[2] |= c[2]
        fold(lambda k: (k[0], k[1], k[2], "otros" if k[2] else None))
        fold(lambda k: ("otros", k[1], k[2], k[3]))
        for k in [k for k, c in cells.items() if small(c)]:
            peers = [p for p in cells if p != k and p[1] == k[1] and p[2] == k[2] and not small(cells[p])]
            if peers and k in cells:
                tgt = max(peers, key=lambda p: cells[p][1])
                c = cells.pop(k)
                cells[tgt][0] += c[0]; cells[tgt][1] += c[1]; cells[tgt][2] |= c[2]
        return {"definicion": "en_arancel_mle = el código de la fila está en la lista oficial del Arancel MLE 2026 de "
                              "FONASA; pertenencia = campo 16 del archivo SIS; celdas con < 3 prestadores o < 30 de "
                              "frecuencia agrupadas en «otros»", "codigos_mle": len(self.mle_codes),
                # "celdas", not "filas": the file's metadata keeps "filas" = rows read from the ZIP (v9 fix).
                "celdas": [{"pertenencia": p, "tipo_atencion": a, "en_arancel_mle": m, "grupo_mle": g,
                            "facturado": round(v[0]), "frecuencia": round(v[1]), "prestadores_min_3": len(v[2]) >= FUNNEL_MIN_PROVIDERS}
                           for (p, a, m, g), v in sorted(cells.items(), key=str)]}

    def fonasa_totals(self) -> dict:
        """System totals of Fonasa-arancel codes (all providers, all regions): the denominator of basket coverage."""
        return {"facturado_fonasa": round(self.fonasa_tot[0]), "frecuencia_fonasa": round(self.fonasa_tot[1])}

    def atencion_table(self) -> dict:
        """Fonasa-arancel codes by tipo de atención (field 20 of the SIS file: ambulatoria / hospitalaria) and tipo de
        prestador, nationally (Dirección 6-nov-2026 20:09): per (code, atención, tipo) frecuencia and number of providers;
        facturado only with >= 3 providers. System totals per (atención, tipo) are not suppressed."""
        cells: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0])
        tot: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])
        for (codigo, att, tipo, _prov), (freq, fact) in self.code_att.items():
            c = cells[(codigo, att, tipo)]
            c[0] += freq; c[1] += fact; c[2] += 1
            t = tot[(att, tipo)]
            t[0] += freq; t[1] += fact
        cols = ["codigo_prestacion", "tipo_atencion", "tipo_prestador", "n_prestadores", "frecuencia", "facturado"]
        hid = {key: v[2] < IQR_MIN_PROVIDERS - 1 for key, v in cells.items()}
        by_code: dict[str, dict] = defaultdict(dict)
        for key in cells:
            by_code[key[0]][key] = hid[key]
        for code, kids in by_code.items():  # complementary suppression against the code total (review of PR #152)
            for key in complementary_money(kids, {x: cells[x][0] for x in kids}):
                hid[key] = True
        rows = [[c, a, t, v[2], round(v[0]), None if hid[(c, a, t)] else round(v[1])]
                for (c, a, t), v in sorted(cells.items())]
        return {"regla": "facturado por código sólo con >= 3 prestadores y supresión complementaria contra el total del "
                         "código; totales del sistema sin supresión",
                "totales": [{"tipo_atencion": a, "tipo_prestador": t, "frecuencia": round(v[0]), "facturado": round(v[1])}
                            for (a, t), v in sorted(tot.items())],
                "columns": cols, "rows": rows}

    def tipo_table(self) -> dict:
        """Public vs private prices of the same code and region (Dirección 6-nov-2026): per (code, region|NACIONAL,
        tipo de prestador) the median unit price among providers, under the disclosure rule (>= 2 providers and >= 30
        frecuencia; 1 provider: no price; 2 providers: no facturado). Unit price = facturado / frecuencia."""
        cells: dict[tuple, list] = defaultdict(list)
        nat: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])
        for (codigo, region, tipo, prov), (fact, freq) in self.tipo_price.items():
            if freq > 0 and fact > 0:
                cells[(codigo, region, tipo)].append((fact / freq, freq))
            n = nat[(codigo, tipo, prov)]
            n[0] += fact; n[1] += freq
        for (codigo, tipo, prov), (fact, freq) in nat.items():
            if freq > 0 and fact > 0:
                cells[(codigo, "NACIONAL", tipo)].append((fact / freq, freq))
        cols = ["codigo_prestacion", "region", "tipo_prestador", "n_prestadores", "frecuencia", "precio_mediana"]
        provs: dict[tuple, set] = defaultdict(set)
        for (codigo, region, tipo, prov), (fact, freq) in self.tipo_price.items():
            if freq > 0 and fact > 0:
                provs[(region, tipo)].add(prov)
        rows = []
        for (codigo, region, tipo), lst in sorted(cells.items()):
            n, freq = len(lst), sum(x[1] for x in lst)
            ok = n >= TIPO_MIN_PROVIDERS and freq >= PRICE_MIN_FREQ
            rows.append([codigo, region, tipo, n, round(freq), r(quantile(sorted(x[0] for x in lst), .5), 0) if ok else None])
        return {"regla": f"mediana con >= {TIPO_MIN_PROVIDERS} prestadores del grupo y >= {PRICE_MIN_FREQ} frecuencia; si no, nula",
                "prestadores_por_region": [{"region": rg, "tipo_prestador": t, "prestadores": len(v)}
                                           for (rg, t), v in sorted(provs.items())],
                "columns": cols, "rows": rows}

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


def price_change(cur: PrestacionesAgg, prev_price: dict) -> dict:
    """Same-provider price change between quarters (Dirección 6-nov-2026). For each (code, region|NACIONAL), only the
    pseudonymous providers with frecuencia > 0 and facturado > 0 in BOTH quarters: a fixed-quantity (Laspeyres) index
    Σ q_prev·p_cur / Σ q_prev·p_prev − 1 and the median of the providers' price relatives p_cur/p_prev − 1. Published
    only with >= CHANGE_MIN_PROVIDERS matched providers and >= PRICE_MIN_FREQ previous frecuencia; never per provider."""
    def per(price: dict) -> dict:
        out: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])
        for (codigo, region, prov), v in price.items():
            for key in ((codigo, region, prov), (codigo, "NACIONAL", prov)):
                out[key][0] += v[0]; out[key][1] += v[1]
        return out
    a, b = per(prev_price), per(cur.price)
    cells: dict[tuple, list] = defaultdict(list)
    for key, (f0, q0) in a.items():
        f1, q1 = b.get(key, (0.0, 0.0))
        if f0 > 0 and q0 > 0 and f1 > 0 and q1 > 0:
            cells[(key[0], key[1])].append((f0 / q0, f1 / q1, q0, q1))
    cols = ["codigo_prestacion", "region", "n_prestadores_ambos", "frecuencia_anterior", "frecuencia_actual",
            "indice_laspeyres_pct", "mediana_relativos_pct"]
    rows = []
    for (codigo, region), lst in sorted(cells.items()):
        n, q0 = len(lst), sum(x[2] for x in lst)
        if n < CHANGE_MIN_PROVIDERS or q0 < PRICE_MIN_FREQ:
            continue
        las = sum(x[2] * x[1] for x in lst) / sum(x[2] * x[0] for x in lst) - 1
        rel = sorted(x[1] / x[0] - 1 for x in lst)
        rows.append([codigo, region, n, round(q0), round(sum(x[3] for x in lst)), r(las * 100), r(quantile(rel, .5) * 100)])
    return {"definicion": "mismos prestadores seudónimos en ambos trimestres; índice de cantidades fijas del trimestre "
                          f"anterior y mediana de relativos; >= {CHANGE_MIN_PROVIDERS} prestadores y >= {PRICE_MIN_FREQ} "
                          "frecuencia anterior", "columns": cols, "rows": rows}


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
        # Two-way cell Isapre x diagnosis group (both allowed dimensions; same minimum cell).
        self.isapre_diag: dict[tuple, LicGroup] = defaultdict(LicGroup)
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
        groups.append(self.isapre_diag[(f[L_ISAPRE].strip() or "(vacío)", f[L_DIAG].strip() or "(vacío)")])
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
        d = {"grupo": key, "licencias": g.n, "rechazadas": g.kinds["rechazada"], "reducidas": g.kinds["reducida"],
             "pct_rechazadas": pct(g.kinds["rechazada"], g.n),
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
        out["regla_supresion"] = ("celda < 10 suprimida; supresión complementaria: si lo suprimido de un grupo publicado "
                                  "suma entre 1 y 9 licencias, se suprime también la celda publicada más chica hasta "
                                  "llegar a >= 10 (por dimensión; en el cruce, por Isapre y por diagnóstico)")
        for dim, groups in self.groups.items():
            sup = complementary_suppression({k: g.n for k, g in groups.items()}, [list(groups)])
            rows = [self.row(k, g) for k, g in sorted(groups.items(), key=lambda kv: -kv[1].n) if k not in sup]
            out["breakdowns"][dim] = {"filas": rows, "celdas_suprimidas": len(sup),
                                      **suppressed_count(sum(groups[k].n for k in sup))}
        cells = self.isapre_diag
        published_isapres = {r["grupo"] for r in out["breakdowns"]["isapre"]["filas"]}
        published_diags = {r["grupo"] for r in out["breakdowns"]["diagnostico"]["filas"]}
        # Row totals (Isapre) and column totals (diagnosis) are published in the breakdowns, and so is the grand total.
        by_i = [[k for k in cells if k[0] == i] for i in published_isapres]
        by_d = [[k for k in cells if k[1] == d] for d in published_diags]
        sup = complementary_suppression({k: g.n for k, g in cells.items()}, by_i + by_d + [list(cells)])
        out["cruces"] = {"isapre_x_diagnostico": {
            "filas": [{**self.row(f"{i}|{d}", g), "isapre": i, "diagnostico": d}
                      for (i, d), g in sorted(cells.items(), key=lambda kv: (kv[0][0], -kv[1].n)) if (i, d) not in sup],
            "celdas_suprimidas": len(sup), **suppressed_count(sum(cells[k].n for k in sup))}}
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


FILE_RX = re.compile(r"/([A-Za-z_]+)_(\d{4})t([1-4])\.zip$", re.I)


def page_links() -> list[str]:
    """Links of the SIS open-data page that point to the file host (robots.txt honoured; [] on any failure)."""
    try:
        ok, _ = allowed(PAGE)
        if not ok:
            return []
        st, body, _ = get(PAGE, limit=8 * 1024 * 1024, timeout=60)
    except (URLError, OSError, ValueError):
        return []
    if st != 200:
        return []
    out = []
    for m in re.findall(r'href=["\']([^"\']+)["\']', body.decode("utf-8", "replace")):
        u = urljoin(PAGE, html.unescape(m))
        if urlparse(u).netloc == FILE_HOST:
            out.append(u)
    return out


def quarter_key(q: str) -> int:
    m = QUARTER.match(q)
    if not m:
        raise ValueError(f"invalid_quarter:{q}")
    return int(m.group(1)) * 4 + int(m.group(2)) - 1


def previous_quarter(q: str) -> str:
    k = quarter_key(q) - 1
    return f"{k // 4}t{k % 4 + 1}"


def latest_quarter(links: list[str], dataset: str = "Prestaciones Bonificadas") -> str | None:
    """Newest quarter for which the SIS page links a ``<Dataset>_<yyyy>t<q>.zip`` file; never guessed."""
    want = dataset.replace(" ", "_").lower()
    qs = []
    for u in links:
        m = FILE_RX.search(unquote(u))
        if m and m.group(1).lower() == want:
            qs.append(f"{m.group(2)}t{m.group(3)}")
    return max(qs, key=quarter_key) if qs else None


def discover(dataset: str, period: str, links: list[str] | None = None) -> str:
    """URL from the SIS page links; falls back to the probe-observed pattern."""
    fname = f"{dataset.replace(' ', '_')}_{period}.zip"
    for u in (page_links() if links is None else links):
        if unquote(u).lower().endswith("/" + fname.lower()):
            return u
    return f"https://{FILE_HOST}/archivos/{quote(dataset)}/{period[:4]}/{fname}"


def head(url: str) -> dict:
    """Content-Length and Last-Modified of a remote file (robots.txt honoured), to skip unchanged files."""
    ok, why = allowed(url)
    if not ok:
        return {"error": why}
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}, method="HEAD"), timeout=60) as resp:
            return {"content_length": resp.headers.get("Content-Length"), "last_modified": resp.headers.get("Last-Modified")}
    except HTTPError as e:
        return {"error": f"http_{e.code}"}
    except (URLError, OSError, ValueError) as e:
        return {"error": f"{type(e).__name__}"}


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


DATASETS = (("Prestaciones Bonificadas", "prest"), ("Licencias Medicas", "lic"))


MLE_REFERENCE = Path(__file__).resolve().parents[1] / "data" / "reference" / "fonasa_mle_2026.json"
def aggregate_quarter(period: str, out: Path, fetch, drop, prev_ids: "PrestacionesAgg | None" = None,
                      prev_period: str | None = None, which: Iterable[str] = ("prestaciones", "licencias"),
                      mle_codes: Iterable[str] | None = None):
    """Full aggregates of one quarter into ``out``. Returns (receipts, provider-id aggregate for the next quarter)."""
    receipts: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "script_version": SCRIPT_VERSION,
                      "user_agent": UA, "max_file_bytes": MAX_FILE_BYTES,
                      "github_run_id": os.environ.get("GITHUB_RUN_ID"), "github_sha": os.environ.get("GITHUB_SHA"),
                      "period": period, "files": []}
    ids = None
    which = set(which)
    if "prestaciones" in which:
        cur = PrestacionesAgg(mle_codes=mle_codes)
        p, rec = fetch("Prestaciones Bonificadas", period, f"prest_{period}")
        if p:
            process_zip(p, PREST_N, cur.add, rec)
            rec["numeric_parse_errors"] = dict(cur.err)
            drop(p)
        receipts["files"].append(rec)
        if p:
            meta = {"periodo": period, "script_version": SCRIPT_VERSION, "sha256_archivo": rec["sha256"],
                    "filas": cur.rows}
            write_json(out / f"prestaciones_{period}_resumen.json", {
                **meta, "periodos_en_archivo": dict(cur.periods.most_common(10)),
                "filas_pertenencia_fonasa": cur.fonasa_rows,
                "por_isapre_tipo_atencion": cur.isapre_table(), "concentracion": cur.concentration(),
                "totales_fonasa": cur.fonasa_totals(),
                "perfil_columnas": cur.profile.result()})
            write_json(out / f"prestaciones_{period}_precios_fonasa_region.json", {**meta, **cur.price_table()})
            write_json(out / f"prestaciones_{period}_indice_isapre_mismo_prestador.json", {**meta, **cur.cross_isapre()})
            write_json(out / f"prestaciones_{period}_precios_tipo_prestador.json", {**meta, **cur.tipo_table()})
            write_json(out / f"prestaciones_{period}_atencion_codigo.json", {**meta, **cur.atencion_table()})
            if cur.mle_codes is not None:
                write_json(out / f"prestaciones_{period}_embudo_arancel_mle.json", {**meta, **cur.funnel_table()})
            if prev_ids is not None and getattr(prev_ids, "price", None):
                write_json(out / f"prestaciones_{period}_cambio_mismo_prestador.json",
                           {**meta, "periodo_anterior": prev_period, **price_change(cur, prev_ids.price)})
            top = cur.top_codes()
            tx: dict = {**meta, "criterio": f"los {TOP_CODES} códigos Fonasa con más frecuencia nacional (todos los "
                                            "prestadores)", "codigos": top}
            ap, arec = fetch("Arancel Isapre", period[:4], f"arancel_{period[:4]}")
            if ap:
                desc = arancel_descriptions(ap, {c["codigo_prestacion"] for c in top}, arec)
                for c in top:
                    c["descripcion_arancel_isapre"] = desc.get(c["codigo_prestacion"]) or []
                tx["sha256_arancel"] = arec["sha256"]
                drop(ap)
            receipts["files"].append(arec)
            write_json(out / f"prestaciones_{period}_top_codigos.json", tx)
            if prev_ids is not None:
                write_json(out / f"prestaciones_{period}_consistencia_ids.json",
                           {**meta, "periodo_anterior": prev_period, **id_consistency(cur, prev_ids)})
            ids = PrestacionesAgg(ids_only=True)  # keep only the pseudonymous-ID sets for the next quarter
            ids.prov_isapres, ids.prov_fact, ids.prov_rows, ids.rows = cur.prov_isapres, cur.prov_fact, cur.prov_rows, cur.rows
            ids.price = cur.price  # provider x code x region (fact, freq, ...) for the next quarter's same-provider change
        del cur
    if "licencias" in which:
        lic = LicenciasAgg()
        p, rec = fetch("Licencias Medicas", period, f"lic_{period}")
        if p:
            process_zip(p, LIC_N, lic.add, rec)
            rec["numeric_parse_errors"] = dict(lic.err)
            write_json(out / f"licencias_{period}.json", {"periodo": period, "script_version": SCRIPT_VERSION,
                                                          "sha256_archivo": rec["sha256"], "filas": rec["parse"]["rows_ok"],
                                                          **lic.result(), "perfil_columnas": lic.profile.result()})
            drop(p)
        receipts["files"].append(rec)
    receipts["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(out / f"receipts_{period}.json", receipts)
    return receipts, ids


def unchanged(out_root: Path, quarters: list[str], links: list[str] | None) -> bool:
    """True when every remote file of every quarter still has the Content-Length and Last-Modified recorded in the
    committed receipts written by this script version (no download needed)."""
    for q in quarters:
        try:
            rec = json.loads((out_root / q / f"receipts_{q}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if rec.get("script_version") != SCRIPT_VERSION:
            return False
        by = {(f.get("dataset"), f.get("period")): f for f in rec.get("files") or []}
        for dataset, _ in DATASETS:
            old = by.get((dataset, q)) or {}
            if not old.get("sha256"):
                return False
            now = head(discover(dataset, q, links))
            if now.get("error") or now.get("content_length") != old.get("content_length") \
                    or now.get("last_modified") != old.get("last_modified"):
                return False
    return True


def run(period: str, prev: str | None, out_root: Path, local: dict[str, Path] | None = None,
        which: Iterable[str] = ("prestaciones", "licencias"), links: list[str] | None = None) -> dict:
    """Aggregates ``prev`` (if any) and then ``period``, each into ``out_root/<quarter>/``. When the MLE code table
    (``out_root/arancel_mle/arancel_mle_2026.json``) exists, the coverage funnel is computed against it."""
    mle = None
    try:  # FONASA's official MLE 2026 code list (incl. pabellón 0000001-0000014), parsed by scripts/fonasa_mle.py
        mle = list(json.loads(MLE_REFERENCE.read_text(encoding="utf-8"))["codigos"])
    except (OSError, ValueError, KeyError):
        pass
    tmp = Path(tempfile.mkdtemp(prefix="sis_agg_"))

    def fetch(dataset: str, per: str, key: str) -> tuple[Path | None, dict]:
        if local is not None:
            p = local.get(key)
            if p is None:
                return None, {"dataset": dataset, "period": per, "error": "local_missing"}
            data = p.read_bytes()
            return p, {"dataset": dataset, "period": per, "url": f"local:{p.name}", "bytes": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}
        url = discover(dataset, per, links)
        dest = tmp / f"{key}.zip"
        rec = {"dataset": dataset, "period": per, **download(url, dest, MAX_BYTES[dataset])}
        if "sha256" not in rec and dest.exists():
            dest.unlink()  # a partial or refused download is never kept
        return (dest if "sha256" in rec else None), rec

    def drop(p: Path) -> None:
        if local is None and p.exists():
            p.unlink()

    out: dict = {}
    try:
        ids = None
        for q in ([prev] if prev else []) + [period]:
            rec, ids = aggregate_quarter(q, out_root / q, fetch, drop, prev_ids=ids if q == period else None,
                                         prev_period=prev if q == period else None, which=which, mle_codes=mle)
            out[q] = rec
    finally:
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="latest", help="'latest' (newest quarter linked on the SIS page) or yyyytq")
    ap.add_argument("--previous", default="auto", help="'auto' (the quarter before), '' (none) or yyyytq")
    ap.add_argument("--output-root", required=True, help="quarters are written to <output-root>/<quarter>/")
    ap.add_argument("--only", choices=["prestaciones", "licencias"], action="append")
    ap.add_argument("--skip-unchanged", action="store_true",
                    help="download nothing when the committed receipts still match the remote files")
    a = ap.parse_args()
    links = page_links()
    period = latest_quarter(links) if a.period == "latest" else a.period
    if not period:
        raise SystemExit("no quarter linked on the SIS page (robots, network or layout): nothing is guessed")
    prev = previous_quarter(period) if a.previous == "auto" else (a.previous or None)
    quarters = [q for q in (prev, period) if q]
    out_root = Path(a.output_root)
    if a.skip_unchanged and unchanged(out_root, quarters, links):
        print(json.dumps({"status": "unchanged", "quarters": quarters}))
        return
    recs = run(period, prev, out_root, which=a.only or ("prestaciones", "licencias"), links=links)
    print(json.dumps({q: [{k: f.get(k) for k in ("dataset", "period", "status", "bytes", "sha256", "error")}
                          | {"rows_ok": f.get("parse", {}).get("rows_ok"),
                             "malformed": f.get("parse", {}).get("rows_malformed")}
                          for f in rec["files"]] for q, rec in recs.items()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
