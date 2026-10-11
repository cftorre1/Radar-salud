import importlib.util
import json
import sys
from pathlib import Path

from radar_salud import engine_cli, paths
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue
from radar_salud.processing import DeferredProcessing
from radar_salud.source_health import record

ROOT = Path(__file__).resolve().parents[1]


def test_provider_sources_enter_daily_durable_queue_without_ai(tmp_path, monkeypatch):
    configs = json.loads((ROOT / "config/sources.json").read_text())
    expected = {"red_davila", "andes_salud", "clinicas_achs_salud"}
    assert expected <= {r["slug"] for r in configs}
    class Empty:
        def __init__(self, *args, **kwargs): pass
        def discover(self, *args, **kwargs): return []
    class Provider(Empty):
        def __init__(self, slug): self.slug = slug
        def discover(self):
            if self.slug not in expected: return []
            return [RawItem(self.slug, "Nueva capacidad clínica con convenio Fonasa",
                            f"https://example.org/{self.slug}", self.slug, "corporate", "2026-09-23")]
    for name in ("SuperintendenciaStatsScout", "SuperintendenciaNormativaScout",
                 "SuperintendenciaFiscalizacionScout", "MinsalNewsScout", "SusesoNormativeScout",
                 "SusesoNewsScout", "SusesoFiscalizacionScout", "DfHealthScout", "FonasaDataHubScout",
                 "FonasaNewsScout", "IspSurveillanceScout", "IspAnamedAlertScout", "ClinicasChileScout",
                 "DeisResourceScout", "DiarioOficialHealthScout", "CorporateNewsroomScout"):
        monkeypatch.setattr(engine_cli, name, Empty)
    monkeypatch.setattr(engine_cli, "CuratedBetaSourceScout", Provider)
    monkeypatch.setattr(engine_cli, "load_sources", lambda path: configs)
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setattr(engine_cli, "seed_from_history", lambda root: None)
    monkeypatch.setattr(engine_cli, "has_capacity", lambda kind: False)
    monkeypatch.setattr(sys, "argv", ["engine_cli"])
    engine_cli.main()
    queue = PendingQueue(tmp_path / "data/state/pending_queue.json")
    assert {r["source"] for r in queue.items.values()} == expected
    assert all(r["status"] == "pending" and r["lane"] == "BACKFILL" for r in queue.items.values())
    engine_cli.main()
    assert len(PendingQueue(queue.path).items) == 3
    monkeypatch.setattr(engine_cli, "has_capacity", lambda kind: True)
    def deferred(raw, cfg): raise DeferredProcessing("Provider original blocked: HTTP 403")
    monkeypatch.setattr(engine_cli, "process_curated_beta_source", deferred)
    engine_cli.main()
    assert all(r["status"] == "retry" and r["deferred_detail"] == "Provider original blocked: HTTP 403"
               for r in PendingQueue(queue.path).items.values())


def test_discovery_only_health_does_not_claim_editorial_assessment(tmp_path):
    record(tmp_path, "red_davila", name="Red Dávila", discovered=5, new=0, published=0,
           evaluation_performed=False)
    health = json.loads((tmp_path / "data/source_health.json").read_text())["sources"]["red_davila"]
    assert health["technical_status"] == "ok"
    assert health["editorial_outcome"] == "not_evaluated" and health["status"] == "warning"


def test_sector_association_counts_as_provider():
    spec = importlib.util.spec_from_file_location("provider_report", ROOT / "scripts/product_report.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module._source_segments("clinicas_chile", {"system_domain": "PROVIDERS"}) == {"Prestadores"}


def test_partial_poll_error_keeps_real_publication_outcome(tmp_path):
    record(tmp_path,'redsalud',name='RedSalud',discovered=4,new=1,published=1,
           rows=[{'event_date':'2026-10-02'}],error='partial_discovery: page=4: HTTPError')
    row=json.loads((tmp_path/'data/source_health.json').read_text())['sources']['redsalud']
    assert row['technical_status']=='error' and row['coverage_status']=='unverified'
    assert row['editorial_outcome']=='published'


def test_provider_stale_original_survives_successful_technical_poll(tmp_path):
    record(tmp_path,'pfizer_chile',name='Pfizer Chile',discovered=3,new=0,published=0,latest_original_at='2023-06-08')
    row=json.loads((tmp_path/'data/source_health.json').read_text())['sources']['pfizer_chile']
    assert row['technical_status']=='ok' and row['status']=='warning'
    assert row['content_freshness']=='stale_external_surface' and row['coverage_status']=='gap'
