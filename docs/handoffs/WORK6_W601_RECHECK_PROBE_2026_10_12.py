"""Independent documentary audit probe; NOT application code or a product gate.
Usage: python recheck_w601.py WORK5_EVIDENCE.json ORIGINALS_DIR OUTPUT.json
Requires xlrd and openpyxl only for the two previously downloaded originals.
"""
import json, sys, hashlib
from pathlib import Path
from decimal import Decimal as D, InvalidOperation
import xlrd, openpyxl

def evaluate(a, b, p):
    kind = p.get('kind', 'result')
    try:
        a, b = D(str(a)), D(str(b))
        if not a.is_finite() or not b.is_finite():
            raise InvalidOperation
    except InvalidOperation:
        return (None, None, None, 'missing_or_invalid')
    for flag, reason in [('revised_ok','HOLD_REVISED_BASE'),('comparable','incomparable'),('denominator_ok','invalid_denominator')]:
        if p.get(flag, True) is False:
            return (None, None, None, reason)
    if (kind in ('count','rate','proportion') and min(a,b)<0) or (kind=='proportion' and max(a,b)>1):
        return (None,None,None,'invalid_domain')
    delta = b-a
    pp = delta*100 if kind in ('margin','proportion') else None
    reason = None
    if not p.get('proportional', True): reason = 'nonproportional'
    elif a == 0: reason = 'zero_base'
    elif kind in ('result','margin') and a*b<0: reason = 'sign_change'
    elif a < 0: reason = 'negative_base'
    pct = None if reason else delta*100/a
    return delta,pct,pp,reason

def same(x,y):
    return x is None and y is None or x is not None and y is not None and x==D(str(y))

manifest, originals, output = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
j=json.loads(manifest.read_text())['w6_01_correction']
cases=j['test_results']['cases']
assert len(cases)==37 and len({c['id'] for c in cases})==37
results=[]
for c in cases:
    got=evaluate(*c['inputs'], c['policy'])
    for key,value in zip(('delta','pct','pp'),got[:3]):
        assert same(value,c['actual'][key]), (c['id'],key,got,c['actual'])
        assert same(value,c['expected_numeric'][key]), (c['id'],key,'expected mismatch')
    assert got[3]==c['actual']['reason'], (c['id'],'reason',got[3],c['actual'])
    results.append({'id':c['id'],'independent_numeric_reason_check':'PASS'})

# Work5's 15 categories are described, but its exact ephemeral inputs are not
# archived. These are new explicit Work6 examples, not a replay of that file.
extra=[
 ('near_zero_loss_profit','-.0001','.0001',{'kind':'result'},('.0002',None,None,'sign_change')),
 ('smaller_loss',-20,-1,{'kind':'result'},('19',None,None,'negative_base')),
 ('profit_loss',1,-2,{'kind':'result'},('-3',None,None,'sign_change')),
 ('zero_stock',0,8,{'kind':'count'},('8',None,None,'zero_base')),
 ('stock_to_zero',8,0,{'kind':'count'},('-8','-100',None,None)),
 ('proportion_down','.8','.4',{'kind':'proportion'},('-.4','-50','-40',None)),
 ('margin_negative_zero','-.05',0,{'kind':'margin'},('.05',None,'5','negative_base')),
 ('margin_over_one','1.2','1.5',{'kind':'margin'},('.3','25','30',None)),
 ('rate_down',20,5,{'kind':'rate'},('-15','-75',None,None)),
 ('unharmonized_revision',120,150,{'revised_ok':False},(None,None,None,'HOLD_REVISED_BASE')),
 ('invalid_source_denominator','.2','.3',{'kind':'proportion','denominator_ok':False},(None,None,None,'invalid_denominator')),
 ('incomparable_periods',10,15,{'comparable':False},(None,None,None,'incomparable')),
 ('arbitrary_index',100,120,{'kind':'index','proportional':False},('20',None,None,'nonproportional')),
 ('invalid_negative_count',-1,3,{'kind':'count'},(None,None,None,'invalid_domain')),
 ('nan',10,'NaN',{},(None,None,None,'missing_or_invalid')),
]
extra_results=[]
for name,a,b,p,want in extra:
    got=evaluate(a,b,p)
    assert all(same(x,y) for x,y in zip(got[:3],want[:3])) and got[3]==want[3], (name,got,want)
    extra_results.append({'id':name,'inputs':[a,b],'policy':p,'output':got,'result':'PASS'})
