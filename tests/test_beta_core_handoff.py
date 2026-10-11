import json
from datetime import datetime, timedelta, timezone

import pytest

from radar_salud import beta_source_engine, beta_source_engine_fast
from radar_salud.beta_core_handoff import core_handoff


def setup_root(root, polled=None):
    (root / "config").mkdir()
    (root / "data/state").mkdir(parents=True)
    (root / "config/sources.json").write_text(json.dumps([{"slug": "pulso_latercera"}]))
    (root / "config/beta_source_configs.json").write_text("[]")
    polled = polled or datetime.now(timezone.utc) - timedelta(seconds=10)
    run = {"at": polled.isoformat(), "sources": {"pulso_latercera": {"discovered": 9, "technical_status": "ok", "error_type": None}},
           "source_details": {"pulso_latercera": [{"status": "discovered", "publication_date": polled.date().isoformat()}]}}
    health = {"sources": {"pulso_latercera": {"checked_at": (polled + timedelta(seconds=1)).isoformat(), "published": 2, "pending": 3, "rejected": 4, "status": "ok"}}}
    (root / "data/state/discovery_run.json").write_text(json.dumps(run))
    (root / "data/source_health.json").write_text(json.dumps(health))


def test_handoff_keeps_observed_core_outcomes_and_fails_closed_when_stale(tmp_path):
    setup_root(tmp_path)
    row = core_handoff(tmp_path, "pulso_latercera")
    assert row["published"] == 2 and row["discovered"] == 9
    assert row["validation_mode"] == "core_handoff"
    p = tmp_path / "data/state/discovery_run.json"
    run = json.loads(p.read_text())
    run["at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    p.write_text(json.dumps(run))
    assert core_handoff(tmp_path, "pulso_latercera")["error"] == "core_runtime_not_current"
    p.unlink()
    assert core_handoff(tmp_path, "pulso_latercera")["published"] is None


@pytest.mark.parametrize("module", [beta_source_engine, beta_source_engine_fast])
def test_beta_writer_neither_rediscovers_nor_overwrites_promoted_core_source(tmp_path, monkeypatch, module):
    setup_root(tmp_path)
    monkeypatch.setattr(module, "project_root", lambda: tmp_path)
    others = {slug: {"name": slug} for slug in ("prestadores_data", "red_davila", "andes_salud", "clinicas_achs_salud", "achs_seguro_laboral", "mutual_seguridad", "ist", "pulso_latercera")}
    monkeypatch.setattr(module, "_cfgs", lambda root: others)
    class Scout:
        def __init__(self, slug=None):
            self.slug = slug
        def discover(self):
            assert self.slug != "pulso_latercera", "Promoted source must use core evidence"
            return []
    monkeypatch.setattr(module, "PrestadoresDataScout", Scout)
    monkeypatch.setattr(module, "FastCuratedBetaSourceScout" if module is beta_source_engine_fast else "CuratedBetaSourceScout", Scout)
    recorded = []
    monkeypatch.setattr(module, "health_record", lambda root, slug, **kwargs: recorded.append(slug))
    monkeypatch.setattr(module, "load_history", lambda path: [])
    monkeypatch.setattr(module, "save_history", lambda path, rows: None)
    before = (tmp_path / "data/source_health.json").read_bytes()
    module.main()
    assert "pulso_latercera" not in recorded
    assert (tmp_path / "data/source_health.json").read_bytes() == before
    report = json.loads((tmp_path / "data/state/beta_source_validation.json").read_text())["sources"]["pulso_latercera"]
    assert report["published"] == 2 and report["technical_status"] == "ok"
