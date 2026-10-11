"""Reconcile verified observations to durable stock; --apply touches only this scope.

Evidence is explicit: this is a source observation replay, never a claim that
native discovery/AI ran successfully. Original captures remain immutable.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import json
from pathlib import Path
from radar_salud.models import RawItem
from radar_salud.history import load_history, merge_history, save_history
from radar_salud.pending_queue import PendingQueue, atomic_json, fingerprint
from radar_salud.scouts import SeenStore
from radar_salud.sources import load_sources, source_index
from radar_salud.superintendencia_fiscalizacion import canonical_url, process_fiscalizacion
from radar_salud.suseso_fiscalizacion import reviewed_normative_candidate, process_reviewed_normative
from radar_salud.editorial_gate import publication_ready
from radar_salud.processing import RejectedProcessing


def reconcile(root, observations, apply=False):
    as_of=date.fromisoformat(observations['as_of'])
    now=datetime.combine(as_of,datetime.min.time(),tzinfo=timezone.utc)
    history_path=root/'data/history/superintendencia_signals.json'
    history=load_history(history_path)
    before={canonical_url(row.get('source_url','')):row for row in history}
    feed=json.loads((root/'web/data/radar_today.json').read_text())['signals']
    feed_urls={canonical_url(row.get('source_url','')) for row in feed}
    feed_urls.update(canonical_url(alt.get('url','')) for row in feed for alt in row.get('source_alternatives',[]))
    queue=PendingQueue(root/'data/state/pending_queue.json')
    cfgs=source_index(load_sources(root/'config/sources.json'))
    records=[]
    published=[]
    baseline=observations.get('baseline', {})
    for document in observations['documents']:
        raw=RawItem(**document)
        url=canonical_url(raw.url)
        existing=before.get(url)
        receipt=dict(source=raw.source_slug,url=raw.url,title=raw.title,
            publication_date=raw.metadata.get('publication_date'),event_date=raw.event_date,
            actors=raw.metadata.get('fiscalized_actors') or [raw.metadata.get('regulated_entity')],
            scope=raw.metadata.get('scope') or raw.metadata.get('fiscalized_actors'),
            history_before=bool(existing),feed_before=url in feed_urls,
            queue_before=[dict(key=key,status=item['status'],reason=item.get('reason')) for key,item in queue.items.items()
                if canonical_url(item['raw'].get('url',''))==url],
            event_windows={},publication_windows={})
        # Baseline evidence survives subsequent replays; *_before describes this run.
        receipt['baseline_presence']=baseline.get('documents', {}).get(url)
        for window in (30,90):
            receipt['event_windows'][str(window)]=0 <= (as_of-date.fromisoformat(raw.event_date)).days <= window
            receipt['publication_windows'][str(window)]=0 <= (as_of-date.fromisoformat(raw.metadata['publication_date'])).days <= window
        if raw.source_slug=='superintendencia_fiscalizacion':
            try:
                row=process_fiscalizacion(raw,cfgs[raw.source_slug])
                passed,reason,_=publication_ready(row)
                if not passed:raise RejectedProcessing(reason)
                if not existing:
                    # This audit does not promote unreviewed new sanctions by default.
                    raise RejectedProcessing('new_sanction_requires_editorial_review')
                row.update(source_url=existing['source_url'],ingestion_mode=existing.get('ingestion_mode') or 'BACKFILL')
                if existing.get('detected_at'):row['detected_at']=existing['detected_at']
                published.append(row)
                receipt.update(decision='correct_existing_history',reason='published_material_act; dates_actor_effect_reconciled',
                    previous_event_date=existing.get('event_date'))
            except RejectedProcessing as exc:
                receipt.update(decision='hold',reason=str(exc))
                if apply:
                    queue.discover(raw.source_slug,[raw],now=now,last_discovered_at=observations['observed_at'])
                    key=fingerprint(raw)
                    if key in queue.items:queue.finish(key,'rejected',str(exc),now=now)
        else:
            candidate=reviewed_normative_candidate(raw)
            receipt.update(decision='exclude_from_fiscalization',reason='related_normative_not_enforcement')
            if existing:
                receipt.update(normative_outcome='already_in_history')
                if candidate:
                    receipt.update(normative_outcome='already_published_reviewed_material_instruction',
                        materiality_reason=candidate.metadata['reviewed_normative']['reason'])
            elif candidate:
                row=process_reviewed_normative(candidate,cfgs['suseso'])
                passed,reason,_=publication_ready(row)
                if not passed:raise ValueError(f'Reviewed normativa rejected: {reason}')
                row.update(ingestion_mode='BACKFILL',detected_at=observations['observed_at'])
                published.append(row)
                receipt.update(normative_outcome='published_reviewed_material_instruction',materiality_reason=candidate.metadata['reviewed_normative']['reason'])
                if apply:
                    queue.discover('suseso',[candidate],now=now,last_discovered_at=observations['observed_at'])
                    key=fingerprint(candidate)
                    if key in queue.items:
                        queue.finish(key,'published','reviewed_fiscalization_route_to_normativa',now=now)
                        SeenStore(root/'data/state/suseso_seen.json').add_many([key])
            else:
                receipt.update(normative_outcome='excluded_from_this_enforcement_scope',
                    materiality_reason='Related circular/pronouncement is not a new sanction or verified enforcement result; no fiscalization publication. Independent normative value is not inferred from taxonomy membership.')
            if apply:
                queue.discover(raw.source_slug,[raw],now=now,last_discovered_at=observations['observed_at'])
                key=fingerprint(raw)
                if key in queue.items:
                    queue.finish(key,'rejected','related_normative_not_enforcement',now=now)
                    SeenStore(root/'data/state/suseso_fiscalizacion_seen.json').add_many([key])
        records.append(receipt)
    report=dict(as_of=observations['as_of'],observed_at=observations['observed_at'],mode='official_web_observation_replay',
        baseline_commit=baseline.get('commit'),
        coverage_complete=False, native_validation='blocked_environment_proxy_403',
        limits=observations['limits'],surfaces=observations['surfaces'],decisions=records,
        outcome_counts=dict(Counter(record['decision'] for record in records)),
        next_step='Run native collectors in an environment allowing official domains; compare raw HTML and dated surface receipts after this SHA. Extend reconciliation to all dynamic rows. Review other SUSESO normative value independently; never label taxonomy rows as enforcement.')
    if apply:
        history=merge_history(history,published);save_history(history_path,history)
        health_path=root/'data/source_health.json';health=json.loads(health_path.read_text())
        for slug in ('superintendencia_fiscalizacion','suseso_fiscalizacion'):
            source=health['sources'][slug]
            stock=[row for row in history if 'Fiscalización' in (row.get('signal_types') or []) and
                ('superdesalud.gob.cl' if slug.startswith('superintendencia') else 'suseso.gob.cl') in row.get('source_url','')]
            docs=[row for row in observations['documents'] if row['source_slug']==slug]
            counts=queue.counts(slug)
            source.update(status='warning',coverage_status='partial',coverage_reason='verified_visible_web_rows; native_http_blocked; site_wide_completeness_unverified',
                last_signal_at=max((row.get('event_date') or '' for row in stock),default='') or None,
                published_total=len(stock),last_observed_event_at=max(row['event_date'] for row in docs),
                last_observed_publication_at=max(row['metadata']['publication_date'] for row in docs),
                live_pending=counts['live_pending'],backfill_pending=counts['backfill_pending'],pending=counts['live_pending']+counts['backfill_pending'],
                rejected=counts['rejected'],archived=sum(item['status']=='archived' for item in queue.items.values() if item['source']==slug),
                rejection_reasons=dict(Counter(item.get('reason') for item in queue.items.values() if item['source']==slug and item['status']=='rejected')),
                editorial_outcome='reconciled_existing_history' if stock else 'related_normative_excluded',
                reconciliation=dict(at=observations['observed_at'],mode='official_web_observation_replay',native_live_validated=False),
                counter_semantics={'discovered':'last native discovery run, including historical documents','published':'last native run publications; not history/feed stock','published_total':'persisted fiscalization history stock','pending':'current queue stock','rejected':'current evaluated rejection stock','archived':'queue outside 90-day horizon'})
            # checked_at remains the actual native poll timestamp; replay is separate.
        atomic_json(health_path,health)
        # Refresh this scope while preserving independently reviewed feed rows.
        import importlib.util
        from radar_salud.editorial_copy import apply_reviewed_copy
        spec=importlib.util.spec_from_file_location('fiscalization_export',root/'scripts/export_web_snapshot.py')
        exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
        selected={url for url,review in json.loads((root/'config/fiscalization_editorial_reviews.json').read_text()).get('source_records',{}).items()
            if review.get('decision')=='publish_normative'}
        scoped=[row for row in history if 'Fiscalización' in (row.get('signal_types') or []) or row.get('source_url') in selected]
        retained=[row for row in feed if 'Fiscalización' not in (row.get('signal_types') or []) and row.get('source_url') not in selected]
        refreshed=apply_reviewed_copy(exporter.curate(scoped,resolve_external=False))
        combined=sorted(retained+refreshed,key=lambda row:row.get('event_date') or '',reverse=True)
        payload=json.loads((root/'web/data/radar_today.json').read_text())
        payload.update(signals=combined,date=as_of.isoformat(),generated_at=observations['observed_at'])
        atomic_json(root/'web/data/radar_today.json',payload)
        atomic_json(root/'web/data/source_health.json',health)
        report['scoped_feed_refresh']=dict(preserved_other_rows=len(retained),refreshed_rows=len(refreshed),
            note='No source poll timestamp is updated by rebuilding the feed.')
        atomic_json(root/'data/audits/fiscalizacion/reconciliation_2026_10_11.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path('.'))
    parser.add_argument('--observations',type=Path,default=Path('data/audits/fiscalizacion/original_observations_2026_10_11.json'))
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    result=reconcile(args.root,json.loads(args.observations.read_text()),args.apply)
    print(json.dumps({'decisions':result['outcome_counts'],'coverage_complete':result['coverage_complete'],'native_validation':result['native_validation']},ensure_ascii=False))
