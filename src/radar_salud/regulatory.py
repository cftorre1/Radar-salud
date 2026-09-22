from __future__ import annotations
import re
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin

from .models import RawItem
from .scouts import fetch_html

MONTHS={"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06","julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}

def _date(text: str) -> Optional[str]:
    m=re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})",text)
    if m:return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m=re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(20\d{2})",text,re.I)
    if m and m.group(2).lower() in MONTHS:return f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
    return None

class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self._row=None; self._cell=None; self._href=None; self._anchor=[]
    def handle_starttag(self,tag,attrs):
        tag=tag.lower()
        if tag=="tr": self._row=[]
        elif tag in ("td","th") and self._row is not None: self._cell={"text":[],"links":[]}
        elif tag=="a" and self._cell is not None:
            self._href=dict(attrs).get("href"); self._anchor=[]
    def handle_data(self,data):
        if self._cell is not None:
            t=" ".join(data.split())
            if t:self._cell["text"].append(t)
        if self._href is not None:self._anchor.append(data)
    def handle_endtag(self,tag):
        tag=tag.lower()
        if tag=="a" and self._href is not None and self._cell is not None:
            self._cell["links"].append((self._href," ".join("".join(self._anchor).split())))
            self._href=None;self._anchor=[]
        elif tag in ("td","th") and self._cell is not None and self._row is not None:
            self._cell["text"]=" ".join(self._cell["text"]).strip()
            self._row.append(self._cell); self._cell=None
        elif tag=="tr" and self._row is not None:
            if self._row:self.rows.append(self._row)
            self._row=None

class SuperintendenciaNormativaScout:
    SOURCE_SLUG="superintendencia_normativa"; SOURCE_NAME="Superintendencia de Salud"; SOURCE_TYPE="official"
    PAGES=[
      ("Circulares","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-aseguradoras-4097/circulares-2991/","Isapres"),
      ("Oficios Circulares","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-aseguradoras-4097/oficios-circulares-2993/","Isapres"),
    ]

    def discover(self)->List[RawItem]:
        out=[]; seen=set()
        for listing_name,listing_url,scope in self.PAGES:
            parser=_TableParser(); parser.feed(fetch_html(listing_url))
            for row in parser.rows:
                row_text=" ".join(c["text"] for c in row if c.get("text"))
                event_date=_date(row_text)
                title=None; detail_url=None; pdf_url=None
                for c in row:
                    for href,label in c.get("links",[]):
                        absolute=urljoin(listing_url,href)
                        if re.search(r"(Circular|Oficio)",label,re.I) and not re.search(r"Descargar",label,re.I):
                            title=label; detail_url=absolute
                        if re.search(r"\.pdf(?:$|\?)",absolute,re.I) or re.search(r"Descargar.*PDF",label,re.I):
                            pdf_url=absolute
                if not title:
                    m=re.search(r"((?:Circular|Oficio(?: Circular)?)\s+[A-Z/°Nºn°\-\d]+)",row_text,re.I)
                    if m:title=m.group(1)
                if not title: continue
                source_url=detail_url or pdf_url or listing_url
                key=(title,source_url)
                if key in seen: continue
                seen.add(key)
                # The last cell is the official summary in the current SuperSalud tables.
                summary=row[-1]["text"] if row else ""
                if summary==title or len(summary)<12: summary=row_text
                out.append(RawItem(
                    source_slug=self.SOURCE_SLUG,title=title,url=source_url,
                    source_name=self.SOURCE_NAME,source_type=self.SOURCE_TYPE,
                    event_date=event_date,raw_text=summary,
                    metadata={"listing_url":listing_url,"listing_name":listing_name,"scope":scope,"pdf_url":pdf_url}
                ))
        return out
