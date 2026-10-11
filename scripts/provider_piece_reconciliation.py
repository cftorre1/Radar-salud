"""Reconcile reviewed original pieces with each persisted Alicanto ledger.

This is read-only with respect to queue, history and paid decisions. Explicit
editorial decisions are required; missing reviews cannot become zero activity.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote,urlsplit,urlunsplit
from radar_salud.pending_queue import atomic_json

SLUGS=('redsalud','bupa_chile','indisa','red_davila','andes_salud','clinicas_chile','pfizer_chile','clinicas_achs_salud')

def canonical(url):
    p=urlsplit(unquote(str(url or '')))
    return urlunsplit((p.scheme,p.netloc.lower().removeprefix('www.'),p.path.rstrip('/'),p.query,''))

def reconcile_piece(item,decision,queue,seen,history,feed):
    urls={canonical(item['url']),*(canonical(u) for u in decision.get('aliases',[]))}
    queued=[{'key':k,'status':v['status'],'reason':v.get('reason'),'lane':v['lane'],
             'deferred_detail':v.get('deferred_detail'),'assessment':v['raw'].get('metadata',{}).get('editorial_assessment'),
             'current_editorial_review':v.get('current_editorial_review')}
            for k,v in queue.items() if v['source']==item['institution'] and canonical(v['raw']['url']) in urls]
    published=[r for r in history if canonical(r.get('source_url')) in urls and r.get('feed_visibility') is not False]
    shown=[r for r in feed if canonical(r.get('source_url')) in urls]
    fingerprint=hashlib.sha256(f"{item['institution']}|{item['url']}|{item['title']}".encode()).hexdigest()
    seen_match=fingerprint in seen or any(q['key'] in seen for q in queued)
    related_urls={canonical(u) for u in decision.get('related_to',[])}
    related=[{'url':r['source_url'],'title':r['title'],'publication_date':r.get('event_date')}
             for r in history if canonical(r.get('source_url')) in related_urls and r.get('feed_visibility') is not False]
    detected=bool(queued or seen_match or published or shown)
    current={**decision,'detected':detected,'queue':queued,'seen_ledger_match':seen_match,
        'history_count':len(published),'feed_count':len(shown),'related_published_signals':related,
        'alicanto_status':'published' if shown else queued[0]['status'] if len(queued)==1 else 'not_detected',
        'omitted':decision['materiality']=='candidate' and not detected and not related,
        'publication_count_role':'publisher_piece; aliases and related events are counted separately',
        'evidence':{'capture_date':item.get('capture_date'),'body_sha256':item.get('body_sha256'),
                    'date_stamps':item.get('date_stamps'),'date_reason':item.get('date_reason'),
                    'access_error':item.get('access_error')}}
    return current

def main():
    root=Path('.');read=lambda p:json.loads((root/p).read_text())
    decisions=read('data/audits/provider_editorial_decisions_2026_10_11.json')
    queue=read('data/state/pending_queue.json');history=read('data/history/superintendencia_signals.json')
    feed=read('web/data/radar_today.json')['signals'];health=read('data/source_health.json')
    result={'as_of':'2026-10-11','captured_at':datetime.now(timezone.utc).isoformat(),'sources':{},'promotion':'none'}
    for slug in SLUGS:
        inv_path=f'data/audits/provider_inventory_2026_10_11/{slug}.json';inv=read(inv_path)
        seen_path=root/f'data/state/{slug}_seen.json';seen=set(json.loads(seen_path.read_text())) if seen_path.exists() else set()
        for item in inv['items']:
            decision=decisions['pieces'].get(item['url'])
            if not decision:raise ValueError('Missing explicit editorial classification: '+item['url'])
            item.update(materiality=decision['materiality'],editorial_reason=decision['reason'],
                        event_date=decision.get('event_date'),reporting_period=decision.get('reporting_period'),
                        effective_date=decision.get('effective_date'))
            item['alicanto']=reconcile_piece(item,decision,queue,seen,history,feed)
        candidates=[x for x in inv['items'] if x['materiality']=='candidate']
        policy=decisions['sources'][slug]
        facets={**policy,'pages_checked':len(inv['requests']),'archive_depth':policy['archive_depth'],
            'latest_original_publication':inv.get('latest_original_at'),'discovered':inv['discovered'],'unique':inv['unique'],
            'recent_30d':sum(x.get('in_30_days') is True for x in inv['items']),
            'recent_90d':sum(x.get('in_90_days') is True for x in inv['items']),
            'publication_date_unknown':sum(not x.get('publication_date') and x['materiality']!='navigation' for x in inv['items']),
            'material_30d':sum(x.get('in_30_days') is True for x in candidates),
            'material_90d':sum(x.get('in_90_days') is True for x in candidates),
            'material_date_unknown':sum(not x.get('publication_date') for x in candidates),
            'published':sum(x['alicanto']['feed_count']>0 for x in candidates),
            'rejected':sum(x['alicanto']['alicanto_status']=='rejected' for x in candidates),
            'deferred':sum(x['alicanto']['alicanto_status'] in ('retry','pending') for x in candidates),
            'detected_material':sum(x['alicanto']['detected'] for x in candidates),
            'omitted_material':sum(x['alicanto']['omitted'] for x in candidates),
            'parse_errors':sum(x.get('reason')=='listing_parse_error' for x in inv['notes']),
            'access_errors':sum(bool(x.get('error')) for x in inv['requests']),
            'inventory':inv_path,'count_semantics':'verified original lower bounds where date/access blockers exist; unknown is never zero'}
        inv.update(coverage_complete=policy['coverage_complete'],coverage_reason=policy['coverage_reason'],outcome=policy['outcome'])
        atomic_json(inv_path,inv);result['sources'][slug]=facets
        h=health['sources'][slug];h['provider_coverage']=facets
        h.update(latest_original_at=facets['latest_original_publication'],coverage_status='observed' if policy['coverage_complete'] else 'unverified')
        if not policy['coverage_complete'] and h.get('status')=='ok':h['status']='warning'
    atomic_json('data/source_health.json',health)
    atomic_json('data/audits/provider_piece_reconciliation_2026_10_11.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
