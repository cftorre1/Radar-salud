"""Version-bound incremental depth. Similarity diagnoses; an independent receipt attests semantics."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime,timezone,date
from urllib.parse import urlparse
from typing import Any, Mapping

PUBLIC_FIELDS=('piece_id','title','display_title','brief_deck','detail_body','claims','evidence','dates',
               'depth_modules','paragraph_claim_ids','statistical_view','source_documents','source_url',
               'source_name','signal_types','scopes','event_type','event_date','event_date_basis','issued_on','emission_date',
               'publication_date','published_on','data_period','validation_date','inspection_date',
               'inspection_period','effective_from','effective_until','fact_period','related_context','source_alternatives','editorial_enrichment',
               'historical_connections','historical_sanction_context','historical_context_status','sanction_count',
               'primary_document_review','normative_document_label','validity_text','legal_identity','hold_reason','publication_status')

def content_version(record: Mapping[str,Any]) -> str:
    payload={key:record.get(key) for key in PUBLIC_FIELDS}
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def normalized(text):
    # Negations, numbers, signs and legal operators are retained.
    return ' '.join(str(text or '').casefold().split())

def depth_diagnostics(record):
    texts=[('title',record.get('display_title') or record.get('title')),('brief_deck',record.get('brief_deck')),
           *[(f'paragraph:{i}',p) for i,p in enumerate(str(record.get('detail_body') or '').split('\n\n'))]]
    alerts=[]
    for i,(left,a) in enumerate(texts):
        if not a:continue
        for right,b in texts[i+1:]:
            if not b:continue
            if normalized(a)==normalized(b):alerts.append({'code':'exact_duplicate','left':left,'right':right})
            else:
                aa=set(re.findall(r'\w+|[%+−-]',normalized(a)));bb=set(re.findall(r'\w+|[%+−-]',normalized(b)))
                if aa and bb and len(aa&bb)/len(aa|bb)>=.75:alerts.append({'code':'overlap_review','left':left,'right':right})
    return alerts

def _validate_depth(record):
    reasons=[]
    for key in ('piece_id','detail_body','claims','evidence','paragraph_claim_ids'):
        if not record.get(key):reasons.append('missing_'+key)
    claims=record.get('claims') or [];evidence=record.get('evidence') or []
    if not isinstance(claims,list) or not isinstance(evidence,list):return {'ok':False,'reason_codes':['invalid_claim_inventory'],'diagnostics':[]}
    ids=[x.get('id') for x in claims if isinstance(x,dict)];eids=[x.get('id') for x in evidence if isinstance(x,dict)]
    if len(ids)!=len(claims) or None in ids or len(set(ids))!=len(ids):reasons.append('invalid_claim_ids')
    if len(eids)!=len(evidence) or None in eids or len(set(eids))!=len(eids):reasons.append('invalid_evidence_ids')
    for e in evidence:
        if not isinstance(e,dict):reasons.append('invalid_evidence');continue
        url=urlparse(str(e.get('url') or ''))
        if url.scheme!='https' or not url.netloc or not str(e.get('locator') or '').strip():reasons.append('unresolved_evidence_locator')
        try:
            raw=str(e.get('observed_at'))
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):
                if date.fromisoformat(raw)>date.today():reasons.append('invalid_evidence_date')
            else:
                observed=datetime.fromisoformat(raw.replace('Z','+00:00'))
                if observed.tzinfo is None or observed>datetime.now(timezone.utc):reasons.append('invalid_evidence_date')
        except (ValueError,TypeError):reasons.append('invalid_evidence_date')
    for c in claims:
        if not isinstance(c,dict):continue
        if not str(c.get('text') or '').strip():reasons.append('empty_claim')
        refs=c.get('evidence_refs') or []
        if not refs or not set(refs)<=set(eids):reasons.append('unsupported_claim')
        if c.get('kind') not in {'fact','analysis','hypothesis','limitation'}:reasons.append('invalid_claim_kind')
        if c.get('kind') in {'analysis','hypothesis'} and not c.get('premise_claim_ids'):reasons.append('unsupported_conclusion')
        if not set(c.get('premise_claim_ids') or [])<=set(ids):reasons.append('unresolved_premise')
        if c.get('adds_to') not in {'title','brief_deck','detail_body'} or not c.get('incremental_value'):reasons.append('no_incremental_information')
    inventory={c['id']:c for c in claims if isinstance(c,dict) and c.get('id')}
    def grounded(cid,path):
        if cid in path or cid not in inventory:return False
        claim=inventory[cid]
        if claim.get('kind') in {'fact','limitation'}:return bool(claim.get('evidence_refs'))
        premises=claim.get('premise_claim_ids') or []
        return bool(premises) and all(grounded(p,path|{cid}) for p in premises)
    if any(c.get('kind') in {'analysis','hypothesis'} and not grounded(c.get('id'),set()) for c in claims if isinstance(c,dict)):
        reasons.append('unsupported_conclusion')
    paragraphs=[p for p in str(record.get('detail_body') or '').split('\n\n') if p.strip()]
    mapping=record.get('paragraph_claim_ids') or {}
    if not isinstance(mapping,dict):mapping={};reasons.append('invalid_paragraph_map')
    for i in range(len(paragraphs)):
        refs=mapping.get(str(i)) or []
        if not refs or not set(refs)<=set(ids):reasons.append('unmapped_paragraph')
    for module in record.get('depth_modules') or []:
        if not isinstance(module,dict):reasons.append('invalid_depth_module');continue
        if not module.get('id') or not str(module.get('label') or '').strip() or not module.get('claim_ids') or not set(module['claim_ids'])<=set(ids):reasons.append('invalid_depth_module')
        if not module.get('evidence_refs') or not set(module['evidence_refs'])<=set(eids):reasons.append('unresolved_module_evidence')
    review=record.get('review') or {}
    if not isinstance(review,dict):review={}
    if review.get('verdict')!='PASS':reasons.extend(review.get('reason_codes') or ['independent_review_pending'])
    if not review.get('author') or not review.get('reviewer') or review.get('author')==review.get('reviewer'):reasons.append('independent_review_required')
    try:version=content_version(record)
    except (TypeError,ValueError):version=None;reasons.append('invalid_content_version')
    if review.get('content_version')!=version:reasons.append('stale_review')
    verdicts=review.get('claim_verdicts') or {}
    if not isinstance(verdicts,dict):verdicts={};reasons.append('invalid_claim_review')
    if any(verdicts.get(cid)!='SUPPORTED' for cid in ids):reasons.append('unsupported_claim')
    decisions=review.get('paragraph_verdicts') or {};new_claims=set()
    if not isinstance(decisions,dict):decisions={};reasons.append('invalid_paragraph_review')
    for i in range(len(paragraphs)):
        decision=decisions.get(str(i)) or {};refs=set(decision.get('new_claim_ids') or [])
        if decision.get('verdict') not in {'NEW','NECESSARY_REPEAT','LIMITATION'}:reasons.append('no_incremental_information')
        if not refs<=set(mapping.get(str(i)) or []):reasons.append('unresolved_incremental_claim')
        if decision.get('verdict')=='NEW' and (not refs or refs<=new_claims):reasons.append('no_incremental_information')
        if decision.get('verdict')=='NECESSARY_REPEAT' and not decision.get('necessary_repeat_reason'):reasons.append('unjustified_repeat')
        new_claims.update(refs)
    if not new_claims:reasons.append('no_incremental_information')
    modules_review=review.get('module_verdicts') or {}
    for module in record.get('depth_modules') or []:
        if not isinstance(module,dict):continue
        decision=modules_review.get(module.get('id')) or {}
        if decision.get('verdict') not in {'NEW','SUPPORTING_DETAIL'}:reasons.append('unreviewed_module')
        if set(module.get('claim_ids') or [])<=new_claims and decision.get('verdict')!='SUPPORTING_DETAIL':reasons.append('no_incremental_module')
        if decision.get('verdict')=='SUPPORTING_DETAIL' and not decision.get('incremental_evidence'):reasons.append('no_incremental_module')
    if record.get('hold_reason') or record.get('publication_status')=='HOLD':reasons.append('publication_hold')
    return {'ok':not reasons,'reason_codes':sorted(set(reasons)),'content_version':version,'diagnostics':depth_diagnostics(record)}

def validate_depth(record):
    try:return _validate_depth(record)
    except (TypeError,ValueError,AttributeError,KeyError):
        return {'ok':False,'reason_codes':['invalid_editorial_schema'],'diagnostics':[]}

def editorial_route(record, *, paid_authorized=False,powerful_model=None,monetary_reserve=False,valid_receipt=False):
    """Plan only. Existing budgets/cached responses remain authoritative."""
    if valid_receipt and validate_depth(record)['ok']:return {'route':'reuse_receipt','paid_call':False}
    if record.get('hold_reason') or not record.get('evidence'):return {'route':'HOLD','paid_call':False,'reason':'missing_or_conflicting_evidence'}
    if not paid_authorized:return {'route':'manual_review','paid_call':False}
    complex_case=bool(record.get('legal_conflict') or record.get('material_contradiction') or record.get('high_impact_review'))
    if complex_case and not (powerful_model and monetary_reserve):return {'route':'HOLD','paid_call':False,'reason':'powerful_route_not_budgeted'}
    return {'route':'powerful' if complex_case else 'economic','paid_call':True,'max_repairs':1,'max_escalations':1}

EDITOR_PROMPT=('Usa sólo evidencia entregada. Ficha única con claims y localizadores; cada párrafo añade '
               'hechos frente al título y el conjunto anterior. Sin bloques obligatorios Qué pasó/Por qué '
               'importa ni mínimo de palabras. Materialidad en selection_rationale interno. Distingue '
               'hecho/análisis/hipótesis, conserva vigencias y bases. Si falta soporte, HOLD. No apruebes '
               'tu propia salida. Los modelos no calculan métricas.')
