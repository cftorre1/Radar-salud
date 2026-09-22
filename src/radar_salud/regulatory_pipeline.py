from __future__ import annotations
import re
from .models import RawItem
from .pipeline import build_signal

def process_superintendencia_normativa(raw: RawItem, source_cfg):
    text=f"{raw.title} {raw.raw_text}"
    kind="Oficio Circular" if "oficio" in text.lower() else "Circular"
    scope=raw.metadata.get("scope","Isapres")
    summary=raw.raw_text if raw.raw_text and raw.raw_text!=raw.title else f"La Superintendencia publicó {raw.title}."
    why="Puede modificar obligaciones operativas, contractuales o de información de las Isapres; conviene revisar su alcance, fecha de entrada en vigencia y eventuales ajustes de procesos."
    raw.metadata.update({
      "what_happened": summary,
      "why_it_matters": why,
      "key_facts":[summary],
      "watch_tags":["normativa","isapres","superintendencia"],
      "signal_types":["Normativa"],
      "scopes":[scope],
      "event_type":"REGULATION",
      "institution_types":["ISAPRE"],
      "scores":{"economic":55,"regulatory":95,"scope":80,"novelty":85,"actionability":90},
      "subcategory":kind,
    })
    s=build_signal(raw,source_cfg)
    row=s.to_dict()
    row["signal_types"]=["Normativa"]
    row["scopes"]=[scope]
    row["category"]="Regulación & Legal"
    row["radar_score"]=max(row["radar_score"],82)
    return row
