"""probe_source_expansion: robots.txt (RFC 9309) and per-response byte ceiling (revisión PR #71)."""
import importlib.util
import subprocess
from pathlib import Path

spec = importlib.util.spec_from_file_location("probe", Path("scripts/probe_source_expansion.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def fake_run(body, code, returncode=0):
    def run(command, **kwargs):
        assert "--max-filesize" in command
        return subprocess.CompletedProcess(command, returncode, stdout=f"{body}\n{code}", stderr="")
    return run


def test_robots_rules_disallow_and_4xx_5xx_semantics(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "ROBOTS", {})
    monkeypatch.setattr(probe.subprocess, "run", fake_run("User-agent: *\nDisallow: /privado/", 200))
    assert probe.robots_allowed("https://www.cmfchile.cl/institucional/x")
    assert not probe.robots_allowed("https://www.cmfchile.cl/privado/x")
    receipt, html = probe.fetch("https://www.cmfchile.cl/privado/x", tmp_path / "captures")
    assert receipt["transport_ok"] is False and receipt["blocked_reason"] == "robots_disallowed" and html == ""
    monkeypatch.setattr(probe, "ROBOTS", {})
    monkeypatch.setattr(probe.subprocess, "run", fake_run("", 404))
    assert probe.robots_allowed("https://www.dipres.gob.cl/a")
    monkeypatch.setattr(probe, "ROBOTS", {})
    monkeypatch.setattr(probe.subprocess, "run", fake_run("", 503))
    assert not probe.robots_allowed("https://www.dipres.gob.cl/a")


def test_every_fetch_has_a_byte_ceiling(monkeypatch, tmp_path):
    seen = []
    def run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 63, stdout="{}", stderr="Maximum file size exceeded")
    monkeypatch.setattr(probe.subprocess, "run", run)
    receipt, _ = probe.fetch_verified("https://www.cmfchile.cl/doc.pdf", tmp_path / "captures")
    assert "--max-filesize" in seen[0] and receipt["transport_ok"] is False
