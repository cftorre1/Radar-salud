"""Import reviewed, source-scoped paid outputs without network or publication.

All conflicts are checked before writes. Replaying the same receipt is a no-op;
monthly usage is additive by new response_id, preserving concurrent MINSAL work.
"""
import argparse
import hashlib
import json
from pathlib import Path

BUNDLE = 'data/audits/integration_commander_2026_10_12/paid_runtime_delta.json'

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def reconcile(root, apply=False):
    root = Path(root)
    read = lambda name: json.loads((root / name).read_text())
    bundle = read(BUNDLE)
    queue = read('data/state/pending_queue.json')
    usage = read('data/ai_usage/2026-10.json')
    health = read('data/source_health.json')
    telemetry_path = root / 'data/ai_usage/responses.jsonl'
    telemetry = telemetry_path.read_text()
    existing = {r['response_id']: r for r in map(json.loads, telemetry.splitlines())}
    changed = 0
    for key, change in bundle['queue'].items():
        after = change['after']
        if queue.get(key) == after:
            continue
        if digest(queue.get(key)) != change['before_sha256']:
            raise ValueError('Concurrent queue change; preserve and review: ' + key)
        if after['source'] != 'pulso_latercera' or after['status'] == 'published':
            raise ValueError('Unapproved source/publication')
        if queue.get(key, {}).get('status') in ('published', 'rejected'):
            raise ValueError('Original terminal decision cannot change')
        queue[key] = after
        changed += 1
    new = []
    for receipt in bundle['responses']:
        rid = receipt['response_id']
        if rid in existing:
            if existing[rid] != receipt:
                raise ValueError('Conflicting paid receipt: ' + rid)
            continue
        if receipt['kind'] != 'fast' or not receipt['success']:
            raise ValueError('Unreviewed usage type')
        if not any(rid in json.dumps(v['after']) for v in bundle['queue'].values()):
            raise ValueError('Paid output missing')
        existing[rid] = receipt
        new.append(receipt)
        usage['fast']['attempted'] += 1
        usage['fast']['successful'] += 1
    for source, row in bundle['source_health'].items():
        if source not in ('pulso_latercera', 'diario_financiero'):
            raise ValueError('Unapproved health source')
        old = health['sources'].get(source, {})
        if row.get('checked_at', '') > old.get('checked_at', ''):
            health['sources'][source] = row
    result = {'queue_updates': changed, 'new_paid_receipts': len(new), 'usage': usage,
              'network_requests': 0, 'new_ai_calls': 0, 'publications': 0,
              'runtime_sha': bundle['baseline_sha'], 'runtime_run_id': bundle['runtime_run_id']}
    if apply:
        for name, value in [('data/state/pending_queue.json', queue), ('data/ai_usage/2026-10.json', usage), ('data/source_health.json', health)]:
            path = root / name
            text = json.dumps(value, ensure_ascii=False, indent=2)
            if json.loads(path.read_text()) != value:
                temporary = path.with_suffix(path.suffix + '.tmp')
                temporary.write_text(text)
                temporary.replace(path)
        if new:
            telemetry_path.write_text(telemetry.rstrip('\n') + '\n' + ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in new))
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(reconcile(args.root, args.apply), indent=2))
