"""Lectura Alicanto figure verifier (Dirección 28-oct-2026 15:25: "puede tener cifras, solo que no caiga en ser
redundantes, debe aportar algo más").

1. Parse.   NFKC; insurer names, aliases and misspellings (edit distance ≤ 2 on names longer than 5 letters) are
            masked first, so 'Vida 3' or 'Vida Tres' is an insurer and never a number. Every figure mention becomes
            (value, decimals, comparator, sign, unit, subject, period). Sign: +/− or the nearest direction word.
            Unit: %, pp, persons (the metric noun after the figure, or before it in the same clause), 'veces' or
            'N … por cada …' (ratio), entity counts ('7 Isapres'). Comparator: más de / superior a / sobre (true >
            stated), menos de / inferior a / bajo (true < stated), casi (true < stated, within 5 %), cerca de /
            alrededor de / unos / aproximadamente (within 5 %). Subject: the insurer, 'el sistema', 'las Isapres',
            'las abiertas' or 'las cerradas' the clause credits the figure to. Period: the months named in the
            clause (else the sentence), YTD wording ('desde enero', 'en lo que va del año', 'en el año', 'entre enero
            y …') and a 12-month window ('en doce meses', 'últimos 12 meses'), which is a period, never a figure.
2. Trace.   Every digit mention must equal a ``lectura_pool`` entry (declared by the family builder, never the whole
            package) rounded half-up to the shown precision (or satisfy its comparator), with matching unit, sign,
            scope (system / open / closed / insurer:<code>) and period kind (month / ytd / interval / stock_at).
            Years are allowed only when they are package periods. Base: a share or rate entry declares its
            denominator (``base``: 'abiertas', 'sistema', 'variacion_sistema', …). A required base must be named in
            the clause (else the sentence): an open-only share credited to 'del mercado' / 'del sistema' fails as
            ``share_base_mismatch``, one that names no base fails as ``share_base_unstated``.
3. Words.   A closed lexicon (doble, triple, quíntuple, mitad, tercio, cuarto, par, décima, centésimo, ordinals,
            Roman numerals, 'medio punto', 'uno de cada N', decenas/miles…) maps each number word to a value that
            must equal a ``derived_ratios`` or ``ranks`` entry within display tolerance (pp words and magnitudes
            may also match ``lectura_pool``). An ordinal must trace to a rank of the ranking it names (size, decline,
            growth, streak) in that ranking's period. A figure-free superlative ('es la Isapre que más crece', 'la
            mayor baja', 'la más grande') is a rank too: rank 1 (or the last rank for 'que menos') of the ranking it
            names, credited to the Isapre in the clause. Any other number-like token fails.
4. Adds.    D = value ids traced from the headline, dek, KPIs, tab texts and facts. A sentence with figures must
            cite at least one traced, non-trivial id outside D (entity counts such as the 7 open Isapres are
            trivial); every sentence must have content-word Jaccard < 0.5 against every displayed sentence; a
            sentence without figures must also name an audience or implication.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Any

MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")
MONTH_RX = "|".join(MONTHS)
PERSON_UNITS = {"personas", "cotizantes", "contratos", "beneficiarios", "cargas", "desahucios"}
NOUNS = {"personas": None, "beneficiarios": "beneficiarios", "cotizantes": "cotizantes", "cargas": "cargas",
         "afiliados": None, "contratos": "contratos", "desahucios": "desahucios"}
NOUN_RX = "personas|beneficiarios|cotizantes|cargas|afiliados|contratos|desahucios"
WORD_TOL_REL = 0.05  # display tolerance of a multiple or fraction word ('doble' = 1,9–2,1)
APPROX_TOL_REL = 0.05  # 'cerca de', 'alrededor de', 'unos', 'aproximadamente', 'casi'
BOUND_TOL_REL = 0.10  # 'más de' / 'menos de': the stated bound must also be close (never 'más de 1')

_ACC = str.maketrans("áéíóúüñàèìòù", "aeiouunaeiou")


def fold(text: str) -> str:
    """Lower case without accents, same length as the input (positions map back to the original)."""
    return "".join((c.lower()[:1] or c) for c in str(text or "")).translate(_ACC)


CARD = {"cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
        "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
        "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21,
        "veintiuno": 21, "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
        "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40,
        "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100}
for _w, _v in (("dos", 200), ("tres", 300), ("cuatro", 400), ("quin", 500), ("seis", 600), ("sete", 700),
               ("ocho", 800), ("nove", 900)):
    CARD[f"{_w}cientos"] = CARD[f"{_w}cientas"] = _v
CARD["quinientos"] = CARD["quinientas"] = 500
SCALE = {"mil": 1_000, "millon": 1_000_000, "millones": 1_000_000}
CARD_RX = "|".join(sorted((k for k in CARD if k not in ("un", "una", "uno")), key=len, reverse=True))
CARD_ANY = "|".join(sorted(CARD, key=len, reverse=True))
ORDINALS = [(r"primer[oa]?s?", 1), (r"segund[oa]s?", 2), (r"tercer[oa]?s?", 3), (r"cuart[oa]s?", 4),
            (r"quint[oa]s?", 5), (r"sext[oa]s?", 6), (r"s[e]?ptim[oa]s?", 7), (r"octav[oa]s?", 8),
            (r"noven[oa]s?", 9), (r"decim[oa]s?", 10), (r"undecim[oa]s?", 11), (r"duodecim[oa]s?", 12),
            (r"vigesim[oa]s?", 20), (r"trigesim[oa]s?", 30), (r"centesim[oa]s?", 100), (r"milesim[oa]s?", 1000)]
MULTIPLES = [(r"dobles?|duplic\w*", 2), (r"triples?|triplic\w*", 3), (r"cuadruples?|cuadruplic\w*", 4),
             (r"quintuples?|quintuplic\w*", 5), (r"sextuples?|sextuplic\w*", 6), (r"septuples?|septuplic\w*", 7),
             (r"octuples?|octuplic\w*", 8)]
FRACTION_NOUNS = {"medio": 2, "medios": 2, "tercio": 3, "tercios": 3, "cuarto": 4, "cuartos": 4, "quinto": 5,
                  "quintos": 5, "sexto": 6, "sextos": 6, "decimo": 10, "decimos": 10, "centesimo": 100,
                  "centesimos": 100}
PARTS = {"media": 2, "tercera": 3, "cuarta": 4, "quinta": 5, "sexta": 6, "decima": 10, "centesima": 100}
MAGNITUDES = [(r"decenas? de miles", 10_000, 100_000), (r"(?:cientos|centenares|centenas) de miles", 100_000, 1_000_000),
              (r"decenas? de millones", 10_000_000, 100_000_000), (r"decenas", 10, 100),
              (r"(?:cientos|centenares|centenas)", 100, 1_000), (r"(?:miles|millares)", 1_000, 1_000_000),
              (r"millones", 1_000_000, 1_000_000_000)]
NEG = (r"ca(?:e|en|ia|ian|yo|yeron|ida|idas|ido|er|era|eran|yendo)|baj\w*|pierd\w*|perd\w*|retroced\w*|"
       r"disminu\w*|reduc\w*|reduj\w*|contra(?:e|en|jo|jeron|ccion\w*)|cede|ceden|cedio|cedieron|descen\w*|"
       r"desciend\w*|merm\w*|resta|restan|resto|restaron|menos|negativ\w*|retroceso")
POS = (r"sub(?:e|en|io|ieron|ida|ir|iendo)|alza\w*|crec\w*|creci\w*|gan(?:a|an|o|aron|ando|ancia\w*)|aument\w*|"
       r"avanz\w*|suma|suman|sumo|sumaron|agreg\w*|increment\w*|ascen\w*|asciend\w*|mas|positiv\w*|repunt\w*")
NUMBERISH = (r"cero|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|dieci\w+|"
             r"veint\w*|trein\w*|cuarent\w*|cincuent\w*|sesent\w*|setent\w*|ochent\w*|novent\w*|cien|ciento\w*|"
             r"\w+cient[oa]s|mil|miles|millar\w*|millon\w*|billon\w*|decena\w*|docena\w*|centena\w*|centenar\w*|"
             r"doble\w*|duplic\w*|triple\w*|triplic\w*|cuadrupl\w*|quintupl\w*|sextupl\w*|mitad\w*|tercio\w*|"
             r"cuart[oa]s?|quint[oa]s?|sext[oa]s?|s[e]?ptim\w*|octav[oa]s?|noven[oa]s?|decim[oa]s?|undecim\w*|"
             r"duodecim\w*|vigesim\w*|centesim\w*|milesim\w*|primer\w*|segund[oa]s?|tercer\w*|por ciento")
ROMAN = re.compile(r"(?<![\w·])(?=[MDCLXVI])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})(?![\w·])")
DIGIT_NUM = (r"(?P<sign>[+\-−–]\s?)?(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)")
SUFFIX = (r"(?:\s*(?P<pct>%|por ciento)|\s*(?P<pp>pp\b|p\.p\.|puntos? porcentuales?\b|puntos?\b)"
          r"|\s+(?P<veces>veces)\b|\s+(?P<scale>mil|millon(?:es)?)\b)?"
          r"(?:\s+(?:de\s+)?(?P<noun>" + NOUN_RX + r")\b|\s+(?P<cnoun>isapres|aseguradoras)\b)?")
DIGIT_RX = re.compile(r"(?<![\w.,])" + DIGIT_NUM + r"(?![\w])" + SUFFIX)
STOP = set("""a al algo ante antes aun bajo cada como con contra cual cuando de del desde donde dos durante e el ella
ellas ello ellos en entre era es esa ese eso esta este esto estos estas fue ha han hasta hay la las le les lo los mas
me mientras muy ni no nos o otra otro para pero poco por que quien se segun ser si sin sino sobre son su sus tambien
tan tanto te tiene tienen todo todos tras u un una uno unos y ya""".split())

# Comparators before a figure (folded). 'gt': true > stated; 'lt': true < stated; 'almost': true < stated and within
# 5 %; 'approx': within 5 %.
# Matched on lower-case text WITH accents, so the verb 'bajó' is never the comparator 'bajo'.
COMPARATORS = [
    (r"poco m[aá]s del?|m[aá]s del?|superior(?:es)? al?|por sobre|sobre|por encima del?", "gt"),
    (r"poco menos del?|menos del?|inferior(?:es)? al?|por debajo del?|bajo", "lt"),
    (r"casi|pr[aá]cticamente", "almost"),
    (r"cerca del?|alrededor del?|unos|unas|aproximadamente|aprox\.?|en torno al?|del orden del?", "approx"),
]
COMPARATOR_RX = re.compile(r"(?<![a-záéíóúüñ0-9·])(?P<cmp>" + "|".join(f"(?:{p})" for p, _ in COMPARATORS) +
                           r")\s+(?:(?:el|la|los|las)\s+)?$")
YTD_GENERIC = re.compile(r"en lo que va (?:del ano|de 20\d\d)|desde (?:el )?(?:inicio|comienzo|principio)s? (?:del?|de) "
                         r"ano|en el acumulado del ano|acumulad[oa]s? del ano|ano a la fecha|"
                         r"(?:en|durante) el (?:presente |actual )?ano(?! (?:pasado|anterior|movil))")
# A 12-month window is a period phrase, never a figure ('en doce meses', 'en los últimos 12 meses'); a streak
# ('doce meses consecutivos') stays a figure.
WINDOW_RX = re.compile(r"(?<![a-z0-9·])(?P<n>12|doce) meses(?! (?:consecutiv|seguid|de (?:alza|baja|caida|crecimiento)))")
YTD_FROM = re.compile(r"(?:desde|entre|de) (?P<m>" + MONTH_RX + r")(?: de 20\d\d)?(?= y | a | hasta |\b)")
GROUP_MARKERS = [  # subject phrases (folded); the order matters: 'las Isapres abiertas' is open, not system
    (r"(?:las |los |a las |de las |entre las )?(?:isapres |aseguradoras )?abiertas", "open"),
    (r"(?:las |los |a las |de las |entre las )?(?:isapres |aseguradoras )?cerradas", "closed"),
    (r"(?:el|al|del) sistema(?: isapre)?|(?:las|a las|de las|entre las) isapres|la industria|el sector|"
     r"la cartera(?! de)|(?:el|al|del) total", "system"),
]
RANKING_WORDS = [  # the ranking an ordinal names, from the words around it (folded)
    ("baja", r"baj\w*|perd\w*|pierd\w*|ca(?:e|en|ida|idas|yo|yeron)|retroce\w*|cede\w*|cedi\w*|merm\w*|disminu\w*"),
    ("alza", r"crec\w*|creci\w*|gan(?:a|an|o|aron|ancia\w*)|sub(?:e|en|io|ieron|ida)|alza\w*|aument\w*|avanz\w*"),
    ("racha", r"mes|meses|consecutiv\w*|seguid\w*"),
    ("tamano", r"grande\w*|tamano|cartera|beneficiarios|participacion|mercado"),
]
# Figure-free superlatives (folded): 'que más crece', 'la mayor baja', 'la más grande', 'lidera el crecimiento'.
SUPERLATIVE_RX = re.compile(
    r"(?<![a-z])(?:(?:que|quien|quienes) (?P<q>mas|menos) (?P<w>[a-z]+)"
    r"|(?P<q2>mayor|menor) (?P<w2>[a-z]+)"
    r"|(?:la|el|las|los)(?: isapres?| aseguradoras?)? (?P<q3>mas) (?P<w3>grandes?|chicas?|pequenas?)"
    r"|lider\w* (?:(?:en|el|la|del|de la|de) )*(?P<w4>[a-z]+))")
SUPERLATIVE_KINDS = [  # the ranking the superlative word names
    ("alza", r"crec\w*|creci\w*|gan(?:a|an|o|aron|ancia\w*)|sub(?:e|en|io|ieron|ida)|alza\w*|aument\w*|avanz\w*|avance"),
    ("baja", r"baj\w*|perd\w*|pierd\w*|ca(?:e|en|ida|idas|yo|yeron)|retroce\w*|cede\w*|cedi\w*|merm\w*|disminu\w*|contrac\w*"),
    ("tamano", r"grandes?|chicas?|pequenas?|cartera|tamano|mercado"),
]
# Denominators of share and rate entries. ``accept``: phrases that name the base; ``reject``: phrases that name a
# different base. A ``required`` base must be named next to the figure (its clause, else its sentence).
BASES = {
    "abiertas": {
        "short": "participación entre Isapres abiertas",
        "es": "participación entre las Isapres abiertas (beneficiarios de la Isapre / Σ beneficiarios de las abiertas); "
              "no es participación del sistema ni del mercado Isapre: escribe 'entre las abiertas'",
        "required": True,
        "accept": r"(?:entre|de|del total de) (?:las |los )?(?:isapres |aseguradoras )?abiert[oa]s"
                  r"|(?:mercado|segmento|grupo) (?:de (?:las )?(?:isapres |aseguradoras )?)?abiert[oa]s?",
        "reject": r"(?<!para )(?:del|de|el|al|en el) mercado|(?:del|el|al|en el) sistema|(?:de|en) la industria|del total"
                  r"|(?:de|entre) (?:todas )?las (?:isapres|aseguradoras)|(?:de|entre) las (?:isapres |aseguradoras )?cerradas",
    },
    "sistema": {
        "short": "participación en el sistema Isapre",
        "es": "participación en el sistema Isapre (abiertas y cerradas): escribe 'del sistema'",
        "required": True,
        "accept": r"(?<!para )(?:del|de|el|al|en el) (?:mercado|sistema)(?: isapre)?|(?:de|entre) (?:todas )?las isapres"
                  r"|(?:de|en) la industria|del total",
        "reject": r"abiert[oa]s|cerrad[oa]s",
    },
    "variacion_sistema": {
        "short": "parte de la variación neta del sistema",
        "es": "parte de la variación neta de beneficiarios del sistema (Δ de la Isapre / Δ del sistema); no es "
              "participación de mercado: escribe 'de la baja' o 'de la variación'",
        "required": True,
        "accept": r"baj\w*|caid\w*|cae\w*|perdid\w*|pierd\w*|perdi\w*|variacion\w*|cambio\w*|alza\w*|aument\w*"
                  r"|ganancia\w*|disminu\w*|retroce\w*|saldo|contracci\w*|merma\w*|descens\w*|crecimiento|net[oa]",
        "reject": r"(?<!para )(?:del|de|el|al) mercado|participacion",
    },
    "stock_base": {"short": "variación sobre su stock del mes base", "es": "variación sobre su propio stock del mes base",
                   "required": False},
    "stock_mes_anterior": {"short": "variación sobre el stock del mes anterior",
                           "es": "variación sobre el stock del mes anterior", "required": False},
    "cotizantes": {"short": "cargas por cotizante", "es": "cargas por cotizante (no es un porcentaje)", "required": False},
}

COPULA = r"(?:\s*,\s*|\s+)(?:(?:es|fue|era|sigue siendo|queda|quedo|se ubica como|se ubico como|como|ya es)\s+)?(?:el|la)\s+$"


@lru_cache(maxsize=None)
def _w(pat: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9·])(?:" + pat + r")(?![a-z0-9·])")


def round_half_up(x: float, decimals: int) -> float:
    q = Decimal(1).scaleb(-decimals)
    return float(Decimal(str(abs(x))).quantize(q, rounding=ROUND_HALF_UP))


def parse_num(token: str) -> tuple[float, int]:
    dec = len(token.split(",", 1)[1]) if "," in token else 0
    return float(token.replace(".", "").replace(",", ".")), dec


def card_value(words: list[str]) -> int | None:
    total, cur, seen = 0, 0, False
    for w in words:
        if w == "y":
            continue
        if w in SCALE:
            cur = (cur or 1) * SCALE[w]
            total, cur = total + cur, 0
            seen = True
        elif w in CARD:
            cur += CARD[w]
            seen = True
        else:
            return None
    return total + cur if seen else None


# ---------------------------------------------------------------------------------------------
# Insurer detection (exact names and aliases, then misspellings)

# Common words one or two edits away from an insurer name: never an insurer.
NOT_INSURERS = {"salud", "especial", "especiales", "esencia", "esenciales", "columna", "columnas", "colmenas",
                "consulta", "consultas", "fundaciones", "fundador", "fundadora", "vidas", "consulado", "isapres",
                "isapre", "fondos", "banca", "bancaria", "cruzada"}


def _lev(a: str, b: str, cap: int) -> int:
    """Levenshtein distance, stopping early once every path exceeds ``cap``."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _squash(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", fold(name))


