from datetime import datetime, timezone

from src.radar_salud.public_source_catalog import build_catalog


def test_sources_outside_daily_capture_are_labelled_as_trial():
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    base = {"status": "warning", "technical_status": "ok", "coverage_status": "observed",
            "checked_at": "2026-10-11T16:07:31+00:00"}
    sources = {"global_who": {**base, "name": "OMS", "operation_mode": "isolated_qualification"},
               "minsal": {**base, "name": "MINSAL"}}
    rows = {r["id"]: r for r in build_catalog(sources, now=now)["sources"]}
    assert rows["global_who"]["description"].endswith("En prueba: sin consulta diaria.")
    assert "superficie de metadatos verificada" not in rows["global_who"]["description"]
    assert "En prueba" not in rows["minsal"]["description"]
