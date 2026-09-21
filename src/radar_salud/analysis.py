from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .models import RawItem


@dataclass
class AnalysisResult:
    what_happened: str
    key_facts: List[str]
    key_numbers: List[Dict[str, str]]
    why_it_matters: str
    who_cares: List[str]
    watch_tags: List[str]
    scores: Dict[str, int]
    subcategory: str = "Estadísticas"


def analyze_superintendencia(raw: RawItem) -> AnalysisResult:
    """Deterministic first analyst for Superintendencia statistical releases.

    Later this can be complemented by LLM structured output and file-level
    analysis. For V0 it intentionally avoids unsupported interpretation.
    """
    text = f"{raw.title} {raw.raw_text}".lower()
    tags: List[str] = ["superintendencia"]
    who: List[str] = ["estrategia", "estudios"]
    economic, regulatory, scope, novelty, actionability = 45, 35, 65, 70, 60
    why = "Actualiza información oficial útil para monitorear tendencias y cambios del sistema de salud."

    if "cartera" in text or "cotizante" in text or "beneficiario" in text:
        tags += ["isapres", "cartera", "cotizantes"]
        who += ["isapres", "prestadores", "desarrollo de negocios"]
        economic, scope, actionability = 60, 80, 70
        why = "Permite seguir tamaño, composición y movimientos de la cartera Isapre con una fuente oficial comparable en el tiempo."
    if "movilidad" in text:
        tags += ["movilidad", "entradas", "salidas"]
        economic, novelty, actionability = 65, 75, 75
        why = "Permite detectar qué Isapres ganan o pierden cotizantes y cómo cambia la movilidad del mercado."
    if "ges" in text:
        tags += ["ges"]
        regulatory = max(regulatory, 60)
    if "prestacion" in text or "prestación" in text:
        tags += ["prestaciones"]
        who += ["prestadores"]

    description = raw.metadata.get("description") or raw.raw_text
    facts = [description[:400]] if description else []
    updated = raw.metadata.get("updated_through")
    if updated:
        facts.append(f"Información actualizada a {updated}.")

    numbers = [{"raw": x} for x in raw.metadata.get("extracted_numbers", [])[:10]]

    return AnalysisResult(
        what_happened=(description[:500] if description else raw.title),
        key_facts=facts,
        key_numbers=numbers,
        why_it_matters=why,
        who_cares=list(dict.fromkeys(who)),
        watch_tags=list(dict.fromkeys(tags)),
        scores={
            "economic": economic,
            "regulatory": regulatory,
            "scope": scope,
            "novelty": novelty,
            "actionability": actionability,
        },
    )
