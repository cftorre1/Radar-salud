"""Ámbito de la plataforma (Dirección 12-nov-2026: «Sacarlas de la plataforma completa lo que no tenga relación con salud»).

A norm is outside health when its own official wording is about cajas de compensación (crédito social, afiliación),
servicios de bienestar del sector público, subsidio al empleo / SENCE or family bonuses, and says nothing about health
(licencias médicas, SIL, Ley 16.744, enfermedad, salud). Salud ocupacional (Ley 16.744), licencias médicas and SIL stay.
Only official-wording fields are read, never automated analysis. History is kept; the norm is hidden everywhere.
"""
from __future__ import annotations

import re
from typing import Any

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


def outside_health(r: dict[str, Any]) -> bool:
    if not isinstance(r, dict) or not _is_norm(r):
        return False
    text = " ".join(str(r.get(f) or "") for f in FIELDS)
    issuer = str(r.get("source_name") or r.get("emisor") or "")
    if "Superintendencia de Salud" in issuer:
        text = text.replace("Superintendencia de Salud", "")
    return bool(NON_HEALTH.search(text)) and not HEALTH.search(text)
