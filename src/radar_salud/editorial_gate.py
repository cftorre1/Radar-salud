from __future__ import annotations
from typing import Any, Dict, Tuple

_BINARY=("%pdf-"," endobj"," endstream","/resources ","/contents "," obj <"," stream ")
_HTML=("<a ","<script","<style",'target="_blank"',"schema.org")
_GENERIC=(
    "formaliza un cambio normativo o legal del sector salud",
    "aporta información oficial reciente",
    "describe un cambio material para una parte relevante del sistema de salud",
)
_MINSAL_NOISE=(
    "renuncia","nombramiento","designa nueva","designa nuevo","asume como",
    "nuevo subsecretario","nueva subsecretaria","seremi","visita nuevo","visita el",
    "visita la","continúa recorrido","continua recorrido","conmemora","participa en",
    "trayectoria","historia del ministerio",
)

def _text(r:Dict[str,Any])->str:
    return " ".join(str(r.get(k,"") or "") for k in ("title","what_happened","why_it_matters"))

def has_garbage(r:Dict[str,Any])->bool:
    t=_text(r).lower()
    return any(x in t for x in _BINARY+_HTML) or t.count("�")>=3

def is_minsal_noise(r:Dict[str,Any])->bool:
    if r.get("source_name")!="Ministerio de Salud": return False
    t=_text(r).lower()
    if any(x in t for x in _MINSAL_NOISE): return True
    if any(x in t for x in ("alerta alimentaria","retiro de producto","lote de","marca ")) and int(r.get("editorial_relevance") or 0)<80:
        return True
    return False

def quality_score(r:Dict[str,Any])->int:
    q=100
    if not r.get("event_date"): q-=18
    if not r.get("source_url"): q-=15
    if len(str(r.get("title") or "").strip())<12: q-=20
    if len(str(r.get("what_happened") or "").strip())<35: q-=20
    if len(str(r.get("why_it_matters") or "").strip())<35: q-=15
    why=" ".join(str(r.get("why_it_matters") or "").lower().split())
    if any(x in why for x in _GENERIC): q-=18
    if has_garbage(r): q-=80
    if is_minsal_noise(r): q-=80
    return max(0,q)

def publication_ready(r:Dict[str,Any])->Tuple[bool,str,int]:
    q=quality_score(r)
    if has_garbage(r): return False,"binary_or_markup",q
    if is_minsal_noise(r): return False,"editorial_noise",q
    if not r.get("source_url"): return False,"missing_source",q
    if not r.get("event_date") and r.get("source_name") in ("Ministerio de Salud","Diario Financiero","SUSESO","Diario Oficial"):
        return False,"missing_date",q
    if q<62: return False,"quality_below_threshold",q
    return True,"ok",q
