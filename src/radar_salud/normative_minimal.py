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
_GENERAL_KIND = re.compile(r"^(Circular|Decreto|Norma Técnica)\b", re.I)
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
    text = " ".join(str(r.get(k) or "") for k in ("title", "source_title_full", "what_happened", "why_it_matters"))
    if _PARTICULAR.search(text):
        return "particular"
    if _GENERAL_KIND.search(label):
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


def _official_subject(r: dict[str, Any], label: str) -> str:
    """SUSESO listings carry the official subject in capitals after the number."""
    raw = str(r.get("what_happened") or "")
    m = re.match(r"^\s*Circular\s+\d+\s+(.+)$", raw)
    if not m or r.get("source_name") != "Superintendencia de Seguridad Social (SUSESO)":
        return ""
    subject = m.group(1).strip().rstrip(".")
    if subject.upper() != subject:  # not the verbatim official heading
        return ""
    subject = _sentence_case(subject)
    if len(subject) > 120:
        subject = subject[:120].rsplit(" ", 1)[0] + "…"
    return subject


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


def minimal_card(r: dict[str, Any], label: str) -> dict[str, Any] | None:
    issuer = str(r.get("source_name") or "")
    if issuer not in ISSUERS or not label or not _official(r.get("source_url"), issuer):
        return None
    if act_scope(r, label) != "general" or not r.get("event_date"):
        return None
    modifies = _modified_acts(r)
    subject = _official_subject(r, label)
    scopes = [str(x) for x in _as_list(r.get("scopes")) if x]
    short = "SUSESO" if "SUSESO" in issuer else "Superintendencia de Salud"
    if subject:
        title = f"{label} · {short}: {subject}"
    elif modifies:
        title = f"{label} · {short}: modifica {' y '.join(modifies)}"
    else:
        return None  # nothing verifiable to say beyond the number: keep held
    facts = [f"Emitida por {issuer} con fecha {r['event_date']}."]
    if modifies:
        facts.append("Modifica: " + "; ".join(modifies) + ".")
    if scopes:
        facts.append("Ámbito: " + ", ".join(scopes) + ".")
    context = " ".join(facts)
    return {
        "display_title": title,
        "normative_context": context,
        "what_happened": context,
        "card_what": context,
        "why_it_matters": DISCLAIMER,
        "card_why": DISCLAIMER,
        "normative_minimal": True,
        "editorial_badge": BADGE,
        "normative_act_scope": "general",
    }
