from __future__ import annotations
import argparse,json,re,shutil
from collections import defaultdict
from datetime import datetime,timezone,date
from pathlib import Path
from radar_salud.reference_resolver import resolve_reference
from radar_salud.editorial_gate import publication_ready

TYPES=("Normativa","Legal","Noticias","Datos","Fiscalización")

def _d(v):
    if not v:return None
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).date()
    except:
        try:return date.fromisoformat(str(v)[:10])
        except:return None

def _normalize_type(s):
    r=dict(s);types=[]
    for x in r.get("signal_types",[]) or []:
        x=str(x).strip();x="Noticias" if x=="Mercado" else x
        if x in TYPES and x not in types:types.append(x)
    if not types:
        cat=(r.get("category") or "").lower()
        types=["Fiscalización" if "fiscal" in cat else ("Normativa" if "regul" in cat else ("Legal" if "legal" in cat else "Noticias"))]
    r["signal_types"]=types;return r

def _normalize_scopes(s):
    r=dict(s);out=[];text=" ".join(str(r.get(k,"") or "") for k in ("title","what_happened","why_it_matters")).lower()
    for scope in r.get("scopes",[]) or []:
        x=str(scope).strip();low=x.lower()
        if "isapre" in low and "fonasa" in low:
            if re.search(r"\bisapre(?:s)?\b|instituciones? de salud previsional",text):out.append("Isapres")
            if re.search(r"\bfonasa\b|fondo nacional de salud",text):out.append("Fonasa")
        elif low in ("isapre","isapres"):out.append("Isapres")
        elif low=="fonasa":out.append("Fonasa")
        else:out.append(x)
    r["scopes"]=list(dict.fromkeys(out)) or ["Sistema de salud"];return r

def _doc_key(s):
    title=s.get("title","") or ""
    m=re.search(r"resoluci[oó]n(?:\s+exenta)?\s+(?:n[uú]mero\s+)?(?:if|ip)?\s*[/\-]?\s*n?[°º]?\s*([\d\.]+)",title,re.I)
    if m:return "res-"+re.sub(r"\D","",m.group(1))
    m=re.search(r"circular\s+(?:n[uú]mero\s+)?(?:if|ip)?\s*[/\-]?\s*n?[°º]?\s*(\d+)",title,re.I)
    if m:return "circular-"+m.group(1)
    return None

def _merge_duplicates(signals):
    groups=defaultdict(list);other=[]
    for s in signals:
        k=_doc_key(s)
        if k:groups[k].append(s)
        else:other.append(s)
    merged=[]
    for _,items in groups.items():
        if len(items)==1:merged.append(items[0]);continue
        base=max(items,key=lambda x:(x.get("source_name")=="Superintendencia de Salud",len(x.get("key_points",[]) or []),len(x.get("what_happened",""))))
        r=dict(base);alts=[];seen={r.get("source_url")}
        for x in items:
            if x is base:continue
            u=x.get("source_url")
            if u and u not in seen:
                alts.append({"title":x.get("title"),"source_name":x.get("source_name"),"url":u,"event_date":x.get("event_date")});seen.add(u)
        r["source_alternatives"]=alts;merged.append(r)
    return other+merged

def _relmap(s):
    return {str(x["id"]).strip():str(x.get("relationship") or "").strip() for x in s.get("related_reference_contexts",[]) or [] if isinstance(x,dict) and x.get("id")}

def _ref_key(text):
    m=re.search(r"circular\s+(?:if\s*[/\-]?\s*)?n?[°º]?\s*(\d+)",text or "",re.I)
    return "circular-"+m.group(1) if m else None

def _related_context(signals):
    idx={_doc_key(s):s for s in signals if _doc_key(s)};out=[]
    for s in signals:
        r=dict(s);rels=[];seen=set();relmap=_relmap(r)
        for ref in r.get("related_reference_ids",[]) or []:
            k=_ref_key(ref);relationship=relmap.get(ref) or "Antecedente normativo citado por el documento actual."
            target=idx.get(k) if k else None
            if target and target.get("source_url")!=r.get("source_url"):
                item={"title":target.get("title"),"summary":target.get("what_happened"),"relationship":relationship,
                      "url":target.get("source_url"),"event_date":target.get("event_date"),"verified":True}
            else:item=resolve_reference(ref,relationship)
            if not item:continue
            identity=item.get("url") or item.get("title")
            if not identity or identity in seen or item.get("url")==r.get("source_url"):continue
            seen.add(identity);rels.append(item)
        r["related_context"]=rels[:5]
        related_keys={_doc_key({"title":x.get("title","")}) for x in rels}
        r["source_alternatives"]=[x for x in (r.get("source_alternatives") or []) if _doc_key(x) not in related_keys and x.get("url") not in {y.get("url") for y in rels}]
        r.pop("related_norms",None);r.pop("related_sources",None);out.append(r)
    return out

def _stat_family(s):
    if s.get("source_name")!="Superintendencia de Salud" or "Datos" not in (s.get("signal_types") or []):return None
    t=(s.get("title") or "").lower()
    if "movilidad" in t:return "movilidad"
    if "cartera" in t and ("regional" in t or "nivel regional" in t):return "cartera_regional"
    if "cartera" in t:return "cartera_total"
    if "suscripciones" in t or "desahucios" in t:return "suscripciones"
    if "financier" in t:return "financiero"
    if "ges" in t or "auge" in t:return "ges"
    if "boletín" in t or "boletin" in t:return "boletin"
    return None

def _latest_stats(signals):
    fam=defaultdict(list);other=[]
    for s in signals:
        f=_stat_family(s)
        if f:fam[f].append(s)
        else:other.append(s)
    for items in fam.values():other.append(max(items,key=lambda x:(_d(x.get("event_date")) or date.min,x.get("radar_score",0))))
    return other

def curate(signals):
    normalized=[]
    for s in signals:
        r=_normalize_scopes(_normalize_type(s))
        ok,reason,q=publication_ready(r);r["publication_ready_score"]=q;r["publication_gate_reason"]=reason
        if ok:normalized.append(r)
    if not normalized:return []
    latest=max([_d(x.get("event_date")) for x in normalized if _d(x.get("event_date"))] or [date.today()])
    recent=[s for s in normalized if _d(s.get("event_date")) and (latest-_d(s.get("event_date"))).days<=90]
    recent=_latest_stats(recent);recent=_merge_duplicates(recent);recent=_related_context(recent)
    recent.sort(key=lambda s:(_d(s.get("event_date")) or date.min,s.get("radar_score",0)),reverse=True);return recent

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",default="web/data/radar_today.json");args=ap.parse_args()
    raw=json.loads(Path(args.input).read_text(encoding="utf-8"));signals=raw.get("signals",raw) if isinstance(raw,dict) else raw
    payload={"date":date.today().isoformat(),"generated_at":datetime.now(timezone.utc).isoformat(),"signals":curate(signals)}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    health=Path("data/source_health.json")
    if health.exists():shutil.copyfile(health,out.parent/"source_health.json")
    print(f"snapshot={out} signals={len(payload['signals'])}")
if __name__=="__main__":main()
