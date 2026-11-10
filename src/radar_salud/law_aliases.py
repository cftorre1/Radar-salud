"""Common names of widely known Chilean health laws in display titles (Dirección 10-nov-2026).

«Decreto exento 67/2026 · Aprueba prestadores de salud del Sistema de Protección Financiera de la
ley N° 20.850» did not say what it was about; the reader knows that law as the Ley Ricarte Soto.

Deterministic and data-only: config/law_aliases.json is a curated map (law number -> common name,
with its BCN LeyChile source). No inference and no alias outside the map. A citation of a mapped law
in a display title becomes «<Nombre> (Ley <número>)»; per-law phrases made redundant by the name may
be removed. Only ``display_title``/``short_title`` change: the official ``title`` and the act
identity (type, number, year) are never touched. A rewrite that would exceed TITLE_MAX when the
original fits is not applied.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG = Path(__file__).resolve().parents[2] / "config" / "law_aliases.json"
TITLE_MAX = 110
# «ley N° 20.850», «Ley Nº20850», «LEY N.º 20.850», «ley 20.850»; not one already inside «(Ley 20.850)».
_CITATION = re.compile(r"(?<![\w(])ley\s*(?:N\s*\.?\s*[°º]\s*|N\.?\s+|n[uú]mero\s+)?(\d{1,2})\.?(\d{3})(?!\d|\.\d)", re.I)


@lru_cache(maxsize=4)
def _load(path: str) -> dict[str, dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {re.sub(r"\D", "", str(e["number"])): e for e in data.get("laws", [])}


def aliases(path: Path | None = None) -> dict[str, dict[str, Any]]:
    return _load(str(path or CONFIG))


def apply_alias(text: str, path: Path | None = None) -> str:
    """Name each mapped law cited in ``text``; unmapped laws and everything else stay as they are."""
    text = str(text or "")
    table = aliases(path)

    def name(m: re.Match) -> str:
        number = m.group(1) + m.group(2)
        entry = table.get(number)
        if not entry:
            return m.group(0)
        return f"{entry['alias']} (Ley {m.group(1)}.{m.group(2)})"

    out = _CITATION.sub(name, text)
    if out == text:
        return text
    for number, entry in table.items():
        if f"(Ley {number[:-3]}.{number[-3:]})" not in out:
            continue
        for rule in entry.get("redundant_before_citation", []):
            # Only directly before the named law: «… del Sistema de Protección Financiera de la Ley Ricarte Soto».
            out = re.sub(rule["pattern"] + r"(?=\s*" + re.escape(entry["alias"]) + r" \(Ley)",
                         rule["replacement"], out, flags=re.I)
    return re.sub(r"\s{2,}", " ", out).strip()


def apply_to_title(title: str, limit: int = TITLE_MAX, path: Path | None = None) -> str:
    """Display-title rewrite with the length guard: never push a fitting title past ``limit``."""
    new = apply_alias(title, path)
    if new != title and len(new) > limit and len(str(title)) <= limit:
        return title
    return new


def _eligible(card: dict[str, Any]) -> bool:
    types = card.get("signal_types") or []
    return (card.get("source_name") == "Diario Oficial" or card.get("event_type") in ("REGULATION", "LEGAL")
            or "Normativa" in types or "Legal" in types)


def apply(cards: list[dict[str, Any]], path: Path | None = None) -> list[dict[str, Any]]:
    out = []
    for card in cards:
        current = str(card.get("display_title") or "")
        if not current or not _eligible(card):
            out.append(card)
            continue
        new = apply_to_title(current, path=path)
        identity = str(card.get("normative_document_label") or "")
        if new == current or (identity and identity not in new):
            out.append(card)
            continue
        r = dict(card)
        r["display_title"] = new
        if r.get("short_title") == current:
            r["short_title"] = new
        for key, field in (("editorial_committee", "public_title"), ("normative_editorial", "plain_language_title")):
            if isinstance(r.get(key), dict) and r[key].get(field) == current:
                r[key] = {**r[key], field: new}
        r["law_alias_applied"] = sorted({m.group(1) + m.group(2) for m in _CITATION.finditer(current)
                                         if (m.group(1) + m.group(2)) in aliases(path)})
        out.append(r)
    return out
