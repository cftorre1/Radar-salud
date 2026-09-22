from __future__ import annotations
import re
from html.parser import HTMLParser
from .models import RawItem
from .pipeline import build_signal
from .scouts import fetch_html
from .llm_analysis import analyze_official_news, analyze_news

MONTHS={"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06","julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}

class _Meta(HTMLParser):
    def __init__(self):
        super().__init__();self.description="";self.published="";self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()!="meta":return
        a={k.lower():v for k,v in attrs};key=(a.get("name") or a.get("property") or "").lower();content=a.get("content") or ""
        if key in ("description","og:description","twitter:description") and content and not self.description:self.description=" ".join(content.split())
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

def enrich(raw):
    try:
        p=_Meta();p.feed(fetch_html(raw.url));body=" ".join(p.text)
        raw.raw_text=p.description or body[:1400]
        raw.event_date=raw.event_date or _date(p.published) or _date(body[:7000])
        raw.metadata["page_text"]=body[:12000]
    except Exception as e:print("enrich:",e)
    return raw

def _fallback_minsal_score(title,text):
    t=f"{title} {text}".lower()
    if any(x in t for x in ("renuncia del secretario regional","designa nueva seremi","trayectoria","historia del ministerio","visita la región","conmemora","participa en")):return 25
    if any(x in t for x in ("ley","decreto","reglamento","plan nacional","estrategia nacional","listas de espera","ges","fonasa","financiamiento","presupuesto","red asistencial","inversión","inversion")):return 80
    if any(x in t for x in ("programa","medida","fiscalización","fiscalizacion","hospital","eleam","medicamentos","alerta sanitaria")):return 66
    return 45

def _personnel_noise(title):
    t=(title or "").lower()
    patterns=("renuncia","designa nueva","designa nuevo","nombramiento","asume como","nuevo subsecretario","nueva subsecretaria","seremi")
    return any(x in t for x in patterns)

def process_minsal(raw,cfg):
    if _personnel_noise(raw.title):return None
    raw=enrich(raw)
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    ai=analyze_official_news(title=raw.title,text=body,source_name=raw.source_name)
    score=int(ai.get("relevance_score")) if ai else _fallback_minsal_score(raw.title,body)
    if score<65:return None
    raw.metadata.update({
      "what_happened":(ai.get("what_happened") if ai else raw.raw_text) or raw.title,
      "why_it_matters":(ai.get("why_it_matters") if ai else "La publicación describe un cambio material para una parte relevante del sistema de salud."),
      "signal_types":["Mercado"],"scopes":["Salud pública"],"watch_tags":["minsal","salud pública"],
      "scores":{"economic":45,"regulatory":55,"scope":score,"novelty":score,"actionability":60}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Mercado"];row["scopes"]=["Salud pública"];row["editorial_relevance"]=score;return row

def process_suseso(raw,cfg):
    raw=enrich(raw)
    if not raw.event_date:return None
    text=raw.metadata.get("page_text") or raw.raw_text
    # SUSESO detail pages already expose materia / vigencia / destinatario.
    vig=None
    m=re.search(r"(?:Observaci[oó]n:?\s*)?(Vigencia[^.]{0,180})",text,re.I)
    if m:vig=m.group(1).strip()
    raw.metadata.update({
      "what_happened":raw.raw_text or raw.title,
      "why_it_matters":"La instrucción de SUSESO puede modificar obligaciones o criterios aplicables a organismos administradores, empleadores y actores de salud laboral.",
      "signal_types":["Normativa"],"scopes":["Salud laboral"],"watch_tags":["suseso","salud laboral","normativa"],
      "event_type":"REGULATION","validity_text":vig,
      "scores":{"economic":50,"regulatory":90,"scope":75,"novelty":75,"actionability":82}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Normativa"];row["scopes"]=["Salud laboral"];return row

def _scopes(text):
    t=text.lower();out=[]
    if "isapre" in t:out.append("Isapres")
    if "fonasa" in t:out.append("Fonasa")
    if any(x in t for x in ("clínica","clinica","hospital","prestador","centro médico","centro medico")):out.append("Prestadores")
    if any(x in t for x in ("farmac","medicamento","laboratorio")):out.append("Farma / medicamentos")
    return out or ["Sistema de salud"]

def process_df(raw,cfg):
    raw=enrich(raw)
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    ai=analyze_news(title=raw.title,text=body,source_name=raw.source_name,kind="prensa económica especializada")
    if ai and int(ai.get("relevance_score",0))<65:return None
    sc=_scopes(f"{raw.title} {raw.raw_text}")
    what=(ai.get("what_happened") if ai else raw.raw_text) or raw.title
    why=(ai.get("why_it_matters") if ai else "La señal describe un movimiento competitivo, financiero, de inversión o estrategia de un actor del sector salud.")
    score=int(ai.get("relevance_score",75)) if ai else 75
    raw.metadata.update({
      "what_happened":what,"why_it_matters":why,
      "signal_types":["Mercado"],"scopes":sc,"watch_tags":["df","mercado"]+[x.lower() for x in sc],
      "scores":{"economic":min(95,max(65,score)),"regulatory":30,"scope":70,"novelty":score,"actionability":70}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Mercado"];row["scopes"]=sc;row["editorial_relevance"]=score;return row

def process_diario_oficial(raw,cfg):
    raw=enrich(raw)
    t=f"{raw.title} {raw.raw_text}".lower();stype="Legal" if re.search(r"\bley\b",t) else "Normativa";sc=_scopes(t)
    if sc==["Sistema de salud"]:sc=["Salud pública"]
    raw.metadata.update({
      "what_happened":raw.raw_text or raw.title,
      "why_it_matters":"La publicación en Diario Oficial formaliza un cambio normativo o legal del sector salud.",
      "signal_types":[stype],"scopes":sc,"watch_tags":["diario oficial",stype.lower()]+[x.lower() for x in sc],
      "event_type":"LEGAL" if stype=="Legal" else "REGULATION",
      "scores":{"economic":55,"regulatory":95,"scope":82,"novelty":85,"actionability":88}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=[stype];row["scopes"]=sc;return row
