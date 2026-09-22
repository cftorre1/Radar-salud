from __future__ import annotations
import re
from html.parser import HTMLParser
from .models import RawItem
from .pipeline import build_signal
from .scouts import fetch_html
from .llm_analysis import analyze_official_news

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

def _date_from_text(text):
    if not text:return None
    m=re.search(r"(20\d{2})-(\d{2})-(\d{2})",text)
    if m:return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m=re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(20\d{2})",text,re.I)
    if m and m.group(2).lower() in MONTHS:return f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
    return None

def enrich(raw: RawItem):
    try:
        p=_Meta();p.feed(fetch_html(raw.url));body=" ".join(p.text)
        raw.raw_text=p.description or body[:1200]
        raw.event_date=raw.event_date or _date_from_text(p.published) or _date_from_text(body[:7000])
        raw.metadata["page_text"]=body[:12000]
    except Exception:pass
    return raw

def _fallback_minsal_score(title,text):
    t=f"{title} {text}".lower()
    low_patterns=("visita la región","visita región","trayectoria","historia del ministerio","renuncia del secretario regional","seremi de salud","saludo protocolar","conmemora","participa en")
    if any(x in t for x in low_patterns):return 30
    high=("ley","decreto","reglamento","plan nacional","estrategia nacional","red asistencial","listas de espera","ges","fonasa","financiamiento","presupuesto","alerta sanitaria","autorización sanitaria","autorizacion sanitaria","telemedicina","salud digital","inversión","inversion","licitación","licitacion")
    if any(x in t for x in high):return 76
    medium=("programa","medida","fiscalización","fiscalizacion","prestaciones","hospital","eleam","medicamentos","farmac")
    if any(x in t for x in medium):return 62
    return 48

def process_minsal(raw: RawItem,cfg):
    raw=enrich(raw)
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    ai=analyze_official_news(title=raw.title,text=body,source_name=raw.source_name)
    score=ai.get("relevance_score") if ai else _fallback_minsal_score(raw.title,body)
    if score<60:return None
    what=(ai.get("what_happened") if ai else raw.raw_text) or f"MINSAL publicó {raw.title}."
    why=(ai.get("why_it_matters") if ai else "La publicación introduce una medida o información oficial con efectos relevantes para una parte del sistema de salud.")
    raw.metadata.update({
      "what_happened":what,
      "why_it_matters":why,
      "signal_types":["Mercado"],
      "scopes":["Salud pública"],
      "watch_tags":["minsal","salud pública"],
      "scores":{"economic":45,"regulatory":55,"scope":min(95,max(55,int(score))),"novelty":min(95,max(55,int(score))),"actionability":60},
    })
    s=build_signal(raw,cfg);row=s.to_dict()
    row["signal_types"]=["Mercado"];row["scopes"]=["Salud pública"]
    row["editorial_relevance"]=score
    return row

def process_suseso(raw: RawItem,cfg):
    raw=enrich(raw)
    if not raw.event_date:return None
    raw.metadata.update({
      "what_happened":raw.raw_text or f"SUSESO publicó {raw.title}.",
      "why_it_matters":"Puede modificar reglas, obligaciones o criterios aplicables a salud laboral y seguridad social.",
      "signal_types":["Normativa"],"scopes":["Salud laboral"],
      "watch_tags":["suseso","salud laboral","normativa"],
      "event_type":"REGULATION",
      "scores":{"economic":50,"regulatory":85,"scope":72,"novelty":72,"actionability":78},
    })
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Normativa"];row["scopes"]=["Salud laboral"];return row

def _scopes(text):
    t=text.lower();out=[]
    if "isapre" in t:out.append("Isapres")
    if "fonasa" in t:out.append("Fonasa")
    if any(x in t for x in ("clínica","clinica","hospital","prestador","centro médico","centro medico")):out.append("Prestadores")
    if any(x in t for x in ("farmac","medicamento","laboratorio")):out.append("Farma / medicamentos")
    return out or ["Sistema de salud"]

def process_df(raw: RawItem,cfg):
    raw=enrich(raw)
    if not raw.event_date:return None
    text=f"{raw.title} {raw.raw_text}";sc=_scopes(text)
    raw.metadata.update({
      "what_happened":raw.raw_text or raw.title,
      "why_it_matters":"Aporta una señal de mercado sobre movimientos competitivos, inversión, desempeño o estrategia de actores de salud.",
      "signal_types":["Mercado"],"scopes":sc,"watch_tags":["df","mercado"]+[x.lower() for x in sc],
      "scores":{"economic":72,"regulatory":35,"scope":68,"novelty":78,"actionability":68},
    })
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Mercado"];row["scopes"]=sc;return row

def process_diario_oficial(raw: RawItem,cfg):
    # Diario Oficial is a legal/publication source. Regulatory acts issued by health authorities
    # remain "Normativa"; laws are "Legal".
    raw=enrich(raw)
    t=f"{raw.title} {raw.raw_text}".lower()
    stype="Legal" if re.search(r"\bley\b",t) else "Normativa"
    scopes=_scopes(t)
    if scopes==["Sistema de salud"]:scopes=["Salud pública"]
    raw.metadata.update({
      "what_happened":raw.raw_text or raw.title,
      "why_it_matters":"La publicación oficial formaliza un cambio normativo o legal que puede producir efectos desde su vigencia o publicación.",
      "signal_types":[stype],"scopes":scopes,
      "watch_tags":["diario oficial",stype.lower()]+[x.lower() for x in scopes],
      "event_type":"LEGAL" if stype=="Legal" else "REGULATION",
      "scores":{"economic":55,"regulatory":95,"scope":82,"novelty":85,"actionability":88},
    })
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=[stype];row["scopes"]=scopes;return row
