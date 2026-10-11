"""Replay original-site evidence into BACKFILL; never manufacture a signal.

Default is read-only. --apply admits audited candidates to the existing queue.
--live evaluates only these candidates with normal processors and AI budgets;
it writes a checkpoint locally and never pushes/deploys anything.
"""
from __future__ import annotations
import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, atomic_json
from radar_salud.sources import load_sources, source_index


def canonical_url(value):
    return str(value or '').split('#')[0].rstrip('/')


def in_window(stamp, as_of, days):
    if not stamp:return None
    return 0 <= (date.fromisoformat(as_of)-date.fromisoformat(stamp)).days <= days


def admit(queue, audit, cfg, now):
    changes=[]
    for evidence in audit['original_items']:
        if not evidence.get('recover'):continue
        url=evidence['url'];parsed=urlparse(url)
        expected=urlparse(audit['surfaces'][0]['url']).netloc.removeprefix('www.')
        if parsed.scheme!='https' or parsed.netloc.removeprefix('www.')!=expected:
            raise ValueError(f"Untrusted recovery URL: {url}")
        stamp=evidence.get('publication_date')
        if stamp and evidence['date_evidence'] not in ('article:published_time','dated_news_listing','verified_article_header','verified_document_release'):
            raise ValueError(f"Unverified recovery publication date: {url}")
        if stamp and not in_window(stamp,audit['as_of'],90):
            raise ValueError(f"Recovery outside 90 days: {url}")
        meta={'discovered_from':audit['surfaces'][0]['url'],
              'publication_date_source':evidence['date_evidence'],
              'recovery_audit':audit['audit_path'],
              'source_quality_gate':audit.get('source_quality_gate','passed')}
        if evidence.get('review_revision'):meta['review_revision']=evidence['review_revision']
        if evidence.get('supporting_official_sources'):meta['supporting_official_sources']=evidence['supporting_official_sources']
        if audit['slug']=='clinicas_chile':meta['clinicas_channel']=evidence.get('channel','Noticias')
        if audit.get('market_role'):meta['market_role']=audit['market_role']
        raw=RawItem(audit['slug'],evidence['title'],url,cfg['name'],cfg['source_type'],stamp,metadata=meta)
        matches=[(k,v) for k,v in queue.items.items() if v['source']==audit['slug']
                 and canonical_url(v['raw']['url'])==canonical_url(url)]
        if len(matches)>1:raise ValueError(f"Duplicate queue URL requires review: {url}")
        if matches:
            key,item=matches[0]
            if item['status'] in ('published','archived'):continue
            reassess=(item['status']=='rejected' and evidence.get('review_false_negative') is True
                      and evidence.get('review_revision') and evidence.get('supporting_official_sources')
                      and item['raw'].get('metadata',{}).get('review_revision')!=evidence['review_revision'])
            if item['status']=='rejected' and not reassess:continue
            if audit['slug']=='clinicas_chile':
                item['raw']['metadata'].pop('page_text',None);item['raw']['raw_text']=''
            if item['raw'].get('metadata',{}).get('recovery_audit')==audit['audit_path'] and not reassess:continue
            item['audit_prior_state']={'status':item['status'],'reason':item.get('reason')}
            if reassess:item.setdefault('review_history',[]).append({'at':now.isoformat(),'prior_status':item['status'],
                'historical_processor_reason':'unknown; original model reason/score not persisted',
                'review_revision':evidence['review_revision'],'reason':'Reviewer confirmed material programme; reassess once with additional official announcement/execution evidence'})
            old_gate=item['raw'].get('metadata',{}).get('source_quality_gate')
            item['raw']['metadata'].update(meta)
            if old_gate and old_gate!='passed':item['raw']['metadata']['source_quality_gate']=old_gate
            if stamp:item['raw']['event_date']=stamp
            item.update(status='pending',lane='BACKFILL',reason='audited_recovery_pending_assessment',retry_at=None)
            changes.append({'key':key,'url':url,'action':'refresh_pending'})
        else:
            previous=set(queue.items)
            queue.discover(audit['slug'],[raw],now=now)
            key=next(iter(set(queue.items)-previous))
            queue.items[key]['reason']='audited_recovery_pending_assessment' if stamp else 'unverified_publication_date'
            changes.append({'key':key,'url':url,'action':'admit_backfill'})
    queue.save()
    return changes


