from __future__ import annotations
import json, os, re
from typing import Any, Dict, Optional
from .ai_budget import allow_call, record_result
from .telemetry import record_response

def _client():
    if not os.getenv("OPENAI_API_KEY"):return None
    try:
        from openai import OpenAI
        return OpenAI(max_retries=0)
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
        parsed=_parse_json(r.output_text);record_response("deep",model,r,bool(parsed),None if parsed else "invalid_json");record_result("deep",bool(parsed));return parsed
    except Exception as e:
        record_response("deep",model,None,False,type(e).__name__)
        record_result("deep",False);print(f"deep model error: {type(e).__name__}");return None

def news_analysis_input(*, title, text, source_name, full_text=False):
    """The exact text request, shared with source evidence bookkeeping."""
    content = text if full_text else text[:5500]
    return f"Fuente: {source_name}\nTítulo: {title}\nContenido:\n{content}"


def analyze_news(*,title,text,source_name,kind="sector",full_text=False,pulso_editorial_proof=False):
    if pulso_editorial_proof and not full_text:
        raise ValueError("Pulso editorial proof requires complete primary input")
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
    schema=NEWS_SCHEMA
    schema_name="alicanto_news_v3"
    if pulso_editorial_proof:
        from .pulso_editorial_proof import PROOF_SCHEMA, VERSION
        schema=dict(NEWS_SCHEMA,properties=dict(NEWS_SCHEMA["properties"],pulso_editorial_proof=PROOF_SCHEMA),
                    required=NEWS_SCHEMA["required"]+["pulso_editorial_proof"])
        schema["properties"]["what_happened"] = {"type": "string", "description":
            "Hechos atribuidos a la nota, con período de datos y condición actual/futura separados. En BACKFILL, fecha los estados entonces observados con la publicación original; no los declares vigentes a la fecha de revisión."}
        schema["properties"]["why_it_matters"] = {"type": "string", "description":
            "Actor y efecto concreto con atribución de prensa. En BACKFILL, fecha explícitamente cualquier estado persistente a la publicación original, también en este campo; no conviertas entonces-pendiente/en-curso en estado verificado hoy."}
        schema_name=VERSION
        instructions+="""
Para Pulso/La Tercera exige un cambio concreto de salud HUMANA en Chile: actor,
acción y consecuencia explícitos para aseguramiento/cobertura, prestadores,
financiamiento sanitario, regulación clínica o sanitaria, medicamentos, inversión,
competencia, datos sectoriales o una acción específica de salud poblacional.
La mención incidental de Salud en macroeconomía/gobernanza/telecomunicaciones,
salud animal/vegetal/ecosistemas, marketing y opinión no acreditan ese cambio.
Usa scope_decision incidental_health/non_human_health/marketing/opinion cuando
corresponda, aunque la noticia tenga importancia económica o el score sea alto.
NO publiques por cantidad. Citas exactas no equivalen a aprobación independiente.
Devuelve pulso_editorial_proof: scope_reason y human_health_scope_quote (cita
literal del CONTENIDO, nunca del título ni de navegación); actor/action/consequence
son fragmentos literales breves contenidos en sus correspondientes citas,
que deben explicar el vínculo sanitario directo. Las citas de acción, consecuencia,
estatus y novedad deben contener la frase completa relevante, sin puntos suspensivos
ni paráfrasis. Para un scope excluido puedes dejar actor/action/consequence vacíos.
CONTRATO LITERAL: copia actor (mínimo 3 caracteres) dentro de actor_quote (mínimo 8),
action dentro de action_quote (mínimo 20), consequence dentro de consequence_quote
(mínimo 20). No reformules esos tres valores: conserva exactamente las palabras,
verbos, negaciones y cifras del fragmento citado. Las citas son UN solo fragmento
CONTIGUO del contenido; nunca unas dos frases separadas, agregues conectores,
comillas exteriores, puntos suspensivos o citas del título. event_status_quote
requiere al menos 12 caracteres y novelty_quote/human_health_scope_quote al menos 20.
No suprimas palabras intermedias, fechas, siglas entre paréntesis, comillas internas
ni errores tipográficos del original en una cita. Si el contenido repite «de de»,
la cita debe conservar esa repetición. Si dice «encabezó este viernes la firma»,
no cites «encabezó la firma». Copia primero una cita contigua y extrae de ella el
actor, la acción o la consecuencia exactos; no agregues un sujeto ausente.
Ejemplo de copia, sólo si el contenido realmente dijera «El Hospital del Sur
suspendió las consultas durante dos días.»: actor="Hospital del Sur",
actor_quote="El Hospital del Sur suspendió las consultas durante dos días.",
action="suspendió las consultas", action_quote igual a esa frase completa,
consequence="durante dos días", consequence_quote igual a esa frase completa.
El ejemplo NO es evidencia del artículo y NO debes copiarlo como hecho.
Elige una cita de scope que nombre atención clínica, enfermedad humana, cobertura,
medicamentos o autoridad sanitaria concreta; «el sector» o «un equipo» no basta.
El actor debe ser quien REALIZA la acción elegida, no sólo una parte afectada,
beneficiaria o demandada. Para un fallo, distingue el tribunal que decide de los
prestadores demandados; para una demanda, distingue al demandante del tribunal.
Clasifica event_status: actual, proposal, plan, mixed_actual_and_future o
historical_context. Conserva período y métrica de los datos, estado de investigación
y condición de propuesta. Un anuncio, proyecto, plan o notificación FNE no es
aprobación, implementación, adquisición cerrada ni capacidad ya disponible.
No rejuvenezcas hechos históricos con la fecha de publicación; una auditoría/fallo
actual sí puede informar hechos de períodos antiguos, claramente separados.
BACKFILL describe la vía de ingreso y no implica historical_context: un balance,
fallo o cambio nuevo a la fecha de publicación puede ser actual con atribución a
esa fecha. Reserva historical_context para antecedentes sin un cambio nuevo.
La aprobación de un artículo o de una comisión no acredita la aprobación íntegra
de una reforma. Distingue el precio base de un precio que incluye GES y no cambies
porcentajes por puntos porcentuales. No iguales porcentajes de gastos o ingresos
con márgenes distintos ni extiendes «hasta la fecha» a un período más corto.
Usa las fechas de publicación original y revisión entregadas en Tipo de fuente.
Si la publicación es anterior a la revisión (BACKFILL), fecha explícitamente los
estados persistentes en AMBOS campos, what_happened y why_it_matters: «Según la
nota del [fecha original]...» o «Al [fecha original], según la nota...». «Sigue
pendiente», «en curso», «mantiene alta circulación», «todavía no disponible» o
«ahora» sólo describen lo observado en esa fecha original, salvo nueva evidencia
fechada que acredite continuidad. La importancia al ingresar al radar no prueba
el estado operativo de hoy. Conserva también el período propio de cada métrica.
Si las cifras publicadas no cuadran, no las corrijas ni inventes un saldo por
resta. Atribuye las cifras explícitamente a la nota y señala la discrepancia, o
evita el saldo derivado; no sumes personas, registros, períodos o bases distintas.
Clasifica novelty_decision: new_material_information, repetition_or_context o
uncertain, con razón y cita literal; un nuevo artículo sobre un hecho ya conocido
no es necesariamente nueva señal. Usa el contexto incremental entregado.
Para proposal/plan/mixed_actual_and_future incluye future_claims con al menos
una entrada de what_happened y otra de why_it_matters: summary_quote debe copiar
literalmente TODO el campo correspondiente, no una frase condicional secundaria;
source_quote debe dar su apoyo literal en el contenido. Conserva futuro/condicional
en ambos campos completos, sin presentar la medida futura como logro ejecutado ni decir que
ya se alcanzó, ejecutó o elevó capacidad futura. Para actual usa future_claims=[];
si mezcla logros reales y medidas futuras, separa expresamente ambos en el texto.
Para liveblog, usa cada fecha de entrada verificada; no trates un balance repetido
como nuevo, no cambies la fecha del documento y no sumes los mismos pacientes.
Mantén atribución de prensa: lo reportado sigue siendo media_reported.
"""
    try:
        request_input = news_analysis_input(title=title, text=text, source_name=source_name, full_text=full_text)
        r=c.responses.create(model=model,instructions=instructions,input=request_input,text={"format":{"type":"json_schema","name":schema_name,"strict":True,"schema":schema}})
        parsed=_parse_json(r.output_text)
        if pulso_editorial_proof and isinstance(parsed,dict):
            import hashlib
            parsed["_pulso_analysis_meta"]={"schema_version":VERSION,"source_name":source_name,
                "model":getattr(r,"model",None) or model,"response_id":getattr(r,"id",None),
                "analysis_text_sha256":hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "request_input_sha256":hashlib.sha256(request_input.encode("utf-8")).hexdigest(),
                "raw_model_output_sha256":hashlib.sha256(r.output_text.encode("utf-8")).hexdigest()}
        record_response("fast",model,r,bool(parsed),None if parsed else "invalid_json");record_result("fast",bool(parsed));return parsed
    except Exception as e:
        record_response("fast",model,None,False,type(e).__name__)
        record_result("fast",False);print(f"fast model error: {type(e).__name__}");return None

def analyze_official_news(*,title,text,source_name):
    return analyze_news(title=title,text=text,source_name=source_name,kind="fuente oficial")
