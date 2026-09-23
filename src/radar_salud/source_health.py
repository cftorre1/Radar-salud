from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def _path(root:Path)->Path:return root/"data"/"source_health.json"
def _load(root:Path)->dict[str,Any]:
    p=_path(root)
    if not p.exists():return {"sources":{}}
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return {"sources":{}}

def record(root:Path,slug:str,*,name:str,discovered:int,new:int,published:int,rows:list[dict]|None=None,error:str|None=None)->None:
    d=_load(root);src=d.setdefault("sources",{});rows=rows or []
    dates=[x.get("event_date") for x in rows if x.get("event_date")]
    prev=src.get(slug,{})
    src[slug]={
        "name":name,"checked_at":datetime.now(timezone.utc).isoformat(),
        "last_signal_at":max(dates) if dates else prev.get("last_signal_at"),
        "discovered":discovered,"new":new,"published":published,
        "status":"error" if error else ("warning" if new>0 and published==0 else "ok"),
        "error":error,
    }
    d["generated_at"]=datetime.now(timezone.utc).isoformat()
    p=_path(root);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
