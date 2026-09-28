from __future__ import annotations
import json,os
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
from pathlib import Path
from typing import Any
from openai import OpenAI
ROOT=Path(__file__).resolve().parents[2]
DEFAULT_ROUTING=ROOT/"config/model_routing_v1.json"
DEFAULT_LEDGER=ROOT/"data/state/model_usage.json"

@dataclass
class ModelResult:
    model:str
    output:dict[str,Any]
    input_tokens:int
    output_tokens:int
    estimated_cost_usd:float
    response_id:str|None
    fallback_used:bool=False

def _cfg(path=DEFAULT_ROUTING):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _load(path=DEFAULT_LEDGER):
    p=Path(path)
    if not p.exists():return []
    try:return json.loads(p.read_text(encoding="utf-8")).get("calls",[])
    except Exception:return []

def rolling_7d_spend(path=DEFAULT_LEDGER):
    cutoff=datetime.now(timezone.utc)-timedelta(days=7);total=0.0
    for row in _load(path):
        try:at=datetime.fromisoformat(str(row.get("at")).replace("Z","+00:00"))
        except Exception:continue
        if at>=cutoff:total+=float(row.get("estimated_cost_usd") or 0)
    return round(total,6)

# Standard API input/output rates per 1M tokens. Astra rate verified against
# https://developers.openai.com/api/docs/pricing (USD 10 input / USD 50 output).
_MODEL_PRICES_PER_MILLION={
    "gpt-5.6-luna":(.20,1.20),
    "gpt-5.6-terra":(2.00,12.00),
    "gpt-6-astra":(10.00,50.00),
}

def _prices(model):
    try:return _MODEL_PRICES_PER_MILLION[model]
    except KeyError as exc:raise ValueError("model_pricing_missing:"+str(model)) from exc

def _estimate(model,i,o):
    a,b=_prices(model);return round(i*a/1_000_000+o*b/1_000_000,6)

def _append(row,path=DEFAULT_LEDGER):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);calls=_load(p);calls.append(row)
    p.write_text(json.dumps({"calls":calls[-500:]},ensure_ascii=False,indent=2),encoding="utf-8")

def _parse(text):
    raw=text.strip()
    if raw.startswith("```"):raw=raw.split("\n",1)[1].rsplit("```",1)[0].strip()
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError("model_output_not_object")
    return value

def call_json(prompt,*,feature,preferred_model="gpt-5.6-terra",allow_luna_fallback=True,ledger_path=DEFAULT_LEDGER,routing_path=DEFAULT_ROUTING):
    key=os.getenv("OPENAI_API_KEY")
    if not key:raise RuntimeError("OPENAI_API_KEY_missing")
    cfg=_cfg(routing_path);limit=float(cfg.get("weekly_budget_usd") or cfg.get("cost_policy",{}).get("hard_application_guard_usd_rolling_7d",10))
    if rolling_7d_spend(ledger_path)>=limit:raise RuntimeError("weekly_api_budget_exhausted")
    client=OpenAI(api_key=key);models=[preferred_model]+(["gpt-5.6-luna"] if allow_luna_fallback and preferred_model!="gpt-5.6-luna" else [])
    last=None
    for idx,model in enumerate(models):
        try:
            response=client.responses.create(model=model,input=prompt,max_output_tokens=1800)
            output=_parse(getattr(response,"output_text","") or "")
            usage=getattr(response,"usage",None);i=int(getattr(usage,"input_tokens",0) or 0);o=int(getattr(usage,"output_tokens",0) or 0)
            cost=_estimate(model,i,o)
            if rolling_7d_spend(ledger_path)+cost>limit:raise RuntimeError("call_would_exceed_weekly_budget")
            row={"at":datetime.now(timezone.utc).isoformat(),"feature":feature,"model":model,"input_tokens":i,"output_tokens":o,"estimated_cost_usd":cost,"response_id":getattr(response,"id",None),"fallback_used":idx>0}
            _append(row,ledger_path)
            return ModelResult(model,output,i,o,cost,row["response_id"],idx>0)
        except Exception as exc:last=exc
    raise RuntimeError("model_call_failed:%s:%s"%(type(last).__name__,last))
