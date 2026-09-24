from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse
from .models import RawItem
from .scouts import fetch_html

class _A(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self._href=None;self._text=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":self._href=dict(attrs).get("href");self._text=[]
    def handle_data(self,data):
        if self._href is not None:self._text.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=="a" and self._href is not None:
            self.links.append((self._href," ".join("".join(self._text).split())));self._href=None;self._text=[]

class SusesoNormativeScout:
    SOURCE_SLUG="suseso";SOURCE_NAME="SUSESO";SOURCE_TYPE="official"
    PAGES=["https://www.suseso.gob.cl/612/w3-propertyvalue-63007.html","https://www.suseso.gob.cl/612/w3-propertyvalue-10335.html","https://www.suseso.gob.cl/612/w3-propertyvalue-31037.html"]
    def discover(self):
        out=[];seen=set()
        for page in self.PAGES:
            try:html=fetch_html(page)
            except Exception as e:print("SUSESO fetch:",e);continue
            p=_A();p.feed(html)
            for href,text in p.links:
                if not href or not text:continue
                url=urljoin(page,href)
                if not re.search(r"/612/w3-article-\d+\.html",url,re.I) or url in seen or not re.search(r"(circular|dictamen)",text,re.I):continue
                seen.add(url);out.append(RawItem(self.SOURCE_SLUG,text,url,self.SOURCE_NAME,self.SOURCE_TYPE,raw_text="",metadata={"discovered_from":page}))
        print(f"SUSESO discovered={len(out)}");return out

class DfHealthScout:
    SOURCE_SLUG="diario_financiero";SOURCE_NAME="Diario Financiero";SOURCE_TYPE="press_high_trust"
    PAGES=["https://www.df.cl/empresas/dfsalud","https://www.df.cl/noticias/site/tag/port/all/tagport_161_1.html"]
    def discover(self):
        out=[];seen=set()
        for page in self.PAGES:
            try:html=fetch_html(page)
            except Exception as e:print("DF fetch:",e);continue
            p=_A();p.feed(html)
            for href,text in p.links:
                if not href or len(text)<18:continue
                url=urljoin(page,href);u=urlparse(url);path=u.path.rstrip("/")
                if u.netloc not in ("www.df.cl","df.cl"):continue
                if any(x in path for x in ("/autor/","/suscripcion","/login","/tag/","/tax/")):continue
                if path in ("/empresas/dfsalud","/empresas/salud","/noticias/site/tag/port/all/tagport_161_1.html") or path.count("/")<3 or url in seen:continue
                seen.add(url);out.append(RawItem(self.SOURCE_SLUG,text,url,self.SOURCE_NAME,self.SOURCE_TYPE,raw_text="",metadata={"discovered_from":page}))
        print(f"DF discovered={len(out)}");return out

class FonasaNewsScout:
    """Direct official newsroom; discovery never fabricates publication dates."""
    SOURCE_SLUG="fonasa";SOURCE_NAME="FONASA";SOURCE_TYPE="official"
    PAGE="https://www.fonasa.gob.cl/noticias/"
    def discover_from_html(self,html):
        parser=_A();parser.feed(html)
        out=[];seen=set()
        for href,title in parser.links:
            if not href or len(title)<18:continue
            url=urljoin(self.PAGE,href);parsed=urlparse(url)
            if parsed.netloc not in ("www.fonasa.gob.cl","fonasa.gob.cl") or not re.fullmatch(r"/noticias/[^/]+/?",parsed.path):continue
            if parsed.path.rstrip("/")=="/noticias" or url in seen:continue
            seen.add(url)
            out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                               metadata={"discovered_from":self.PAGE}))
        return out
    def discover(self):
        from .public_source_pipeline import _Meta, _date
        items=self.discover_from_html(fetch_html(self.PAGE))
        # A date on the detail page is required to distinguish LIVE from BACKFILL.
        for item in items[:15]:
            try:
                meta=_Meta();meta.feed(fetch_html(item.url))
                item.event_date=_date(meta.published)
            except Exception:
                # Keep the item but classify it as BACKFILL until verified.
                item.event_date=None
        return items[:15]
