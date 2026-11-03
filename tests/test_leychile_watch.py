"""Dirección 3-nov-2026: BCN LeyChile probe + no-AI watch of key health norms.

Offline only. Fixtures under tests/fixtures/leychile are SYNTHETIC (see their
header comments): bcn.cl / leychile.cl were unreachable from the development
session, so the real response shape is first observed by the daily CI run.
"""
import json
import socket
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from radar_salud import leychile_watch as lw

FIX = Path(__file__).parent / "fixtures" / "leychile"
NORM = (FIX / "norma_ley_19966_synthetic.xml").read_bytes()
SEARCH = (FIX / "search_dfl_synthetic.xml").read_bytes()
CONFIG = json.loads(Path("config/bcn_leychile_watch.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access in a LeyChile test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def law_xml(numero, norma_id, version="2024-06-01"):
    """Synthetic norm XML for another law number (same synthetic shape)."""
    return (NORM.replace(b"<Numero>19966</Numero>", f"<Numero>{numero}</Numero>".encode())
            .replace(b'normaId="900001"', f'normaId="{norma_id}"'.encode())
            .replace(b'fechaVersion="2024-06-01"', f'fechaVersion="{version}"'.encode()))


class FakeService:
    """Answers opt=7 by idLey/idNorma and opt=61 search; records every request."""

    def __init__(self, versions=None, search=SEARCH, errors=None):
        self.versions = versions or {}
        self.search = search
        self.errors = errors or {}
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        key = q.get("idLey") or q.get("idNorma") or ("search" if q.get("opt") == "61" else None)
        if key in self.errors:
            raise HTTPError(url, self.errors[key], "synthetic", {}, None)
        if q.get("opt") == "61":
            return self.search, {"sha256": "s", "http_status": 200}
        ids = {"19966": "900001", "20584": "900002", "21674": "900003", "900101": "900101"}
        numero = {"900001": "19966", "900002": "20584", "900003": "21674"}.get(key, key)
        if key == "900101":
            body = (NORM.replace(b"<Tipo>Ley</Tipo><Numero>19966</Numero>",
                                 b"<Tipo>Decreto con Fuerza de Ley</Tipo><Numero>1</Numero>")
                    .replace(b'normaId="900001"', b'normaId="900101"')
                    .replace(b'fechaPromulgacion="2004-08-25"', b'fechaPromulgacion="2005-07-23"')
                    .replace(b'fechaPublicacion="2004-09-03"', b'fechaPublicacion="2006-04-24"')
                    .replace(b'fechaVersion="2024-06-01"', f'fechaVersion="{self.versions.get(key, "2024-06-01")}"'.encode()))
            return body, {"sha256": "d", "http_status": 200, "final_url": url}
        return law_xml(numero, ids.get(numero, key), self.versions.get(numero, "2024-06-01")), {
            "sha256": f"sha-{numero}", "http_status": 200, "final_url": url}


def scout(tmp_path, service, day, robots=lambda url: True, **kw):
    return lw.LeyChileWatchScout(state_path=tmp_path / "state.json", config=CONFIG, fetch_fn=service,
                                 robots=robots, today=day, enabled=True, now=lambda: f"{day}T12:00:00+00:00", **kw)


def state(tmp_path):
    return json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))


def test_parse_norm_keeps_metadata_only():
    meta = lw.parse_norm(NORM)
    assert meta["id_norma"] == "900001"
    assert meta["fecha_version"] == "2024-06-01" and meta["fecha_version_basis"] == "root@fechaVersion"
    assert meta["fecha_publicacion"] == "2004-09-03" and meta["fecha_promulgacion"] == "2004-08-25"
    assert meta["tipos_numeros"] == [{"tipo": "Ley", "numero": "19966"}]
    assert meta["organismos"] == ["MINISTERIO DE SALUD"]
    assert "SENTINEL" not in json.dumps(meta)
    with pytest.raises(ValueError):
        lw.parse_norm(b"<?xml version='1.0'?><!DOCTYPE x [<!ENTITY a 'b'>]><Norma/>")
    with pytest.raises(ValueError, match="unexpected root"):
        lw.parse_norm(b"<html><body>error</body></html>")
    with pytest.raises(ValueError, match="fechaVersion"):
        lw.parse_norm(b"<Norma><Identificador><TiposNumeros><TipoNumero><Tipo>Ley</Tipo>"
                      b"<Numero>1</Numero></TipoNumero></TiposNumeros></Identificador></Norma>")


