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
    r"(?:(IF|IP|SS)\s*[/\-]?\s*)?" + r"(?:N(?:\s*\.?\s*[°º˚]|o\.?|\.)?|[°º˚])?" + r"\s*(\d[\d\.]*)", re.I)
# Number marks seen in official text for the same act: N°, Nº, N˚, No., N.º, N. (staging audit 29-oct:
# "Circular IF/N°528" and "Circular IF/Nº528" are one act).
_TARGET_KINDS = ("circular", "oficio circular")
_EFFECTS = r"(?:los\s+)?efectos\s+de"
_ADJ = r"(?:(?:transitoria|temporal|provisoria)\s+)?"  # "suspensión transitoria de los efectos de"
# The appealed instruction must be named right after "contra (de) (la|el)".
_AGAINST = (r"[^;]{0,300}?\b(?:en\s+)?contra\s+(?:de\s+)?(?:(?:la|el)\s+)?"
            r"(?=(?:Oficio\s+Circular|Circular)\s)")

# A gap that never crosses another decision verb ("Acoge … y rechaza la solicitud de suspender …").
_SE_SUSPENDE = r"(?:se\s+)?susp[eé]nd(?:e|en|ase|ense)"
_START_ONLY = {_SE_SUSPENDE}
_STOP = r"rechaz|acoge|no\s|deneg|ha\s+lugar|desist|retir|renunci|inadmisib|archiv"
_GAP = r"(?:(?!\b(?:" + _STOP + r"))[^;])"
# The request noun follows the verb within a few words ("Acoge solicitud de …", "Ha lugar, en parte,
# a lo solicitado de …"); a withdrawal/inadmissibility in between never reads as a suspension.
_SUSPEND_INFINITIVE = (r"^(?:[\s,]+(?!(?:" + _STOP + r"))\S+){0,5}?[\s,]+(?:la\s+)?"
                       r"(?:solicitud(?:es)?|petici[oó]n|lo\s+solicitado)\b" + _GAP +
                       r"{0,80}?\bde\s+suspender\s+(?:los\s+efectos\s+de\s+)?")

# (relation, finite main verb, object that must follow the verb; target named <= 15 words after it).
# A verb counts at the start of a clause, or coordinated ("…, y suspende …" after a comma, or
# "… y deroga …" once a finite main verb opened the clause); never negated, never an infinitive.
# "de suspender" / "solicitud de suspensión" only with acoge / ha lugar (suspende) or rechaza.
_RULES = (
    ("rechaza_suspension", r"no\s+ha\s+lugar", r"^[^;]{0,40}?\bsuspensi[oó]n\s+" + _ADJ + r"de\s+" + _EFFECTS),
    ("suspende", r"ha\s+lugar", r"^" + _GAP + r"{0,40}?\bsuspensi[oó]n\s+" + _ADJ + r"de\s+" + _EFFECTS),
    ("suspende", r"ha\s+lugar", _SUSPEND_INFINITIVE),
    ("suspende", r"susp[eé]nd(?:e|ase|ense)",
     r"^\s+(?:(?:transitoria|temporal|provisoria)mente\s+)?" + _EFFECTS),
    # "Se suspenden los efectos de …": only where it opens the clause.
    ("suspende", _SE_SUSPENDE,
     r"^\s+(?:(?:transitoria|temporal|provisoria)mente\s+)?" + _EFFECTS),
    ("suspende", r"acoge(?:\s+parcialmente)?", r"^" + _GAP + r"{0,60}?\bsuspensi[oó]n\s+" + _ADJ + r"de\s+" + _EFFECTS),
    ("suspende", r"acoge(?:\s+parcialmente)?", _SUSPEND_INFINITIVE),
    ("modifica_por_recurso", r"acoge(?:\s+parcialmente)?", r"^[^;]{0,40}?\brecursos?\b" + _AGAINST),
    ("rechaza_suspension", r"rechaza", r"^[^;]{0,40}?\bsolicitud(?:es)?\s+de\s+suspensi[oó]n\s+" + _ADJ + r"de\s+" + _EFFECTS),
    ("rechaza_suspension", r"rechaza", _SUSPEND_INFINITIVE),
    ("confirma", r"rechaza(?:\s+en\s+todas\s+sus\s+partes)?", r"^[^;]{0,40}?\brecursos?\b" + _AGAINST),
    ("modifica", r"modif[ií]ca(?:se)?", r"^"),
    ("deja_sin_efecto", r"d[eé]ja(?:se)?\s+sin\s+efecto", r"^"),
    ("deroga", r"der[oó]ga(?:se)?", r"^"),
    ("posterga_vigencia", r"(?:posterga|prorroga|pror[oó]gase|posp[oó]ne)",
     r"^[^;]{0,60}?\b(?:entrada\s+en\s+vigencia|vigencia|plazo)\s+de\s+"),
)
_OPENER = re.compile(r"^\s*(?:" + "|".join(dict.fromkeys(v for _, v, _ in _RULES)) + r")\b", re.I)
_GATED_OPENER = re.compile(r"^\s*(?:modif[ií]ca(?:se)?|d[eé]ja(?:se)?\s+sin\s+efecto|der[oó]ga(?:se)?)\b", re.I)
# IF/5382 wording ("Acoge la suspensión de la Circular IF/N°521"): SIS Resoluciones only, clause
# opened by acoge / ha lugar, the instruction named immediately after "suspensión".
_NARROW_SUSPENSION = re.compile(
    r"^\s*(?:acoge(?:\s+parcialmente)?|ha\s+lugar)\b" + _GAP + r"{0,40}?"
    r"\b(?:la\s+)?(?:solicitud\s+de\s+)?suspensi[oó]n\s+" + _ADJ + r"(?:de\s+(?:los\s+efectos\s+de\s+)?)?"
    r"(?:(?:la|el)\s+)?(?=(?:Oficio\s+Circular|Circular)\s)", re.I)
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