def insurer_spans(text: str, catalog: list[dict], name_rx) -> list[tuple[int, int, str]]:
    """(start, end, key) of every insurer named in ``text`` (NFKC; positions are the same in ``fold(text)``).

    Exact names and aliases first (spaces and hyphens optional; names of ≤ 3 characters such as 'CB' or 'BMI' only
    in upper case), then misspellings: a run of 1–3 words whose letters are within edit distance 2 of a name longer
    than 5 characters, with the same first letter, unless the run is a common word (``NOT_INSURERS``).
    """
    f = fold(text)
    spans: list[tuple[int, int, str]] = []
    names: list[tuple[str, str]] = []
    for e in catalog:
        for n in e["names"]:
            sq = _squash(n)
            if not sq:
                continue
            if len(sq) <= 3:
                for mm in re.finditer(r"(?<![A-Za-z0-9])" + re.escape(n.strip()) + r"(?![A-Za-z0-9])", text):
                    spans.append((mm.start(), mm.end(), e["key"]))
                continue
            for mm in name_rx(n).finditer(f):
                spans.append((mm.start(), mm.end(), e["key"]))
            if len(sq) > 5 and not any(ch.isdigit() for ch in sq):
                names.append((sq, e["key"]))
    toks = [(m.start(), m.end(), m.group()) for m in re.finditer(r"[a-z0-9]+", f)]
    for i in range(len(toks)):
        for k in (1, 2, 3):
            if i + k > len(toks):
                break
            gap = f[toks[i + k - 2][1]:toks[i + k - 1][0]] if k > 1 else ""
            if k > 1 and not re.fullmatch(r"[\s-]+", gap):
                break
            run = "".join(t[2] for t in toks[i:i + k])
            if run in NOT_INSURERS or any(ch.isdigit() for ch in run) or len(run) < 5:
                continue
            for sq, key in names:
                if run[0] == sq[0] and _lev(run, sq, 2) <= 2:
                    spans.append((toks[i][0], toks[i + k - 1][1], key))
                    break
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    out: list[tuple[int, int, str]] = []
    for s in spans:  # longest first at each start; drop overlaps
        if out and s[0] < out[-1][1]:
            continue
        out.append(s)
    return out


