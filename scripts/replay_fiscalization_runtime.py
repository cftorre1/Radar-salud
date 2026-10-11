"""Run the real collectors/engine twice against verified native captures in a copy.

The checked-out repository and all other source lanes remain unchanged. This is
an end-to-end replay of native HTTP evidence, not a fabricated network success.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from radar_salud import engine_cli
from radar_salud.pending_queue import atomic_json
import radar_salud.superintendencia_fiscalizacion as sis
import radar_salud.suseso_fiscalizacion as su


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def replay(captures, output, repository=Path('.')):
    manifest=json.loads((captures/'manifest.json').read_text())
    pages={}
    for receipt in manifest['receipts']:
        path=Path(receipt['body_file'])
        if not path.exists():path=next(captures.rglob(path.name))
        assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['sha256'], receipt['url']
        if receipt['transport_ok'] and path.suffix!='.pdf':
            pages[receipt['url']]=path.read_text(errors='replace')
    originals=(sis.fetch_html,su.fetch_html,engine_cli.has_capacity,sys.argv,os.environ.get('RADAR_ROOT'))
    snapshots=[]
    try:
        with tempfile.TemporaryDirectory(prefix='fiscalization-native-') as temporary:
            root=Path(temporary)
            shutil.copytree(repository/'config',root/'config')
            for relative in ['data/state/pending_queue.json','data/history/superintendencia_signals.json','data/source_health.json']:
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repository/relative,target)
            for path in (repository/'data/state').glob('*seen.json'):
                shutil.copyfile(path,root/'data/state'/path.name)
            os.environ['RADAR_ROOT']=str(root)
            sis.fetch_html=lambda url:pages[url]
            su.fetch_html=lambda url:pages[url]
            engine_cli.has_capacity=lambda kind:False
            collectors=[sis.SuperintendenciaFiscalizacionScout(),su.SusesoFiscalizacionScout()]
            inventory=[];surfaces={}
            for collector in collectors:
                inventory.extend(asdict(raw) for raw in collector.discover())
                surfaces[collector.SOURCE_SLUG]=collector.surface_results
            atomic_json(output/'collector_inventory.json',inventory)
            queue_before=json.loads((root/'data/state/pending_queue.json').read_text())
            other_before={key:value for key,value in queue_before.items() if value['source'] not in ('superintendencia_fiscalizacion','suseso_fiscalizacion')}
            for _ in range(2):
                sys.argv=['engine_cli','--only-source','superintendencia_fiscalizacion','--only-source','suseso_fiscalizacion']
                engine_cli.main()
                history=json.loads((root/'data/history/superintendencia_signals.json').read_text())
                queue=json.loads((root/'data/state/pending_queue.json').read_text())
                snapshots.append(dict(history=digest(history),queue=digest(queue)))
            other_after={key:value for key,value in queue.items() if key in other_before}
            report=dict(runtime_run_url=manifest['github_run_url'],captured_sha=manifest['started_from_sha'],
                actual_collectors=True,actual_engine=True,network_mode='verified_native_capture_replay',
                surfaces=surfaces,inventory_items=len(inventory),idempotent=snapshots[0]==snapshots[1],
                snapshots=snapshots,other_queue_records_preserved=other_before==other_after,
                writes_to_repository_state=False,writes_to_staging_or_main=False,ai_budget_available=False)
            atomic_json(output/'replay_report.json',report)
            atomic_json(output/'history.json',history)
            atomic_json(output/'pending_queue.json',queue)
            atomic_json(output/'source_health.json',json.loads((root/'data/source_health.json').read_text()))
            if not report['idempotent'] or not report['other_queue_records_preserved']:
                raise RuntimeError('Native replay must be idempotent and preserve independent queue records')
            return report
    finally:
        sis.fetch_html,su.fetch_html,engine_cli.has_capacity,sys.argv,old_root=originals
        if old_root is None:os.environ.pop('RADAR_ROOT',None)
        else:os.environ['RADAR_ROOT']=old_root


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--captures',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=replay(args.captures,args.output)
    print(json.dumps({key:result[key] for key in ('idempotent','actual_collectors','actual_engine','other_queue_records_preserved')}))
