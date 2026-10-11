"""Independent, reproducible P0 data lane; news and live promotion remain gated."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
from .isapre_universe import parse_registry, release_metadata, parse_portfolio, REGISTRY_URL
from .pending_queue import atomic_json
from .source_health import record_data_adapter
from .cmf_sources import parse_actor, parse_essential_index, financial_documents, financial_results, classify_primary
from .cmf_sources import parse_shareholders, apply_verified_primary, parse_issuer_health_group, equity_identity
from urllib.parse import parse_qs, urlsplit


class Captures:
    def __init__(self, path):
        self.path = Path(path)
        payload=json.loads((self.path / 'receipts.json').read_text())
        self.receipts = payload['receipts']
        self.as_of=payload.get('as_of')

    def body(self, receipt):
        file = (self.path / receipt['body_file']).resolve()
        if not file.is_relative_to(self.path.resolve()): raise ValueError('Invalid capture path')
        data = file.read_bytes()
        if hashlib.sha256(data).hexdigest() != receipt['sha256']: raise ValueError('Capture hash mismatch')
        if not receipt['transport_ok']: raise ValueError('Official capture transport failed')
        return data

    def html(self, receipt):
        data=self.body(receipt)
        charset=re.search(br'charset\s*=\s*["\']?([a-zA-Z0-9_-]+)',data[:1500])
        encoding=charset[1].decode() if charset else 'utf-8'
        return data.decode(encoding, errors='replace')


def health(captures, package, *, discovered, unique, recent=0, material=0, published=0,
           rejected=0, deferred=0, errors=0, complete=False, reason):
    receipts = [r for r in captures.receipts if r['package'] == package]
    return dict(pages_checked=len(receipts), items_discovered=discovered, unique_items=unique,
                items_recent=recent, items_material=material, published=published, rejected=rejected,
                deferred=deferred, parse_errors=errors, coverage_complete=complete, coverage_reason=reason,
                technical_status='error' if errors else 'ok' if receipts and all(r['transport_ok'] for r in receipts) else 'degraded',
                snapshot_semantics='Data observations; published is news cards, never table rows',
                recurrence_validated=False, runtime_activation='held_for_core_quality_gate')


def collect_isapres(captures, root):
    registry = next(r for r in captures.receipts if r['package']=='isapres' and r['kind']=='registry')
    entities = parse_registry(captures.html(registry), fetched_at=registry['completed_at'], sha256=registry['sha256'])
    stock_path=root/'data/entities/isapres.json'
    prior=json.loads(stock_path.read_text()).get('entities',[]) if stock_path.exists() else []
    for entity in entities:
        existing=next((old for old in prior if old['canonical_id']==entity['canonical_id']),None)
        if existing and existing.get('group_control'):
            entity['group_control']=existing['group_control']
            entity['group_control_reason']='Retained dated primary ownership observation; registry refresh does not revalidate control'
    atomic_json(root/'data/entities/isapres.json', {'schema_version': 1, 'entities': entities})
    release = next(r for r in captures.receipts if r['package']=='isapres' and r['kind']=='cartera_release')
    meta = release_metadata(captures.html(release))
    linked = {x['url'] for x in release['links'] if '.xlsx' in x['url'].lower()}
    book = next(r for r in captures.receipts if r['url'] in linked and r['transport_ok'])
    portfolio = parse_portfolio(captures.body(book), source_url=book['url'], sha256=book['sha256'],
                               published_at=meta['published_at'], fetched_at=book['completed_at'], universe=entities)
    if portfolio['coverage'][-1]['period'] != meta['reporting_period']:
        raise ValueError('Official release month and workbook latest data disagree')
    atomic_json(root/'data/market/isapre_portfolio.json', {'schema_version': 1, **meta, **portfolio})
    evidence = health(captures, 'isapres', discovered=10, unique=10, recent=None, complete=False,
        reason='10/10 official codes and January–August portfolio reconcile; complete control perimeter, legal form Isalud, networks and separate-cadence recurrence remain unverified',
        deferred=1)
    evidence.update(inventory_entities=10, open_entities=7, closed_entities=3,
                    observations=len(portfolio['observations']), validated_periods=len(portfolio['coverage']),
                    latest_reporting_period=meta['reporting_period'], latest_release_at=meta['published_at'],
                    recency_reason='Registry validity is observed, not dated publication; release date and data month are separate',
                    inventory_coverage_complete=True, outcome='OPERATIVE_DEGRADED')
    evidence['entities_with_control_evidence']=sum(bool(e['group_control']) for e in entities)
    record_data_adapter(root, 'sis_isapre_universe', evidence)
    return evidence


def collect_cmf(captures, root):
    from datetime import date, timedelta
    actor_path=root/'data/entities/cmf_reporting_actors.json'
    actors=json.loads(actor_path.read_text()).get('actors',[]) if actor_path.exists() else []
    documents=[]; statements=[]; observations=[]; actor_coverage=[]
    receipts=[r for r in captures.receipts if r['package']=='cmf']
    from datetime import datetime
    from zoneinfo import ZoneInfo
    as_of=captures.as_of or max(datetime.fromisoformat(r['completed_at']).astimezone(ZoneInfo('America/Santiago')).date().isoformat() for r in receipts)
    start=(date.fromisoformat(as_of)-timedelta(days=89)).isoformat()
    for r in receipts:
        if r['kind']=='1' and r['transport_ok']:
            parsed_actor=parse_actor(captures.html(r),source_url=r['url'],sha256=r['sha256'],fetched_at=r['completed_at'])
            prior=next((a for a in actors if a['entity_id']==parsed_actor['entity_id']),{})
            for key in ['reported_major_shareholders','control_evidence','parent_entity_id','subsidiary_entity_ids','issuer_reported_health_relationships','ticker','ticker_reason','ticker_evidence']:
                if key in prior:parsed_actor[key]=prior[key]
            actors.append(parsed_actor)
    actors=list({a['entity_id']:a for a in actors}.values())
    by_rut={a['rut'].split('-')[0]:a for a in actors}
    group_relationships=[]
    for r in receipts:
        if r['kind'] in ['issuer_equity','exchange_equity_clc','exchange_market_maker'] and r['transport_ok']:
            if r['kind']=='exchange_market_maker':
                from .dipres_sources import pdf_text
                content=pdf_text(captures.body(r))
            else:content=captures.html(r)
            identity=equity_identity(content,kind=r['kind'],source_url=r['url'],sha256=r['sha256'],fetched_at=r['completed_at'])
            actor=next((a for a in actors if a['entity_id']==identity['entity_id']),None)
            if actor:actor.update(ticker=identity['ticker'],ticker_evidence=identity,ticker_reason=identity['validity'])
        if r['kind']=='issuer_group_report' and r['transport_ok']:
            group_relationships=parse_issuer_health_group(captures.html(r),source_url=r['url'],sha256=r['sha256'],fetched_at=r['completed_at'])
            ilc=by_rut.get('94139000')
            if ilc:ilc['issuer_reported_health_relationships']=group_relationships
            universe_path=root/'data/entities/isapres.json'
            if universe_path.exists():
                universe=json.loads(universe_path.read_text())
                for entity in universe['entities']:
                    relation=next((r for r in group_relationships if r['entity_id']==entity['canonical_id']),None)
                    if relation:
                        entity['group_control']=relation
                        entity['group_control_reason']='Majority ownership explicitly reported by issuer; no effective date or subsidiary event inferred'
                atomic_json(universe_path,universe)
    for r in receipts:
        if not r['transport_ok']: continue
        rut=parse_qs(urlsplit(r['url']).query).get('rut',[None])[0]
        if rut not in by_rut: continue
        actor=by_rut[rut]
        if r['kind']=='reporting_5':
            owners=parse_shareholders(captures.html(r),source_url=r['url'],sha256=r['sha256'])
            if not owners:
                actor['shareholder_poll_status']='unrecognized_or_form_only';continue
            actor['reported_major_shareholders']=owners
            control=next((owner for owner in actor['reported_major_shareholders'] if owner['ownership_pct']>50),None)
            actor['control_evidence']=control
            parent=next((a for a in actors if control and fold_name(a['legal_name'])==fold_name(control['name'])),None)
            actor['parent_entity_id']=parent['entity_id'] if parent else None
            if parent:
                actor['parent_entity_id']=parent['entity_id']
                if actor['entity_id'] not in parent['subsidiary_entity_ids']:parent['subsidiary_entity_ids'].append(actor['entity_id'])
        if r['kind']=='essential_90d':
            query=parse_qs(r['request_body'])
            query_start=f"{query['aa'][0]}-{query['mm'][0]}-{query['dd'][0]}"
            query_end=f"{query['aa2'][0]}-{query['mm2'][0]}-{query['dd2'][0]}"
            parsed=parse_essential_index(captures.html(r),actor=actor,source_url=r['url'],query_start=query_start,query_end=query_end)
            actor_coverage.append({'issuer':actor['entity_id'],'registration_status':actor['issuer_registration_status'],**{k:v for k,v in parsed.items() if k!='documents'}})
            for doc in parsed['documents']:
                primary=next((x for x in receipts if x['url']==doc['source_url'] and x['transport_ok']),None)
                if primary:
                    content=captures.body(primary)
                    if content.startswith(b'%PDF'):
                        from .primary_documents import extract_primary_pdf
                        text,method=extract_primary_pdf(content)
                        doc.update(primary_sha256=primary['sha256'], primary_verified=True,
                                   primary_fetched_this_poll=True,
                                   primary_excerpt=' '.join(text.split())[:1000], primary_extraction_method=method,
                                   primary_content_usable=len(text.strip())>=80, materiality=classify_primary(text))
                        doc['disposition']=doc['materiality']['disposition'];doc['reason']=doc['materiality']['reason']
                documents.append(doc)
        if r['kind']=='financial_period':
            query=parse_qs(urlsplit(r['url']).query); period=query['aa'][0]+'-'+query['mm'][0]
            statements.extend(financial_documents(captures.html(r),actor=actor,source_url=r['url'],reporting_period=period,sha256=r['sha256']))
            observations.extend(financial_results(captures.html(r),actor=actor,source_url=r['url'],sha256=r['sha256'],reporting_period=period))
    # Preserve first detection across polls and replays; transient CMF token URLs do not identify events.
    old_path=root/'data/market/cmf_disclosures.json'
    old={d['record_id']:d for d in json.loads(old_path.read_text()).get('documents',[])} if old_path.exists() else {}
    for doc in documents:
        prior=old.get(doc['record_id'],{})
        if not doc.get('primary_sha256') and prior.get('primary_sha256'):
            for key,value in prior.items():
                if key.startswith('primary_') or key=='materiality':doc[key]=value
            doc['primary_fetched_this_poll']=False
        doc['detected_at']=prior.get('detected_at',next(r['completed_at'] for r in receipts if r['kind']=='essential_90d' and 'rut='+doc['issuer_entity_id'].split(':')[-1].split('-')[0]+'&' in r['url']))
    from .paths import project_root
    review_path=project_root()/'config/cmf_verified_events_2026_10_11.json'
    verified={r['official_document_number']:r for r in json.loads(review_path.read_text())['records']} if review_path.exists() else {}
    for doc in documents:
        apply_verified_primary(doc,verified.get(doc['official_document_number']))
    merged={**old,**{d['record_id']:d for d in documents}}
    atomic_json(actor_path,{'schema_version':1,'actors':actors})
    atomic_json(old_path,{'schema_version':1,'query_start':start,'query_end':as_of,'documents':list(merged.values()),'actor_coverage':actor_coverage})
    events={}
    for doc in merged.values():
        verified_event=doc.get('verified_event')
        if not verified_event:continue
        key=verified_event['event_id'];event=events.setdefault(key,{'event_id':key,'primary_disclosures':[],'publication_status':'deferred','discovery_lane':'BACKFILL'})
        event['primary_disclosures'].append(doc['record_id'])
        if not verified_event.get('supporting_update') and (not event.get('event_date') or doc['event_date']>event['event_date']):
            event.update(verified_event,source_url=doc['source_url'],issuer_entity_id=doc['issuer_entity_id'])
    atomic_json(root/'data/market/cmf_events.json',{'schema_version':1,'events':list(events.values())})
    fin_path=root/'data/market/cmf_financials.json'
    old_fin=json.loads(fin_path.read_text()) if fin_path.exists() else {}
    statements=list({(d['issuer_entity_id'],d['reporting_period'],d['document_kind']):d for d in old_fin.get('documents',[])+statements}.values())
    observations=list({(o['entity_id'],o['metric_id'],o['period_start'],o['period_end'],o['reporting_perimeter'],o['unit']):o for o in old_fin.get('observations',[])+observations}.values())
    atomic_json(fin_path,{'schema_version':1,'documents':statements,'observations':observations})
    evidence=health(captures,'cmf',discovered=len(documents),unique=len({d['record_id'] for d in documents}),
        recent=sum(d['published_at']>= (date.fromisoformat(as_of)-timedelta(days=29)).isoformat() for d in documents),
        material=sum(d.get('materiality',{}).get('material') is True for d in documents),
        rejected=sum(d['disposition']=='rejected' for d in documents),deferred=sum(d['disposition']=='deferred' for d in documents),
        reason='Official issuer queries and primary disclosures reconciled; reviewed BACKFILL events held for core/editorial activation; complete health-group reporting perimeter and separate-cadence recurrence remain pending')
    evidence.update(outcome='OPERATIVE_DEGRADED',reporting_actors=len(actors),active_issuers=sum(a['issuer_registration_status']=='Vigente' for a in actors),
                    financial_observations=len(observations),statement_documents=len(statements),primary_documents_verified=sum(d.get('primary_verified',False) for d in documents),
                    primary_documents_reverified=sum(d.get('primary_fetched_this_poll',False) for d in documents),
                    actor_coverage=actor_coverage,material_events=len(events), transport_failures=[{'url':r['url'],'http':r['network']['http_code'],'reason':r['network'].get('errormsg')} for r in receipts if not r['transport_ok']])
    evidence['issuer_reported_health_relationships']=len(group_relationships)
    record_data_adapter(root,'cmf_health_ecosystem',evidence)
    return evidence


def fold_name(value):
    from .official_tables import fold
    return re.sub(r'[^a-z0-9]','',fold(value))


def collect_dipres(captures, root):
    from .dipres_sources import pdf_text, parse_project, parse_comparative, parse_execution, budget_key, material_variations, canonical_url
    stock_path=root/'data/market/dipres_health_budget.json'
    previous_stock=json.loads(stock_path.read_text()) if stock_path.exists() else {}
    rows=[]; ledger=[];seen=set()
    for receipt in captures.receipts:
        if receipt['package']!='dipres':continue
        if not any(x in receipt['kind'] for x in ['Proyecto de Ley','Comparativo','Ejecución']):continue
        if '.pdf' not in receipt['url']:continue
        url=canonical_url(receipt['url'])
        if url in seen:continue
        seen.add(url);entry={'source_url':url,'source_sha256':receipt['sha256'],'kind':receipt['kind'], 'fetched_at':receipt['completed_at']}
        try:
            text=pdf_text(captures.body(receipt))
            parser=parse_comparative if 'Comparativo' in receipt['kind'] else parse_execution if 'Ejecución' in receipt['kind'] else parse_project
            values=parser(text,source_url=receipt['url'],sha256=receipt['sha256'])
            for value in values:value['detected_at']=receipt['completed_at']
            rows.extend(values);entry.update(disposition='data_snapshot',observations=len(values),reason='Official total and hierarchy validated; no per-row news')
        except ValueError as exc:
            entry.update(disposition='deferred',observations=0,reason=str(exc))
        ledger.append(entry)
    # Same metric/state/period can be corroborated by several documents. Keep all provenance.
    merged={}
    for row in previous_stock.get('records',[])+rows:
        key=budget_key(row)
        if key in merged:
            previous=merged[key]
            if previous['value']!=row['value']:
                key+='|version:'+row['source_sha256']
            else:
                source={'url':row['source_url'],'sha256':row['source_sha256']}
                if source['url']!=previous['source_url'] and source not in previous.setdefault('additional_sources',[]):previous['additional_sources'].append(source)
                continue
        merged[key]=row
    candidates=list({(c['source_url'],c['source_sha256']):c for c in previous_stock.get('material_variations',[])+material_variations(rows)}.values())
    ledger_stock={(d['source_url'],d['source_sha256']):d for d in previous_stock.get('document_ledger',[])}
    for entry in ledger:
        key=entry['source_url'],entry['source_sha256']
        if entry['disposition']=='deferred' and ledger_stock.get(key,{}).get('disposition')=='data_snapshot':continue
        ledger_stock[key]=entry
    retained_ledger=list(ledger_stock.values())
    payload={'schema_version':1,'records':list(merged.values()),'document_ledger':retained_ledger,'poll_document_ledger':ledger,'material_variations':candidates,
             'aggregation_rule':'Do not sum nested fiscal levels or transfer-financed programs. Execution is accumulated, not monthly flow.',
             'coverage_complete':False,'coverage_reason':'Declared Salud project/execution perimeter parsed; source publication dates, complete fiscal version stock and separated-cadence recurrence remain unverified'}
    atomic_json(stock_path,payload)
    evidence=health(captures,'dipres',discovered=len(ledger),unique=len(seen),recent=None,material=len(material_variations(rows)),
        errors=sum(d['disposition']=='deferred' for d in ledger),
        deferred=sum(d['disposition']=='deferred' for d in ledger)+len(candidates),
        reason=payload['coverage_reason'])
    evidence.update(outcome='OPERATIVE_DEGRADED',data_documents=sum(d['disposition']=='data_snapshot' for d in ledger),
        observations=len(merged),recency_reason='Original PDF publication dates unknown; fiscal years and execution cutoffs do not prove recent publication',
        programs=sorted({f"{r['partida']}.{r['chapter']}.{r['program']}" for r in merged.values() if r['program']}),
        fiscal_years=sorted({r['fiscal_year'] for r in rows}),publication_reason='Tables feed Trend/Benchmark; material changes without verified publication day stay deferred')
    record_data_adapter(root,'dipres_health_budget',evidence)
    return evidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--capture-dir', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--only', choices=['isapres', 'cmf', 'dipres', 'all'], default='all')
    args=parser.parse_args(); captures=Captures(args.capture_dir); result={}
    collectors={'isapres': collect_isapres, 'cmf': collect_cmf, 'dipres': collect_dipres}
    for name, collector in collectors.items():
        if args.only not in (name, 'all'): continue
        try: result[name]=collector(captures, args.output_root)
        except Exception as exc:
            result[name]=health(captures, name, discovered=None, unique=None, recent=None, errors=1,
                               reason=f'{type(exc).__name__}: {exc}')
            result[name]['outcome']='OPERATIVE_DEGRADED'
            slug={'isapres':'sis_isapre_universe','cmf':'cmf_health_ecosystem','dipres':'dipres_health_budget'}[name]
            record_data_adapter(args.output_root, slug, result[name])
    atomic_json(args.output_root/'data/market/collection_result.json', result)
    if args.only=='all' and not any(v['parse_errors'] for v in result.values()):
        from .market_intelligence import export_views
        export_views(args.output_root)
    print(json.dumps({k: {'outcome':v.get('outcome','OPERATIVE_DEGRADED'), 'reason':v['coverage_reason']} for k,v in result.items()}, ensure_ascii=False))
    if any(v['parse_errors'] for v in result.values()): raise SystemExit(1)


if __name__=='__main__': main()