# ---------------------------------------------------------------------------------------------
# Pool entries


def entry_periods(e: dict) -> list[str]:
    return [p for p in (e.get("periods") or []) if p]


def entry_scope(e: dict) -> str:
    """system / open / closed / insurer:<code>; entries without a declared scope fall back to their entity."""
    if e.get("scope"):
        return str(e["scope"])
    return f"insurer:{e['entity']}" if e.get("entity") is not None else "system"


def is_trivial(e: dict) -> bool:
    """Counts of entities (the 7 open Isapres, 3 that grow) and small integers add no information."""
    return bool(e.get("trivial")) or (e.get("unit") == "count" and abs(float(e.get("value") or 0)) <= 10)


def _entity_ok(e: dict, ents: set) -> bool:
    return e.get("entity") is None or e.get("entity") in ents


def _month(p: str) -> int:
    return int(p[5:7])


def _year_ok(ps: list[str], years: set[int]) -> bool:
    return not years or any(int(p[:4]) in years for p in ps)


def _period_ok(e: dict, ctx: dict) -> bool:
    months, years = ctx["months"], ctx["years"]
    ps = entry_periods(e)
    kind = e.get("period_kind")
    if kind is None:  # legacy entry: any named month/year must be one of its periods
        if not months and not years:
            return not e.get("requires_period")
        return any((not months or _month(p) in months) and (not years or int(p[:4]) in years) for p in ps)
    if not ps:
        return False
    pm = {_month(p) for p in ps}
    if ctx.get("window"):  # 'en doce meses': only an entry that spans exactly that window
        if kind in (None, "stock_at") or len(ps) < 2:
            return False
        a, b = ps[0], ps[-1]
        span = (int(b[:4]) - int(a[:4])) * 12 + _month(b) - _month(a)
        return span == ctx["window"] and (not months or months <= pm) and _year_ok(ps, years)
    if kind == "ytd":  # needs YTD wording that starts at the entry's base month
        base = _month(ps[0])
        ytd = base in ctx["ytd_from"] or (ctx["ytd_generic"] and base == 1)
        return ytd and months <= pm and _year_ok(ps, years)
    if not _year_ok(ps, years):
        return False
    if kind == "interval":  # between two cuts: no month, or both ends named
        return not months or (months <= pm and (len(months) >= 2 or len(years) >= 2))
    if ctx["ytd_from"] or ctx["ytd_generic"]:
        if kind == "month":
            return False  # a single month's change is not a year-to-date change
    if not months:
        return not e.get("requires_period")
    target = _month(ps[-1])
    if kind == "month":  # 'en agosto' (the month) or 'entre julio y agosto' (its two stocks)
        return target in months and months <= pm
    if kind == "stock_at":
        return target in months
    return False


