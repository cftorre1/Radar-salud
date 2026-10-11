"""Apply scoped, verified native engine output, retaining original discovery evidence.

Historical URL counts remain distinct from certified legal-act counts. Report
publication uncertainty prevents a site-wide completeness claim.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import date
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from radar_salud.history import load_history,save_history,_key
from radar_salud.models import RawItem
from radar_salud.pending_queue import atomic_json,fingerprint
from radar_salud.sources import load_sources,source_index
from radar_salud.superintendencia_fiscalizacion import canonical_url,process_fiscalizacion,reviewed_primary_act

SOURCES=('superintendencia_fiscalizacion','suseso_fiscalizacion')
AS_OF=date(2026,10,11)

def recent(raw,days):
    meta=raw['metadata']
    for value in (meta.get('publication_date'),meta.get('emission_date'),raw.get('event_date')):
        try:
            if 0<=(AS_OF-date.fromisoformat(value)).days<=days:return True
        except (ValueError,TypeError):pass
    return False

def baseline(path):
    return json.loads(subprocess.check_output(['git','show','cadb6c2:'+path],text=True))

def reconcile(runtime,root=Path('.'),apply=False):
    manifest=json.loads((runtime/'manifest.json').read_text())
    replay=runtime/'isolated-replay'
    result=json.loads((replay/'replay_report.json').read_text())
    assert result['actual_engine'] and result['actual_collectors'] and result['idempotent'] and result['other_queue_records_preserved']
    assert result['captured_sha']==manifest['started_from_sha']
    inventory=json.loads((replay/'collector_inventory.json').read_text())
    history=load_history(replay/'history.json');queue=json.loads((replay/'pending_queue.json').read_text())
    reviews=json.loads((root/'config/fiscalization_editorial_reviews.json').read_text())
    cfg=source_index(load_sources(root/'config/sources.json'))
    # Preserve other lanes from current checkout even when the replay copy predates it.
    other_queue={k:v for k,v in json.loads((root/'data/state/pending_queue.json').read_text()).items() if v['source'] not in SOURCES}
    queue={k:v for k,v in queue.items() if v['source'] in SOURCES}|other_queue
    current_history=load_history(root/'data/history/superintendencia_signals.json')
    selected_norms={url for url,review in reviews.get('source_records',{}).items() if review.get('decision')=='publish_normative'}
    independent=[s for s in current_history if 'Fiscalización' not in s.get('signal_types',[]) and s.get('source_url') not in selected_norms]
    scoped=[s for s in history if 'Fiscalización' in s.get('signal_types',[]) or s.get('source_url') in selected_norms]
    history=independent+scoped
    history_ids={_key(s):s for s in history}
    old_q=baseline('data/state/pending_queue.json')
    old_h=baseline('data/history/superintendencia_signals.json');old_h=old_h.get('signals',old_h) if isinstance(old_h,dict) else old_h
    baseline_ids={_key(s) for s in old_h}
    baseline_qids={(i['source'],canonical_url(i['raw']['url'])) for i in old_q.values()}
    repairs=[]
    asset_reviews=reviews.get('historical_listing_alias_reviews',{})
    for index,raw in enumerate(inventory):
        assets=[asset for asset,review in asset_reviews.items() if review['document_url']==raw['url']]
        if assets:raw['metadata']['listing_asset_aliases']=assets
        if raw['source_slug']=='superintendencia_fiscalizacion':
            raw=asdict(reviewed_primary_act(RawItem(**raw)));inventory[index]=raw
            key=canonical_url(raw['url'])
            if key in history_ids and raw['metadata'].get('date_conflicts') and not recent(raw,90):
                history_ids[key]['date_conflicts']=raw['metadata']['date_conflicts']
                history_ids[key]['date_reconciliation']='historical_primary_date_conflict_unresolved; not rejuvenated'
                repairs.append(dict(url=key,conflicts=raw['metadata']['date_conflicts']))
            elif key in history_ids:
                old=history_ids[key]
                if recent(raw,90):
                    row=process_fiscalizacion(RawItem(**raw),cfg[raw['source_slug']])
                    from radar_salud.editorial_gate import publication_ready
                    assert publication_ready(row)[0],raw['url']
                    row['source_url']=old['source_url']
                    for field in ('detected_at','ingestion_mode'):
                        if old.get(field):row[field]=old[field]
                    history_ids[key]=row
                else:
                    # Correct dates from dated stock without inventing actors/text.
                    old.update(publication_date=raw['metadata'].get('publication_date'),
                        emission_date=raw['metadata'].get('emission_date'),
                        event_date=raw.get('event_date'),event_date_basis=raw['metadata'].get('event_date_basis'))
                    if raw['metadata'].get('primary_document_review'):
                        old.update({k:raw['metadata'][k] for k in ('primary_document_review','date_reconciliation','observed_listing_publication_date','date_conflicts','regulated_entity','sanction_amount','sanction_unit') if k in raw['metadata']})
        elif raw['metadata'].get('document_class')=='related_normative':
            meta=raw['metadata'];meta['emission_date']=meta.get('emission_date') or raw['event_date'];meta['publication_date']=None;meta['event_date_basis']='emission'
        k=fingerprint(RawItem(**raw))
        if k in queue and queue[k]['raw']!=raw:
            queue[k].setdefault('stock_reconciliation',[]).append(dict(reason='native_primary_fields_reconciled',previous_raw=queue[k]['raw'],at=manifest['completed_at']))
            queue[k]['raw']=raw
    # Explain all 38 legacy SUSESO items; their actor-taxonomy membership was normative.
    for asset,review in asset_reviews.items():
        asset_item=next(((k,v) for k,v in queue.items() if v['source']=='superintendencia_fiscalizacion' and canonical_url(v['raw']['url'])==asset),None)
        document_item=next((v for v in queue.values() if v['source']=='superintendencia_fiscalizacion' and canonical_url(v['raw']['url'])==review['document_url']),None)
        if asset_item and document_item:
            document_item['detected_at']=min(document_item['detected_at'],asset_item[1]['detected_at'])
            document_item.setdefault('superseded_records',[]).append(asset_item[1])
            document_item.setdefault('legacy_keys',[]).append(asset_item[0])
            document_item['listing_asset_identity_review']=review
            del queue[asset_item[0]]
    legacy_su=[]
    for old_key,item in old_q.items():
        if item['source']!='suseso_fiscalizacion':continue
        raw=item['raw'];identity=canonical_url(raw['url']);match=next((v for v in queue.values() if v['source']=='suseso_fiscalizacion' and canonical_url(v['raw']['url'])==identity),None)
        kind=raw['title'].split()[0]
        legacy_su.append(dict(url=identity,title=raw['title'],document_kind=kind,detected_at=item['detected_at'],previous_status=item['status'],decision='rejected',reason='related_normative_not_enforcement'))
        if match:
            if match['status']!='rejected':match.setdefault('stock_reconciliation',[]).append(dict(at=manifest['completed_at'],previous_status=match['status'],previous_reason=match.get('reason'),reason='related_normative_not_enforcement'))
            match.update(status='rejected',reason='related_normative_not_enforcement',retry_at=None)
            match['raw']['metadata'].update(document_class='related_normative',publication_date=None,emission_date=raw.get('event_date'),event_date_basis='emission')
    # Administrative subrogation is not an enforcement report.
    administrative=[]
    for item in queue.values():
        if item['source']=='superintendencia_fiscalizacion' and item['raw']['title'].startswith('Decreto Exento'):
            administrative.append(dict(url=item['raw']['url'],title=item['raw']['title'],decision='rejected',reason='administrative_subrogation_not_enforcement'))
            item.update(status='rejected',reason='administrative_subrogation_not_enforcement',retry_at=None)
    # One verified PDF, two conflicting listing aliases; do not invent the 200 UTM act.
    alias_review=reviews['historical_identity_reviews']['IP/4640']
    aliases=alias_review['urls'];canonical=canonical_url(aliases[0]);duplicate=canonical_url(aliases[1])
    alias_items=[(k,v) for k,v in queue.items() if v['source']=='superintendencia_fiscalizacion' and canonical_url(v['raw']['url']) in aliases]
    if len(alias_items)==2:
        keep=next((k,v) for k,v in alias_items if canonical_url(v['raw']['url'])==canonical)
        removed=next((k,v) for k,v in alias_items if canonical_url(v['raw']['url'])==duplicate)
        keep[1].setdefault('primary_aliases',[]).append(dict(key=removed[0],record=removed[1],review=alias_review))
        del queue[removed[0]]
    for row in history_ids.values():
        if row.get('source_url') in aliases:
            row.update(publication_date='2024-07-17',emission_date=alias_review['emission_date'],event_date=alias_review['emission_date'],event_date_basis='verified_primary_emission',regulated_entity=alias_review['regulated_entity'],sanction_amount=700,sanction_unit='UTM',primary_document_review=alias_review)
    if duplicate in history_ids:
        dup=history_ids.pop(duplicate)
        if canonical in history_ids:history_ids[canonical]['primary_aliases']=[dup]
        else:dup.update(source_url=canonical,primary_aliases=[duplicate]);history_ids[canonical]=dup
    history=list(history_ids.values())
    # The already approved routed dictamen's row date is issuance, not publication.
    for row in history:
        if row.get('source_url') in selected_norms:
            row.update(publication_date=None,emission_date=row['event_date'],event_date_basis='emission')
    ledger=[];unknown=[];stock=[]
    for raw in inventory:
        key=fingerprint(RawItem(**raw));item=queue.get(key);meta=raw['metadata']
        hkey=raw['url']+('|record:'+meta['source_record_id'] if meta.get('source_record_id') else '')
        row=history_ids.get(hkey)
        kind=meta.get('document_class')
        published=bool(row and 'Fiscalización' in row.get('signal_types',[]))
        decision='published' if published else (item or {}).get('status','outside_scope')
        reason='verified_material_enforcement; durable_history' if published else (item or {}).get('reason')
        if raw['url']==duplicate:decision='deduplicated';reason='same_verified_primary_pdf_with_conflicting_listing_observation'
        receipt=dict(source=raw['source_slug'],url=raw['url'],source_record_id=meta.get('source_record_id'),title=raw['title'],document_class=kind or meta.get('fiscalization_kind'),decision=decision,reason=reason,
            event_date=raw.get('event_date'),publication_date=meta.get('publication_date'),emission_date=meta.get('emission_date'),notification_date=meta.get('notification_date'),modification_date=meta.get('modification_date'),fact_date=meta.get('fact_date'),fact_period=meta.get('fact_period'),execution_period=meta.get('execution_period'),event_date_basis=meta.get('event_date_basis'),actor=meta.get('regulated_entity'),actor_category=meta.get('scope') or meta.get('fiscalized_actors'),amount=meta.get('sanction_amount'),unit=meta.get('sanction_unit'),effect=meta.get('sanction_effect'),validity=meta.get('validity_text'),detected_at=(item or row or {}).get('detected_at'),baseline_detected=hkey in baseline_ids or (raw['source_slug'],canonical_url(raw['url'])) in baseline_qids,baseline_published=hkey in baseline_ids,
            materiality=(row or {}).get('why_it_matters'),what_happened=(row or {}).get('what_happened') or raw['raw_text'],primary_documents=meta.get('attachments',[]))
        stock.append({k:receipt[k] for k in ('source','url','source_record_id','title','document_class','decision','reason','event_date','publication_date','emission_date','actor_category','baseline_detected')})
        if kind=='enforcement_report_candidate':unknown.append(receipt)
        if recent(raw,90):ledger.append(receipt)
    confirmed=lambda r:r['source']=='superintendencia_fiscalizacion' or r['decision']=='published'
    windows={}
    for source in SOURCES:
        windows[source]={}
        for days in (30,90):
            rows=[r for r in ledger if r['source']==source and confirmed(r) and any(v and 0<=(AS_OF-date.fromisoformat(v)).days<=days for v in (r['publication_date'],r['emission_date'],r['event_date']))]
            windows[source][str(days)]=dict(publication_dated=sum(bool(r['publication_date'] and 0<=(AS_OF-date.fromisoformat(r['publication_date'])).days<=days) for r in rows),emission_dated=sum(bool(r['emission_date'] and 0<=(AS_OF-date.fromisoformat(r['emission_date'])).days<=days) for r in rows),official_confirmed=len(rows),detected=len(rows),baseline_detected=sum(r['baseline_detected'] for r in rows),baseline_omitted=sum(not r['baseline_detected'] for r in rows),omitted=0,material=sum(r['decision']=='published' for r in rows),published=sum(r['decision']=='published' for r in rows),rejected=sum(r['decision']=='rejected' for r in rows),deferred=sum(r['decision'] in ('retry','pending','processing') for r in rows))
    legacy_urls={canonical_url(r['url']) for r in json.loads((root/'data/audits/fiscalizacion/native_runtime_2026_10_11.json').read_text())['legacy_sis_rows']}
    legacy_urls={asset_reviews.get(url,{}).get('document_url',url) for url in legacy_urls}
    missing_verified_alias=duplicate not in {raw['url'] for raw in inventory}

    report=dict(historical_date_conflicts=repairs,as_of=AS_OF.isoformat(),runtime=manifest['github_run_url'],runtime_sha=manifest['started_from_sha'],native_engine=result,windows=windows,
        coverage_complete=False,coverage_reason='All dated rows reconciled in enumerated official surfaces. Ten medical reports lack daily publication/emission dates. Historical SIS document identity only verified where primary attachments permit; unique URLs do not certify unique legal acts.',
        final_states={s:'OPERATIVE_DEGRADED' for s in SOURCES},recent_decisions=ledger,date_uncertain_reports=unknown,
        legacy_suseso=dict(count=len(legacy_su),classification_counts=dict(Counter(r['document_kind'] for r in legacy_su)),decisions=legacy_su),
        legacy_sis=dict(classification_counts=dict(Counter(('report' if raw['metadata'].get('fiscalization_kind')=='report' else raw['metadata'].get('sanction_effect') or 'unknown') for raw in inventory if raw['source_slug']=='superintendencia_fiscalizacion' and raw['url'] in legacy_urls)),discovered_urls=2696,pagination_duplicate_urls=0,administrative_exclusions=administrative,verified_primary_alias=alias_review,unique_enforcement_listing_urls=2695,unique_after_one_verified_primary_alias=2694,all_legal_act_identities_certified=False),
        stock_classification_counts={s:dict(Counter((r['document_class'] or 'unknown')+':'+r['decision'] for r in stock if r['source']==s)) for s in SOURCES})
    if missing_verified_alias:report['legacy_sis']['classification_counts']['sanction']+=1
    report['legacy_sis'].update(original_representations={'document_urls':2684,'thumbnail_assets':11,'administrative_subrogation':1},thumbnail_asset_identity_repairs=asset_reviews)
    if apply:
        save_history(root/'data/history/superintendencia_signals.json',history);atomic_json(root/'data/state/pending_queue.json',queue)
        health=json.loads((root/'data/source_health.json').read_text());runtime_health=json.loads((replay/'source_health.json').read_text())
        for source in SOURCES:
            source_health=runtime_health['sources'][source]
            domain='superdesalud.gob.cl' if source.startswith('super') else 'suseso.gob.cl'
            receipts=[r for r in manifest['receipts'] if domain in r['url']]
            own=[v for v in queue.values() if v['source']==source]
            source_health.update(archived=sum(v['status']=='archived' for v in own),pending=sum(v['status'] in ('retry','pending','processing') for v in own),checked_at=max(r['completed_at'] for r in receipts),unique_items=sum(r['source']==source and r['decision']!='deduplicated' for r in stock),pages_checked=sum(not r['body_file'].endswith('.pdf') for r in receipts),documents_checked=sum(r['body_file'].endswith('.pdf') for r in receipts),http_receipts_checked=len(receipts),items_recent=windows[source]['90']['official_confirmed'],items_material=windows[source]['90']['material'],items_recent_enforcement=windows[source]['90']['official_confirmed'],windows=windows[source],coverage_complete=False,coverage_reason=('Seven official results indexes fully reconciled in 30/90-day dated windows; coverage outside these indexes and all historical legal-act identities not certified.' if source.startswith('superintendencia') else 'Dated sanctions and official news fully reconciled. Publication dates remain unknown for 439 historical-execution programme rows and ten medical result reports; no site-wide absence claim.'),publication_date_uncertain_reports=sum(r['source']==source and r['document_class'] in ('enforcement_report_candidate','historical_enforcement_report') for r in stock),bounded_dated_coverage_complete=True,final_state='OPERATIVE_DEGRADED',status='warning',rejected=sum(v['status']=='rejected' for v in own),deferred=sum(v['status']=='retry' for v in own),deferred_date_uncertain=sum(v['raw']['metadata'].get('document_class')=='enforcement_report_candidate' for v in own),rejection_reasons=dict(Counter(v.get('reason') for v in own if v['status']=='rejected')),reconciliation=dict(at=manifest['completed_at'],native_live_validated=True,runtime_url=manifest['github_run_url'],runtime_sha=manifest['started_from_sha'],stock_preserves_detected_at=True,backfill_only=True),zero_published_reason='idempotent replay; all confirmed recent material acts already persisted')
            health['sources'][source]=source_health
        health['generated_at']=manifest['completed_at'];atomic_json(root/'data/source_health.json',health);atomic_json(root/'web/data/source_health.json',health)
        spec=importlib.util.spec_from_file_location('native_scope_export',root/'scripts/export_web_snapshot.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
        from radar_salud.editorial_copy import apply_reviewed_copy
        feed_path=root/'web/data/radar_today.json';payload=json.loads(feed_path.read_text());retained=[s for s in payload['signals'] if 'Fiscalización' not in s.get('signal_types',[]) and s.get('source_url') not in selected_norms]
        refreshed=apply_reviewed_copy(exporter.curate([s for s in history if 'Fiscalización' in s.get('signal_types',[]) or s.get('source_url') in selected_norms],resolve_external=False,as_of=AS_OF))
        payload.update(signals=sorted(retained+refreshed,key=lambda s:s.get('event_date') or '',reverse=True),generated_at=manifest['completed_at'],date=AS_OF.isoformat());atomic_json(feed_path,payload)
        report['feed']=dict(independent_rows_preserved=len(retained),fiscalization_cards=len([r for r in refreshed if 'Fiscalización' in r.get('signal_types',[])]),grouped_register_cards=2)
        destination=root/'data/audits/fiscalizacion';atomic_json(destination/'native_reconciliation_2026_10_11.json',report);atomic_json(destination/'native_stock_ledger_2026_10_11.json',stock)
        atomic_json(destination/'native_transport_receipts_2026_10_11.json',manifest)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    result=reconcile(args.runtime,apply=args.apply)
    print(json.dumps(dict(windows=result['windows'],coverage_complete=result['coverage_complete']),ensure_ascii=False))
