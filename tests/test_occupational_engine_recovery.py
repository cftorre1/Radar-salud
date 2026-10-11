import json
import shutil
import sys
from pathlib import Path
from radar_salud import engine_cli, paths
from radar_salud.models import RawItem
from radar_salud.occupational_sources import SourceDiscoveryError


def test_partial_capture_enters_queue_without_advancing_watermark_or_blocking_next_source(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    shutil.copy(Path(__file__).resolve().parents[1] / "config/sources.json", tmp_path / "config/sources.json")
    state = tmp_path / "data/state"
    state.mkdir(parents=True)
    old = "2026-09-01T00:00:00+00:00"
    (state / "discovery_watermarks.json").write_text(json.dumps({"mutual_seguridad": old}))
    raw = RawItem("mutual_seguridad", "Verified partial article", "https://www.mutual.cl/partial", "Mutual", "mutuality", event_date="2026-10-01")
    visited = []
    class Null:
        def __init__(self, *args, **kwargs):
            pass
        def discover(self, *args, **kwargs):
            return []
    class Scoped:
        def __init__(self, slug):
            self.slug = slug
            self.inventory = {"coverage_complete": False, "raw_items": [], "pages": [], "rows": [], "errors": []}
        def discover(self):
            visited.append(self.slug)
            if self.slug == "mutual_seguridad":
                error = SourceDiscoveryError("partial_detail_failure", "https://www.mutual.cl/missing")
                error.partial_items = [raw]
                error.diagnostics = [{"code": "detail_fetch_failed", "url": error.url}]
                raise error
            return []
    for name in ("SuperintendenciaStatsScout", "SuperintendenciaNormativaScout", "SuperintendenciaFiscalizacionScout",
                 "MinsalNewsScout", "SusesoNormativeScout", "SusesoNewsScout", "SusesoFiscalizacionScout", "DfHealthScout",
                 "FonasaDataHubScout", "FonasaNewsScout", "IspSurveillanceScout", "IspAnamedAlertScout", "ClinicasChileScout",
                 "DeisResourceScout", "DiarioOficialHealthScout", "CorporateNewsroomScout"):
        monkeypatch.setattr(engine_cli, name, Null)
    monkeypatch.setattr(engine_cli, "CuratedBetaSourceScout", Scoped)
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setattr(engine_cli, "seed_from_history", lambda root: None)
    monkeypatch.setattr(engine_cli, "has_capacity", lambda kind: True)
    monkeypatch.setattr(engine_cli, "process_curated_beta_source", lambda raw, cfg: None)
    monkeypatch.setattr(engine_cli, "ai_budget_status", lambda: {})
    monkeypatch.setattr(sys, "argv", ["engine_cli", "--limit", "1"])
    engine_cli.main()
    assert "ist" in visited and "achs_seguro_laboral" in visited
    assert json.loads((state / "discovery_watermarks.json").read_text())["mutual_seguridad"] == old
    queue = json.loads((state / "pending_queue.json").read_text())
    assert len(queue) == 1 and next(iter(queue.values()))["source"] == "mutual_seguridad"
    audit = json.loads((state / "occupational_source_discovery.json").read_text())["mutual_seguridad"]
    assert audit["discovered"] == 1 and audit["technical_status"] == "partial"
    health = json.loads((tmp_path / "data/source_health.json").read_text())["sources"]["mutual_seguridad"]
    assert health["coverage_completeness"] is False and health["recovery_outcome"] == "OPERATIVE_DEGRADED"
