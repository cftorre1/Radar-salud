from __future__ import annotations
from .models import RawItem
from .pipeline import build_signal
from .document_intelligence import analyze_attachments

def process_superintendencia_normativa(raw: RawItem, source_cfg):
    scope=raw.metadata.get("scope","Sistema de salud")
    intel=analyze_attachments(raw.metadata.get("attachments",[]))
    summary=raw.raw_text if raw.raw_text and raw.raw_text!=raw.title else f"La Superintendencia publicó {raw.title}."
    why="La instrucción o acto administrativo puede modificar obligaciones, procesos, coberturas o requerimientos de información para los actores alcanzados."
    raw.metadata.update({
      "what_happened":summary,"why_it_matters":why,"key_facts":[summary],
      "watch_tags":["normativa",scope.lower(),"superintendencia"],
      "signal_types":["Normativa"],"scopes":[scope],"event_type":"REGULATION",
      "scores":{"economic":55,"regulatory":95,"scope":82,"novelty":85,"actionability":90},
      "subcategory":"Acto regulatorio",
      "key_points":intel.get("key_points",[]),"risk_notes":intel.get("risk_notes",[]),
      "validity_text":intel.get("validity_text"),
      "source_documents":raw.metadata.get("attachments",[]),
    })
    s=build_signal(raw,source_cfg);row=s.to_dict()
    row["signal_types"]=["Normativa"];row["scopes"]=[scope];row["category"]="Regulación & Legal";row["radar_score"]=max(row["radar_score"],82)
    return row
