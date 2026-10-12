"""Exercise the installed CLI entry points without pytest's repository import path."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def run_cli(script,*arguments,cwd=ROOT):
    env=dict(os.environ)
    env.pop('PYTHONPATH',None)
    return subprocess.run([sys.executable,str(ROOT/'scripts'/script),*map(str,arguments)],
                          cwd=cwd,env=env,check=True,capture_output=True,text=True,timeout=60)


def test_offline_snapshot_cli_exports_public_catalog_without_repository_pythonpath(tmp_path):
    output=tmp_path/'radar_today.json'
    result=run_cli('export_web_snapshot.py','--input','data/history/superintendencia_signals.json',
                   '--offline','--output',output)
    snapshot=json.loads(output.read_text())
    assert snapshot['signals'] and 'snapshot=' in result.stdout
    catalog=json.loads((tmp_path/'public_sources.json').read_text())
    assert catalog['sources']
    assert all(set(row)=={'id','name','group','url','description'} for row in catalog['sources'])
    assert 'global_reuters' not in {row['id'] for row in catalog['sources']}
    assert (tmp_path/'source_health.json').read_bytes()==(ROOT/'data/source_health.json').read_bytes()


def test_standalone_catalog_cli_preserves_input_and_excludes_blocked_source(tmp_path):
    health=tmp_path/'data/source_health.json'
    health.parent.mkdir()
    health.write_text(json.dumps({'sources':{
        'minsal':{'name':'Ministerio de Salud','technical_status':'ok','coverage_status':'observed','checked_at':'2026-10-01T12:00:00Z'},
        'global_who':{'name':'WHO bloqueada','technical_status':'ok','coverage_status':'blocked','checked_at':'2026-10-01T12:00:00Z'}}}))
    original=health.read_bytes()
    run_cli('export_public_sources.py',cwd=tmp_path)
    catalog=json.loads((tmp_path/'web/data/public_sources.json').read_text())
    assert [row['id'] for row in catalog['sources']]==['minsal']
    assert set(catalog['sources'][0])=={'id','name','group','url','description'}
    assert health.read_bytes()==original
