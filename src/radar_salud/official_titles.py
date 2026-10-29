"""Deterministic short display titles for official acts (Diario Oficial and similar).

Built only from the official title text: an abbreviated act label plus the operative
clause, with legal boilerplate removed. Nothing is added except the word-level
abbreviations listed in ABBREVIATION_WORDS. The full title stays in ``title`` /
``source_title_full``.

Hard rules (each candidate short title is checked against them):

* every number, normative ID and year (or year range) in the operative part survives;
* the health service, region or comuna the act refers to survives;
* for "Modifica <act>" titles, the topic noun phrase after the last cited act ID survives;
* the output never ends on a verb, article, preposition or conjunction (no mid-phrase cut).

Target is ``MAX_CHARS`` (110). If no faithful candidate fits, ``EXTENDED_MAX_CHARS`` (140)
is allowed; if that also fails, the full operative title is returned uncut.
"""
from __future__ import annotations

import re
from collections import Counter

MAX_CHARS = 110
EXTENDED_MAX_CHARS = 140
ELLIPSIS = "…"
SEP = " · "

_HEADER = re.compile(
    r"(?:(Extracto)\s+de\s+)?\b(decreto|resoluci[oó]n)(\s+exent[oa])?\s+n[uú]mero\s+"
    r"((?:[A-Z]{1,3}\s?)?\d[\d\.]*),\s+de\s+(\d{4})\.-\s*(.*)",
    re.I | re.S,
)
_LEGACY = re.compile(  # "Decreto Exento N°66 que aprueba ..." (not lowercase cited fragments)
    r"^(Decreto|Resoluci[oó]n)(\s+[Ee]xent[oa])?\s+N[°º]\s?(\d[\d\.]*)\s+que\s+(.*)", re.S
)
# Contamination from the Diario Oficial index page: next act link, HTML attrs.
_TAIL = re.compile(r"\s+(?:Ver PDF\b|<a\b|\(CVE-).*$", re.S)

_ID = r"N° ?\d[\d\.]*(?:/\d{4})?"
_CITED_ID = re.compile(
    r"\b(?:decreto|resolución|res\.|ley|Norma(?: General)? Técnica)(?: exent[oa])? " + _ID, re.I
)
_CITED_VERBS = ("dispone|establece|aprueba|constituye|decreta|determina|declara|crea|fija|"
                "autoriza|regula|otorga")

# Stage 1 — boilerplate only (never touches IDs, numbers or topic words).
BOILERPLATE: list[tuple[str, str]] = [
    (r"\bN[º°]\s?", "N° "),
    (r",?\s+en la forma que (?:se )?indica,?", ""),
    (r"\s+por (?:el )?período que señala\b", ""),
    (r"\s+a (?:los )?grupos? de (?:la )?población que indica\b", ""),
    (r"\s+que (?:se )?(?:indican?|señalan?)\b", ""),
    (r",?\s+en cualquiera de sus presentaciones", ""),
    (r"\s+en su composición", ""),
    (r",?\s+de los Ministerios de [^,]*", ""),
    (r"\s+generales y específic[oa]s\b", ""),
    (r"\bde acuerdo al artículo \w+ del (decreto|resolución|ley)\b", r"de acuerdo al \1"),
    (r"\s+y otorga facultades extraordinarias\b", ""),
    # word-level compression of fixed phrases
    (r"\bNorma Técnica Operativa\b", "Norma Técnica"),
    (r"\b(N° [\d\.]+) que establece (?:los |las )?", r"\1: "),
    (r"\bde (?:las )?especialidades de la medicina y de la odontología\b",
     "de especialidades médicas y odontológicas"),
    (r"\bfolletos de información al profesional y al paciente\b", "folletos de información"),
    (r",?\s+para los productos farmacéuticos que contienen\b", " de productos con"),
    # cited acts: "decreto N° 4 exento, de 2026," -> "decreto exento N° 4/2026"
    (r"\b(decreto|resolución) N° ([\d\.]+) (exent[oa]),? de (\d{4}),?", r"\1 \3 N° \2/\4"),
    (r"\b(decreto|resolución) N° ([\d\.]+) (exent[oa]) de (\d{4}),?", r"\1 \3 N° \2/\4"),
    (r"\b(decreto|resolución) N° ([\d\.]+),? de (\d{4}),?", r"\1 N° \2/\3"),
    # "Modifica decreto N° 4/2026 que dispone X" -> "Modifica decreto N° 4/2026: X"
    (r"(" + _ID + r") que (?:" + _CITED_VERBS + r") (?:el |la |los |las )?", r"\1: "),
]

