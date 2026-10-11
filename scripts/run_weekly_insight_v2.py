from __future__ import annotations
import argparse,json
from pathlib import Path
from radar_salud.weekly_insight_v2 import run_weekly_pipeline
from radar_salud.weekly_freshness import reconcile_weekly_publication
ROOT=Path(__file__).resolve().parents[1]
snapshot=json.loads((ROOT/"web/data/radar_today.json").read_text(encoding="utf-8"))
history_path=ROOT/"data/free_value/history.json"
history=json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
if isinstance(history,dict): history=history.get("weeks",history.get("history",[]))
parser=argparse.ArgumentParser()
parser.add_argument('--review-only',action='store_true',help='Reconcile approved publication and candidate evidence without a model call')
args=parser.parse_args()
try:
    generated=run_weekly_pipeline(snapshot,history,run_model=not args.review_only)
except Exception as exc:
    generated={"status":"generation_error","error_type":type(exc).__name__}
approved_path=ROOT/"data/weekly_insight/editorial_approved.json"
try:
    approved=json.loads(approved_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    approved={}
result=reconcile_weekly_publication(generated,approved)
out=ROOT/"data/weekly_insight/latest.json";out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
free_path=ROOT/"web/data/free_value.json";free=json.loads(free_path.read_text(encoding="utf-8")) if free_path.exists() else {}
free["weekly_insight"]=result.get("weekly_insight")
free.setdefault("selection_policy",{})["weekly_insight_status"]="published_deep_intelligence" if result.get("status")=="pass" else result.get("status")
free["selection_policy"]["top3"]=result.get("top3",[])
free["selection_policy"]["deep_intelligence"]=result.get("model") or {"status":result.get("status")}
free_path.write_text(json.dumps(free,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"status":result.get("status"),"top3":[x.get("title") for x in result.get("top3",[])],"model":result.get("model")},ensure_ascii=False))
if result.get("generation_status")=="generation_error": raise SystemExit(2)

