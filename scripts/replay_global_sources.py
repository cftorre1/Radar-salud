"""Reproduce live metadata from captured bytes in a disposable root."""
import hashlib
import json
import shutil
import tempfile
from datetime import date
from pathlib import Path
from discover_global_sources import run

root = Path(__file__).resolve().parents[1]
live_path = root/'data/global_intelligence/discovery.json'
live = json.loads(live_path.read_text())
protected = [live_path, root/'data/global_intelligence/source_health.json',
             root/'data/global_intelligence/editorial_candidates.json', root/'data/global_intelligence/ledger.json',
             root/'data/source_health.json',root/'web/data/source_health.json',root/'web/data/product.json',
             root/'data/global/themes.json',root/'web/data/global_themes.json']
cooldown=root/'data/global_intelligence/http_cooldowns.json'
if cooldown.exists(): protected.append(cooldown)
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = {str(p.relative_to(root)):digest(p) for p in protected}
with tempfile.TemporaryDirectory(prefix='global-replay-',dir=root/'work') as temporary:
    replay_root=Path(temporary)
    for relative in ('config/global_discovery.json','data/global/themes.json','data/global_intelligence/ledger.json'):
        destination=replay_root/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/relative,destination)
    result=run(replay_root,replay_root/'captures',date.fromisoformat(live['as_of']),live['run_id'],root/'work/global-runtime-captures')
    for field in ('items','routes','editorial_topics','technical_failures'):
        if result[field] != live[field]: raise ValueError('replay differs: '+field)
    for source in ('who','paho','reuters'):
        for field in ('counts','coverage_completeness','outcome','pages_checked','published'):
            if result['source_health'][source][field] != live['source_health'][source][field]:
                raise ValueError('replay health differs: '+source+'/'+field)
    if result['network_requests'] or result['paid_ai_calls'] or result['publication_count']:
        raise ValueError('replay exceeded read-only/no-network contract')
after = {str(p.relative_to(root)):digest(p) for p in protected}
if before != after: raise ValueError('replay modified canonical state')
evidence=root/'data/audits/global_source_recovery_2026_10_11/runs'/live['run_id']/'replay.json'
evidence.write_text(json.dumps({'result':'PASS','run_id':live['run_id'],
    'live_inventory_sha256':digest(live_path),'inventory_mode':live['mode'],'canonical_inventory_sha256':digest(live_path),'metadata_projection_ref':(live.get('metadata_projection') or {}).get('inventory_ref'),'items':len(live['items']),
    'network_requests':0,'paid_ai_calls':0,'publication_count':0,
    'protected_sha256':before,'canonical_state_unchanged':True,
    'metadata_and_native_control_identical':True},indent=2)+'\n')
print('PASS: captured-byte replay, native control and canonical preservation')
