"""Synthetic empty-discovery regression; does not prove publisher coverage."""
import json
import sys
from pathlib import Path

from radar_salud import engine_cli, paths


def test_empty_core_poll_uses_configured_pulso_publisher_name(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    source = json.loads((Path(__file__).resolve().parents[1] / "config/sources.json").read_text())
    (tmp_path / "config/sources.json").write_text(json.dumps(source))

    class EmptySyntheticScout:
        def __init__(self, slug):
            assert slug == "pulso_latercera"
            self.discovery_audit = []

        def discover(self):
            return []

    monkeypatch.setattr(engine_cli, "CuratedBetaSourceScout", EmptySyntheticScout)
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setattr(engine_cli, "seed_from_history", lambda root: None)
    monkeypatch.setattr(engine_cli, "ai_budget_status", lambda: {})
    monkeypatch.setattr(sys, "argv", ["engine_cli", "--sources", "pulso_latercera", "--discovery-only"])
    engine_cli.main()
    health = json.loads((tmp_path / "data/source_health.json").read_text())["sources"]["pulso_latercera"]
    assert health["name"] == "Pulso / La Tercera"
    assert health["published"] == 0
    assert health["last_signal_at"] is None