def _sign_ok(m: dict, e: dict) -> bool:
    v = float(e["value"])
    if not e.get("signed", True):
        return m.get("explicit_sign") != -1
    if m.get("sign") is None or v == 0:
        return True
    return (v > 0) == (m["sign"] > 0)


def _unit_ok(m: dict, e: dict) -> bool:
    u, eu = m["unit"], e.get("unit")
    if u == "%":
        return eu == "%"
    if u == "pp":
        return eu == "pp"
    if u == "persons":
        if eu not in PERSON_UNITS:
            return False
        return not m.get("noun") or not e.get("metric") or e["metric"] == m["noun"]
    if u == "x":
        return eu in ("x", "ratio")
    if u == "share":
        return eu in ("share", "%")
    if u == "count":
        return eu == "count"
    if u == "rank":
        return eu == "rank"
    if u == "approx":
        return eu in PERSON_UNITS and (not m.get("noun") or not e.get("metric") or e["metric"] == m["noun"])
    return eu in ("ratio", "x", "count")  # a bare figure without unit


def _value_ok(m: dict, e: dict) -> bool:
    v = float(e["value"])
    if m["unit"] == "share" and e.get("unit") == "%":
        v = v / 100
    if m.get("range"):
        lo, hi = m["range"]
        return lo <= abs(v) < hi
    true, stated = abs(v), abs(m["value"]) * m.get("scale", 1)
    cmp = m.get("cmp")
    if cmp == "gt":
        return true > stated and true <= stated * (1 + BOUND_TOL_REL)
    if cmp == "lt":
        return true < stated and true >= stated * (1 - BOUND_TOL_REL)
    if cmp == "almost":
        return true < stated and stated - true <= APPROX_TOL_REL * stated + 1e-12
    if cmp == "approx":
        return abs(true - stated) <= max(APPROX_TOL_REL, m.get("tol_rel") or 0) * true + 1e-12
    if m.get("tol_rel") is not None:
        return abs(true - m["value"]) <= m["tol_rel"] * m["value"] + 1e-12
    return abs(round_half_up(v / m.get("scale", 1), m["decimals"]) - m["value"]) < 1e-9


def _scope_ok(m: dict, e: dict) -> bool:
    """The figure is credited to the entry's own scope: an insurer's figure to that insurer, a system figure to
    'el sistema' / 'las Isapres', an open-Isapres figure to 'las abiertas', a closed one to 'las cerradas'."""
    if e.get("unit") == "count":
        return True  # a count of entities is bound by its noun ('7 Isapres abiertas'), and is trivial anyway
    if m["unit"] == "rank" and not m.get("bound"):
        return True  # 'la segunda Isapre con mayor baja' describes an Isapre; it does not credit a named one
    return entry_scope(e) in (m.get("subject") or set())


def base_status(m: dict, e: dict) -> str | None:
    """None when the entry's denominator is named (or needs no naming); else 'mismatch' or 'unstated'."""
    spec = BASES.get(e.get("base") or "")
    if not spec or not spec.get("required"):
        return None
    for text in m.get("base_texts") or ():
        acc = list(re.finditer(spec["accept"], text))
        masked = text
        for mm in acc:
            masked = masked[:mm.start()] + " " * (mm.end() - mm.start()) + masked[mm.end():]
        if re.search(spec["reject"], masked):
            return "mismatch"
        if acc:
            return None
    return "unstated"


