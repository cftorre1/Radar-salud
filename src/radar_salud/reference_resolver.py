from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.request import Request,urlopen

class _Meta(HTMLParser):
    def __init__(self):
        super().__init__();self.desc="";self.title="";self.links=[];self._in_title=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);tag=tag.lower()
        if tag=="meta" and (a.get("name")=="description" or a.get("property")=="og:description"):
            if a.get("content") and not self.desc:self.desc=" ".join(a["content"].split())
        elif tag=="title":self._in_title=True
        elif tag=="a" and a.get("href"):self.links.append(a["href"])
    def handle_endtag(self,tag):
        if tag.lower()=="title":self._in_title=False
    def handle_data(self,data):
        if self._in_title:self.title+=" "+data

def _fetch(url):
    req=Request(url,headers={"User-Agent":"AlicantoSaludBot/0.4 (+public-source-monitor)"})
    with urlopen(req,timeout=20) as r:return r.read().decode(r.headers.get_content_charset() or "utf-8",errors="replace")

def resolve_reference(ref: str):
    m=re.search(r"circular\s+(?:if\s*[/\-]?\s*)?n?[°º]?\s*(\d+)",ref or "",re.I)
    if not m:return None
    n=m.group(1)
    url=f"https://www.superdesalud.gob.cl/normativa/circular-if-n{n}/"
    try:
        p=_Meta();p.feed(_fetch(url))
    except Exception:
        return None
    summary=(p.desc or "").strip()
    if not summary:summary=f"Antecedente normativo citado por el documento actual: Circular IF/N°{n}."
    return {"title":f"Circular IF/N°{n}","summary":summary[:500],"url":url,"event_date":None}
