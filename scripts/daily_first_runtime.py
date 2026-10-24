"""Bounded official daily-recovery capture; no AI or operational writes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
from email.message import Message
import shutil
import zipfile
import os
from pathlib import Path
import subprocess

from recover_public_sources_runtime import probe, tls_diagnostic, now

ROOT = Path(__file__).resolve().parents[1]


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('data/history','data/ai_usage','data/analysis_cache')
            for p in (root/folder).rglob('*') if p.is_file()}


def replay_core(output, captures, *, live=False, assess=False):
    """Run the actual core in an isolated data root; publication is disabled."""
    from radar_salud import engine_cli, public_source_transport as transport
    import sys
    isolated = output/'isolated'
    isolated.mkdir(parents=True,exist_ok=True)
    for directory in ('config','data/state','data/history','data/ai_usage','data/analysis_cache'):
        shutil.copytree(ROOT/directory,isolated/directory,dirs_exist_ok=True)
    shutil.copyfile(ROOT/'data/source_health.json',isolated/'data/source_health.json')
    before_queue=json.loads((isolated/'data/state/pending_queue.json').read_text())
    before_health=json.loads((isolated/'data/source_health.json').read_text())
    history_path=isolated/'data/history/superintendencia_signals.json'
    before_history=json.loads(history_path.read_text())
    usage_path=isolated/'data/ai_usage/2026-10.json'
    usage_before=json.loads(usage_path.read_text())
    responses_path=isolated/'data/ai_usage/responses.jsonl'
    responses_before=responses_path.read_bytes()
    protected=snapshot(isolated)
    captured=[]
    original=transport._download_official
    def download(url,slug,**kwargs):
        if slug != 'minsal':raise ValueError('Runtime is scoped to MINSAL')
        if live:
            metadata={}; kwargs['capture_metadata']=metadata
            result=original(url,slug,**kwargs)
            body=result[0]; digest=hashlib.sha256(body).hexdigest()
            path=output/'captures'/(digest+'.html');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
            captured.append(dict(metadata,body_path=str(path.relative_to(output))))
            return result
        row=next(r for r in captures if r['url']==url)
        body=(output/row['body_path']).read_bytes()
        if hashlib.sha256(body).hexdigest()!=row['sha256']:raise ValueError('Capture hash mismatch')
        content_type=row.get('content_type') or next((v for k,v in row.get('headers',{}).items() if k.lower()=='content-type'),'text/html; charset=utf-8')
        headers=Message();headers['Content-Type']=content_type
        return body,headers
    transport._download_official=download
    old_argv=sys.argv; old_root=os.environ.get('RADAR_ROOT')
    os.environ['RADAR_ROOT']=str(isolated)
    sys.argv=['engine_cli','--source','minsal','--discovery-only']
    try:
        engine_cli.main()
        first=json.loads((isolated/'data/state/pending_queue.json').read_text())
        first_health=json.loads((isolated/'data/source_health.json').read_text())
        if live:
            captures=captured.copy();live=False
        if assess:
            # Capture is already verified; assess only four existing pending records.
            sys.argv=['engine_cli','--source','minsal','--limit','4']
            engine_cli.main()
            first=json.loads((isolated/'data/state/pending_queue.json').read_text())
            first_health=json.loads((isolated/'data/source_health.json').read_text())
            if captured:
                actual=max(r['captured_at'] for r in captured)
                first_health['sources']['minsal'].update(checked_at=actual,last_attempt_at=actual,
                    engine_checked_at=actual,poll_mode='native_capture_then_retained_editorial_assessment')
        usage_settled=json.loads(usage_path.read_text())
        engine_cli.main()  # Exact retained replay, not a second fresh network poll.
        second=json.loads((isolated/'data/state/pending_queue.json').read_text())
    finally:
        sys.argv=old_argv;transport._download_official=original
        if old_root is None:os.environ.pop('RADAR_ROOT',None)
        else:os.environ['RADAR_ROOT']=old_root
    assert first==second, 'Replay changed queue decisions/provenance/detection'
    assert json.loads(usage_path.read_text())==usage_settled, 'Replay spent paid calls'
    after_history=json.loads(history_path.read_text())
    old_rows=before_history.get('signals',[]) if isinstance(before_history,dict) else before_history
    new_rows=after_history.get('signals',[]) if isinstance(after_history,dict) else after_history
    assert all(row in new_rows for row in old_rows), 'Accepted stock changed'
    additions=[row for row in new_rows if row not in old_rows]
    assert all(row.get('source_name')=='Ministerio de Salud' for row in additions)
    calls=usage_settled['fast']['attempted']-usage_before['fast']['attempted']
    assert 0<=calls<=4 and usage_settled['deep']==usage_before['deep']
    if not assess:assert snapshot(isolated)==protected, 'Paid analyses/history/usage changed'
    responses_after=responses_path.read_bytes()
    assert responses_after.startswith(responses_before), 'Prior model ledger changed'
    (output/'history-new.json').write_text(json.dumps(additions,ensure_ascii=False,indent=2))
    (output/'usage-delta.json').write_text(json.dumps({'before':usage_before,'after':usage_settled,
        'responses_base_sha256':hashlib.sha256(responses_before).hexdigest(),
        'new_responses':[json.loads(line) for line in responses_after[len(responses_before):].splitlines()]},indent=2))
    assert {k:v for k,v in before_queue.items() if v['source']!='minsal'}=={k:v for k,v in second.items() if v['source']!='minsal'}
    # A retained replay cannot refresh the actual network poll timestamp.
    after_health=first_health
    if not captured:
        previous=before_health['sources']['minsal']
        for key in ('checked_at','engine_checked_at','last_attempt_at','last_successful_capture_at','last_verified_discovery_at'):
            after_health['sources']['minsal'][key]=previous.get(key)
        after_health['sources']['minsal']['poll_mode']='retained_replay_not_a_fresh_poll'
    assert {k:v for k,v in before_health['sources'].items() if k!='minsal'}=={k:v for k,v in after_health['sources'].items() if k!='minsal'}
    delta={k:v for k,v in first.items() if before_queue.get(k)!=v}
    for k,v in delta.items():
        if k in before_queue:
            old=before_queue[k]
            assert v['detected_at']==old['detected_at'] and v['lane']==old['lane']
            assert v['attempts']==old['attempts']+(1 if assess and v['status'] in ('published','rejected','retry') else 0)
            assert old['status'] not in ('published','rejected'), 'Terminal decision changed'
    (output/'queue-delta.json').write_text(json.dumps(delta,ensure_ascii=False,indent=2))
    (output/'health.json').write_text(json.dumps(after_health['sources']['minsal'],ensure_ascii=False,indent=2))
    (output/'native-captures.json').write_text(json.dumps(captures,ensure_ascii=False,indent=2))
    report={'fresh_network_capture':bool(captured),'replay':'PASS','queue_changes':len(delta),
            'protected_stock_preserved':True,'unrelated_queue_and_health_preserved':True,
            'ai_calls':calls,'new_publications':len(additions),'window_days':30,'priority_hours':72,
            'history_and_paid_hashes':protected,'health':after_health['sources']['minsal']}
    (output/'replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    shutil.rmtree(isolated)
    return report


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--replay',action='store_true')
    ap.add_argument('--assess',action='store_true')
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if args.replay:
        rows=json.loads((args.output/'native-captures.json').read_text())
        replay_core(args.output,rows)
        return
    verified=ROOT/'data/audits/daily_first_20261012/verified-native-runtime.zip'
    if verified.exists():
        # Recovery stop-loss: subsequent branch QA reuses the verified native input.
        # No source retries, paid reevaluation or renewed native timestamps.
        assert hashlib.sha256(verified.read_bytes()).hexdigest()=='f55065b15fa709aba48c831618a1cef0c2b0067fce584a98ba485dccd2c5669a'
        with zipfile.ZipFile(verified) as z:
            assert all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in z.namelist())
            z.extractall(args.output)
        rows=json.loads((args.output/'native-captures.json').read_text())
        replay_core(args.output,rows)
        (args.output/'current-replay.json').write_text(json.dumps(dict(
            candidate_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            native_producer_sha='6b6ef2c6a83d8244b0338598b393760709ef0dae',
            mode='retained_exact_primary_replay',new_network_requests=0,new_ai_calls=0),indent=2))
        return
    # Existing failed surface captures remain evidence; do not repeat FONASA's equivalent403.
    with zipfile.ZipFile(ROOT/'data/audits/daily_first_20261012/initial-primary-capture.zip') as z:
        retained=json.loads(z.read('capture.json'))
    alternatives=[('isp_anamed','https://www.ispch.gob.cl/categorias-alertas/anamed/'),
                  ('isp_surveillance','https://www.ispch.gob.cl/boletin/')]
    with ThreadPoolExecutor(max_workers=2) as pool:
        alternate_captures=list(pool.map(lambda p:probe(*p,args.output,timeout=15),alternatives))
    receipt={'captured_at':now(),'run_id':os.getenv('GITHUB_RUN_ID'),
             'candidate_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'retained_preflight':retained,'alternative_probes':alternate_captures,
             'retained_archive_sha256':hashlib.sha256((ROOT/'data/audits/daily_first_20261012/initial-primary-capture.zip').read_bytes()).hexdigest(),
             'ai_calls':0,'maximum_days':30,'window_priority_hours':72}
    (args.output/'capture.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    report=replay_core(args.output,[],live=True,assess=args.assess)
    assert report['health']['unique_items'], 'No verified MINSAL discovery'
    print(json.dumps({'queue_changes':report['queue_changes'],'replay':report['replay'],
                      'recent72':report['health']['items_recent'],'verified':report['health']['unique_items']}))


if __name__=='__main__':main()
