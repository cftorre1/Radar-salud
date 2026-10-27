"""datos.gob.cl (CKAN) data releases: Dirección 27-oct-2026, decision (a).

Fixtures are the real package_search responses captured from GitHub Actions
on 11-oct-2026 (runs 38117618594 and 38117181348, sha256-named files).
"""
from datetime import date
import json
from pathlib import Path

import pytest

from radar_salud.datos_gob_sources import (DatosGobScout, parse_package_search, process_datos_gob,
                                           query_url, live_lane_enabled)
from radar_salud.processing import DeferredProcessing

RUNS = Path(__file__).resolve().parents[1] / "data/audits/public_sources_c_20261011/recovery/runs"
FONASA = RUNS / "38117618594/captures/16a36dc92d59e1da36982c7b864e908b371d3529a0c5bc5d87cedad11b023490.html"
DEIS = RUNS / "38117181348/captures/972013294a6609f0d50d91985809e91e6ba6634c51db4ffd930868a1c54fc392.html"
CFG = {"slug": "datos_gob_cl", "name": "datos.gob.cl", "source_type": "official", "base_confidence": 100,
       "default_category": "Datos sectoriales", "force_category": True}


def deis_payload():
    # The DEIS capture answered q=DEIS; scope it as the organization query would.
    payload = json.loads(DEIS.read_text())
    payload["result"]["results"] = [r for r in payload["result"]["results"]
                                    if r["organization"]["name"] == "ministerio_de_salud"]
    payload["result"]["count"] = len(payload["result"]["results"])
    return payload


def test_real_fonasa_catalog_has_no_release_in_window_and_says_so():
    payload = json.loads(FONASA.read_text())
    items, report = parse_package_search(payload, "fondo_nacional_de_salud", api_url=query_url("fondo_nacional_de_salud"),
                                         today=date(2026, 10, 11), window_days=30)
    # Real finding: FONASA's datos.gob.cl catalog was last modified in 2015.
    assert items == [] and report["catalog_count"] == 14 and report["window_complete"]
    assert report["latest_metadata_modified"] == "2015-10-30"


def test_real_deis_releases_inside_window_become_labelled_data_release_items():
    items, report = parse_package_search(deis_payload(), "ministerio_de_salud",
                                         api_url=query_url("ministerio_de_salud"), today=date(2026, 10, 11),
                                         window_days=30)
    assert len(items) == 4 and report["window_complete"]
    dates = sorted(raw.event_date for raw in items)
    assert dates == ["2026-09-25", "2026-10-06", "2026-10-06", "2026-10-07"]  # Chile calendar day
    raw = next(r for r in items if "Establecimientos" in r.title)
    assert raw.url.startswith("https://datos.gob.cl/dataset/") and raw.url.endswith("#liberacion-2026-10")
    assert raw.source_name == "DEIS-MINSAL (datos.gob.cl)" and raw.metadata["data_release_scope"] == "data"
    meta = raw.metadata
    assert meta["date_basis"] == "data_release" and meta["release_kind"] == "dataset_update"
    assert meta["publication_date_evidence"]["kind"] == "ckan:metadata_modified"
    assert meta["publication_date_evidence"]["basis"] == "data_release_not_news_publication"
    assert meta["terms_policy"] == "catalog_metadata_and_links_only" and meta["license_id"] == "cc-zero"
    assert any(r["updated_in_window"] and r["format"] == "csv" for r in meta["resources"])


def test_window_excludes_older_updates_and_unverified_publishers():
    payload = deis_payload()
    items, _ = parse_package_search(payload, "ministerio_de_salud", api_url=query_url("ministerio_de_salud"),
                                    today=date(2026, 10, 11), window_days=10)
    assert {r.event_date for r in items} == {"2026-10-06", "2026-10-07"}
    for row in payload["result"]["results"]:
        row["tags"], row["author_email"], row["notes"] = [], None, "Otro departamento"
    items, report = parse_package_search(payload, "ministerio_de_salud", api_url=query_url("ministerio_de_salud"),
                                         today=date(2026, 10, 11), window_days=30)
    assert items == [] and all(x["reason"] == "publisher_scope_not_verified" for x in report["excluded"])