def test_lane_disabled_in_tests_does_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("RADAR_LEYCHILE", raising=False)
    service = FakeService()
    s = lw.LeyChileWatchScout(state_path=tmp_path / "state.json", config=CONFIG, fetch_fn=service, robots=lambda u: True)
    assert s.discover() == []
    assert service.urls == [] and not (tmp_path / "state.json").exists()
    assert s.diagnostics["status"] == "not_run_outside_engine_runtime"
    assert lw.live_lane_enabled({"RADAR_CAPTURE_EVIDENCE": "1"}) is True
    assert lw.live_lane_enabled({"RADAR_CAPTURE_EVIDENCE": "1", "RADAR_LEYCHILE": "0"}) is False


def test_robots_denial_fetches_nothing_and_health_records_it(tmp_path):
    service = FakeService()
    s = scout(tmp_path, service, date(2026, 11, 4), robots=lambda url: False)
    with pytest.raises(PermissionError, match="robots_disallowed"):
        s.discover()
    assert service.urls == []
    st = state(tmp_path)
    assert st["probe"]["passed"] is False and "robots_disallowed" in st["probe"]["failure"]
    assert st["runs"][-1]["status"] == "robots_disallowed" and st["candidates"] == []
    assert s.diagnostics["probe_status"].startswith("failed: PermissionError: robots_disallowed")
    assert s.diagnostics["published"] == 0
    # A later run the same Chile day requests nothing and still reports the failure.
    service2 = FakeService()
    again = scout(tmp_path, service2, date(2026, 11, 4))
    with pytest.raises(RuntimeError, match="probe_failed_today"):
        again.discover()
    assert service2.urls == []


def test_baseline_then_change_held_for_review_never_published(tmp_path):
    service = FakeService()
    s = scout(tmp_path, service, date(2026, 11, 4))
    assert s.discover() == []  # nothing ever enters the queue
    st = state(tmp_path)
    assert st["probe"]["passed"] is True and st["probe"]["norm"] == "ley_19966"
    assert st["endpoint"]["base"] == lw.ENDPOINTS[0]
    assert service.urls[0] == "https://www.leychile.cl/Consulta/obtxml?opt=7&idLey=19966"
    assert st["norms"]["ley_19966"]["status"] == "watching"
    assert st["norms"]["ley_19966"]["id_norma"] == "900001"
    assert st["norms"]["ley_19966"]["resolution_basis"] == "opt7_idLey_response_normaId"
    assert st["norms"]["ley_19966"]["link"] == "https://www.bcn.cl/leychile/navegar?idNorma=900001"
    assert set(st["runs"][-1]["baselines"]) == {"ley_19966", "ley_20584", "ley_21674"}
    assert st["candidates"] == []  # first run: baseline only, no change signals
    assert st["norms"]["dfl_1_2005_salud"]["status"] == "resolved_pending_first_fetch"
    assert st["norms"]["dfl_1_2005_salud"]["id_norma"] == "900101"  # unique identity match (Salud, 2005)
    assert st["norms"]["ds_3_1984_salud"]["status"] == "unresolved"
    assert st["norms"]["ds_3_1984_salud"]["unresolved_reason"] == "search_no_identity_match"
    assert "SENTINEL" not in json.dumps(st)
    # At most one request per norm per day: a later run the same day stays offline.
    n = len(service.urls)
    assert len({u for u in service.urls}) == n == 5
    assert scout(tmp_path, service, date(2026, 11, 4)).discover() == []
    assert len(service.urls) == n
    # Next day: Ley 20.584 has a newer version; the DFL gets its first (baseline) fetch.
    service.versions = {"20584": "2026-11-05"}
    nxt = scout(tmp_path, service, date(2026, 11, 5))
    nxt.discover()
    st = state(tmp_path)
    assert [c["norm_key"] for c in st["candidates"]] == ["ley_20584"]
    c = st["candidates"][0]
    assert c["status"] == "held_for_review" and c["published"] is False and c["ai_used"] is False
    assert c["title"] == ("Se modificó la Ley N° 20.584 (derechos y deberes de las personas en su atención de salud) "
                          "(versión vigente desde 05-11-2026)")
    assert c["previous_fecha_version"] == "2024-06-01" and c["fecha_version"] == "2026-11-05"
    assert c["link"] == "https://www.bcn.cl/leychile/navegar?idNorma=900002"
    assert st["norms"]["dfl_1_2005_salud"]["status"] == "watching"
    assert "dfl_1_2005_salud" in st["runs"][-1]["baselines"]
    assert nxt.diagnostics["changes_this_run"] == ["ley_20584"]
    assert nxt.diagnostics["candidates_held_for_review"] == 1 and nxt.diagnostics["published"] == 0
    # The same version seen again does not duplicate the candidate.
    scout(tmp_path, service, date(2026, 11, 6)).discover()
    assert len(state(tmp_path)["candidates"]) == 1


