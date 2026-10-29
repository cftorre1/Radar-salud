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

GES_PARSER="ges_pinned_year_reconciled_v2"  # mirrored in stats_fichas.GES_PARSER

def _ges_hold(reason:str,period:str|None,**extra)->dict:
    return {"family":"ges","status":"HOLD","hold_reason":reason,"parser":GES_PARSER,"period":period,"insights":[],**extra}

def parse_ges_workbook(book_bytes:bytes,title:str)->dict:
    """GES table under the corrected contract (Dirección 28-oct-2026); never infer causes.

    1. Pin the sheet of the reporting year taken from the title (e.g. 'a junio 2026' → the one sheet
       whose name contains 2026). Historical sheets such as 'Año 2005' are never read.
    2. Rows need a text problem label (a bare code such as '21' is not a label).
    3. The sum of the rows must equal the declared 'Total' row for Fonasa and for Isapre.
    Any failure returns HOLD with no insight.
    """
    try:
        from openpyxl import load_workbook
        wb=load_workbook(io.BytesIO(book_bytes),read_only=True,data_only=True)
    except Exception as exc:
        return {"family":"ges","status":"download_or_open_failed","insights":[],"error":str(exc)[:180]}
    period=_title_period(title)
    if not period:
        return {"family":"ges","status":"period_not_validated","insights":[]}
    year=period[:4]
    pinned=[ws for ws in wb.worksheets if re.search(rf"(?<!\d){year}(?!\d)",ws.title)]
    if len(pinned)!=1:
        return _ges_hold("HOLD_GES_SHEET_NOT_PINNED",period,sheets=[ws.title for ws in wb.worksheets][:30])
    ws=pinned[0]
    rows=[list(r[:30]) for r in ws.iter_rows(min_row=1,max_row=450,values_only=True)]
    for hi,row in enumerate(rows[:80]):
        labels=[_norm(v).lower() for v in row]
        fonasa=next((i for i,x in enumerate(labels) if "fonasa" in x),None)
        isapre=next((i for i,x in enumerate(labels) if "isapre" in x),None)
        name_col=next((i for i,x in enumerate(labels) if any(k in x for k in ("problema","patolog","condición","condicion"))),None)
        if fonasa is None or isapre is None or fonasa==isapre or name_col is None:
            continue
        observations=[];declared=None;total_row=None
        for offset,data in enumerate(rows[hi+1:],hi+2):
            if len(data)<=max(fonasa,isapre,name_col):continue
            label=_norm(data[name_col])
            if not label:continue
            a=_safe_numeric(data[fonasa]);b=_safe_numeric(data[isapre])
            if label.lower().startswith("total"):
                if a is not None and b is not None and declared is None:
                    declared=(a,b);total_row=offset
                continue
            if declared is not None:break  # rows after the declared total belong to another table
            if a is None or b is None:continue
            if not re.search(r"[a-záéíóúñ]",label,re.I):
                return _ges_hold("HOLD_GES_LABEL_NOT_TEXT",period,sheet=ws.title,row=offset,label=label[:40])
            if a<0 or b<0 or a!=int(a) or b!=int(b):
                return _ges_hold("HOLD_GES_INVALID_COUNT",period,sheet=ws.title,row=offset)
            observations.append({"label":label,"fonasa":int(a),"isapre":int(b),"row":offset})
        if len(observations)<3:
            continue
        if declared is None:
            return _ges_hold("HOLD_GES_TOTAL_MISSING",period,sheet=ws.title,header_row=hi+1)
        sums=(sum(o["fonasa"] for o in observations),sum(o["isapre"] for o in observations))
        reconciliation={"ok":sums==(int(declared[0]),int(declared[1])),"rows_sum":list(sums),"declared_total":[int(declared[0]),int(declared[1])],
                        "total_row":total_row}
        if not reconciliation["ok"]:
            return _ges_hold("HOLD_GES_RECONCILIATION",period,sheet=ws.title,reconciliation=reconciliation)
        largest=max(observations,key=lambda x:x["fonasa"]+x["isapre"])
        return {
            "family":"ges","status":"validated","parser":GES_PARSER,"sheet":ws.title,"period":period,
            "rows":len(observations),"reconciliation":reconciliation,
            "insights":[f"{largest['label']} registra el mayor número de casos GES informados por Fonasa e Isapres en la hoja {ws.title} del corte {period}; no se infiere prevalencia ni causalidad."],
            "evidence":{"header_row":hi+1,"fonasa_column":fonasa+1,"isapre_column":isapre+1,"label_column":name_col+1,
                        "aggregation":"rows reconciled to declared total","largest_row":largest["row"]},
        }
    return _ges_hold("HOLD_GES_SCHEMA_NOT_VALIDATED",period,sheet=ws.title)

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
