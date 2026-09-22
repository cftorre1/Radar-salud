from __future__ import annotations
import argparse,json,re
from collections import defaultdict
from datetime import datetime,timezone,date
from pathlib import Path

def _d(v):
    if not v:return None
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).date()
    except:
        try:return date.fromisoformat(str(v)[:10])
        except:return None

def _garbage(s):
    t=" ".join(str(s.get(k,"") or "") for k in ("title","what_happened","why_it_matters")).lower()
    return any(x in t for x in ("@context","@graph","schema.org",'"@type"','"ispartof"'))

def _doc_key(s):
    t=(s.get("title") or "")+" "+(s.get("what_happened") or "")
    m=re.search(r"circular\s+(?:n[uú]mero\s+)?(?:if\s*[/\-]?\s*)?n?[°º]?\s*(\d+)",t,re.I)
    if m:return "circular-if-"+m.group(1)
    m=re.search(r"resoluci[oó]n(?:\s+exenta)?\s+(?:n[uú]mero\s+)?(?:if\s*[/\-]?\s*)?n?[°º]?\s*([\d\.]+)",t,re.I)
    if m:return "res-"+re.sub(r"\D","",m.group(1))
    return None

def _merge_duplicates(signals):
    groups=defaultdict(list);other=[]
    for s in signals:
        k=_doc_key(s)
        if k:groups[k].append(s)
        else:other.append(s)
    merged=[]
    for k,items in groups.items():
        if len(items)==1:merged.append(items[0]);continue
        # Prefer the richest signal, usually regulator analysis over publication mirror.
        base=max(items,key=lambda x:(len(x.get("key_points",[]) or []),len(x.get("what_happened","")),x.get("source_name")=="Superintendencia de Salud"))
        r=dict(base)
        rel=list(r.get("related_sources",[]) or [])
        seen={x.get("url") for x in rel}
        for x in items:
            if x is base:continue
            u=x.get("source_url")
            if u and u not in seen:
                rel.append({"title":x.get("title"),"summary":x.get("what_happened"),"url":u,"event_date":x.get("event_date"),"source_name":x.get("source_name")})
                seen.add(u)
        r["related_sources"]=rel
        r["corroborating_sources"]=list(dict.fromkeys([x.get("source_name") for x in items if x.get("source_name")]))
        r["event_date"]=max([x.get("event_date") for x in items if x.get("event_date")] or [r.get("event_date")])
        merged.append(r)
    return other+merged

def _ref_key(text):
    t=text or ""
    m=re.search(r"circular\s+(?:if\s*[/\-]?\s*)?n?[°º]?\s*(\d+)",t,re.I)
    if m:return "circular-if-"+m.group(1)
    m=re.search(r"resoluci[oó]n(?:\s+exenta)?\s+(?:if\s*[/\-]?\s*)?n?[°º]?\s*([\d\.]+)",t,re.I)
    if m:return "res-"+re.sub(r"\D","",m.group(1))
    return None

def _resolve_related_norms(signals):
    index={}
    for s in signals:
        k=_doc_key(s)
        if k and k not in index:index[k]=s
    out=[]
    for s in signals:
        r=dict(s);rels=[]
        refs=r.get("related_reference_ids",[]) or []
        # fallback: detect refs from visible analysis
        if not refs:
            text=" ".join([r.get("what_happened",""),*(r.get("key_points",[]) or [])])
            refs=re.findall(r"(?:Circular|Resoluci[oó]n(?:\s+Exenta)?)\s+(?:IF/)?N?[°º]?\s*[\d\.]+",text,re.I)
        seen=set()
        for ref in refs:
            k=_ref_key(ref)
            target=index.get(k)
            if not target or target.get("source_url")==r.get("source_url"):continue
            u=target.get("source_url")
            if u in seen:continue
            seen.add(u)
            rels.append({
              "title":target.get("title"),
              "summary":target.get("what_happened"),
              "url":u,
              "event_date":target.get("event_date"),
            })
        r["related_norms"]=rels[:4]
        out.append(r)
    return out

def _monthly(s):
    t=(s.get("title") or "").lower()
    return s.get("source_name")=="Superintendencia de Salud" and "isapre" in t and any(x in t for x in ("mensual","cartera","movilidad","suscripciones"))

