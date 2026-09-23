from __future__ import annotations
import io, re
from datetime import datetime
from urllib.request import Request, urlopen
from typing import Any

ISAPRES=("banmédica","banmedica","colmena","consalud","cruz blanca","nueva masvida","masvida","esencial","isalud","fundación","fundacion")
MONTHS={"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12}

def _download(url:str,timeout:int=45)->bytes:
    req=Request(url,headers={"User-Agent":"AlicantoSaludBot/0.8.5.1 (+public-source-monitor)"})
    with urlopen(req,timeout=timeout) as r:return r.read()

def _norm(v:Any)->str:
    return " ".join(str(v or "").replace("\n"," ").split()).strip()

def family_from_title(title:str)->str|None:
    t=(title or "").lower()
    if "movilidad" in t:return "movilidad"
    if "suscripciones" in t or "desahucios" in t:return "suscripciones"
    if "cartera" in t and "beneficiarios" in t:return "cartera"
    return None

def _month_key(v:Any):
    if isinstance(v,datetime):return (v.year,v.month)
    s=_norm(v).lower()
    m=re.search(r"(20\d{2})[-/](\d{1,2})",s)
    if m:return (int(m.group(1)),int(m.group(2)))
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

def source_specific_insights(url:str,title:str)->dict:
    """Fail-closed parser for three known SuperSalud statistical families.

    It only produces insights if a worksheet contains:
    - at least two identifiable period columns,
    - at least three identifiable Isapre rows,
    - one numeric observation per Isapre for those period columns.
    If the workbook layout is more complex, it returns no insight instead of guessing.
    """
    fam=family_from_title(title)
    if not fam or not url:return {"family":fam,"status":"unsupported","insights":[]}
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
            if len(periods)<2:continue
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
        insights.append(f"{high[1]} registra la mayor variación positiva entre los dos últimos períodos comparables ({high[0]:+.1f}%).")
        insights.append(f"{low[1]} registra la mayor variación negativa entre los dos últimos períodos comparables ({low[0]:+.1f}%).")
    elif fam=="cartera":
        insights.append(f"{high[1]} muestra el mayor crecimiento de la métrica comparable de cartera en el último período ({high[0]:+.1f}%).")
        insights.append(f"{low[1]} muestra la mayor caída de la métrica comparable de cartera en el último período ({low[0]:+.1f}%).")
    elif fam=="suscripciones":
        insights.append(f"{high[1]} presenta la mayor variación positiva en la métrica comparable de suscripciones/desahucios ({high[0]:+.1f}%).")
        insights.append(f"{low[1]} presenta la mayor variación negativa en la métrica comparable de suscripciones/desahucios ({low[0]:+.1f}%).")
    return {"family":fam,"status":"validated","sheet":sheet,"period":period,"insights":insights[:3]}
