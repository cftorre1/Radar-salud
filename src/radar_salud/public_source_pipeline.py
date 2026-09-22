from __future__ import annotations
import re
from html.parser import HTMLParser
from .models import RawItem
from .pipeline import build_signal
from .scouts import fetch_html

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
        raw.raw_text=p.description or body[:650]
        raw.event_date=raw.event_date or _date_from_text(p.published) or _date_from_text(body[:5000])
    except Exception:pass
    return raw

def _scopes(text):
    t=text.lower();out=[]
    if "isapre" in t:out.append("Isapres")
    if "fonasa" in t:out.append("Fonasa")
    if any(x in t for x in ("clínica","clinica","hospital","prestador","centro médico","centro medico")):out.append("Prestadores")
    if any(x in t for x in ("farmac","medicamento","laboratorio")):out.append("Farma / medicamentos")
    return out or ["Sistema de salud"]

def process_minsal(raw: RawItem,cfg):
    raw=enrich(raw)
    if not raw.event_date:return None  # static institutional pages are not news
    raw.metadata.update({"what_happened":raw.raw_text or f"MINSAL publicó {raw.title}.",
      "why_it_matters":"Aporta información oficial reciente sobre decisiones, programas o cambios del sistema de salud.",
      "signal_types":["Mercado"],"scopes":["Salud pública"],"watch_tags":["minsal","salud pública"],
      "scores":{"economic":45,"regulatory":55,"scope":75,"novelty":72,"actionability":60}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Mercado"];row["scopes"]=["Salud pública"];return row

def process_suseso(raw: RawItem,cfg):
    raw=enrich(raw)
    if not raw.event_date:return None
    raw.metadata.update({"what_happened":raw.raw_text or f"SUSESO publicó {raw.title}.",
      "why_it_matters":"Puede modificar reglas, obligaciones o criterios aplicables a salud laboral y seguridad social.",
      "signal_types":["Normativa"],"scopes":["Salud laboral"],"watch_tags":["suseso","salud laboral","normativa"],
      "event_type":"REGULATION",
      "scores":{"economic":50,"regulatory":85,"scope":72,"novelty":72,"actionability":78}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Normativa"];row["scopes"]=["Salud laboral"];return row

def process_df(raw: RawItem,cfg):
    raw=enrich(raw)
    if not raw.event_date:return None
    text=f"{raw.title} {raw.raw_text}";sc=_scopes(text)
    raw.metadata.update({"what_happened":raw.raw_text or raw.title,
      "why_it_matters":"Aporta una señal de mercado sobre movimientos competitivos, inversión, desempeño o estrategia de actores de salud.",
      "signal_types":["Mercado"],"scopes":sc,"watch_tags":["df","mercado"]+[x.lower() for x in sc],
      "scores":{"economic":72,"regulatory":35,"scope":68,"novelty":78,"actionability":68}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Mercado"];row["scopes"]=sc;return row