def test_deterministic_card_is_data_not_news_and_passes_editorial_gate():
    from radar_salud.editorial_gate import publication_ready
    items, _ = parse_package_search(deis_payload(), "ministerio_de_salud", api_url=query_url("ministerio_de_salud"),
                                    today=date(2026, 10, 11), window_days=30)
    row = process_datos_gob(items[0], CFG)
    assert row["signal_types"] == ["Datos"] and row["date_basis"] == "data_release"
    assert row["publication_date"] is None and row["data_release_date"] == row["event_date"]
    assert "no una noticia" in row["why_it_matters"] and "datos.gob.cl" in row["what_happened"]
    assert publication_ready(row)[0], publication_ready(row)


def test_tampered_release_evidence_is_deferred():
    items, _ = parse_package_search(deis_payload(), "ministerio_de_salud", api_url=query_url("ministerio_de_salud"),
                                    today=date(2026, 10, 11), window_days=30)
    raw = items[0]
    raw.metadata["publication_date_evidence"]["value"] = "2026-01-01T00:00:00"
    with pytest.raises(DeferredProcessing):
        process_datos_gob(raw, CFG)


def test_scout_respects_robots_and_partial_failures():
    calls = []

    def fetch(url):
        calls.append(url)
        if "fondo_nacional" in url:
            raise TimeoutError("timeout")
        return json.dumps(deis_payload()).encode(), {"sha256": "x" * 64, "captured_at": "2026-10-11T12:00:00+00:00"}

    scout = DatosGobScout(fetch=fetch, today=date(2026, 10, 11), window_days=30, enabled=True, robots=lambda url: True)
    items = scout.discover()
    assert len(items) == 4 and scout.diagnostics["partial_failure"]
    assert scout.diagnostics["errors"][0]["organization"] == "fondo_nacional_de_salud"
    blocked = DatosGobScout(fetch=fetch, today=date(2026, 10, 11), enabled=True, robots=lambda url: False)
    with pytest.raises(RuntimeError):
        blocked.discover()


def test_lane_never_runs_inside_tests_unless_forced():
    assert live_lane_enabled({"RADAR_CAPTURE_EVIDENCE": "1", "PYTEST_CURRENT_TEST": "x"}) is False
    assert live_lane_enabled({"RADAR_CAPTURE_EVIDENCE": "1"}) is True
    assert live_lane_enabled({"RADAR_DATOS_GOB": "0", "RADAR_CAPTURE_EVIDENCE": "1"}) is False
    assert DatosGobScout().discover() == []


def test_metadata_only_change_is_labelled_catalog_update():
    payload = deis_payload()
    for row in payload["result"]["results"]:
        for resource in row["resources"]:
            resource["last_modified"] = resource["created"] = "2024-01-01T00:00:00"
    items, _ = parse_package_search(payload, "ministerio_de_salud", api_url=query_url("ministerio_de_salud"),
                                    today=date(2026, 10, 11), window_days=30)
    raw = items[0]
    assert raw.metadata["data_release_scope"] == "catalog" and "ficha de catálogo" in raw.metadata["release_action"]
    # Same identity (url + title) as the data-update variant of that month.
    data_items, _ = parse_package_search(deis_payload(), "ministerio_de_salud", api_url=query_url("ministerio_de_salud"),
                                         today=date(2026, 10, 11), window_days=30)
    twin = next(r for r in data_items if r.metadata["dataset_id"] == raw.metadata["dataset_id"])
    from radar_salud.pending_queue import fingerprint
    assert twin.metadata["data_release_scope"] == "data" and fingerprint(twin) == fingerprint(raw)
    row = process_datos_gob(raw, CFG)
    assert row["data_release_scope"] == "catalog" and "sin recurso nuevo" in row["what_happened"]
