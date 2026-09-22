from __future__ import annotations
import argparse,json,re
from collections import defaultdict
from datetime import datetime,timezone,date
from pathlib import Path
from radar_salud.reference_resolver import resolve_reference

def _d(v):
    if not v:return None
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).date()
    except:
        try:return date.fromisoformat(str(v)[:10])
        except:return None

def _garbage(s):
    t=" ".join(str(s.get(k,"") or "") for k in ("title","what_happened","why_it_matters")).lower()
    return any(x in t for x in ("@context","@graph","schema.org",'"@type"','"ispartof"'))

def _legacy_minsal_noise(s):
    if s.get("source_name")!="Ministerio de Salud":return False
    t=f"{s.get('title','')} {s.get('what_happened','')}".lower()
    personnel=("renuncia","designa nueva","designa nuevo","nombramiento","asume como","nuevo subsecretario","nueva subsecretaria","seremi")
    if any(x in t for x in personnel):return True
    if any(x in t for x in ("trayectoria ministra","historia del ministerio","visita la región","visita la region")):return True
    er=s.get("editorial_relevance")
    return er is not None and er<65

def _normalize_scopes(s):
    r=dict(s);out=[]
    for scope in r.get("scopes",[]) or []:
        x=str(scope).strip()
        low=x.lower()
        if "isapre" in low and "fonasa" in low:
            out += ["Isapres","Fonasa"]
        elif low in ("isapre","isapres"):out.append("Isapres")
        elif low=="fonasa":out.append("Fonasa")
        else:out.append(x)
    r["scopes"]=list(dict.fromkeys(out)) or ["Sistema de salud"]
    return r

def _doc_key(s):
    t=f"{s.get('title','')} {s.get('what_happened','')}"
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
    for _,items in groups.items():
        if len(items)==1:merged.append(items[0]);continue
        base=max(items,key=lambda x:(len(x.get("key_points",[]) or []),len(x.get("what_happened","")),x.get("source_name")=="Superintendencia de Salud"))
        r=dict(base);rel=list(r.get("related_sources",[]) or []);seen={x.get("url") for x in rel}
        for x in items:
            if x is base:continue
            u=x.get("source_url")
            if u and u not in seen:
                rel.append({"title":x.get("title"),"summary":x.get("what_happened"),"url":u,"event_date":x.get("event_date"),"source_name":x.get("source_name")});seen.add(u)
        r["related_sources"]=rel
        r["corroborating_sources"]=list(dict.fromkeys([x.get("source_name") for x in items if x.get("source_name")]))
        merged.append(r)
    return other+merged

def _ref_key(text):
    m=re.search(r"circular\s+(?:if\s*[/\-]?\s*)?n?[°º]?\s*(\d+)",text or "",re.I)
    return "circular-if-"+m.group(1) if m else None

def _related(signals):
    idx={_doc_key(s):s for s in signals if _doc_key(s)};out=[]
    for s in signals:
        r=dict(s);rels=[];seen=set()
        for ref in r.get("related_reference_ids",[]) or []:
            k=_ref_key(ref);target=idx.get(k) if k else None
            if target and target.get("source_url")!=r.get("source_url"):
                item={"title":target.get("title"),"summary":target.get("what_happened"),"url":target.get("source_url"),"event_date":target.get("event_date")}
            else:
                item=resolve_reference(ref)
            if not item or not item.get("url") or item["url"] in seen:continue
            seen.add(item["url"]);rels.append(item)
        r["related_norms"]=rels[:4];out.append(r)
    return out

def _stat_family(s):
    if s.get("source_name")!="Superintendencia de Salud":return None
    t=(s.get("title") or "").lower()
    if "movilidad" in t:return "movilidad"
    if "cartera" in t and ("regional" in t or "nivel regional" in t):return "cartera_regional"
    if "cartera" in t:return "cartera_total"
    if "suscripciones" in t or "desahucios" in t:return "suscripciones"
    if "boletín" in t or "boletin" in t:return "boletin"
    return None

