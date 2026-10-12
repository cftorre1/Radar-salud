from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import pytest

from radar_salud.editorial_v3 import content_version,validate_depth,depth_diagnostics,editorial_route
from radar_salud.editorial_gate import publication_ready
from radar_salud.editorial_rules_v2 import validate_publication_contract
from radar_salud.statistics_v3 import compare,reconcile,select_representation,portfolio_view
from radar_salud.public_source_catalog import eligible,build_catalog
from radar_salud.normative_dates import legal_dates

def record():
    r={'editorial_schema_version':'3','piece_id':'synthetic:legal','title':'Resolución IF/N°1 rechaza reposición',
       'detail_body':'Aplica el artículo 57 porque no se acreditó daño irreparable.',
       'event_date':'2026-10-12','source_url':'https://example.org/resolution','source_name':'Prueba',
       'signal_types':['Legal'],'scopes':['Isapres'],
       'claims':[{'id':'c1','kind':'fact','text':'No se acreditó daño irreparable.','evidence_refs':['e1'],'adds_to':'title','incremental_value':'Fundamento cautelar'}],
       'evidence':[{'id':'e1','url':'https://example.org/resolution','locator':'resuelvo 2','observed_at':'2026-10-12T10:00:00Z'}],
       'paragraph_claim_ids':{'0':['c1']}}
    r['review']={'author':'writer','reviewer':'independent','verdict':'PASS','content_version':content_version(r),
                 'claim_verdicts':{'c1':'SUPPORTED'},'paragraph_verdicts':{'0':{'verdict':'NEW','new_claim_ids':['c1']}}}
    return r

def test_v3_support_and_depth_replace_length_and_why_template():
    r=record();assert validate_depth(r)['ok'];assert publication_ready(r)[0]
    assert validate_publication_contract(r)['status']=='pass'
    assert 'why_it_matters' not in r

def test_v3_publication_gate_preserves_signed_copy_and_rejects_invalid_validity():
    r=record();r['validity_text']='schema.org PropertyValue'
    r['review']['content_version']=content_version(r)
    before=deepcopy(r)
    assert validate_depth(r)['ok']
    assert publication_ready(r)==(False,'editorial_v3_invalid_validity',0)
    assert r==before and validate_depth(r)['ok']

@pytest.mark.parametrize('mutation,code',[
    (lambda r:r['review'].update(reviewer='writer'),'independent_review_required'),
    (lambda r:r.update(detail_body='Una paráfrasis nueva sin hecho adicional.'),'stale_review'),
    (lambda r:r['evidence'][0].update(locator='otro considerando'),'stale_review'),
    (lambda r:r['claims'][0].update(evidence_refs=['absent']),'unsupported_claim'),
    (lambda r:r['review']['claim_verdicts'].update(c1='UNSUPPORTED'),'unsupported_claim'),
    (lambda r:r['review'].update(verdict='REVISE',reason_codes=['no_incremental_information']),'no_incremental_information'),
    (lambda r:r['review']['paragraph_verdicts'].update({'0':{'verdict':'REDUNDANT'}}),'no_incremental_information'),
    (lambda r:r['claims'][0].update(kind='analysis',premise_claim_ids=[]),'unsupported_conclusion'),
    (lambda r:r.update(hold_reason='HOLD_SOURCE_METHOD'),'publication_hold')])
def test_v3_fail_closed_for_adversarial_receipts(mutation,code):
    r=record();mutation(r);assert code in validate_depth(r)['reason_codes'];assert not publication_ready(r)[0]

def test_paraphrase_is_rejected_by_independent_semantic_receipt_not_lexical_threshold():
    r=record();r['detail_body']='No acoge la reconsideración.';r['claims'][0]['text']=r['detail_body'];r['review']['content_version']=content_version(r)
    r['review'].update(verdict='REVISE',reason_codes=['no_incremental_information'])
    assert not validate_depth(r)['ok']
    valid=record();valid['detail_body']=valid['title']+'; aplica el artículo 57 por daño no acreditado.'
    valid['review']['content_version']=content_version(valid);assert validate_depth(valid)['ok']

def test_normalization_preserves_negation_and_signed_metrics():
    r=record();r['detail_body']='Resolución IF/N°1 acoge reposición';assert not depth_diagnostics(r)
    r.update(title='Cambio: -10',detail_body='Cambio: +10');assert not depth_diagnostics(r)

def test_circular_hypothesis_cannot_attest_its_own_premise():
    r=record();r['claims'][0].update(kind='hypothesis',premise_claim_ids=['c1']);r['review']['content_version']=content_version(r)
    assert 'unsupported_conclusion' in validate_depth(r)['reason_codes']

