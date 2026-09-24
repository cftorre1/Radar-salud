from __future__ import annotations
import re
from html.parser import HTMLParser
from .models import RawItem
from .pipeline import build_signal
from .scouts import fetch_html
from .document_intelligence import extract_pdf_text
from .llm_analysis import analyze_official_news, analyze_news
from .processing import DeferredProcessing

MONTHS={"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06","julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}

class _Meta(HTMLParser):
    def __init__(self):super().__init__();self.description="";self.published="";self.text=[];self.ogtitle=""
    def handle_starttag(self,tag,attrs):
        if tag.lower()!="meta":return
        a={k.lower():v for k,v in attrs};key=(a.get("name") or a.get("property") or "").lower();content=a.get("content") or ""
        if key in ("description","og:description","twitter:description") and content and not self.description:self.description=" ".join(content.split())
        if key=="og:title" and content and not self.ogtitle:self.ogtitle=" ".join(content.split())
        if key in ("article:published_time","date","datepublished","publishdate") and content and not self.published:self.published=content
    def handle_data(self,data):
        t=" ".join(data.split())
        if t:self.text.append(t)

def _date(text):
    if not text:return None
    m=re.search(r"(20\d{2})-(\d{2})-(\d{2})",text)
    if m:return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m=re.search(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})",text)
    if m:return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m=re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(20\d{2})",text,re.I)
    if m and m.group(2).lower() in MONTHS:return f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
    return None

def _field(text,label):
    flat=" ".join((text or "").split())
    m=re.search(rf"\b{re.escape(label)}\s*:?\s*(.{{1,220}}?)(?=\s+(?:Materia|Destinatario|Observaci[oó]n|Vigencia|Acci[oó]n|Fuentes|Fiscalizados|Entidades Fiscalizadas|Tipo Contenido Normativo|Departamento)\b|$)",flat,re.I)
    return m.group(1).strip(" :-") if m else None

def enrich(raw):
    raw.metadata.pop("fetch_error",None)
    try:
        p=_Meta();p.feed(fetch_html(raw.url));body=" ".join(p.text)
        if p.ogtitle and len(raw.title)<18:raw.title=p.ogtitle
        raw.raw_text=p.description or body[:1400]
        raw.event_date=raw.event_date or _date(p.published)
        raw.metadata["page_text"]=body[:18000]
    except Exception as e:
        raw.metadata["fetch_error"]=type(e).__name__
        print("enrich:",e)
    return raw

def _noise(title):
    t=(title or "").lower()
    terms=("renuncia","nombramiento","nombra,","nombra a","nombra mediante","designa","designación","designacion",
           "asume como","alta dirección pública","alta direccion publica","nuevo subsecretario","nueva subsecretaria",
           "seremi","director del servicio de salud","directora del servicio de salud","continúa recorrido",
           "continua recorrido","visita nuevo","visita el","visita la","conmemora","participa en","trayectoria")
    return any(x in t for x in terms)

def _fallback_minsal_score(title,text):
    t=f"{title} {text}".lower()
    if _noise(title):return 0
    if any(x in t for x in ("alerta alimentaria","retiro de producto","lote de")):return 45
    if any(x in t for x in ("ley","decreto","reglamento","plan nacional","estrategia nacional","listas de espera","ges","fonasa","financiamiento","presupuesto","red asistencial","inversión","inversion")):return 80
    if any(x in t for x in ("programa","medida","fiscalización","fiscalizacion","hospital","eleam","medicamentos","alerta sanitaria")):return 66
    return 45

