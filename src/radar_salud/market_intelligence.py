"""Comparable consumers for the source-expansion snapshots; no synthetic news."""
import json
import hashlib
from pathlib import Path
from .isapre_universe import portfolio_benchmark
from .pending_queue import atomic_json


def build_views(root):
    root=Path(root)
    def load(name):
        path=root/'data/market'/name
        return json.loads(path.read_text()) if path.exists() else {}
    portfolio=load('isapre_portfolio.json');financial=load('cmf_financials.json');budget=load('dipres_health_budget.json')
    period=portfolio.get('reporting_period')
    comparisons=[]
    records=portfolio.get('observations',[])
    for current in records:
        if current['period']!=period or current['metric_id']!='beneficiarios':continue
        prior=sorted([r for r in records if r['entity_id']==current['entity_id'] and r['metric_id']=='beneficiarios'
                      and r['population']==current['population'] and r['period']<period],key=lambda r:r['period'])
        if not prior:continue
        previous=prior[-1]
        comparisons.append({'entity_id':current['entity_id'],'previous_period':previous['period'],'current_period':period,
                            'delta':current['value']-previous['value'],'population':current['population'],
                            'source_url':current['source_url'],'source_sha256':current['source_sha256'],
                            'interpretation':'Observed stock change; no causal or income claim'})
    financial_results=[]
    for current in financial.get('observations',[]):
        year=int(current['period_end'][:4])
        if current['metric_id']!='revenue' or current['period_start']!=f'{year}-01-01':continue
        # Prior-year columns are corroboration, never a second current observation.
        if any(r['entity_id']==current['entity_id'] and r['metric_id']==current['metric_id']
               and r['period_end'][5:]==current['period_end'][5:] and r['period_end']>current['period_end']
               and r['unit']==current['unit'] and r['reporting_perimeter']==current['reporting_perimeter']
               for r in financial['observations']):continue
        peers=[r for r in financial['observations'] if r['entity_id']==current['entity_id'] and r['metric_id']==current['metric_id']
               and r['period_start']==f'{year-1}-01-01' and r['period_end'][5:]==current['period_end'][5:]
               and r['unit']==current['unit'] and r['reporting_perimeter']==current['reporting_perimeter']]
        if peers and peers[0]['value']:
            financial_results.append({'entity_id':current['entity_id'],'metric_id':'revenue','period_end':current['period_end'],
                'pct_change':round((current['value']/peers[0]['value']-1)*100,4),'source_url':current['source_url'],
                'unit':current['unit'],'perimeter':current['reporting_perimeter'],
                'caveat':'Same issuer/interval only; parent performance is not subsidiary performance'})
    return {'schema_version':1,'news_generation':'none_per_row','benchmark':{
        'isapres':{'period':period,'open':portfolio_benchmark(records,period=period,cohort='open'),
                   'closed':portfolio_benchmark(records,period=period,cohort='closed')},
        'cmf':{'observations':financial.get('observations',[]),'cross_entity_ranking':False},
        'dipres':{'observations':budget.get('records',[]),'aggregation_rule':budget.get('aggregation_rule')}},
        'trend':{'isapre_stock_changes':comparisons,'cmf_same_issuer_results':financial_results,
                 'budget_allocation_changes':budget.get('material_variations',[])},
        'global_promotion':'No Chile trend promotion from a global theme or a fiscal row; canonical Trend rules unchanged'}


def export_views(root):
    """Executable consumer contract for integration; candidates require editorial acceptance."""
    root=Path(root)
    views=build_views(root)
    atomic_json(root/'data/market/market_intelligence.json',views)
    path=root/'data/market/cmf_events.json'
    events=json.loads(path.read_text()).get('events',[]) if path.exists() else []
    candidates=[dict(candidate_id=e['event_id'],source_slug='cmf_health_ecosystem',
                     title=e['what_happened'],primary_source_url=e['source_url'],
                     event_date=e['event_date'],issuer_entity_id=e['issuer_entity_id'],
                     entity_scope='issuer',discovery_lane='BACKFILL',status='deferred',
                     reason=e['publication_reason'],verified_event=e)
                for e in events if not e.get('supporting_update')]
    candidates.extend(dict(candidate_id='dipres:'+hashlib.sha256(json.dumps(variation,sort_keys=True).encode()).hexdigest()[:24],source_slug='dipres_health_budget',
                           status='deferred',discovery_lane='BACKFILL',evidence=variation)
                      for variation in views['trend']['budget_allocation_changes'])
    atomic_json(root/'data/market/signal_candidates.json',{'schema_version':1,
                'activation':'editorial_and_core_gates_required','candidates':candidates})
    return views
