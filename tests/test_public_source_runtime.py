import importlib.util
import json
from pathlib import Path
from urllib.error import URLError

from radar_salud import engine_cli
from radar_salud.deis_sources import DeisDocumentScout
from radar_salud.fonasa_sources import FonasaNewsScout, FonasaDataHubScout
from radar_salud.isp_sources import IspAnamedAlertScout, IspSurveillanceScout
from radar_salud.models import RawItem


spec=importlib.util.spec_from_file_location("public_source_check",Path("scripts/check_public_sources.py"))
monitor=importlib.util.module_from_spec(spec);spec.loader.exec_module(monitor)


def test_daily_runtime_uses_strict_source_modules():
    assert engine_cli.FonasaNewsScout is FonasaNewsScout
    assert engine_cli.FonasaDataHubScout is FonasaDataHubScout
    assert engine_cli.IspAnamedAlertScout is IspAnamedAlertScout
    assert engine_cli.IspSurveillanceScout is IspSurveillanceScout
    assert engine_cli.DeisDocumentScout is DeisDocumentScout


def test_live_poll_records_exact_proxy_failure_without_mutating_ingestion(tmp_path):
    state=tmp_path/"data/state";state.mkdir(parents=True)
    protected={"discovery_watermarks.json":"{\"deis\":\"old\"}","deis_seen.json":"[\"keep\"]",
               "pending_queue.json":"{\"keep\":true}"}
    for name,body in protected.items():(state/name).write_text(body)
    health_path=tmp_path/"data/source_health.json"
    health_path.write_text(json.dumps({"sources":{"other":{"checked_at":"do not change","status":"ok"}}}))
    class Blocked:
        SOURCE_SLUG="deis";SOURCE_NAME="DEIS"
        diagnostics={"listing_url":"https://deis.minsal.cl/centrofic/"}
        def discover(self):raise URLError("Tunnel connection failed: 403 Forbidden")
    result=monitor.check(tmp_path,record_health=True,factories=[Blocked])
    row=result["sources"]["deis"]
    assert row["operational"] is False and row["technical_status"]=="error"
    assert row["error_details"]["transport_stage"]=="proxy_connect_rejected"
    health=json.loads(health_path.read_text())["sources"]
    assert health["deis"]["coverage_status"]=="unverified"
    assert health["other"]=={"checked_at":"do not change","status":"ok"}
    assert all((state/name).read_text()==body for name,body in protected.items())
    assert result["ai_calls"]==0 and not result["ingestion_state_mutated"]


def test_listing_success_with_failed_pdf_cannot_be_operational(tmp_path,monkeypatch):
    class Listed:
        SOURCE_SLUG="deis";SOURCE_NAME="DEIS"
        diagnostics={}
        def discover(self):
            kind="official_document_listing:published";listing="https://deis.minsal.cl/centrofic/"
            return [RawItem("deis","Orientaciones de codificación", "https://repositoriodeis.minsal.cl/guide.pdf",
                "DEIS","official",event_date="2026-06-25",metadata={"discovered_from":listing,
                "publication_date_source":kind,"publication_date_evidence":{"kind":kind,
                "value":"Publicado 25/06/2026","date":"2026-06-25","url":listing}})]
    monkeypatch.setattr(monitor,"extract_public_source_pdf",lambda *a,**kw:"")
    row=monitor.check(tmp_path,record_health=True,factories=[Listed])["sources"]["deis"]
    assert row["discovery_verified"] and not row["operational"]
    assert row["technical_status"]=="degraded"
    assert row["diagnostics"]["evidence_status"]=="capture_pending"
    assert row["diagnostics"]["document_checks"][0]["status"]=="blocked"
    assert not row["operative_degraded"]


def test_degraded_operation_requires_an_actual_readable_primary_document(tmp_path,monkeypatch):
    class Listed:
        SOURCE_SLUG="deis";SOURCE_NAME="DEIS"
        diagnostics={}
        def discover(self):
            listing="https://deis.minsal.cl/centrofic/";kind="official_document_listing:published"
            return [RawItem("deis", "Orientaciones de codificación", "https://repositoriodeis.minsal.cl/"+name+".pdf",
                "DEIS", "official",event_date="2026-06-25",metadata={"discovered_from":listing,
                "publication_date_source":kind,"publication_date_evidence":{"kind":kind,
                "value":"Publicado 25/06/2026","date":"2026-06-25","url":listing}})
                for name in ['readable','oversized']]
    def capture(url,*args,**kwargs):
        if 'oversized' in url: raise ValueError('Public-source capture exceeds the byte limit')
        return 'Official guidance with verified readable content. '*20
    monkeypatch.setattr(monitor,"extract_public_source_pdf",capture)
    row=monitor.check(tmp_path,factories=[Listed])["sources"]["deis"]
    assert row["runtime_outcome"]=="OPERATIVE_DEGRADED"
    assert row["operative_degraded"] and not row["operational"]