def process_minsal(raw,cfg):
    if _noise(raw.title):return None
    raw=enrich(raw)
    if not raw.event_date:
        raw.event_date=_date(raw.metadata.get("page_text","")[:6000])
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    ai=analyze_official_news(title=raw.title,text=body,source_name=raw.source_name)
    score=int(ai.get("relevance_score")) if ai else _fallback_minsal_score(raw.title,body)
    if score<65:return None
    raw.metadata.update({"what_happened":(ai.get("what_happened") if ai else raw.raw_text) or raw.title,
      "why_it_matters":(ai.get("why_it_matters") if ai else "La publicación contiene un cambio oficial con efectos relevantes para una parte del sistema de salud."),
      "signal_types":["Noticias"],"scopes":["Salud pública"],"watch_tags":["minsal","salud pública"],
      "scores":{"economic":45,"regulatory":55,"scope":score,"novelty":score,"actionability":60}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Noticias"];row["scopes"]=["Salud pública"];row["editorial_relevance"]=score;return row

def _clean_validity(text):
    v=_field(text,"Vigencia")
    if not v:return None
    if any(x in v.lower() for x in ('nj:','"529"','"535"','propertyvalue','javascript')):return None
    return v[:180]

def _suseso_date(text):
    v=_field(text,"Fecha")
    return _date(v) if v else None

def process_suseso(raw,cfg):
    raw=enrich(raw)
    text=raw.metadata.get("page_text") or raw.raw_text
    raw.event_date=_suseso_date(text) or raw.event_date
    if not raw.event_date:return None
    vig=_clean_validity(text)
    raw.metadata.update({"what_happened":raw.raw_text or raw.title,
      "why_it_matters":"La instrucción modifica o precisa criterios aplicables a salud laboral, organismos administradores o empleadores y puede exigir cambios de cumplimiento u operación.",
      "signal_types":["Normativa"],"scopes":["Salud laboral"],"watch_tags":["suseso","salud laboral","normativa"],
      "event_type":"REGULATION","validity_text":vig,
      "scores":{"economic":50,"regulatory":90,"scope":75,"novelty":75,"actionability":82}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Normativa"];row["scopes"]=["Salud laboral"];return row

def _scopes(text):
    t=text.lower();out=[]
    if re.search(r"\bisapre(?:s)?\b",t):out.append("Isapres")
    if re.search(r"\bfonasa\b|fondo nacional de salud",t):out.append("Fonasa")
    if any(x in t for x in ("clínica","clinica","hospital","prestador","centro médico","centro medico")):out.append("Prestadores")
    if any(x in t for x in ("farmac","medicamento","laboratorio","novo nordisk","moderna")):out.append("Farma / medicamentos")
    if any(x in t for x in ("healthtech","salud digital","telemedicina")):out.append("Healthtech")
    return out or ["Sistema de salud"]

def _health_relevance(title,text):
    t=f"{title} {text}".lower()
    health_terms=("salud","clínica","clinica","hospital","isapre","fonasa","médic","medic","farmac","laboratorio",
                  "healthtech","biotech","telemedicina","prestador","bupa","redsalud","banmédica","banmedica",
                  "colmena","consalud","cruz blanca","nueva masvida","esencial")
    return any(x in t for x in health_terms)

def process_df(raw,cfg):
    raw=enrich(raw)
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    if not _health_relevance(raw.title,body):return None
    ai=analyze_news(title=raw.title,text=body,source_name=raw.source_name,kind="prensa económica especializada en salud")
    if not ai:raise DeferredProcessing("DF pendiente de evaluación IA")
    if int(ai.get("relevance_score",0))<65:return None
    score=int(ai.get("relevance_score",0));sc=_scopes(f"{raw.title} {raw.raw_text}")
    raw.metadata.update({"what_happened":ai.get("what_happened") or raw.title,"why_it_matters":ai.get("why_it_matters") or "",
      "signal_types":["Noticias"],"scopes":sc,"watch_tags":["df","noticias"]+[x.lower() for x in sc],
      "scores":{"economic":min(95,max(65,score)),"regulatory":30,"scope":70,"novelty":score,"actionability":70}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Noticias"];row["scopes"]=sc;row["editorial_relevance"]=score;return row

def process_diario_oficial(raw,cfg):
    text=extract_pdf_text(raw.url,max_pages=10)
    if not text or text.startswith("%PDF"):return None
    issuer=raw.metadata.get("issuer","Diario Oficial")
    ai=analyze_news(title=raw.title,text=text[:7000],source_name=f"Diario Oficial / {issuer}",kind="publicación legal oficial")
    if not ai:raise DeferredProcessing("Diario Oficial pendiente de evaluación IA")
    score=int(ai.get("relevance_score",0))
    if score<68:return None
    what=ai.get("what_happened") or raw.title;why=ai.get("why_it_matters") or ""
    t=f"{raw.title} {text[:2500]}".lower();stype="Legal" if re.search(r"\bley\b",t) else "Normativa";sc=_scopes(t)
    if sc==["Sistema de salud"]:
        sc=["Salud laboral"] if issuer=="SUSESO" else (["Fonasa"] if issuer=="FONASA" else ["Salud pública"])
    raw.metadata.update({"what_happened":what,"why_it_matters":why,"signal_types":[stype],"scopes":sc,
      "watch_tags":["diario oficial",stype.lower(),issuer.lower()]+[x.lower() for x in sc],
      "event_type":"LEGAL" if stype=="Legal" else "REGULATION",
      "scores":{"economic":55,"regulatory":95,"scope":max(72,score),"novelty":score,"actionability":82}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=[stype];row["scopes"]=sc;row["editorial_relevance"]=score;row["issuer"]=issuer;return row


def process_fonasa(raw,cfg):
    """Only dated, substantive official evidence may reach the feed."""
    raw=enrich(raw)
    if raw.metadata.get("fetch_error"):raise DeferredProcessing("FONASA detalle temporalmente inaccesible")
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    if len(body)<180:return None
    ai=analyze_official_news(title=raw.title,text=body,source_name="FONASA")
    if not ai:raise DeferredProcessing("FONASA pendiente de evaluación IA")
    score=int(ai.get("relevance_score",0))
    what=(ai.get("what_happened") or "").strip()
    why=(ai.get("why_it_matters") or "").strip()
    if score<65 or len(what)<45 or len(why)<35:return None
    raw.metadata.update({"what_happened":what,"why_it_matters":why,
      "signal_types":["Noticias"],"scopes":["Fonasa"],"watch_tags":["fonasa","aseguramiento público"],
      "scores":{"economic":55,"regulatory":50,"scope":score,"novelty":score,"actionability":65}})
    row=build_signal(raw,cfg).to_dict()
    row.update(signal_types=["Noticias"],scopes=["Fonasa"],editorial_relevance=score)
    return row
