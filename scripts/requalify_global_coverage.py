"""Qualify the captured PAHO end protocol; preserve fresh and metadata history."""
import copy
import hashlib
import json
import os
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
if __package__:
    from .discover_global_sources import run,write,project_inventory_csv,mirror_health,coverage_contract_id
else:
    from discover_global_sources import run,write,project_inventory_csv,mirror_health,coverage_contract_id

END='date_partition_native_empty_after_clamped_numbered_end'
HEALTH_FIELDS={'coverage_status','outcome','coverage_completeness','window_completeness','boundary_evidence','source_quality_disposition','coverage_contract_id'}
def assert_coverage_projection(before,after):
    for field in ('as_of','run_id','items','editorial_topics','technical_failures','publication_count','default_window_days','maximum_editorial_topics'):
        if before[field]!=after[field]:raise ValueError('coverage projection changed immutable '+field)
    if after['mode']!='projection_replay' or after['network_requests'] or after['paid_ai_calls'] or after['publication_count']:
        raise ValueError('coverage projection exceeded read-only replay contract')
    if len(before['routes'])!=len(after['routes']):raise ValueError('route membership changed')
    closures=[]
    for a,b in zip(before['routes'],after['routes']):
        if a==b:continue
        if a['route']['source']!='paho' or not a.get('date_partitions'):raise ValueError('non-PAHO/date-partition route changed')
        if len(a['pages'])!=len(b['pages']) or len(a['date_partitions'])!=len(b['date_partitions']):raise ValueError('page/partition membership changed')
        cleaned=copy.deepcopy(b)
        proofs=[]
        for index,(old,new) in enumerate(zip(a['pages'],b['pages'])):
            proof=new.get('clamped_empty_native_pager')
            if proof:
                if index<1 or old['items'] or old['native_control'] or old['native_records']:raise ValueError('empty proof on a populated/initial page')
                prior=a['pages'][index-1];pager=prior.get('numbered_native_pager') or {}
                expected={'requested_page':pager.get('current',-1)+1,'clamped_current':pager.get('current'),'maximum':pager.get('maximum'),'terminal':True,'previous_page_url':prior['url']}
                if proof!=expected or not prior['items'] or not pager.get('terminal') or not 0<pager['current']==pager['maximum']<8:raise ValueError('clamped proof lacks verified previous terminal')
                proofs.append(old['url']);cleaned['pages'][index].pop('clamped_empty_native_pager')
        if not proofs:raise ValueError('coverage changed without captured empty end proof')
        changed=0
        for index,(old,new) in enumerate(zip(a['date_partitions'],b['date_partitions'])):
            if old==new:continue
            if old['archive_complete'] or old['stop_reason']!='date_partition_empty_unverified' or not new['archive_complete'] or new['stop_reason']!=END:raise ValueError('unexpected partition transition')
            cleaned['date_partitions'][index]['archive_complete']=old['archive_complete'];cleaned['date_partitions'][index]['stop_reason']=old['stop_reason'];changed+=1
        if changed!=len(proofs) or not all(p['archive_complete'] for p in b['date_partitions']) or not b['archive_complete'] or b['stop_reason']!='verified_date_partition_coverage':raise ValueError('coverage or end proofs do not reconcile')
        cleaned['archive_complete']=a['archive_complete'];cleaned['stop_reason']=a['stop_reason']
        if cleaned!=a:raise ValueError('coverage projection changed native pages, receipts, dates or control')
        closures.extend(proofs)
    if not closures:raise ValueError('no PAHO end protocol qualified')
    if set(before['source_health'])!=set(after['source_health']):raise ValueError('source membership changed')
    for source,old in before['source_health'].items():
        new=after['source_health'][source]
        if source!='paho':
            if new!=old:raise ValueError('unowned WHO/Reuters qualification changed')
            continue
        if {k:v for k,v in old.items() if k not in HEALTH_FIELDS}!={k:v for k,v in new.items() if k not in HEALTH_FIELDS}:raise ValueError('PAHO dates/counts/cadence/HTTP/provenance changed')
        if new['outcome']!='READY_FOR_INTEGRATION' or new['coverage_completeness']!='complete' or new['coverage_status']!='complete' or set(new['window_completeness'].values())!={'complete_on_declared_surfaces'} or new['source_quality_disposition']!='pass_data' or new['recurrent_operation_proven'] or new['publication_activation']:raise ValueError('unsupported coverage or operational promotion')
        config=json.loads((Path(__file__).resolve().parents[1]/'config/global_discovery.json').read_text())
        if new['coverage_contract_id']==old['coverage_contract_id'] or new['coverage_contract_id']!=coverage_contract_id(config,'paho'):raise ValueError('new protocol did not reset coverage contract precisely')
    return closures

