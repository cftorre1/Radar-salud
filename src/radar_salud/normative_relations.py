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
}
# Relations that change the legal status of the target act (shown on the target card).
STATUS_RELATIONS = tuple(RELATIONS)
ISSUER = "Superintendencia de Salud"
TARGET_MAX_WORDS = 15

_ID = re.compile(
    r"\b(Oficio\s+Circular|Oficio\s+Ord(?:inario)?\.?|Circular|Resoluci[oó]n\s+Exenta)\s+"
    r"(?:(IF|IP|SS)\s*[/\-]?\s*)?N?\s*[°º]?\s*(\d[\d\.]*)", re.I)
_TARGET_KINDS = ("circular", "oficio circular")
_EFFECTS = r"(?:los\s+)?efectos\s+de"
_AGAINST = r"[^;]{0,300}?\b(?:en\s+)?contra\s+(?:de\s+)?"

# (relation, main verb, object that must follow the verb; target named <= 15 words after it).
# A verb only counts at the start of a clause or coordinated ("…, y suspende …"); never negated.
# "solicitud de suspender/suspensión" yields a suspension only with acoge / ha lugar.
_RULES = (
    ("rechaza_suspension", r"no\s+ha\s+lugar", r"^[^;]{0,40}?\bsuspensi[oó]n\s+de\s+" + _EFFECTS),
    ("suspende", r"ha\s+lugar", r"^[^;]{0,40}?\bsuspensi[oó]n\s+de\s+" + _EFFECTS),
    ("suspende", r"susp[eé]nd(?:e|ase|ense|er)",
     r"^\s+(?:(?:transitoria|temporal|provisoria)mente\s+)?" + _EFFECTS),
    ("suspende", r"acoge(?:\s+parcialmente)?", r"^[^;]{0,60}?\bsuspensi[oó]n\s+de\s+" + _EFFECTS),
    ("modifica_por_recurso", r"acoge(?:\s+parcialmente)?", r"^[^;]{0,40}?\brecursos?\b" + _AGAINST),
    ("rechaza_suspension", r"rechaza", r"^[^;]{0,40}?\bsolicitud(?:es)?\s+de\s+suspensi[oó]n\s+de\s+" + _EFFECTS),
    ("confirma", r"rechaza(?:\s+en\s+todas\s+sus\s+partes)?", r"^[^;]{0,40}?\brecursos?\b" + _AGAINST),
    ("modifica", r"modif[ií]ca(?:se)?", r"^"),
    ("deja_sin_efecto", r"d[eé]ja(?:se)?\s+sin\s+efecto", r"^"),
    ("deroga", r"der[oó]ga(?:se)?", r"^"),
    ("posterga_vigencia", r"(?:posterga|prorroga|pror[oó]gase|posp[oó]ne)",
     r"^[^;]{0,60}?\b(?:entrada\s+en\s+vigencia|vigencia|plazo)\s+de\s+"),
)
# Only acts whose subject IS that verb may modify/repeal/revoke (Resoluciones, or a Circular
# whose own subject opens with the verb).
_ACTOR_GATED = ("modifica", "deja_sin_efecto", "deroga")
_NEGATED = re.compile(r"\bno\s+(?:se\s+)?$", re.I)


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


def issuer_prefix(norm_id: str) -> str | None:
    m = _ID.search(norm_id or "")
    return (m.group(2) or "").upper() or None if m else None


def target_key(norm_id: str, default_prefix: str | None = None) -> str | None:
    """Identity including the issuing Intendencia (IF/IP/SS): ``circular-if-534``.

    An id without prefix takes the actor's (same issuer); with neither it has no key,
    so Circular IF/N°1 can never be confused with Circular IP/N°1.
    """
    m = _ID.search(norm_id or "")
    if not m:
        return None
    prefix = (m.group(2) or default_prefix or "").lower()
    if not prefix:
        return None
    number = re.sub(r"\D", "", m.group(3))
    kind = _kind(m.group(1)).lower().replace(".", "").replace(" ", "-")
    return f"{kind}-{prefix}-{number}"


def _within_words(text: str, limit: int = TARGET_MAX_WORDS) -> str:
    return " ".join(text.split()[:limit])


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
    actor_kind = _kind(_ID.search(own_title).group(1)) if _ID.search(own_title or "") else ""
    actor_prefix = issuer_prefix(own_title)
    own_key = target_key(own_title)
    out: list[dict[str, Any]] = []
    for index, clause in enumerate(_clauses(text)):
        for relation, verb, obj in _RULES:
            if relation in _ACTOR_GATED and not (
                    actor_kind == "Resolución Exenta" or (actor_kind == "Circular" and index == 0)):
                continue
            main = re.compile(r"(?:^\s*|(?:,\s*|\s)y\s+)(" + verb + r")\b", re.I)
            for m in main.finditer(clause):
                if relation in _ACTOR_GATED and actor_kind == "Circular" and m.start(1) != 0:
                    continue  # a circular's subject must open with the verb
                if _NEGATED.search(clause[:m.start(1)]):
                    continue
                o = re.search(obj, clause[m.end(1):], re.I)
                if not o:
                    continue
                window = _within_words(clause[m.end(1) + o.end():])
                target = next((normalize_id(t.group(1), t.group(2), t.group(3)) for t in _ID.finditer(window)
                               if _kind(t.group(1)).lower() in _TARGET_KINDS), None)
                if not target:
                    continue
                key = target_key(target, actor_prefix)
                if not key or key == own_key:
                    continue
                item = {"relation": relation, "target_id": target, "target_key": key,
                        "evidence": clause, "basis": BASIS}
                if not any(x["relation"] == relation and x["target_key"] == key for x in out):
                    out.append(item)
    # "No ha lugar a la suspensión" also contains "ha lugar a la suspensión": the guard wins.
    rejected = {x["target_key"] for x in out if x["relation"] == "rechaza_suspension"}
    return [x for x in out if not (x["relation"] == "suspende" and x["target_key"] in rejected
                                   and re.search(r"\bno\s+ha\s+lugar\b", x["evidence"], re.I))]


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
        key = target_key(_act_label(r)) if r.get("source_name") == ISSUER else None
        if key:
            by_key.setdefault(key, []).append(r)
    for actor in rows:
        if actor.get("source_name") != ISSUER:
            continue
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
                events = [e for e in target.get("normative_status_events") or [] 
                          if (e.get("by_url"), e.get("relation")) != (event["by_url"], event["relation"])]
                events.append(event)
                events.sort(key=lambda e: str(e.get("date") or ""), reverse=True)
                target["normative_status_events"] = events
                target["normative_status"] = events[0]["status"]
    return rows
