"""Two genuine daily-engine polls in one isolated persisted checkout, no AI."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from radar_salud.pending_queue import atomic_json
from provider_inventory import SLUGS


def read(path,default):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def main():
    queue_path=Path('data/state/pending_queue.json')
    before=read(queue_path,{})
    published={k:deepcopy(v) for k,v in before.items() if v['source'] in SLUGS and v['status']=='published'}
    history_before=digest(read('data/history/superintendencia_signals.json',[]))
    usage_before=digest({str(p):read(p,{}) for p in Path('data/ai_usage').glob('*.json')})
    results=[]
    for number in (1,2):
        watermarks_before=read('data/state/discovery_watermarks.json',{})
        cmd=[sys.executable,'-m','radar_salud.engine_cli','--discovery-only']
        for slug in SLUGS:cmd.extend(['--source',slug])
        subprocess.run(cmd,check=True)
        run=read('data/state/discovery_run.json',{})
        watermarks_after=read('data/state/discovery_watermarks.json',{})
        queue=read(queue_path,{})
        blocked=[slug for slug,row in run['sources'].items() if row['technical_status']=='error']
        assert all(watermarks_before.get(slug)==watermarks_after.get(slug) for slug in blocked)
        assert all(queue.get(k)==v for k,v in published.items())
        results.append({'poll':number,'discovery':run,'queue_items':len(queue),
            'new':sum(x['new'] for x in run['sources'].values()),
            'watermarks':watermarks_after,'partial_watermarks_preserved':True,
            'published_terminal_preserved':len(published),
            'queue_identity_sha256':digest(sorted(queue))})
    assert results[1]['new']==0,'Second poll discovered new queue identities; inspect before claiming idempotence'
    assert history_before==digest(read('data/history/superintendencia_signals.json',[]))
    assert usage_before==digest({str(p):read(p,{}) for p in Path('data/ai_usage').glob('*.json')})
    after=read(queue_path,{})
    nonfront={k:v for k,v in before.items() if v['source'] not in SLUGS}
    assert all(after.get(k)==v for k,v in nonfront.items())
    output={'at':datetime.now(timezone.utc).isoformat(),'runtime':'actual engine_cli; isolated PR checkout',
        'polls':results,'idempotent':True,'history_unchanged':True,'ai_ledger_unchanged':True,
        'unrelated_queue_unchanged':True,'editorial_assessment_performed':False,
        'coverage_claim':'recurrent discovery verified; inventory and editorial coverage remain separate',
        'promotion':'none'}
    selected={k:deepcopy(v) for k,v in after.items() if v['source'] in SLUGS}
    for row in selected.values():
        row['raw']['raw_text']='';row['raw'].get('metadata',{}).pop('page_text',None)
    output.update(recovered_queue=selected,source_health=read('data/source_health.json',{})['sources'],
        seen_ledgers={slug:read('data/state/'+slug+'_seen.json',[]) for slug in SLUGS},
        commit=__import__('os').getenv('GITHUB_SHA'))
    atomic_json('data/audits/provider_recurrent_checkpoint_2026_10_11.json',output)
    print('PROVIDER_RECURRENT_JSON '+json.dumps(output,separators=(',',':')))


if __name__=='__main__':main()
