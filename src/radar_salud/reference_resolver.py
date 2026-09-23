from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.request import Request,urlopen

class _Page(HTMLParser):
    def __init__(self):
        super().__init__();self.desc="";self.title="";self.text=[];self._title=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);tag=tag.lower()
        if tag=="meta" and (a.get("name")=="description" or a.get("property")=="og:description"):
            if a.get("content") and not self.desc:self.desc=" ".join(a["content"].split())
        elif tag=="title":self._title=True
    def handle_endtag(self,tag):
        if tag.lower()=="title":self._title=False
    def handle_data(self,data):
        t=" ".join(data.split())
        if not t:return
        self.text.append(t)
        if self._title:self.title+=" "+t

def _fetch(url):
    req=Request(url,headers={"User-Agent":"AlicantoSaludBot/0.5 (+public-source-monitor)"})
    with urlopen(req,timeout=20) as r:return r.read().decode(r.headers.get_content_charset() or "utf-8",errors="replace")

def resolve_reference(ref:str,relationship:str|None=None):
    m=re.search(r"circular\s+(?:if\s*[/\-]?\s*)?n?[°º]?\s*(\d+)",ref or "",re.I)
    if not m:return None
    n=m.group(1);url=f"https://www.superdesalud.gob.cl/normativa/circular-if-n{n}/"
    try:p=_Page();p.feed(_fetch(url))
    except Exception:return None
    hay=" ".join([p.title,p.desc,*p.text[:100]]).lower()
    pats=[rf"circular\s+if\s*/?\s*n?[°º]?\s*{re.escape(n)}\b",rf"circular\s+n?[°º]?\s*{re.escape(n)}\b",rf"circular-if-n{re.escape(n)}\b"]
    if not any(re.search(x,hay,re.I) for x in pats):return None
    summary=(p.desc or "").strip() or f"Circular IF/N°{n}, antecedente oficial citado por el documento."
    return {"title":f"Circular IF/N°{n}","summary":summary[:500],"relationship":relationship or "Antecedente normativo citado por el documento actual.","url":url,"event_date":None}