def reconcile(audit, queue, history, visible):
    out=[]
    for evidence in audit['original_items']:
        url=canonical_url(evidence['url'])
        queued=[{'key':k,'status':v['status'],'reason':v.get('reason'),'lane':v['lane']}
                for k,v in queue.items.items() if v['source']==audit['slug'] and canonical_url(v['raw']['url'])==url]
        published=[v for v in history if canonical_url(v.get('source_url'))==url and v.get('feed_visibility') is not False]
        shown=[v for v in visible if canonical_url(v.get('source_url'))==url]
        out.append({'url':evidence['url'],'publication_date':evidence.get('publication_date'),
                    'in_30_days':in_window(evidence.get('publication_date'),audit['as_of'],30),
                    'in_90_days':in_window(evidence.get('publication_date'),audit['as_of'],90),
                    'materiality':evidence['materiality'],'queue':queued,
                    'history_count':len(published),'visible_count':len(shown)})
    material=[v for v in out if v['materiality']=='candidate']
    return {'scope':'verified original items; lower bound where inventory is blocked',
            'material_candidates_30_days':sum(v['in_30_days'] is True for v in material),
            'material_candidates_90_days':sum(v['in_90_days'] is True for v in material),
            'publication_date_unknown':sum(v['publication_date'] is None for v in out),
            'queue_counts':queue.counts(audit['slug']),'items':out}


