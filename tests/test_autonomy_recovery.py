"""Security boundaries and actual failure/repair/validation for recovery."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/autonomy_recovery.py"
spec = importlib.util.spec_from_file_location("autonomy_recovery", SCRIPT)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "src/radar_salud/calculation.py"
        self.source.parent.mkdir(parents=True)
        (self.source.parent / "__init__.py").write_text("")
        self.source.write_text("def total():\n    return 1\n", encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests/test_calculation.py").write_text(
            'import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parents[1] / "src"))\n'
            "from radar_salud.calculation import total\n\ndef test_total():\n    assert total() == 2\n",
            encoding="utf-8",
        )
        self.log = "FAILED tests/test_calculation.py::test_total - AssertionError: assert 1 == 2"
        self.command = [sys.executable, "-m", "pytest", "-q", "tests/test_calculation.py::test_total"]

    def plan(self, *, name="src/radar_salud/calculation.py", old="return 1", new="return 2"):
        path = self.root / name
        return {"schema_version": 1, "replacements": [{"path": name, "sha256": recovery.digest(path.read_bytes()), "old": old, "new": new}]}

    def init_repo(self, branch="staging"):
        def git(*args):
            return subprocess.run(["git", *args], cwd=self.root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()
        git("init", "-b", branch)
        git("config", "user.name", "Recovery Test")
        git("config", "user.email", "recovery@example.test")
        git("add", "src", "tests")
        git("commit", "-m", "fixture")
        return git

    @staticmethod
    def mocked_runner(*codes):
        remaining = iter(codes)
        def run(command, root):
            code = next(remaining)
            return {"command": command, "returncode": code, "output": "FAILED tests/test_calculation.py::test_total - AssertionError" if code else "1 passed"}
        return run

    def test_exact_replacement_preserves_unrelated_content(self):
        prepared = recovery.validate_plan(self.root, self.plan())
        recovery.apply_changes(self.root, prepared)
        self.assertEqual(self.source.read_text(), "def total():\n    return 2\n")
        recovery.restore_changes(self.root, prepared)
        self.assertEqual(self.source.read_text(), "def total():\n    return 1\n")

    def test_entire_plan_is_validated_before_any_mutation(self):
        another = self.root / "src/radar_salud/other.py"
        another.write_text("def other():\n    return 1\n")
        plan = self.plan()
        plan["replacements"].append({"path": "src/radar_salud/other.py", "sha256": "0" * 64, "old": "return 1", "new": "return 2"})
        with self.assertRaisesRegex(recovery.RecoveryError, "Stale file hash"):
            recovery.validate_plan(self.root, plan)
        self.assertIn("return 1", self.source.read_text())

    def test_repeated_old_text_is_not_ambiguous(self):
        self.source.write_text("x = 1\ny = 1\n")
        with self.assertRaisesRegex(recovery.RecoveryError, "exactly once"):
            recovery.validate_plan(self.root, self.plan(old="1", new="2"))

    def test_missing_old_text_and_identical_replacement_rejected(self):
        for old, new in [("not present", "value"), ("return 1", "return 1"), ("", "value")]:
            with self.subTest(old=old), self.assertRaises(recovery.RecoveryError):
                recovery.validate_plan(self.root, self.plan(old=old, new=new))

    def test_traversal_workflows_tests_and_secret_paths_rejected(self):
        names = ["../outside.py", "/tmp/outside.py", "src//radar_salud/calculation.py", "src/../scripts/a.py",
            "src\\radar_salud\\calculation.py", ".github/workflows/recovery.yml", "tests/test_calculation.py",
            "config/auth.json", "src/radar_salud/ai_budget.py", "src/radar_salud/editorial_gate.py",
            "scripts/autonomy_recovery.py", "web/auth/login.js", "web/.env.json"]
        names += ["scripts/review_candidate.py", "scripts/package_pages.py", "scripts/smoke_release.py"]
        for name in names:
            with self.subTest(name=name), self.assertRaises(recovery.RecoveryError):
                recovery.safe_path(self.root, name)

    def test_symlink_and_symlink_parent_rejected(self):
        target = self.root / "target.py"
        target.write_text("return 1")
        self.source.unlink()
        self.source.symlink_to(target)
        with self.assertRaisesRegex(recovery.RecoveryError, "Symlink"):
            recovery.safe_path(self.root, "src/radar_salud/calculation.py")
        self.source.unlink()
        (self.source.parent / "__init__.py").unlink()
        self.source.parent.rmdir()
        self.source.parent.symlink_to(self.root)
        with self.assertRaisesRegex(recovery.RecoveryError, "Symlink"):
            recovery.safe_path(self.root, "src/radar_salud/target.py")

    def test_hardlink_rejected(self):
        os.link(self.source, self.root / "copy.py")
        with self.assertRaisesRegex(recovery.RecoveryError, "Hard-linked"):
            recovery.safe_path(self.root, "src/radar_salud/calculation.py")

    def test_candidate_python_and_json_syntax_rejected_before_write(self):
        with self.assertRaisesRegex(recovery.RecoveryError, "syntax invalid"):
            recovery.validate_plan(self.root, self.plan(new="return ("))
        data = self.root / "web/data.json"
        data.parent.mkdir()
        data.write_text('{"value": 1}')
        with self.assertRaisesRegex(recovery.RecoveryError, "syntax invalid"):
            recovery.validate_plan(self.root, self.plan(name="web/data.json", old="1", new="NaN ???"))
        self.assertIn("return 1", self.source.read_text())

    def test_limits_and_duplicate_paths_fail_closed(self):
        plan = self.plan()
        plan["replacements"] *= 2
        with self.assertRaisesRegex(recovery.RecoveryError, "Duplicate"):
            recovery.validate_plan(self.root, plan)
        for new in ["2" * recovery.MAX_REPLACEMENT_BYTES, "\x00"]:
            with self.subTest(new_len=len(new)), self.assertRaises(recovery.RecoveryError):
                recovery.validate_plan(self.root, self.plan(new=new))

    def test_schema_rejects_extra_fields_and_duplicate_json_keys(self):
        plan = self.plan()
        plan["commands"] = ["git push origin main"]
        with self.assertRaises(recovery.RecoveryError):
            recovery.validate_plan(self.root, plan)
        for raw in ['{"schema_version":1,"schema_version":1,"replacements":[]}', "```json\n{}\n```", "diff --git a/x b/x"]:
            with self.subTest(raw=raw), self.assertRaises(recovery.RecoveryError):
                recovery.parse_plan(raw)

    def test_context_is_selected_from_failure_and_imports(self):
        unrelated = self.root / "web/unrelated.js"
        unrelated.parent.mkdir()
        unrelated.write_text("unrelated")
        context = recovery.select_context(self.root, self.log)
        by_path = {item["path"]: item for item in context}
        self.assertFalse(by_path["tests/test_calculation.py"]["editable"])
        self.assertTrue(by_path["src/radar_salud/calculation.py"]["editable"])
        self.assertNotIn("web/unrelated.js", by_path)
        with self.assertRaisesRegex(recovery.RecoveryError, "unobserved"):
            recovery.validate_plan(self.root, self.plan(), allowed_paths={"web/unrelated.js"})

    def test_sensitive_files_never_enter_context_and_known_credentials_redacted(self):
        sensitive = self.root / "src/radar_salud/secrets.py"
        sensitive.write_text("secret value")
        self.assertEqual(recovery.select_context(self.root, "src/radar_salud/secrets.py"), [])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sensitive-openai-secret"}):
            text = recovery.redact("sensitive-openai-secret password=other-secret")
        self.assertNotIn("sensitive-openai-secret", text)
        self.assertNotIn("other-secret", text)

    def test_target_command_cannot_execute_log_supplied_options(self):
        command = recovery.targeted_command(self.root, self.log + "\n--override-ini=addopts=--ignore=tests")
        self.assertEqual(command, self.command)

    def test_stale_apply_detected_without_overwriting_concurrent_work(self):
        prepared = recovery.validate_plan(self.root, self.plan())
        self.source.write_text("def total():\n    return 3\n")
        with self.assertRaisesRegex(recovery.RecoveryError, "Concurrent mutation"):
            recovery.apply_changes(self.root, prepared)
        self.assertIn("return 3", self.source.read_text())

    def test_rollback_does_not_overwrite_new_concurrent_mutation(self):
        prepared = recovery.validate_plan(self.root, self.plan())
        recovery.apply_changes(self.root, prepared)
        self.source.write_text("def total():\n    return 3\n")
        with self.assertRaisesRegex(recovery.RecoveryError, "Concurrent mutation"):
            recovery.restore_changes(self.root, prepared)
        self.assertIn("return 3", self.source.read_text())

    def test_green_target_runs_full_gate_without_model_or_mutation(self):
        result = recovery.recover(self.root, {}, self.log, allow_model=True, runner=self.mocked_runner(0, 0, 0))
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["validated"])
        self.assertEqual(result["changed_paths"], [])
        self.assertEqual(result["evidence"][1]["command"], [sys.executable, "-m", "pytest", "-q"])

    def test_infrastructure_failure_never_calls_model(self):
        def unavailable(command, root):
            return {"command": command, "returncode": 1, "output": "No module named pytest"}
        with patch.object(recovery, "generate_plan", side_effect=AssertionError("must not call")):
            result = recovery.recover(self.root, {}, self.log, allow_model=True, runner=unavailable)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("infrastructure", result["blocker"])

    def test_main_product_mutation_is_forbidden(self):
        self.init_repo("main")
        result = recovery.recover(self.root, {}, self.log, patch=self.plan(), runner=self.mocked_runner(1, 1))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("main/detached", result["blocker"])
        self.assertIn("return 1", self.source.read_text())

    def test_failed_project_gate_rolls_back_and_never_stages(self):
        git = self.init_repo()
        result = recovery.recover(self.root, {}, self.log, patch=self.plan(), stage=True, runner=self.mocked_runner(1, 0, 0, 1))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(result["rolled_back"])
        self.assertEqual(result["changed_paths"], [])
        self.assertEqual(git("status", "--porcelain"), "")

    def test_browser_gate_mandatory_when_project_has_package_json(self):
        self.init_repo()
        (self.root / "package.json").write_text('{"scripts":{"test":"node test.js"}}')
        result = recovery.recover(self.root, {}, self.log, patch=self.plan(), runner=self.mocked_runner(1, 0, 0, 0, 1))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["evidence"][-1]["command"], ["npm", "test"])
        self.assertIn("return 1", self.source.read_text())

    def test_existing_staged_files_are_not_absorbed(self):
        git = self.init_repo()
        unrelated = self.root / "unrelated.txt"
        unrelated.write_text("keep")
        git("add", "unrelated.txt")
        result = recovery.recover(self.root, {}, self.log, patch=self.plan(), stage=True, runner=self.mocked_runner(1, 1))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(git("diff", "--cached", "--name-only"), "unrelated.txt")

    def test_real_failure_is_recovered_and_only_validated_path_staged(self):
        git = self.init_repo()
        unrelated = self.root / "unrelated.txt"
        unrelated.write_text("must remain untracked")
        before = recovery.run_command(self.command, self.root)
        self.assertNotEqual(before["returncode"], 0)
        self.assertIn("AssertionError", before["output"])
        result = recovery.recover(self.root, {"signature": "unit_test"}, self.log, patch=self.plan(), stage=True)
        self.assertEqual(result["status"], "REPAIRED", result)
        self.assertTrue(result["validated"])
        self.assertEqual(result["changed_paths"], ["src/radar_salud/calculation.py"])
        self.assertEqual(git("diff", "--cached", "--name-only"), "src/radar_salud/calculation.py")
        self.assertIn("?? unrelated.txt", git("status", "--porcelain"))
        self.assertEqual([entry["returncode"] for entry in result["evidence"]], [1, 1, 0, 0, 0])

    def test_verified_repair_survives_unchanged_unrelated_project_failure(self):
        git = self.init_repo()
        unrelated = "FAILED tests/test_unrelated.py::test_other - AssertionError: unrelated baseline"
        outputs = iter([(1, self.log), (1, self.log + "\n" + unrelated), (0, "1 passed"), (1, unrelated), (0, "")])
        def runner(command, root):
            code, output = next(outputs)
            return {"command": command, "returncode": code, "output": output}
        result = recovery.recover(self.root, {}, self.log, patch=self.plan(), stage=True, runner=runner)
        self.assertEqual(result["status"], "REPAIRED_CANDIDATE", result)
        self.assertTrue(result["partial_candidate"])
        self.assertTrue(result["targeted_validated"])
        self.assertTrue(result["no_new_failures"])
        self.assertFalse(result["validated"])
        self.assertEqual(git("diff", "--cached", "--name-only"), "")
        self.assertIn("return 2", self.source.read_text())
        self.assertLess(len(result["non_regression"]["candidate_failures"]), len(result["non_regression"]["baseline_failures"]))

    def test_generated_asset_is_read_only_and_canonical_source_enters_context(self):
        (self.root / "app.js").write_text("const count = 1;\n")
        (self.root / "web").mkdir()
        (self.root / "web/app.js").write_text("const count = 1;\n")
        with self.assertRaisesRegex(recovery.RecoveryError, "canonical source"):
            recovery.safe_path(self.root, "web/app.js")
        paths = {item["path"]: item for item in recovery.select_context(self.root, "web/app.js:30 Error")}
        self.assertTrue(paths["app.js"]["editable"])
        self.assertFalse(paths["web/app.js"]["editable"])

    def test_live_external_failure_is_exact_blocker_without_model(self):
        payload = {"slug": "diario_financiero", "technical_status": "error", "error": "HTTPError: HTTP Error 403: Forbidden", "requests": [{"status": "FAIL", "error": "HTTP Error 403", "url": "https://source.test"}]}
        def runner(command, root):
            return {"command": command, "returncode": 1, "output": "AUTONOMY_SOURCE_JSON=" + json.dumps(payload)}
        with patch.object(recovery, "generate_plan", side_effect=AssertionError("must not call")):
            result = recovery.recover(self.root, {}, "source failed", source_slug="diario_financiero", allow_model=True, runner=runner)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("403", result["blocker"])
        self.assertEqual(len(result["evidence"]), 1)

    def test_live_slug_cannot_supply_an_arbitrary_command(self):
        result = recovery.recover(self.root, {}, "source failed", source_slug="--evil-shell", runner=self.mocked_runner())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("allowlist", result["blocker"])

    def test_live_parser_repair_requires_live_rerun_and_project_validation(self):
        parser = self.root / "src/radar_salud/source_scouts.py"
        parser.write_text("def discover():\n    return 1\n")
        self.init_repo()
        failed = {"slug": "diario_financiero", "technical_status": "error", "error": "ValueError: unexpected date schema", "discovered": 0, "dated": 0, "requests": [{"status": "PASS"}]}
        passed = {"slug": "diario_financiero", "technical_status": "ok", "error": None, "discovered": 1, "dated": 1, "requests": [{"status": "PASS"}]}
        outputs = iter([(1, "AUTONOMY_SOURCE_JSON=" + json.dumps(failed)), (0, "1 passed"), (0, "AUTONOMY_SOURCE_JSON=" + json.dumps(passed)), (0, "1 passed"), (0, "")])
        def runner(command, root):
            code, output = next(outputs)
            return {"command": command, "returncode": code, "output": output}
        result = recovery.recover(self.root, {}, "source failed", source_slug="diario_financiero", patch=self.plan(name="src/radar_salud/source_scouts.py"), runner=runner)
        self.assertEqual(result["status"], "REPAIRED", result)
        self.assertTrue(result["live_validated"])
        self.assertTrue(result["targeted_validated"])
        self.assertTrue(result["validated"])

    def test_existing_no_paid_ai_policy_blocks_model_before_any_call(self):
        (self.root / "config").mkdir()
        (self.root / "config/autopilot.json").write_text('{"ai_builder_enabled": false}')
        with patch.dict(os.environ, {"RADAR_REPAIR_MODEL": "existing-model", "OPENAI_API_KEY": "test-api-key"}):
            with self.assertRaisesRegex(recovery.RecoveryError, "disables"):
                recovery.generate_plan(self.root, [], "failure", {})

    def test_model_requires_shared_task_bound_approved_budget_reservation(self):
        (self.root / "config").mkdir()
        (self.root / "config/autopilot.json").write_text('{"ai_builder_enabled": true}')
        with patch.dict(os.environ, {"RADAR_REPAIR_MODEL": "existing-model", "OPENAI_API_KEY": "test-api-key"}):
            with self.assertRaisesRegex(recovery.RecoveryError, "reservation unavailable"):
                recovery.generate_plan(self.root, [], "failure", {"id": "task-1"})
            ledger = self.root / "reservation.json"
            ledger.write_text(json.dumps({"reservations": {"reservation-1": {"state": "reserved", "task_id": "other-task", "model": "existing-model"}}}))
            task = {"id": "task-1", "repair_budget_reservation": {"artifact": str(ledger), "sha256": recovery.digest(ledger.read_bytes()), "reservation_id": "reservation-1"}}
            with self.assertRaisesRegex(recovery.RecoveryError, "does not authorize"):
                recovery.generate_plan(self.root, [], "failure", task)

    def test_relative_existing_budget_import_and_reserved_model_response(self):
        (self.root / "config").mkdir()
        (self.root / "config/autopilot.json").write_text('{"ai_builder_enabled": true}')
        ledger = self.root / "reservation.json"
        ledger.write_text(json.dumps({"reservations": {"reservation-1": {"state": "reserved", "task_id": "task-1", "model": "existing-model"}}}))
        task = {"id": "task-1", "repair_budget_reservation": {"artifact": str(ledger), "sha256": recovery.digest(ledger.read_bytes()), "reservation_id": "reservation-1"}}
        (self.source.parent / "paths.py").write_text('APPROVED = True\n')
        (self.source.parent / "ai_budget.py").write_text(
            'from .paths import APPROVED\n'
            'def allow_call(kind):\n    return APPROVED and kind == "deep"\n'
            'def record_result(kind, success):\n    assert kind == "deep" and success\n')
        calls = []
        plan = self.plan()
        class Client:
            def __init__(self, **kwargs):
                self.responses = self
            def create(self, **kwargs):
                calls.append(kwargs)
                return types.SimpleNamespace(output_text=json.dumps(plan))
        with patch.dict(os.environ, {"RADAR_REPAIR_MODEL": "existing-model", "OPENAI_API_KEY": "test-api-key"}), patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=Client)}):
            result = recovery.generate_plan(self.root, [], "AssertionError", task)
        self.assertEqual(result, plan)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "existing-model")
        self.assertEqual(calls[0]["reasoning"], {"effort": "high"})


if __name__ == "__main__":
    unittest.main()
