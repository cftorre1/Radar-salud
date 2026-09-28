from __future__ import annotations
import json, os, random, time
from datetime import datetime, timezone
from pathlib import Path
from openai import OpenAI
from radar_salud.openai_runtime import _append, _cfg, _estimate, rolling_7d_spend

ROOT=Path(__file__).resolve().parents[1]
MODELS=("gpt-5.6-luna","gpt-5.6-terra","gpt-6-astra")
MAX_OUTPUT_TOKENS=1200
MAX_PROMPT_CHARS=20000
OUTPUT_KEYS=("headline","executive_thesis","key_claims","why_it_matters","business_implications","chile_watch","decision_use","uncertainties_and_limits","source_refs")

def build_experiment(snapshot, weekly, themes_doc):
    signals=snapshot.get("signals") or []
    local=next((s for s in signals if "cenabast" in ((s.get("title") or "")+" "+(s.get("what_happened") or "")).lower()),None)
    if not local: raise ValueError("corpus_source_missing:local_cenabast")
    theme_map={x.get("id"):x for x in themes_doc.get("themes",[])}
    workforce=theme_map.get("global-workforce-pressure-2026")
    ai=theme_map.get("global-health-ai-operating-model-2026")
    if not workforce or not ai: raise ValueError("corpus_theme_missing")
    tops=(weekly.get("top3") or [])[:3]
    if len(tops)<3: raise ValueError("corpus_source_missing:three_local_normative_items")
    def rec(sid,publisher,title,date,url,kind,evidence,analysis=None):
        return {"id":sid,"publisher":publisher,"title":title,"published_at":date,"url":url,"material_type":kind,"evidence":evidence,"analysis":analysis or {}}
    news=rec("L1",local.get("source_name","Ministerio de Salud"),local.get("display_title") or local.get("title"),local.get("event_date"),local.get("source_url"),"official_news",{"what_happened":local.get("card_what") or local.get("what_happened"),"why_it_matters":local.get("card_why") or local.get("why_it_matters"),"key_facts":local.get("key_facts") or [],"key_numbers":local.get("key_numbers") or []})
    norms=[rec("L"+str(i+2),x.get("source","Superintendencia de Salud"),x.get("title"),x.get("event_date"),x.get("url"),"normative_signal",{"what_happened":x.get("what"),"why_it_matters":x.get("why"),"selection_score":x.get("score")}) for i,x in enumerate(tops)]
    def theme_source(theme,publisher,sid):
        s=next((x for x in theme.get("sources",[]) if x.get("publisher")==publisher),None)
        if not s: raise ValueError("corpus_source_missing:"+sid)
        return rec(sid,s.get("publisher"),s.get("title"),s.get("published_at"),s.get("url"),s.get("material_type"),s.get("evidence"),s.get("analysis"))
    who=theme_source(workforce,"WHO","WHO report")
    reuters=theme_source(workforce,"Reuters","Reuters workforce")
    deloitte=theme_source(ai,"Deloitte","Deloitte AI")
    pwc=theme_source(ai,"PwC","PwC governance")
    catalog=[news,*norms,who,reuters,deloitte,pwc]
    if len(catalog)!=8: raise ValueError("corpus_must_contain_exactly_8_pieces")
    cases=[
      {"id":"simple_news","instruction":"Redacta una tarjeta FREE clara y breve sobre una noticia local: hecho, relevancia práctica y un límite de evidencia. Máximo 80 palabras.","evidence_ids":["L1"]},
      {"id":"complex_report","instruction":"Analiza el informe extenso de la OMS sobre personal sanitario usando su ficha de evidencia; Reuters es contexto separado, no sustituye al informe. Distingue resultados globales de hipótesis para Chile. Máximo 180 palabras.","evidence_ids":["G1","G2"]},
      {"id":"multisource_chile","instruction":"Sintetiza la evidencia Deloitte + PwC sobre IA en salud. No sumes porcentajes ni atribuyas datos globales a Chile. Propón qué observar localmente y marca hipótesis. Máximo 160 palabras.","evidence_ids":["G3","G4"],"theme_context":ai.get("cross_analysis",{})},
      {"id":"free_feature","instruction":"Crea un Insight Alicanto FREE semanal de alto valor usando estas tres señales normativas independientes. No las presentes como una reforma coordinada; prioriza una consecuencia ejecutiva demostrable y no ocultes contexto para vender. Máximo 130 palabras.","evidence_ids":["L2","L3","L4"]},
      {"id":"global_teaser","instruction":"Escribe un teaser FREE autosuficiente de Global Intelligence, basado en Deloitte + PwC, útil por sí mismo y de máximo 55 palabras; agrega CTA Premium sin urgencia falsa ni withholding artificial.","evidence_ids":["G3","G4"],"theme_context":ai.get("cross_analysis",{})}
    ]
    lookup={x["id"]:x for x in catalog}
    for c in cases:c["evidence"]=[lookup[sid] for sid in c["evidence_ids"]]
    return {"version":"1.0","pieces":catalog,"cases":cases}

