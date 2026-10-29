"""Deterministic short display titles for official acts (Diario Oficial and similar).

Built only from the official title text: an abbreviated act label plus the operative
clause, with legal boilerplate removed. Nothing is added except the word-level
abbreviations listed in ABBREVIATIONS. The full title stays in ``title`` /
``source_title_full``.
"""
from __future__ import annotations

import re

MAX_CHARS = 110

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

# (pattern, replacement): word-level abbreviations/removals of the source wording.
# Replacements may only use words from the source or from ABBREVIATION_WORDS.
ABBREVIATIONS: list[tuple[str, str]] = [
    # boilerplate
    (r",?\s+(?:de acuerdo (?:al?|con)|conforme (?:al?|con))\b.*$", ""),
    (r",?\s+en la forma que (?:se )?indica,?", ""),
    (r"\s+que (?:se )?(?:indican?|señalan?)\b", ""),
    (r",?\s+en cualquiera de sus presentaciones", ""),
    (r"\s+en su composición", ""),
    (r",?\s+de los Ministerios de [^,]*", ""),
    (r"\s+generales y específic[oa]s\b", ""),
    # word-level compression
    (r"\bNorma Técnica Operativa\b", "Norma Técnica"),
    (r"\b(N[°º] ?[\d\.]+) que establece (?:los |las )?", r"\1: "),
    (r"\bde (?:las )?especialidades de la medicina y de la odontología\b", "de especialidades médicas y odontológicas"),
    (r"\bfolletos de información al profesional y al paciente\b", "folletos de información"),
    (r",?\s+para los productos farmacéuticos que contienen\b", " de productos con"),
    (r"\b(decreto|resolución) N[°º] ?([\d\.]+) (exent[oa]),? de (\d{4}),?", r"\1 \3 N° \2/\4"),
    (r"\b(decreto|resolución) N[°º] ?([\d\.]+),? de (\d{4}),?", r"\1 N° \2/\3"),
]
ABBREVIATION_WORDS = {"res", "con", "médicas", "odontológicas", "n°", "de"}


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


def _clauses(body: str) -> list[str]:
    """Split at clause boundaries: commas, semicolons, relatives and coordination."""
    return [p for p in re.split(r"(?=,\s|;\s|\s(?:que|sobre|para|del que|y)\s)", body) if p]


def _fit(label: str, body: str, limit: int) -> str:
    sep = " · "
    if len(label) + len(sep) + len(body) <= limit:
        return f"{label}{sep}{body}"
    out = ""
    for part in _clauses(body):
        if len(label) + len(sep) + len(out + part) + 1 > limit:
            break
        out += part
    out = out.rstrip(" ,;:")
    if not out:  # first clause alone too long: cut at the last word boundary
        out = body[: limit - len(label) - len(sep) - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{label}{sep}{out}…"


def short_official_title(title: str | None, limit: int = MAX_CHARS) -> str | None:
    """Return a short display title for an official act, or None if not an act title."""
    text = " ".join(str(title or "").split())
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
    body = _TAIL.sub("", body).strip().rstrip(".")
    if not body:
        return None
    for pattern, repl in ABBREVIATIONS:
        body = re.sub(pattern, repl, body, flags=re.I)
    body = " ".join(body.split()).strip(" ,;:")
    body = body[0].upper() + body[1:]
    return _fit(label, body, limit)


def is_official_act(record: dict) -> bool:
    return record.get("source_name") == "Diario Oficial" or bool(
        _HEADER.search(str(record.get("title") or ""))
    )


def apply_short_title(record: dict) -> dict:
    """Set display_title to the short act title unless a curated short title exists."""
    if not is_official_act(record):
        return record
    full = str(record.get("source_title_full") or record.get("title") or "")
    short = short_official_title(full)
    if not short:
        return record
    r = dict(record)
    current = str(r.get("display_title") or "").strip()
    if current and current != str(r.get("title") or "").strip() and len(current) <= MAX_CHARS:
        return r  # keep reviewed/curated titles
    r.setdefault("source_title_full", r.get("title"))
    r["display_title"] = short
    r["short_title"] = short
    return r
