from __future__ import annotations
import io, re
from datetime import datetime
from urllib.request import Request, urlopen
from typing import Any

ISAPRES=("banmédica","banmedica","colmena","consalud","cruz blanca","nueva masvida","masvida","esencial","isalud","fundación","fundacion")
MONTHS={"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12}

USER_AGENT="AlicantoSaludBot/0.8.5.1 (+public-source-monitor)"
MAX_DOWNLOAD_BYTES=25*1024*1024

def _download(url:str,timeout:int=30,max_bytes:int=MAX_DOWNLOAD_BYTES)->bytes:
    """Legacy one-shot download (superintendencia_pipeline). Read in chunks and abort past ``max_bytes``.
    The F4/F6 capture does not use it: ``stats_capture.SisFetcher`` adds robots.txt, the SIS host allowlist
    (redirects included) and a time budget."""
    req=Request(url,headers={"User-Agent":USER_AGENT})
    with urlopen(req,timeout=timeout) as r:
        chunks,size=[],0
        while True:
            chunk=r.read(64*1024)
            if not chunk:break
            size+=len(chunk)
            if size>max_bytes:raise ValueError(f"download exceeds {max_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

def _norm(v:Any)->str:
    return " ".join(str(v or "").replace("\n"," ").split()).strip()

def family_from_title(title:str)->str|None:
    t=(title or "").lower()
    if "movilidad" in t:return "movilidad"
    if "ges" in t or "auge" in t:return "ges"
    if "suscripciones" in t or "desahucios" in t:return "suscripciones"
    if "cartera" in t and "beneficiarios" in t:return "cartera"
    return None

def _month_key(v:Any):
    if isinstance(v,datetime):return (v.year,v.month)
    s=_norm(v).lower()
    m=re.search(r"(20\d{2})[-/](\d{1,2})",s)
    if m and 1<=int(m.group(2))<=12:return (int(m.group(1)),int(m.group(2)))
    m=re.search(r"([a-záéíóú]{3,})[^\d]*(20\d{2})",s)
    if m:
        k=m.group(1)[:3]
        if k in MONTHS:return (int(m.group(2)),MONTHS[k])
    return None

def _isapre_label(row)->str|None:
    for v in row[:5]:
        s=_norm(v)
        low=s.lower()
        if any(x in low for x in ISAPRES) and len(s)<80:return s
    return None

def _safe_numeric(v):
    return float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) else None

def _title_period(title:str):
    s=(title or "").lower()
    m=re.search(r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(20\d{2})",s)
    if not m:return None
    names={"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
    return f"{m.group(2)}-{names[m.group(1)]:02d}"

from .ges_workbook import GES_PARSER  # noqa: E402,F401  (re-exported; mirrored in stats_fichas.GES_PARSER)

def parse_ges_workbook(book_bytes:bytes,title:str)->dict:
    """GES workbook under the year-to-date contract (Dirección 3-nov-2026); never infer causes.

    Delegates to ``ges_workbook.parse``: the year sheets of the release, the previous year and the one before are
    pinned by name; every column read reconciles to the declared total; the year-to-date column equals the
    cumulative cut minus the previous December cut (per problem and in total). Any failure returns HOLD."""
    from . import ges_workbook
    return ges_workbook.parse(book_bytes,title)

def source_specific_insights(url:str,title:str,validated_schemas:dict|None=None)->dict:
    """Fail-closed parser for three known SuperSalud statistical families.

    It only produces insights if a worksheet contains:
    - at least two identifiable period columns,
    - at least three identifiable Isapre rows,
    - one numeric observation per Isapre for those period columns.
    If the workbook layout is more complex, it returns no insight instead of guessing.
    """
    fam=family_from_title(title)
    if not fam or not url:return {"family":fam,"status":"unsupported","insights":[]}
    if fam=="ges":
        try:return parse_ges_workbook(_download(url),title)
        except Exception as e:return {"family":"ges","status":"download_or_open_failed","insights":[],"error":str(e)[:180]}
    try:
        from openpyxl import load_workbook
        wb=load_workbook(io.BytesIO(_download(url)),read_only=True,data_only=True)
    except Exception as e:
        return {"family":fam,"status":"download_or_open_failed","insights":[],"error":str(e)[:180]}

    candidates=[]
    for ws in wb.worksheets[:12]:
        rows=[list(r[:40]) for r in ws.iter_rows(min_row=1,max_row=350,values_only=True)]
        rows=[r for r in rows if any(v not in (None,"") for v in r)]
        for hi,h in enumerate(rows[:35]):
            periods=[(j,_month_key(v)) for j,v in enumerate(h) if _month_key(v)]
            if len(periods)<2 or len({period for _,period in periods})!=len(periods):continue
            periods=sorted(periods,key=lambda x:x[1])
            j1,p1=periods[-2];j2,p2=periods[-1]
            obs=[]
            seen=set()
            for r in rows[hi+1:]:
                if len(r)<=max(j1,j2):continue
                label=_isapre_label(r)
                if not label:continue
                key=label.lower()
                if key in seen:
                    # Complex sheet with repeated Isapre rows: do not aggregate blindly.
                    obs=[];break
                a=_safe_numeric(r[j1]);b=_safe_numeric(r[j2])
                if a is None or b is None:continue
                seen.add(key);obs.append((label,a,b))
            if len(obs)>=3:
                candidates.append((ws.title,p1,p2,obs))
                break

    if not candidates:return {"family":fam,"status":"schema_not_validated","insights":[]}

    sheet,p1,p2,obs=candidates[0]
    # Generic period/Isapre columns do not prove the metric, unit or denominator.
    # Require a reviewed, family-specific worksheet signature before publishing claims.
    if not validated_schemas or validated_schemas.get(fam)!=sheet:
        return {"family":fam,"status":"schema_not_validated","sheet":sheet,
                "period":f"{p2[0]}-{p2[1]:02d}","insights":[]}
    changes=[]
    for label,a,b in obs:
        if a==0:continue
        pct=(b-a)/abs(a)*100
        if abs(pct)<=100:
            changes.append((pct,label,a,b))
    if len(changes)<3:return {"family":fam,"status":"insufficient_comparable_rows","insights":[]}

    changes.sort()
    low=changes[0];high=changes[-1]
    period=f"{p2[0]}-{p2[1]:02d}"
    insights=[]
    if fam=="movilidad":
        insights.append(f"{high[1]} registra la mayor variación entre los dos últimos períodos comparables ({high[0]:+.1f}%).")
        insights.append(f"{low[1]} registra la menor variación entre los dos últimos períodos comparables ({low[0]:+.1f}%).")
    elif fam=="cartera":
        insights.append(f"{high[1]} muestra el mayor variación de la métrica comparable de cartera en el último período ({high[0]:+.1f}%).")
        insights.append(f"{low[1]} muestra la menor variación de la métrica comparable de cartera en el último período ({low[0]:+.1f}%).")
    elif fam=="suscripciones":
        insights.append(f"{high[1]} presenta la mayor variación en la métrica comparable de suscripciones/desahucios ({high[0]:+.1f}%).")
        insights.append(f"{low[1]} presenta la menor variación en la métrica comparable de suscripciones/desahucios ({low[0]:+.1f}%).")
    return {"family":fam,"status":"validated","sheet":sheet,"period":period,"insights":insights[:3]}
