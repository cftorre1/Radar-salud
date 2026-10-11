"""Connectivity-only evidence respects robots, low concurrency and state isolation."""
import hashlib
import json
from pathlib import Path
import threading
import pytest

from scripts import clinic_connectivity_diagnostic as diagnostic
from radar_salud.achs_clinics import CLINICS, NETWORK_IDENTITY_URL


def mock_probe(output, *, robots_status=200, challenge=False, exception=False):
    calls = []
    def probe(url, destination, *, ua, timeout):
        calls.append((url, ua, timeout))
        if exception: raise TimeoutError("bounded public transport failure")
        robots = url.endswith("/robots.txt")
        body = b"User-agent: *\nAllow: /\n" if robots else b"<h1>Official clinical surface</h1>"
        identity = hashlib.sha256((url + "\n" + ua).encode()).hexdigest()[:20]
        file = Path(destination) / (identity + "-0.body")
        file.write_bytes(body)
        hop = dict(url=url, http_status=robots_status if robots else 200, curl_exit=0,
                   tls={"verified": True}, waf=None, body_file=file.name,
                   sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
        record = dict(url=url, user_agent=ua, final_url=url, captured_at="2026-10-11T10:00:00Z",
                      stop_reason="response_captured", http_status=hop["http_status"],
                      waf="possible_access_challenge" if challenge and not robots else None, hops=[hop])
        file.with_name(identity + ".json").write_text(json.dumps(record))
        return record
    return probe, calls


def test_plan_contains_only_nine_confirmed_clinics_and_the_identity_hub():
    phases = diagnostic.planned_phases()
    assert len(phases[0][1]) == 3
    planned = [publisher for _, group in phases for publisher in group]
    assert len(planned) == 10 and len({row["id"] for row in planned}) == 10
    assert {row["home"] for row in planned} == {row["home"] for row in CLINICS} | {NETWORK_IDENTITY_URL}
    assert {row["news"] for row in planned if row["news"]} == {row["news"] for row in CLINICS}


def test_all_publishers_standard_captures_use_browser_only_at_home_and_no_state(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostic, "REPO_ROOT", tmp_path)
    output = tmp_path / "data/audits/source_e_recovery/clinic_connectivity_actions/test"
    output.mkdir(parents=True)
    unrelated = tmp_path / "data/state/pending_queue.json"
    unrelated.parent.mkdir(parents=True); unrelated.write_bytes(b"UNCHANGED")
    probe, calls = mock_probe(output)
    active = 0; maximum = 0; lock = threading.Lock()
    def observed_probe(*args, **kwargs):
        nonlocal active, maximum
        with lock: active += 1; maximum = max(maximum, active)
        try: return probe(*args, **kwargs)
        finally:
            with lock: active -= 1
    report = diagnostic.run_diagnostic(output, probe=observed_probe, dns_lookup=lambda host: {"host": host, "addresses_observed_only": []})
    assert report["phase"] == "completed" and report["publishers_completed"] == 10
    assert report["summary"]["successful_identified_newsrooms"] == 9
    assert len(calls) == 39 and maximum <= 2
    homes = {publisher["home"] for _, group in diagnostic.planned_phases() for publisher in group}
    assert all(url in homes for url, ua, _ in calls if ua == "browser_comparison")
    assert all(timeout == 35 for _, _, timeout in calls)
    assert unrelated.read_bytes() == b"UNCHANGED" and report["state_mutation"] is False and report["ai_calls"] == 0
    assert json.loads((output / "report.json").read_text())["publishers_completed"] == 10
    for record in report["records"]:
        last = record["hops"][-1]
        original = output / (last["body_file"].rsplit("-", 1)[0] + ".json")
        assert json.loads(original.read_text())["url"] == record["url"]
        assert hashlib.sha256((output / last["body_file"]).read_bytes()).hexdigest() == last["sha256"]


@pytest.mark.parametrize("status,expected", [(404, 4), (403, 3)])
def test_verified_robots_404_permits_listing_but_blocked_policy_does_not(tmp_path, status, expected):
    probe, calls = mock_probe(tmp_path, robots_status=status)
    result = diagnostic.diagnose_publisher(CLINICS[0], tmp_path, probe=probe, dns_lookup=lambda host: {})
    assert len(calls) == expected
    if status == 403: assert result["skipped_surfaces"][0]["reason"] == "robots_policy_unavailable"


def test_timeout_and_dns_error_do_not_abort_other_clinics_or_claim_tls(tmp_path):
    probe, calls = mock_probe(tmp_path, exception=True)
    def failed_dns(host): raise OSError("resolver failure")
    result = diagnostic.diagnose_publisher(CLINICS[0], tmp_path, probe=probe, dns_lookup=failed_dns)
    assert len(calls) == 3 and all(not diagnostic.successful(record) for record in result["records"])
    assert result["skipped_surfaces"][0]["reason"] == "robots_policy_unavailable"
    assert result["dns"]["error"].startswith("OSError:")


def test_challenge_never_triggers_listing_or_execution(tmp_path):
    probe, calls = mock_probe(tmp_path, challenge=True)
    result = diagnostic.diagnose_publisher(CLINICS[0], tmp_path, probe=probe, dns_lookup=lambda host: {})
    assert len(calls) == 3 and result["skipped_surfaces"][0]["reason"] == "publisher_challenge_observed_no_further_surface_probe"


def test_output_cannot_enter_canonical_state(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostic, "REPO_ROOT", tmp_path)
    with pytest.raises(ValueError, match="Diagnostic output"):
        diagnostic.run_diagnostic(tmp_path / "data/state", probe=lambda *args, **kwargs: pytest.fail("network unexpectedly called"))


def test_dns_uses_normal_resolver_and_observations_never_enter_curl(monkeypatch):
    calls = []
    def process(command, **kwargs):
        calls.append((command, kwargs))
        return type("Result", (), {"returncode": 0, "stdout": '[["AF_INET", "203.0.113.7"]]', "stderr": ""})()
    monkeypatch.setattr(diagnostic.subprocess, "run", process)
    result = diagnostic.observe_dns("clinicaportada.cl")
    assert result["addresses_observed_only"] == [["AF_INET", "203.0.113.7"]]
    assert calls[0][1]["timeout"] == 8 and "socket.getaddrinfo" in calls[0][0][2]
    assert calls[0][0][-1] == "clinicaportada.cl"


def test_workflow_only_triggers_own_paths_and_commits_diagnostic_directory():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/clinic-connectivity-diagnostic.yml").read_text()
    def trigger_paths(text):
        block = text.split("    paths:\n", 1)[1].split("  workflow_dispatch:", 1)[0]
        return {line.strip()[2:] for line in block.splitlines() if line.strip().startswith("- ")}
    assert trigger_paths(workflow) == {".github/workflows/clinic-connectivity-diagnostic.yml", "scripts/clinic_connectivity_diagnostic.py"}
    assert "branches: [codex/e-salud-laboral-20261011]" in workflow
    assert "--apply" not in workflow and "OPENAI_API_KEY" not in workflow and "data/state" not in workflow
    assert "git commit --only" in workflow and "clinic_connectivity_actions/${GITHUB_RUN_ID}" in workflow
    assert "refs/heads/codex/e-salud-laboral-20261011" in workflow
    core = (root / ".github/workflows/occupational-source-recovery.yml").read_text()
    assert not trigger_paths(workflow) & trigger_paths(core)