def run(root, slug=None, apply=False, live=False, limit=12, urls=None, checkpoint_path=None):
    from radar_salud.history import load_history, merge_history, save_history
    from radar_salud.processing import DeferredProcessing, OutsideBackfillHorizon
    from radar_salud.public_source_pipeline import process_corporate_news, process_clinicas_chile
    from radar_salud.beta_sources import process_curated_beta_source
    from radar_salud.ai_budget import has_capacity
    cfgs=source_index(load_sources(root/'config/sources.json'))
    queue=PendingQueue(root/'data/state/pending_queue.json')
    health=json.loads((root/'data/source_health.json').read_text())
    history_path=root/'data/history/superintendencia_signals.json'
    history=load_history(history_path)
    visible=json.loads((root/'web/data/radar_today.json').read_text())['signals']
    now=datetime.now(timezone.utc);live_results=[];attempted=0
    for path in sorted((root/'data/audits/providers_2026_10_11').glob('*.json')):
        audit=json.loads(path.read_text());name=audit['slug']
        if slug and name!=slug:continue
        if apply:
            changes=admit(queue,audit,cfgs[name],now)
            audit.setdefault('recovery_checkpoint',{'at':now.isoformat(),'changes':changes})
            # Library content/data dates cannot establish publication dates.
            quarantine={canonical_url(x) for x in audit.get('quarantine_unverified_dates',[])}
            for row in history:
                if canonical_url(row.get('source_url')) in quarantine:
                    row.setdefault('event_date_before_provider_audit',row.get('event_date'))
                    row.update(event_date=None,feed_visibility=False,publication_gate_reason='unverified_publication_date')
            for item in queue.items.values():
                raw=item['raw']
                if name=='clinicas_chile' and item['source']==name and (urlparse(raw['url']).path.lower().endswith(('.pdf','.xls','.xlsx','.csv'))
                        or raw.get('metadata',{}).get('clinicas_channel') in ('Memorias','Estudios y análisis','Documentos')):
                    if raw.get('event_date') and raw['metadata'].get('publication_date_source')!='verified_document_release':
                        raw['metadata'].setdefault('event_date_before_provider_audit',raw['event_date']);raw['event_date']=None
                        raw['metadata']['publication_date_source']='unverified'
                    if canonical_url(raw['url']) in quarantine:
                        item.update(status='retry',lane='BACKFILL',reason='unverified_publication_date',retry_at=None)
            if live:
                processor=process_clinicas_chile if name=='clinicas_chile' else process_curated_beta_source if audit.get('market_role') else process_corporate_news
                for key,item in list(queue.items.items()):
                    if item['source']!=name or item['raw'].get('metadata',{}).get('recovery_audit')!=audit['audit_path'] or item['status'] not in ('pending','retry'):continue
                    if urls and canonical_url(item['raw']['url']) not in {canonical_url(url) for url in urls}:continue
                    if attempted>=limit or not (has_capacity('fast') or has_capacity('deep')):
                        live_results.append({'source':name,'url':item['raw']['url'],'outcome':'not_evaluated','blocker':'processing_limit_or_existing_ai_budget'});continue
                    attempted+=1;queue.start(key);raw=RawItem(**item['raw'])
                    try:
                        row=processor(raw,cfgs[name])
                        from dataclasses import asdict
                        item['raw']=asdict(raw)
                        if row:
                            row.update(detected_at=item['detected_at'],ingestion_mode='BACKFILL')
                            history=merge_history(history,[row]);save_history(history_path,history)
                        from radar_salud.provider_assessment import rejection_reason
                        queue.finish(key,'published' if row else 'rejected',None if row else rejection_reason(raw))
                        from radar_salud.scouts import SeenStore
                        SeenStore(root/'data/state'/f'{name}_seen.json').add_many([key])
                        live_results.append({'source':name,'url':raw.url,'outcome':'published' if row else 'rejected','signal':row,
                                             'editorial_assessment':raw.metadata.get('editorial_assessment')})
                    except OutsideBackfillHorizon as exc:
                        item['raw']['event_date']=str(exc);queue.finish(key,'archived','outside_90_day_backfill')
                        live_results.append({'source':name,'url':raw.url,'outcome':'archived','blocker':'outside_90_day_backfill'})
                    except Exception as exc:
                        item['deferred_detail']=str(exc);queue.finish(key,'retry','budget_or_analysis_deferred' if isinstance(exc,DeferredProcessing) else type(exc).__name__)
                        live_results.append({'source':name,'url':raw.url,'outcome':'retry','blocker':str(exc)})
                    finally:
                        from dataclasses import asdict
                        item['raw']=asdict(raw);queue.save()
            audit['reconciliation']=reconcile(audit,queue,history,visible)
            h=health['sources'].setdefault(name,{})
            counts=queue.counts(name)
            h.update(name=cfgs[name]['name'],live_pending=counts['live_pending'],backfill_pending=counts['backfill_pending'],
                     pending=counts['live_pending']+counts['backfill_pending'],rejected=counts['rejected'],
                     coverage_status='unverified' if audit['blockers'] else 'observed',status='error' if h.get('technical_status')=='error' else 'warning')
            if name=='clinicas_chile':
                legitimate=[v['event_date'] for v in history if v.get('source_name')==cfgs[name]['name'] and v.get('event_date') and v.get('feed_visibility') is not False]
                h.update(last_signal_at=max(legitimate) if legitimate else None,content_freshness='older' if legitimate else 'unknown')
            if name in ('red_davila','andes_salud') and not h.get('audited_assessment'):
                h.update(evaluation_performed=False,editorial_outcome='not_evaluated',collection_mode='discovery_only')
            assessed=[v for v in live_results if v['source']==name and v['outcome'] in ('published','rejected')]
            published=[v['signal'] for v in assessed if v['outcome']=='published']
            if live and any(v['source']==name for v in live_results):
                h['audited_assessment']={'at':now.isoformat(),'evaluated':len(assessed),'published':len(published),
                    'last_signal_at':max([v.get('event_date') for v in published if v.get('event_date')] or ['']) or None,
                    'outcome':'published' if published else 'rejected' if assessed else 'not_evaluated'}
                # These fields describe this bounded assessment, while the
                # unchanged checked_at still identifies the previous full poll.
                h.update(evaluation_performed=bool(assessed),editorial_outcome=h['audited_assessment']['outcome'],published=len(published),collection_mode='audited_candidates_only')
                if published:h['last_signal_at']=max([v.get('event_date') for v in published if v.get('event_date')]+[h.get('last_signal_at') or ''])
            if name=='pfizer_chile':h['content_freshness']='stale_external_surface'
            h['provider_audit']={'as_of':audit['as_of'],'path':audit['audit_path'],'blockers':audit['blockers'],
                'latest_verified_original_at':max([x.get('publication_date') for x in audit['original_items'] if x.get('publication_date')] or ['']) or None,
                'recovered_pending':sum(v['status'] in ('pending','retry') and v['raw'].get('metadata',{}).get('recovery_audit')==audit['audit_path'] for v in queue.items.values() if v['source']==name)}
            atomic_json(path,audit)
        else:audit['reconciliation']=reconcile(audit,queue,history,visible)
        print(name,json.dumps(audit['reconciliation']['queue_counts']),audit['reconciliation']['material_candidates_30_days'],audit['reconciliation']['material_candidates_90_days'])
    if apply:
        queue.save();save_history(history_path,history);atomic_json(root/'data/source_health.json',health)
    if live:atomic_json(root/(checkpoint_path or 'data/audits/provider_live_checkpoint_2026_10_11.json'),{'at':now.isoformat(),'attempted':attempted,'results':live_results,'promotion':'none; isolated candidate outputs only'})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path('.'));ap.add_argument('--source');ap.add_argument('--apply',action='store_true');ap.add_argument('--live',action='store_true');ap.add_argument('--limit',type=int,default=12);ap.add_argument('--url',action='append')
    args=ap.parse_args()
    if args.live and not args.apply:ap.error('--live requires --apply')
    run(args.root,args.source,args.apply,args.live,args.limit,args.url)
