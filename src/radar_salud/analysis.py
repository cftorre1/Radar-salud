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
    u=raw.metadata.get("updated_through")
    return f" a {u}" if u else ""

def analyze_superintendencia(raw: RawItem) -> AnalysisResult:
    # Family classification is title-first. Descriptions often mention several measures
    # (e.g. cartera pages also mention suscripciones), which previously caused misclassification.
    title=(raw.title or "").lower()
    full=f"{raw.title} {raw.raw_text}".lower()
    tags=["superintendencia"];who=["estrategia","estudios"]
    economic,regulatory,scope,novelty,actionability=45,35,65,70,60
    what=clean_technical_text(raw.metadata.get("description") or raw.raw_text) or raw.title
    why="Actualiza una fuente oficial útil para seguir la evolución del sistema de salud."

    if "movilidad" in title:
        tags += ["isapres","cartera","movilidad"];who += ["isapres","prestadores","desarrollo de negocios"]
        economic,novelty,actionability,scope=65,75,80,82
        what=f"La Superintendencia actualizó{_period(raw)} la movilidad de cotizantes entre Isapres y su entrada o salida del sistema, con cortes por edad, sexo y región."
        why="Permite detectar qué actores ganan o pierden cotizantes, dónde ocurre la movilidad y si cambian los patrones de entrada, salida o traspaso dentro del sistema."
    elif "cartera" in title or "beneficiario" in title:
        tags += ["isapres","cartera","cotizantes"];who += ["isapres","prestadores","desarrollo de negocios"]
        economic,scope,actionability=60,80,72
        regional=" por región" if "regional" in title or "región" in title else ""
        what=f"La Superintendencia actualizó{_period(raw)} la cartera Isapre{regional}: cotizantes, cargas, edad, sexo, tipo de trabajador y cotización percibida."
        why="Permite dimensionar tamaño y composición de cartera y observar cambios territoriales o demográficos que afectan demanda asistencial, ingresos y planificación."
    elif "suscripciones" in title or "desahucios" in title:
        tags += ["isapres","cartera","suscripciones","desahucios"];who += ["isapres","estrategia comercial"]
        economic,scope,actionability=60,75,72
        what=f"La Superintendencia actualizó{_period(raw)} las suscripciones y desahucios del sistema Isapre, incluyendo causal, sexo e Isapre."
        why="Permite seguir altas, bajas y motivos de salida, una señal útil para detectar presión comercial y cambios en la dinámica de afiliación."
    elif "financier" in title or "ifrs" in full or "estado de resultados" in full:
        tags += ["isapres","finanzas","fefi"];who += ["isapres","finanzas","prestadores"]
        economic,scope,actionability=78,88,82
        what=f"La Superintendencia publicó{_period(raw)} la actualización financiera del sistema Isapre, con resultados, balance, indicadores y estándares legales."
        why="Permite comparar sostenibilidad financiera, presión de costos y resultados operacionales entre Isapres con una base oficial comparable."
    elif "ges" in title or "auge" in title:
        tags += ["ges","fonasa","isapres"];who += ["isapres","fonasa","prestadores"]
        regulatory,scope,actionability=65,85,75
        what=f"La Superintendencia actualizó{_period(raw)} los casos y tasas de uso GES de Fonasa e Isapres por problema de salud."
        why="Permite detectar cambios de utilización por patología y dimensionar exposición asistencial y financiera entre seguros."
    elif "boletín" in title or "boletin" in title:
        tags += ["boletín","estadísticas"]
        why="Consolida indicadores oficiales del período; solo debería ganar espacio en portada cuando contiene cambios materiales."

    desc=clean_technical_text(raw.metadata.get("description") or raw.raw_text)
    facts=[desc[:400]] if desc else []
    if raw.metadata.get("updated_through"):facts.append(f"Información actualizada a {raw.metadata['updated_through']}.")
    numbers=[{"raw":x} for x in raw.metadata.get("extracted_numbers",[])[:10]]
    return AnalysisResult(what[:650],facts,numbers,why,list(dict.fromkeys(who)),list(dict.fromkeys(tags)),
      {"economic":economic,"regulatory":regulatory,"scope":scope,"novelty":novelty,"actionability":actionability})
