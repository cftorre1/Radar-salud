"""Ámbito de la plataforma (Dirección 12-nov-2026: «Sacarlas de la plataforma completa lo que no tenga relación con salud»).

A norm is outside health when its own official wording is about cajas de compensación (crédito social, afiliación),
servicios de bienestar del sector público, subsidio al empleo / SENCE or family bonuses, and says nothing about health
(licencias médicas, SIL, Ley 16.744, enfermedad, salud). Salud ocupacional (Ley 16.744), licencias médicas and SIL stay.
The norms Dirección retired by name (data/normativa/fuera_de_ambito.json) are checked first, together with SUSESO
news items presenting them; the rule then covers future norms. History is kept; the norm is hidden everywhere.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DECIDED = Path(__file__).resolve().parents[2] / "data/normativa/fuera_de_ambito.json"

NON_HEALTH = re.compile(
    r"\bC\.?\s?C\.?\s?A\.?\s?F\.?(?![a-z])|cajas? de compensaci[oó]n|cr[eé]dito social|servicios? de bienestar|"
    r"subsidio al empleo|servicio nacional de capacitaci[oó]n|\bSENCE\b|\bbono\b[^.]{0,60}ni[ñn]ez", re.I)
HEALTH = re.compile(
    r"licencias? m[eé]dicas?|subsidios? por incapacidad|\bSIL\b|salud|enfermedad|accidentes? del trabajo|16\.?744|"
    r"prestaci[oó]n(?:es)? m[eé]dicas?", re.I)
FIELDS = ("subject", "official_subject", "display_title", "title", "what_happened", "normative_context")
REASON = "fuera_del_ambito_salud"


def _is_norm(r: dict[str, Any]) -> bool:
    return (r.get("event_type") == "REGULATION" or "Normativa" in (r.get("signal_types") or [])
            or bool(r.get("emisor")))  # registry records carry «emisor»


@lru_cache(maxsize=1)
def decided_numbers() -> frozenset[str]:
    """Numbers of the norms Dirección retired by name (checked before the rule, so later text cannot bring them back)."""
    try:
        labels = json.loads(DECIDED.read_text(encoding="utf-8")).get("labels") or []
    except (OSError, ValueError):
        return frozenset()
    return frozenset(m.group(1) for x in labels if (m := re.search(r"N[°º]\s*(\d+)", str(x))))


_CITED = re.compile(r"\bCircular(?:es)?\s*(?:N[°º.]?\s*)?(\d{3,5})\b", re.I)


def _numbers(r: dict[str, Any]) -> set[str]:
    text = " ".join(str(r.get(f) or "") for f in ("normative_document_label", "legal_identity", "label", "title",
                                                     "display_title", "subject", "what_happened", "card_what"))
    return set(_CITED.findall(text))


def _suseso(r: dict[str, Any]) -> bool:
    return "SUSESO" in str(r.get("source_name") or r.get("emisor") or "") or "suseso.gob.cl" in str(
        r.get("source_url") or r.get("url") or "")


def presents_retired_norm(r: dict[str, Any]) -> bool:
    """A SUSESO news item that presents a circular Dirección retired (review #189: 3927 and 3928 news cards)."""
    return isinstance(r, dict) and _suseso(r) and bool(_numbers(r) & decided_numbers())


def outside_health(r: dict[str, Any]) -> bool:
    if not isinstance(r, dict):
        return False
    if presents_retired_norm(r):
        return True
    if not _is_norm(r):
        return False
    text = " ".join(str(r.get(f) or "") for f in FIELDS)
    issuer = str(r.get("source_name") or r.get("emisor") or "")
    if "Superintendencia de Salud" in issuer:
        text = text.replace("Superintendencia de Salud", "")
    return bool(NON_HEALTH.search(text)) and not HEALTH.search(text)
