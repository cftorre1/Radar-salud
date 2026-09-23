from __future__ import annotations
import json, os, re
from typing import Any, Dict, Optional
from .ai_budget import allow_call

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

NORM_SCHEMA={"type":"object","properties":{
 "what_happened":{"type":"string"},"why_it_matters":{"type":"string"},
 "validity_text":{"type":["string","null"]},
 "key_points":{"type":"array","items":{"type":"string"},"maxItems":3},
 "review_points":{"type":"array","items":{"type":"string"},"maxItems":3},
 "references":{"type":"array","items":{"type":"object","properties":{
   "id":{"type":"string"},"relationship":{"type":"string"}},
   "required":["id","relationship"],"additionalProperties":False},"maxItems":8}},
 "required":["what_happened","why_it_matters","validity_text","key_points","review_points","references"],
 "additionalProperties":False}
NEWS_SCHEMA={"type":"object","properties":{
 "relevance_score":{"type":"integer","minimum":0,"maximum":100},
 "what_happened":{"type":"string"},"why_it_matters":{"type":"string"},"reason":{"type":"string"}},
 "required":["relevance_score","what_happened","why_it_matters","reason"],"additionalProperties":False}

def analyze_normative_pdf(*,title,pdf_url,source_name,scope,fallback_summary=""):
    c=_client()
    if not c or not pdf_url or not allow_call("deep"):return None
    model=os.getenv("RADAR_DEEP_MODEL","gpt-5.6-terra")
    instructions="""Eres el analista documental senior de Alicanto Salud Chile. Analiza SOLO el PDF.
Sé neutral, preciso y ejecutivo. No inventes datos, fechas, obligaciones, riesgos ni vigencias.
Qué pasó: 1-2 frases con el cambio o decisión concreta.
Por qué importa: 1-2 frases MUY específicas: actor(es) afectados + efecto práctico plausible
(cumplimiento, operación, reportabilidad, acceso/cobertura, financiamiento/costos o gestión).
Si no se puede concluir del documento, dilo.
Vigencia: solo si es inequívoca; si no, null.
Puntos clave: máximo 3; contenido material. No repetir vigencia.
Aspectos a revisar: máximo 3; chequeos concretos derivados del texto.
Ignora membretes, firmas y antecedentes no sustantivos.
REFERENCIAS: si modifica, aplica, resuelve, suspende, interpreta o cita otra norma, devuelve
id exacto y relationship: una frase que explique por qué esa norma es necesaria para entender ESTE documento.
No incluyas la propia norma como referencia a sí misma."""
    try:
        r=c.responses.create(model=model,instructions=instructions,input=[{"role":"user","content":[
          {"type":"input_text","text":f"Documento: {title}\nFuente: {source_name}\nÁmbito: {scope}\nFicha oficial: {fallback_summary[:1400]}"},
          {"type":"input_file","file_url":pdf_url}]}],
          text={"format":{"type":"json_schema","name":"alicanto_normative_v2","strict":True,"schema":NORM_SCHEMA}})
        return _parse_json(r.output_text)
    except Exception as e:print(f"deep model error: {e}");return None

def analyze_news(*,title,text,source_name,kind="sector"):
    c=_client()
    if not c or not allow_call("fast"):return None
    model=os.getenv("RADAR_FAST_MODEL","gpt-5.6-luna")
    instructions=f"""Eres editor senior de Alicanto Salud Chile. Usa SOLO el contenido entregado.
Evalúa si merece un radar estratégico del sector salud. Tipo de fuente: {kind}.
90-100: cambio sectorial/nacional material: regulación, financiamiento, cobertura, capacidad,
inversión, M&A, estrategia competitiva, resultados relevantes, acceso o política pública.
75-89: cambio relevante para actores importantes.
65-74: contexto útil pero secundario.
0-64: ceremonial, visita de autoridad, nombramiento/renuncia, campaña rutinaria, hito local,
alerta puntual de producto, historia institucional o contenido sin cambio material.
Qué pasó: concreto y verificable.
Por qué importa: actor afectado + efecto específico + por qué merece atención ahora.
Evita frases genéricas reutilizables en decenas de tarjetas. No inventes implicancias."""
    try:
        r=c.responses.create(model=model,instructions=instructions,
          input=f"Fuente: {source_name}\nTítulo: {title}\nContenido:\n{text[:5500]}",
          text={"format":{"type":"json_schema","name":"alicanto_news_v2","strict":True,"schema":NEWS_SCHEMA}})
        return _parse_json(r.output_text)
    except Exception as e:print(f"fast model error: {e}");return None

def analyze_official_news(*,title,text,source_name):
    return analyze_news(title=title,text=text,source_name=source_name,kind="fuente oficial")
