from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse
from datetime import date
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
            except Exception as exc:
                # A failed detail request is technical failure, not an undated publication.
                raise RuntimeError(f"FONASA detail unavailable: {type(exc).__name__}") from exc
        return items[:15]


class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.cell=None; self.anchor=None
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="tr":self.row={"text":[],"links":[],"cells":[]}
        if self.row is not None and tag.lower() in ("td","th"):self.cell=[]
        if self.row is not None and tag.lower()=="a":self.anchor=[dict(attrs).get("href"),[]]
    def handle_data(self,data):
        if self.row is not None:
            self.row["text"].append(data)
            if self.cell is not None:self.cell.append(data)
            if self.anchor is not None:self.anchor[1].append(data)
    def handle_endtag(self,tag):
        if tag.lower()=="a" and self.anchor is not None:
            self.row["links"].append((self.anchor[0]," ".join(" ".join(self.anchor[1]).split())))
            self.anchor=None
        if tag.lower() in ("td","th") and self.cell is not None:
            self.row["cells"].append(" ".join(" ".join(self.cell).split()));self.cell=None
        if tag.lower()=="tr" and self.row is not None:
            self.rows.append(self.row);self.row=None


class IspAnamedAlertScout:
    """Official ANAMED alerts with a verified date in the listing row."""
    SOURCE_SLUG="isp_anamed";SOURCE_NAME="ISP / ANAMED";SOURCE_TYPE="official"
    PAGE="https://www.ispch.gob.cl/categorias-alertas/anamed/"
    def discover_from_html(self,html):
        # Capture hrefs only within rows; a date on an unrelated page element
        # must never be attributed to an alert.
        from .public_source_pipeline import _date
        parser=_TableRows();parser.feed(html);items=[];seen=set();dated_rows=0
        for row in parser.rows:
            body=" ".join(" ".join(row["text"]).split())
            # Only a standalone date cell is a publication date. A date in the
            # alert description or another document is never a publication date.
            dates=[c for c in row["cells"] if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]20\d{2}",c)]
            day=_date(dates[0]) if len(dates)==1 else None
            try:
                if day:day=date.fromisoformat(day).isoformat()
                if day and day>date.today().isoformat():day=None
            except ValueError:day=None
            if day:dated_rows+=1
            if not day or not re.search(r"retiro del mercado|nota informativa|falsificad|seguridad",body,re.I):continue
            titles=[cell for cell in row["cells"] if len(cell)>25 and not cell.lower().startswith("publicación isp")]
            if not titles:continue
            title=max(titles,key=len)
            for href,label in row["links"]:
                if not href or label.lower()!="publicación isp":continue
                url=urljoin(self.PAGE,href);parsed=urlparse(url)
                if parsed.netloc not in ("www.ispch.gob.cl","ispch.gob.cl") or not parsed.path.lower().endswith(".pdf") or url in seen:continue
                seen.add(url)
                items.append(RawItem(self.SOURCE_SLUG,title[:300],url,self.SOURCE_NAME,self.SOURCE_TYPE,
                                     event_date=day,metadata={"discovered_from":self.PAGE,"listing_text":body}))
                break
        if not dated_rows:raise RuntimeError("ANAMED alert listing has no verified publication-date rows")
        return items[:20]
    def discover(self):return self.discover_from_html(fetch_html(self.PAGE))
