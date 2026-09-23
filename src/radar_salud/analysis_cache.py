from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Optional
from .pending_queue import atomic_json

CURRENT_ANALYSIS_VERSION=3

def _cache_path(root: Path) -> Path:
    return root / "data" / "analysis_cache" / "normative.json"

def _key(url: str) -> str:
    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()

def load_cache(root: Path) -> dict[str, dict[str, Any]]:
    p=_cache_path(root)
    if not p.exists(): return {}
    try:
        raw=json.loads(p.read_text(encoding="utf-8"));return raw if isinstance(raw,dict) else {}
    except Exception:return {}

def save_cache(root: Path, cache: dict[str,dict[str,Any]]) -> None:
    atomic_json(_cache_path(root),cache)

def get_cached(root: Path, document_url: str) -> Optional[dict[str,Any]]:
    return load_cache(root).get(_key(document_url))

def needs_upgrade(entry:dict|None)->bool:
    if not entry:return False
    if int(entry.get("analysis_version",0) or 0)>=CURRENT_ANALYSIS_VERSION:return False
    a=entry.get("analysis") or {}
    return bool(a.get("references")) or not a.get("affected_actors")

def put_cached(root: Path, document_url: str, analysis: dict[str,Any], *, model: str) -> None:
    if not document_url or not analysis:return
    cache=load_cache(root)
    cache[_key(document_url)]={"document_url":document_url,"analysis_model":model,"analysis_version":CURRENT_ANALYSIS_VERSION,"analysis":analysis}
    save_cache(root,cache)

def seed_from_history(root: Path) -> int:
    history=root/"data"/"history"/"superintendencia_signals.json"
    if not history.exists(): return 0
    raw=json.loads(history.read_text(encoding="utf-8"));signals=raw.get("signals",raw) if isinstance(raw,dict) else raw
    cache=load_cache(root);added=0
    for s in signals:
        if "Normativa" not in (s.get("signal_types") or []):continue
        if not (s.get("key_points") or s.get("validity_text") or s.get("related_reference_ids")):continue
        docs=s.get("source_documents") or []
        doc_url=next((x.get("url") for x in docs if x.get("url") and ".pdf" in x.get("url","").lower()),None)
        if not doc_url:continue
        k=_key(doc_url)
        if k in cache:continue
        cache[k]={"document_url":doc_url,"analysis_model":"gpt-5.6-terra","analysis_version":2,"analysis":{
            "what_happened":s.get("what_happened",""),"why_it_matters":s.get("why_it_matters",""),
            "validity_text":s.get("validity_text"),"key_points":s.get("key_points") or [],"review_points":s.get("risk_notes") or [],
            "references":s.get("related_reference_ids") or [],"affected_actors":[],"affected_processes":[]}}
        added+=1
    save_cache(root,cache);return added
