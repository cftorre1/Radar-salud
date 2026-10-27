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


def test_short_names_keep_the_official_name_and_skip_identical_labels():
    # Review N3 (PR #72): narrow screens show short_name; the official name stays in the catalog.
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    base = {"status": "ok", "technical_status": "ok", "coverage_status": "observed",
            "checked_at": "2026-10-11T16:07:31+00:00"}
    sources = {"suseso": {**base, "name": "Superintendencia de Seguridad Social (SUSESO)"},
               "superintendencia": {**base, "name": "Superintendencia de Salud"},
               "pulso_latercera": {**base, "name": "Pulso / La Tercera"}}
    rows = {r["id"]: r for r in build_catalog(sources, now=now)["sources"]}
    assert rows["suseso"]["short_name"] == "SUSESO"
    assert rows["suseso"]["name"] == "Superintendencia de Seguridad Social (SUSESO)"
    assert "short_name" not in rows["superintendencia"]
    assert "short_name" not in rows["pulso_latercera"]
