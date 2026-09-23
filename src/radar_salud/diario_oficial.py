from __future__ import annotations
import re
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

def _strip(s):
    s=re.sub(r"<script.*?</script>"," ",s,flags=re.S|re.I);s=re.sub(r"<style.*?</style>"," ",s,flags=re.S|re.I);s=re.sub(r"<[^>]+>"," ",s)
    return " ".join(unescape(s).split())

def _issuer(context):
    matches=[]
    for name,pat in ISSUERS:
        for m in re.finditer(pat,context,re.I):matches.append((m.start(),name))
    return max(matches)[1] if matches else None

def _section_urls(day):
    ds=day.strftime("%d-%m-%Y");idx=f"{BASE}?date={ds}"
    try:html=fetch_html(idx)
    except Exception:return []
    urls=[idx]
    for name in ("normas_generales.php","normas_particulares.php"):
        for m in re.finditer(r'href=["\']([^"\']*'+re.escape(name)+r'[^"\']*)["\']',html,re.I):urls.append(urljoin(idx,m.group(1)))
    return list(dict.fromkeys(urls))

def _title(context_html):
    clean=_strip(context_html)
    m=re.search(r"((?:Ley|Decreto(?:\s+exento)?|Resoluci[oó]n(?:\s+exenta)?|Circular|Reglamento)[^.]{3,650})$",clean,re.I)
    if m:return " ".join(m.group(1).split())
    bits=[x.strip() for x in re.split(r"\s{2,}|\|",clean) if len(x.strip())>12]
    return bits[-1][:650] if bits else ""

class DiarioOficialHealthScout:
    SOURCE_SLUG="diario_oficial";SOURCE_NAME="Diario Oficial";SOURCE_TYPE="official"
    def discover(self,days_back=8):
        out=[];seen=set();today=date.today()
        for delta in range(days_back):
            d=today-timedelta(days=delta)
            for section in _section_urls(d):
                try:html=fetch_html(section)
                except Exception:continue
                for m in re.finditer(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\'][^>]*>.*?</a>',html,re.I|re.S):
                    pdf=urljoin(section,m.group(1))
                    if pdf in seen:continue
                    context_html=html[max(0,m.start()-1800):m.start()];context=_strip(context_html);issuer=_issuer(context)
                    if not issuer:continue
                    title=_title(context_html)
                    if not title or not ACT_RE.search(title):continue
                    low=title.lower()
                    if any(x in low for x in ("calificación ambiental","calificacion ambiental","impacto ambiental","desarrollo inmobiliario","acuicultura","pesca","viviendas expuestas")):continue
                    seen.add(pdf)
                    out.append(RawItem(self.SOURCE_SLUG,title,pdf,self.SOURCE_NAME,self.SOURCE_TYPE,event_date=d.isoformat(),raw_text=title,metadata={"listing_url":section,"issuer":issuer,"attachments":[{"url":pdf,"label":"PDF Diario Oficial"}]}))
        print(f"DiarioOficial discovered={len(out)}");return out
