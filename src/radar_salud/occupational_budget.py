"""Account for this isolated branch's calls alongside the read-only staging ledger."""
import copy
import json
from pathlib import Path
from .ai_budget import _load, _save
from .paths import project_root
from .pending_queue import atomic_json

BASELINE = {'fast':{'attempted':31,'successful':31,'failed':0},
            'deep':{'attempted':14,'successful':14,'failed':0}}


def reconcile_budget(local, upstream, record=None):
    record = copy.deepcopy(record or {'baseline':BASELINE,'upstream':BASELINE,'isolated_delta':{
        k:{m:0 for m in ('attempted','successful','failed')} for k in ('fast','deep')}})
    total = copy.deepcopy(local)
    for kind in ('fast','deep'):
        for metric in ('attempted','successful','failed'):
            origin = upstream.get(kind, {}).get(metric)
            if not isinstance(origin,int) or origin < 0:
                raise ValueError('Staging ledger invalid; calls blocked')
            prior = record['upstream'][kind][metric]
            if origin < prior:
                raise ValueError('Staging ledger regressed; reconciliation required before calls')
            # Recover calls persisted in the normal ledger before an interrupted
            # source could save this receipt. Staging is never written here.
            delta=max(record['isolated_delta'][kind][metric],local[kind][metric]-prior)
            record['isolated_delta'][kind][metric]=delta
            total[kind][metric]=origin+delta
    record['upstream']=copy.deepcopy(upstream)
    record['policy']='Unpromoted isolated branch: staging plus its own delta, shared writer lock; no staging/main writes'
    record['phase_fast_limit']=30
    return total, record


def receipt_path(root=None):
    return Path(root or project_root())/'data/ai_usage/occupational_recovery_2026_10.json'


def sync_budget(upstream):
    path=receipt_path()
    record=json.loads(path.read_text()) if path.exists() else None
    total,record=reconcile_budget(_load(),upstream,record)
    _save(total);atomic_json(path,record)
    return record


def checkpoint_usage():
    path=receipt_path()
    if not path.exists():
        return
    record=json.loads(path.read_text())
    total,record=reconcile_budget(_load(),record['upstream'],record)
    atomic_json(path,record)


def remaining_phase_calls():
    path=receipt_path()
    if not path.exists():
        raise RuntimeError('Occupational budget receipt missing; sync the read-only staging ledger before --apply')
    record=json.loads(path.read_text())
    return max(0,record['phase_fast_limit']-record['isolated_delta']['fast']['attempted'])
