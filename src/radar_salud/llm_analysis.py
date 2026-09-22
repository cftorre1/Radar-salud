from __future__ import annotations
import json, os, re
from typing import Any, Dict, Optional

def _client():
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
        return OpenAI()
    except Exception:
        return None

def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(text)
    except Exception:
        m=re.search(r"\{.*\}", text or "", re.S)
        if not m:
            return None
        try:return json.loads(m.group(0))
        except Exception:return None

NORM_SCHEMA = {
  "type":"object",
  "properties":{
    "what_happened":{"type":"string"},
    "why_it_matters":{"type":"string"},
    "validity_text":{"type":["string","null"]},
    "key_points":{"type":"array","items":{"type":"string"},"maxItems":3},
    "review_points":{"type":"array","items":{"type":"string"},"maxItems":3},
    "references":{"type":"array","items":{"type":"string"},"maxItems":6},
  },
  "required":["what_happened","why_it_matters","validity_text","key_points","review_points","references"],
  "additionalProperties":False
}

NEWS_SCHEMA = {
  "type":"object",
  "properties":{
    "relevance_score":{"type":"integer","minimum":0,"maximum":100},
    "what_happened":{"type":"string"},
    "why_it_matters":{"type":"string"},
    "reason":{"type":"string"},
  },
  "required":["relevance_score","what_happened","why_it_matters","reason"],
  "additionalProperties":False
}

def analyze_normative_pdf(*, title: str, pdf_url: str, source_name: str, scope: str, fallback_summary: str="") -> Optional[Dict[str, Any]]:
    client=_client()
    if not client or not pdf_url:
        return None
    model=os.getenv("RADAR_LLM_MODEL","gpt-5.6-terra")
    instructions="""Eres el analista documental de Radar Salud Chile.
Analiza SOLO el documento adjunto y no uses conocimiento externo.
Escribe en español, de forma neutral, precisa y ejecutiva.

Reglas:
- No inventes datos, fechas, obligaciones, riesgos ni vigencias.
- "Qué pasó": 1-2 frases que expliquen el cambio concreto; evita copiar títulos o encabezados.
- "Por qué importa": explica el efecto potencial para el sistema o actores alcanzados, sin adoptar la perspectiva de una Isapre, prestador, autoridad u otro actor.
- "Vigencia": transcribe o parafrasea únicamente la regla de vigencia del documento. Si no es inequívoca, null.
- "Puntos clave": máximo 3. Deben ser cambios sustantivos, obligaciones, alcance, excepciones o efectos. NO incluir vigencia aquí.
- "Aspectos a revisar": máximo 3. Deben ser chequeos concretos derivados del documento; no uses frases genéricas del tipo 'revisar obligaciones' si puedes especificar qué obligación/plazo/sistema/proceso debe revisarse.
- No copies membretes, nombres de autoridades, pies de página ni antecedentes irrelevantes.
- Si el documento resuelve, modifica, complementa o cita una Circular, Oficio, Resolución, Ley o Decreto previo, incluye su identificador en references.
- Si una resolución trata un recurso contra una circular, explica qué resuelve y qué efecto tiene sobre esa circular; no repitas los considerandos como si fueran cambios nuevos."""
    prompt=f"""Documento: {title}
Fuente: {source_name}
Ámbito: {scope}
Resumen de la ficha oficial, solo como contexto secundario:
{fallback_summary[:1600]}"""
    try:
        r=client.responses.create(
            model=model,
            instructions=instructions,
            input=[{
                "role":"user",
                "content":[
                    {"type":"input_text","text":prompt},
                    {"type":"input_file","file_url":pdf_url},
                ],
            }],
            text={"format":{
                "type":"json_schema",
                "name":"radar_normative_analysis",
                "strict":True,
                "schema":NORM_SCHEMA,
            }},
        )
        return _parse_json(r.output_text)
    except Exception:
        return None

def analyze_official_news(*, title: str, text: str, source_name: str) -> Optional[Dict[str, Any]]:
    client=_client()
    if not client:
        return None
    model=os.getenv("RADAR_LLM_MODEL","gpt-5.6-terra")
    instructions="""Eres editor de Radar Salud Chile.
Evalúa una publicación oficial para decidir si merece aparecer en un radar estratégico del sector salud.
Sé neutral y usa SOLO la información entregada.

Puntaje:
90-100 cambio nacional/sectorial muy relevante: regulación, financiamiento, cobertura, red asistencial, política pública, alerta sanitaria de alto alcance, reforma, inversión/capacidad material.
70-89 cambio relevante para una parte importante del sistema.
55-69 contexto útil pero no prioritario.
0-54 ceremonial, visita de autoridad, nombramiento/renuncia local, historia institucional, campaña rutinaria, actividad protocolar o contenido sin cambio material.

"Qué pasó": 1-2 frases concretas.
"Por qué importa": efecto específico; evita la frase genérica 'aporta información oficial reciente'.
No inventes implicancias."""
    try:
        r=client.responses.create(
            model=model,
            instructions=instructions,
            input=f"Fuente: {source_name}\nTítulo: {title}\nContenido:\n{text[:7000]}",
            text={"format":{
                "type":"json_schema",
                "name":"radar_official_news",
                "strict":True,
                "schema":NEWS_SCHEMA,
            }},
        )
        return _parse_json(r.output_text)
    except Exception:
        return None