def trace(m: dict, entries: list[dict], ctx: dict) -> tuple[list[str], str | None]:
    """Ids the mention traces to; or the first failing aspect among value-equal candidates."""
    cands = [e for e in entries if _value_ok(m, e)]
    if not cands:
        return [], "not_in_pool"
    mctx = m.get("period_ctx") or ctx

    def sign_ok(e):
        if m["unit"] == "approx" and m.get("sign") is not None and not e.get("signed", True):
            return False  # 'perdió miles' is a change, never a stock level
        return _sign_ok(m, e)

    def rank_ok(e):
        return not e.get("ranking") or m.get("rank_kind") == e["ranking"]
    checks = (("unit", lambda e: _unit_ok(m, e)), ("sign", sign_ok), ("rank", rank_ok), ("entity", lambda e: _scope_ok(m, e)),
              ("period", lambda e: _period_ok(e, mctx)))
    for name, ok in checks:
        nxt = [e for e in cands if ok(e)]
        if not nxt:
            return [], f"{name}_mismatch"
        cands = nxt
    status = [base_status(m, e) for e in cands]
    if None not in status:  # every candidate is a share or rate whose denominator the text misstates or omits
        return [], "share_base_mismatch" if "mismatch" in status else "share_base_unstated"
    return [e["id"] for e, st in zip(cands, status) if st is None], None


# ---------------------------------------------------------------------------------------------
# Parsing


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;!?])\s+", str(text or "")) if s.strip()]


CLAUSE_BREAK = re.compile(r",(?!\d)|[;:()—]|\s(?:pero|mientras|aunque)\s|\sy\s(?!(?:" + MONTH_RX + r")\b)")


def _clauses(f: str) -> list[tuple[int, int]]:
    cuts = [0] + [m.end() for m in CLAUSE_BREAK.finditer(f)] + [len(f) + 1]
    return [(a, b) for a, b in zip(cuts, cuts[1:])]


def _clause_of(clauses: list[tuple[int, int]], pos: int) -> tuple[int, int]:
    return next((c for c in clauses if c[0] <= pos < c[1]), (0, 10**9))


def _period_ctx(f: str) -> dict:
    return {"months": {i + 1 for i, mo in enumerate(MONTHS) if _w(mo).search(f)},
            "ytd_from": {MONTHS.index(m.group("m")) + 1 for m in YTD_FROM.finditer(f)},
            "ytd_generic": bool(YTD_GENERIC.search(f)), "window": 12 if WINDOW_RX.search(f) else None}


def _direction(f: str, start: int, end: int) -> int | None:
    before = f[max(0, start - 60):start]
    cut = max((before.rfind(d) for d in "0123456789"), default=-1)
    before = before[cut + 1:]  # never borrow the verb of an earlier figure
    words = re.findall(r"[a-z]+", before)[-4:]
    for w in reversed(words):
        if _w(NEG).fullmatch(w) and w not in ("mas",):
            return -1
        if _w(POS).fullmatch(w) and w not in ("menos", "mas"):
            return 1
    after = re.findall(r"[a-z]+", f[end:end + 40])[:3]
    for w in after:
        if w == "menos":
            return -1
        if w == "mas":
            return 1
    return None


def _comparator(low: str, start: int) -> tuple[str | None, int]:
    """Comparator right before a figure ('más de 2,4 millones') and where it starts (``low``: lower case, accents kept)."""
    mm = COMPARATOR_RX.search(low[max(0, start - 40):start])
    if not mm:
        return None, start
    word = mm.group("cmp")
    kind = next(k for p, k in COMPARATORS if re.fullmatch(p, word))
    return kind, max(0, start - 40) + mm.start()


def _rank_kind(f: str, start: int, end: int) -> str | None:
    after = re.findall(r"[a-z]+", f[end:end + 60])[:6]
    before = list(reversed(re.findall(r"[a-z]+", f[max(0, start - 50):start])[-6:]))
    for words in (after, before):
        for w in words:
            for kind, rx in RANKING_WORDS:
                if re.fullmatch(rx, w):
                    return kind
    return None


