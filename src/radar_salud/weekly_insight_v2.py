from __future__ import annotations
import json
from datetime import date
from .free_value import rank_weekly_candidates
from .openai_runtime import call_json
from .editorial_committee import build_committee_artifact
REQUIRED=("headline","executive_thesis","what_changed","why_it_matters","business_implications","decision_use","what_to_watch","uncertainties_and_limits","source_refs")

def _related(candidate,signals):
    scopes=set(candidate.get("scopes") or []);out=[]
    for s in signals:
        if s.get("source_url")==candidate.get("source_url") or s.get("feed_visibility") is False:continue
        if not (scopes.intersection(s.get("scopes") or []) or s.get("category")==candidate.get("category")):continue
        out.append({"title":s.get("display_title") or s.get("title"),"source":s.get("source_name"),"url":s.get("source_url"),"event_date":s.get("event_date"),"what":s.get("card_what") or s.get("what_happened"),"why":s.get("card_why") or s.get("why_it_matters")})
    return out[:5]

def build_evidence_package(snapshot,history=None,as_of:date|None=None):
    signals=snapshot.get("signals") or [];ranked=rank_weekly_candidates(signals,history or [],as_of);top=[]
    for row in ranked[:3]:
        s=row["signal"];top.append({"rank":len(top)+1,"score":row["selection_score"],"dimensions":row["strategic_dimensions"],"editorial_gate":row.get("editorial_gate"),"title":s.get("display_title") or s.get("title"),"source":s.get("source_name"),"url":s.get("source_url"),"event_date":s.get("event_date"),"what":s.get("card_what") or s.get("what_happened"),"why":s.get("card_why") or s.get("why_it_matters")})
    if not ranked:return {"top3":[],"candidate":None,"related":[]}
    c=ranked[0]["signal"]
    return {"top3":top,"candidate":c,"related":_related(c,signals),"committee":build_committee_artifact(c)}

def _prompt(p):
    c=p["candidate"]
    e={"candidate":{k:c.get(k) for k in ("title","display_title","source_name","source_url","event_date","card_what","what_happened","card_why","why_it_matters","key_points","data_insights","data_insight_evidence","summary_table","related_context")},"related":p["related"],"ranking":p["top3"]}
    return "Actúa como analista senior de inteligencia de negocio en salud chilena. Usa EXCLUSIVAMENTE la evidencia JSON. No inventes hechos ni causalidad. Devuelve JSON puro con claves: headline, executive_thesis, what_changed, why_it_matters, business_implications, decision_use, what_to_watch, uncertainties_and_limits, source_refs. source_refs solo URLs literales de la evidencia.\\nEVIDENCIA:\\n"+json.dumps(e,ensure_ascii=False)

def run_weekly_pipeline(snapshot,history=None,as_of=None,run_model=True):
    p=build_evidence_package(snapshot,history,as_of)
    if not p["candidate"]:return {"status":"no_candidate","top3":p["top3"],"weekly_insight":None}
    result={"status":"evidence_ready","top3":p["top3"],"evidence_package":{"candidate_url":p["candidate"].get("source_url"),"related":p["related"],"committee":p["committee"]},"weekly_insight":None}
    if not run_model:return result
    m=call_json(_prompt(p),feature="weekly_insight_v2",preferred_model="gpt-5.6-terra",allow_luna_fallback=True);o=m.output
    missing=[k for k in REQUIRED if k not in o];allowed={p["candidate"].get("source_url"),*[x.get("url") for x in p["related"]]};refs=o.get("source_refs") if isinstance(o.get("source_refs"),list) else [];invalid=[x for x in refs if x not in allowed]
    if missing or invalid:
        result.update(status="model_revise",audit={"verdict":"REVISE","missing":missing,"invalid_source_refs":invalid},model={"name":m.model,"fallback_used":m.fallback_used,"cost_usd":m.estimated_cost_usd});return result
    c=p["candidate"]
    result.update(status="pass",audit={"verdict":"PASS"},model={"name":m.model,"fallback_used":m.fallback_used,"cost_usd":m.estimated_cost_usd,"response_id":m.response_id},weekly_insight={"id":"weekly-insight-v2:"+str(c.get("event_date")),"title":o["headline"],"insight_title":o["headline"],"summary":o["executive_thesis"],"insight_teaser":o["why_it_matters"],"insight_reading":o["business_implications"],"decision_use":o["decision_use"],"what_to_watch":o["what_to_watch"],"uncertainties":o["uncertainties_and_limits"],"source_refs":refs,"source_name":c.get("source_name"),"source_url":c.get("source_url"),"event_date":c.get("event_date"),"weekly_mode":"deep_intelligence","engine":m.model,"engine_fallback":m.fallback_used,"model_trace":{"api_call":True,"model":m.model,"response_id":m.response_id,"estimated_cost_usd":m.estimated_cost_usd}})
    return result
