from __future__ import annotations
import json, os, re
from typing import Any, Dict, Optional
from .ai_budget import allow_call, record_result

def _client():
    if not os.getenv("OPENAI_API_KEY"):return None
    try:
        from openai import OpenAI
        return OpenAI()
    except Exception:return None

def _parse_json(text:str)->Optional[Dict[str,Any]]:
    try:return json.loads(text)
    except Exception:
        m=re.search(r"\{.*\}",text or "",re.S)
        if not m:return None
        try:return json.loads(m.group(0))
        except Exception:return None

ACTORS=["Isapres","Fonasa","Prestadores","Salud pública","Salud laboral","Farma / medicamentos","Healthtech"]
PROCESSES=["Legal & Compliance","Operaciones","Finanzas / Tesorería","Convenios / Red","Beneficios / Cobertura",
           "Licencias médicas","Tecnología / Canales","Calidad / Acreditación","Planificación / Capacidad",
           "Estrategia","Comercial","Personas"]
NORM_SCHEMA={"type":"object","properties":{
 "what_happened":{"type":"string"},"why_it_matters":{"type":"string"},"validity_text":{"type":["string","null"]},
 "key_points":{"type":"array","items":{"type":"string"},"maxItems":3},
 "review_points":{"type":"array","items":{"type":"string"},"maxItems":3},
 "affected_actors":{"type":"array","items":{"type":"string","enum":ACTORS},"maxItems":4},
 "affected_processes":{"type":"array","items":{"type":"string","enum":PROCESSES},"maxItems":3},
 "references":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"relationship":{"type":"string"}},"required":["id","relationship"],"additionalProperties":False},"maxItems":8}},
 "required":["what_happened","why_it_matters","validity_text","key_points","review_points","affected_actors","affected_processes","references"],"additionalProperties":False}
NEWS_SCHEMA={"type":"object","properties":{"relevance_score":{"type":"integer","minimum":0,"maximum":100},"what_happened":{"type":"string"},"why_it_matters":{"type":"string"},"reason":{"type":"string"}},"required":["relevance_score","what_happened","why_it_matters","reason"],"additionalProperties":False}

def analyze_normative_pdf(*,title,pdf_url,source_name,scope,fallback_summary=""):
    c=_client()
    if not c or not pdf_url or not allow_call("deep"):return None
    model=os.getenv("RADAR_DEEP_MODEL","gpt-5.6-terra")
    instructions="""Eres el analista documental senior de Alicanto Salud Chile. Analiza SOLO el PDF.
Sé neutral, preciso y ejecutivo. No inventes datos, fechas, obligaciones, riesgos ni vigencias.
QUÉ PASÓ: 1-2 frases autosuficientes. Si el acto resuelve, modifica, suspende o aplica otra norma,
explica en una cláusula breve QUÉ REGULABA ese antecedente para que el lector entienda la decisión sin abrir otro documento.
POR QUÉ IMPORTA: actor(es) afectados + efecto práctico específico sobre cumplimiento, operación, reportabilidad,
acceso/cobertura, financiamiento/costos o gestión. Evita frases genéricas.
VIGENCIA: solo si es inequívoca; si no, null.
PUNTOS CLAVE y ASPECTOS A REVISAR: máximo 3 cada uno, concretos y no redundantes.
ACTORES AFECTADOS: selecciona solo actores que el documento realmente afecte; no infieras FONASA solo porque la fuente sea la Superintendencia de Salud.
PROCESOS AFECTADOS: máximo 3 procesos organizacionales directamente implicados.
REFERENCIAS: devuelve id exacto y una relación específica. Si el texto menciona un Oficio, Circular, Resolución, Ley, DFL o DS necesario para entender el acto, inclúyelo.
No incluyas la propia norma como referencia a sí misma."""
    try:
        r=c.responses.create(model=model,instructions=instructions,input=[{"role":"user","content":[
          {"type":"input_text","text":f"Documento: {title}\nFuente: {source_name}\nÁmbito de origen (NO implica actor afectado): {scope}\nFicha oficial: {fallback_summary[:1400]}"},
          {"type":"input_file","file_url":pdf_url}]}],text={"format":{"type":"json_schema","name":"alicanto_normative_v3","strict":True,"schema":NORM_SCHEMA}})
        parsed=_parse_json(r.output_text);record_result("deep",bool(parsed));return parsed
    except Exception as e:
        record_result("deep",False);print(f"deep model error: {e}");return None

def analyze_news(*,title,text,source_name,kind="sector"):
    c=_client()
    if not c or not allow_call("fast"):return None
    model=os.getenv("RADAR_FAST_MODEL","gpt-5.6-luna")
    instructions=f"""Eres editor senior de Alicanto Salud Chile. Usa SOLO el contenido entregado.
Evalúa si merece un radar estratégico del sector salud. Tipo de fuente: {kind}.
90-100: cambio sectorial/nacional material: regulación, financiamiento, cobertura, capacidad, inversión, M&A, estrategia competitiva, resultados relevantes, acceso o política pública.
75-89: cambio relevante para actores importantes.
65-74: contexto útil pero secundario.
0-64: ceremonial, visita de autoridad, nombramiento/renuncia, campaña rutinaria, hito local, alerta puntual de producto, historia institucional o contenido sin cambio material.
Qué pasó: concreto y verificable. Por qué importa: actor afectado + efecto específico + por qué merece atención ahora.
Evita frases genéricas reutilizables. No inventes implicancias."""
    try:
        r=c.responses.create(model=model,instructions=instructions,input=f"Fuente: {source_name}\nTítulo: {title}\nContenido:\n{text[:5500]}",text={"format":{"type":"json_schema","name":"alicanto_news_v3","strict":True,"schema":NEWS_SCHEMA}})
        parsed=_parse_json(r.output_text);record_result("fast",bool(parsed));return parsed
    except Exception as e:
        record_result("fast",False);print(f"fast model error: {e}");return None

def analyze_official_news(*,title,text,source_name):
    return analyze_news(title=title,text=text,source_name=source_name,kind="fuente oficial")