def parse_sentence(sentence: str, *, catalog: list[dict], name_rx, key_code: dict, package_years: set[int],
                   package_months: set[tuple[int, int]]) -> dict:
    """Mentions, period context and unmapped number-like tokens of one sentence."""
    text = unicodedata.normalize("NFKC", sentence)
    spans = insurer_spans(text, catalog, name_rx)
    out = list(text)
    for a, b, _ in spans:
        for i in range(a, b):
            out[i] = "·" if not out[i].isspace() else out[i]
    masked = "".join(out)
    ents = {key_code.get(k) for _, _, k in spans} - {None}
    f = fold(masked)
    low = "".join((c.lower()[:1] or c) for c in masked)
    used = [False] * len(f)
    mentions: list[dict] = []
    unmapped: list[str] = []
    years: set[int] = set()
    errors: list[str] = []
    clauses = _clauses(f)
    # Subjects: insurers (masked spans) and group phrases, with their positions.
    markers: list[tuple[int, int, str]] = [(a, b, f"insurer:{key_code.get(k) if key_code.get(k) is not None else k}")
                                           for a, b, k in spans]
    taken = [False] * len(f)
    for rx, scope in GROUP_MARKERS:
        for mm in _w(rx).finditer(f):
            if any(taken[mm.start():mm.end()]):
                continue
            for i in range(mm.start(), mm.end()):
                taken[i] = True
            markers.append((mm.start(), mm.end(), scope))
    markers.sort()

    def is_base_phrase(mk) -> bool:
        """'entre las abiertas' / 'de participación … de las abiertas' names a denominator, not who the figure is of."""
        if mk[2].startswith("insurer:"):
            return False
        return f[mk[0]:mk[1]].startswith("entre ") or bool(re.search(r"participacion\W+(?:\w+\W+){0,3}$", f[max(0, mk[0] - 40):mk[0]]))

    def subject(a: int, b: int) -> set[str]:
        ca, cb = _clause_of(clauses, a)
        if any(ca <= mk[0] < cb and mk[2].startswith("insurer:") for mk in markers):
            # An Isapre named in the clause owns its share figures: 'la participación de Nueva Masvida entre las
            # abiertas subió 0,3 puntos' credits Nueva Masvida, not the open group.
            ins = [mk for mk in markers if ca <= mk[0] < cb and not is_base_phrase(mk)]
        else:
            ins = markers
        before = [mk for mk in ins if ca <= mk[0] and mk[1] <= a]
        if before:
            return {before[-1][2]}
        after = [mk for mk in ins if b <= mk[0] < cb]
        if after:
            ins = {mk[2] for mk in after if mk[2].startswith("insurer:")}
            return ins or {after[0][2]}
        before = [mk for mk in markers if mk[1] <= a]
        if before:
            return {before[-1][2]}
        # No subject named ('los cotizantes subieron en 1.296'): the system, never an insurer.
        return {"system"}

    sentence_ctx = _period_ctx(f)

    def period_ctx(a: int) -> dict:
        ca, cb = _clause_of(clauses, a)
        local = _period_ctx(f[ca:cb])
        if local["months"] or local["ytd_from"] or local["ytd_generic"] or local["window"]:
            return local
        return sentence_ctx

    def take(a: int, b: int) -> bool:
        if any(used[a:b]):
            return False
        for i in range(a, b):
            used[i] = True
        return True

    def add(tok, a, b, **kw):
        cmp, cstart = _comparator(low, a)
        ca, cb = _clause_of(clauses, a)
        m = {"text": tok, "sign": None, "explicit_sign": None, "decimals": 0, "scale": 1, "cmp": cmp,
             "subject": subject(a, b), "period_ctx": period_ctx(a), "base_texts": (f[ca:cb], f), **kw}
        if cmp and m["explicit_sign"] is None and m["unit"] not in ("rank", "count", "roman"):
            m["sign"] = _direction(f, cstart, b)  # 'menos de' / 'bajo' are comparators, not a direction
        mentions.append(m)
        return m

    # Quarters/halves: 'IV trimestre', 'cuarto trimestre', 'primer semestre' are period mentions.
    for mm in re.finditer(r"(?<![\w·])(?P<r>[ivx]+|primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|[1-4])\s+(?P<k>trimestre|semestre)\b", f):
        raw = masked[mm.start("r"):mm.end("r")]
        r = mm.group("r")
        n = {"i": 1, "ii": 2, "iii": 3, "iv": 4}.get(r) if re.fullmatch(r"[ivx]+", r) else None
        if re.fullmatch(r"[ivx]+", r) and raw != raw.upper():
            continue
        if n is None:
            n = int(r) if r.isdigit() else next(v for p, v in ORDINALS if re.fullmatch(p, r))
        size = 3 if mm.group("k") == "trimestre" else 6
        span = range((n - 1) * size + 1, n * size + 1)
        if not take(mm.start(), mm.end()):
            continue
        if n > (4 if size == 3 else 2) or not any(m in span for _, m in package_months):
            errors.append(f"period_not_in_package:{masked[mm.start():mm.end()]}")
        else:
            sentence_ctx["months"] |= set(m for _, m in package_months if m in span)
    # 'en doce meses', 'últimos 12 meses': a period window (read by ``_period_ctx``), never a figure.
    for mm in WINDOW_RX.finditer(f):
        take(mm.start("n"), mm.end("n"))

    def word_mentions(rx: str, build):
        for mm in re.finditer(r"(?<![a-z0-9·])(?:" + rx + r")(?![a-z0-9·])", f):
            if not take(mm.start(), mm.end()):
                continue
            built = build(mm)
            if built is None:
                for i in range(mm.start(), mm.end()):
                    used[i] = False
                continue
            if built.get("unit") in ("pp", "approx"):
                built.setdefault("sign", _direction(f, mm.start(), mm.end()))
            add(masked[mm.start():mm.end()], mm.start(), mm.end(), kind="word", **built)

    num_word = r"(?:\d+|" + CARD_ANY + r")"

    def nval(s: str) -> int | None:
        return int(s) if s.isdigit() else CARD.get(s)

    # 'uno de cada cuatro', '3 de cada 4'
    word_mentions(rf"(?P<a>{num_word}) de cada (?P<b>{num_word})",
                  lambda mm: {"value": nval(mm.group("a")) / nval(mm.group("b")), "unit": "share", "tol_rel": WORD_TOL_REL}
                  if nval(mm.group("b")) else None)
    # Digits (with optional scale and unit). Years first: a bare 19xx/20xx is a period mention.
    for mm in DIGIT_RX.finditer(f):
        num = mm.group("num")
        if not take(mm.start(), mm.end()):
            continue
        value, dec = parse_num(num)
        tok = masked[mm.start():mm.end()].strip()
        unit_given = any(mm.group(g) for g in ("pct", "pp", "veces", "scale", "noun", "cnoun"))
        if not unit_given and not mm.group("sign") and dec == 0 and re.fullmatch(r"(19|20)\d\d", num):
            if int(num) in package_years:
                years.add(int(num))
            else:
                errors.append(f"year_not_in_package:{num}")
            continue
        sign_txt = (mm.group("sign") or "").strip()
        explicit = -1 if sign_txt in ("-", "−", "–") else 1 if sign_txt == "+" else None
        unit = "%" if mm.group("pct") else "pp" if mm.group("pp") else "x" if mm.group("veces") else (
            "count" if mm.group("cnoun") else "persons" if mm.group("noun") or mm.group("scale") else "none")
        scale = SCALE.get(mm.group("scale") or "", 1)
        noun = NOUNS.get(mm.group("noun") or "") if mm.group("noun") else None
        if unit in ("persons", "none") and re.match(r"\s+por cada\b", f[mm.end():]):
            unit, noun = "x", None  # '1,3 contratos por cada desahucio' is a ratio
        elif unit == "none" and dec == 0:
            # 'los cotizantes subieron en 1.296': a metric noun earlier in the clause binds the unit.
            ca, _ = _clause_of(clauses, mm.start())
            lead = f[ca:mm.start()]
            if not re.search(r"\d", lead):
                nouns = re.findall(r"(?<![a-z])(" + NOUN_RX + r")(?![a-z])", lead)
                if nouns:
                    unit, noun = "persons", NOUNS.get(nouns[-1])
                elif value >= 100:  # 'las cerradas perdieron 1.433': a head count of whatever metric traces
                    unit = "persons"
        sign = explicit if explicit is not None else _direction(f, mm.start(), mm.end())
        add(tok, mm.start(), mm.end(), value=value, decimals=dec, scale=scale, unit=unit, noun=noun, sign=sign,
            explicit_sign=explicit, kind="digit")

    # 'medio punto', 'una décima (de punto)', 'dos décimas', 'un punto (porcentual)', 'tres puntos'
    word_mentions(r"medio punto(?: porcentual)?", lambda mm: {"value": 0.5, "decimals": 1, "unit": "pp"})
    word_mentions(rf"(?P<a>{CARD_ANY}) decimas?(?: de punto)?(?: porcentual(?:es)?)?(?! parte)",
                  lambda mm: {"value": round(CARD[mm.group("a")] * 0.1, 1), "decimals": 1, "unit": "pp"})
    word_mentions(rf"(?P<a>{CARD_ANY}) puntos?(?: porcentual(?:es)?)?",
                  lambda mm: {"value": float(CARD[mm.group("a")]), "decimals": 0, "unit": "pp"})
    # Fractions: 'la mitad', 'un tercio', 'dos tercios', 'un cuarto', 'la cuarta parte', 'un centésimo'
    word_mentions(r"mitad(?:es)?", lambda mm: {"value": 0.5, "unit": "share", "tol_rel": WORD_TOL_REL})
    word_mentions(rf"(?P<a>{CARD_ANY}) (?P<n>{'|'.join(FRACTION_NOUNS)})(?! (?:mes|lugar|trimestre|semestre|ano|puesto))",
                  lambda mm: {"value": CARD[mm.group("a")] / FRACTION_NOUNS[mm.group("n")], "unit": "share",
                              "tol_rel": WORD_TOL_REL})
    word_mentions(r"tercios?", lambda mm: {"value": 1 / 3, "unit": "share", "tol_rel": WORD_TOL_REL})
    word_mentions(rf"(?P<n>{'|'.join(PARTS)}) parte", lambda mm: {"value": 1 / PARTS[mm.group("n")], "unit": "share",
                                                                  "tol_rel": WORD_TOL_REL})
    # Multiples
    for pat, n in MULTIPLES:
        word_mentions(pat, lambda mm, n=n: {"value": float(n), "unit": "x", "tol_rel": WORD_TOL_REL})
    word_mentions(rf"(?P<a>{CARD_RX}) veces", lambda mm: {"value": float(CARD[mm.group("a")]), "unit": "x",
                                                          "tol_rel": WORD_TOL_REL})
    # 'un par de', 'par de' (never 'a la par')
    word_mentions(r"(?<!la )(?:un )?par(?= de| (?:mas|menos))", lambda mm: {"value": 2.0, "unit": "count"})
    # Magnitudes ('decenas de miles de beneficiarios')
    for pat, lo, hi in MAGNITUDES:
        word_mentions(pat + r"(?: de (?P<noun>" + NOUN_RX + r"))?",
                      lambda mm, lo=lo, hi=hi: {"value": float(lo), "range": (lo, hi), "unit": "approx",
                                                "noun": NOUNS.get(mm.group("noun") or "")})
    # Ordinals → ranks of the ranking they name; bound to an insurer only through a copula ('Colmena es la segunda').
    for pat, n in ORDINALS:
        def build_rank(mm, n=n):
            bound = None
            for a, b, scope in markers:
                if b <= mm.start() and scope.startswith("insurer:") and re.fullmatch(COPULA, f[b:mm.start()]):
                    bound = scope
            tail = f[mm.end():mm.end() + 70]
            m2 = re.match(r"[^,;:.]*?\s(?:es|fue|son)\s+(?=·)", tail)
            if bound is None and m2:
                after = [mk for mk in markers if mk[0] == mm.end() + m2.end()]
                if after and after[0][2].startswith("insurer:"):
                    bound = after[0][2]
            return {"value": float(n), "unit": "rank", "rank_kind": _rank_kind(f, mm.start(), mm.end()),
                    "bound": bound is not None, "subject_override": {bound} if bound else None}
        word_mentions(pat, build_rank)
    for m in mentions:
        if m.get("subject_override"):
            m["subject"] = m.pop("subject_override")
        else:
            m.pop("subject_override", None)
    # Cardinal runs ('veinte mil beneficiarios', 'siete Isapres')
    run = rf"(?:{CARD_RX}|mil|millon(?:es)?)(?:(?: y | )(?:{CARD_ANY}|mil|millon(?:es)?))*"
    for mm in re.finditer(r"(?<![a-z0-9·])" + run + r"(?![a-z0-9·])" + SUFFIX.replace("(?P<scale>mil|millon(?:es)?)", "(?P<scale>xx_never)"), f):
        if any(used[mm.start():mm.end()]):
            continue
        words = re.findall(r"[a-z]+", f[mm.start():mm.end()])
        core = []
        for w in words:
            if w in CARD or w in SCALE or w == "y":
                core.append(w)
            else:
                break
        val = card_value(core)
        if val is None:
            continue
        take(mm.start(), mm.end())
        tok = masked[mm.start():mm.end()]
        if mm.group("pct"):
            add(tok, mm.start(), mm.end(), value=float(val), unit="%", kind="word", sign=_direction(f, mm.start(), mm.end()))
        elif mm.group("pp"):
            add(tok, mm.start(), mm.end(), value=float(val), unit="pp", kind="word", sign=_direction(f, mm.start(), mm.end()))
        elif mm.group("noun"):
            add(tok, mm.start(), mm.end(), value=float(val), unit="persons", noun=NOUNS.get(mm.group("noun")), kind="word",
                sign=_direction(f, mm.start(), mm.end()))
        else:
            add(tok, mm.start(), mm.end(), value=float(val), unit="count", kind="word")
    # Roman numerals outside 'IV trimestre' ('siglo XXI' → 21, must be a rank or count)
    for mm in ROMAN.finditer(masked):
        if not mm.group(0) or any(used[mm.start():mm.end()]):
            continue
        take(mm.start(), mm.end())
        add(mm.group(0), mm.start(), mm.end(), value=float(_roman(mm.group(0))), unit="roman", kind="word")
    # Leftovers: any digit, Unicode numeric character or number word not consumed above.
    for i, ch in enumerate(masked):
        if used[i] or ch == "·":
            continue
        if ch.isdigit() or (unicodedata.numeric(ch, None) is not None):
            unmapped.append(ch)
        elif ch in "⁄½¼¾":
            unmapped.append(ch)
    for mm in _w(NUMBERISH).finditer(f):
        if not any(used[mm.start():mm.end()]):
            unmapped.append(masked[mm.start():mm.end()])
    # Figure-free superlatives ('Esencial es la Isapre que más crece'): a rank claim about the Isapre in the clause.
    superlatives: list[dict] = []
    for mm in SUPERLATIVE_RX.finditer(f):
        word = mm.group("w") or mm.group("w2") or mm.group("w3") or mm.group("w4")
        qw = mm.group("q") or mm.group("q2") or mm.group("q3") or "mas"
        kind = next((k for k, rx in SUPERLATIVE_KINDS if re.fullmatch(rx, word)), None)
        if kind is None:
            continue
        lead = f[max(0, mm.start() - 50):mm.start()]
        if re.search(r"(?<![a-z])(?:" + "|".join(p for p, _ in ORDINALS) + r")\s+(?:[a-z·]+\s+){0,3}$", lead):
            continue  # 'la segunda Isapre con mayor baja': the ordinal is the claim, checked above
        if re.match(r"\s+(?:del (?:ano|mes|periodo)|de la serie|en \w+ meses)", f[mm.end():]):
            continue  # 'la menor baja del año': a claim about months, not a ranking of Isapres
        ca, cb = _clause_of(clauses, mm.start())
        ins = [mk for mk in markers if mk[2].startswith("insurer:")]
        bound = ([mk for mk in ins if ca <= mk[0] and mk[1] <= mm.start()][-1:] or
                 [mk for mk in ins if mm.end() <= mk[0] < cb][:1] or [mk for mk in ins if mk[1] <= mm.start()][-1:])
        if not bound:
            continue  # no Isapre named: nothing to rank
        q = "min" if qw in ("menos", "menor") or re.fullmatch(r"chicas?|pequenas?", word) else "max"
        if (re.search(r"(?:una|uno) de (?:las|los)\s+(?:[a-z·]+\s+){0,2}$", lead)
                or re.search(r"(?<![a-z])(?:las|los|son)\s+(?:(?:isapres|aseguradoras)\s+)?$", lead)):
            q = "any"  # 'una de las que más crece', 'son las que más crecen': in the ranking at all
        superlatives.append({"text": masked[mm.start():mm.end()], "rank_kind": kind, "q": q, "subject": {bound[0][2]},
                             "period_ctx": period_ctx(mm.start())})
    ctx = {"entities": ents, "months": sentence_ctx["months"], "years": years, "ytd_from": sentence_ctx["ytd_from"],
           "ytd_generic": sentence_ctx["ytd_generic"], "window": sentence_ctx["window"]}
    for m in mentions + superlatives:
        m["period_ctx"] = {**m["period_ctx"], "years": years}
    return {"mentions": mentions, "unmapped": unmapped, "errors": errors, "ctx": ctx, "insurer_spans": spans,
            "superlatives": superlatives}


