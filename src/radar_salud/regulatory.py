from __future__ import annotations
import re
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin
from .models import RawItem
from .scouts import fetch_html

MONTHS={"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06","julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}

def _date(text:str)->Optional[str]:
    m=re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})",text)
    if m:return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m=re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(20\d{2})",text,re.I)
    if m and m.group(2).lower() in MONTHS:return f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
    return None

class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self._row=None;self._cell=None;self._href=None;self._anchor=[]
    def handle_starttag(self,tag,attrs):
        tag=tag.lower()
        if tag=="tr":self._row=[]
        elif tag in ("td","th") and self._row is not None:self._cell={"text":[],"links":[]}
        elif tag=="a" and self._cell is not None:self._href=dict(attrs).get("href");self._anchor=[]
    def handle_data(self,data):
        if self._cell is not None:
            t=" ".join(data.split())
            if t:self._cell["text"].append(t)
        if self._href is not None:self._anchor.append(data)
    def handle_endtag(self,tag):
        tag=tag.lower()
        if tag=="a" and self._href is not None and self._cell is not None:
            self._cell["links"].append((self._href," ".join("".join(self._anchor).split())));self._href=None;self._anchor=[]
        elif tag in ("td","th") and self._cell is not None and self._row is not None:
            self._cell["text"]=" ".join(self._cell["text"]).strip();self._row.append(self._cell);self._cell=None
        elif tag=="tr" and self._row is not None:
            if self._row:self.rows.append(self._row)
            self._row=None

class SuperintendenciaNormativaScout:
    SOURCE_SLUG="superintendencia_normativa";SOURCE_NAME="Superintendencia de Salud";SOURCE_TYPE="official"
    PAGES=[
      ("Para ISAPREs y FONASA","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-aseguradoras-4097/","Isapres / Fonasa"),
      ("Para Prestadores Institucionales","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-prestadores-institucionales-6256/","Prestadores"),
      ("Para Entidades Acreditadoras","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-entidades-acreditadoras-6266/","Prestadores"),
      ("Para Entidades Certificadoras","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-entidades-certificadoras-6271/","Prestadores"),
      ("Para Prestadores Individuales","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-prestadores-individuales-6261/","Prestadores"),
      ("Para otros destinatarios","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-otros-destinatarios-7926/","Sistema de salud"),
    ]
    TITLE_RE=re.compile(r"(Circular|Oficio(?:\s+Circular)?|Ordinario(?:\s+Circular)?|Resoluci[oó]n(?:\s+Exenta)?)",re.I)
    ADMIN_NOISE=("licitación","licitacion","comisión evaluadora","comision evaluadora","aseo","fumigación","fumigacion",
                 "mantenciones","mantenimiento","licencias hcl","tableau","data center","monitoreo de medios",
                 "concurso de personal","designa miembros")
    def discover(self)->List[RawItem]:
        out=[];seen=set()
        for page_name,page_url,scope in self.PAGES:
            try:html=fetch_html(page_url)
            except Exception as e:print("SuperSalud regulatory fetch:",page_name,e);continue
            p=_TableParser();p.feed(html)
            for row in p.rows:
                row_text=" ".join(c["text"] for c in row if c.get("text"))
                if page_name=="Para otros destinatarios" and any(x in row_text.lower() for x in self.ADMIN_NOISE):continue
                if not self.TITLE_RE.search(row_text):continue
                event_date=_date(row_text);title=None;detail=None;pdf=None
                for c in row:
                    for href,label in c.get("links",[]):
                        absolute=urljoin(page_url,href)
                        if self.TITLE_RE.search(label) and "descargar" not in label.lower():
                            title=label;detail=absolute
                        if ".pdf" in absolute.lower() or "pdf" in label.lower():pdf=absolute
                if not title:
                    m=re.search(r"((?:Resoluci[oó]n(?:\s+Exenta)?|Oficio(?:\s+Circular)?|Ordinario(?:\s+Circular)?|Circular)\s+[A-Z/°Nºn°\-\d\s]+)",row_text,re.I)
                    if m:title=" ".join(m.group(1).split())
                if not title:continue
                url=detail or pdf or page_url;key=(title,url,scope)
                if key in seen:continue
                seen.add(key)
                summary=row[-1]["text"] if row else row_text
                if len(summary)<15:summary=row_text
                out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                    event_date=event_date,raw_text=summary,
                    metadata={"listing_url":page_url,"listing_name":page_name,"scope":scope,"pdf_url":pdf,
                              "attachments":[{"url":pdf,"label":"PDF"}] if pdf else []}))
        out.sort(key=lambda x:x.event_date or "",reverse=True)
        return out
