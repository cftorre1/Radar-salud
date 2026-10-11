"""Requalify metadata from existing verified bytes; preserve the fresh inventory."""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
if __package__:
    from .discover_global_sources import run, write, project_inventory_csv, mirror_health
else:
    from discover_global_sources import run, write, project_inventory_csv, mirror_health

CLASSIFICATION_FIELDS={'classification','classification_evidence','classification_basis','status','reason','translation_members'}
HEALTH_FIELDS={'material_items','rejected','deferred'}

def assert_metadata_projection(before, after):
    for field in ('as_of','run_id','routes','technical_failures','publication_count','default_window_days','maximum_editorial_topics'):
        if before[field]!=after[field]:raise ValueError('projection changed immutable '+field)
    if after['mode']!='projection_replay':raise ValueError('projection cannot assert a fresh live capture')
    if after['network_requests'] or after['paid_ai_calls'] or after['publication_count']:
        raise ValueError('projection exceeded zero-network/AI/publication contract')
    old={r['url']:r for r in before['items']};new={r['url']:r for r in after['items']}
    if list(old)!=list(new):raise ValueError('projection changed identities or ordering')
    for url,row in old.items():
        updated=new[url]
        if {k:v for k,v in row.items() if k not in CLASSIFICATION_FIELDS}!={k:v for k,v in updated.items() if k not in CLASSIFICATION_FIELDS}:
            raise ValueError('projection changed immutable identity/date/evidence '+url)
        members=updated.get('translation_members',[])
        prior=row.get('translation_members',[])
        if len(prior)!=len(members):raise ValueError('projection changed translation membership')
        for a,b in zip(prior,members):
            if any(b.get(k)!=v for k,v in a.items() if k not in {'classification','section'}):
                raise ValueError('projection changed translation evidence '+url)
    if set(before['source_health'])!=set(after['source_health']):raise ValueError('projection changed source health membership')
    for source,health in before['source_health'].items():
        updated=after['source_health'][source]
        if source=='reuters':
            if updated!=health:raise ValueError('projection changed Reuters license hold or counts')
            continue
        if {k:v for k,v in health.items() if k not in HEALTH_FIELDS}!={k:v for k,v in updated.items() if k not in HEALTH_FIELDS}:
            raise ValueError('projection changed HTTP/date/coverage/cadence health '+source)
        rows=[r for r in after['items'] if r['source']==source]
        expected={'material_items':sum(r['detail_verified'] and bool(r['published_at']) and r['classification']['materiality']=='candidate' for r in rows),
                  'rejected':sum(r['status']=='rejected' for r in rows),'deferred':sum(r['status']=='pending' for r in rows)}
        if any(updated[k]!=v for k,v in expected.items()):raise ValueError('projection materiality/dispositions do not reconcile '+source)