def _latest_stat_snapshots(signals):
    fam=defaultdict(list);other=[]
    for s in signals:
        f=_stat_family(s)
        if f:fam[f].append(s)
        else:other.append(s)
    latest=[]
    for _,items in fam.items():
        latest.append(max(items,key=lambda x:(_d(x.get("event_date")) or date.min,x.get("radar_score",0))))
    return other+latest

def _period(s):
    t=s.get("title","")
    m=re.search(r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)(?:\s+de)?\s+20\d{2}",t,re.I)
    if m:return re.sub(r"\s+de\s+(20\d{2})$",r" \1",m.group(0).lower())
    for f in s.get("key_facts",[]) or []:
        m=re.search(r"actualizada? a\s+(.+?)[\.]?$",f,re.I)
        if m:return re.sub(r"\s+de\s+(20\d{2})$",r" \1",m.group(1).strip(" .").lower())
    return "actual"

def _monthly(s):return _stat_family(s) in ("movilidad","cartera_regional","cartera_total","suscripciones")

def _group_monthly(items):
    groups=defaultdict(list)
    for s in items:groups[_period(s)].append(s)
    out=[]
    for p,best in groups.items():
        if len(best)<2:out.extend(best);continue
        base=dict(max(best,key=lambda x:x.get("radar_score",0)));labels=[]
        for s in best:
            f=_stat_family(s)
            labels.append({"movilidad":"movilidad de cartera","cartera_regional":"cartera regional","cartera_total":"cartera total","suscripciones":"suscripciones y desahucios"}.get(f,f))
        base.update({
          "title":f"Actualización mensual del sistema Isapre — {p}",
          "what_happened":f"La Superintendencia actualizó {len(best)} conjuntos de datos: "+"; ".join(dict.fromkeys(labels))+".",
          "why_it_matters":"Reúne en una sola lectura las principales señales mensuales de cartera: tamaño y composición, movilidad, altas y bajas del sistema.",
          "related_sources":[{"title":x.get("title"),"summary":x.get("what_happened"),"url":x.get("source_url"),"event_date":x.get("event_date")} for x in best],
          "grouped_count":len(best),"signal_types":["Datos"],"scopes":["Isapres"],"data_insights":[],
          "event_date":max([x.get("event_date") for x in best if x.get("event_date")] or [base.get("event_date")])})
        out.append(base)
    return out

def curate(signals):
    clean=[]
    for s in signals:
        if _garbage(s) or _legacy_minsal_noise(s) or s.get("validation_status")=="human_review_required":continue
        r=_normalize_scopes(s);r["data_insights"]=[]  # generic Excel insights remain disabled until source-specific parsers
        if r.get("source_name") in ("Ministerio de Salud","Diario Financiero","SUSESO","Diario Oficial") and not _d(r.get("event_date")):continue
        clean.append(r)
    if not clean:return []
    latest=max([_d(x.get("event_date")) for x in clean if _d(x.get("event_date"))] or [date.today()])
    recent=[s for s in clean if _d(s.get("event_date")) and (latest-_d(s.get("event_date"))).days<=90]
    recent=_latest_stat_snapshots(recent)
    monthly=[s for s in recent if _monthly(s)];rest=[s for s in recent if s not in monthly]
    out=_related(_merge_duplicates(_group_monthly(monthly)+rest))
    out.sort(key=lambda s:(_d(s.get("event_date")) or date.min,s.get("radar_score",0)),reverse=True)
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",default="web/data/radar_today.json");args=ap.parse_args()
    raw=json.loads(Path(args.input).read_text(encoding="utf-8"));signals=raw.get("signals",raw) if isinstance(raw,dict) else raw
    payload={"date":date.today().isoformat(),"generated_at":datetime.now(timezone.utc).isoformat(),"signals":curate(signals)}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8");print(out)
if __name__=="__main__":main()