# Stage 2 — meaning-preserving compression, used only when stage 1 does not fit.
COMPRESSION: list[tuple[str, str]] = [
    (r"^Pone término y establece\b", "Establece"),  # the operative act is the new order
    (r"\b(subrogancia) (?:al|en el) cargo de\b", r"\1 de"),
    (r"(?-i:\b(a |de )?(?:don|doña) (?=[A-ZÁÉÍÓÚÑ]))", r"\1"),
    (r"\b(resolución)( exent[oa] " + _ID + ")", r"res.\2"),
    (r"(?-i:\bde (?:los|las) )", "de "),
    (r"\bpara otorgar (?:las )?prestaciones sujetas al\b", "del"),
    (r"\bdel que trata (la ley N° [\d\.]+)", r"de \1"),
    (r"\bpara (?:los )?establecimientos de (Atención Primaria) pertenecientes a la jurisdicción del\b",
     r"de \1 del"),
    (r"\b(atención) para las entidades administradoras de (salud municipal)\b", r"\1 de \2"),
    (r",? de acuerdo al ((?:decreto|resolución|ley) (?:exent[oa] )?" + _ID + r"),?", r" (\1),"),
    (r"^(Designa a .+?) en el cargo de\b", r"\1"),
    (r"\bsobre Estándares de (Acreditación)\b", r"sobre \1"),
    (r"\s+-\s+", "-"),
]
ABBREVIATION_WORDS = {"res", "con", "médicas", "odontológicas", "n°", "de", "del"}

_ARTICLES = {"el", "la", "los", "las", "lo", "un", "una", "unos", "unas"}
_PREPOSITIONS = {"a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "en", "entre",
                 "hacia", "hasta", "para", "por", "según", "sin", "sobre", "tras"}
_CONJUNCTIONS = {"y", "e", "o", "u", "que", "como", "ni"}
_VERBS = {"aprueba", "modifica", "establece", "establecen", "dispone", "determina", "decreta",
          "otorga", "constituye", "declara", "fija", "actualiza", "designa", "renueva", "acepta",
          "pone", "extiende", "delega", "crea", "requiere", "instruye", "indica", "señala",
          "trata", "contiene", "contienen", "regulariza", "abre", "autoriza", "llama", "deroga",
          "prorroga", "aprueban", "prevenir", "otorgar", "regula", "nombra", "renuncia"}
FORBIDDEN_END = _ARTICLES | _PREPOSITIONS | _CONJUNCTIONS | _VERBS | {"n°", "nº"}

# Clause boundaries where a trailing qualifier may be cut (cut happens before the match).
_BOUNDARY = re.compile(r",\s|;\s|:\s|\s(?:que|sobre|para|y|a|en|por|con|del que)\s")
_TOPIC_STOP = re.compile(r",\s|;\s|\s(?:que|para|a|en)\s")
_NUMBER = re.compile(r"\d[\d\.]*\d|\d")
_PLACE_HEAD = re.compile(r"\b(Servicio de Salud|Región|[Cc]omuna)\b")
_PLACE_LINK = {"de", "del", "la", "los", "las", "-", "y"}


def numbers(text: str) -> Counter:
    """Numeric tokens with multiplicity (IDs, law numbers, years; '4/2026', '2026-2028' split)."""
    return Counter(_NUMBER.findall(text or ""))


def _places(body: str) -> list[str]:
    """Named health services, regions and comunas: 'Servicio de Salud Viña del Mar-Quillota'."""
    out = []
    for m in _PLACE_HEAD.finditer(body):
        rest = body[m.end():]
        tokens = re.findall(r"\s*(-|[^\s,;:()-]+(?:-[^\s,;:()-]+)*)", rest)
        name: list[str] = []
        for tok in tokens:
            t = tok.strip()
            if t in _PLACE_LINK or t[:1].isupper():
                name.append(t)
            else:
                break
        while name and name[-1] in _PLACE_LINK:
            name.pop()
        if name and (name[0] not in _PLACE_LINK or len(name) > 1):
            # keep only the proper-name words; spacing around hyphens may be compressed
            out.append(m.group(1) + " " + " ".join(w for w in name if w != "-"))
    return out


def _topic(body: str) -> str | None:
    """For 'Modifica <act>' titles: the noun phrase after the last cited act ID."""
    if not re.match(r"Modifica\b", body):
        return None
    ids = list(_CITED_ID.finditer(body))
    if not ids:
        return None
    rest = body[ids[-1].end():]
    rest = re.sub(r"^[\s:,)]+", "", rest)
    rest = re.sub(r"^que \w+\s+", "", rest)
    topic = _TOPIC_STOP.split(rest, maxsplit=1)[0].strip(" ,;:")
    return topic or None


def _norm_words(text: str) -> str:
    return " ".join(re.sub(r"\s*-\s*", " ", text).split())


