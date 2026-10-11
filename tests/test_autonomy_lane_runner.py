"""Adversarial runner contracts: no fake LIVE, acceptance or material progress."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("autonomy_lane_runner", Path(__file__).resolve().parents[1] / "scripts/autonomy_lane_runner.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tests").mkdir()
        (self.root / "config").mkdir()
        self.report = self.root / "artifacts/report.json"
        self.task = {"id": "approved-source-lane", "approved_at": "2026-10-11"}
        self.sha = "a" * 40

    def fake_commands(self, *, skipped=False, failure=False, full_failure=False, source_failure=False, branch="autonomy/media/test"):
        def run(command, workspace, timeout=180, **kwargs):
            result = {"command": command, "returncode": 0, "stdout": "", "stderr": ""}
            if command[0] == "git":
                result["stdout"] = branch if "symbolic-ref" in command else self.sha
            elif "--diagnose-source" in command:
                row = {"slug": command[-1], "technical_status": "ok", "discovered": 1, "dated": 1,
                       "publication_verified": False, "samples": [{"source_url": "https://source.example/item", "event_date": "2026-10-10"}],
                       "requests": [{"url": "https://source.example/listing", "status": "PASS"}]}
                if source_failure:
                    row.update(technical_status="error", error="RuntimeError: parser failed")
                    row["requests"][0].update(status="FAIL", error="HTTPError: HTTP Error 403: Forbidden")
                    result["returncode"] = 1
                result["stdout"] = "AUTONOMY_SOURCE_JSON=" + json.dumps(row)
            elif "pytest" in command:
                xml = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml=")))
                xml.parent.mkdir(parents=True, exist_ok=True)
                fail = failure or (full_failure and not any(arg.startswith("tests/") for arg in command))
                detail = '<failure message="assert 11 &gt;= 12">normative rows 11 versus 12</failure>' if fail else ('<skipped message="live beta integration needs API key"/>' if skipped else "")
                xml.write_text('<testsuites><testsuite><testcase classname="tests.test_source" name="test_real_gate">' + detail + "</testcase></testsuite></testsuites>")
                result["returncode"] = 1 if fail else 0
                result["stdout"] = "FAILED tests/test_web_snapshot.py::test_normative - assert 11 >= 12" if fail else ("1 skipped" if skipped else "1 passed")
            return result
        return run

    def install_gate(self, family):
        for name in runner.TESTS[family]:
            (self.root / "tests" / name).write_text("# gate placeholder for controlled command evidence\n")

    def execute(self, family="media", **kwargs):
        self.install_gate(family)
        with patch.object(runner, "tracked_hashes", return_value={"src/product.py": "same"}):
            return runner.execute_lane(family, self.root, self.task, self.report, command_runner=self.fake_commands(**kwargs))

    def acceptance(self, family="media", **overrides):
        evidence = self.root / "acceptance-evidence.json"
        evidence.write_text(json.dumps({"source_url": "https://source.example/item", "event_date": "2026-10-10"}))
        checks = runner.SOURCE_ACCEPTANCE if runner.FAMILIES[family] else runner.EDITORIAL_ACCEPTANCE
        payload = {"task_id": self.task["id"], "candidate_sha": self.sha, "verdict": "PASS", "sources": list(runner.FAMILIES[family]),
                   "checks": {name: True for name in checks}, "evidence": [{"path": evidence.name, "sha256": runner.digest(evidence.read_bytes())}]}
        payload.update(overrides)
        path = self.root / "acceptance.json"
        path.write_text(json.dumps(payload))
        self.task["acceptance_artifact"] = {"path": path.name, "sha256": runner.digest(path.read_bytes())}
        return path, evidence

    def test_semantic_hash_ignores_heartbeat_and_report_location_not_source_date(self):
        first = {"generated_at": "2026-10-11T02:00:00Z", "checked_at": "old", "event_date": "2026-10-10",
                 "command": ["pytest", "--junitxml=/run/1/evidence.xml"], "log_sha256": "a"}
        second = {**first, "generated_at": "2026-10-11T03:00:00Z", "checked_at": "new", "log_sha256": "b",
                  "command": ["pytest", "--junitxml=/run/2/evidence.xml"]}
        self.assertEqual(runner.semantic_hash(first), runner.semantic_hash(second))
        self.assertNotEqual(runner.semantic_hash(first), runner.semantic_hash({**second, "event_date": "2026-10-09"}))

    def test_skipped_pytest_exit_zero_is_not_live_or_acceptance_proof(self):
        report = self.execute(skipped=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["validated"])
        self.assertEqual(report["gates"][0]["status"], "SKIP")
        self.assertFalse(report["acceptance_proof"])
        self.assertFalse(report["material_progress"]["mutation_candidate"])

    def test_targeted_pass_and_dated_discovery_never_close_source_task(self):
        report = self.execute()
        self.assertEqual(report["gates"][0]["status"], "PASS")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["workflow_success_is_progress"])
        self.assertFalse(report["acceptance_proof"])
        self.assertTrue(all(row["publication_verified"] is False for row in report["source_results"]))

    def test_identical_audits_do_not_change_fingerprint_with_report_path(self):
        first = self.execute()
        self.report = self.root / "artifacts/run2/report.json"
        self.task.update(token="new-lease-token", owner="new-worker", pickup_commit="b" * 40, started_at="2026-10-11T05:00:00Z")
        second = self.execute()
        self.assertEqual(first["audit_fingerprint"], second["audit_fingerprint"])
        self.assertEqual(first["semantic_hash"], second["semantic_hash"])
        self.assertEqual(first["evidence_revision"], second["evidence_revision"])
        self.assertTrue(first["material_progress"]["requires_durable_comparison"])

    def test_explicit_revision_bound_acceptance_closes_only_complete_task(self):
        self.acceptance()
        report = self.execute()
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["acceptance_proof"][0]["verified"])
        self.assertEqual(report["acceptance_proof"][0]["candidate_sha"], self.sha)
        self.assertFalse(report["blockers"])

    def test_acceptance_rejects_changed_artifact_missing_family_or_wrong_revision(self):
        for overrides in ({"candidate_sha": "b" * 40}, {"sources": ["diario_financiero"]}, {"checks": {"qa_pass": True}}, {"task_id": "another-task"}):
            with self.subTest(overrides=overrides):
                self.acceptance(**overrides)
                proof, reason = runner.verify_acceptance(self.root, self.task, "media", self.sha)
                self.assertFalse(proof)
                self.assertTrue(reason)
        _, evidence = self.acceptance()
        evidence.write_text("Changed substantive evidence")
        proof, reason = runner.verify_acceptance(self.root, self.task, "media", self.sha)
        self.assertFalse(proof)
        self.assertIn("changed", reason)

    def test_acceptance_rejects_outside_workspace_reference(self):
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "proof.json"
            path.write_text("{}")
            self.task["acceptance_artifact"] = {"path": str(path), "sha256": runner.digest(path.read_bytes())}
            proof, reason = runner.verify_acceptance(self.root, self.task, "media", self.sha)
            self.assertFalse(proof)
            self.assertIn("outside", reason)

    def test_failure_has_reproducible_command_log_hash_and_no_human_claim(self):
        report = self.execute(failure=True)
        failing = report["gates"][0]
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["validated"])
        self.assertEqual(len(failing["log_sha256"]), 64)
        self.assertEqual(len(failing["failure_hash"]), 64)
        self.assertIn("11 >= 12", Path(failing["log_path"]).read_text())
        self.assertTrue(all(not item["human_required"] for item in report["blockers"]))

    def test_main_and_wrong_declared_sha_are_rejected_before_gate(self):
        report = self.execute(branch="main")
        self.assertFalse(report["gates"])
        self.assertEqual(report["blockers"][0]["kind"], "policy")
        self.install_gate("media")
        report = runner.execute_lane("media", self.root, self.task, self.report, input_sha="b" * 40, command_runner=self.fake_commands())
        self.assertFalse(report["gates"])

    def test_candidate_mutation_with_full_normative_failure_is_not_validated(self):
        self.install_gate("editorial")
        with patch.object(runner, "tracked_hashes", side_effect=[{"web/data/free_value.json": "before"}, {"web/data/free_value.json": "after"}]), \
             patch.object(runner, "sync_reviewed_editorial", return_value={"operation": "sync_existing_reviewed_weekly", "changed_paths": ["web/data/free_value.json"]}):
            report = runner.execute_lane("editorial", self.root, self.task, self.report, command_runner=self.fake_commands(full_failure=True))
        self.assertEqual(report["changed_paths"], ["web/data/free_value.json"])
        self.assertNotEqual(report["before_hash"], report["after_hash"])
        self.assertFalse(report["validated"])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["material_progress"]["mutation_candidate"])
        self.assertTrue(any("11 >= 12" in Path(gate["log_path"]).read_text() for gate in report["gates"] if gate["status"] == "FAIL"))

    def test_timeout_is_bounded_and_preserves_partial_failure_logs(self):
        error = subprocess.TimeoutExpired(["python", "probe"], 1, output=b"partial evidence", stderr=b"endpoint failed")
        with patch.object(runner.subprocess, "run", side_effect=error):
            result = runner.run_command(["python", "probe"], self.root, timeout=1)
        self.assertEqual(result["returncode"], 124)
        self.assertEqual(result["stdout"], "partial evidence")
        self.assertIn("endpoint failed", result["stderr"])

    def test_live_failure_attempts_automatic_recovery_despite_green_fixtures(self):
        recovery = Mock(return_value={"status": "BLOCKED", "validated": False, "blocker": "External HTTP 403 access failure"})
        with patch.object(runner, "recovery_module", return_value=SimpleNamespace(recover=recovery)):
            report = self.execute(source_failure=True)
        self.assertEqual(report["gates"][0]["status"], "PASS")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["validated"])
        self.assertTrue(report["targeted_validated"])
        self.assertFalse(report["live_validated"])
        self.assertEqual(recovery.call_count, 2)
        self.assertEqual({call.kwargs["source_slug"] for call in recovery.call_args_list}, set(runner.FAMILIES["media"]))
        proof = report["real_failure"]
        self.assertTrue(proof["verified"])
        self.assertEqual(proof["trace_sha256"], runner.digest(Path(proof["trace_path"]).read_bytes()))
        self.assertEqual(report["failure_action"], "blocked")
        technical = next(item for item in report["blockers"] if item["kind"] == "technical")
        self.assertIn("log_sha256", technical["evidence"][0])
        self.assertIn("source_urls", technical["evidence"][0])
        self.assertFalse(technical["human_required"])

    def test_partial_directed_repair_keeps_failed_full_gates_and_hashed_proof(self):
        report = {"family": "media", "validated": False}
        full = {"command": ["python", "-m", "pytest", "-q"], "returncode": 1,
                "output": "FAILED tests/test_web_snapshot.py::test_normative - assert 11 >= 12"}
        recovery = {"partial_candidate": True, "targeted_validated": True, "no_new_failures": True, "source_slug": "diario_financiero",
                    "directed_gates": [{"command": ["python", "-m", "pytest", "-q", "tests/test_press_pipeline.py"], "returncode": 0, "output": "3 passed"}],
                    "non_regression": {"verified": True, "baseline_failures": ["a" * 64], "candidate_failures": ["a" * 64],
                                       "baseline_gate": full, "candidate_gate": full}, "live_validated": True,
                    "live_gate": {"command": ["python", "lane_runner", "--diagnose-source", "diario_financiero"], "returncode": 0,
                                  "output": "Scoped real dated discovery PASS"}}
        runner.preserve_partial_proof(report, recovery, self.root / "logs", "source")
        self.assertTrue(report["partial_candidate"])
        self.assertFalse(report["validated"])
        self.assertEqual(report["candidate_scope"], "isolated")
        self.assertEqual(report["non_regression"]["candidate_gate"]["status"], "FAIL")
        self.assertEqual(report["non_regression"]["baseline_gate"]["command"], report["non_regression"]["candidate_gate"]["command"])
        self.assertEqual(report["directed_gates"][0]["status"], "PASS")
        self.assertEqual(report["live_scope"], ["diario_financiero"])
        for gate in [*report["directed_gates"], report["live_gate"], report["non_regression"]["baseline_gate"], report["non_regression"]["candidate_gate"]]:
            self.assertEqual(gate["log_sha256"], runner.digest(Path(gate["log_path"]).read_bytes()))


if __name__ == "__main__":
    unittest.main()
