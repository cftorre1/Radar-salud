"""Rolling accreditation pulse for providers (panel de expertos, 26-oct-2026).

Individual accreditation acts of the Superintendencia de Salud (inscriptions,
maintained registrations, authorised accrediting entities) never get their own
card. This module groups them into ONE card per 30-day window, built only from
the regulator's verbatim listing subject (``official_subject``): names, city and
counts are read from that text, never from automated PDF analysis.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable

SOURCE = "Superintendencia de Salud"
REGISTRY_URL = "https://www.superdesalud.gob.cl/registro/"
WINDOW_DAYS = 30
# Dirección 28-oct-2026: information stays available 90 days. Acts 31-90 days old get a
# second rolling card (same pattern as the sanction pulses), never an individual card.
RETENTION_DAYS = 90
WHY = ("La Garantía de Calidad GES (Ley 19.966) exige, de forma gradual según tipo y complejidad, que "
       "los prestadores institucionales que otorgan prestaciones GES estén acreditados; cada acto modifica "
       "el Registro Público de Prestadores Institucionales Acreditados de la Superintendencia.")

_PROVIDER = re.compile(
    r"al Prestador Institucional\s+(?P<name>.+?),\s+de la (?:Ciudad|Comuna|ciudad|comuna) de\s+(?P<place>[^,.]+)")
_ENTITY = re.compile(r"sociedad denominada\s+(?P<legal>.+?),\s+con nombre de fantas[íi]a\s+(?P<name>.+?)\s+para la ejecuci")
_KINDS = (
    ("new", re.compile(r"^\s*Inscr[íi]base\b", re.I)),
    ("kept", re.compile(r"^\s*Mant[ée]ngase\b", re.I)),
    ("entity", re.compile(r"^\s*Autor[íi]zase a la sociedad\b", re.I)),
    ("fix", re.compile(r"^\s*Rectif[íi]quese\b.*\b(acreditaci[óo]n|Prestador Institucional)\b", re.I | re.S)),
    ("change", re.compile(r"^\s*Modif[íi]quese\s+la\s+inscripci[óo]n\b", re.I)),
)
_CHANGED = re.compile(r"del Prestador Institucional\s+(?P<name>.+?),\s+inscrito")


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _classify(subject: str) -> tuple[str, str] | None:
    for kind, pattern in _KINDS:
        if pattern.match(subject):
            if kind in ("new", "kept"):
                m = _PROVIDER.search(subject)
                return (kind, f"{m['name'].strip()}, {m['place'].strip()}") if m else None
            if kind == "entity":
                m = _ENTITY.search(subject)
                return (kind, m["name"].strip()) if m else None
            if kind == "change":
                m = _CHANGED.search(subject)
                return (kind, m["name"].strip()) if m else None
            return (kind, "")
    return None


def _names(items: list[str], limit: int = 4) -> str:
    shown = "; ".join(items[:limit])
    return shown + (f" y {len(items) - limit} más" if len(items) > limit else "")


def accreditation_pulses(signals: Iterable[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    """Both rolling cards: last 30 days and days 31-90 (90-day availability)."""
    signals = list(signals)
    out = [accreditation_pulse(signals, as_of),
           accreditation_pulse(signals, as_of, first_day=WINDOW_DAYS, last_day=RETENTION_DAYS)]
    return [p for p in out if p]


def accreditation_pulse(signals: Iterable[dict[str, Any]], as_of: date, first_day: int = 0,
                        last_day: int = WINDOW_DAYS) -> dict[str, Any] | None:
    acts, seen = [], set()
    for s in signals:
        if s.get("source_name") != SOURCE or not s.get("official_subject"):
            continue
        url = s.get("source_url")
        if not url or url in seen:  # a re-ingested act is counted once
            continue
        day = _day(s.get("event_date"))
        # Window: ages [first_day, last_day) in calendar days before the feed's reference date.
        if not day or not first_day <= (as_of - day).days < last_day:
            continue
        seen.add(url)
        found = _classify(str(s["official_subject"]))
        if found:
            acts.append((day, found[0], found[1], s))
    if not acts:
        return None
    acts.sort(key=lambda x: x[0], reverse=True)
    by = {k: [name for _, kind, name, _ in acts if kind == k] for k, _ in _KINDS}
    def n(count, one, many):
        return f"{count} {one if count == 1 else many}"
    parts = []
    if by["new"]:
        parts.append(f"{n(len(by['new']), 'nueva inscripción', 'nuevas inscripciones')}: {_names(by['new'])}")
    if by["kept"]:
        parts.append(f"{n(len(by['kept']), 'mantiene', 'mantienen')} su acreditación: {_names(by['kept'])}")
    if by["entity"]:
        parts.append(f"{n(len(by['entity']), 'entidad acreditadora autorizada', 'entidades acreditadoras autorizadas')}: {_names(by['entity'])}")
    if by["fix"]:
        parts.append(n(len(by["fix"]), "rectificación", "rectificaciones"))
    if by["change"]:
        parts.append(f"{n(len(by['change']), 'modificación de inscripción', 'modificaciones de inscripción')}: {_names(by['change'])}")
    total = len(acts)
    period = f"últimos {last_day} días" if first_day == 0 else f"días {first_day + 1} a {last_day}"
    lead = (f"En los últimos {last_day} días" if first_day == 0
            else f"Entre {first_day + 1} y {last_day} días atrás")
    what = (f"{lead} la Superintendencia de Salud publicó "
            f"{n(total, 'acto', 'actos')} de acreditación. " + ". ".join(p[0].upper() + p[1:] for p in parts) + ".")
    latest = acts[0][0].isoformat()
    title = f"Acreditación de prestadores · {period}: {n(total, 'acto', 'actos')}"
    return {
        "title": title, "display_title": title, "source_name": SOURCE, "source_type": "official",
        "source_url": REGISTRY_URL, "event_date": latest, "publication_date": latest,
        "event_type": "ACCREDITATION_PULSE", "signal_types": ["Acreditación"], "scopes": ["Prestadores"],
        "category": "Calidad y acreditación", "what_happened": what, "card_what": what,
        "why_it_matters": WHY, "card_why": WHY, "radar_score": 60, "confidence_score": 100,
        "accreditation_counts": {k: len(v) for k, v in by.items()},
        "source_alternatives": [{"title": s.get("title"), "source_name": SOURCE, "url": s.get("source_url"), "event_date": s.get("event_date")}
                                for _, _, _, s in acts if s.get("source_url")],
        "ingestion_mode": "LIVE" if any(s.get("ingestion_mode") == "LIVE" for *_, s in acts) else "BACKFILL",
        "derived_from": "official_listing_subject", "window_days": [first_day, last_day],
    }
