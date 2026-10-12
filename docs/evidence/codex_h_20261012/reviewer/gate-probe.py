import json,sys,copy
sys.path.insert(0,'/workspace/work/codex-h/implementation/src')
from radar_salud.editorial_v3 import validate_depth,content_version
from radar_salud.statistics_v3 import compare,select_representation,portfolio_view
from radar_salud.normative_dates import legal_dates
out=[]
def emit(name,fn):
 try:r=fn();row={'name':name,'result':r}
 except Exception as e:row={'name':name,'error':type(e).__name__+': '+str(e)}
 out.append(row);print(json.dumps(row,ensure_ascii=False))
def valid():
 r={'piece_id':'piece:1','title':'Título factual','detail_body':'Dato adicional.','claims':[{'id':'c1','kind':'fact','text':'Dato adicional.','evidence_refs':['e1'],'adds_to':'title','incremental_value':'Añade dato'}],'evidence':[{'id':'e1','url':'https://example.org/original','locator':'p1','observed_at':'2026-10-12T10:00:00Z'}],'paragraph_claim_ids':{'0':['c1']},'review':{'author':'a','reviewer':'b','verdict':'PASS','claim_verdicts':{'c1':'SUPPORTED'},'paragraph_verdicts':{'0':{'verdict':'NEW','new_claim_ids':['c1']}}}}
 r['review']['content_version']=content_version(r);return r
def mutation(fn):
 r=valid();fn(r);r['review']['content_version']=content_version(r);return validate_depth(r)
emit('baseline',lambda:validate_depth(valid()))
emit('invalid_evidence_and_empty_claim',lambda:mutation(lambda r:(r['evidence'][0].update(url='https://',locator=' ',observed_at='invalid'),r['claims'][0].update(text=''))))
emit('module_unknown_evidence',lambda:mutation(lambda r:r.update(depth_modules=[{'id':'m1','label':'Módulo nuevo','claim_ids':['c1'],'evidence_refs':['missing']}])) )
emit('module_scalar_crash',lambda:mutation(lambda r:r.update(depth_modules=[17])))
emit('malformed_verdict_crash',lambda:mutation(lambda r:r['review'].update(claim_verdicts=['SUPPORTED'])))
emit('post_receipt_public_context_mutation',lambda:(lambda r,before:(r.update(event_date='2099-01-01',related_context=[{'title':'Contexto','summary':'Afirmación pública no sustentada.'}]),{'same_hash':before==content_version(r),'depth':validate_depth(r)})[1])(valid(),content_version(valid())))
emit('self_premise',lambda:mutation(lambda r:r['claims'][0].update(kind='hypothesis',premise_claim_ids=['c1'])))
def obs(value,period):return {'value':value,'unit':'proporción','scale':1,'population':'personas','definition':'partes sobre total','period_scope':'mes','period':period,'version':'v1','source_hash':'a'*64,'locator':'Sheet!A1','denominator':100}
a=obs('0.2','2026-01');b=obs('0.3','2026-02')
emit('proportion_denominator_missing',lambda:compare({k:v for k,v in a.items() if k!='denominator'},{k:v for k,v in b.items() if k!='denominator'},{'value_domain':'proportion','comparison_policy':'proportion','proportional_change_allowed':True}))
emit('proportion_signed_out_of_range',lambda:compare({**a,'value':'1.2'},{**b,'value':'1.5'},{'value_domain':'signed','comparison_policy':'proportion','proportional_change_allowed':True}))
emit('invalid_point_scale_keeps_pass',lambda:compare({**a,'scale':1000},{**b,'scale':1000},{'value_domain':'proportion','comparison_policy':'proportion','proportional_change_allowed':True}))
emit('invalid_original_base_keeps_numbers',lambda:compare({**a,'original_value':'S/I'},b,{'value_domain':'proportion','comparison_policy':'proportion','proportional_change_allowed':True}))
emit('unordered_duplicate_nonfinite_line',lambda:select_representation({'profile':{'verified':True,'family':'respiratoria','unit':'casos','population':'total','definition':'notificados','period_scope':'semana','source_url':'bad','source_hash':'bad','complete_series':True},'finding_candidates':[{'id':'f1','verified':True,'material':True,'novel':True,'input_refs':['bad'],'kind':'trend','observations':[{'period':'2026-02','value':'NaN'},{'period':'2026-01','value':4},{'period':'2026-01','value':5}]}]}))
emit('invalid_issued_date',lambda:legal_dates({'event_type':'SANCTION','issued_on':'invalid','event_date_basis':'verified_primary_emission','primary_document_review':{'primary_document_sha256':'bad','emission_date':'invalid'}}))
open('/workspace/work/codex-h/reviewer/gate-probe-results-'+(sys.argv[1] if len(sys.argv)>1 else 'run')+'.json','w').write(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
