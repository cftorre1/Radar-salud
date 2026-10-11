"""Expose an existing owned checkpoint through durable CI logs; no new calls."""
import json
import sys
from pathlib import Path

if '--durable' in sys.argv:
    # Once imported, the branch contains the actual checkpoint. Validation must
    # not depend on a temporary Actions artifact or repeat paid analysis.
    files=['provider_live_checkpoint_2026_10_11.json','provider_repair_checkpoint_2026_10_11.json']
    history=json.loads(Path('data/history/superintendencia_signals.json').read_text())['signals']
    outputs=[]
    for filename in files:
        checkpoint=json.loads((Path('data/audits')/filename).read_text())
        assert checkpoint['promotion']=='none'
        for result in checkpoint['results']:
            if result['outcome']=='published':
                row=result['signal'];matches=[v for v in history if v.get('source_url')==row['source_url']]
                assert len(matches)==1, f"Checkpoint original URL must remain unique: {row['source_url']}"
                assert matches[0]['event_date']==row['event_date']
                assert matches[0]['source_name']==row['source_name']
                outputs.append(row['source_url'])
    assert len(set(outputs))==5
    print(json.dumps({'checkpoint':'durable_original_and_repair_receipts','candidate_outputs':len(outputs),
                      'promotion':'none','paid_calls':0,'artifact_download_required':False}))
    raise SystemExit(0)

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
