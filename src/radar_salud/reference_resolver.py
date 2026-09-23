from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.request import Request,urlopen

class _Page(HTMLParser):
    def __init__(self):
        super().__init__();self.title="";self.text=[];self._title=False
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="title":self._title=True
    def handle_endtag(self,tag):
        if tag.lower()=="title":self._title=False
    def handle_data(self,data):
        t=" ".join(data.split())
        if not t:return
        self.text.append(t)
        if self._title:self.title+=" "+t

def _fetch(url):
    req=Request(url,headers={"User-Agent":"AlicantoSaludBot/0.8.5 (+public-source-monitor)"})
    with urlopen(req,timeout=20) as r:return r.read().decode(r.headers.get_content_charset() or "utf-8",errors="replace")

def _norm(s):return " ".join((s or "").split())

def _visible_summary(p:_Page,kind:str,num:str)->str|None:
    text=_norm(" ".join(p.text))
    m=re.search(r"\bMateria\s*:?\s*(.{25,900}?)(?=\s+(?:Fecha|Vigencia|Temas|Documentos?|Descargar|Ver\s+documento|$))",text,re.I)
    if m:return _norm(m.group(1))[:650]
    pat=rf"{re.escape(kind)}[^.]{{0,80}}{re.escape(num)}"
    m=re.search(pat,text,re.I)
    if m:
        tail=text[m.end():m.end()+1200]
        chunks=[_norm(x) for x in re.split(r"\s{2,}|[•|]",tail) if len(_norm(x))>=45]
        for x in chunks:
            if not re.search(r"superintendencia de salud|inicio|buscar|imprimir|compartir",x,re.I):return x[:650]
    return None

def resolve_reference(ref:str,relationship:str|None=None):
    raw=ref or ""
    m=re.search(r"\bcircular\s+(?:if\s*[/\-]?\s*)?n?[°º]?\s*(\d+)",raw,re.I)
    if not m:
        if re.search(r"\b(Oficio|Resoluci[oó]n|Ley|DFL|D\.?S\.?|Decreto)\b",raw,re.I):
            return {"title":_norm(raw),"summary":None,"relationship":relationship or "Antecedente normativo citado por el documento actual.","url":None,"event_date":None,"verified":False}
        return None
    n=m.group(1);url=f"https://www.superdesalud.gob.cl/normativa/circular-if-n{n}/"
    try:p=_Page();p.feed(_fetch(url))
    except Exception:return None
    hay=_norm(" ".join([p.title,*p.text[:220]])).lower()
    pats=[rf"circular\s+if\s*/?\s*n?[°º]?\s*{re.escape(n)}\b",rf"circular\s+n?[°º]?\s*{re.escape(n)}\b",rf"circular-if-n{re.escape(n)}\b"]
    if not any(re.search(x,hay,re.I) for x in pats):return None
    summary=_visible_summary(p,"Circular",n)
    if not summary:return None
    return {"title":f"Circular IF/N°{n}","summary":summary,"relationship":relationship or "Antecedente normativo citado por el documento actual.","url":url,"event_date":None,"verified":True}
