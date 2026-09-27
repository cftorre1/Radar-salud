"""Fail loudly when approved/in-progress work is executable but staging has gone stale."""
from __future__ import annotations
import argparse, json, subprocess
from datetime import datetime, timezone
from pathlib import Path

ACTIVE={"approved","in_progress"}
DONE={"validated","completed"}

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def executable_tasks(queue):
    tasks=queue.get("tasks") or []
    status={t.get("id"):t.get("status") for t in tasks}
    out=[]
    for t in tasks:
        if t.get("status") not in ACTIVE:
            continue
        if t.get("blocked_by"):
            continue
        deps=t.get("depends_on") or []
        if all(status.get(dep) in DONE for dep in deps):
            out.append(t.get("id"))
    return out

def head_age_minutes(now=None):
    now=now or datetime.now(timezone.utc)
    raw=subprocess.check_output(["git","log","-1","--format=%cI"],text=True).strip()
    at=datetime.fromisoformat(raw.replace("Z","+00:00"))
    return max(0.0,(now-at).total_seconds()/60)

def evaluate(queue,age_minutes,threshold_minutes=75):
    active=executable_tasks(queue)
    return {
        "executable_tasks":active,
        "head_age_minutes":round(age_minutes,1),
        "threshold_minutes":threshold_minutes,
        "stalled":bool(active and age_minutes>threshold_minutes),
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--queue",default="config/orchestrator_queue.json")
    p.add_argument("--threshold-minutes",type=int,default=75)
    p.add_argument("--output",default="artifacts/orchestrator_liveness.json")
    args=p.parse_args()
    result=evaluate(load(args.queue),head_age_minutes(),args.threshold_minutes)
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
    if result["stalled"]:
        raise SystemExit("Executable Alicanto work is stalled without a new staging commit")

if __name__=="__main__":
    main()
