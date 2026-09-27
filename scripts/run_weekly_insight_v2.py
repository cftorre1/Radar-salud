from __future__ import annotations
import json
from pathlib import Path
from radar_salud.weekly_insight_v2 import run_weekly_pipeline
ROOT=Path(__file__).resolve().parents[1]
snapshot=json.loads((ROOT/"web/data/radar_today.json").read_text(encoding="utf-8"))
history_path=ROOT/"data/free_value/history.json"
history=json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
if isinstance(history,dict): history=history.get("weeks",history.get("history",[]))
result=run_weekly_pipeline(snapshot,history,run_model=True)
out=ROOT/"data/weekly_insight/latest.json";out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
free_path=ROOT/"web/data/free_value.json";free=json.loads(free_path.read_text(encoding="utf-8")) if free_path.exists() else {}
free["weekly_insight"]=result.get("weekly_insight")
free.setdefault("selection_policy",{})["weekly_insight_status"]="published_deep_intelligence" if result.get("status")=="pass" else result.get("status")
free["selection_policy"]["top3"]=result.get("top3",[])
free["selection_policy"]["deep_intelligence"]=result.get("model") or {"status":result.get("status")}
free_path.write_text(json.dumps(free,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"status":result.get("status"),"top3":[x.get("title") for x in result.get("top3",[])],"model":result.get("model")},ensure_ascii=False))
if result.get("status") not in {"pass","model_revise"}: raise SystemExit(2)