_DOUBLE_QUOTE_PAIRS = (("“", "”"), ("«", "»"))


def clean_subject(text: str | None) -> str | None:
    """Official subject text with whitespace collapsed and unmatched *double* quotes removed.

    The SIS listing often quotes the title of the act inside its subject; when the excerpt
    starts or is cut inside that quote, a lone closing quote remains (``(TEA)" y cuyo``).
    Only straight or typographic double quotes are touched: apostrophes (O’Higgins, ``'``) and
    inch marks after a digit (``12"``) are never removed, and no word is added or changed."""
    s = " ".join(str(text or "").split())
    if not s:
        return None
    for opening, closing in _DOUBLE_QUOTE_PAIRS:
        if s.count(opening) != s.count(closing):
            if not s.count(opening):
                s = s.replace(closing, "")
            elif not s.count(closing):
                s = s.replace(opening, "")
    # Only an odd number of straight quotes means one is unpaired; it is never one after a digit.
    quotes = [i for i, ch in enumerate(s) if ch == '"' and not (i and s[i - 1].isdigit())]
    if s.count('"') % 2 and quotes:
        first = quotes[0]
        # A first quote glued to the previous word (``(TEA)" y``) closes a quote that was never
        # opened: drop it; otherwise the last quote is the unpaired one.
        lone = first if first and not s[first - 1].isspace() else quotes[-1]
        s = s[:lone] + s[lone + 1:]
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s or None


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


def extract_relations(subject: str, own_title: str = "", issuer: str | None = None) -> list[dict[str, Any]]:
    """Relations stated by the official subject; empty when none is stated verbatim."""
    text = " ".join(str(subject or "").split())
    if not text:
        return []
    actor_kind = _kind(_ID.search(own_title).group(1)) if _ID.search(own_title or "") else ""
    actor_prefix = issuer_prefix(own_title)
    own_key = target_key(own_title)
    out: list[dict[str, Any]] = []

    def add(relation, target, clause):
        key = target_key(target, actor_prefix)
        if not key or key == own_key:
            return
        if not any(x["relation"] == relation and x["target_key"] == key for x in out):
            out.append({"relation": relation, "target_id": target, "target_key": key,
                        "evidence": clause, "basis": BASIS})

    def first_target(window):
        return next((normalize_id(t.group(1), t.group(2), t.group(3)) for t in _ID.finditer(window)
                     if _kind(t.group(1)).lower() in _TARGET_KINDS), None)

    for index, clause in enumerate(_clauses(text)):
        opened = bool(_OPENER.match(clause))
        gated_ok = actor_kind == "Resolución Exenta" or (
            actor_kind == "Circular" and index == 0 and bool(_GATED_OPENER.match(clause)))
        for relation, verb, obj in _RULES:
            if relation in _ACTOR_GATED and not gated_ok:
                continue
            main = re.compile(r"(?:^\s*|(?P<comma>,)\s*y\s+|\sy\s+)(?P<v>" + verb + r")\b", re.I)
            for m in main.finditer(clause):
                if verb in _START_ONLY and clause[:m.start("v")].strip():
                    continue  # clause-initial form only
                if m.start("v") > 0 and not m.group("comma") and not opened:
                    continue  # " y VERB" only after a comma or inside a clause a finite verb opened
                if _NEGATED.search(clause[:m.start("v")]):
                    continue
                o = re.search(obj, clause[m.end("v"):], re.I)
                if not o:
                    continue
                target = first_target(_within_words(clause[m.end("v") + o.end():]))
                if target:
                    add(relation, target, clause)
        if issuer == ISSUER and actor_kind == "Resolución Exenta":
            n = _NARROW_SUSPENSION.match(clause)
            if n:
                t = _ID.match(clause, n.end())
                if t and _kind(t.group(1)).lower() in _TARGET_KINDS:
                    add("suspende", normalize_id(t.group(1), t.group(2), t.group(3)), clause)
    # "No ha lugar a la suspensión" also contains "ha lugar a la suspensión": the guard wins.
    rejected = {x["target_key"] for x in out if x["relation"] == "rechaza_suspension"}
    return [x for x in out if not (x["relation"] == "suspende" and x["target_key"] in rejected
                                   and re.search(r"\bno\s+ha\s+lugar\b", x["evidence"], re.I))]


