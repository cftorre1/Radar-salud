from __future__ import annotations
import re
import time
from datetime import date,timedelta
from html import unescape
from urllib.parse import urljoin
from .models import RawItem
from .scouts import fetch_html

BASE="https://www.diariooficial.interior.gob.cl/edicionelectronica/index.php"
ISSUERS=[
 ("Ministerio de Salud",r"\bMINISTERIO\s+DE\s+SALUD\b"),
 ("Subsecretaría de Salud Pública",r"\bSUBSECRETAR[IÍ]A\s+DE\s+SALUD\s+P[UÚ]BLICA\b"),
 ("Subsecretaría de Redes Asistenciales",r"\bSUBSECRETAR[IÍ]A\s+DE\s+REDES\s+ASISTENCIALES\b"),
 ("Superintendencia de Salud",r"\bSUPERINTENDENCIA\s+DE\s+SALUD\b"),
 ("Instituto de Salud Pública",r"\bINSTITUTO\s+DE\s+SALUD\s+P[UÚ]BLICA\b|\bISP\b"),
 ("FONASA",r"\bFONASA\b|\bFONDO\s+NACIONAL\s+DE\s+SALUD\b"),
 ("SUSESO",r"\bSUSESO\b|\bSUPERINTENDENCIA\s+DE\s+SEGURIDAD\s+SOCIAL\b"),
 ("COMPIN",r"\bCOMPIN\b|\bCOMISI[OÓ]N\s+DE\s+MEDICINA\s+PREVENTIVA\s+E\s+INVALIDEZ\b"),
]
ACT_RE=re.compile(r"\b(Ley|Decreto(?:\s+exento)?|Resoluci[oó]n(?:\s+exenta)?|Circular|Reglamento)\b",re.I)


FETCH_ATTEMPTS=3
FETCH_TIMEOUT_SECONDS=12
FETCH_BACKOFF_SECONDS=0.5

def _fetch_with_retry(url,attempts=FETCH_ATTEMPTS,timeout=FETCH_TIMEOUT_SECONDS,backoff=FETCH_BACKOFF_SECONDS):
    last_error=None
    for attempt in range(max(1, attempts)):
        try:
            return fetch_html(url, timeout=timeout)
        except Exception as exc:
            last_error=exc
            if attempt + 1 < max(1, attempts) and backoff > 0:
                time.sleep(backoff * (2 ** attempt))
    raise RuntimeError(
        f"Diario Oficial unavailable after {max(1, attempts)} attempts: {type(last_error).__name__}"
    ) from last_error

def _strip(s):
    s=re.sub(r"<script.*?</script>"," ",s,flags=re.S|re.I);s=re.sub(r"<style.*?</style>"," ",s,flags=re.S|re.I);s=re.sub(r"<[^>]+>"," ",s)
    return " ".join(unescape(s).split())

_SEREMI=re.compile(r"\bSECRETAR[IÍ]A\s+REGIONAL\s+MINISTERIAL\b",re.I)
_MINISTRY=re.compile(r"\bMINISTERIO\s+DE(?:L)?\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ,]+")  # listing headers are upper case

def _issuer(context, current=None):
    """Issuer of an entry: the latest health header inside it, else the header still in force
    from earlier entries. A ministry header other than Salud ends the health block; a SEREMI
    header counts as health only inside the Ministerio de Salud block."""
    matches=[]
    for name,pat in ISSUERS:
        for m in re.finditer(pat,context,re.I):matches.append((m.start(),name))
    for m in _MINISTRY.finditer(context):
        if not re.match(r"MINISTERIO\s+DE\s+SALUD\b",m.group(0)):matches.append((m.start(),None))
    if matches:
        current=max(matches,key=lambda x:x[0])[1]
    if current and _SEREMI.search(context) and current in ("Ministerio de Salud","Subsecretaría de Salud Pública","Subsecretaría de Redes Asistenciales"):
        current="SEREMI de Salud"
    return current

def _section_urls(day):
    ds=day.strftime("%d-%m-%Y");idx=f"{BASE}?date={ds}"
    html=_fetch_with_retry(idx)
    urls=[idx]
    for name in ("normas_generales.php","normas_particulares.php"):
        for m in re.finditer(r'href=["\']([^"\']*'+re.escape(name)+r'[^"\']*)["\']',html,re.I):urls.append(urljoin(idx,m.group(1)))
    return list(dict.fromkeys(urls))

_ACT_START=re.compile(r"(?:Extracto de\s+)?(?:Ley|Decreto(?:\s+(?:exento|supremo|con fuerza de ley))?|Resoluci[oó]n(?:\s+exenta)?|Circular|Reglamento)\b",re.I)

def _title(context_html):
    # The context is one listing entry (text since the previous PDF link): the act title
    # runs from its first act keyword to the end, numbers like "3.955" included.
    clean=re.sub(r"\bVer PDF\b.*$","",_strip(context_html)).strip()
    clean=re.sub(r"^\(?CVE-\d+\)?\s*","",clean)
    m=_ACT_START.search(clean)
    if m:return " ".join(clean[m.start():].split())[:650]
    bits=[x.strip() for x in re.split(r"\s{2,}|\|",clean) if len(x.strip())>12]
    return bits[-1][:650] if bits else ""

class DiarioOficialHealthScout:
    SOURCE_SLUG="diario_oficial";SOURCE_NAME="Diario Oficial";SOURCE_TYPE="official"
    def discover(self,days_back=8):
        out=[];seen=set();today=date.today()
        for delta in range(days_back):
            d=today-timedelta(days=delta)
            for section in _section_urls(d):
                try:html=_fetch_with_retry(section)
                except Exception:continue
                previous_end=0;current_issuer=None
                for m in re.finditer(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\'][^>]*>.*?</a>',html,re.I|re.S):
                    pdf=urljoin(section,m.group(1))
                    # One entry = everything since the previous PDF link (never half a tag or the previous act).
                    start=max(previous_end,m.start()-1800);previous_end=m.end()
                    anchor=[x.start() for x in re.finditer(r"<a\b",html[start:m.start()],re.I)];context_html=html[start:start+anchor[-1]] if anchor else html[start:m.start()]
                    if context_html[:1]!="<" and ">" in context_html[:200] and "<" not in context_html[:context_html.find(">")]:
                        context_html=context_html[context_html.find(">")+1:]
                    if pdf in seen:continue
                    context=_strip(context_html);issuer=current_issuer=_issuer(context,current_issuer)
                    if issuer=="SEREMI de Salud":current_issuer="Ministerio de Salud"
                    if not issuer:continue
                    title=_title(context_html)
                    if not title or not ACT_RE.search(title):continue
                    low=title.lower()
                    if any(x in low for x in ("calificación ambiental","calificacion ambiental","impacto ambiental","desarrollo inmobiliario","acuicultura","pesca","viviendas expuestas")):continue
                    seen.add(pdf)
                    out.append(RawItem(self.SOURCE_SLUG,title,pdf,self.SOURCE_NAME,self.SOURCE_TYPE,event_date=d.isoformat(),raw_text=title,metadata={"listing_url":section,"issuer":issuer,"attachments":[{"url":pdf,"label":"PDF Diario Oficial"}]}))
        print(f"DiarioOficial discovered={len(out)}");return out
