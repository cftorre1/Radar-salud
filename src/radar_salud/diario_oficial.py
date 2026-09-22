from __future__ import annotations
import re
from datetime import date,timedelta
from html import unescape
from urllib.parse import urljoin
from .models import RawItem
from .scouts import fetch_html

BASE="https://www.diariooficial.interior.gob.cl/edicionelectronica/index.php"

def _strip(s):
    s=re.sub(r"<script.*?</script>"," ",s,flags=re.S|re.I)
    s=re.sub(r"<style.*?</style>"," ",s,flags=re.S|re.I)
    s=re.sub(r"<[^>]+>"," ",s)
    return " ".join(unescape(s).split())

def _section_urls(day):
    ds=day.strftime("%d-%m-%Y")  # Diario Oficial expects DD-MM-YYYY
    idx=f"{BASE}?date={ds}"
    try:html=fetch_html(idx)
    except Exception:return []
    urls=[idx]
    for name in ("normas_generales.php","normas_particulares.php"):
        for m in re.finditer(r'href=["\']([^"\']*'+re.escape(name)+r'[^"\']*)["\']',html,re.I):
            urls.append(urljoin(idx,m.group(1)))
    return list(dict.fromkeys(urls))

class DiarioOficialHealthScout:
    SOURCE_SLUG="diario_oficial";SOURCE_NAME="Diario Oficial";SOURCE_TYPE="official"
    def discover(self,days_back=8):
        out=[];seen=set();today=date.today()
        for delta in range(days_back):
            d=today-timedelta(days=delta)
            for section in _section_urls(d):
                try:html=fetch_html(section)
                except Exception:continue
                # Look for every PDF link, then decide from nearby context whether it belongs to Salud.
                for m in re.finditer(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\'][^>]*>(.*?)</a>',html,re.I|re.S):
                    pdf=urljoin(section,m.group(1))
                    if pdf in seen:continue
                    context=_strip(html[max(0,m.start()-2600):m.start()])
                    # The nearest ministry heading in the preceding context must be Salud,
                    # or the act itself must clearly refer to a health authority.
                    mins=list(re.finditer(r"MINISTERIO\s+DE\s+([A-ZÁÉÍÓÚÑ\s]+)",context,re.I))
                    nearest=mins[-1].group(1).strip().lower() if mins else ""
                    health=("salud" in nearest) or any(k in context.lower() for k in (
                      "superintendencia de salud","instituto de salud pública","instituto de salud publica",
                      "isapre","fonasa","prestador","sanitari","medicamento"))
                    if not health:continue
                    # Extract the last act-like sentence.
                    tail=context[-1400:]
                    acts=re.findall(r"((?:Ley|Decreto(?:\s+exento)?|Resoluci[oó]n(?:\s+exenta)?|Circular)[^.]{15,800})",tail,re.I)
                    title=" ".join(acts[-1].split()) if acts else tail[-600:]
                    if len(title)<15:continue
                    seen.add(pdf)
                    out.append(RawItem(self.SOURCE_SLUG,title,pdf,self.SOURCE_NAME,self.SOURCE_TYPE,
                      event_date=d.isoformat(),raw_text=title,
                      metadata={"listing_url":section,"attachments":[{"url":pdf,"label":"PDF Diario Oficial"}]}))
        print(f"DiarioOficial discovered={len(out)}")
        return out