def relationship_text(rel: dict[str, Any]) -> str:
    verb = RELATIONS.get(rel.get("relation"), ("se relaciona con", None))[0]
    return (f"Acto sobre el que actúa: esta resolución {verb} {rel['target_id']} "
            f"(según el asunto oficial publicado por la Superintendencia).")


def is_general_relation(subject: str, own_title: str = "", issuer: str | None = None) -> bool:
    """A resolution acting on a general instruction (circular / oficio circular)."""
    return any(r["relation"] in STATUS_RELATIONS for r in extract_relations(subject, own_title, issuer))


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
            relations = extract_relations(actor["official_subject"], _act_label(actor), ISSUER)
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


def load_listing_index(path) -> dict[str, dict[str, Any]]:
    """Official SIS listing identities (``data/state/sis_normative_index.json``); empty if absent."""
    import json
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return dict(json.loads(p.read_text(encoding="utf-8")).get("acts") or {})
    except (OSError, ValueError, AttributeError):
        return {}


def related_documents(card: dict[str, Any], history: Iterable[dict[str, Any]],
                      index: dict[str, dict[str, Any]] | None = None,
                      in_feed: Iterable[str] = ()) -> list[dict[str, Any]]:
    """"Documentos relacionados" for an act that suspends/modifies/confirms an instruction,
    whatever the age of that instruction (Dirección 28-oct-2026).

    Resolution order, never inventing a URL: (1) our own record of the original in history,
    at any date; (2) the regulator's listing index (URL read from the official listing);
    (3) the identity only, without a link.
    """
    if card.get("source_name") != ISSUER:
        return []
    relations = card.get("normative_relations")
    if relations is None and card.get("official_subject"):
        relations = extract_relations(card["official_subject"], _act_label(card), ISSUER)
    if not relations:
        return []
    by_key: dict[str, dict[str, Any]] = {}
    for row in history:
        if row.get("source_name") != ISSUER or not row.get("source_url"):
            continue
        key = target_key(_act_label(row))
        if key and (key not in by_key or str(row.get("event_date") or "") > str(by_key[key].get("event_date") or "")):
            by_key[key] = row
    feed = set(in_feed)
    out, seen = [], set()
    for rel in relations:
        key = rel.get("target_key")
        if not key or key in seen:
            continue
        seen.add(key)
        text = relationship_text(rel)
        original = by_key.get(key)
        listed = (index or {}).get(key)
        if original and original.get("source_url") != card.get("source_url"):
            out.append({"title": original.get("display_title") or original.get("title") or rel["target_id"],
                        "summary": clean_subject(original.get("official_subject") or (listed or {}).get("official_subject")),
                        "relationship": text, "url": original["source_url"], "event_date": original.get("event_date"),
                        "verified": True, "basis": "history_record", "target_id": rel["target_id"],
                        "history_ficha": {"title": original.get("title"), "event_date": original.get("event_date"),
                                          "source_url": original["source_url"],
                                          "in_feed": original["source_url"] in feed}})
        elif listed and listed.get("url"):
            out.append({"title": listed.get("id") or rel["target_id"], "summary": clean_subject(listed.get("official_subject")),
                        "relationship": text, "url": listed["url"], "event_date": listed.get("event_date"),
                        "verified": True, "basis": "official_listing_index", "target_id": rel["target_id"]})
        else:
            out.append({"title": rel["target_id"], "summary": None, "relationship": text, "url": None,
                        "event_date": None, "verified": False, "basis": "id_only", "target_id": rel["target_id"]})
    return out