def check_superlative(sp: dict, ranks: list[dict]) -> str | None:
    """None when the superlative matches ``ranks`` (rank 1, the last rank for 'que menos', any rank for 'una de las');
    else the failing aspect."""
    rk = [r for r in ranks if r.get("ranking") == sp["rank_kind"]]
    if not rk:
        return "not_in_pool"
    values = sorted({float(r["value"]) for r in rk})
    wanted = values if sp["q"] == "any" else [values[-1]] if sp["q"] == "min" else [1.0]
    why = None
    for v in wanted:
        m = {"text": sp["text"], "value": v, "decimals": 0, "scale": 1, "cmp": None, "sign": None, "explicit_sign": None,
             "unit": "rank", "rank_kind": sp["rank_kind"], "bound": True, "subject": sp["subject"],
             "period_ctx": sp["period_ctx"], "kind": "word"}
        _, why = trace(m, ranks, sp["period_ctx"])
        if why is None:
            return None
    return why


def _roman(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for a, b in zip(s, s[1:] + " "):
        v = vals[a]
        total += -v if b != " " and vals.get(b, 0) > v else v
    return total


# ---------------------------------------------------------------------------------------------
# Redundancy


def content_stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]+", fold(unicodedata.normalize("NFKC", text))) if len(w) > 2 and w not in STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def entries_for(m: dict, pool: list[dict], ratios: list[dict], ranks: list[dict]) -> list[dict]:
    if m["kind"] == "digit":
        return pool + (ratios if m["unit"] in ("x", "none", "count") else [])
    if m["unit"] in ("pp", "approx", "persons", "%"):
        return pool + ratios
    if m["unit"] == "rank":
        return ranks
    if m["unit"] == "roman":
        return ranks + [r for r in ratios if r.get("unit") == "count"]
    return ratios + (ranks if m["unit"] == "count" else [])


