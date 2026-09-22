from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.parse import urljoin
from .models import RawItem
from .scouts import fetch_html

class _A(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self._href=None;self._text=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":self._href=dict(attrs).get("href");self._text=[]
    def handle_data(self,data):
        if self._href is not None:self._text.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=="a" and self._href is not None:
            self.links.append((self._href," ".join("".join(self._text).split())));self._href=None;self._text=[]

class SusesoNormativeScout:
    SOURCE_SLUG="suseso";SOURCE_NAME="SUSESO";SOURCE_TYPE="official"
    DEFAULT_URL="https://www.suseso.cl/612/w3-channel.html"
    def discover(self):
        p=_A();p.feed(fetch_html(self.DEFAULT_URL));out=[];seen=set()
        for href,text in p.links:
            if not href or not text:continue
            url=urljoin(self.DEFAULT_URL,href)
            if not re.search(r"suseso\.cl/612/w3-article-\d+",url,re.I):continue
            if url in seen:continue
            if not re.search(r"(circular|dictamen|resoluci|norma|compendio)",text,re.I):continue
            seen.add(url);out.append(RawItem(self.SOURCE_SLUG,text,url,self.SOURCE_NAME,self.SOURCE_TYPE,raw_text="",metadata={"discovered_from":self.DEFAULT_URL}))
        return out

class DfHealthScout:
    SOURCE_SLUG="diario_financiero";SOURCE_NAME="Diario Financiero";SOURCE_TYPE="press_high_trust"
    PAGES=["https://www.df.cl/empresas/dfsalud","https://www.df.cl/noticias/site/tag/port/all/tagport_161_1.html"]
    def discover(self):
        out=[];seen=set()
        for page in self.PAGES:
            p=_A();p.feed(fetch_html(page))
            for href,text in p.links:
                if not href or len(text)<18:continue
                url=urljoin(page,href)
                if not url.startswith("https://www.df.cl/"):continue
                if any(x in url for x in ("/autor/","/tag/","/noticias/site/","/suscripcion","/login")):continue
                if url in seen:continue
                if not any(k in f"{text} {url}".lower() for k in ("salud","isapre","fonasa","clínica","clinica","hospital","farmac","medic","prestador","licencia")):continue
                seen.add(url);out.append(RawItem(self.SOURCE_SLUG,text,url,self.SOURCE_NAME,self.SOURCE_TYPE,raw_text="",metadata={"discovered_from":page}))
        return out