def test_probe_identity_mismatch_stops_the_pass(tmp_path):
    service = FakeService()
    original = service.__call__

    def wrong(url):
        body, cap = original(url)
        return body.replace(b"<Numero>19966</Numero>", b"<Numero>19967</Numero>"), cap
    s = scout(tmp_path, wrong, date(2026, 11, 4))
    with pytest.raises(RuntimeError, match="identity_mismatch"):
        s.discover()
    assert len(service.urls) == 1
    st = state(tmp_path)
    assert st["probe"]["passed"] is False and st["probe"]["identity_problems"] == ["tipo_numero"]
    assert "endpoint" not in st and st["norms"]["ley_19966"]["status"] == "identity_mismatch"


def test_probe_http_error_and_fallback_endpoint(tmp_path):
    hits = []

    def service(url):
        hits.append(url)
        if url.startswith(lw.ENDPOINTS[0]):
            raise HTTPError(url, 404, "synthetic", {}, None)
        return FakeService()(url)
    s = scout(tmp_path, service, date(2026, 11, 4))
    s.discover()
    assert hits[:2] == [f"{lw.ENDPOINTS[0]}?opt=7&idLey=19966", f"{lw.ENDPOINTS[1]}?opt=7&idLey=19966"]
    assert state(tmp_path)["endpoint"]["base"] == lw.ENDPOINTS[1]
    assert all(u.startswith(lw.ENDPOINTS[1]) for u in hits[1:])
    # A 500 on the probe is a failure (no fallback, nothing else requested).
    service2 = FakeService(errors={"19966": 500})
    with pytest.raises(HTTPError):
        scout(tmp_path / "b", service2, date(2026, 11, 4)).discover()
    assert len(service2.urls) == 1
    assert state(tmp_path / "b")["probe"]["http_status"] == 500


def test_later_norm_errors_are_partial_and_429_stops(tmp_path):
    service = FakeService(errors={"20584": 503})
    s = scout(tmp_path, service, date(2026, 11, 4))
    s.discover()
    st = state(tmp_path)
    assert st["norms"]["ley_20584"]["last_http_status"] == 503 and st["runs"][-1]["status"] == "ok_partial"
    assert s.diagnostics["partial_failure"] is True and st["norms"]["ley_21674"]["status"] == "watching"
    service2 = FakeService(errors={"20584": 429})
    with pytest.raises(PermissionError, match="rate_limited"):
        scout(tmp_path / "b", service2, date(2026, 11, 4)).discover()
    assert not any("21674" in u for u in service2.urls)


def test_unresolved_until_endpoint_verified_and_never_guessed(tmp_path):
    cfg = {**CONFIG, "probe_norm": "ley_19966"}
    service = FakeService(search=b"<Resultado><Mensaje>sin resultados</Mensaje></Resultado>")
    s = lw.LeyChileWatchScout(state_path=tmp_path / "state.json", config=cfg, fetch_fn=service,
                              robots=lambda u: True, today=date(2026, 11, 4), enabled=True)
    s.discover()
    st = state(tmp_path)
    for key in ("dfl_1_2005_salud", "ds_3_1984_salud"):
        assert st["norms"][key]["status"] == "unresolved"
        assert st["norms"][key]["unresolved_reason"] == "search_no_parsable_candidates"
        assert st["norms"][key].get("id_norma") is None
    assert s.diagnostics["unresolved"] == ["dfl_1_2005_salud", "ds_3_1984_salud"]

def test_ambiguous_search_is_never_resolved_by_picking_one(tmp_path):
    two_salud = SEARCH.replace(b"MINISTERIO DE HACIENDA", b"MINISTERIO DE SALUD").replace(b"2005-01-10", b"2005-03-10")
    s = scout(tmp_path, FakeService(search=two_salud), date(2026, 11, 4))
    s.discover()
    dfl = state(tmp_path)["norms"]["dfl_1_2005_salud"]
    assert dfl["status"] == "unresolved" and dfl["unresolved_reason"] == "search_ambiguous_identity_match"
    assert dfl.get("id_norma") is None and dfl["search"]["matches"] == ["900101", "900102"]


def test_redirect_targets_are_robots_checked_before_following(monkeypatch):
    from urllib import request as ur
    from urllib.request import Request
    seen, captured = [], {}

    def allowed(url):
        seen.append(url)
        return "bloqueado" not in url

    def fake_build_opener(handler):
        captured["handler"] = handler
        raise RuntimeError("stop before network")
    monkeypatch.setattr(ur, "build_opener", fake_build_opener)
    with pytest.raises(RuntimeError, match="stop before network"):
        lw._robots_aware_fetch("https://www.leychile.cl/Consulta/obtxml?opt=7&idLey=1", allowed, 10)
    h = captured["handler"]
    req = Request("https://www.leychile.cl/Consulta/obtxml?opt=7&idLey=1")
    with pytest.raises(PermissionError, match="robots_disallowed"):
        h.redirect_request(req, None, 302, "Found", {}, "https://www.bcn.cl/bloqueado/x")
    with pytest.raises(ValueError, match="official"):
        h.redirect_request(req, None, 302, "Found", {}, "https://evil.example/x")
    assert seen == ["https://www.bcn.cl/bloqueado/x"]


