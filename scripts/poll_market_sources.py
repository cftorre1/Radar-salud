"""Daily public discovery in an isolated lane. Safe to call repeatedly from a scheduler."""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def due(last_poll, now, cadence_hours):
    return last_poll is None or now-datetime.fromisoformat(last_poll)>=timedelta(hours=cadence_hours)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--force-qualification',action='store_true')
    a=p.parse_args()
    config=json.loads(Path('config/source_expansion_runtime.json').read_text())
    cadence=config['cadence_hours'];now=datetime.now(timezone.utc)
    state_path=a.output/'poll_state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {'polls':[]}
    polls=state['polls'];last=polls[-1]['started_at'] if polls else None
    if not a.force_qualification and not due(last,now,cadence):
        print(json.dumps({'status':'not_due','next_poll_at':(datetime.fromisoformat(last)+timedelta(hours=cadence)).isoformat(),'coverage_claim':'none'}))
        return
    stamp=now.strftime('%Y%m%dT%H%M%SZ');run=a.output/stamp
    subprocess.run([sys.executable,'scripts/probe_source_expansion.py','--output',str(run/'capture')],check=True)
    seed=Path(polls[-1]['output'])/'qualification/stock' if polls else Path('.')
    subprocess.run([sys.executable,'scripts/validate_market_source_runtime.py','--capture-dir',str(run/'capture'),'--output',str(run/'qualification'),'--stock-seed',str(seed)],check=True)
    polls.append({'started_at':now.isoformat(),'completed_at':datetime.now(timezone.utc).isoformat(),
                  'github_run_id':os.environ.get('GITHUB_RUN_ID'),'output':str(run),'status':'qualified_snapshot'})
    state.update(schema_version=1,cadence_hours=cadence,next_poll_at=(now+timedelta(hours=cadence)).isoformat(),
                 recurrence_validated=len(polls)>=2 and due(polls[-2]['started_at'],now,cadence),
                 activation='qualification_only_core_editorial_gate_required')
    state_path.parent.mkdir(parents=True,exist_ok=True)
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(state,ensure_ascii=False))


if __name__=='__main__':main()
