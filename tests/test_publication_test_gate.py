"""Publication test gate (daily-radar.yml, 4-nov-2026): only internal-tooling tests may fail without blocking."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_test_gate as gate  # noqa: E402

POLICY = ROOT / "config/publication_test_policy.json"


def junit(tmp_path, cases):
    body = "".join(
        f'<testcase classname="{c}" name="{n}">' + (f'<{k} message="{m}"/>' if k else "") + "</testcase>"
        for c, n, k, m in cases)
    p = tmp_path / "j.xml"
    p.write_text(f'<?xml version="1.0"?><testsuites><testsuite name="pytest">{body}</testsuite></testsuites>')
    return p


def test_policy_entries_exist_and_avoid_protected_names():
    data = json.loads(POLICY.read_text(encoding="utf-8"))
    allowed, warnings = gate.load_policy(POLICY)
    assert warnings == [] and allowed == frozenset(data["non_blocking_files"])
    for entry in data["non_blocking_files"]:
        assert (ROOT / entry).is_file(), entry
    # The gate's own tests must block, otherwise the gate could be broken silently.
    assert "tests/test_publication_test_gate.py" not in allowed


@pytest.mark.parametrize("path", [
    # Every file that blocked the daily run between 20-oct and 2-nov-2026 guards data, rights or paid outputs.
    "tests/test_paywall_rights_v4_20261028.py", "tests/test_paywall_rights_v5_20261028.py",
    "tests/test_stats_fichas.py", "tests/test_provider_original_reader.py",
    "tests/test_provider_runtime_reconciliation.py", "tests/test_pulso_paid_guard_revalidation.py",
    "tests/test_pulso_actual_final12_assigned7_review.py", "tests/test_weekly_insight_a.py",
    "tests/test_normative_autorecord.py", "tests/test_web_snapshot.py", "tests/test_ai_monthly_usd_budget.py",
])
def test_data_rights_and_paid_output_tests_stay_blocking(path):
    allowed, _ = gate.load_policy(POLICY)
    assert path not in allowed


def test_protected_fragment_overrides_a_listed_file(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"non_blocking_files": ["tests/test_paywall_tooling.py", "tests/test_pmo_readiness.py"],
                             "protected_name_fragments": ["paywall"]}))
    allowed, warnings = gate.load_policy(p)
    assert allowed == {"tests/test_pmo_readiness.py"} and "paywall" in warnings[0]


def test_file_mapping():
    assert gate.test_file_of("tests.test_x.TestC", "test_y[a.b]") == "tests/test_x.py"
    assert gate.test_file_of("tests.pulso.test_z", "test_y") == "tests/pulso/test_z.py"
    assert gate.test_file_of("", "tests.test_broken") == "tests/test_broken.py"  # collection error
    assert gate.test_file_of("", "") is None


def test_decisions(tmp_path):
    nb = frozenset({"tests/test_pmo_readiness.py"})
    tooling = junit(tmp_path, [("tests.test_pmo_readiness", "test_a", "failure", "boom"),
                               ("tests.test_stats_fichas", "test_ok", None, "")])
    assert gate.decide(1, gate.failures_from_junit(tooling), nb)[:2] == (False, "only_non_blocking_failures")
    mixed = junit(tmp_path, [("tests.test_pmo_readiness", "test_a", "failure", "x"),
                             ("tests.test_paywall_rights_v4_20261028", "test_b", "failure", "KeyError: 'rights_review'")])
    blocked, reason, blocking, tolerated = gate.decide(1, gate.failures_from_junit(mixed), nb)
    assert blocked and reason == "publication_critical_failure"
    assert [f["file"] for f in blocking] == ["tests/test_paywall_rights_v4_20261028.py"] and len(tolerated) == 1
    collection = junit(tmp_path, [("", "tests.test_pmo_readiness", "error", "collection failure")])
    assert gate.decide(1, gate.failures_from_junit(collection), nb)[0] is False
    unmapped = junit(tmp_path, [("", "", "error", "internal")])
    assert gate.decide(1, gate.failures_from_junit(unmapped), nb)[0] is True
    # Fail closed on anything unexpected.
    assert gate.decide(0, None, nb) == (False, "all_tests_passed", [], [])
    for rc in (2, 3, 4, 5, -15, 124):
        assert gate.decide(rc, [], nb)[:2] == (True, f"pytest_exit_{rc}")
    assert gate.decide(1, None, nb)[:2] == (True, "junit_report_unreadable")
    assert gate.decide(1, [], nb)[:2] == (True, "pytest_failed_without_recorded_failure")


def test_main_end_to_end_with_real_pytest_junit(tmp_path):
    """Real pytest JUnit output: a failing listed tooling test passes the gate, a failing other test blocks."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_tooling_x.py").write_text("def test_a():\n    assert False, 'tooling'\n")
    (tmp_path / "tests/test_data_y.py").write_text("def test_b():\n    assert True\n")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"non_blocking_files": ["tests/test_tooling_x.py"], "protected_name_fragments": ["data"]}))
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    run = lambda: subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                  f"--junitxml={tmp_path / 'j.xml'}", "tests"], cwd=tmp_path, env=env,
                                 capture_output=True, text=True)
    rc = run().returncode
    assert rc == 1
    summary = tmp_path / "summary.md"
    os.environ["GITHUB_STEP_SUMMARY"] = str(summary)
    try:
        assert gate.main(["--junit", str(tmp_path / "j.xml"), "--pytest-rc", str(rc), "--policy", str(policy)]) == 0
        (tmp_path / "tests/test_data_y.py").write_text("def test_b():\n    assert False, 'data'\n")
        rc = run().returncode
        assert gate.main(["--junit", str(tmp_path / "j.xml"), "--pytest-rc", str(rc), "--policy", str(policy)]) == 1
        assert gate.main(["--junit", str(tmp_path / "missing.xml"), "--pytest-rc", "1", "--policy", str(policy)]) == 1
        # Unreadable policy: everything blocks.
        assert gate.main(["--junit", str(tmp_path / "j.xml"), "--pytest-rc", "1", "--policy", str(tmp_path / "nope")]) == 1
    finally:
        os.environ.pop("GITHUB_STEP_SUMMARY", None)
    assert "BLOCKED" in summary.read_text() and "PASS" in summary.read_text()


def _build_steps():
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((ROOT / ".github/workflows/daily-radar.yml").read_text(encoding="utf-8"))
    return wf["jobs"]["build"]["steps"]


def test_daily_workflow_wires_the_gate_without_ai_key():
    step = next(s for s in _build_steps() if s.get("name") == "Core deterministic tests before collection")
    assert step["env"]["OPENAI_API_KEY"] == "" and "continue-on-error" not in step
    run = step["run"]
    assert '--junitxml="$RUNNER_TEMP/core-tests.xml"' in run and "rc=${PIPESTATUS[0]}" in run
    assert run.strip().splitlines()[-1].startswith("python scripts/publication_test_gate.py")
    assert '--pytest-rc "$rc"' in run and "config/publication_test_policy.json" in run


def test_every_daily_step_that_can_stall_has_a_timeout():
    quick = {"Record beta validation status"}  # echo-only
    for s in _build_steps():
        name = s.get("name") or s.get("uses")
        if name in quick or s.get("uses", "").startswith("actions/setup-python"):
            continue
        assert isinstance(s.get("timeout-minutes"), int), name
    stats = next(s for s in _build_steps() if s.get("name") == "Statistics fichas")
    assert stats["continue-on-error"] is True and stats["timeout-minutes"] <= 30