def make_prompt(case):
    contract={"headline":"string","executive_thesis":"string","key_claims":[{"claim":"string","source_ids":["L1"]}],"why_it_matters":"string","business_implications":["string"],"chile_watch":{"classification":"evidence|hypothesis|none","text":"string","source_ids":["L1"]},"decision_use":"string","uncertainties_and_limits":["string"],"source_refs":["L1"]}
    payload={"task":case["id"],"instruction":case["instruction"],"evidence":case["evidence"],"theme_context":case.get("theme_context",{}),"output_contract":contract}
    return "Actúa como analista de inteligencia de negocio en salud. Responde en español y devuelve SOLO JSON. Usa exclusivamente la evidencia, sin búsqueda externa ni causalidad inventada. source_refs y key_claims.source_ids solo pueden usar los ID entregados. Respeta el límite de palabras.\n"+json.dumps(payload,ensure_ascii=False,separators=(",",":"))

def validate_output(output, allowed_ids):
    if not isinstance(output,dict): return {"valid":False,"missing_keys":list(OUTPUT_KEYS),"invalid_source_ids":[]}
    missing=[k for k in OUTPUT_KEYS if k not in output]
    refs=output.get("source_refs") if isinstance(output.get("source_refs"),list) else []
    claims=output.get("key_claims") if isinstance(output.get("key_claims"),list) else []
    used=list(refs)
    for claim in claims:
        if isinstance(claim,dict): used.extend(claim.get("source_ids") or [])
    watch=output.get("chile_watch")
    if isinstance(watch,dict): used.extend(watch.get("source_ids") or [])
    invalid=sorted({str(x) for x in used if x not in allowed_ids})
    return {"valid":not missing and not invalid,"missing_keys":missing,"invalid_source_ids":invalid}

def reserve_usd(prompts, models=MODELS):
    if any(len(p)>MAX_PROMPT_CHARS for p in prompts): raise ValueError("prompt_too_large_for_budget_guard")
    return round(sum(_estimate(m,len(p),MAX_OUTPUT_TOKENS) for m in models for p in prompts),6)