def shown_ids(texts: list[str], refs: list[str], *, entries: list[dict], parse) -> set[str]:
    """D: ids traced from the displayed blocks (loose: sign, scope and period ignored; unit-less figures match any unit)."""
    d = set(refs)
    for text in texts:
        for s in sentences(text):
            parsed = parse(s)
            for m in parsed["mentions"]:
                for e in entries:
                    if not _entity_ok(e, parsed["ctx"]["entities"]):
                        continue
                    if m["unit"] == "roman":
                        continue
                    unit_ok = m["unit"] == "none" or _unit_ok(m, e) or (m["unit"] == "count" and e.get("unit") == "rank")
                    probe = dict(m, unit=m["unit"] if m["unit"] != "none" else e.get("unit"), cmp=None)
                    if unit_ok and _value_ok(probe, e):
                        d.add(e["id"])
    # A derived entry that only re-expresses one shown value (77% → 'tres de cada cuatro') is shown too.
    for e in entries:
        if len(e.get("inputs") or []) == 1 and e["inputs"][0] in d:
            d.add(e["id"])
    return d


def check(text: str, *, pool: list[dict], ratios: list[dict], ranks: list[dict], displayed: list[str],
          shown: set[str], parse, implication_terms: list[str], jaccard_max: float = 0.5) -> list[str]:
    errors: list[str] = []
    disp_stems = [content_stems(s) for t in displayed for s in sentences(t)]
    by_id = {e["id"]: e for e in pool + ratios + ranks}
    for s in sentences(text):
        parsed = parse(s)
        errors += parsed["errors"]
        errors += [f"number_unmapped:{tok}" for tok in parsed["unmapped"]]
        cited: set[str] = set()
        for m in parsed["mentions"]:
            ids, why = trace(m, entries_for(m, pool, ratios, ranks), parsed["ctx"])
            if why:
                errors.append(f"{why}:{m['text']}" if why.startswith("share_base") else f"number_{why}:{m['text']}")
            cited |= set(ids)
        for sp in parsed.get("superlatives") or []:
            why = check_superlative(sp, ranks)
            if why:
                errors.append(f"superlative_{why}:{sp['text']}")
        # A restatement in other words fails even when it carries a new figure.
        stems = content_stems(s)
        if any(jaccard(stems, d) >= jaccard_max for d in disp_stems):
            errors.append(f"restates_shown_text:{s[:40]}")
        if parsed["mentions"]:
            new = {i for i in cited - shown if not is_trivial(by_id.get(i, {}))}
            if cited and not new:
                errors.append(f"restates_shown:{s[:40]}")
            continue
        if not any(fold(t) in fold(s) for t in implication_terms):
            errors.append(f"no_implication:{s[:40]}")
    return errors


PERIOD_KIND_ES = {"month": "mes", "ytd": "desde enero (acumulado del año)", "interval": "entre cortes", "stock_at": "stock al cierre"}
SCOPE_ES = {"system": "el sistema (todas las Isapres)", "open": "las Isapres abiertas", "closed": "las Isapres cerradas"}


def describe(entry: dict, names: dict[Any, str]) -> dict:
    """Prompt line for a pool entry: id, value, unit, denominator, scope and period, never more."""
    out = {"id": entry["id"], "valor": entry["value"], "unidad": entry.get("unit")}
    base = BASES.get(entry.get("base") or "")
    if base:  # '%' alone hides the denominator: '23,3 %' among the open Isapres is not 23,3 % of the market
        out["unidad"] = f"{entry.get('unit')} ({base['short']})"
        out["denominador"] = base["es"]
    if entry.get("metric"):
        out["métrica"] = entry["metric"]
    scope = entry_scope(entry)
    if scope.startswith("insurer:"):
        out["entidad"] = names.get(entry.get("entity"), entry.get("entity"))
    else:
        out["ámbito"] = SCOPE_ES.get(scope, scope)
    if entry.get("ranking"):
        out["ranking"] = entry["ranking"]
    if entry.get("periods"):
        out["período"] = " → ".join(entry["periods"])
    if entry.get("period_kind"):
        out["tipo_período"] = PERIOD_KIND_ES.get(entry["period_kind"], entry["period_kind"])
    if is_trivial(entry):
        out["trivial"] = True
    return out
