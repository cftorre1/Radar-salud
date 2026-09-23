from __future__ import annotations
import re
from urllib.parse import urljoin
from .models import RawItem
from .scouts import fetch_html
from .regulatory import _TableParser, _date

PAGES=[
 ("Informes de fiscalización","https://www.superdesalud.gob.cl/tax-otros-actos-de-la-superintendencia/informes-de-fiscalizacion-5126/","Sistema de salud","report"),
 ("Sanciones a Isapres","https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/sanciones-a-isapres-6248/","Isapres","sanction"),
 ("Sanciones a Prestadores","https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/sanciones-a-prestadores-6249/","Prestadores","sanction"),
]

AMOUNT_RE=re.compile(r"(?:multa\s+(?:de|por)|pago\s+de\s+una\s+multa\s+(?:de|por)?)\s*(\d[\d\.\,]*)\s*(UF|UTM|Unidades de Fomento|Unidades Tributarias Mensuales)",re.I)
ENTITY_PATTERNS=[
 re.compile(r"(?:a la Isapre|a Isapre)\s+([A-ZÁÉÍÓÚÑ0-9][A-Za-zÁÉÍÓÚáéíóúÑñ0-9 .&\-]+?)(?:\s+una|\s+la|\s+por|,)",re.I),
 re.compile(r"(?:al prestador|a la prestadora)\s+[“\"']?([^,“\"']{3,100})",re.I),
 re.compile(r"(?:a|al)\s+(Cl[ií]nica\s+[^,\.]{3,90}|Hospital\s+[^,\.]{3,90}|Centro\s+M[eé]dico[^,\.]{3,90})",re.I),
]

def _entity(text):
    for p in ENTITY_PATTERNS:
        m=p.search(text or "")
        if m:return " ".join(m.group(1).strip(" \"'“”").split())[:120]
    return None

def _amount(text):
    m=AMOUNT_RE.search(text or "")
    if not m:return (None,None)
    try:v=float(m.group(1).replace(".","").replace(",","."))
    except:v=None
    u=m.group(2).upper()
    unit="UTM" if "TRIBUT" in u or u=="UTM" else "UF"
    return (v,unit)

class SuperintendenciaFiscalizacionScout:
    SOURCE_SLUG="superintendencia_fiscalizacion";SOURCE_NAME="Superintendencia de Salud";SOURCE_TYPE="official"
    def discover(self):
        out=[];seen=set()
        for page_name,page_url,scope,kind in PAGES:
            try:html=fetch_html(page_url)
            except Exception as e:print("Fiscalizacion fetch:",page_name,e);continue
            p=_TableParser();p.feed(html)
            headers=[]
            if p.rows:headers=[c.get("text","") for c in p.rows[0]]
            for row in p.rows[1:]:
                cells=[c.get("text","") for c in row]
                row_text=" ".join(x for x in cells if x)
                event_date=_date(row_text)
                if not event_date:continue
                title=None;pdf=None;detail=None
                for c in row:
                    for href,label in c.get("links",[]):
                        absolute=urljoin(page_url,href)
                        if ".pdf" in absolute.lower() or "pdf" in label.lower():pdf=absolute
                        elif label and len(label)>12:detail=absolute;title=title or label
                if not title:
                    m=re.search(r"((?:Informe[^|]{3,180}|Resoluci[oó]n(?:\s+Exenta)?[^|]{3,160}))",row_text,re.I)
                    title=" ".join(m.group(1).split()) if m else row_text[:160]
                url=detail or pdf or page_url
                key=(title,url,kind)
                if key in seen:continue
                seen.add(key)
                summary=max(cells,key=len) if cells else row_text
                topic=cells[-1] if kind=="sanction" and len(cells)>=4 else None
                amount,unit=_amount(summary)
                entity=_entity(summary)
                out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                    event_date=event_date,raw_text=summary,
                    metadata={"listing_url":page_url,"listing_name":page_name,"scope":scope,"fiscalization_kind":kind,
                              "fiscalization_topic":topic,"regulated_entity":entity,"sanction_amount":amount,
                              "sanction_unit":unit,"attachments":[{"url":pdf,"label":"PDF"}] if pdf else []}))
        out.sort(key=lambda x:x.event_date or "",reverse=True);return out

def process_fiscalizacion(raw,cfg):
    from .pipeline import build_signal
    kind=raw.metadata.get("fiscalization_kind")
    scope=raw.metadata.get("scope") or "Sistema de salud"
    entity=raw.metadata.get("regulated_entity")
    topic=raw.metadata.get("fiscalization_topic")
    amount=raw.metadata.get("sanction_amount");unit=raw.metadata.get("sanction_unit")
    if kind=="sanction":
        bits=[]
        if entity:bits.append(entity)
        if amount and unit:bits.append(f"{amount:g} {unit}")
        if topic:bits.append(topic)
        why=("Permite observar qué incumplimientos está sancionando la Superintendencia y comparar recurrencia, "
             "materias y actores. Es especialmente útil para anticipar focos de cumplimiento y fiscalización.")
        raw.metadata.update({"what_happened":raw.raw_text or raw.title,"why_it_matters":why,
          "signal_types":["Fiscalización"],"scopes":[scope],"event_type":"SANCTION",
          "watch_tags":["fiscalización","sanción",scope.lower()]+([topic.lower()] if topic else []),
          "scores":{"economic":65 if amount else 50,"regulatory":88,"scope":72,"novelty":70,"actionability":84}})
    else:
        raw.metadata.update({"what_happened":raw.raw_text or raw.title,
          "why_it_matters":"Muestra qué materias, procesos o actores está revisando la Superintendencia y qué hallazgos está observando, una señal útil para anticipar focos de cumplimiento.",
          "signal_types":["Fiscalización"],"scopes":[scope],"event_type":"FISCALIZATION_REPORT",
          "watch_tags":["fiscalización","informe",scope.lower()],
          "scores":{"economic":55,"regulatory":90,"scope":78,"novelty":75,"actionability":88}})
    s=build_signal(raw,cfg);row=s.to_dict()
    row["signal_types"]=["Fiscalización"];row["scopes"]=[scope]
    row["regulated_entity"]=entity;row["sanction_amount"]=amount;row["sanction_unit"]=unit
    row["fiscalization_topic"]=topic;row["source_documents"]=raw.metadata.get("attachments",[])
    return row