additional=[]
for name,a,b,p,want in [
 ('revised_base_zero',0,40,{'kind':'result'},('40',None,None,'zero_base')),
 ('positive_margin_relative','.05','.08',{'kind':'margin'},('.03','60','3',None)),
 ('relative_explicitly_disabled','.2','.3',{'kind':'proportion','proportional':False},('.1',None,'10','nonproportional')),
 ('rate_rescale',D('10')*100,1500,{'kind':'rate'},('500','50',None,None)),
]:
    got=evaluate(a,b,p)
    assert all(same(x,y) for x,y in zip(got[:3],want[:3])) and got[3]==want[3]
    additional.append({'id':name,'inputs':[a,b],'policy':p,'output':got,'result':'PASS'})

hashes={}
for n,h in [('fefi.xls','e3c4f7b3cfee9a6e4a3122aef4d0c65a26d41630e482c16ec4345b8a804db065'),('cartera.xlsx','bff79f5f67785da49e1e899d0a2f8c91479a1a14a33f205e4d9d0f0fddd1dbec')]:
    hashes[n]=hashlib.sha256((originals/n).read_bytes()).hexdigest()
    assert hashes[n]==h
f=xlrd.open_workbook(str(originals/'fefi.xls'))
s=f.sheet_by_name('Result. Financieros comparados')
a,b,delta=(D(str(s.cell_value(15,c))).quantize(D('.001')) for c in (1,3,5))
assert (a,b,delta)==(D('-273.285'),D('34090.653'),D('34363.938')) and b-a==delta
fefi_meta={pos:s.cell_value(r,c) for pos,r,c in [('A4',3,0),('B5',4,1),('D5',4,3),('A8',7,0)]}
fefi_note=f.sheet_by_name('Notas Explicativas').cell_value(17,0)
fefi=evaluate(a,b,{'kind':'result'})
assert fefi[0]==delta and fefi[1] is None
w=openpyxl.load_workbook(originals/'cartera.xlsx',data_only=True,read_only=True)
ca,cb=w['Enero']['E20'].value,w['Julio']['E20'].value
assert (ca,cb)==(2514038,2487497)
cartera=evaluate(ca,cb,{'kind':'count'})
assert cartera[0]==-26541
mutants=[('negative_base_naive_pct',100*(b-a)/a,None),('absolute_base_universal_fix',100*(b-a)/abs(a),None),('stock_end_denominator',D(100)*(cb-ca)/cb,cartera[1])]
assert all(not same(wrong,correct) for _,wrong,correct in mutants)
assert evaluate(120,150,{'kind':'count'})[1]==25 and D(120)-100==20
result={'scope':'Independent specification corroboration, not product implementation or replay of unavailable Work5 harness','candidate_sha':'a3e254d9ada6d2750787b416d7a9ee2253c08334','result':'PASS','reported_37':results,'reconstructed_15_categories':extra_results,'additional_boundary_checks':additional,'mutants':[{'name':n,'wrong':v,'correct':c,'detected':True} for n,v,c in mutants],'original_hashes':hashes,'fefi':{'period_unit_cells':fefi_meta,'values':[a,b,delta],'output':fefi,'coverage_note':fefi_note,'publication_status':'HOLD_COVERAGE_ESENCIAL'},'cartera':{'cells':'Enero!E20; Julio!E20','values':[ca,cb],'output':cartera},'revision_example':{'original':100,'revised':120,'end':150,'revision_delta':20,'temporal_delta':30,'temporal_pct':25},'source_harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
output.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+'\n')
print(json.dumps({'result':'PASS','reported_cases_verified':len(results),'independent_category_checks':len(extra_results),'additional_boundaries':len(additional),'mutants_detected':len(mutants),'fefi_metadata':fefi_meta,'original_hashes_verified':hashes},ensure_ascii=False))
