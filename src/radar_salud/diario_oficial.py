from __future__ import annotations
import re
from datetime import date, timedelta
from html import unescape
from urllib.parse import urljoin
from .models import RawItem
from .scouts import fetch_html

BASE="https://www.diariooficial.interior.gob.cl/edicionelectronica/index.php"

def _strip_html(s):
    s=re.sub(r"<script.*?</script>"," ",s,flags=re.S|re.I)
    s=re.sub(r"<style.*?</style>"," ",s,flags=re.S|re.I)
    s=re.sub(r"<[^>]+>"," ",s)
    return " ".join(unescape(s).split())

def _health_segments(html):
    # Keep blocks headed by MINISTERIO DE SALUD until the next ministry-level heading.
    # This is deliberately conservative: better to miss a marginal item than ingest unrelated law.
    out=[]
    pat=re.compile(r"MINISTERIO\s+DE\s+SALUD",re.I)
    starts=[m.start() for m in pat.finditer(html)]
    for st in starts:
        tail=html[st:]
        nxt=re.search(r"MINISTERIO\s+DE\s+(?!SALUD)[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s,]+",tail[30:],re.I)
        en=st+30+(nxt.start() if nxt else min(len(tail)-30,30000))
        out.append(html[st:en])
    return out

def _section_urls(day):
    idx=f"{BASE}?date={day.isoformat()}"
    html=fetch_html(idx)
    urls=[]
    for name in ("normas_generales.php","normas_particulares.php"):
        m=re.search(r'href=["\']([^"\']*'+re.escape(name)+r'[^"\']*)["\']',html,re.I)
        if m:urls.append(urljoin(idx,m.group(1)))
    # Some editions expose content directly from index.php. Include it as fallback.
    return list(dict.fromkeys(urls+[idx]))

class DiarioOficialHealthScout:
    SOURCE_SLUG="diario_oficial";SOURCE_NAME="Diario Oficial";SOURCE_TYPE="official"
    def discover(self, days_back: int=8):
        out=[];seen=set();today=date.today()
        for delta in range(days_back):
            d=today-timedelta(days=delta)
            for section in _section_urls(d):
                try:html=fetch_html(section)
                except Exception:continue
                for seg in _health_segments(html):
                    # Each "Ver PDF" belongs to the nearest preceding publication title.
                    for m in re.finditer(r'href=["\']([^"\']+\.pdf[^"\']*)["\'][^>]*>.*?(?:Ver\s+PDF|PDF).*?</a>',seg,re.I|re.S):
                        pdf=urljoin(section,m.group(1))
                        pre=seg[max(0,m.start()-1800):m.start()]
                        text=_strip_html(pre)
                        # Take the last meaningful phrase before "Ver PDF".
                        parts=re.split(r"\s{2,}|\|",text)
                        title=parts[-1].strip() if parts else text[-600:]
                        if len(title)>700:title=title[-700:]
                        # Prefer explicit act title if present.
                        act=re.search(r"((?:Ley|Decreto|Resoluci[oó]n|Circular)[^.]{15,650})$",title,re.I)
                        if act:title=act.group(1).strip()
                        if not title or pdf in seen:continue
                        # Health signal guard.
                        combined=f"{title} {_strip_html(seg[:m.start()])[-900:]}".lower()
                        if not any(k in combined for k in ("salud","isapre","fonasa","sanitari","medicamento","farmac","hospital","prestador","superintendencia de salud","instituto de salud pública","instituto de salud publica")):
                            continue
                        seen.add(pdf)
                        out.append(RawItem(
                          self.SOURCE_SLUG,title,pdf,self.SOURCE_NAME,self.SOURCE_TYPE,
                          event_date=d.isoformat(),raw_text=title,
                          metadata={"listing_url":section,"attachments":[{"url":pdf,"label":"PDF Diario Oficial"}]}
                        ))
        return out
