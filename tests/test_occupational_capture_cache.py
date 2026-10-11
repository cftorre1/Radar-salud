import hashlib
import json
import pytest
from radar_salud.occupational_capture import CaptureLoader
from radar_salud.occupational_sources import SourceDiscoveryError


def record(folder, url, body, stamp="2026-10-11T00:00:00+00:00", status=200):
    folder.mkdir(parents=True, exist_ok=True)
    name=hashlib.sha256(url.encode()).hexdigest()+".body"
    (folder/name).write_bytes(body)
    return dict(url=url, final_url=url, user_agent="identified", captured_at=stamp, artifact_dir=str(folder),
        stop_reason="response_captured", http_status=status, waf=None,
        hops=[dict(body_file=name, sha256=hashlib.sha256(body).hexdigest(), http_status=status, tls={"verified":True})])


def test_current_origin_probe_overrides_previous_cached_listing(tmp_path):
    url="https://ist.cl/noticias/"
    prior=tmp_path/"prior";fresh=tmp_path/"fresh"
    old=record(prior,url,b"old archive")
    (prior/"capture_index.json").write_text(json.dumps({url:old}))
    new=record(fresh,url,b"current archive","2026-10-11T01:00:00+00:00")
    (fresh/"report.json").write_text(json.dumps({"records":[new]}))
    loader=CaptureLoader(tmp_path/"result",cache=prior,probe=fresh/"report.json")
    assert loader._body(loader._request(url)) == "current archive"
    assert loader.evidence(url)["captured_at"] == new["captured_at"]


def test_replay_has_no_network_fallback_and_still_verifies_bytes(tmp_path,monkeypatch):
    url="https://ist.cl/noticias/"
    prior=tmp_path/"prior";r=record(prior,url,b"archive")
    (prior/"capture_index.json").write_text(json.dumps({url:r}))
    def forbidden(*args,**kwargs):
        raise AssertionError("replay must never use network")
    monkeypatch.setattr("radar_salud.occupational_capture.capture",forbidden)
    loader=CaptureLoader(tmp_path/"result",replay=prior)
    with pytest.raises(SourceDiscoveryError,match="replay_capture_missing"):
        loader._request("https://ist.cl/uncaptured/")
    (prior/r["hops"][0]["body_file"]).write_bytes(b"tampered")
    with pytest.raises(SourceDiscoveryError,match="capture_hash_mismatch"):
        loader._body(r)


def test_public_robots_denial_prevents_article_request(tmp_path,monkeypatch):
    prior=tmp_path/"prior"
    url="https://ist.cl/robots.txt"
    r=record(prior,url,b"User-agent: *\nDisallow: /private/\n")
    (prior/"capture_index.json").write_text(json.dumps({url:r}))
    def forbidden(*args,**kwargs):
        raise AssertionError("robots must stop prohibited requests")
    monkeypatch.setattr("radar_salud.occupational_capture.capture",forbidden)
    loader=CaptureLoader(tmp_path/"result",cache=prior)
    with pytest.raises(SourceDiscoveryError,match="robots_disallowed"):
        loader("https://ist.cl/private/article")

