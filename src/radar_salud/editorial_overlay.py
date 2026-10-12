"""Guarded candidate overlay; preserves the paid record and requires final receipt."""
import hashlib
import json
from copy import deepcopy
from .editorial_v3 import validate_depth,PUBLIC_FIELDS

def source_version(record):
    return hashlib.sha256(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def apply_overlay(base,overlay):
    if overlay.get('base_version')!=source_version(base):
        return {'ok':False,'reason':'HOLD_BASE_VERSION','record':deepcopy(base)}
    candidate=overlay.get('candidate') or {}
    allowed=set(PUBLIC_FIELDS)|{'editorial_schema_version','review','selection_rationale','read_aliases'}
    protected=[key for key,value in candidate.items() if base.get(key)!=value and key not in allowed]
    if protected:return {'ok':False,'reason':'HOLD_PROTECTED_LINEAGE','protected_fields':protected,'record':deepcopy(base)}
    result={**deepcopy(base),**deepcopy(candidate)}
    gate=validate_depth(result)
    if not gate['ok']:return {'ok':False,'reason':'HOLD_EDITORIAL_REVIEW','gate':gate,'record':deepcopy(base)}
    result['editorial_lineage']={'base_version':overlay['base_version'],'content_version':gate['content_version'],
                               'reason':overlay.get('reason'),'original_record':deepcopy(base)}
    result['depth_gate']=gate
    return {'ok':True,'record':result}
