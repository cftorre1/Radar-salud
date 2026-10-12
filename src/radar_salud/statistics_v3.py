"""Deterministic calculation domains and adaptive presentation; no model calls."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import urlparse

def decimal(value):
    if value is None or isinstance(value,bool):raise ValueError('missing_or_invalid_value')
    try:out=Decimal(str(value))
    except InvalidOperation:raise ValueError('missing_or_invalid_value') from None
    if not out.is_finite():raise ValueError('missing_or_invalid_value')
    return out

def _compare(start,end,policy):
    """Observations must declare compatible units, universe, period scope and version.

    Decimal arithmetic never rounds inputs silently. Normalization, if needed,
    belongs to the parser and is recorded as provenance.
    """
    result={'absolute_delta':None,'relative_pct':None,'point_delta':None,'transition':None,
            'reason_code':None,'comparison_status':'HOLD','publication_status':'HOLD',
            'base_version_used':start.get('version'),'revision_delta':None}
    def hold(reason):
        result.update(absolute_delta=None,relative_pct=None,point_delta=None,transition=None,revision_delta=None,comparison_status='HOLD',publication_status='HOLD',reason_code=reason)
        return result
    for key in ('unit','scale','population','definition','period_scope'):
        if start.get(key) is None or end.get(key) is None or start[key]!=end[key]:return hold('incomparable_'+key)
    if not start.get('period') or not end.get('period'):return hold('missing_period')
    if not start.get('version') or not end.get('version'):return hold('missing_version')
    if start['version']!=end['version']:
        bridge=policy.get('revision_bridge') or {}
        if bridge.get('versions')!=[start['version'],end['version']] or not bridge.get('evidence_ref') or bridge.get('harmonized') is not True:
            return hold('HOLD_REVISED_BASE')
    for observation in (start,end):
        if not observation.get('locator') or not re.fullmatch(r'[0-9a-f]{64}',str(observation.get('source_hash') or '')):
            return hold('missing_input_provenance')
    try:
        a,b=decimal(start.get('value')),decimal(end.get('value'))
        if policy.get('requires_denominator') or policy.get('comparison_policy') in {'rate','proportion','margin'}:
            if any(decimal(x.get('denominator'))<=0 for x in (start,end)):return hold('invalid_denominator')
    except ValueError as exc:return hold(str(exc))
    domain=policy.get('value_domain');kind=policy.get('comparison_policy')
    if domain not in {'nonnegative','signed','proportion'} or kind not in {'proportional','financial_result','rate','proportion','margin','absolute_only'}:
        return hold('unregistered_policy')
    if kind=='proportion' and domain!='proportion' or kind in {'margin','financial_result'} and domain!='signed':return hold('invalid_policy_domain')
    if domain=='nonnegative' and (a<0 or b<0) or domain=='proportion' and not (0<=a<=1 and 0<=b<=1):return hold('invalid_domain')
    delta=b-a;result['absolute_delta']=str(delta);result['comparison_status']='PASS'
    if kind in {'proportion','margin'}:
        if start['scale'] not in {1,100}:return hold('invalid_point_scale')
        result['point_delta']=str(delta*(100 if start['scale']==1 else 1))
    if kind in {'financial_result','margin'}:
        if a<0<b:result['transition']='loss_to_profit' if kind=='financial_result' else 'negative_to_positive'
        elif a>0>b:result['transition']='profit_to_loss' if kind=='financial_result' else 'positive_to_negative'
        elif a<0 and b<0:result['transition']='smaller_loss' if b>a else 'larger_loss' if b<a else 'unchanged_loss'
        elif a<0 and b==0:result['transition']='loss_to_zero'
        elif a==0:result['transition']='zero_to_profit' if b>0 else 'zero_to_loss' if b<0 else 'unchanged_zero'
    if kind=='absolute_only' or policy.get('proportional_change_allowed') is not True:result['reason_code']='not_proportional'
    elif a==0:result['reason_code']='zero_base'
    elif a<0:result['reason_code']=result['transition'] if a<0<b else 'negative_base'
    elif kind in {'financial_result','margin'} and b<0:result['reason_code']=result['transition']
    else:result['relative_pct']=str(delta/a*100)
    if start.get('original_value') is not None:
        try:result['revision_delta']=str(a-decimal(start['original_value']))
        except ValueError:return hold('invalid_original_base')
    result['publication_status']='HOLD' if policy.get('hold_reason') else 'CALCULATION_ONLY'
    return result

def compare(start,end,policy):
    try:return _compare(start,end,policy)
    except (TypeError,ValueError,AttributeError,KeyError):
        return {'absolute_delta':None,'relative_pct':None,'point_delta':None,'transition':None,'revision_delta':None,
                'comparison_status':'HOLD','publication_status':'HOLD','reason_code':'invalid_comparison_schema','base_version_used':None}

def reconcile(values,total,*,unit,source_precision=None,tolerance=None):
    """Exact integers for counts; explicitly recorded tolerance for money."""
    try:parts=[decimal(v) for v in values];target=decimal(total)
    except ValueError as exc:return {'ok':False,'reason':str(exc)}
    if unit in {'personas','casos','contratos'}:
        if any(v<0 or v!=v.to_integral_value() for v in [*parts,target]):return {'ok':False,'reason':'invalid_count'}
        threshold=Decimal(0)
    else:
        if source_precision is None or tolerance is None:return {'ok':False,'reason':'missing_precision_policy'}
        threshold=decimal(tolerance)
        if threshold<0:return {'ok':False,'reason':'invalid_tolerance'}
    residual=sum(parts)-target
    return {'ok':abs(residual)<=threshold,'residual':str(residual),'tolerance':str(threshold),'source_precision':source_precision}

def _select_representation(dataset):
    """Choose after verified findings; missingness/contradictions never create charts."""
    profile=dataset.get('profile') or {};findings=dataset.get('finding_candidates') or []
    if dataset.get('hold_reason') or profile.get('contradictions'):
        return {'publication_status':'HOLD','reason':dataset.get('hold_reason') or 'conflicting_source','modules':[]}
    for field in ('family','unit','population','definition','period_scope','source_url','source_hash'):
        if not profile.get(field):return {'publication_status':'HOLD','reason':'missing_profile_'+field,'modules':[]}
    if profile.get('verified') is not True:return {'publication_status':'HOLD','reason':'unverified_profile','modules':[]}
    source=urlparse(str(profile['source_url']))
    if source.scheme!='https' or not source.netloc or not re.fullmatch(r'[a-f0-9]{64}',str(profile['source_hash'])):
        return {'publication_status':'HOLD','reason':'invalid_source_provenance','modules':[]}
    selected=[f for f in findings if f.get('verified') is True and f.get('material') is True and f.get('novel') is True and f.get('input_refs')]
    if not selected:return {'publication_status':'NO_SIGNAL','reason':'no_material_verified_finding','modules':[]}
    modules=[]
    for f in selected:
        kind=f.get('kind');observations=f.get('observations') or []
        if kind=='trend' and profile.get('complete_series') is True and len(observations)>=3:
            try:
                periods=[x['period'] for x in observations]
                valid=periods==sorted(set(periods)) and all(re.fullmatch(r'\d{4}-\d{2}',p) for p in periods)
                cuts=[int(p[:4])*12+int(p[5:]) for p in periods]
                valid=valid and all(1<=int(p[5:])<=12 for p in periods) and all(b-a==1 for a,b in zip(cuts,cuts[1:]))
                for x in observations:
                    decimal(x.get('value'))
                    valid=valid and bool(x.get('locator')) and x.get('source_hash')==profile['source_hash'] and x.get('unit')==profile['unit']
            except (ValueError,TypeError,KeyError):valid=False
            if not valid:return {'publication_status':'HOLD','reason':'invalid_or_incomparable_series','modules':[]}
            rep='line'
        elif kind in {'entity_gap','comparison'} and profile.get('comparable_entities') is True and profile.get('reconciled_totals') is True and observations:rep='table'
        elif kind=='magnitude' and observations:rep='kpi'
        elif kind=='distribution' and profile.get('verified_distribution') is True:rep='distribution'
        else:rep='text'
        modules.append({'id':f['id'],'representation':rep,'reason':f.get('incremental_value'),'finding':f})
    return {'publication_status':'REVIEW_REQUIRED','modules':modules}

def select_representation(dataset):
    try:return _select_representation(dataset)
    except (TypeError,ValueError,AttributeError,KeyError):return {'publication_status':'HOLD','reason':'invalid_dataset_schema','modules':[]}

def portfolio_view(validation):
    """Use already validated aggregates; entity comparisons require retained parser rows."""
    family=validation['families']['cartera'];series=family['series'];first,last=series[0],series[-1]
    def observation(row):return {'value':row['metrics']['beneficiarios'],'period':row['period'],'unit':'personas','scale':1,'population':'beneficiarios sistema Isapre','definition':'beneficios vigentes','period_scope':'stock mensual','version':family['sha256'],'source_hash':family['sha256'],'locator':row['sheet']+'!E20'}
    change=compare(observation(first),observation(last),{'value_domain':'nonnegative','comparison_policy':'proportional','proportional_change_allowed':True})
    if change['comparison_status']!='PASS':return {'publication_status':'HOLD','hold_reason':change['reason_code']}
    view={'family':'cartera','publication_status':'RECORDED_VALIDATION','unit':'personas','period_start':first['period'],'period_end':last['period'],'provisional':True,'complete_series_verified':True,
          'source_url':family['source_url'],'source_hash':family['sha256'],'comparison':change,
          'kpis':[{'label':'Beneficiarios','value':last['metrics']['beneficiarios'],'reference':last['period']},
                  {'label':'Cambio desde '+first['period'],'value':change['absolute_delta'],'reference':first['period']+' → '+last['period']},
                  {'label':'Variación relativa','value':change['relative_pct'],'unit':'%','reference':'Base '+str(first['metrics']['beneficiarios'])}],
          'series':[{'period':x['period'],'value':x['metrics']['beneficiarios'],'locator':x['sheet']+'!E20'} for x in series],
          'limitations':['Datos provisionales; personas con beneficios vigentes. La composición de cartera no prueba causalidad ni ingresos.'],
          'entities':[],'entity_status':'desglose no verificado','methodology':{'formula':'fin − inicio; relativa = 100 × (fin − inicio) / inicio','source_hash':family['sha256'],'source_url':family['source_url']}}
    profile={'family':'cartera','unit':'personas','population':'beneficiarios sistema Isapre','definition':'beneficios vigentes',
             'period_scope':'stock mensual','source_url':family['source_url'],'source_hash':family['sha256'],'verified':True,'complete_series':True}
    observations=[{**x,'source_hash':family['sha256'],'unit':'personas'} for x in view['series']]
    selection=select_representation({'profile':profile,'finding_candidates':[{'id':'portfolio-trend','kind':'trend','verified':True,
                  'material':decimal(change['absolute_delta'])!=0,'novel':True,'input_refs':[x['locator'] for x in observations],
                  'observations':observations,'incremental_value':'Trayectoria mensual comparable, sin inferir causalidad.'}]})
    view['chosen_representation']=selection
    view['complete_series_verified']=any(x['representation']=='line' for x in selection.get('modules',[]))
    sub=validation['families'].get('suscripciones') or {};mob=validation['families'].get('movilidad') or {}
    if sub.get('status')=='validated' and mob.get('status')=='validated' and sub.get('series') and mob.get('series'):
        contracts=sub['series'][-1];cuts=mob['series'][-1]
        view['additional_views']=[
            {'label':'Contratos · '+contracts['period'],'unit':'contratos','period':contracts['period'],'source_url':sub['source_url'],'source_hash':sub['sha256'],
             'limitation':'Desahucios voluntarios no incluyen todas las terminaciones; su diferencia no es cambio neto de cartera.',
             'rows':[{'label':'Suscripciones','value':contracts['metrics']['contratos_suscritos'],'locator':contracts['sheet']+'!C20'},
                     {'label':'Desahucios voluntarios','value':contracts['metrics']['desahucios_voluntarios'],'locator':contracts['sheet']+'!D20'}]},
            {'label':'Movilidad · cortes '+cuts['period_start']+' y '+cuts['period_end'],'unit':'cotizantes','period_start':cuts['period_start'],'period_end':cuts['period_end'],
             'source_url':mob['source_url'],'source_hash':mob['sha256'],'limitation':'Comparación entre cortes; no variación mensual ni conteo de todos los movimientos intermedios.',
             'rows':[{'label':'Entradas entre cortes','value':cuts['metrics']['entradas_intervalo'],'locator':'Nacional!D31'},
                     {'label':'Salidas entre cortes','value':cuts['metrics']['salidas_intervalo'],'locator':'Nacional!D19'}]}]
    # Only official code-matched rows with every component and exact system reconciliation.
    previous={str(x['code']):x for x in first.get('entities',[])};current=last.get('entities',[])
    if current and len(current)==len(previous) and {str(x['code']) for x in current}==set(previous):
        if all(sum(int(x[k]) for x in current)==last['metrics'][k] for k in ('cotizantes','cargas','beneficiarios')) and sum(int(x['beneficiarios']) for x in previous.values())==first['metrics']['beneficiarios']:
            for x in current:
                old=previous[str(x['code'])];a=observation(first);b=observation(last);a.update(value=old['beneficiarios'],population='isapre:'+str(x['code']),locator=old['locator']);b.update(value=x['beneficiarios'],population=a['population'],locator=x['locator']);calc=compare(a,b,{'value_domain':'nonnegative','comparison_policy':'proportional','proportional_change_allowed':True})
                if calc['comparison_status']!='PASS':view['entities']=[];break
                view['entities'].append({**x,'delta':calc['absolute_delta'],'relative_pct':calc['relative_pct'],'na_reason':calc['reason_code']})
            if len(view['entities'])==len(current):view['entity_status']='verified';view['system_total']=last['metrics'];view['missing_entity_ids']=[]
    return view