def execute(snapshot,weekly,themes_doc,output_dir):
    if not os.getenv("OPENAI_API_KEY"): raise RuntimeError("OPENAI_API_KEY_missing")
    experiment=build_experiment(snapshot,weekly,themes_doc);prompts=[make_prompt(c) for c in experiment["cases"]]
    cfg=_cfg();limit=float(cfg.get("weekly_budget_usd") or 10.0);spent=rolling_7d_spend();reserve=reserve_usd(prompts)
    if spent+reserve>limit: raise RuntimeError("experiment_reserve_exceeds_weekly_budget")
    client=OpenAI(api_key=os.environ["OPENAI_API_KEY"]);rng=random.Random(int(os.getenv("GITHUB_RUN_ID","20260927")))
    shuffled=list(MODELS);rng.shuffle(shuffled);aliases={m:"Modelo "+chr(65+i) for i,m in enumerate(shuffled)}
    blind=[];manifest=[]
    for model in shuffled:
        for case,prompt in zip(experiment["cases"],prompts):
            started=time.monotonic()
            try:
                response=client.responses.create(model=model,input=prompt,max_output_tokens=MAX_OUTPUT_TOKENS)
                elapsed=round((time.monotonic()-started)*1000);raw=getattr(response,"output_text","") or "";clean=raw.strip()
                if clean.startswith(chr(96)*3): clean=clean.split("\n",1)[-1].rsplit(chr(96)*3,1)[0].strip()
                try: parsed=json.loads(clean)
                except Exception: parsed=None
                usage=getattr(response,"usage",None);ins=int(getattr(usage,"input_tokens",0) or 0);outs=int(getattr(usage,"output_tokens",0) or 0);cost=_estimate(model,ins,outs);rid=getattr(response,"id",None)
                _append({"at":datetime.now(timezone.utc).isoformat(),"feature":"model_quality_experiment_v1","model":model,"input_tokens":ins,"output_tokens":outs,"estimated_cost_usd":cost,"response_id":rid,"fallback_used":False,"experiment_case":case["id"],"latency_ms":elapsed})
                validation=validate_output(parsed,set(case["evidence_ids"]))
                blind.append({"blind_id":aliases[model],"case_id":case["id"],"status":"output" if parsed is not None else "invalid_json","output":parsed if parsed is not None else raw,"contract_validation":validation})
                manifest.append({"blind_id":aliases[model],"case_id":case["id"],"model":model,"input_tokens":ins,"output_tokens":outs,"estimated_cost_usd":cost,"latency_ms":elapsed,"response_id":rid,"fallback_used":False})
                if rolling_7d_spend()>limit: raise RuntimeError("weekly_api_budget_exceeded_after_call")
            except Exception as exc:
                if isinstance(exc,RuntimeError) and str(exc).startswith("weekly_api_budget_exceeded"): raise
                blind.append({"blind_id":aliases[model],"case_id":case["id"],"status":"call_error","output":None,"contract_validation":{"valid":False,"error_type":type(exc).__name__}})
                manifest.append({"blind_id":aliases[model],"case_id":case["id"],"model":model,"status":"call_error","error_type":type(exc).__name__})
                break
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"corpus.json").write_text(json.dumps(experiment,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"blinded_outputs.json").write_text(json.dumps({"version":"1.0","outputs":blind},ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"cost_manifest.json").write_text(json.dumps({"reserved_usd":reserve,"rolling_7d_before_usd":spent,"rolling_7d_after_usd":rolling_7d_spend(),"weekly_limit_usd":limit,"calls":manifest},ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"scorecard_template.json").write_text(json.dumps({"rubric":{"fidelity":25,"selection_prioritization":20,"synthesis_connection":20,"value_for_chile":20,"executive_utility":15},"scores":[{"blind_id":a,"case_id":c["id"],"dimension_scores":{},"factual_errors":[],"unsupported_claims":[],"material_omissions":[],"human_edit_minutes":None,"publishable_without_editing":None} for a in sorted(set(aliases.values())) for c in experiment["cases"]]},ensure_ascii=False,indent=2),encoding="utf-8")
    return {"cases":len(experiment["cases"]),"pieces":len(experiment["pieces"]),"successes":sum(x["status"]=="output" for x in blind),"outputs":len(blind),"reserved_usd":reserve}

def main():
    snapshot=json.loads((ROOT/"web/data/radar_today.json").read_text(encoding="utf-8"))
    weekly=json.loads((ROOT/"data/weekly_insight/latest.json").read_text(encoding="utf-8"))
    themes=json.loads((ROOT/"data/global/themes.json").read_text(encoding="utf-8"))
    summary=execute(snapshot,weekly,themes,ROOT/"artifacts/model_quality");print(json.dumps(summary))
    if summary["successes"]<15: raise SystemExit(2)

if __name__=="__main__":main()