def requalify(root, captures, qa_run):
    canonical=root/'data/global_intelligence/discovery.json';before=json.loads(canonical.read_text())
    if before['mode']!='live_discovery':raise ValueError('requalification requires the original fresh inventory, not a prior projection')
    run_id=before['run_id'];base=Path('data/audits/global_source_recovery_2026_10_11/runs')/run_id
    projection=base/'metadata_requalification'/qa_run
    if (root/projection).exists():raise ValueError('projection receipt already exists; do not overwrite history')
    protected=[root/p for p in ('data/global/themes.json','web/data/global_themes.json','data/global_intelligence/ledger.json','web/data/radar_today.json')]
    protected += [root/base/name for name in ('inventory.json','inventory.csv','capture_manifest.json')]
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    hashes={str(p.relative_to(root)):digest(p) for p in protected}
    if canonical.read_bytes()!=(root/base/'inventory.json').read_bytes():raise ValueError('canonical does not match the original fresh inventory')
    with tempfile.TemporaryDirectory(prefix='global-metadata-requalification-',dir=root/'work') as folder:
        scratch=Path(folder)
        for name in ('config/global_discovery.json','data/global/themes.json','data/global_intelligence/ledger.json','data/global_intelligence/discovery.json'):
            dest=scratch/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,dest)
        after=run(scratch,scratch/'captures',date.fromisoformat(before['as_of']),run_id,captures)
        # New-identity delta belongs to the fresh discovery, not to this projection.
        for source in after['source_health']:after['source_health'][source]['new']=before['source_health'][source]['new']
        assert_metadata_projection(before,after)
    differences=[{'url':a['url'],'before':a['classification'],'after':b['classification'],'before_status':a['status'],'after_status':b['status'],'provenance':b.get('classification_evidence',[])}
                 for a,b in zip(before['items'],after['items']) if a['classification']!=b['classification'] or a['status']!=b['status'] or a['reason']!=b['reason']]
    stamp=datetime.now(timezone.utc).isoformat()
    after['generated_at']=before['generated_at']
    after['metadata_projection']={'projected_at':stamp,'qa_run_id':qa_run,'code_commit':os.environ.get('GITHUB_SHA'),
        'fresh_capture_run_id':run_id,'fresh_inventory_ref':str(base/'inventory.json'),'fresh_inventory_sha256':hashes[str(base/'inventory.json')],
        'inventory_ref':str(projection/'inventory.json'),'inventory_csv_ref':str(projection/'inventory.csv'),
        'publisher_requests':0,'does_not_prove_fresh_capture_or_cadence':True}
    for source in ('who','paho'):
        after['source_health'][source]['materiality_evidence_ref']=str(projection/'inventory.json')
        after['source_health'][source]['materiality_projection_run_id']=qa_run
    for name in ('python_qa.json','browser_qa.json','replay.json','independent_capture_audit.json'):
        src=root/base/name;dest=root/base/'fresh_qa'/name
        if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    write(root,projection/'inventory.json',after)
    write(root,'data/global_intelligence/discovery.json',after)
    write(root,'data/global_intelligence/source_health.json',{'sources':after['source_health']})
    write(root,'data/global_intelligence/editorial_candidates.json',{'as_of':after['as_of'],'default_window_days':30,'maximum_topics':10,'topics':after['editorial_topics'],'publication_count':0})
    project_inventory_csv(root,after);mirror_health(root,after['source_health'])
    if hashes!={str(p.relative_to(root)):digest(p) for p in protected}:raise ValueError('projection modified protected fresh/core/curated evidence')
    report={'result':'PASS_METADATA_ONLY_PROJECTION','fresh_capture_run_id':run_id,'qa_run_id':qa_run,'projection_code_commit':os.environ.get('GITHUB_SHA'),
            'projected_at':stamp,'network_requests':0,'paid_ai_calls':0,'publication_count':0,'fresh_inventory_preserved':True,'ledger_and_curated_data_preserved':True,
            'protected_sha256':hashes,'immutable_checks':'identity, aliases, publication/index dates, routes/control, receipts, HTTP/coverage/cadence/new unchanged',
            'classification_changes':differences,'source_materiality':{s:{k:h[k] for k in ('material_items','rejected','deferred')} for s,h in after['source_health'].items()},
            'inventory_ref':str(projection/'inventory.json'),'inventory_csv_ref':str(projection/'inventory.csv'),'canonical_inventory_sha256':digest(canonical)}
    write(root,projection/'report.json',report)
    print(json.dumps({k:report[k] for k in ('result','fresh_capture_run_id','qa_run_id','network_requests','inventory_ref')}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--captures',type=Path,default=Path('work/global-runtime-captures'));parser.add_argument('--qa-run',default=os.environ.get('GITHUB_RUN_ID'));args=parser.parse_args()
    if not args.qa_run or not args.qa_run.isdigit():raise ValueError('numeric isolated QA run ID required')
    requalify(args.root.resolve(),args.captures.resolve(),args.qa_run)
