from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from .paths import project_root
from .pending_queue import atomic_json

_RUN = {
    "deep": {"attempted": 0, "successful": 0, "failed": 0},
    "fast": {"attempted": 0, "successful": 0, "failed": 0},
}

def _root() -> Path:
    return project_root()

def _path() -> Path:
    month=datetime.now(timezone.utc).strftime("%Y-%m")
    return _root()/"data"/"ai_usage"/f"{month}.json"

def _blank():
    return {
        "deep":{"attempted":0,"successful":0,"failed":0},
        "fast":{"attempted":0,"successful":0,"failed":0},
    }

def _load():
    p=_path()
    if not p.exists(): return _blank()
    try: raw=json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc: raise RuntimeError("AI usage ledger unreadable; calls blocked") from exc
    if isinstance(raw.get("deep"),int) or isinstance(raw.get("fast"),int):
        out=_blank()
        for k in ("deep","fast"):
            old=int(raw.get(k,0) or 0)
            out[k]["attempted"]=old
            out[k]["failed"]=old
        return out
    out=_blank()
    for k in ("deep","fast"):
        if isinstance(raw.get(k),dict):
            for metric in out[k]: out[k][metric]=int(raw[k].get(metric,0) or 0)
    return out

def _save(d):
    p=_path();p.parent.mkdir(parents=True,exist_ok=True)
    atomic_json(p,d)

def allow_call(kind: str) -> bool:
    if kind not in ("deep","fast"): return False
    per_run=int(os.getenv("RADAR_DEEP_PER_RUN","5") if kind=="deep" else os.getenv("RADAR_FAST_PER_RUN","40"))
    monthly=int(os.getenv("RADAR_DEEP_PER_MONTH","60") if kind=="deep" else os.getenv("RADAR_FAST_PER_MONTH","400"))
    d=_load();run_attempted=_RUN[kind]["attempted"];month_attempted=int(d[kind]["attempted"])
    if run_attempted>=per_run or month_attempted>=monthly:
        print(f"AI budget: {kind} call deferred (run={run_attempted}/{per_run}, month={month_attempted}/{monthly})")
        return False
    _RUN[kind]["attempted"]+=1;d[kind]["attempted"]+=1;_save(d);return True

def record_result(kind:str, success:bool)->None:
    if kind not in ("deep","fast"): return
    metric="successful" if success else "failed"
    _RUN[kind][metric]+=1;d=_load();d[kind][metric]+=1;_save(d)

def status():
    return {"run":_RUN,"month":_load()}

def has_capacity(kind):
    if kind not in ("fast","deep"): return False
    prefix="RADAR_DEEP" if kind=="deep" else "RADAR_FAST"
    run_limit=int(os.getenv(prefix+"_PER_RUN", "5" if kind=="deep" else "40"))
    month_limit=int(os.getenv(prefix+"_PER_MONTH", "60" if kind=="deep" else "400"))
    return _RUN[kind]["attempted"] < run_limit and _load()[kind]["attempted"] < month_limit