def main(root,captures,qa_run):
    canonical=root/'data/global_intelligence/discovery.json';before=json.loads(canonical.read_text())
    if before['mode']!='projection_replay' or not before.get('metadata_projection') or before.get('coverage_projection'):raise ValueError('requires original metadata qualification, not an existing coverage projection')
    run_id=before['run_id'];base=Path('data/audits/global_source_recovery_2026_10_11/runs')/run_id;dest=base/'coverage_requalification'/qa_run
    if (root/dest).exists():raise ValueError('qualification receipt already exists')
    metadata=before['metadata_projection'];prior=root/metadata['inventory_ref']
    if canonical.read_bytes()!=prior.read_bytes():raise ValueError('canonical differs from qualified metadata history')
    protected=[root/p for p in ('data/global/themes.json','web/data/global_themes.json','data/global_intelligence/ledger.json','web/data/radar_today.json')]
    protected += [root/base/n for n in ('inventory.json','inventory.csv','capture_manifest.json')]+[prior,root/metadata['inventory_csv_ref'],prior.parent/'report.json']
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();hashes={str(p.relative_to(root)):digest(p) for p in protected}
    if digest(root/base/'inventory.json')!=metadata['fresh_inventory_sha256']:raise ValueError('original fresh inventory modified')
    with tempfile.TemporaryDirectory(prefix='global-coverage-qualification-',dir=root/'work') as temporary:
        scratch=Path(temporary)
        for name in ('config/global_discovery.json','data/global/themes.json','data/global_intelligence/ledger.json','data/global_intelligence/discovery.json'):
            target=scratch/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target)
        after=run(scratch,scratch/'captures',date.fromisoformat(before['as_of']),run_id,captures)
        for source in after['source_health']:
            after['source_health'][source]['new']=before['source_health'][source]['new']
            for k,v in before['source_health'][source].items():
                if k.startswith('materiality_'):after['source_health'][source][k]=v
        closures=assert_coverage_projection(before,after)
    stamp=datetime.now(timezone.utc).isoformat();after['generated_at']=before['generated_at'];after['metadata_projection']=metadata
    after['coverage_projection']={'qualified_at':stamp,'qa_run_id':qa_run,'code_commit':os.environ.get('GITHUB_SHA'),'fresh_capture_run_id':run_id,'fresh_inventory_sha256':metadata['fresh_inventory_sha256'],'metadata_inventory_ref':metadata['inventory_ref'],'metadata_inventory_sha256':digest(prior),'inventory_ref':str(dest/'inventory.json'),'inventory_csv_ref':str(dest/'inventory.csv'),'publisher_requests':0,'does_not_prove_fresh_capture_or_cadence':True}
    after['source_health']['paho']['coverage_evidence_ref']=str(dest/'inventory.json');after['source_health']['paho']['coverage_qualification_run_id']=qa_run
    after['source_health']['paho']['coverage_qualification_mode']='captured_byte_replay'
    after['source_health']['paho']['first_complete_fresh_capture_under_current_contract_pending']=True
    after['source_health']['paho']['cadence_validation_requires']='First complete fresh live capture under current contract, then a second at least 86400 seconds later. This projection is not a fresh cadence anchor.'
    for name in ('python_qa.json','browser_qa.json','replay.json','independent_capture_audit.json'):
        src=root/base/name;target=root/base/'metadata_qa'/metadata['qa_run_id']/name;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copyfile(src,target)
    write(root,dest/'inventory.json',after);write(root,'data/global_intelligence/discovery.json',after)
    write(root,'data/global_intelligence/source_health.json',{'sources':after['source_health']});project_inventory_csv(root,after);mirror_health(root,after['source_health'])
    if hashes!={str(p.relative_to(root)):digest(p) for p in protected}:raise ValueError('fresh/metadata/ledger/core/curated history changed')
    report={'result':'PASS_CAPTURED_COVERAGE_QUALIFICATION','fresh_capture_run_id':run_id,'qa_run_id':qa_run,'qualification_code_commit':os.environ.get('GITHUB_SHA'),'qualified_at':stamp,'network_requests':0,'paid_ai_calls':0,'publication_count':0,'fresh_and_metadata_inventories_preserved':True,'ledger_unchanged':True,'protected_sha256':hashes,'newly_qualified_empty_end_urls':closures,'counts_before':before['source_health']['paho']['counts'],'counts_after':after['source_health']['paho']['counts'],'health_before':before['source_health']['paho'],'health_after':after['source_health']['paho'],'inventory_ref':str(dest/'inventory.json'),'inventory_csv_ref':str(dest/'inventory.csv'),'canonical_inventory_sha256':digest(canonical)}
    write(root,dest/'report.json',report);print(json.dumps({k:report[k] for k in ('result','fresh_capture_run_id','qa_run_id','network_requests','counts_after')}))
if __name__=='__main__':
    run_id=os.environ.get('GITHUB_RUN_ID')
    if not run_id or not run_id.isdigit():raise ValueError('numeric isolated QA run required')
    main(Path(__file__).resolve().parents[1],Path('work/global-runtime-captures').resolve(),run_id)
