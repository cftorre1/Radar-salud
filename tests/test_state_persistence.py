import json
import pytest
from pathlib import Path
from radar_salud.history import load_history, save_history
from radar_salud.scouts import SeenStore


def test_history_survives_failed_atomic_replace(tmp_path, monkeypatch):
    path=tmp_path/"history.json"
    old=[{"title":"Previous","source_url":"https://example.org/old"}]
    save_history(path,old)
    original=path.read_bytes()
    def interrupted(source,target):
        raise OSError("Interrupted before replacement")
    monkeypatch.setattr(Path,"replace",interrupted)
    with pytest.raises(OSError,match="Interrupted"):
        save_history(path,[{"title":"New"}])
    assert path.read_bytes()==original
    assert load_history(path)==old


def test_seen_state_remains_parseable_after_failure(tmp_path,monkeypatch):
    path=tmp_path/"seen.json"
    SeenStore(path).add_many(["original"])
    original=path.read_bytes()
    monkeypatch.setattr(Path,"replace",lambda *args: (_ for _ in ()).throw(OSError("Interrupted")))
    with pytest.raises(OSError):SeenStore(path).add_many(["new"])
    assert path.read_bytes()==original
    assert SeenStore(path).is_seen("original")
    assert not SeenStore(path).is_seen("new")
