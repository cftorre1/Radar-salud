from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .models import RawItem
from .quality import clean_technical_text


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


def _period(raw: RawItem) -> str:
    updated = raw.metadata.get("updated_through")
    return f" a {updated}" if updated else ""


def analyze_superintendencia(raw: RawItem) -> AnalysisResult:
    """Deterministic editorial layer for Superintendencia releases.

    It intentionally stays factual. Its job is to turn a source description into
    a concise market-intelligence signal; deeper numeric analysis belongs to the
    structured-data / BENCHMARK layer once attachments are ingested.
    """
    text = f"{raw.title} {raw.raw_text}".lower()
    tags: List[str] = ["superintendencia"]
    who: List[str] = ["estrategia", "estudios"]
    economic, regulatory, scope, novelty, actionability = 45, 35, 65, 70, 60
    why = "Actualiza una fuente oficial que puede modificar la lectura del mercado y sus tendencias."
    what = clean_technical_text(raw.metadata.get("description") or raw.raw_text) or raw.title

    if "suscripciones" in text or "desahucios" in text:
        tags += ["isapres", "cartera", "suscripciones", "desahucios"]
        who += ["isapres", "estrategia comercial", "estudios"]
        economic, scope, actionability = 60, 75, 72
        what = f"La Superintendencia actualizó{_period(raw)} las suscripciones y desahucios del sistema Isapre, incluyendo causal, sexo e Isapre."
        why = "Permite observar altas, bajas y motivos de salida, una señal temprana de presión comercial y cambios en la composición de cartera."
    elif "movilidad" in text:
        tags += ["isapres", "cartera", "cotizantes", "movilidad", "entradas", "salidas"]
        who += ["isapres", "prestadores", "desarrollo de negocios"]
        economic, novelty, actionability, scope = 65, 75, 80, 82
        what = f"La Superintendencia actualizó{_period(raw)} la movilidad de cotizantes entre Isapres y su entrada o salida del sistema, con cortes por edad, sexo y región."
        why = "Permite identificar qué Isapres ganan o pierden cotizantes, dónde ocurre la movilidad y si el mercado está acelerando entradas, salidas o cambios entre competidores."
    elif "cartera" in text or "cotizante" in text or "beneficiario" in text:
        tags += ["isapres", "cartera", "cotizantes"]
        who += ["isapres", "prestadores", "desarrollo de negocios"]
        economic, scope, actionability = 60, 80, 72
        regional = " por región" if "regional" in text or "región" in text else ""
        what = f"La Superintendencia actualizó{_period(raw)} la cartera Isapre{regional}: cotizantes, cargas, edad, sexo, tipo de trabajador y cotización percibida."
        why = "Sirve para medir tamaño y composición de cartera, participación, envejecimiento y cambios territoriales que afectan demanda, ingresos y planificación comercial."
    elif "financier" in text or "ifrs" in text or "estado de resultados" in text:
        tags += ["isapres", "finanzas", "fefi"]
        who += ["isapres", "finanzas", "estrategia", "prestadores"]
        economic, scope, actionability = 78, 88, 82
        what = f"La Superintendencia publicó{_period(raw)} la actualización financiera del sistema Isapre, con resultados, balance, indicadores y cumplimiento de estándares legales."
        why = "Es la base para comparar sostenibilidad financiera, presión de costos, resultados operacionales y diferencias entre Isapres; alimentará directamente BENCHMARK."
    elif "ges" in text or "auge" in text:
        tags += ["ges", "fonasa", "isapres"]
        who += ["isapres", "fonasa", "prestadores", "gestión de salud"]
        regulatory, scope, actionability = 65, 85, 75
        what = f"La Superintendencia actualizó{_period(raw)} los casos y tasas de uso GES de Fonasa e Isapres por problema de salud."
        why = "Permite comparar utilización GES, detectar cambios de demanda por patología y dimensionar exposición asistencial y financiera entre seguros."
    elif "series estadísticas" in text or "series estadisticas" in text:
        tags += ["isapres", "benchmark", "histórico"]
        who += ["estrategia", "estudios", "benchmark"]
        scope, actionability = 90, 78
        what = "La Superintendencia publicó/actualizó las series históricas del sistema Isapre, con varias décadas de información oficial comparable."
        why = "Esta fuente es especialmente valiosa para BENCHMARK y TREND porque permite distinguir cambios coyunturales de movimientos estructurales de largo plazo."
    elif "boletín" in text or "boletin" in text:
        tags += ["boletín", "estadísticas"]
        what = clean_technical_text(raw.metadata.get("description") or raw.title) or raw.title
        why = "Consolida indicadores oficiales del período y puede aportar cambios que luego se incorporan a BENCHMARK; no debería ocupar portada si no contiene una variación material."

    description = clean_technical_text(raw.metadata.get("description") or raw.raw_text)
    facts = [description[:400]] if description else []
    updated = raw.metadata.get("updated_through")
    if updated:
        facts.append(f"Información actualizada a {updated}.")

    numbers = [{"raw": x} for x in raw.metadata.get("extracted_numbers", [])[:10]]

    return AnalysisResult(
        what_happened=what[:650],
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
