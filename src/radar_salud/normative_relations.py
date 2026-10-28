"""Deterministic relations between SIS acts, read only from the official listing subject.

The Superintendencia de Salud lists, under "Instrucciones dictadas", general-scope
resolutions that act on a circular or oficio circular: they suspend its effects
(Ley 19.880 art. 57), reject a suspension request, accept or reject the
reposición appeals filed against it (thereby modifying or confirming it), or
leave it without effect. Those acts are normative news in their own right and
change the status of the circular they act on (e.g. Circular IF/N°534).

Nothing here is inferred from automated PDF analysis: the relation and its
target come from the regulator's verbatim listing subject ("Resumen y
modificaciones") or the act title, and every relation carries that evidence.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

BASIS = "official_listing_subject"

# relation -> (Spanish verb phrase for the acting act, status of the target act)
RELATIONS = {
    "suspende": ("suspende transitoriamente los efectos de", "Suspendida transitoriamente"),
    "rechaza_suspension": ("rechaza suspender", "Vigente: suspensión rechazada"),
    "modifica": ("modifica", "Modificada"),
    "modifica_por_recurso": ("acoge recursos contra y modifica", "Modificada por recurso"),
    "confirma": ("rechaza los recursos y confirma", "Confirmada tras recursos"),
    "deja_sin_efecto": ("deja sin efecto", "Sin efecto"),
    "deroga": ("deroga", "Derogada"),
    "posterga_vigencia": ("posterga la entrada en vigencia de", "Vigencia postergada"),
    "complementa": ("complementa", None),
}
# Relations that change the legal status of the target act (shown on the target card).
STATUS_RELATIONS = ("suspende", "rechaza_suspension", "modifica", "modifica_por_recurso",
                    "confirma", "deja_sin_efecto", "deroga", "posterga_vigencia")

_ID = re.compile(
    r"\b(Oficio\s+Circular|Oficio\s+Ord(?:inario)?\.?|Circular|Resoluci[oó]n\s+Exenta)\s+"
    r"(?:(IF|IP|SS)\s*[/\-]?\s*)?N?\s*[°º]?\s*(\d[\d\.]*)", re.I)

# Order matters: the first matching pattern decides the relation for a clause.
_PATTERNS = (
    ("rechaza_suspension", re.compile(
        r"\brechaz\w*\b[^;]{0,160}?\bsuspen(?:der|si[oó]n|da)\b", re.I)),
    ("rechaza_suspension", re.compile(
        r"\bno\s+ha\s+lugar\b[^;]{0,120}?\bsuspen", re.I)),
    ("suspende", re.compile(
        r"\b(?:suspende(?:r)?|susp[eé]ndase|suspendi[oó]|acoge\w*\b[^;]{0,80}?\bsuspensi[oó]n)\b", re.I)),
    ("deja_sin_efecto", re.compile(r"\b(?:deja(?:r)?|d[eé]jase|dejando)\s+sin\s+efecto\b", re.I)),
    ("deroga", re.compile(r"\bderog\w*\b", re.I)),
    ("posterga_vigencia", re.compile(
        r"\b(?:posterg|prorrog|difier)\w*\b[^;]{0,80}?\b(?:vigencia|entrada\s+en\s+vigor|plazo)\b", re.I)),
    ("modifica_por_recurso", re.compile(
        r"\bacoge\w*\b[^;]{0,40}?\brecursos?\b", re.I)),
    ("confirma", re.compile(r"\brechaz\w*\b[^;]{0,60}?\brecursos?\b", re.I)),
    ("modifica", re.compile(r"\bmodific\w*\b|\breemplaz\w*\b|\bsustitu\w*\b", re.I)),
    ("complementa", re.compile(r"\bcomplement\w*\b", re.I)),
)
_TARGET_KINDS = ("circular", "oficio circular")


def _kind(raw: str) -> str:
    k = " ".join(raw.split()).lower()
    if k.startswith("oficio circular"):
        return "Oficio Circular"
    if k.startswith("oficio"):
        return "Oficio Ord."
    if k.startswith("resol"):
        return "Resolución Exenta"
    return "Circular"


def normalize_id(kind: str, prefix: str | None, number: str) -> str:
    prefix = (prefix or "").upper()
    return f"{_kind(kind)} {prefix + '/' if prefix else ''}N°{number.rstrip('.')}"


def target_key(norm_id: str) -> str | None:
    """Same identity convention as the web export (``circular-534``)."""
    m = _ID.search(norm_id or "")
    if not m:
        return None
    number = re.sub(r"\D", "", m.group(3))
    kind = _kind(m.group(1)).lower().replace(".", "").replace(" ", "-")
    return f"{kind}-{number}"


def _ids(text: str) -> list[tuple[int, str]]:
    return [(m.start(), normalize_id(m.group(1), m.group(2), m.group(3))) for m in _ID.finditer(text or "")]


_ABBREV = re.compile(r"\b(?:S\.A|Ltda|Ord|N|Sr|Sra|Art|art|Res|Ex)\.$")


def _clauses(text: str) -> list[str]:
    """Sentences, without breaking at abbreviations (``Isapre Esencial S.A. de suspender``)."""
    out: list[str] = []
    for piece in re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ])", text):
        if out and _ABBREV.search(out[-1]):
            out[-1] += " " + piece
        else:
            out.append(piece)
    return out


def extract_relations(subject: str, own_title: str = "") -> list[dict[str, Any]]:
    """Relations stated by the official subject; empty when none is stated verbatim."""
    text = " ".join(str(subject or "").split())
    if not text:
        return []
    own_key = target_key(own_title)
    out: list[dict[str, Any]] = []
    for clause in _clauses(text):
        targets = [(pos, i) for pos, i in _ids(clause)
                   if _kind(i).lower() in _TARGET_KINDS and target_key(i) != own_key]
        if not targets:
            continue
        for relation, pattern in _PATTERNS:
            m = pattern.search(clause)
            if not m:
                continue
            # The target is the first instruction named after the verb (or the only one).
            after = [i for pos, i in targets if pos >= m.start()]
            target = (after or [targets[0][1]])[0]
            item = {"relation": relation, "target_id": target, "target_key": target_key(target),
                    "evidence": clause, "basis": BASIS}
            if item not in out:
                out.append(item)
            break
    return out


def relationship_text(rel: dict[str, Any]) -> str:
    verb = RELATIONS.get(rel.get("relation"), ("se relaciona con", None))[0]
    return (f"Acto sobre el que actúa: esta resolución {verb} {rel['target_id']} "
            f"(según el asunto oficial publicado por la Superintendencia).")


def is_general_relation(subject: str, own_title: str = "") -> bool:
    """A resolution acting on a general instruction (circular / oficio circular)."""
    return any(r["relation"] in STATUS_RELATIONS for r in extract_relations(subject, own_title))


def _act_label(s: dict[str, Any]) -> str:
    m = _ID.search(str(s.get("title") or ""))
    return normalize_id(m.group(1), m.group(2), m.group(3)) if m else str(s.get("title") or "")


def apply_backlinks(signals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark each instruction with the later acts that suspend/modify/confirm it.

    Adds ``normative_status_events`` (newest first) and ``normative_status``
    to the target card; never removes or rewrites existing fields.
    """
    rows = [dict(s) for s in signals]
    by_key: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        key = target_key(_act_label(r))
        if key:
            by_key.setdefault(key, []).append(r)
    for actor in rows:
        relations = actor.get("normative_relations")
        if relations is None and actor.get("official_subject"):
            # Acts processed before relations existed: same verbatim-subject rule.
            relations = extract_relations(actor["official_subject"], _act_label(actor))
        for rel in relations or []:
            if rel.get("relation") not in STATUS_RELATIONS:
                continue
            for target in by_key.get(rel.get("target_key") or "", []):
                if target is actor or target.get("source_url") == actor.get("source_url"):
                    continue
                event = {"relation": rel["relation"], "status": RELATIONS[rel["relation"]][1],
                         "by": _act_label(actor), "by_url": actor.get("source_url"),
                         "date": actor.get("event_date"), "evidence": rel.get("evidence"), "basis": BASIS}
                events = [e for e in target.get("normative_status_events") or [] if e.get("by_url") != event["by_url"]]
                events.append(event)
                events.sort(key=lambda e: str(e.get("date") or ""), reverse=True)
                target["normative_status_events"] = events
                target["normative_status"] = events[0]["status"]
    return rows
