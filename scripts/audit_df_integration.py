"""Targeted DF integration review; reuse originals, never repeat the inventory.

Captures only explicit independent controls/official auxiliary surfaces. No model
calls and no publication decisions are made by this script.
"""
import argparse
import hashlib
import json
import re
from html import unescape
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree

from radar_salud.df_article import article_url, parse_df_article
from radar_salud.df_media_gate import material
from radar_salud.df_recovery import _remember
from radar_salud.df_resolution import defer_format
from radar_salud.history import load_history, save_history
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, atomic_json, lane
from radar_salud.scouts import fetch_html


def baseline_json(root, path):
    return json.loads(subprocess.check_output(['git', 'show', 'origin/staging:'+path], cwd=root))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture-controls', action='store_true')
    parser.add_argument('--resolve', action='store_true')
    parser.add_argument('--capture-publications',action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    branch = subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()
    if branch != 'codex/df-end-to-end-20261011':
        parser.error('Only the existing isolated DF branch is authorized')
    now = datetime.now(timezone.utc)
    audit_path = root/'data/audits/df_reconciliation_2026_10_11.json'
    audit = json.loads(audit_path.read_text())
    queue = PendingQueue(root/'data/state/pending_queue.json')
    history = load_history(root/'data/history/superintendencia_signals.json')
    baseline = baseline_json(root, 'data/history/superintendencia_signals.json')
    baseline = baseline.get('signals', baseline) if isinstance(baseline,dict) else baseline
    baseline_feed = baseline_json(root, 'web/data/radar_today.json')['signals']
    originals = audit['originals']
    cache_dir = root/'work/df-originals'
    cache_dir.mkdir(parents=True, exist_ok=True)
    controls = json.loads((root/'config/df_integration_controls.json').read_text())
    if args.resolve:
        for url,review in controls.get('publication_duplicate_pairs',{}).items():
            counterpart=next((r for r in history if r.get('source_url')==review['url'] and r.get('editorial_decision')!='reject'),None)
            if not counterpart:continue
            for row in history:
                if row.get('source_url')==url and row.get('df_duplicate_of')!=review['url']:
                    row['df_duplicate_review']=dict(at=now.isoformat(),basis=review['basis'],before_feed_visibility=row.get('feed_visibility'))
                    row['df_duplicate_of']=review['url']
        save_history(root/'data/history/superintendencia_signals.json',history)
    capture = {}; new_raw = []
    if args.capture_publications:
        for item in queue.items.values():
            if item.get('source')!='diario_financiero' or item['status']!='published':continue
            url=item['raw']['url']
            if url in originals:continue
            html=fetch_html(url);payload=html.encode();digest=hashlib.sha256(payload).hexdigest()
            (cache_dir/(digest+'.html')).write_bytes(payload);parsed=parse_df_article(html,url)
            originals[url]=dict(sha256=digest,fetch='ok',captured_at=datetime.now(timezone.utc).isoformat(),
                event_date=parsed['event_date'],evidence={k:v for k,v in parsed['metadata'].items() if k!='page_text'},
                readable_characters=len(parsed['metadata']['page_text']),article_excerpt=parsed['metadata']['page_text'][:1200])
        audit['originals']=originals;atomic_json(audit_path,audit)

    def read_original(url):
        original = originals.get(url, {})
        path = cache_dir/(str(original.get('sha256'))+'.html')
        if path.exists():
            payload = path.read_bytes()
            assert hashlib.sha256(payload).hexdigest() == original['sha256']
            return payload.decode('utf-8'), original
        return None, original

    surfaces = []
    if args.capture_controls:
        for url in controls['official_surfaces'] + controls['control_urls']:
            html, original = read_original(url)
            if html is None:
                try:
                    html = fetch_html(url)
                    payload = html.encode('utf-8'); digest = hashlib.sha256(payload).hexdigest()
                    (cache_dir/(digest+'.html')).write_bytes(payload)
                    parsed = parse_df_article(html,url)
                    original = dict(captured_at=datetime.now(timezone.utc).isoformat(),sha256=digest,fetch='ok',
                        event_date=parsed['event_date'], evidence={k:v for k,v in parsed['metadata'].items() if k!='page_text'},
                        readable_characters=len(parsed['metadata']['page_text']), article_excerpt=parsed['metadata']['page_text'][:1200])
                    originals[url] = original
                except Exception as exc:
                    surfaces.append(dict(url=url,fetch='error',error=type(exc).__name__,message=str(exc)))
                    continue
            parsed = parse_df_article(html,url)
            if url in controls['official_surfaces']:
                record = dict(url=url,original_sha256=original['sha256'],captured_at=original['captured_at'])
                if url.endswith('.xml'):
                    try:
                        tree = ElementTree.fromstring(html)
                        record['entries'] = [{'url':n.findtext('{*}loc'),
                            'publication_date':n.findtext('.//{*}publication_date')} for n in tree.findall('.//{*}url')]
                        record['entries_count'] = len(record['entries'])
                    except ElementTree.ParseError:
                        record['xml_parse_error'] = True
                elif url.endswith('robots.txt'):
                    record['advertised_sitemaps'] = re.findall(r'Sitemap:\s*(\S+)',html)
                else:
                    from radar_salud.df_inventory import DfListing
                    listing=DfListing();listing.feed(html)
                    record['primary_control_urls'] = list(dict.fromkeys(urljoin(url,h) for card in listing.primary_cards for h,t in card['links']))
                surfaces.append(record)
            else:
                already = any(article_url(i['raw']['url'])==article_url(url) for i in queue.items.values() if i.get('source')=='diario_financiero')
                record = dict(url=url,was_in_215_inventory=url in audit['originals'] and url not in controls['known_missing'],
                    already_in_queue=already,original_sha256=original['sha256'],publication_day=parsed['event_date'],
                    title=parsed['metadata']['article_title'],primary_characters=len(parsed['metadata']['page_text']),
                    metadata=parsed['metadata'],description=parsed['raw_text'])
                capture[url]=record
                if not already and parsed['event_date']:
                    new_raw.append(RawItem(source_slug='diario_financiero',source_name='Diario Financiero',source_type='press_high_trust',url=url,title=parsed['metadata']['article_title'],
                        event_date=parsed['event_date'],raw_text=parsed['raw_text'],metadata={**parsed['metadata'],
                        'original_sha256':original['sha256'],'original_captured_at':original['captured_at'],
                        'discovered_from':'independent_integration_control'}))
        if new_raw:
            watermark=json.loads((root/'data/state/discovery_watermarks.json').read_text()).get('diario_financiero')
            queue.discover('diario_financiero',new_raw,now=now,last_discovered_at=watermark,
                published_urls=[r['source_url'] for r in history if r.get('editorial_decision')!='reject'])

    resolution_path=root/'data/audits/df_retry_resolution_2026_10_11.json'
    prior=json.loads(resolution_path.read_text()) if resolution_path.exists() else {}
    remaining=[]
    target_keys=prior.get('original_40_fingerprints') or [k for k,i in queue.items.items() if i.get('source')=='diario_financiero' and i['status']=='retry']
    for key in target_keys:
        item=queue.items[key];raw=item['raw'];url=raw['url'];html,original=read_original(url)
        parsed=parse_df_article(html,url) if html is not None else None
        metadata=parsed['metadata'] if parsed else raw.get('metadata',{})
        date=parsed['event_date'] if parsed else raw.get('event_date')
        reason=item.get('reason')
        review=controls.get('retry_reviews',{}).get(url)
        if args.resolve and review and date and item['status'] in ('retry','deferred'):
            counterpart=review.get('duplicate_of')
            confirmed=not counterpart or any(r.get('source_url')==counterpart and r.get('editorial_decision')!='reject' for r in history)
            if confirmed:
                _remember(item,now,'individual_publisher_scope_or_event_duplicate_review')
                item.update(status='superseded' if counterpart else 'rejected',retry_at=None,
                    reason='duplicate_verified_df_event' if counterpart else 'df_unrelated_primary_multimedia_topic',
                    updated_at=now.isoformat(),df_resolution=review)
                if counterpart:item['duplicate_of']=counterpart
                else:
                    from radar_salud.scouts import SeenStore
                    SeenStore(root/'data/state/diario_financiero_seen.json').add_many([key])
        state=(item.get('df_resolution',{}).get('state') if item['status'] in ('rejected','superseded') else None) or ('RESOLVED_PUBLISHED' if item['status']=='published' else 'RESOLVED_REJECTED' if item['status']=='rejected' else 'RESOLVED_DUPLICATE' if item['status']=='superseded' else None)
        if state is None:
            state='RESOLVED_NO_VERIFIABLE_DATE' if not date else 'DEFERRED_MULTIMEDIA'
            reason='df_publication_date_conflict' if not date and metadata.get('publication_date_conflict') else 'df_missing_publication_date' if not date else 'df_image_only_requires_ocr' if metadata.get('primary_image_urls') else 'df_media_transcript_unavailable' if metadata.get('primary_media_urls') or '/podcast/' in url or '/videos/' in url else 'df_insufficient_article_evidence'
            if reason=='df_insufficient_article_evidence':state='RESOLVED_NO_VERIFIABLE_TEXT'
            if args.resolve:
                # Use a before snapshot even when only the publication date changes.
                if parsed and (raw.get('event_date')!=date or raw.get('metadata')!=metadata):
                    _remember(item,now,'targeted_original_format_and_date_review')
                    item['raw']={**raw,'event_date':date,'raw_text':parsed['raw_text'],
                        'metadata':{**raw.get('metadata',{}),**metadata}}
                    if date:item['lane']=lane(RawItem(**item['raw']),now,item.get('classification_watermark'))
                if not defer_format(item,reason,now):
                    resolution=dict(state=state,reason=reason,original_sha256=original.get('sha256'),
                        next_action='Resume only with verified publisher publication day and primary text')
                    if item.get('df_resolution')!=resolution:
                        _remember(item,now,'explicit_capture_debt_disposition')
                        item.update(status='deferred',reason=reason,retry_at=None,df_resolution=resolution,updated_at=now.isoformat())
        remaining.append(dict(fingerprint=key,url=url,title=metadata.get('article_title') or raw['title'],
            resolution=state,queue_status=item['status'],reason=reason,publication_day=date,
            original_sha256=original.get('sha256'),captured_at=original.get('captured_at'),
            date_evidence={k:v for k,v in metadata.items() if k.startswith('publication_')},
            primary_characters=len(metadata.get('page_text','')),images=metadata.get('primary_image_urls',[]),media=metadata.get('primary_media_urls',[]),
            description=parsed['raw_text'] if parsed else raw.get('raw_text'),
            media_markup=re.findall(r'.{0,300}<iframe\b[^>]*>.{0,300}',html or '',flags=re.I)[:6],
            equivalent_official_text=controls.get('equivalents',{}).get(url),
            reviewed_basis=item.get('df_resolution',{}).get('basis'),
            next_action=item.get('df_resolution',{}).get('next_action')))
    queue.save()
    if args.resolve:
        for url,repair in controls.get('reprocess_capture_defects',{}).items():
            for item in queue.items.values():
                if item.get('source')!='diario_financiero' or item['raw']['url']!=url:continue
                metadata=item['raw'].get('metadata',{})
                if (item['status']=='rejected' and item.get('reason')==repair['old_reason'] and
                        item['raw'].get('event_date') and material(metadata.get('article_title',''),metadata.get('page_text',''))
                        and not metadata.get('df_integration_reprocess_version')):
                    _remember(item,now,'verified_health_taxonomy_capture_defect')
                    metadata['df_integration_reprocess_version']=1
                    item.update(status='pending',reason=repair['basis'],retry_at=None,updated_at=now.isoformat())
        queue.save()
    atomic_json(resolution_path,dict(at=now.isoformat(),branch=branch,model_calls=0,
        original_40_fingerprints=target_keys,counts=dict(Counter(r['resolution'] for r in remaining)),items=remaining))
    undated_urls=prior.get('original_13_undated_urls') or [r['url'] for r in audit['matrix'] if not r['publication_day']]
    undated=[]
    for url in undated_urls:
        html,original=read_original(url);parsed=parse_df_article(html,url) if html else None
        meta=parsed['metadata'] if parsed else original.get('evidence',{})
        date=parsed['event_date'] if parsed else original.get('event_date')
        undated.append(dict(url=url,publication_day=date,
            resolution='RESOLVED_VERIFIED_DATE' if date else 'RESOLVED_IRRELEVANT' if url.endswith('.pdf') or re.search(r'/p/\d+$',url) else 'RESOLVED_NO_VERIFIABLE_DATE',
            evidence=meta,original_sha256=original.get('sha256'),
            canonical=meta.get('publisher_canonical_url'),jsonld_identity=meta.get('publisher_jsonld_identity'),
            investigation_order=['matching JSON-LD','article:published_time','cXense','primary visible header','canonical','publisher archive/listings','advertised sitemaps'],
            reason='Excluded PDF/commercial document/listing, no news publication identity' if not date and not meta.get('publication_date_candidates') else 'Original conflicting observations retained; primary label used only with matching story identity and primary body/media',
            sitemap_matches=[e for s in surfaces for e in s.get('entries',[]) if article_url(e.get('url') or '')==article_url(url)]))
    atomic_json(root/'data/audits/df_undated_resolution_2026_10_11.json',dict(at=now.isoformat(),original_13_undated_urls=undated_urls,items=undated))
    prior['original_13_undated_urls']=undated_urls
    resolution=json.loads(resolution_path.read_text());resolution['original_13_undated_urls']=undated_urls;atomic_json(resolution_path,resolution)
    publications=[]
    for key,item in queue.items.items():
        if item.get('source')!='diario_financiero' or item['status']!='published':continue
        raw=item['raw'];url=raw['url'];meta=raw.get('metadata',{});html,original=read_original(url)
        parsed=parse_df_article(html,url) if html else None
        body=parsed['metadata']['page_text'] if parsed else meta.get('page_text','')
        rows=[r for r in history if article_url(r.get('source_url',''))==article_url(url) and r.get('editorial_decision')!='reject']
        assessment=meta.get('editorial_assessment',{})
        parsed_metadata=parsed['metadata'] if parsed else meta
        header_title=parsed_metadata.get('primary_header_title')
        other_exact=[r['source_url'] for r in history if r.get('source_name')!='Diario Financiero' and r.get('editorial_decision')!='reject' and (article_url(r.get('source_url',''))==article_url(url) or (r.get('title','').casefold()==meta.get('article_title','').casefold() and r.get('event_date')==raw.get('event_date')))]
        publications.append(dict(fingerprint=key,url=url,date=raw.get('event_date'),title=meta.get('article_title'),lane=item['lane'],
            score=assessment.get('score'),category=rows[0].get('category') if rows else None,materiality=assessment.get('reason'),
            publication_reason=assessment,original_sha256=original.get('sha256'),captured_at=original.get('captured_at'),
            original_reparsed=parsed is not None,primary_body_matches=body==meta.get('page_text'),
            primary_header_title=header_title,publisher_jsonld_identity=parsed_metadata.get('publisher_jsonld_identity'),
            publisher_canonical_url=parsed_metadata.get('publisher_canonical_url'),
            title_matches_primary_header=bool(header_title) and unescape(header_title).casefold()==unescape(meta.get('article_title','')).casefold(),
            verified_primary_characters=len(body),material_gate=material(meta.get('article_title',''),body),
            date_matches_original=not parsed or parsed['event_date']==raw.get('event_date'),
            history_rows=len(rows),already_in_staging_history=any(article_url(r.get('source_url',''))==article_url(url) for r in baseline),
            already_in_staging_feed=any(article_url(r.get('source_url',''))==article_url(url) for r in baseline_feed),
            previous_defects=[o['action'] for o in item.get('recovery_observations',[])],
            cross_source_exact_duplicates=other_exact,
            cross_source_review=controls.get('publication_reviews',{}).get(url,'Reviewed primary story/decision; no identical other-source event in retained history'),
            canonical_event=controls.get('publication_duplicate_pairs',{}).get(url),
            primary_body_sha256=hashlib.sha256(body.encode()).hexdigest(),primary_excerpt=body[:400]))
    atomic_json(root/'data/audits/df_publications_review_2026_10_11.json',dict(at=now.isoformat(),count=len(publications),items=publications,
        semantic_dedupe_limitation='Explicit event review plus exact identity checks, not a global semantic dedupe guarantee'))
    if args.capture_controls:
        atomic_json(root/'data/audits/df_independent_controls_2026_10_11.json',dict(at=now.isoformat(),controls=capture,surfaces=surfaces,
            method=controls['method'],limitations=controls['limitations'],new_queue_urls=[r.url for r in new_raw]))
        audit['originals']=originals;atomic_json(audit_path,audit)
    print(json.dumps(dict(resolutions=dict(Counter(r['resolution'] for r in remaining)),publications=len(publications),
        dates_resolved=sum(bool(r['publication_day']) for r in undated),new_controls=len(new_raw))))


if __name__=='__main__':main()