def _period(s):
    for f in s.get("key_facts",[]) or []:
        m=re.search(r"actualizada? a\s+(.+?)[\.]?$",f,re.I)
        if m:return re.sub(r"\s+de\s+(20\d{2})$",r" \1",m.group(1).strip(" .").lower())
    t=s.get("title","");m=re.search(r"[-–]\s*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)(?:\s+de)?\s+20\d{2}",t,re.I)
    return re.sub(r"\s+de\s+(20\d{2})$",r" \1",m.group(0).lstrip("-– ").strip().lower()) if m else None

def _group_monthly(items):
    if len(items)<2:return items
    groups=defaultdict(list)
    for s in items:groups[_period(s) or "actual"].append(s)
    out=[]
    for p,best in groups.items():
        if len(best)<2:
            out.extend(best);continue
        labels=[]
        for s in best:
            t=(s.get("title") or "").lower()
            if "movilidad" in t:labels.append("movilidad de cartera de cotizantes")
            elif "suscripciones" in t or "desahucios" in t:labels.append("suscripciones y desahucios")
            elif "regional" in t:labels.append("cartera regional")
            elif "cartera" in t:labels.append("cartera total")
        labels=list(dict.fromkeys(labels))
        base=dict(max(best,key=lambda x:x.get("radar_score",0)))
        rel=[{"title":s.get("title"),"summary":s.get("what_happened"),"url":s.get("source_url"),"event_date":s.get("event_date")} for s in best if s.get("source_url")]
        ins=[]
        for s in best:
            for x in s.get("data_insights",[]) or []:
                if x not in ins:ins.append(x)
        base.update({
          "title":f"Actualización mensual del sistema Isapre — {p}",
          "what_happened":f"La Superintendencia actualizó {len(best)} conjuntos de información: "+"; ".join(labels)+".",
          "why_it_matters":"Leídos en conjunto, permiten observar cambios de cartera, movilidad y diferencias regionales sin revisar publicaciones aisladas.",
          "related_sources":rel,"grouped_count":len(best),"signal_types":["Datos"],"scopes":["Isapres"],
          "data_insights":ins[:3],
          "event_date":max([s.get("event_date") for s in best if s.get("event_date")] or [base.get("event_date")])
        })
        out.append(base)
    return out

def _tags(s):
    r=dict(s)
    if not r.get("signal_types"):
        cat=(r.get("category") or "").lower()
        r["signal_types"]=["Normativa" if "regul" in cat else "Legal" if "legal" in cat else "Datos"]
    if not r.get("scopes"):
        dom=r.get("system_domain")
        r["scopes"]=[{"HEALTH_INSURANCE":"Isapres","OCCUPATIONAL_HEALTH":"Salud laboral","PUBLIC_HEALTH":"Salud pública"}.get(dom,"Sistema de salud")]
    return r

def curate(signals):
    clean=[]
    for s in signals:
        if _garbage(s) or s.get("validation_status")=="human_review_required":continue
        if s.get("source_name") in ("Ministerio de Salud","Diario Financiero","SUSESO","Diario Oficial") and not _d(s.get("event_date")):continue
        clean.append(_tags(s))
    if not clean:return []
    latest=max([_d(x.get("event_date")) for x in clean if _d(x.get("event_date"))] or [date.today()])
    ninety=[s for s in clean if _d(s.get("event_date")) and (latest-_d(s.get("event_date"))).days<=90]
    # Keep all relevant signals in the 90-day window. Only monthly repetitive stats are bundled.
    monthly=[s for s in ninety if _monthly(s)]
    rest=[s for s in ninety if s not in monthly]
    selected=_group_monthly(monthly)+rest
    selected=_merge_duplicates(selected)
    selected=_resolve_related_norms(selected)
    selected.sort(key=lambda s:(_d(s.get("event_date")) or date.min,s.get("radar_score",0)),reverse=True)
    return selected

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",default="web/data/radar_today.json");args=ap.parse_args()
    raw=json.loads(Path(args.input).read_text(encoding="utf-8"));signals=raw.get("signals",raw) if isinstance(raw,dict) else raw
    payload={"date":datetime.now().date().isoformat(),"generated_at":datetime.now(timezone.utc).isoformat(),"signals":curate(signals)}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8");print(out)
if __name__=="__main__":main()