def test_processor_never_publishes():
    from radar_salud.models import RawItem
    from radar_salud.processing import RejectedProcessing
    with pytest.raises(RejectedProcessing, match="never_published"):
        lw.process_leychile_watch(RawItem(lw.SLUG, "x", "https://www.bcn.cl/leychile/navegar?idNorma=1", lw.SOURCE_NAME,
                                          "official"), {})


def test_registration_config_and_engine():
    from radar_salud import engine_cli
    from radar_salud.public_source_catalog import CATALOG
    sources = {s["slug"]: s for s in json.loads(Path("config/sources.json").read_text(encoding="utf-8"))}
    assert sources[lw.SLUG]["cadence"] == "daily" and sources[lw.SLUG]["publication"] == "held_for_review"
    policy = json.loads(Path("config/source_freshness_policy.json").read_text(encoding="utf-8"))
    assert lw.SLUG in policy["activated_daily_2026_11_03"]
    assert lw.SLUG in set(engine_cli.DETERMINISTIC_SOURCES) & set(engine_cli.PUBLIC_DATA_SOURCES)
    assert engine_cli.LeyChileWatchScout is lw.LeyChileWatchScout
    assert lw.SLUG not in CATALOG  # not listed publicly until a reviewer approves the evidence
    keys = [n["key"] for n in CONFIG["norms"]]
    assert keys == ["ley_19966", "dfl_1_2005_salud", "ley_20584", "ds_3_1984_salud", "ley_21674"]
    assert all(n["id_norma"] is None for n in CONFIG["norms"])  # never guessed
    assert "CC BY-NC-SA" in CONFIG["license_note"] and "CC BY-SA 3.0 CL" in CONFIG["license_note"]


def test_engine_daily_run_records_probe_and_publishes_nothing(tmp_path, monkeypatch):
    """engine_cli.main with only this lane enabled: health/discovery evidence, empty queue and history."""
    import shutil
    import sys
    from radar_salud import engine_cli, paths
    from radar_salud.pending_queue import PendingQueue
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "config").mkdir()
    for name in ("sources.json", "bcn_leychile_watch.json"):
        shutil.copy(root / "config" / name, tmp_path / "config" / name)
    (tmp_path / "data/state").mkdir(parents=True)
    service = FakeService()

    def transport(url, allowed, limit):
        assert allowed(url)
        return service(url)
    robots_seen = []

    def robots_txt(url, hosts, **kw):
        robots_seen.append(url)
        return b"User-agent: *\nDisallow: /privado/\n", {}
    monkeypatch.setattr(lw, "_robots_aware_fetch", transport)
    monkeypatch.setattr(lw, "open_fetch", robots_txt)
    monkeypatch.setenv("RADAR_LEYCHILE", "1")
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setattr(engine_cli, "seed_from_history", lambda root: None)
    recorded = {}
    monkeypatch.setattr(engine_cli, "health_record", lambda root, slug, **kw: recorded.setdefault(slug, kw))
    monkeypatch.setattr(sys, "argv", ["engine_cli", "--sources", "bcn_leychile_watch", "--discovery-only"])
    engine_cli.main()
    run = json.loads((tmp_path / "data/state/discovery_run.json").read_text())
    row = run["sources"]["bcn_leychile_watch"]
    assert row["technical_status"] == "ok" and row["error_type"] is None
    assert row["diagnostics"]["probe_status"] == "passed"
    assert row["diagnostics"]["probe"]["evidence"]["url"] == "https://www.leychile.cl/Consulta/obtxml?opt=7&idLey=19966"
    assert row["diagnostics"]["robots"] == {"www.leychile.cl": "parsed"}
    assert robots_seen == ["https://www.leychile.cl/robots.txt"]
    health = recorded["bcn_leychile_watch"]
    assert health["published"] == 0 and health["diagnostics"]["published"] == 0
    assert PendingQueue(tmp_path / "data/state/pending_queue.json").items == {}
    assert not (tmp_path / "data/history/superintendencia_signals.json").exists()
    st_path = tmp_path / "data/state/bcn_leychile_watch.json"
    st = json.loads(st_path.read_text(encoding="utf-8"))
    assert st["probe"]["passed"] and st["candidates"] == [] and "SENTINEL" not in st_path.read_text(encoding="utf-8")