def obs(value,**fields):
    return {'value':value,'unit':'personas','scale':1,'population':'sistema','definition':'stock vigente','period_scope':'stock mensual',
            'period':'2026-01','version':'v2','source_hash':'a'*64,'locator':'Enero!E20',**fields}

POLICY={'value_domain':'signed','comparison_policy':'financial_result','proportional_change_allowed':True}
@pytest.mark.parametrize('start,end,delta,relative,transition',[
    ('-273.285','34090.653','34363.938',None,'loss_to_profit'),
    (-100,-40,'60',None,'smaller_loss'),(-100,-160,'-60',None,'larger_loss'),
    (-100,-100,'0',None,'unchanged_loss'),(-100,0,'100',None,'loss_to_zero'),
    (0,100,'100',None,'zero_to_profit'),(0,-10,'-10',None,'zero_to_loss'),
    (0,0,'0',None,'unchanged_zero'),(100,-10,'-110',None,'profit_to_loss'),
    (100,0,'-100','-100',None),(100,150,'50','50',None)])
def test_financial_domains(start,end,delta,relative,transition):
    out=compare(obs(start),obs(end,period='2026-07'),POLICY)
    assert Decimal(out['absolute_delta'])==Decimal(delta) and (out['relative_pct'] is None if relative is None else Decimal(out['relative_pct'])==Decimal(relative)) and out['transition']==transition

def test_real_cartera_uses_initial_base_and_fefi_math_does_not_remove_hold():
    p={'value_domain':'nonnegative','comparison_policy':'proportional','proportional_change_allowed':True}
    out=compare(obs(2514038),obs(2487497,period='2026-07'),p)
    assert out['absolute_delta']=='-26541';assert Decimal(out['relative_pct'])==Decimal(-26541)/Decimal(2514038)*100
    fefi=compare(obs('-273.285'),obs('34090.653',period='2026-07'),{**POLICY,'hold_reason':'HOLD_COVERAGE_ESENCIAL'})
    assert fefi['comparison_status']=='PASS' and fefi['publication_status']=='HOLD'

@pytest.mark.parametrize('value',[None,'S/I','NA','NaN','Infinity',True])
def test_missing_and_nonfinite_never_become_zero(value):
    out=compare(obs(value),obs(10),POLICY);assert out['absolute_delta'] is None and out['relative_pct'] is None

@pytest.mark.parametrize('field',['unit','scale','population','definition','period_scope','version'])
def test_comparability_blocks_absolute_and_relative(field):
    out=compare(obs(100),obs(150,**{field:'different'}),POLICY)
    assert out['comparison_status']=='HOLD' and out['absolute_delta'] is None and out['relative_pct'] is None

def test_rates_proportions_margins_and_revisions_keep_distinct_units():
    prop={'value_domain':'proportion','comparison_policy':'proportion','proportional_change_allowed':True,'requires_denominator':True}
    out=compare(obs('.2',denominator=100),obs('.3',denominator=100),prop)
    assert Decimal(out['point_delta'])==10 and Decimal(out['relative_pct'])==50
    margin={**POLICY,'comparison_policy':'margin'}
    out=compare(obs(-5,scale=100,denominator=100),obs(3,scale=100,denominator=100),margin);assert out['point_delta']=='8' and out['relative_pct'] is None
    out=compare(obs(120,scale=100,denominator=100),obs(130,scale=100,denominator=100),margin);assert out['comparison_status']=='PASS'
    rate={**POLICY,'value_domain':'nonnegative','comparison_policy':'rate','requires_denominator':True}
    out=compare(obs(10,denominator=100000),obs(15,denominator=100000),rate);assert out['absolute_delta']=='5' and out['point_delta'] is None
    assert compare(obs(10,denominator=0),obs(15,denominator=100000),rate)['reason_code']=='invalid_denominator'
    revised=compare(obs(120,original_value=100),obs(150,version='v3'),{**POLICY,'revision_bridge':{'versions':['v2','v3'],'evidence_ref':'revision-note','harmonized':True}})
    assert revised['absolute_delta']=='30' and revised['relative_pct']=='25.00' and revised['revision_delta']=='20'

def test_precision_counts_and_money_have_explicit_residuals():
    assert not reconcile([1,2],4,unit='personas')['ok']
    assert reconcile(['-273.28500000000076','34363.938'],34090.653,unit='CLP millones',source_precision='0.001',tolerance='0.000000001')['ok']
    assert not reconcile([100,50],151,unit='CLP millones',source_precision='0.001',tolerance='0.001')['ok']

