"""Lectura Alicanto figure verifier (Dirección 28-oct-2026 15:25: "puede tener cifras, solo que no caiga en ser
redundantes, debe aportar algo más").

1. Parse.   NFKC, insurer names masked (so 'Vida Tres' is not a number), then every figure mention becomes
            (value, decimals, sign, unit, entity, period). Sign: +/− or the nearest direction word. Unit: %, pp,
            persons (personas/beneficiarios/cotizantes/cargas/contratos/desahucios), 'veces', or none (ratio).
            Entity: the insurers named in the same sentence. Period: the months/years named in the sentence.
2. Trace.   Every digit mention must equal a ``lectura_pool`` entry (declared by the family builder, never the whole
            package) rounded half-up to the shown precision, with matching unit, sign, entity and period. Years
            are allowed only when they are package periods.
3. Words.   A closed lexicon (doble, triple, quíntuple, mitad, tercio, cuarto, par, décima, centésimo, ordinals,
            Roman numerals, 'medio punto', 'uno de cada N', decenas/miles…) maps each number word to a value that
            must equal a ``derived_ratios`` or ``ranks`` entry within display tolerance (pp words and magnitudes
            may also match ``lectura_pool``). Any other number-like token fails.
4. Adds.    D = value ids traced from the headline, dek, KPIs, tab texts and facts. A sentence with figures must
            cite at least one traced id outside D (else ``restates_shown``); a sentence without figures must have
            content-word Jaccard < 0.5 against every displayed sentence and name an audience or implication.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")
PERSON_UNITS = {"personas", "cotizantes", "contratos", "beneficiarios", "cargas", "desahucios"}
NOUNS = {"personas": None, "beneficiarios": "beneficiarios", "cotizantes": "cotizantes", "cargas": "cargas",
         "afiliados": None, "contratos": "contratos", "desahucios": "desahucios"}
WORD_TOL_REL = 0.05  # display tolerance of a multiple or fraction word ('doble' = 1,9–2,1)

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
          r"(?:\s+(?:de\s+)?(?P<noun>personas|beneficiarios|cotizantes|cargas|afiliados|contratos|desahucios)\b)?")
DIGIT_RX = re.compile(r"(?<![\w.,])" + DIGIT_NUM + r"(?![\w])" + SUFFIX)
STOP = set("""a al algo ante antes aun bajo cada como con contra cual cuando de del desde donde dos durante e el ella
ellas ello ellos en entre era es esa ese eso esta este esto estos estas fue ha han hasta hay la las le les lo los mas
me mientras muy ni no nos o otra otro para pero poco por que quien se segun ser si sin sino sobre son su sus tambien
tan tanto te tiene tienen todo todos tras u un una uno unos y ya""".split())


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
            if SCALE[w] >= 1_000_000:
                total, cur = total + cur, 0
            else:
                total, cur = total + cur, 0
            seen = True
        elif w in CARD:
            cur += CARD[w]
            seen = True
        else:
            return None
    return total + cur if seen else None


# ---------------------------------------------------------------------------------------------
# Pool entries


def entry_periods(e: dict) -> list[str]:
    return [p for p in (e.get("periods") or []) if p]


def _entity_ok(e: dict, ents: set) -> bool:
    return e.get("entity") is None or e.get("entity") in ents


def _period_ok(e: dict, months: set[int], years: set[int]) -> bool:
    ps = entry_periods(e)
    if not months and not years:
        return not e.get("requires_period")
    for p in ps:
        y, m = int(p[:4]), int(p[5:7])
        if (not months or m in months) and (not years or y in years):
            return True
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
        return eu == "x"
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
    if m.get("tol_rel") is not None:
        return abs(abs(v) - m["value"]) <= m["tol_rel"] * m["value"] + 1e-12
    return abs(round_half_up(v / m.get("scale", 1), m["decimals"]) - m["value"]) < 1e-9


def trace(m: dict, entries: list[dict], ctx: dict) -> tuple[list[str], str | None]:
    """Ids the mention traces to; or the first failing aspect among value-equal candidates."""
    cands = [e for e in entries if _value_ok(m, e)]
    if not cands:
        return [], "not_in_pool"
    def entity_ok(e):
        if m["unit"] == "approx":  # a magnitude word is fuzzy: it must name exactly whose figure it is
            return e.get("entity") in ctx["entities"] if ctx["entities"] else e.get("entity") is None
        return _entity_ok(e, ctx["entities"])

    def sign_ok(e):
        if m["unit"] == "approx" and m.get("sign") is not None and not e.get("signed", True):
            return False  # 'perdió miles' is a change, never a stock level
        return _sign_ok(m, e)
    checks = (("unit", lambda e: _unit_ok(m, e)), ("sign", sign_ok), ("entity", entity_ok),
              ("period", lambda e: _period_ok(e, ctx["months"], ctx["years"])))
    for name, ok in checks:
        nxt = [e for e in cands if ok(e)]
        if not nxt:
            return [], f"{name}_mismatch"
        cands = nxt
    return [e["id"] for e in cands], None


# ---------------------------------------------------------------------------------------------
# Parsing


def _mask(text: str, catalog: list[dict], name_rx) -> str:
    folded = fold(text)
    out = list(text)
    for e in catalog:
        for n in e["names"]:
            if len(fold(n)) < 4:
                continue
            for mm in name_rx(n).finditer(folded):
                for i in range(mm.start(), mm.end()):
                    out[i] = "·" if not out[i].isspace() else out[i]
    return "".join(out)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;!?])\s+", str(text or "")) if s.strip()]


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


def parse_sentence(sentence: str, *, catalog: list[dict], name_rx, insurers_in, package_years: set[int],
                   package_months: set[tuple[int, int]]) -> dict:
    """Mentions, period context and unmapped number-like tokens of one sentence."""
    text = unicodedata.normalize("NFKC", sentence)
    ents = insurers_in(text)
    masked = _mask(text, catalog, name_rx)
    f = fold(masked)
    used = [False] * len(f)
    mentions: list[dict] = []
    unmapped: list[str] = []
    months: set[int] = {i + 1 for i, mo in enumerate(MONTHS) if _w(mo).search(f)}
    years: set[int] = set()
    errors: list[str] = []

    def take(a: int, b: int) -> bool:
        if any(used[a:b]):
            return False
        for i in range(a, b):
            used[i] = True
        return True

    def add(tok, **kw):
        mentions.append({"text": tok, "sign": None, "explicit_sign": None, "decimals": 0, "scale": 1, **kw})

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
            months |= set(m for _, m in package_months if m in span)

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
            add(masked[mm.start():mm.end()], kind="word", **built)

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
        unit_given = any(mm.group(g) for g in ("pct", "pp", "veces", "scale", "noun"))
        if not unit_given and not mm.group("sign") and dec == 0 and re.fullmatch(r"(19|20)\d\d", num):
            if int(num) in package_years:
                years.add(int(num))
            else:
                errors.append(f"year_not_in_package:{num}")
            continue
        sign_txt = (mm.group("sign") or "").strip()
        explicit = -1 if sign_txt in ("-", "−", "–") else 1 if sign_txt == "+" else None
        unit = "%" if mm.group("pct") else "pp" if mm.group("pp") else "x" if mm.group("veces") else (
            "persons" if mm.group("noun") or mm.group("scale") else "none")
        scale = SCALE.get(mm.group("scale") or "", 1)
        noun = NOUNS.get(mm.group("noun") or "") if mm.group("noun") else None
        if mm.group("scale") and not mm.group("noun"):
            unit = "persons"
        sign = explicit if explicit is not None else _direction(f, mm.start(), mm.end())
        add(tok, value=value, decimals=dec, scale=scale, unit=unit, noun=noun, sign=sign, explicit_sign=explicit, kind="digit")

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
        word_mentions(pat + r"(?: de (?P<noun>personas|beneficiarios|cotizantes|cargas|afiliados|contratos|desahucios))?",
                      lambda mm, lo=lo, hi=hi: {"value": float(lo), "range": (lo, hi), "unit": "approx",
                                                "noun": NOUNS.get(mm.group("noun") or "")})
    # Ordinals → ranks
    for pat, n in ORDINALS:
        word_mentions(pat, lambda mm, n=n: {"value": float(n), "unit": "rank"})
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
            add(tok, value=float(val), unit="%", kind="word", sign=_direction(f, mm.start(), mm.end()))
        elif mm.group("pp"):
            add(tok, value=float(val), unit="pp", kind="word", sign=_direction(f, mm.start(), mm.end()))
        elif mm.group("noun"):
            add(tok, value=float(val), unit="persons", noun=NOUNS.get(mm.group("noun")), kind="word",
                sign=_direction(f, mm.start(), mm.end()))
        else:
            add(tok, value=float(val), unit="count", kind="word")
    # Roman numerals outside 'IV trimestre' ('siglo XXI' → 21, must be a rank or count)
    for mm in ROMAN.finditer(masked):
        if not mm.group(0) or any(used[mm.start():mm.end()]):
            continue
        take(mm.start(), mm.end())
        add(mm.group(0), value=float(_roman(mm.group(0))), unit="roman", kind="word")
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
    return {"mentions": mentions, "unmapped": unmapped, "errors": errors,
            "ctx": {"entities": ents, "months": months, "years": years}}


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
        return pool + (ratios if m["unit"] in ("x", "none") else [])
    if m["unit"] in ("pp", "approx", "persons", "%"):
        return pool + ratios
    if m["unit"] == "rank":
        return ranks
    if m["unit"] == "roman":
        return ranks + [r for r in ratios if r.get("unit") == "count"]
    return ratios + (ranks if m["unit"] == "count" else [])


def shown_ids(texts: list[str], refs: list[str], *, entries: list[dict], parse) -> set[str]:
    """D: ids traced from the displayed blocks (loose: sign and period ignored; unit-less figures match any unit)."""
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
                    probe = dict(m, unit=m["unit"] if m["unit"] != "none" else e.get("unit"))
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
    for s in sentences(text):
        parsed = parse(s)
        errors += parsed["errors"]
        errors += [f"number_unmapped:{tok}" for tok in parsed["unmapped"]]
        cited: set[str] = set()
        for m in parsed["mentions"]:
            ids, why = trace(m, entries_for(m, pool, ratios, ranks), parsed["ctx"])
            if why:
                errors.append(f"number_{why}:{m['text']}")
            cited |= set(ids)
        if parsed["mentions"]:
            if cited and not (cited - shown):
                errors.append(f"restates_shown:{s[:40]}")
            continue
        stems = content_stems(s)
        if any(jaccard(stems, d) >= jaccard_max for d in disp_stems):
            errors.append(f"restates_shown_text:{s[:40]}")
        if not any(fold(t) in fold(s) for t in implication_terms):
            errors.append(f"no_implication:{s[:40]}")
    return errors


def describe(entry: dict, names: dict[Any, str]) -> dict:
    """Prompt line for a pool entry: id, value, unit, entity and period, never more."""
    out = {"id": entry["id"], "valor": entry["value"], "unidad": entry.get("unit")}
    if entry.get("metric"):
        out["métrica"] = entry["metric"]
    if entry.get("entity") is not None:
        out["entidad"] = names.get(entry["entity"], entry["entity"])
    if entry.get("periods"):
        out["período"] = " → ".join(entry["periods"])
    return out
