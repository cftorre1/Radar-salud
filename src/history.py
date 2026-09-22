from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Dict, Any


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding='utf-8'))
    return raw.get('signals', raw) if isinstance(raw, dict) else raw


def _key(signal: dict) -> str:
    return str(signal.get('source_url') or signal.get('signal_id') or signal.get('title'))


def merge_history(existing: Iterable[dict], new_signals: Iterable[dict]) -> list[dict]:
    merged: Dict[str, dict] = {_key(s): dict(s) for s in existing if _key(s)}
    for s in new_signals:
        if _key(s):
            merged[_key(s)] = dict(s)
    return list(merged.values())


def save_history(path: Path, signals: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'signals': list(signals)}, ensure_ascii=False, indent=2), encoding='utf-8')
