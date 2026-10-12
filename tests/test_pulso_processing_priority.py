"""Scheduling regressions: recency changes Pulso slots, never queue precedence."""
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar_salud import engine_cli, paths
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue

ROOT = Path(__file__).resolve().parents[1]


def pending(key, day, *, source='pulso_latercera', lane='BACKFILL', attempts=0):
    return key, dict(source=source, lane=lane, attempts=attempts, status='retry' if attempts else 'pending',
                     detected_at='2026-10-11T06:00:00Z', retry_at='2026-10-11T00:00:00Z' if attempts else None,
                     reason='analysis_unavailable' if attempts else None,
                     raw=dict(event_date=day, title=key, metadata={'sentinel': key}))


def test_mixed_sources_keep_exact_global_positions_and_pulso_groups_keep_precedence():
    ready = [pending('live-old', '2026-10-08', lane='LIVE'),
             pending('minsal-live', '2026-10-09', source='minsal', lane='LIVE'),
             pending('live-new', '2026-10-10', lane='LIVE'),
             pending('retry-old', '2026-07-16', attempts=1),
             pending('diario', '2026-10-10', source='diario_oficial'),
             pending('backfill-old', '2026-07-14'),
             pending('retry-new', '2026-10-10', attempts=1),
             pending('backfill-new', '2026-10-09'),
             pending('minsal-backfill', '2026-10-10', source='minsal'),
             pending('backfill-unknown', None)]
    before = copy.deepcopy(ready)
    ordered = engine_cli._prioritize_pulso_ready(iter(ready))
    assert [key for key, _ in ordered] == [
        'live-new', 'minsal-live', 'live-old', 'retry-new', 'diario',
        'backfill-new', 'retry-old', 'backfill-old', 'minsal-backfill', 'backfill-unknown']
    assert ready == before
    original = dict(ready)
    assert all(item is original[key] for key, item in ordered)
    assert [(item['source'], item['lane'], item['attempts']) for _, item in ordered] == [
        (item['source'], item['lane'], item['attempts']) for _, item in ready]
    assert ordered[1] == ready[1] and ordered[4] == ready[4] and ordered[8] == ready[8]


def test_invalid_and_unknown_dates_keep_stable_relative_order_without_guessing():
    ready = [pending('missing', None), pending('bad-date', '2026-02-30'),
             pending('iso-timestamp', '2026-10-10T01:00:00Z'), pending('compact', '20261010'),
             pending('non-string', 20261010), pending('older', '2026-07-14'),
             pending('new', '2026-10-09'), pending('same-new', '2026-10-09')]
    ordered = engine_cli._prioritize_pulso_ready(ready)
    assert [key for key, _ in ordered] == [
        'new', 'same-new', 'older', 'missing', 'bad-date', 'iso-timestamp', 'compact', 'non-string']


@pytest.mark.parametrize('selected', [True, False])
def test_core_processes_recent_pulso_before_older_backfill_without_changing_other_source_slots(
        tmp_path, monkeypatch, selected):
    (tmp_path/'config').mkdir()
    (tmp_path/'config/sources.json').write_bytes((ROOT/'config/sources.json').read_bytes())
    state = tmp_path/'data/state'; state.mkdir(parents=True)
    now = datetime.now(timezone.utc)
    old_day, new_day = (now-timedelta(days=85)).date().isoformat(), (now-timedelta(days=2)).date().isoformat()
    queue = PendingQueue(state/'pending_queue.json')
    old = RawItem('pulso_latercera', 'Hospital anuncia ajustes durante julio',
                  'https://www.latercera.com/pulso/noticia/hospital-old/', 'Pulso', 'press_high_trust', old_day)
    other = RawItem('minsal', 'Minsal anuncia medidas sanitarias',
                    'https://www.minsal.cl/medidas/', 'Minsal', 'official', new_day)
    new = RawItem('pulso_latercera', 'Hospital anuncia ajustes recientes',
                  'https://www.latercera.com/nacional/noticia/hospital-new/', 'Pulso', 'press_high_trust', new_day)
    for raw in (old, other, new):
        queue.discover(raw.source_slug, [raw], now=now)
    before = copy.deepcopy(queue.items)
    for name in dir(engine_cli):
        scout = getattr(engine_cli, name)
        if name.endswith('Scout') and isinstance(scout, type) and hasattr(scout, 'discover'):
            monkeypatch.setattr(scout, 'discover', lambda self, *args, **kwargs: [])
    monkeypatch.setattr(paths, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(engine_cli, 'seed_from_history', lambda _: None)
    monkeypatch.setattr(engine_cli, 'has_capacity', lambda _: True)
    calls = []
    def process(raw, cfg):
        calls.append((raw.source_slug, raw.url))
        raw.metadata['rejection_reason'] = 'synthetic_editorial_rejection'
        return None
    monkeypatch.setattr(engine_cli, 'process_curated_beta_source', process)
    monkeypatch.setattr(engine_cli, 'process_minsal', process)
    argv = ['engine_cli', '--limit', '1' if selected else '2']
    if selected:
        argv += ['--sources', 'pulso_latercera']
    monkeypatch.setattr(sys, 'argv', argv)
    engine_cli.main()
    assert calls == [('pulso_latercera', new.url)] + ([] if selected else [('minsal', other.url)])
    saved = PendingQueue(state/'pending_queue.json').items
    by_url = {item['raw']['url']: item for item in saved.values()}
    assert by_url[old.url]['status'] == 'pending' and by_url[old.url]['attempts'] == 0
    assert by_url[new.url]['status'] == 'rejected' and by_url[new.url]['attempts'] == 1
    for key, original in before.items():
        assert saved[key]['lane'] == original['lane']
        assert saved[key]['detected_at'] == original['detected_at']
        if original['raw']['url'] == old.url or selected and original['source'] == 'minsal':
            assert saved[key] == original
    run = json.loads((state/'discovery_run.json').read_text())
    assert run['processing_attempts'] == (1 if selected else 2)
