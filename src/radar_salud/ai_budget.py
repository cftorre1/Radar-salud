from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path

_RUN = {"deep": 0, "fast": 0}

def _root() -> Path:
    return Path(__file__).resolve().parents[2]

def _path() -> Path:
    month=datetime.now(timezone.utc).strftime("%Y-%m")
    return _root()/"data"/"ai_usage"/f"{month}.json"

def _load():
    p=_path()
    if not p.exists(): return {"deep":0,"fast":0}
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {"deep":0,"fast":0}

def _save(d):
    p=_path();p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")

def allow_call(kind: str) -> bool:
    """Soft engineering guard to keep Alicanto around the US$10/month API target.
    Limits are deliberately conservative and can be overridden with env vars.
    """
    if kind not in ("deep","fast"): return False
    per_run=int(os.getenv("RADAR_DEEP_PER_RUN","5") if kind=="deep" else os.getenv("RADAR_FAST_PER_RUN","40"))
    monthly=int(os.getenv("RADAR_DEEP_PER_MONTH","60") if kind=="deep" else os.getenv("RADAR_FAST_PER_MONTH","400"))
    d=_load()
    if _RUN[kind] >= per_run or int(d.get(kind,0)) >= monthly:
        print(f"AI budget: {kind} call deferred (run={_RUN[kind]}/{per_run}, month={d.get(kind,0)}/{monthly})")
        return False
    _RUN[kind]+=1;d[kind]=int(d.get(kind,0))+1;_save(d)
    return True

def status():
    d=_load()
    return {"run":dict(_RUN),"month":d}