def _ends_badly(text: str) -> bool:
    words = re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ°º/]+", text.rstrip(ELLIPSIS + " ,;:").lower())
    return not words or words[-1] in FORBIDDEN_END


def _valid(candidate: str, required_numbers: Counter, places: list[str], topic: str | None) -> bool:
    if _ends_badly(candidate):
        return False
    if candidate.endswith(ELLIPSIS) and len(candidate.rstrip(ELLIPSIS).split()) < 3:
        return False
    if required_numbers - numbers(candidate):
        return False
    flat = _norm_words(candidate)
    if any(_norm_words(p) not in flat for p in places):
        return False
    if topic and _norm_words(topic) not in flat:
        return False
    return True


def _truncations(body: str) -> list[str]:
    """Body cut at each clause boundary (longest first), with an ellipsis."""
    cuts = []
    for m in _BOUNDARY.finditer(body):
        left = body[: m.start()].rstrip(" ,;:")
        # never split at " que " right after a cited act ID (it carries the act's topic)
        if m.group().strip() == "que" and re.search(_ID + r"$", left):
            continue
        # never split at " y " when the first clause has no object ("Pone término y ...")
        if m.group().strip() == "y" and len(left.split()) < 3:
            continue
        if left:
            cuts.append(left + ELLIPSIS)
    return sorted(set(cuts), key=len, reverse=True)


def _apply(rules: list[tuple[str, str]], body: str) -> str:
    for pattern, repl in rules:
        body = re.sub(pattern, repl, body, flags=re.I)
    body = " ".join(body.split()).strip(" ,;:")
    body = re.sub(r"\s+([,;:)])", r"\1", body)
    return body[:1].upper() + body[1:]


def _parse(text: str) -> tuple[str, str] | None:
    m = _HEADER.search(text)
    if m:
        extract, kind, exempt, number, year, body = m.groups()
        label = _label(kind, exempt or "", " ".join(number.split()), year, bool(extract))
    else:
        m = _LEGACY.match(text)
        if not m:
            return None
        kind, exempt, number, body = m.groups()
        label = _label(kind, exempt or "", number, None, False)
    body = _TAIL.sub("", body).strip().rstrip(".").strip()
    return (label, body) if body else None


def _label(kind: str, exempt: str, number: str, year: str | None, extract: bool) -> str:
    kind = kind.lower()
    exempt = exempt.strip().lower()
    if kind.startswith("resoluci"):
        base = "Res." + (f" {exempt}" if exempt else "")
    else:
        base = "Decreto" + (f" {exempt}" if exempt else "")
    if extract:
        base = "Extracto " + base[0].lower() + base[1:]
    return f"{base} {number}" + (f"/{year}" if year else "")


def operative_part(title: str | None) -> str | None:
    """The operative text of the act (after 'número N, de YYYY.-'), without index noise."""
    parsed = _parse(" ".join(str(title or "").split()))
    return parsed[1] if parsed else None


def short_official_title(title: str | None, limit: int = MAX_CHARS,
                         extended_limit: int = EXTENDED_MAX_CHARS) -> str | None:
    """Return a short display title for an official act, or None if not an act title."""
    parsed = _parse(" ".join(str(title or "").split()))
    if not parsed:
        return None
    label, raw = parsed
    required = numbers(raw)
    plain = _apply(BOILERPLATE, raw)
    compact = _apply(COMPRESSION, plain)
    head = label + SEP

    def ok(body: str) -> bool:
        return _valid(body, required, _places(compact), _topic(compact))

    for max_len, bodies in ((limit, (plain, compact)), (extended_limit, (compact, plain))):
        room = max_len - len(head)
        for body in bodies:
            if len(body) <= room and ok(body):
                return head + body
        for body in _truncations(compact):
            if len(body) <= room and ok(body):
                return head + body
    # nothing faithful fits: the full operative title, uncut
    return head + raw


def is_official_act(record: dict) -> bool:
    return record.get("source_name") == "Diario Oficial" or bool(
        _HEADER.search(str(record.get("title") or ""))
    )


def _has_curated_title(record: dict) -> bool:
    current = str(record.get("display_title") or "").strip()
    if not current:
        return False
    raw = {str(record.get(k) or "").strip() for k in ("title", "source_title_full")}
    return current not in raw


def apply_short_title(record: dict) -> dict:
    """Set short_title/display_title for an official act unless a curated title exists.

    A curated display_title (non-empty and different from the raw title) is never
    overwritten, whatever its length, and short_title is not set either.
    """
    if not is_official_act(record) or _has_curated_title(record):
        return record
    full = str(record.get("source_title_full") or record.get("title") or "")
    short = short_official_title(full)
    if not short:
        return record
    r = dict(record)
    r.setdefault("source_title_full", r.get("title"))
    r["display_title"] = short
    r["short_title"] = short
    return r
