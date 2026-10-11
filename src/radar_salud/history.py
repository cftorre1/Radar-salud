from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Dict, Any
from .pending_queue import atomic_json


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding='utf-8'))
    return raw.get('signals', raw) if isinstance(raw, dict) else raw


def _key(signal: dict) -> str:
    key = str(signal.get('source_url') or signal.get('signal_id') or signal.get('title'))
    if 'Fiscalización' in (signal.get('signal_types') or []) and signal.get('source_record_id'):
        key += '|record:' + signal['source_record_id']
    return key


def merge_history(existing: Iterable[dict], new_signals: Iterable[dict]) -> list[dict]:
    merged: Dict[str, dict] = {_key(s): dict(s) for s in existing if _key(s)}
    for s in new_signals:
        if _key(s):
            merged[_key(s)] = dict(s)
    return list(merged.values())


def save_history(path: Path, signals: Iterable[dict]) -> None:
    atomic_json(path, {'signals': list(signals)})
