"""Real post-merge runtime on a copied stock. Never pushes or publishes state."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

def read(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def main():
    repo=Path(__file__).resolve().parents[1]
    targets=read(repo/'config/integration_runtime_targets.json')
    selected=set(targets['sources'])
    root=repo/'work/integration-runtime'
    if root.exists():raise RuntimeError('Runtime output must start empty; do not overwrite an earlier checkpoint')
    root.mkdir(parents=True)
    shutil.copytree(repo/'data',root/'data',ignore=shutil.ignore_patterns('audits'))
    shutil.copytree(repo/'config',root/'config')
    shutil.copytree(repo/'web',root/'web')
    queue_before=read(root/'data/state/pending_queue.json',{})
    history_before=read(root/'data/history/superintendencia_signals.json',{'signals':[]})
    history_before=history_before.get('signals',history_before)
    health_before=read(root/'data/source_health.json',{}).get('sources',{})
    source_names={v['raw']['source_name'] for v in queue_before.values() if v.get('source') in selected}
    unrelated={k:deepcopy(v) for k,v in queue_before.items() if v.get('source') not in selected}
    unrelated_history=[v for v in history_before if v.get('source_name') not in source_names]
    polls=[]
    environment={**os.environ,'RADAR_ROOT':str(root)}
    for number in (1,2):
        command=[sys.executable,'-m','radar_salud.engine_cli','--limit','5']
        for source in targets['sources']:command.extend(['--source',source])
        start=datetime.now(timezone.utc).isoformat()
        with (root/f'poll-{number}.log').open('w') as log:
            result=subprocess.run(command,cwd=repo,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
        discovery=read(root/'data/state/discovery_run.json',{})
        queue=read(root/'data/state/pending_queue.json',{})
        history=read(root/'data/history/superintendencia_signals.json',{'signals':[]})
        history=history.get('signals',history)
        assert all(queue.get(k)==v for k,v in unrelated.items()),'Unrelated queue changed'
        assert [v for v in history if v.get('source_name') not in source_names]==unrelated_history,'Unrelated history changed'
        health=read(root/'data/source_health.json',{}).get('sources',{})
        assert all(health.get(k)==v for k,v in health_before.items() if k not in selected),'Unrelated source health changed'
        published={k:v for k,v in queue.items() if v.get('source') in selected and v.get('status')=='published'}
        urls=[v.get('source_url') for v in history if v.get('source_name') in source_names]
        assert len(urls)==len(set(urls)),'Duplicate selected-source history URLs'
        polls.append({'poll':number,'started_at':start,'finished_at':datetime.now(timezone.utc).isoformat(),
            'exit_code':result.returncode,'discovery':{k:v for k,v in discovery.get('sources',{}).items() if k in selected},
            'queue_identity_sha256':digest(sorted(queue)),'published_queue_keys':sorted(published),
            'history_sha256':digest(history),'history_count':len(history),'history_selected_unique':len(urls),
            'source_health':{k:v for k,v in health.items() if k in selected},'unrelated_stock_preserved':True})
        (root/'summary.json').write_text(json.dumps({'staging_sha':os.environ.get('GITHUB_SHA'),'targets':targets,
            'actual_engine':True,'isolated_state':True,'polls':polls,'post_merge':os.environ.get('GITHUB_REF')=='refs/heads/staging',
            'editorial_outputs_require_review_before_state_import':True},ensure_ascii=False,indent=2)+'\n')
        if result.returncode:raise RuntimeError(f'Engine poll {number} failed: {result.returncode}; inspect saved log')
    assert polls[0]['published_queue_keys']==polls[1]['published_queue_keys'],'Second poll changes accepted stock; inspect before claiming idempotence'
    assert polls[0]['queue_identity_sha256']==polls[1]['queue_identity_sha256'],'Second poll adds queue identities'
    assert polls[0]['history_sha256']==polls[1]['history_sha256'],'Second poll changes history'
    command=[sys.executable,'scripts/export_web_snapshot.py','--input',str(root/'data/history/superintendencia_signals.json'),
        '--output',str(root/'web/data/radar_today.json'),'--offline']
    subprocess.run(command,cwd=repo,check=True)
    shutil.copyfile(root/'data/source_health.json',root/'web/data/source_health.json')
    subprocess.run([sys.executable,'scripts/review_candidate.py','--web',str(root/'web'),'--sha',os.environ.get('GITHUB_SHA',''),
        '--output',str(root/'reviewer.json')],cwd=repo,check=True)
    summary=read(root/'summary.json');summary.update(idempotent=True,unrelated_stock_preserved=True,
        reviewer=read(root/'reviewer.json'),feed_count=len(read(root/'web/data/radar_today.json')['signals']))
    (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'staging_sha':summary['staging_sha'],'sources':targets['sources'],'idempotent':True,'feed_count':summary['feed_count']}))

if __name__=='__main__':main()
