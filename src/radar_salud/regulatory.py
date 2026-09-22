from __future__ import annotations
import re
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin

from .models import RawItem
from .scouts import fetch_html

MONTHS={"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06","julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}

class _RegParser(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self._href=None;self._text=[];self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a": self._href=dict(attrs).get("href");self._text=[]
    def handle_data(self,data):
        t=" ".join(data.split())
        if t:self.text.append(t)
        if self._href is not None:self._text.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=="a" and self._href is not None:
            self.links.append((self._href," ".join("".join(self._text).split())))
            self._href=None;self._text=[]

def _date_from_context(text:str)->Optional[str]:
    m=re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})",text)
    if m:return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m=re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(20\d{2})",text,re.I)
    if m and m.group(2).lower() in MONTHS:return f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
    return None

class SuperintendenciaNormativaScout:
    SOURCE_SLUG="superintendencia_normativa";SOURCE_NAME="Superintendencia de Salud";SOURCE_TYPE="official"
    PAGES=[
      ("Circulares para aseguradoras","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-aseguradoras-4097/circulares-2991/","Isapres"),
      ("Oficios Circulares para aseguradoras","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-aseguradoras-4097/oficios-circulares-2993/","Isapres"),
    ]
    PDF_RE=re.compile(r"\.pdf(?:$|\?)",re.I)

    def discover(self)->List[RawItem]:
        items=[];seen=set()
        for page_name,url,scope in self.PAGES:
            html=fetch_html(url);parser=_RegParser();parser.feed(html)
            full=" ".join(parser.text)
            for href,label in parser.links:
                absolute=urljoin(url,href)
                if not label or not self.PDF_RE.search(absolute):continue
                if absolute in seen:continue
                if not re.search(r"(Circular|Oficio|Ordinario)",label,re.I):continue
                seen.add(absolute)
                pos=full.find(label);ctx=full[max(0,pos-220):pos+700] if pos>=0 else label
                summary=""
                m=re.search(r"(Circular[^.]{0,220}|Oficio[^.]{0,220})",ctx,re.I)
                if m: summary=" ".join(m.group(1).split())
                event_date=_date_from_context(ctx)
                items.append(RawItem(
                    source_slug=self.SOURCE_SLUG,title=label,url=absolute,source_name=self.SOURCE_NAME,source_type=self.SOURCE_TYPE,
                    event_date=event_date,raw_text=summary or label,
                    metadata={"listing_url":url,"listing_name":page_name,"scope":scope}
                ))
        return items
