"""Backfill histórico de Prestaciones Bonificadas SIS (Dirección aprobó el backfill, 6-nov-2026).

Procesa un bloque de trimestres consecutivos (``--quarters 2025t1,2025t2,...``) más un trimestre de calentamiento
anterior, que sólo se usa en memoria para los relativos de precio y la persistencia de PAM del primer trimestre del
bloque. Por trimestre escribe SÓLO agregados en ``data/sis_open_data_history/<q>/``:

- ``indice_precios_<q-1>_<q>.json``: relativos de precio mismo prestador / mismo código entre trimestres
  consecutivos, por código x región x tipo de atención (y NACIONAL), más agregados por grupo MLE y tipo de atención.
- ``ges_gpp_<q>.json``: gasto, frecuencia y casos distintos por problema GES (prefijo de codigo_gpp), Isapre y región,
  con familias; celdas con >= 10 casos y supresión complementaria.
- ``folios_probe_<q>.json``: sólo conteos y razones sobre el PAM principal (campo 14 del Compendio).
- ``especialidades_v0_<q>.json``: EXPERIMENTAL. Episodios (Isapre, PAM principal) con especialidad asignada por
  trazadoras; celdas con >= 10 episodios y >= 3 prestadores.
- ``receipts_<q>.json``: URL, bytes, SHA-256, filas, chequeo de esquema, tiempos.

Reglas (CLAUDE.md y Dirección): los identificadores cifrados (RUN beneficiario, RUT prestador, folios, id GES) son
llaves opacas que viven sólo en memoria; nunca se revierten ni se escriben, ni siquiera como hash. Las descargas
reutilizan la lógica del agregador (robots.txt, User-Agent, tope 1 GiB, streaming) y se borran tras el parseo.

Mapeo de campos: el archivo público trae 30 campos, un subconjunto del Archivo Maestro (35 campos vigentes,
Compendio SIS 07.09.2026, Título V). Se omiten DV beneficiario (05), DV prestador (10), comuna (12), identificación
del plan (22) y horario (31), así que: público 10 = maestro 13 (prestador preferente), 11 = 14 (PAM principal),
12 = 15 (PAM complementario), 13 = 16 (bono), 14 = 17 (reembolso), 29 = 34 (GPP) y 30 = 35 (id GES). Los índices
0-based vienen de ``aggregate_sis_open_data`` (P_FOLIOS, P_GPP, P_GES). Un trimestre cuyo esquema no calce con ese
mapeo se omite con la razón registrada; nunca se adivina.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_sis_open_data as base  # noqa: E402  (robots, tope 1 GiB, streaming, RowReader)

SCRIPT_VERSION = "sis_historico_v2"
ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "data" / "sis_open_data_history"
GES_REF = ROOT / "data" / "reference" / "ges_problemas_ds29_2025.json"
DATASET = "Prestaciones Bonificadas"

# Índices 0-based del archivo público (de aggregate_sis_open_data; no se redefinen).
I_ISAPRE, I_TIPO_REG, I_BEN, I_PREST, I_REGION = base.P_ISAPRE, base.P_TIPO_REG, base.P_RUN_BEN, base.P_PRESTADOR, base.P_REGION
I_PAM, I_PAM_COMPL, I_BONO, I_REEMB = base.P_FOLIOS
I_CODIGO, I_PERT, I_COB, I_ATN = base.P_CODIGO, base.P_PERTENENCIA, base.P_COBERTURA, base.P_TIPO_ATENCION
I_FREC, I_FACT, I_BONIF, I_GPP, I_GES = base.P_FREC, base.P_FACT, base.P_BONIF, base.P_GPP, base.P_GES
NO_PROVIDER = base.NO_PROVIDER

# Divulgación
REL_MIN_PROVIDERS = 3        # relativos: con 2 prestadores, cada uno despejaría el relativo del otro desde la mediana
REL_MIN_PREV_FREQ = base.PRICE_MIN_FREQ  # >= 30 de frecuencia en el trimestre anterior, como cambio_mismo_prestador
REL_TRIM = (0.2, 5.0)        # relativos fuera de [0,2; 5] se excluyen sólo en la versión recortada de los agregados
GES_MIN_CASES = 10
SPEC_MIN_EPISODES = 10
SPEC_MIN_PROVIDERS = 3
SPEC_MAX_TOP_SHARE = 80.0    # memo 2.2.5: ningún prestador con > 80 % de los episodios de la celda
IQR_MIN_PROVIDERS = base.IQR_MIN_PROVIDERS
MULTI_SPEC_RATIO = 0.8       # segunda especialidad con valor MLE >= 80 % de la primera -> multiespecialidad
PLACEHOLDER_MIN_ROWS = 5000  # un valor de PAM con >= 5.000 filas es el marcador "sin PAM" (valor 0 cifrado)
MAX_PAMS = 9_000_000         # tope de memoria; si se supera, el probe lo informa y el episodio no es válido
SCHEMA_MAX_UNKNOWN_PCT = 0.5
SCHEMA_MAX_MALFORMED_PCT = 1.0

# Vocabularios del Compendio (códigos numéricos) y del archivo público 2026 (texto).
ATN = {"atencion ambulatoria": "Ambulatoria", "ambulatoria": "Ambulatoria", "ambulatorio": "Ambulatoria",
       "1": "Ambulatoria", "atencion hospitalaria": "Hospitalaria", "hospitalaria": "Hospitalaria",
       "hospitalario": "Hospitalaria", "2": "Hospitalaria"}
PERT = {"fonasa": "fonasa", "1": "fonasa", "asegurador": "asegurador", "2": "asegurador",
        "superintendencia": "superintendencia", "3": "superintendencia",
        "listado prestaciones especificas vigente ges": "lep_ges", "4": "lep_ges"}
COB = {"ges": "ges", "1": "ges", "caec": "caec", "2": "caec", "ges-caec": "ges_caec", "3": "ges_caec",
       "plan complementario": "plan_complementario", "4": "plan_complementario", "no bonificado": "no_bonificado",
       "5": "no_bonificado", "otro": "otro", "6": "otro"}
TREG = {"curativa": "curativa", "1": "curativa", "examen medicina preventiva": "preventiva",
        "examen de medicina preventiva": "preventiva", "2": "preventiva",
        "proteccion a la mujer embarazada": "embarazada", "3": "embarazada",
        "control del nino sano": "nino_sano", "4": "nino_sano"}
# ICSA (memoria de cálculo 2025, tabla AMPB): curativa, facturado > 0, códigos MLE, cobertura CAEC / GES-CAEC / Plan
# Complementario ("se excluye al financiamiento GES").
INDEX_COB = {"caec", "ges_caec", "plan_complementario"}
GPP_RX = re.compile(r"^(\d{1,3})([A-Za-z])(\d{0,4})$")

# ---------------------------------------------------------------- especialidades (memo nuevos_analisis.md 2.3 y 2.4)
SPECIALTIES = {
    "traumatologia": "Traumatología y ortopedia", "columna_neurocirugia": "Columna / neurocirugía",
    "cirugia_digestiva": "Cirugía digestiva / general", "bariatrica": "Cirugía bariátrica",
    "gastro_endoscopica": "Gastroenterología endoscópica", "obstetricia": "Obstetricia",
    "ginecologia": "Ginecología", "mama": "Mama", "urologia": "Urología", "nefrologia": "Nefrología / diálisis",
    "cardio_intervencional": "Cardiología intervencional", "cirugia_cardiovascular": "Cirugía cardiovascular y vascular",
    "torax": "Tórax y broncopulmonar", "oftalmologia": "Oftalmología", "otorrino": "Otorrinolaringología",
    "cabeza_cuello": "Cabeza y cuello / endocrina quirúrgica", "oncologia": "Oncología (quimio y radioterapia)",
    "salud_mental": "Salud mental", "neonatologia_pediatria": "Neonatología y pediatría hospitalaria",
    "medicina_interna": "Medicina interna / médico sin cirugía", "uci_adulto": "Cuidados intensivos adulto",
    "dermatologia_plastica": "Dermatología / plástica",
    "multiespecialidad": "Multiespecialidad (trazadoras de especialidades distintas con valor similar)",
    "sin_clasificar": "Sin trazadora ni día cama clasificable",
}
# Prefijo grupo+subgrupo MLE (4 dígitos) -> especialidad.
TRACER_PREFIX = {
    "2104": "traumatologia", "2105": "traumatologia", "2106": "traumatologia", "2107": "traumatologia",
    "1103": "columna_neurocirugia", "1802": "cirugia_digestiva", "1803": "cirugia_digestiva",
    "1801": "gastro_endoscopica", "2004": "obstetricia", "2001": "ginecologia", "2003": "ginecologia",
    "2002": "mama", "1902": "urologia", "1901": "nefrologia", "1701": "cardio_intervencional",
    "1703": "cirugia_cardiovascular", "1704": "torax", "1707": "torax", "1202": "oftalmologia",
    "1302": "otorrino", "1402": "cabeza_cuello", "2908": "oncologia", "2902": "oncologia", "2905": "oncologia",
    "0901": "salud_mental", "0902": "salud_mental", "1502": "dermatologia_plastica",
    "1601": "dermatologia_plastica", "1602": "dermatologia_plastica",
}
# Códigos puntuales (ganan sobre el prefijo): trazadoras del memo 2.4 y PAD 2501/33xx.
TRACER_CODE = {
    "1802158": "bariatrica", "1802159": "bariatrica", "2501058": "bariatrica", "2501059": "bariatrica",
    "0402022": "cardio_intervencional", "0101212": "salud_mental", "0101213": "salud_mental",
    "2501001": "cirugia_digestiva", "2501004": "cirugia_digestiva", "2501005": "cirugia_digestiva",
    "2501009": "obstetricia", "2501021": "oftalmologia", "2501030": "columna_neurocirugia",
    "2501031": "nefrologia", "2501032": "nefrologia", "2501034": "ginecologia", "2501035": "traumatologia",
    "2501038": "traumatologia", "2501051": "cabeza_cuello", "2501052": "cabeza_cuello",
    "3301001": "traumatologia", "3301002": "traumatologia", "3302001": "traumatologia",
    "3302002": "traumatologia", "3303001": "traumatologia",
}
# Respaldo sin trazadora: día cama especial, por prioridad (menor gana).
CAMA_RANK = {"0201405": (0, "salud_mental"), "0201406": (0, "salud_mental"),
             "0201401": (1, "obstetricia"), "0201402": (1, "obstetricia"),
             "0201203": (2, "neonatologia_pediatria"), "0201303": (2, "neonatologia_pediatria"),
             "0201403": (2, "neonatologia_pediatria"), "0201404": (2, "neonatologia_pediatria"),
             "0201202": (2, "neonatologia_pediatria"), "0201302": (2, "neonatologia_pediatria"),
             "0201201": (3, "uci_adulto"), "0201301": (3, "uci_adulto"),
             "0201001": (4, "medicina_interna"), "0201002": (4, "medicina_interna"),
             "0201101": (4, "medicina_interna"), "0201102": (4, "medicina_interna")}
CAMA_BY_RANK = {rank: spec for rank, spec in CAMA_RANK.values()}


def tracer_specialty(code: str) -> str | None:
    return TRACER_CODE.get(code) or TRACER_PREFIX.get(code[:4])


def load_mle_values(path: Path = base.MLE_REFERENCE) -> dict[str, float]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))["codigos"]
    except (OSError, ValueError, KeyError):
        return {}
    return {c: float(v.get("nivel1_total") or 0) for c, v in d.items()}


def load_ges_reference(path: Path = GES_REF) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    fam_of = {int(p): f for f, ps in d["familias"].items() for p in ps}
    return {"names": {int(k): v for k, v in d["problemas"].items()}, "family": fam_of, "fuentes": d["fuentes"]}


def parse_gpp(gpp: str) -> tuple[int, str] | None:
    """'21T1' -> (21, 'T'); 'X' o vacío -> None. El prefijo numérico es el n° de problema (Compendio, campo 34)."""
    m = GPP_RX.match(gpp.strip())
    if not m:
        return None
    return int(m.group(1)), m.group(2).upper()


def _norm_cached(cache: dict, vocab: dict, raw: str) -> str | None:
    try:
        return cache[raw]
    except KeyError:
        n = base.norm(raw)
        v = vocab.get(n)
        if v is None:
            for k, val in vocab.items():  # prefijos de texto largo ("protección a la mujer embarazada y hasta...")
                if not k.isdigit() and n.startswith(k):
                    v = val
                    break
        cache[raw] = v
        return v


def quantile(vals: list[float], q: float) -> float | None:
    return base.quantile(vals, q)


def r(x, nd=2):
    return base.r(x, nd)


def pct(a, b):
    return base.pct(a, b)


def share_band(s):
    return base.share_band(s)


def complementary(sizes: dict, initial: set, groups: list[list], min_hidden: int) -> set:
    """Supresión complementaria genérica: parte de ``initial`` y, mientras un grupo publicado tenga un remanente
    oculto entre 1 y min_hidden-1, suprime la celda publicada más pequeña del grupo. Repite hasta estabilizar."""
    sup = set(initial)
    changed = True
    while changed:
        changed = False
        for g in groups:
            hidden = sum(sizes[k] for k in g if k in sup)
            n_hidden = sum(1 for k in g if k in sup)
            # un único oculto en un grupo con total publicado se despeja por resta aunque sea >= min_hidden
            while (0 < hidden < min_hidden) or n_hidden == 1:
                rest = sorted((sizes[k], str(k)) for k in g if k not in sup)
                if not rest:
                    break
                key = next(k for k in g if str(k) == rest[0][1] and k not in sup)
                sup.add(key)
                hidden += sizes[key]
                n_hidden += 1
                changed = True
    return sup


# ---------------------------------------------------------------- agregador por trimestre
class QuarterAgg:
    """Un trimestre. ``warmup=True`` sólo junta precios por prestador y llaves de PAM (para el trimestre siguiente)."""

    def __init__(self, mle_values: dict[str, float] | None = None, warmup: bool = False,
                 max_pams: int = MAX_PAMS, placeholder_min_rows: int = PLACEHOLDER_MIN_ROWS):
        self.warmup = warmup
        self.mle = mle_values or {}
        self.max_pams, self.placeholder_min_rows = max_pams, placeholder_min_rows
        self.rows = 0
        self.err: Counter = Counter()
        self.unknown: dict[str, Counter] = defaultdict(Counter)
        self._c_atn: dict = {}; self._c_pert: dict = {}; self._c_cob: dict = {}; self._c_treg: dict = {}
        self._c_tracer: dict = {}
        # índice de precios: (prov, codigo, region, atencion) -> [facturado, frecuencia, bonificado]
        self.price: dict[tuple, list] = {}
        # canasta ICSA: (codigo, atencion) -> [bonificado, frecuencia, facturado, prestadores]
        self.code_tot: dict[tuple, list] = {}
        self.scope = Counter()        # facturado por alcance del índice
        self.tot_atn: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0])  # fact, bonif, frec, filas
        # PAM: (isapre, folio) -> [filas, ben, flags, codigo, prov, fact, bonif, trazadoras, cama_rank, filas_hosp]
        self.pams: dict[tuple, list] = {}
        self.pam_overflow = 0
        self.rows_pam_literal_zero: Counter = Counter()
        self.rows_compl: Counter = Counter()
        # GES
        self.ges: dict[tuple, list] = {}      # (problema, isapre, region) -> [fact, bonif, frec, casos, prov]
        self.ges_letter: dict[tuple, list] = {}
        self.ges_tot = [0.0, 0.0, 0.0, 0]     # fact, bonif, frec, filas con GPP parseable
        self.ges_sin_gpp = [0.0, 0]           # cobertura GES con GPP 'X'
        self.ges_sin_id = 0
        self.gpp_unparsed: Counter = Counter()

    # -- normalizadores con caché (valores categóricos no sensibles)
    def _atn(self, raw):
        v = _norm_cached(self._c_atn, ATN, raw)
        if v is None:
            self.unknown["tipo_atencion"][raw.strip()[:40]] += 1
        return v

    def _pert(self, raw):
        v = _norm_cached(self._c_pert, PERT, raw)
        if v is None:
            self.unknown["pertenencia_codigo"][raw.strip()[:40]] += 1
        return v

    def _cob(self, raw):
        v = _norm_cached(self._c_cob, COB, raw)
        if v is None:
            self.unknown["cobertura_financiamiento"][raw.strip()[:40]] += 1
        return v

    def _treg(self, raw):
        v = _norm_cached(self._c_treg, TREG, raw)
        if v is None:
            self.unknown["tipo_registro"][raw.strip()[:40]] += 1
        return v

    def add(self, f: list[str]) -> None:
        self.rows += 1
        num, err = base.num, self.err
        atn = self._atn(f[I_ATN])
        pert = self._pert(f[I_PERT])
        cob = self._cob(f[I_COB])
        treg = self._treg(f[I_TIPO_REG])
        region = f[I_REGION].strip() or "(vacío)"
        if not region.isdigit():
            self.unknown["region_prestador"][region[:40]] += 1
        fact = num(f[I_FACT], err, "valor_facturado")
        freq = num(f[I_FREC], err, "frecuencia")
        bonif = num(f[I_BONIF], err, "valor_bonificado")
        isapre, prov, code = f[I_ISAPRE].strip(), f[I_PREST].strip(), f[I_CODIGO].strip()
        t = self.tot_atn[atn or "(desconocido)"]
        t[0] += fact; t[1] += bonif; t[2] += freq; t[3] += 1

        # (a) insumos del índice de precios
        if pert == "fonasa" and cob in INDEX_COB and treg == "curativa" and fact > 0 and atn \
                and prov not in NO_PROVIDER:
            k = (prov, code, region, atn)
            v = self.price.get(k)
            if v is None:
                self.price[k] = [fact, freq, bonif]
            else:
                v[0] += fact; v[1] += freq; v[2] += bonif
            self.scope["indice"] += fact
            if not self.warmup:
                c = self.code_tot.get((code, atn))
                if c is None:
                    c = self.code_tot[(code, atn)] = [0.0, 0.0, 0.0, set()]
                c[0] += bonif; c[1] += freq; c[2] += fact; c[3].add(prov)
        self.scope["total"] += fact

        # (c)/(d) PAM principal (campo 14 del Compendio = folio_1 del archivo público)
        folio = f[I_PAM].strip()
        if folio in ("", "0"):
            self.rows_pam_literal_zero[atn or "(desconocido)"] += 1
        else:
            key = (isapre, folio)
            e = self.pams.get(key)
            ben = f[I_BEN].strip()
            if e is None:
                if len(self.pams) >= self.max_pams:
                    self.pam_overflow += 1
                    e = None
                else:
                    e = [0, ben, 0, code, prov, 0.0, 0.0, None, None, 0]
                    self.pams[key] = e
            if e is not None:
                e[0] += 1
                fl = e[2]
                if ben != e[1]:
                    fl |= 1
                if code != e[3]:
                    fl |= 2
                if prov != e[4]:
                    fl |= 4
                if atn == "Hospitalaria":
                    fl |= 8
                    e[9] += 1
                elif atn == "Ambulatoria":
                    fl |= 16
                compl = f[I_PAM_COMPL].strip()
                if compl not in ("", "0"):
                    fl |= 32
                e[2] = fl
                if not self.warmup:
                    e[5] += fact; e[6] += bonif
                    spec = self._c_tracer.get(code, 0)
                    if spec == 0:
                        spec = self._c_tracer[code] = tracer_specialty(code)
                    if spec is not None:
                        val = self.mle.get(code) or 1.0
                        d = e[7]
                        if d is None:
                            e[7] = d = {}
                        cur = d.get(spec)
                        if cur is None or val > cur[0]:
                            d[spec] = (val, prov)
                    cr = CAMA_RANK.get(code)
                    if cr is not None and (e[8] is None or cr[0] < e[8]):
                        e[8] = cr[0]
        compl_raw = f[I_PAM_COMPL].strip()
        if compl_raw not in ("", "0"):
            self.rows_compl[atn or "(desconocido)"] += 1
        if self.warmup:
            return

        # (b) GES por GPP
        gpp = f[I_GPP].strip()
        if gpp and gpp.upper() != "X":
            p = parse_gpp(gpp)
            if p is None:
                self.gpp_unparsed["no_parseable"] += 1
            else:
                prob, letter = p
                idg = f[I_GES].strip()
                case = None
                if idg and idg.upper() != "X":
                    case = hash((isapre, idg))  # llave opaca en memoria (hash aleatorizado por proceso); nunca se escribe
                else:
                    self.ges_sin_id += 1
                for store, k in ((self.ges, (prob, isapre, region)), (self.ges_letter, (prob, letter))):
                    c = store.get(k)
                    if c is None:
                        c = store[k] = [0.0, 0.0, 0.0, set(), set()]
                    c[0] += fact; c[1] += bonif; c[2] += freq
                    if case is not None:
                        c[3].add(case)
                    if prov not in NO_PROVIDER:
                        c[4].add(prov)
                g = self.ges_tot
                g[0] += fact; g[1] += bonif; g[2] += freq; g[3] += 1
        elif cob == "ges":
            self.ges_sin_gpp[0] += fact; self.ges_sin_gpp[1] += 1

    # ---------------------------------------------------------------- esquema
    def schema_check(self, parse: dict) -> dict:
        lines = max(parse.get("lines_read", 0) - parse.get("blank_lines", 0) - (1 if parse.get("header_row_detected") else 0), 0)
        malformed_pct = pct(parse.get("rows_malformed", 0), lines) or 0.0
        unknown = {k: pct(sum(v.values()), self.rows) or 0.0 for k, v in self.unknown.items()}
        reasons = []
        if not self.rows:
            reasons.append("sin_filas_con_30_campos")
        if malformed_pct > SCHEMA_MAX_MALFORMED_PCT:
            reasons.append(f"filas_con_n_campos_distinto_a_{base.PREST_N}:{malformed_pct}%")
        for k, v in unknown.items():
            if v > SCHEMA_MAX_UNKNOWN_PCT:
                reasons.append(f"valores_no_mapeados_{k}:{v}%")
        return {"layout": "publico_30_campos_v2026 (Compendio 07.09.2026, Título V, 35 campos maestros menos 05, 10, 12, 22, 31)",
                "ok": not reasons, "razones": reasons, "pct_filas_malformadas": malformed_pct,
                "pct_valores_no_mapeados": unknown,
                # sólo columnas categóricas no sensibles y valores con >= 10 filas
                "valores_no_mapeados_top": {k: [[val, c] for val, c in v.most_common(5) if c >= base.PROFILE_MIN_COUNT]
                                            for k, v in self.unknown.items()},
                "gpp_no_parseable": dict(self.gpp_unparsed)}

    # ---------------------------------------------------------------- PAM: marcador y llaves
    def placeholder_keys(self) -> set:
        thr = self.placeholder_min_rows
        return {k for k, e in self.pams.items() if e[0] >= thr}

    def real_pam_hashes(self) -> set:
        ph = self.placeholder_keys()
        return {hash(k) for k in self.pams if k not in ph}

    def release(self) -> None:
        """Libera la memoria de un trimestre ya escrito (se conservan sólo precio y llaves para el siguiente)."""
        self.pams = {}
        self.ges = {}
        self.ges_letter = {}
        self.code_tot = {}

    # ---------------------------------------------------------------- insumo ICSA (valor unitario por código)
    def icsa_basket(self) -> dict:
        """Totales por código MLE x tipo de atención en el alcance del ICSA (todas las Isapres y prestadores, sin
        emparejar): lo que el ICSA usa para su IVUBI (bonificado / frecuencia) y su ICBI (frecuencia). Con < 3
        prestadores la celda no publica montos (entra sólo al total del tipo de atención)."""
        rows, tot = [], defaultdict(lambda: [0.0, 0.0, 0.0])
        for (code, atn), c in sorted(self.code_tot.items()):
            t = tot[atn]
            t[0] += c[0]; t[1] += c[1]; t[2] += c[2]
            n = len(c[3])
            if n < REL_MIN_PROVIDERS:
                rows.append([code, atn, "suprimido_menos_de_3_prestadores", n, None, None, None])
            else:
                rows.append([code, atn, "publicable", n, round(c[0]), round(c[1]), round(c[2])])
        return {"definicion": self.icsa_basket.__doc__.replace("\n        ", " "),
                "alcance": "pertenencia FONASA (MLE), curativa, cobertura CAEC / GES-CAEC / Plan Complementario, "
                           "facturado > 0, prestador informado (memoria de cálculo ICSA 2025, tabla AMPB)",
                "totales_por_tipo_atencion": {a: {"bonificado": round(v[0]), "frecuencia": round(v[1]),
                                                  "facturado": round(v[2])} for a, v in sorted(tot.items())},
                "columns": ["codigo_prestacion", "tipo_atencion", "estado", "n_prestadores", "bonificado",
                            "frecuencia", "facturado"], "rows": rows}

    # ---------------------------------------------------------------- (c) probe de folios
    def folio_probe(self, prev_pam_hashes: set | None) -> dict:
        ph = self.placeholder_keys()
        rows_ph = Counter()
        n = multi_ben = multi_code = multi_prov = mixed = with_compl = 0
        rows_real = Counter()
        sizes: list[int] = []
        folio_isapres: dict[str, int] = {}
        multi_isapre_vals = 0
        cur_hashes = set()
        for k, e in self.pams.items():
            hosp_rows = e[9]
            if k in ph:
                rows_ph["Hospitalaria"] += hosp_rows
                rows_ph["no_hospitalaria"] += e[0] - hosp_rows
                continue
            n += 1
            fl = e[2]
            multi_ben += bool(fl & 1); multi_code += bool(fl & 2); multi_prov += bool(fl & 4)
            mixed += (fl & 24) == 24; with_compl += bool(fl & 32)
            rows_real["Hospitalaria"] += hosp_rows
            rows_real["no_hospitalaria"] += e[0] - hosp_rows
            sizes.append(e[0])
            if k[1] in folio_isapres:
                if folio_isapres[k[1]] == 1:
                    multi_isapre_vals += 1
                folio_isapres[k[1]] += 1
            else:
                folio_isapres[k[1]] = 1
            if prev_pam_hashes is not None:
                cur_hashes.add(hash(k))
        n_vals = len(folio_isapres)
        del folio_isapres
        sizes.sort()
        atn_rows = {a: v[3] for a, v in self.tot_atn.items()}
        hosp_total = atn_rows.get("Hospitalaria", 0)
        no_hosp_total = self.rows - hosp_total
        overlap = len(cur_hashes & prev_pam_hashes) if prev_pam_hashes is not None else None
        out = {
            "definicion": "PAM = campo 14 del Archivo Maestro (Número Programa Médico Principal; 0 si la prestación no es "
                          "parte de un programa médico y distinto de 0 si la atención es hospitalaria), columna 11 del "
                          "archivo público (folio_1). La llave del episodio es (Isapre, PAM) en memoria. Un valor con >= "
                          f"{self.placeholder_min_rows} filas se trata como el marcador cifrado de 'sin PAM'. Sólo conteos.",
            "filas": self.rows,
            "filas_por_tipo_atencion": atn_rows,
            "marcador_sin_pam": {"valores_distintos_detectados": len(ph),
                                 "filas": sum(rows_ph.values()), "pct_filas": pct(sum(rows_ph.values()), self.rows),
                                 "filas_hospitalarias": rows_ph["Hospitalaria"]},
            "filas_con_pam_literal_0_o_vacio": dict(self.rows_pam_literal_zero),
            "filas_con_pam_real": {"hospitalarias": rows_real["Hospitalaria"],
                                   "no_hospitalarias": rows_real["no_hospitalaria"],
                                   "pct_de_hospitalarias_con_pam": pct(rows_real["Hospitalaria"], hosp_total),
                                   "pct_de_ambulatorias_con_pam": pct(rows_real["no_hospitalaria"], no_hosp_total)},
            "filas_con_pam_complementario_distinto_de_0": dict(self.rows_compl),
            "pam": {"n": n, "valores_folio_distintos": n_vals,
                    "pct_valores_folio_en_2_o_mas_isapres": pct(multi_isapre_vals, n_vals),
                    "pct_pam_con_mas_de_un_beneficiario": pct(multi_ben, n),
                    "pct_pam_con_mas_de_un_codigo": pct(multi_code, n),
                    "pct_pam_con_mas_de_un_prestador": pct(multi_prov, n),
                    "pct_pam_con_filas_ambulatorias_y_hospitalarias": pct(mixed, n),
                    "pct_pam_con_complementario": pct(with_compl, n),
                    "filas_por_pam": {"p50": quantile(sizes, .5), "p90": quantile(sizes, .9),
                                      "p99": quantile(sizes, .99)} if sizes else None},
            "entre_trimestres": None if overlap is None else {
                "pam_del_trimestre_presentes_en_el_anterior": overlap,
                "pct_sobre_pam_del_trimestre": pct(overlap, n),
                "nota": "misma Isapre y mismo valor cifrado; > 0 indica cifrado estable entre trimestres"},
            "pam_descartados_por_tope_de_memoria": self.pam_overflow,
        }
        pm = out["pam"]
        hosp_ok = (out["filas_con_pam_real"]["pct_de_hospitalarias_con_pam"] or 0) >= 95
        ben_ok = (pm["pct_pam_con_mas_de_un_beneficiario"] or 0) <= 5
        isa_ok = (pm["pct_valores_folio_en_2_o_mas_isapres"] or 0) <= 1
        reasons = [m for ok, m in ((hosp_ok, "menos_de_95pct_de_filas_hospitalarias_con_pam"),
                                   (ben_ok, "mas_de_5pct_de_pam_con_varios_beneficiarios"),
                                   (isa_ok, "mas_de_1pct_de_valores_en_varias_isapres"),
                                   (self.pam_overflow == 0, "tope_de_memoria_superado"),
                                   (n > 0, "sin_pam")) if not ok]
        out["veredicto"] = {"agrupacion_por_pam_valida": not reasons, "razones": reasons,
                            "criterio": ">= 95 % de filas hospitalarias con PAM real; <= 5 % de PAM con más de un "
                                        "beneficiario seudónimo; <= 1 % de valores de PAM repetidos entre Isapres"}
        return out

    # ---------------------------------------------------------------- (b) GES
    def ges_tables(self, ref: dict) -> dict:
        names, family = ref["names"], ref["family"]

        def label(p):
            return names.get(p, f"problema {p}")

        def cell(v: list) -> dict:
            return {"casos": len(v[3]), "facturado": round(v[0]), "bonificado": round(v[1]), "frecuencia": round(v[2]),
                    "n_prestadores": len(v[4])}

        def merge(items: Iterable[list]) -> list:
            acc = [0.0, 0.0, 0.0, set(), set()]
            for v in items:
                acc[0] += v[0]; acc[1] += v[1]; acc[2] += v[2]; acc[3] |= v[3]; acc[4] |= v[4]
            return acc

        by_pi: dict[tuple, list] = defaultdict(list)
        by_pr: dict[tuple, list] = defaultdict(list)
        by_p: dict[int, list] = defaultdict(list)
        by_fi: dict[tuple, list] = defaultdict(list)
        by_f: dict[str, list] = defaultdict(list)
        for (p, i, reg), v in self.ges.items():
            by_pi[(p, i)].append(v); by_pr[(p, reg)].append(v); by_p[p].append(v)
            fam = family.get(p, "otros")
            by_fi[(fam, i)].append(v); by_f[fam].append(v)
        pi = {k: merge(v) for k, v in by_pi.items()}
        pr = {k: merge(v) for k, v in by_pr.items()}
        pn = {k: merge(v) for k, v in by_p.items()}
        fi = {k: merge(v) for k, v in by_fi.items()}
        fn = {k: merge(v) for k, v in by_f.items()}
        three = dict(self.ges)

        def sup_one_way(cells: dict, parent_of) -> set:
            sizes = {k: len(v[3]) for k, v in cells.items()}
            init = {k for k, s in sizes.items() if s < GES_MIN_CASES}
            groups: dict = defaultdict(list)
            for k in cells:
                groups[parent_of(k)].append(k)
            return complementary(sizes, init, list(groups.values()), GES_MIN_CASES)

        sup_pn = {k for k, v in pn.items() if len(v[3]) < GES_MIN_CASES}
        sup_pi = sup_one_way(pi, lambda k: k[0])
        sup_pr = sup_one_way(pr, lambda k: k[0])
        sup_fn = {k for k, v in fn.items() if len(v[3]) < GES_MIN_CASES}
        sup_fi = sup_one_way(fi, lambda k: k[0])
        sizes3 = {k: len(v[3]) for k, v in three.items()}
        groups3: dict = defaultdict(list)
        for k in three:
            groups3[("i", k[0], k[1])].append(k)  # fila: problema x isapre (todas las regiones)
            groups3[("r", k[0], k[2])].append(k)  # columna: problema x región (todas las isapres)
        sup3 = complementary(sizes3, {k for k, s in sizes3.items() if s < GES_MIN_CASES}, list(groups3.values()),
                             GES_MIN_CASES)

        def rows(cells: dict, sup: set, keyf) -> tuple[list, dict]:
            out, hidden = [], [0, 0]
            for k in sorted(cells, key=lambda x: tuple(str(y).zfill(4) for y in (x if isinstance(x, tuple) else (x,)))):
                if k in sup:
                    hidden[0] += 1; hidden[1] += len(cells[k][3])
                    continue
                out.append({**keyf(k), **cell(cells[k])})
            return out, {"celdas_suprimidas": hidden[0]}

        def pk(p):
            return {"problema": p, "nombre": label(p), "familia": family.get(p, "otros")}

        nat, nat_s = rows(pn, sup_pn, pk)
        isa, isa_s = rows(pi, sup_pi, lambda k: {**pk(k[0]), "isapre": k[1]})
        reg, reg_s = rows(pr, sup_pr, lambda k: {**pk(k[0]), "region": k[1]})
        ir, ir_s = rows(three, sup3, lambda k: {**pk(k[0]), "isapre": k[1], "region": k[2]})
        fam_n, fam_n_s = rows(fn, sup_fn, lambda k: {"familia": k})
        fam_i, fam_i_s = rows(fi, sup_fi, lambda k: {"familia": k[0], "isapre": k[1]})
        let = {k: v for k, v in self.ges_letter.items()}
        sup_let = sup_one_way(let, lambda k: k[0])
        letters, let_s = rows(let, sup_let, lambda k: {**pk(k[0]), "intervencion": k[1]})
        g = self.ges_tot
        return {
            "definicion": "Filas con codigo_gpp (campo 34 del Compendio) distinto de 'X'; problema = prefijo numérico del "
                          "GPP; casos = id GES distintos (campo 35) por Isapre, contados en memoria como llave opaca. "
                          f"Celdas con >= {GES_MIN_CASES} casos; supresión complementaria dentro de cada problema (y de "
                          "cada fila y columna en problema x Isapre x región). Los casos no son aditivos entre regiones "
                          "o intervenciones (un caso puede tener filas en varias).",
            "fuente_nombres": ref["fuentes"],
            "totales": {"filas_con_gpp": g[3], "facturado": round(g[0]), "bonificado": round(g[1]),
                        "frecuencia": round(g[2]), "pct_facturado_del_trimestre": pct(g[0], self.scope["total"]),
                        "filas_gpp_sin_id_ges": self.ges_sin_id,
                        "ges_sin_gpp": {"filas": self.ges_sin_gpp[1], "facturado": round(self.ges_sin_gpp[0])}},
            "por_problema_nacional": {"filas": nat, **nat_s},
            "por_problema_isapre": {"filas": isa, **isa_s},
            "por_problema_region": {"filas": reg, **reg_s},
            "por_problema_isapre_region": {"filas": ir, **ir_s},
            "por_problema_intervencion": {"filas": letters, **let_s},
            "por_familia_nacional": {"filas": fam_n, **fam_n_s},
            "por_familia_isapre": {"filas": fam_i, **fam_i_s},
        }

    # ---------------------------------------------------------------- (d) especialidades v0
    def specialty_tables(self) -> dict:
        ph = self.placeholder_keys()
        cells: dict[tuple, list] = defaultdict(lambda: [[], Counter(), 0.0, 0.0])  # costos, prov, fact, bonif
        isapre_cnt: dict[str, Counter] = defaultdict(Counter)
        missing_value = 0
        for k, e in self.pams.items():
            if k in ph:
                continue
            tipo = "Hospitalaria" if e[2] & 8 else "Ambulatoria"
            d, prov = e[7], e[4]
            if d:
                ranked = sorted(d.items(), key=lambda kv: -kv[1][0])
                (spec, (v1, prov)), second = ranked[0], ranked[1] if len(ranked) > 1 else None
                if v1 <= 1.0:
                    missing_value += 1
                if second is not None and second[1][0] >= MULTI_SPEC_RATIO * v1:
                    spec = "multiespecialidad"
            elif e[8] is not None:
                spec = CAMA_BY_RANK[e[8]]
            else:
                spec = "sin_clasificar"
            for t in (tipo, "TOTAL"):
                c = cells[(spec, t)]
                c[0].append(e[5]); c[1][prov] += 1; c[2] += e[5]; c[3] += e[6]
            isapre_cnt[k[0]]["episodios"] += 1
            isapre_cnt[k[0]]["sin_clasificar"] += spec == "sin_clasificar"

        def fails(c) -> bool:
            n, provs = len(c[0]), len(c[1])
            top = max(c[1].values()) if c[1] else 0
            return n < SPEC_MIN_EPISODES or provs < SPEC_MIN_PROVIDERS or (pct(top, n) or 0) > SPEC_MAX_TOP_SHARE

        sizes = {k: len(c[0]) for k, c in cells.items()}
        init = {k for k, c in cells.items() if fails(c)}
        groups: dict = defaultdict(list)
        for k in cells:
            groups[("spec", k[0])].append(k)   # Ambulatoria + Hospitalaria = TOTAL publicado
            if k[1] != "TOTAL":
                groups[("tipo", k[1])].append(k)  # suma sobre especialidades = total nacional del tipo
        sup = complementary(sizes, init, list(groups.values()), SPEC_MIN_EPISODES)
        rows = []
        for (spec, tipo), c in sorted(cells.items()):
            n, provs = len(c[0]), len(c[1])
            base_row = {"especialidad": spec, "nombre": SPECIALTIES[spec], "tipo_atencion": tipo}
            if (spec, tipo) in sup:
                rows.append({**base_row, "estado": "suprimido"})
                continue
            costs = sorted(c[0])
            top_share = pct(max(c[1].values()), n)
            rows.append({**base_row, "estado": "publicable", "episodios": n, "facturado": round(c[2]),
                         "bonificado": round(c[3]), "n_prestadores": provs,
                         "costo_episodio_mediana": r(quantile(costs, .5), 0),
                         "costo_episodio_p25": r(quantile(costs, .25), 0) if provs >= IQR_MIN_PROVIDERS else None,
                         "costo_episodio_p75": r(quantile(costs, .75), 0) if provs >= IQR_MIN_PROVIDERS else None,
                         "share_prestador_mayor_pct": top_share if provs > 2 else share_band(top_share)})
        tot = Counter()
        tot_fact = defaultdict(float)
        for (spec, tipo), c in cells.items():
            if tipo != "TOTAL":
                tot[tipo] += len(c[0]); tot_fact[tipo] += c[2]
        return {
            "experimental": True,
            "definicion": "EXPERIMENTAL v0. Episodio = (Isapre, PAM principal) del trimestre de bonificación, sólo PAM "
                          "reales (no el marcador 'sin PAM'). Especialidad = trazadora de mayor valor Arancel MLE 2026 "
                          f"(nivel 1); si otra especialidad tiene >= {int(MULTI_SPEC_RATIO * 100)} % de ese valor, "
                          "'multiespecialidad'; sin trazadora, día cama especial (psiquiatría > obstetricia > neonatal/"
                          "pediátrico > UCI adulto > básico/medio = medicina interna); si no, 'sin_clasificar'. Tipo = "
                          "Hospitalaria si alguna fila del PAM es hospitalaria. Prestador de la celda = el de la "
                          f"trazadora principal. Celdas con >= {SPEC_MIN_EPISODES} episodios, >= {SPEC_MIN_PROVIDERS} "
                          f"prestadores y ningún prestador con > {SPEC_MAX_TOP_SHARE:.0f} % de los episodios; supresión "
                          "complementaria. Un procedimiento no es un diagnóstico: leer como 'actividad asociada a'.",
            "trazadoras": {"por_prefijo_grupo_subgrupo_mle": TRACER_PREFIX, "por_codigo": TRACER_CODE,
                           "dia_cama_respaldo": {c: s for c, (_, s) in CAMA_RANK.items()}},
            "totales_nacionales": {t: {"episodios": tot[t], "facturado": round(tot_fact[t])} for t in sorted(tot)},
            "episodios_con_trazadora_sin_valor_mle_2026": missing_value,
            "por_isapre_pct_sin_clasificar": [
                {"isapre": i, "episodios": c["episodios"], "pct_sin_clasificar": pct(c["sin_clasificar"], c["episodios"])}
                for i, c in sorted(isapre_cnt.items())],
            "filas": rows,
        }


# ---------------------------------------------------------------- (a) relativos de precio entre trimestres
def price_relatives(prev: dict, cur: dict) -> dict:
    """Relativos mismo prestador / mismo código entre trimestres consecutivos.

    ``prev``/``cur``: (prov, codigo, region, atencion) -> [facturado, frecuencia, bonificado]. Por celda elemental
    (codigo x region x atencion, y NACIONAL sumando cada prestador entre regiones), sólo prestadores con frecuencia > 0
    en ambos trimestres. Media ponderada por facturado anterior (= Laspeyres de cantidades fijas del anterior) y
    mediana de los relativos del valor unitario facturado y bonificado. Se publica con >= REL_MIN_PROVIDERS
    prestadores y >= REL_MIN_PREV_FREQ de frecuencia anterior; con 2, sólo n y estado (cada uno despejaría el
    relativo del otro); con 1, sólo estado. Agregados por grupo MLE (2 dígitos) x atención, por atención y total,
    con todos los pares prestador x código (versión cruda y recortada a [0,2; 5])."""
    def national(d: dict) -> dict:
        out: dict[tuple, list] = {}
        for (prov, code, region, atn), v in d.items():
            for key in ((prov, code, region, atn), (prov, code, "NACIONAL", atn)):
                a = out.get(key)
                if a is None:
                    out[key] = [v[0], v[1], v[2]]
                else:
                    a[0] += v[0]; a[1] += v[1]; a[2] += v[2]
        return out

    a, b = national(prev), national(cur)
    cells: dict[tuple, list] = defaultdict(list)
    for key, (f0, q0, b0) in a.items():
        v1 = b.get(key)
        if v1 is None:
            continue
        f1, q1, b1 = v1
        if q0 > 0 and q1 > 0 and f0 > 0 and f1 > 0:
            rf = (f1 / q1) / (f0 / q0)
            rb = (b1 / q1) / (b0 / q0) if b0 > 0 and b1 > 0 else None
            cells[(key[1], key[2], key[3])].append((key[0], f0, q0, b0, f1, q1, b1, rf, rb))
    cols = ["codigo_prestacion", "region", "tipo_atencion", "estado", "n_prestadores", "frecuencia_anterior",
            "frecuencia_actual", "facturado_anterior", "facturado_actual", "bonificado_anterior", "bonificado_actual",
            "rel_facturado_media_pond_pct", "rel_facturado_mediana_pct", "rel_bonificado_media_pond_pct",
            "rel_bonificado_mediana_pct"]
    rows, status = [], Counter()
    groups: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, set(), set(), 0])
    for (code, region, atn), lst in sorted(cells.items()):
        n = len(lst)
        q0 = sum(x[2] for x in lst)
        if region == "NACIONAL":
            for gk in ((code[:2], atn), ("TODOS", atn), ("TODOS", "TOTAL")):
                g = groups[gk]
                for x in lst:
                    g[0] += x[1] * x[7]; g[1] += x[1]                      # Σ f0·rf, Σ f0 (facturado)
                    if x[8] is not None:
                        g[2] += x[3] * x[8]; g[3] += x[3]                  # Σ b0·rb, Σ b0 (bonificado)
                    if REL_TRIM[0] <= x[7] <= REL_TRIM[1]:
                        g[4] += x[1] * x[7]; g[5] += x[1]
                    else:
                        g[10] += 1
                    if x[8] is not None and REL_TRIM[0] <= x[8] <= REL_TRIM[1]:
                        g[6] += x[3] * x[8]; g[7] += x[3]
                    g[8].add(x[0]); g[9].add(code)
        if n == 1:
            st = "concentracion_un_prestador"
        elif n == 2:
            st = "suprimido_dos_prestadores"
        elif q0 < REL_MIN_PREV_FREQ:
            st = f"suprimido_frecuencia_anterior_menor_{REL_MIN_PREV_FREQ}"
        else:
            st = "publicable"
        status[(st, region == "NACIONAL")] += 1
        if st != "publicable":
            if n == 2:
                rows.append([code, region, atn, st, 2] + [None] * (len(cols) - 5))
            continue
        f0 = sum(x[1] for x in lst); f1 = sum(x[4] for x in lst)
        bl = [x for x in lst if x[8] is not None]
        b0 = sum(x[3] for x in bl); b1 = sum(x[6] for x in bl)
        rf = sorted(x[7] for x in lst)
        rb = sorted(x[8] for x in bl)
        rows.append([code, region, atn, st, n, round(q0), round(sum(x[5] for x in lst)), round(f0), round(f1),
                     round(b0), round(b1), r((sum(x[1] * x[7] for x in lst) / f0 - 1) * 100),
                     r((quantile(rf, .5) - 1) * 100),
                     r((sum(x[3] * x[8] for x in bl) / b0 - 1) * 100) if b0 > 0 and len(bl) >= REL_MIN_PROVIDERS else None,
                     r((quantile(rb, .5) - 1) * 100) if len(bl) >= REL_MIN_PROVIDERS else None])
    agg_rows = []
    for (grp, atn), g in sorted(groups.items()):
        if len(g[8]) < REL_MIN_PROVIDERS:
            agg_rows.append({"grupo_mle": grp, "tipo_atencion": atn, "estado": "suprimido_menos_de_3_prestadores"})
            continue
        agg_rows.append({"grupo_mle": grp, "tipo_atencion": atn, "estado": "publicable", "n_prestadores": len(g[8]),
                         "n_codigos": len(g[9]), "facturado_anterior_emparejado": round(g[1]),
                         "laspeyres_facturado_pct": r((g[0] / g[1] - 1) * 100) if g[1] else None,
                         "laspeyres_bonificado_pct": r((g[2] / g[3] - 1) * 100) if g[3] else None,
                         "laspeyres_facturado_recortado_pct": r((g[4] / g[5] - 1) * 100) if g[5] else None,
                         "laspeyres_bonificado_recortado_pct": r((g[6] / g[7] - 1) * 100) if g[7] else None,
                         "pares_excluidos_por_recorte": g[10]})
    return {"definicion": price_relatives.__doc__.split("\n\n", 1)[1].replace("\n    ", " ").strip(),
            "alcance": "pertenencia FONASA (MLE), tipo de registro curativa, cobertura CAEC / GES-CAEC / Plan "
                       "Complementario (se excluye GES, como el ICSA), facturado > 0, prestador informado",
            "nota_valores": "nominales (sin deflactar); el ICSA deflacta por IPC y usa valor bonificado",
            "conteo_estados": [{"estado": k[0], "nacional": k[1], "celdas": v} for k, v in sorted(status.items())],
            "agregados": agg_rows, "columns": cols, "rows": rows}


# ---------------------------------------------------------------- orquestación
def quarters_between(a: str, b: str) -> list[str]:
    ka, kb = base.quarter_key(a), base.quarter_key(b)
    return [f"{k // 4}t{k % 4 + 1}" for k in range(ka, kb + 1)]


def done(out_root: Path, q: str) -> bool:
    p = out_root / q / f"receipts_{q}.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return d.get("script_version") == SCRIPT_VERSION and d.get("estado") in ("ok", "omitido")


def write_json(path: Path, obj) -> None:
    base.write_json(path, obj)


def git_commit(paths: list[Path], msg: str) -> None:
    if os.environ.get("HIST_COMMIT") != "1":
        return
    subprocess.run(["git", "add", *[str(p) for p in paths]], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return
    subprocess.run(["git", "commit", "-q", "-m", msg], check=True)
    branch = os.environ.get("GITHUB_REF_NAME", "")
    for attempt in range(8):
        subprocess.run(["git", "pull", "-q", "--rebase", "origin", branch], check=False)
        if subprocess.run(["git", "push", "-q", "origin", f"HEAD:{branch}"]).returncode == 0:
            return
        time.sleep(5 + 10 * attempt)
    raise SystemExit("git push falló tras 8 intentos")


def run_block(quarters: list[str], out_root: Path = OUT_ROOT, local: dict[str, Path] | None = None,
              links: list[str] | None = None) -> list[dict]:
    """Procesa los trimestres pendientes del bloque, con el trimestre previo como calentamiento en memoria."""
    pending = [q for q in quarters if not done(out_root, q)]
    if not pending:
        print(json.dumps({"estado": "bloque_completo", "trimestres": quarters}))
        return []
    first = pending[0]
    seq = quarters_between(first, quarters[-1])
    warm = base.previous_quarter(first)
    mle = load_mle_values()
    ges_ref = load_ges_reference()
    if links is None and local is None:
        links = base.page_links()
    prev_price: dict | None = None
    prev_pams: set | None = None
    prev_q: str | None = None
    prev_ok = False
    summaries = []
    for q in [warm] + seq:
        is_warm = q == warm
        t0 = time.time()
        rec: dict = {"script_version": SCRIPT_VERSION, "periodo": q, "dataset": DATASET,
                     "generated_at": datetime.now(timezone.utc).isoformat(),
                     "github_run_id": os.environ.get("GITHUB_RUN_ID"), "github_sha": os.environ.get("GITHUB_SHA"),
                     "user_agent": base.UA, "max_file_bytes": base.MAX_FILE_BYTES}
        agg = QuarterAgg(mle, warmup=is_warm)
        tmpdir = Path(tempfile.mkdtemp(prefix="sis_hist_"))
        path = None
        try:
            if local is not None:
                path = local.get(q)
                frec = {"url": f"local:{path}" if path else None}
                if path is None:
                    frec["error"] = "sin_archivo_local"
            else:
                url = base.discover(DATASET, q, links)
                frec = {"url": url, "enlazado_en_pagina": any(u == url for u in (links or []))}
                path = tmpdir / f"{q}.zip"
                frec.update(base.download(url, path, base.MAX_BYTES[DATASET]))
            if "error" not in frec and path is not None:
                base.process_zip(path, base.PREST_N, agg.add, frec)
                frec["numeric_parse_errors"] = dict(agg.err)
        finally:
            if local is None and path is not None and path.exists():
                path.unlink()
            try:
                tmpdir.rmdir()
            except OSError:
                pass
        rec["archivo"] = frec
        schema = agg.schema_check(frec.get("parse", {})) if "error" not in frec else {"ok": False,
                                                                                   "razones": [frec["error"]]}
        rec["esquema"] = schema
        ok = bool(schema.get("ok"))
        if is_warm:
            print(json.dumps({"calentamiento": q, "esquema_ok": ok, "filas": agg.rows,
                              "segundos": round(time.time() - t0, 1)}))
        else:
            qdir = out_root / q
            for old in qdir.glob("*.json") if qdir.exists() else []:
                old.unlink()  # un trimestre se reescribe completo con la versión actual
            written = []
            if ok:
                if prev_ok and prev_price is not None:
                    fp = qdir / f"indice_precios_{prev_q}_{q}.json"
                    write_json(fp, {"periodo_anterior": prev_q, "periodo": q, "script_version": SCRIPT_VERSION,
                                    "cobertura": {"facturado_en_alcance_pct": pct(agg.scope["indice"], agg.scope["total"])},
                                    **price_relatives(prev_price, agg.price)})
                    written.append(fp.name)
                else:
                    rec["indice_precios"] = f"sin_trimestre_anterior_valido:{prev_q}"
                fp = qdir / f"icsa_canasta_{q}.json"
                write_json(fp, {"periodo": q, "script_version": SCRIPT_VERSION, **agg.icsa_basket()})
                written.append(fp.name)
                fp = qdir / f"ges_gpp_{q}.json"
                write_json(fp, {"periodo": q, "script_version": SCRIPT_VERSION, **agg.ges_tables(ges_ref)})
                written.append(fp.name)
                probe = agg.folio_probe(prev_pams if prev_ok else None)
                fp = qdir / f"folios_probe_{q}.json"
                write_json(fp, {"periodo": q, "script_version": SCRIPT_VERSION, **probe})
                written.append(fp.name)
                spec = agg.specialty_tables()
                spec["agrupacion_por_pam_valida"] = probe["veredicto"]["agrupacion_por_pam_valida"]
                fp = qdir / f"especialidades_v0_{q}.json"
                write_json(fp, {"periodo": q, "script_version": SCRIPT_VERSION, **spec})
                written.append(fp.name)
                rec["estado"] = "ok"
            else:
                rec["estado"] = "omitido"
                rec["razon_omision"] = schema.get("razones")
            rec["archivos_escritos"] = written
            rec["totales_por_tipo_atencion"] = {a: {"facturado": round(v[0]), "bonificado": round(v[1]),
                                                    "frecuencia": round(v[2]), "filas": v[3]}
                                                for a, v in sorted(agg.tot_atn.items())}
            rec["segundos"] = round(time.time() - t0, 1)
            rec["finished_at"] = datetime.now(timezone.utc).isoformat()
            write_json(qdir / f"receipts_{q}.json", rec)
            summaries.append({"periodo": q, "estado": rec["estado"], "archivos": written, "segundos": rec["segundos"]})
            print(json.dumps(summaries[-1], ensure_ascii=False))
            git_commit([qdir], f"Histórico SIS {q}: agregados de precios, GES, folios y especialidades "
                               f"({rec['estado']}, run {os.environ.get('GITHUB_RUN_ID')})")
        prev_ok = ok
        prev_q = q
        prev_price = agg.price if ok else None
        prev_pams = agg.real_pam_hashes() if ok else None
        agg.release()
        del agg
    return summaries


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--quarters", required=True, help="lista separada por comas o rango yyyytq..yyyytq")
    ap.add_argument("--output-root", default=str(OUT_ROOT))
    a = ap.parse_args()
    if ".." in a.quarters:
        lo, hi = a.quarters.split("..")
        qs = quarters_between(lo.strip(), hi.strip())
    else:
        qs = [q.strip() for q in a.quarters.split(",") if q.strip()]
    for q in qs:
        base.quarter_key(q)
    run_block(sorted(qs, key=base.quarter_key), Path(a.output_root))


if __name__ == "__main__":
    main()
