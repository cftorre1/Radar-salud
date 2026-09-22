from __future__ import annotations
import re
from html.parser import HTMLParser
from datetime import date
from .models import RawItem
from .pipeline import build_signal
from .scouts import fetch_html

MONTHS={"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06","julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}

class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.description=""; self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="meta":
            a={k.lower():v for k,v in attrs}
            key=(a.get("name") or a.get("property") or "").lower()
            if key in ("description","og:description") and a.get("content") and not self.description:
                self.description=" ".join(a["content"].split())
    def handle_data(self,data):
        t=" ".join(data.split())
        if t:self.text.append(t)

def enrich_public_item(raw: RawItem) -> RawItem:
    try:
        p=_MetaParser(); p.feed(fetch_html(raw.url))
        body=" ".join(p.text)
        desc=p.description or body[:500]
        if not raw.event_date:
            m=re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(20\d{2})",body,re.I)
            if m and m.group(2).lower() in MONTHS:
                raw.event_date=f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
        raw.raw_text=desc
    except Exception:
        pass
    return raw

def process_suseso(raw: RawItem, cfg):
    raw=enrich_public_item(raw)
    t=f"{raw.title} {raw.raw_text}".lower()
    signal_type="Normativa" if any(x in t for x in ("circular","dictamen","resolución","resolucion","ley","instrucción","instruccion")) else "Datos"
    raw.metadata.update({
      "what_happened": raw.raw_text or f"SUSESO publicó {raw.title}.",
      "why_it_matters":"Puede afectar reglas, operación, prestaciones o seguimiento del sistema de salud laboral y seguridad social.",
      "signal_types":[signal_type],"scopes":["Salud laboral"],
      "watch_tags":["suseso","salud laboral",signal_type.lower()],
      "event_type":"REGULATION" if signal_type=="Normativa" else "OTHER",
      "scores":{"economic":50,"regulatory":80 if signal_type=="Normativa" else 45,"scope":70,"novelty":70,"actionability":75},
    })
    s=build_signal(raw,cfg); row=s.to_dict()
    row["signal_types"]=[signal_type]; row["scopes"]=["Salud laboral"]
    return row

def process_minsal(raw: RawItem, cfg):
    raw=enrich_public_item(raw)
    raw.metadata.update({
      "what_happened": raw.raw_text or f"El Ministerio de Salud publicó {raw.title}.",
      "why_it_matters":"Aporta contexto oficial sobre decisiones, programas y cambios relevantes para el sistema de salud.",
      "signal_types":["Mercado"],"scopes":["Salud pública"],
      "watch_tags":["minsal","salud pública"],
      "scores":{"economic":45,"regulatory":55,"scope":75,"novelty":72,"actionability":60},
    })
    s=build_signal(raw,cfg); row=s.to_dict()
    row["signal_types"]=["Mercado"]; row["scopes"]=["Salud pública"]
    return row
