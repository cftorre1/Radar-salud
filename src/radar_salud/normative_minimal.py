"""Opción A (Dirección, 26-oct-2026): ficha normativa mínima el mismo día.

A general-scope act from an official regulator reaches the feed with ONLY
verifiable facts (identity, issuer, date, affected scope, acts it modifies and
the official link) and an explicit "Sin lectura editorial" badge. What the act
changes is never paraphrased here: that interpretation needs an approved V2.1
editorial record. Acts of particular scope (individual accreditations,
authorizations, rectifications) never get an individual card.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

BADGE = "Sin lectura editorial"
# Fields produced by automated analysis or enrichment. A minimal card carries none.
INTERPRETIVE_FIELDS = (
    "key_points", "key_facts", "key_numbers", "validity_text", "risk_notes", "review_points",
    "possible_implications", "who_cares", "related_context", "related_reference_contexts",
    "related_reference_ids", "data_insights", "data_insight_evidence", "normative_subject",
    "source_documents", "summary_table", "affected_processes", "source_alternatives",
    "card_why_optional", "legacy_read_title", "watch_tags", "actionability_score",
    "regulatory_impact_score", "economic_impact_score", "scope_score", "novelty_score",
    "editorial_relevance")
# Neutral relevance until an editor reads the act: "Relevante", never "Esencial".
UNREVIEWED_RADAR_SCORE = 65
_LISTING_SCOPES = {"Prestadores": ["Prestadores"], "Isapres / Fonasa": ["Isapres", "Fonasa"]}
DISCLAIMER = ("Aún sin lectura editorial: los datos provienen del documento oficial; "
              "revisa el texto antes de decidir.")
# Diario Oficial stays held until its reader stops producing truncated titles
# and raw PDF bytes (see revisión de fuentes 26-oct-2026).
ISSUERS = {
    "Superintendencia de Salud": ("superdesalud.gob.cl",),
    "Superintendencia de Seguridad Social (SUSESO)": ("suseso.gob.cl", "suseso.cl"),
}
_PARTICULAR = re.compile(
    r"registro (?:público )?de prestadores|declara(?:r|do)? acreditad|mantiene su inscripci|mantuvo (?:a |al |la |bajo )|"
    r"inscrib(?:e|ió|irá)|entidad(?:es)? acreditadora|certificado de acreditaci|plan de corrección|"
    r"\brectifica\b|\bnombra\b|\bdesigna(?:ción)?\b|delega facultades", re.I)
# Regulator listings open individual acts with an imperative on one party.
_PARTICULAR_VERB = re.compile(r"^\s*(Inscr[íi]base|Mant[ée]ngase|Rectif[íi]quese|Autor[íi]zase|Autoriza|Des[íi]gnase|N[óo]mbrase|Ap[rR]u[ée]base el plan|Acr[ée]ditase|Canc[ée]lese)\b", re.I)
_GENERAL_KIND = re.compile(r"^(Circular|Oficio Circular|Ordinario Circular|Decreto|Norma Técnica)\b", re.I)
_MODIFIES = re.compile(r"modific|deroga|sustituy|complementa|acto modificado", re.I)


def _official(url: str, issuer: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in ISSUERS.get(issuer, ()))


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return []


def act_scope(r: dict[str, Any], label: str) -> str:
    """'general', 'particular' or 'unknown' (unknown stays held)."""
    official = str(r.get("official_subject") or "")
    if _PARTICULAR_VERB.match(official):
        return "particular"
    text = " ".join(str(r.get(k) or "") for k in ("official_subject", "title", "source_title_full", "what_happened", "why_it_matters"))
    if _PARTICULAR.search(text):
        return "particular"
    if _GENERAL_KIND.search(label):
        return "general"
    from .normative_relations import is_general_relation
    if label.lower().startswith("resolución") and is_general_relation(official, label, str(r.get("source_name") or "")):
        # Suspends / modifies / confirms a circular, per the regulator's own listing subject.
        return "general"
    refs = [str(x.get("relationship") or "") for x in _as_list(r.get("related_reference_contexts")) if isinstance(x, dict)]
    if label.lower().startswith("resolución") and any(_MODIFIES.search(x) for x in refs) and any(
            str(i).lower().startswith("circular") for i in _as_list(r.get("related_reference_ids"))):
        return "general"
    return "unknown"


def _modified_acts(r: dict[str, Any]) -> list[str]:
    out = []
    for ctx in _as_list(r.get("related_reference_contexts")):
        if isinstance(ctx, dict) and _MODIFIES.search(str(ctx.get("relationship") or "")):
            out.append(str(ctx.get("id") or "").split(",")[0].strip())
    return [x for x in dict.fromkeys(out) if x][:2]


def _trim(text: str, limit: int | None = 160) -> str:
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    return text if limit is None or len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _official_subject(r: dict[str, Any], label: str, limit: int | None = 160) -> str:
    """Verbatim regulator subject: SIS listing summary or SUSESO capitalised heading."""
    listed = str(r.get("official_subject") or "").strip()
    if listed:
        return _trim(listed[0].upper() + listed[1:], limit)
    raw = str(r.get("what_happened") or "")
    m = re.match(r"^\s*Circular\s+\d+\s+(.+)$", raw)
    if not m or r.get("source_name") != "Superintendencia de Seguridad Social (SUSESO)":
        return ""
    subject = m.group(1).strip().rstrip(".")
    if subject.upper() != subject:  # not the verbatim official heading
        return ""
    return _trim(_sentence_case(subject), limit)


_ACRONYMS = ("C.C.A.F.", "CCAF", "SENCE", "SUSESO", "ISL", "COMPIN", "SIL", "FONASA", "ISAPRE", "ISAPRES", "GES", "MINSAL")


def _sentence_case(text: str) -> str:
    """Official headings arrive in capitals; keep acronyms and roman numerals."""
    out = text.lower()
    out = re.sub(r"(^|[.!?]\s+)([a-záéíóúñ])", lambda m: m.group(1) + m.group(2).upper(), out)
    out = re.sub(r"\b(?=[ivxl]+\b)(i{1,3}|iv|vi{0,3}|ix|xi{0,3}|xiv|xv|xl|l)\b",
                 lambda m: m.group(1).upper(), out)
    for acr in _ACRONYMS:
        out = re.sub(rf"(?<![\w.]){re.escape(acr.lower())}(?![\w])", acr, out)
    out = re.sub(r"\bN[°º]", "N°", out, flags=re.I)
    return out


# Feed title (Dirección 9-nov-2026): "<identidad> · <asunto oficial acortado>". Only words of the
# official subject are kept; nothing is paraphrased. 'title' keeps the regulator's listing text.
TITLE_MAX = 110
_SUBJECT_MIN = 40
_EMISSION_TAIL = re.compile(r"[\s.,;]*(?:Fecha\s+(?:de\s+)?)?emisi[oó]n\s*:.*$", re.I | re.S)
_TRAILING_CLAUSES = (
    re.compile(r"\s+en\s+(?:la|el)\s+(?:aplicaci[oó]n|sistema|plataforma|portal|m[oó]dulo)\s+inform[aá]tic[oa]\b.*$", re.I),
)
_CLAUSE_CUT = re.compile(r"\s*[;:,]\s+|\s+(?=(?:y|e|o|u|en|para|por|con|seg[uú]n|mediante|desde|respecto)\s)", re.I)
_DANGLING = {"de", "del", "la", "el", "los", "las", "y", "e", "o", "u", "en", "a", "al", "por", "para", "con",
             "sobre", "que", "su", "sus", "un", "una"}


def _acronyms(text: str) -> str:
    """'Cobertura Adicional para Enfermedades Catastróficas (CAEC)' -> 'CAEC' when the
    acronym is spelled in the text and its letters are the initials of the words before it."""
    def repl(m: re.Match) -> str:
        acr = m.group(2)
        words = m.group(1).split()
        caps = [w for w in words if w[:1].isupper()]
        for start in range(len(words)):
            span = words[start:]
            initials = "".join(w[0] for w in span if w[:1].isupper())
            if span and span[0][:1].isupper() and initials.upper() == acr.upper() and len(caps) >= len(acr):
                return " ".join(words[:start] + [acr])
        return m.group(0)
    return re.sub(r"((?:[\wÁÉÍÓÚÑáéíóúñ]+\s+){1,10}?[\wÁÉÍÓÚÑáéíóúñ]+)\s*\(([A-ZÁÉÍÓÚÑ]{2,8})\)", repl, text)


def _inside_enumeration(text: str, m: re.Match) -> bool:
    """A cut before 'y/e/o/u' that closes 'A, B y C' would leave 'A, B': not a clause boundary."""
    if not re.match(r"\s+[yeou]\s", text[m.start():], re.I):
        return False
    return "," in re.split(r"[.;:]\s", text[:m.start()])[-1]


def short_subject(subject: str, budget: int) -> str:
    """Deterministic shortening of an official subject: drop the emission-date sentence and
    technical tails, abbreviate spelled-out acronyms, then cut at a clause boundary. Never adds words."""
    text = re.sub(r"\s+", " ", str(subject or "")).strip()
    text = _EMISSION_TAIL.sub("", text).strip().rstrip(".").strip()
    for pattern in _TRAILING_CLAUSES:
        text = pattern.sub("", text).strip()
    text = _acronyms(text)
    if text:
        text = text[0].upper() + text[1:]
    if len(text) <= budget:
        return text
    cuts = [m.start() for m in _CLAUSE_CUT.finditer(text) if _SUBJECT_MIN <= m.start() <= budget
            and not _inside_enumeration(text, m)]
    if cuts:
        return text[:max(cuts)].rstrip(" ,;:")
    head = text[:budget - 1]
    words = head.split() if text[budget - 1] == " " else head.rsplit(" ", 1)[0].split()
    while words and words[-1].lower() in _DANGLING:
        words.pop()
    return " ".join(words).rstrip(" ,;:") + "…"


def minimal_title(label: str, subject: str) -> str:
    """'Circular IF/N°541 · Aclara la determinación de la base de cálculo del deducible de la CAEC'."""
    label = " ".join(str(label or "").split())
    head = f"{label} · "
    from .law_aliases import apply_alias
    # Widely known laws by their common name (config/law_aliases.json), before shortening.
    short = short_subject(apply_alias(subject), TITLE_MAX - len(head))
    return head + short if short else label


def minimal_card(r: dict[str, Any], label: str) -> dict[str, Any] | None:
    issuer = str(r.get("source_name") or "")
    if issuer not in ISSUERS or not label or not _official(r.get("source_url"), issuer):
        return None
    if act_scope(r, label) != "general" or not r.get("event_date"):
        return None
    subject = _official_subject(r, label)
    if not subject:
        return None  # nothing verifiable to say beyond the number: keep held
    full = _official_subject(r, label, limit=None)
    title = minimal_title(label, full)
    if issuer.endswith("(SUSESO)"):
        scopes = ["Seguridad social"]
    else:
        scopes = _LISTING_SCOPES.get(str(r.get("official_listing_scope") or ""), ["Sistema de salud"])
    # Only facts read from the regulator's own listing. Referenced acts and
    # scopes come from automated PDF analysis (once bound to the wrong PDF), so
    # they never appear on a minimal card.
    context = f"Emitida por {issuer} con fecha {r['event_date']}. Asunto oficial: {full}."
    card = {field: None for field in INTERPRETIVE_FIELDS}
    card.update({
        "display_title": title,
        "normative_context": context,
        "what_happened": context,
        "card_what": context,
        "why_it_matters": DISCLAIMER,
        "card_why": DISCLAIMER,
        "normative_minimal": True,
        "editorial_badge": BADGE,
        "normative_act_scope": "general",
        # From the regulator's listing page (or the issuer), never from automated analysis.
        "scopes": scopes,
        "radar_score": UNREVIEWED_RADAR_SCORE,
    })
    from .normative_relations import extract_relations
    relations = extract_relations(str(r.get("official_subject") or ""), label, issuer)
    if relations:
        # Verbatim from the regulator's listing subject (verifiable, not interpretation).
        card["normative_relations"] = relations
        card["official_relations"] = [f"{rel['relation'].replace('_', ' ')}: {rel['target_id']}" for rel in relations]
    return card


def strip_interpretation(r: dict[str, Any]) -> dict[str, Any]:
    """Re-apply the allow-list after any later enrichment step."""
    if r.get("normative_minimal"):
        for field in INTERPRETIVE_FIELDS:
            r[field] = None
    return r
