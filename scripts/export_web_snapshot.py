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

def _latest(xs):
    ds=[_d(x.get("event_date")) for x in xs];ds=[x for x in ds if x];return max(ds) if ds else datetime.now().date()

def _garbage(s):
    t=" ".join(str(s.get(k,"") or "") for k in ("title","what_happened","why_it_matters")).lower()
    return any(x in t for x in ("@context","@graph","schema.org",'"@type"','"ispartof"'))

def _monthly(s):
    t=(s.get("title") or "").lower()
    return s.get("source_name")=="Superintendencia de Salud" and "isapre" in t and any(x in t for x in ("mensual","cartera","movilidad","suscripciones"))

def _period(s):
    for f in s.get("key_facts",[]) or []:
        m=re.search(r"actualizada? a\s+(.+?)[\.]?$",f,re.I)
        if m:return re.sub(r"\s+de\s+(20\d{2})$",r" \1",m.group(1).strip(" .").lower())
    t=s.get("title","");m=re.search(r"[-–]\s*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)(?:\s+de)?\s+20\d{2}",t,re.I)
    return re.sub(r"\s+de\s+(20\d{2})$",r" \1",m.group(0).lstrip("-– ").strip().lower()) if m else None

def _group(items):
    if len(items)<2:return items
    groups=defaultdict(list)
    for s in items:groups[_period(s) or "actual"].append(s)
    p,best=max(groups.items(),key=lambda kv:(len(kv[1]),max((_d(x.get("event_date")) or date.min) for x in kv[1])))
    if len(best)<2:return [max(items,key=lambda x:_d(x.get("event_date")) or date.min)]
    labels=[]
    for s in best:
        t=(s.get("title") or "").lower()
        if "movilidad" in t:labels.append("movilidad de cartera de cotizantes a nivel regional")
        elif "suscripciones" in t or "desahucios" in t:labels.append("suscripciones y desahucios")
        elif "regional" in t:labels.append("cartera del sistema Isapre a nivel regional")
        elif "cartera" in t:labels.append("cartera total del sistema Isapre")
    labels=list(dict.fromkeys(labels))
    rel=[{"title":s.get("title"),"summary":s.get("what_happened") or (s.get("key_facts") or [""])[0],"url":s.get("source_url"),"event_date":s.get("event_date")} for s in best if s.get("source_url")]
    base=dict(max(best,key=lambda x:x.get("radar_score",0)))
    base.update({
      "title":f"Actualización mensual del sistema Isapre — {p}",
      "what_happened":f"La Superintendencia actualizó {len(best)} conjuntos de información correspondientes a: "+"; ".join(labels)+".",
      "why_it_matters":"Leídos en conjunto, permiten observar tamaño y composición de cartera, entradas y salidas, movilidad entre competidores y diferencias regionales sin revisar publicaciones aisladas.",
      "related_sources":rel,"grouped_count":len(best),"grouped_titles":[s.get("title") for s in best],
      "signal_types":["Datos"],"scopes":["Isapres"],"radar_score":max(s.get("radar_score",0) for s in best),
      "confidence_score":min(s.get("confidence_score",100) for s in best),
      "event_date":max((s.get("event_date") for s in best if s.get("event_date")),default=base.get("event_date"))
    })
    return [base]

def _tag_defaults(s):
    r=dict(s)
    if not r.get("signal_types"):
        cat=(r.get("category") or "").lower()
        if "regul" in cat:r["signal_types"]=["Normativa"]
        elif "legal" in cat:r["signal_types"]=["Legal"]
        elif "innov" in cat:r["signal_types"]=["Innovación"]
        elif "talento" in cat:r["signal_types"]=["Talento"]
        else:r["signal_types"]=["Datos"]
    if not r.get("scopes"):
        dom=r.get("system_domain")
        r["scopes"]=[{"HEALTH_INSURANCE":"Isapres","OCCUPATIONAL_HEALTH":"Salud laboral","PUBLIC_HEALTH":"Salud pública"}.get(dom,"Sistema de salud")]
    return r

def curate(signals,min_local=5,max_local=7):
    clean=[_tag_defaults(s) for s in signals if not _garbage(s) and s.get("validation_status")!="human_review_required"]
    if not clean:return []
    latest=_latest(clean); current=[s for s in clean if not _d(s.get("event_date")) or (latest-_d(s.get("event_date"))).days<=21]
    monthly=[s for s in current if _monthly(s)]; rest=[s for s in current if s not in monthly];selected=_group(monthly)+rest
    existing={x.get("source_url") or x.get("title") for x in selected}
    if len(selected)<min_local:
        older=[s for s in clean if s not in current and not _monthly(s) and _d(s.get("event_date")) and (latest-_d(s.get("event_date"))).days<=120]
        older.sort(key=lambda s:(s.get("radar_score",0),_d(s.get("event_date")) or date.min),reverse=True)
        for s in older:
            if len(selected)>=min_local:break
            k=s.get("source_url") or s.get("title")
            if k in existing:continue
            r=dict(s);age=(latest-_d(r.get("event_date"))).days;r["recency_label"]="Contexto reciente" if age<=60 else "Contexto";selected.append(r);existing.add(k)
    selected.sort(key=lambda s:(_d(s.get("event_date")) or date.min,s.get("radar_score",0)),reverse=True)
    return selected[:max_local]

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",default="web/data/radar_today.json");ap.add_argument("--profile",default=None);ap.add_argument("--date",default=None);args=ap.parse_args()
    raw=json.loads(Path(args.input).read_text(encoding="utf-8"));signals=raw.get("signals",raw) if isinstance(raw,dict) else raw
    payload={"date":args.date or datetime.now().date().isoformat(),"generated_at":datetime.now(timezone.utc).isoformat(),"signals":curate(signals)}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8");print(out)
if __name__=="__main__":main()
