from __future__ import annotations
import re
from datetime import datetime
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
    # These public pages reliably expose recent Seguro Laboral circular/article links.
    PAGES=[
      "https://www.suseso.gob.cl/612/w3-propertyvalue-63007.html",
      "https://www.suseso.gob.cl/612/w3-propertyvalue-10335.html",
      "https://www.suseso.gob.cl/612/w3-propertyvalue-31037.html",
    ]
    def discover(self):
        out=[];seen=set()
        for page in self.PAGES:
            try:html=fetch_html(page)
            except Exception as e:
                print("SUSESO fetch:",e);continue
            p=_A();p.feed(html)
            for href,text in p.links:
                if not href or not text:continue
                url=urljoin(page,href)
                if not re.search(r"/612/w3-article-\d+\.html",url,re.I):continue
                if url in seen:continue
                if not re.search(r"(circular|dictamen)",text,re.I):continue
                seen.add(url)
                out.append(RawItem(self.SOURCE_SLUG,text,url,self.SOURCE_NAME,self.SOURCE_TYPE,raw_text="",metadata={"discovered_from":page}))
        print(f"SUSESO discovered={len(out)}")
        return out

class DfHealthScout:
    SOURCE_SLUG="diario_financiero";SOURCE_NAME="Diario Financiero";SOURCE_TYPE="press_high_trust"
    PAGE="https://www.df.cl/empresas/dfsalud"
    ARTICLE_RE=re.compile(r"^https://www\.df\.cl/(?:empresas/salud|regiones/.+?/empresas|empresas/.+?)/",re.I)
    def discover(self):
        try:html=fetch_html(self.PAGE)
        except Exception as e:
            print("DF fetch:",e);return []
        p=_A();p.feed(html);out=[];seen=set()
        for href,text in p.links:
            if not href or len(text)<25:continue
            url=urljoin(self.PAGE,href)
            if url in seen or not self.ARTICLE_RE.search(url):continue
            # DF Salud page itself is the relevance filter: do not require health words in every title.
            if any(x in url for x in ("/autor/","/suscripcion","/login")):continue
            seen.add(url);out.append(RawItem(self.SOURCE_SLUG,text,url,self.SOURCE_NAME,self.SOURCE_TYPE,raw_text="",metadata={"discovered_from":self.PAGE}))
        print(f"DF discovered={len(out)}")
        return out