def test_selector_is_adaptive_and_does_not_invent_charts_or_publish_holds():
    profile={'family':'synthetic','unit':'personas','population':'sistema','definition':'stock','period_scope':'mensual','source_url':'https://example.org','source_hash':'a'*64,'verified':True}
    f={'id':'f1','verified':True,'material':True,'novel':True,'input_refs':['e1'],'kind':'methodology_change','incremental_value':'Nueva definición publicada'}
    out=select_representation({'profile':profile,'finding_candidates':[f]});assert out['modules'][0]['representation']=='text'
    assert select_representation({'profile':profile,'finding_candidates':[]})['publication_status']=='NO_SIGNAL'
    assert not select_representation({'profile':profile,'finding_candidates':[f],'hold_reason':'HOLD_COVERAGE_ESENCIAL'})['modules']

def test_actual_respiratory_se37_contradiction_stays_held_without_cartera_template():
    import json
    from pathlib import Path
    dataset=json.loads(Path('data/epidemiology/respiratory_pressure_2026.json').read_text())
    assert dataset['epidemiological_week']==37
    assert '53,7%' in dataset['risk_notes'][0] and '56,7%' in dataset['risk_notes'][0]
    selected=select_representation({'profile':{'family':'respiratory_positivity','contradictions':[dataset['risk_notes'][0]]},
                                    'hold_reason':'HOLD_CONTRADICTORY_INDICATOR','finding_candidates':[]})
    assert selected=={'publication_status':'HOLD','reason':'HOLD_CONTRADICTORY_INDICATOR','modules':[]}

def test_catalog_is_sanitized_and_does_not_accept_bad_future_or_unknown_dates():
    now=datetime(2026,10,12,tzinfo=timezone.utc);r={'name':'Minsal','technical_status':'ok','coverage_status':'observed','checked_at':'2026-10-11T10:00:00Z'}
    assert eligible(r,now)
    for bad in ['invalid','2099-01-01T00:00:00Z','2026-10-11']:
        assert not eligible({**r,'checked_at':bad},now)
    for blocked in ['paused','blocked','unverified','not_permitted']:
        assert not eligible({**r,'coverage_status':blocked},now)
    catalog=build_catalog({'minsal':r,'fonasa':{**r,'status':'error'}},now)
    assert len(catalog['sources'])==1
    assert set(catalog['sources'][0])=={'id','name','group','url','description'}

def test_sanction_dates_require_primary_issuance_and_keep_other_dimensions():
    r={'event_type':'SANCTION','emission_date':'2026-09-22','publication_date':'2026-10-02','fact_period':'2025','inspection_date':'2025-06-01'}
    assert legal_dates(r)['event_date'] is None and legal_dates(r)['hold_reason']=='HOLD_DATE'
    r.update(event_date_basis='verified_primary_emission',primary_document_review={'emission_date':'2026-09-22','primary_document_sha256':'a'*64})
    out=legal_dates(r);assert out['event_date']=='2026-09-22' and out['published_on']=='2026-10-02' and out['fact_period']=='2025'

def test_no_paid_calls_default_receipt_reuse_and_powerful_route_needs_reserve():
    r=record();assert not editorial_route(r)['paid_call'];assert editorial_route(r,valid_receipt=True)['route']=='reuse_receipt'
    r['legal_conflict']=True;assert editorial_route(r,paid_authorized=True,powerful_model='approved')['route']=='HOLD'

def test_export_gives_approved_same_piece_precedence_without_rewriting_or_duplicate():
    from scripts.export_web_snapshot import curate,preserve_v3_copy
    r=record();legacy={**r,'editorial_schema_version':'2','what_happened':'La resolución confirma el rechazo del recurso con alcance específico.',
                      'why_it_matters':'La fuente acredita un efecto material para los sujetos identificados.'}
    output=curate([legacy,r,r],resolve_external=False)
    assert len(output)==1 and output[0]['piece_id']==r['piece_id']
    copied=preserve_v3_copy(output)
    assert content_version(copied[0])==r['review']['content_version']

def test_signed_browser_fixture_keeps_valid_receipt_with_conflicting_legacy_copy():
    import json
    from pathlib import Path
    from scripts.export_web_snapshot import curate,preserve_v3_copy
    r=json.loads(Path('tests/fixtures/signed_editorial_v3.json').read_text())
    version=r['review']['content_version']
    for key in ('card_what','card_why','what_happened','why_it_matters','normative_subject'):
        r[key]='Resolución IF/N°1 acoge reposición y levanta la sanción.'
    assert content_version(r)==version and validate_depth(r)['ok']
    assert publication_ready(r)[0]
    output=preserve_v3_copy(curate([r],resolve_external=False))
    assert len(output)==1 and output[0]['depth_gate']['ok']
    assert output[0]['title']=='Resolución IF/N°1 rechaza reposición'
    assert content_version(output[0])==version
