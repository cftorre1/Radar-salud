"""Expose an existing owned checkpoint through durable CI logs; no new calls."""
import json
from pathlib import Path

root=Path('work/prior-provider-checkpoint')
path=next(root.rglob('provider_live_checkpoint_2026_10_11.json'))
checkpoint=json.loads(path.read_text())
checkpoint['artifact_receipt']=json.loads(Path('data/audits/provider_ci_receipt_2026_10_11.json').read_text())
queue=json.loads(next(root.rglob('pending_queue.json')).read_text())
recovered={k:v for k,v in queue.items() if v.get('raw',{}).get('metadata',{}).get('recovery_audit','').startswith('data/audits/providers_2026_10_11/')}
for item in recovered.values():
    item['raw']['raw_text']=''
    item['raw']['metadata'].pop('page_text',None)
checkpoint['recovered_queue']=recovered
checkpoint['usage_ledgers']={p.name:json.loads(p.read_text()) for p in root.rglob('ai_usage/*.json')}
print('PROVIDER_CHECKPOINT_JSON='+json.dumps(checkpoint,ensure_ascii=False,separators=(',',':')))
