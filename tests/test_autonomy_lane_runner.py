"""Adversarial runner contracts: no fake LIVE, acceptance or material progress."""
import importlib.util
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

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

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()

    def staging_reference(self, *, incorporated=True):
        """Use real Git ancestry; the fixture records a fetched staging reference."""
        if (self.root / ".git").exists():
            return
        self.git("init", "-b", "autonomy/media/test")
        self.git("config", "user.name", "Runner test")
        self.git("config", "user.email", "runner-test@example.invalid")
        product = self.root / "product.json"
        product.write_text('{"base":true}\n')
        self.git("add", "product.json")
        self.git("commit", "-m", "staging baseline")
        base = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/staging", base)
        product.write_text('{"candidate":true}\n')
        self.git("add", "product.json")
        self.git("commit", "-m", "isolated source candidate")
        self.sha = self.git("rev-parse", "HEAD")
        if incorporated:
            self.git("update-ref", "refs/remotes/origin/staging", self.sha)

    def tracked_json(self, payload, relative="web/data/snapshot.json"):
        self.staging_reference()
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
        self.git("add", "--", relative)
        self.git("commit", "-m", "controlled product snapshot")
        self.sha = self.git("rev-parse", "HEAD")
        return path

    def acceptance(self, family="media", **overrides):
        if runner.FAMILIES[family]:
            self.staging_reference()
        evidence = self.root / "acceptance-evidence.json"
        evidence.write_text(json.dumps({"source_url": "https://source.example/item", "event_date": "2026-10-10"}))
        checks = runner.SOURCE_ACCEPTANCE if runner.FAMILIES[family] else runner.EDITORIAL_ACCEPTANCE
        payload = {"task_id": self.task["id"], "candidate_sha": self.sha, "verdict": "PASS", "sources": list(runner.FAMILIES[family]),
                   "checks": {name: True for name in checks}, "evidence": [{"path": evidence.name, "sha256": runner.digest(evidence.read_bytes())}]}
        if runner.FAMILIES[family]:
            trace = []
            for slug in runner.FAMILIES[family]:
                record = {"source": slug, "staging_sha": self.sha, "source_url": "https://source.example/" + slug,
                          "outcome": "rejected", "runtime_evidence": {"rejected": [{"reason": "Controlled source fixture is outside editorial scope"}]}}
                command = [sys.executable, "-c", "import json; print(json.dumps(" + repr(record) + "))"]
                executed = subprocess.run(command, cwd=self.root, check=True, capture_output=True, text=True)
                log = self.root / (slug + "-runtime.log")
                log.write_text(executed.stdout)
                trace.append({**record, "command": command, "returncode": executed.returncode,
                              "log_path": log.name, "log_sha256": runner.digest(log.read_bytes())})
            runtime = self.root / "runtime-after-merge.json"
            runtime.write_text(json.dumps({"staging_sha": self.sha, "execution_after_merge": True, "trace": trace}))
            payload["staging_merge_sha"] = self.sha
            payload["evidence"].append({"path": runtime.name, "sha256": runner.digest(runtime.read_bytes()), "kind": "runtime_after_merge"})
        payload.update(overrides)
        path = self.root / "acceptance.json"
        path.write_text(json.dumps(payload))
        self.task["acceptance_artifact"] = {"path": path.name, "sha256": runner.digest(path.read_bytes())}
        return path, evidence

    def rewrite_acceptance_runtime(self, modify):
        path = self.root / "acceptance.json"
        manifest = json.loads(path.read_text())
        reference = next(item for item in manifest["evidence"] if item.get("kind") == "runtime_after_merge")
        runtime_path = self.root / reference["path"]
        runtime = json.loads(runtime_path.read_text())
        modify(runtime)
        runtime_path.write_text(json.dumps(runtime))
        reference["sha256"] = runner.digest(runtime_path.read_bytes())
        path.write_text(json.dumps(manifest))
        self.task["acceptance_artifact"]["sha256"] = runner.digest(path.read_bytes())

    def test_semantic_hash_ignores_heartbeat_and_report_location_not_source_date(self):
        first = {"generated_at": "2026-10-11T02:00:00Z", "checked_at": "old", "event_date": "2026-10-10",
                 "command": ["pytest", "--junitxml=/run/1/evidence.xml"], "log_sha256": "a"}
        second = {**first, "generated_at": "2026-10-11T03:00:00Z", "checked_at": "new", "log_sha256": "b",
                  "command": ["pytest", "--junitxml=/run/2/evidence.xml"]}
        self.assertEqual(runner.semantic_hash(first), runner.semantic_hash(second))
        self.assertNotEqual(runner.semantic_hash(first), runner.semantic_hash({**second, "event_date": "2026-10-09"}))

    def episode(self, run_id=123, sha=None):
        return {"id": "staging_qa_failed_run_" + str(run_id), "product_input_fingerprint": "same-product",
            "failure": {"run_id": run_id, "head_sha": sha or self.sha, "failure_signature": "same-demonstrated-failure",
                "run_url": "https://github.com/example/repo/actions/runs/" + str(run_id)}}

    def test_problem_identity_ignores_only_bound_episode_and_capture_metadata(self):
        first_task = self.episode()
        second_task = self.episode(456, "b" * 40)
        def evidence(task):
            return {"kind": "technical", "reason": "Gate rejected candidate", "source_urls": ["https://source.test/item"], "fingerprint": str(task["failure"]["run_id"]),
                "evidence": [{"command": [sys.executable, "scripts/review_candidate.py", "--sha", task["failure"]["head_sha"], "--output", "/artifact/" + str(task["failure"]["run_id"])],
                    "returncode": 1, "status": "FAIL", "captured_stdout_sha256": str(task["failure"]["run_id"]), "captured_stdout_bytes": task["failure"]["run_id"],
                    "failure_sha256": str(task["failure"]["run_id"]), "failure_hash": str(task["failure"]["run_id"]),
                    "source_run_id": task["failure"]["run_id"], "source_run_url": task["failure"]["run_url"], "task_id": task["id"],
                    "reviewer_proof": {"candidate_sha": task["failure"]["head_sha"], "checks": {"normative": False}, "findings": [{"reason": "assert 11 >= 12"}]}}]}
        before, after = evidence(first_task), evidence(second_task)
        original = deepcopy(before)
        self.assertEqual(runner.problem_hash(before, task=first_task, input_sha=self.sha), runner.problem_hash(after, task=second_task, input_sha="b" * 40))
        self.assertEqual(before, original)
        self.assertNotEqual(runner.semantic_hash(before), runner.semantic_hash(after))

    def test_problem_identity_preserves_actual_failure_content_and_unbound_aliases(self):
        task = self.episode()
        original = {"command": ["pytest", "--junitxml=/run/1/pytest.xml"], "returncode": 1, "status": "FAIL", "source_urls": ["https://source.test/item"],
            "pytest": {"cases": [{"name": "test_normative", "status": "FAIL", "reason": "assert 11 >= 12"}]},
            "content_hash": "a" * 64, "response_sha256": "a" * 64, "candidate_sha": "c" * 40,
            "published_at": "2026-10-10T04:00:00Z", "source_content": "Fact published 2026-10-10T04:00:00Z"}
        baseline = runner.problem_hash(original, task=task, input_sha=self.sha)
        for key, changed in (("returncode", 124), ("status", "UNVERIFIED"), ("source_urls", ["https://source.test/other"]),
            ("pytest", {"cases": [{"name": "test_other", "status": "FAIL", "reason": "assert 9 >= 12"}]}),
            ("content_hash", "b" * 64), ("response_sha256", "b" * 64), ("candidate_sha", "d" * 40),
            ("published_at", "2026-10-10T05:00:00Z"), ("source_content", "Fact published 2026-10-10T05:00:00Z")):
            with self.subTest(key=key):
                self.assertNotEqual(baseline, runner.problem_hash({**original, key: changed}, task=task, input_sha=self.sha))
        unknown_task = {"id": task["id"], "failure": task["failure"]}
        self.assertNotEqual(runner.problem_hash({"candidate_sha": self.sha}, task=unknown_task), runner.problem_hash({"candidate_sha": "b" * 40}, task=unknown_task))
        for changed_task in ({**task, "id": "staging_qa_failed_run_999"}, {**task, "product_input_fingerprint": "different-product"},
            {**task, "failure": {**task["failure"], "failure_signature": "different-failure"}}):
            with self.subTest(task=changed_task):
                self.assertNotEqual(baseline, runner.problem_hash(original, task=changed_task, input_sha=self.sha))

    def test_opaque_hash_without_actual_failure_evidence_retains_identity(self):
        first = {"returncode": 1, "status": "FAIL", "failure_hash": "a" * 64}
        self.assertNotEqual(runner.problem_hash(first), runner.problem_hash({**first, "failure_hash": "b" * 64}))
        browser = {**first, "browser_proof": {"stats": {"unexpected": 1}, "projects": ["desktop", "mobile"]}}
        self.assertNotEqual(runner.problem_hash(browser), runner.problem_hash({**browser, "failure_hash": "b" * 64}))
        # Same bound episode with only opaque log churn cannot prove new credit.
        self.assertEqual(runner.problem_hash(browser, task=self.episode()), runner.problem_hash({**browser, "failure_hash": "b" * 64}, task=self.episode()))

    def test_problem_identity_normalizes_only_log_timing_and_browser_observation_clock(self):
        first = {"output": "1 failed in 0.10s", "browser_proof": {"stats": {"unexpected": 1, "startTime": "old"}},
            "pytest": {"cases": [{"name": "test_timeout_contract", "status": "FAIL", "reason": "Expected result in 5s"}]},
            "source_content": "Published fact in 5s", "source": {"startTime": "2026-10-10T04:00:00Z"}}
        second = deepcopy(first)
        second["output"] = "1 failed in 0.90s"
        second["browser_proof"]["stats"]["startTime"] = "new"
        self.assertEqual(runner.problem_hash(first), runner.problem_hash(second))
        for field in ("assertion", "source_content", "startTime"):
            changed = deepcopy(second)
            if field == "assertion":
                changed["pytest"]["cases"][0]["reason"] = "Expected result in 6s"
            elif field == "source_content":
                changed["source_content"] = "Published fact in 6s"
            else:
                changed["source"]["startTime"] = "2026-10-10T05:00:00Z"
            with self.subTest(field=field):
                self.assertNotEqual(runner.problem_hash(first), runner.problem_hash(changed))

    def test_browser_failure_cases_preserve_executed_assertion_and_project(self):
        browser = {"suites": [{"suites": [{"specs": [{"file": "tests/browser/product.spec.cjs", "title": "normative rows", "tests": [
            {"projectName": "desktop", "expectedStatus": "passed", "status": "unexpected", "results": [{"status": "failed", "errors": [{"message": "Expected 12, received 11"}], "duration": 100}]},
            {"projectName": "mobile", "expectedStatus": "passed", "status": "expected", "results": [{"status": "passed"}]}]}]}]}]}
        cases = runner.browser_failure_cases(browser)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["project"], "desktop")
        self.assertEqual(cases[0]["results"][0]["errors"][0]["message"], "Expected 12, received 11")
        proof = {"status": "FAIL", "failure_hash": "opaque", "browser_proof": {"cases": cases}}
        changed = deepcopy(proof)
        changed["browser_proof"]["cases"][0]["results"][0]["errors"][0]["message"] = "Expected 12, received 10"
        self.assertNotEqual(runner.problem_hash(proof), runner.problem_hash(changed))

    def test_runner_repeated_qa_failure_retains_raw_logs_without_new_problem(self):
        reports = []
        for run_id, sha in ((123, "a" * 40), (456, "b" * 40)):
            self.task, self.sha = self.episode(run_id, sha), sha
            base = self.fake_commands(failure=True, branch="autonomy/staging_qa/test")
            def commands(command, workspace, timeout=180, **kwargs):
                result = base(command, workspace, timeout, **kwargs)
                if "scripts/review_candidate.py" in command:
                    proof = {"candidate_sha": sha, "checks": {"statistics": False}, "findings": [{"code": "missing_rows", "reason": "assert 11 >= 12"}]}
                    Path(command[command.index("--output") + 1]).write_text(json.dumps(proof))
                    result.update(returncode=1, stdout=json.dumps(proof))
                elif command == ["npm", "run", "test:browser"]:
                    browser = {"stats": {"expected": 32, "unexpected": 1, "skipped": 0, "startTime": str(run_id)},
                        "config": {"projects": [{"name": "desktop"}, {"name": "mobile"}]},
                        "suites": [{"specs": [{"file": "tests/browser/product.spec.cjs", "title": "normative", "tests": [
                            {"projectName": "desktop", "expectedStatus": "passed", "status": "unexpected", "results": [{"status": "failed", "errors": [{"message": "Expected 12, received 11"}]}]}]}]}]}
                    path = workspace / "artifacts/browser.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(browser))
                    result.update(returncode=1, stdout="Expected 12, received 11; captured run " + str(run_id))
                return result
            reproduction = {"status": "BLOCKED", "validated": False, "blocker": "bounded repair unavailable",
                "failure_sha256": str(run_id), "evidence": [{"returncode": 1, "output": "FAILED tests/test_web_snapshot.py::test_normative - assert 11 >= 12",
                    "captured_stdout_sha256": str(run_id)}]}
            with patch.object(runner, "tracked_hashes", return_value={"src/product.py": "same"}), \
                patch.object(runner, "recovery_module", return_value=SimpleNamespace(recover=Mock(return_value=reproduction))):
                reports.append(runner.execute_lane("staging_qa", self.root, self.task, self.report, command_runner=commands))
        self.assertEqual(reports[0]["audit_fingerprint"], reports[1]["audit_fingerprint"])
        self.assertTrue(all(report["status"] == "BLOCKED" and not report["validated"] for report in reports))
        browser_gates = [next(gate for gate in report["gates"] if gate["name"] == "browser_desktop_and_mobile") for report in reports]
        self.assertNotEqual(browser_gates[0]["failure_hash"], browser_gates[1]["failure_hash"])
        self.assertNotEqual(browser_gates[0]["log_sha256"], browser_gates[1]["log_sha256"])
        self.assertTrue(all(gate["browser_proof"]["cases"] for gate in browser_gates))

    def source_row(self, slug="diario_financiero"):
        return {"slug": slug, "technical_status": "error", "error": "RuntimeError: bounded_probe_budget: 24 requests per source",
            "discovered": 0, "dated": 0, "inventory_hash": "same-inventory", "samples": [], "publication_verified": False,
            "requests": [{"url": "https://source.test/listing", "status": "PASS", "response_sha256": "a" * 64, "response_bytes": 100},
                {"url": "https://source.test/omitted", "status": "UNVERIFIED", "error": "bounded_probe_budget: 24 requests per source"}]}

    def test_source_problem_identity_preserves_facts_without_capture_churn(self):
        first = self.source_row()
        first["observed_at"] = "2026-10-11T05:00:00Z"
        first["samples"] = [{"source_url": "https://source.test/item", "title": "Actual signal", "event_date": "2026-10-10", "content_hash": "actual-content"}]
        second = deepcopy(first)
        second["observed_at"] = "2026-10-11T06:00:00Z"
        second["requests"][0].update(response_sha256="b" * 64, response_bytes=200)
        second["requests"].reverse()
        self.assertEqual(runner.source_problem_hash(first), runner.source_problem_hash(second))
        for field in ("url", "error", "status", "inventory_hash", "dated", "title", "event_date", "content_hash"):
            changed = deepcopy(second)
            if field in {"url", "error", "status"}:
                changed["requests"][0][field] = "distinct actual evidence"
            elif field in {"title", "event_date", "content_hash"}:
                changed["samples"][0][field] = "distinct actual evidence"
            else:
                changed[field] = "distinct actual evidence"
            with self.subTest(field=field):
                self.assertNotEqual(runner.source_problem_hash(first), runner.source_problem_hash(changed))
        for opaque in ({"response_sha256": "a" * 64}, {"requests": first["requests"]}, {**first, "slug": "unknown"}):
            changed = deepcopy(opaque)
            if "requests" in changed:
                changed["requests"][0]["response_sha256"] = "b" * 64
            else:
                changed["response_sha256"] = "b" * 64
            with self.subTest(opaque=opaque):
                self.assertNotEqual(runner.source_problem_hash(opaque), runner.source_problem_hash(changed))
        captured_first = {"returncode": 1, "source_evidence": first, "output": "AUTONOMY_SOURCE_JSON=" + json.dumps(first)}
        captured_second = {"returncode": 1, "source_evidence": second, "output": "AUTONOMY_SOURCE_JSON=" + json.dumps(second)}
        self.assertEqual(runner.problem_hash(captured_first), runner.problem_hash(captured_second))
        actual_first = {"evidence": [first], "real_failure": {"source_slug": first["slug"], "source_url": "https://source.test/item", "observed_at": "old",
            "trace_path": "/run/1/log", "trace_sha256": "a" * 64, "failure_signature": "a" * 64}}
        actual_second = {"evidence": [second], "real_failure": {**actual_first["real_failure"], "observed_at": "new", "trace_path": "/run/2/log",
            "trace_sha256": "b" * 64, "failure_signature": "b" * 64}}
        self.assertEqual(runner.problem_hash(actual_first), runner.problem_hash(actual_second))
        self.assertNotEqual(runner.problem_hash(actual_first["real_failure"]), runner.problem_hash(actual_second["real_failure"]))
        unrelated_first, unrelated_second = deepcopy(actual_first), deepcopy(actual_second)
        unrelated_first["real_failure"]["source_slug"] = "unknown"
        unrelated_second["real_failure"]["source_slug"] = "unknown"
        self.assertNotEqual(runner.problem_hash(unrelated_first), runner.problem_hash(unrelated_second))
        duplicated = deepcopy(second)
        duplicated["requests"].append(deepcopy(duplicated["requests"][0]))
        self.assertNotEqual(runner.source_problem_hash(first), runner.source_problem_hash(duplicated))

    def test_budget_only_scope_is_incomplete_not_external_failure_even_without_exception(self):
        for error in (None, "RuntimeError: bounded_probe_budget: 24 requests per source"):
            row = self.source_row()
            row["error"] = error
            result = runner.classify_source_probe(row)
            self.assertEqual(result["technical_status"], "incomplete")
            self.assertEqual(result["failure_origin"], "instrumentation_limit")
            self.assertFalse(result["probe_complete"])
            self.assertEqual(result["error"], error)
            self.assertEqual(result["probe_budget"]["max_requests"], 24)
        for actual in ("HTTPError: HTTP Error 403: Forbidden", "UnicodeEncodeError: ascii URL encoding failed"):
            row = self.source_row()
            row["technical_status"] = "incomplete"
            row["requests"].append({"url": "https://source.test/real-failure", "status": "FAIL", "error": actual})
            result = runner.classify_source_probe(row)
            self.assertEqual(result["technical_status"], "error")
            self.assertFalse(result["probe_complete"])
        row = self.source_row()
        row["error"] = "ValueError: independent parser schema error"
        self.assertEqual(runner.classify_source_probe(row)["technical_status"], "error")

    def test_source_component_covered_probe_hash_is_redundant_but_other_opaque_gate_remains(self):
        row = self.source_row()
        component = {"kind": "technical", "reason": "Scoped source failed", "source_urls": ["https://source.test/listing"],
            "evidence": [{"command": ["python", "runner.py", "--diagnose-source", row["slug"]], "returncode": 1, "failure_hash": "a" * 64}, row,
                {"automated_recovery": {"status": "BLOCKED", "blocker": "Cannot repair source"}}]}
        changed = deepcopy(component)
        changed["evidence"][0]["failure_hash"] = "b" * 64
        self.assertEqual(runner.problem_hash(component), runner.problem_hash(changed))
        opaque = {"kind": "technical", "reason": "Opaque independent failure", "evidence": [{"command": ["npm", "test"], "returncode": 1, "failure_hash": "unique"}]}
        report = {"blockers": [component, opaque], "evidence": component["evidence"] + opaque["evidence"]}
        same = {"blockers": [changed, opaque], "evidence": changed["evidence"] + opaque["evidence"]}
        self.assertEqual(runner.problem_hash(report), runner.problem_hash(same))
        distinct = deepcopy(same)
        distinct["blockers"][1]["evidence"][0]["failure_hash"] = "different unique failure"
        distinct["evidence"] = distinct["blockers"][0]["evidence"] + distinct["blockers"][1]["evidence"]
        self.assertNotEqual(runner.problem_hash(report), runner.problem_hash(distinct))

    def test_correcting_guard_classification_and_skipping_misdirected_repair_is_not_new_problem(self):
        row = self.source_row()
        classified = runner.classify_source_probe(row)
        self.assertEqual(runner.source_problem_hash(row), runner.source_problem_hash(classified))
        old = {"kind": "technical", "reason": "Scoped live discovery failed: " + row["slug"],
            "source_urls": ["https://source.test/listing"], "evidence": [
                {"command": ["python", "runner.py", "--diagnose-source", row["slug"]], "returncode": 1, "status": "FAIL", "failure_hash": "a" * 64},
                row, {"automated_recovery": {"status": "BLOCKED", "blocker": "Model lane disabled", "evidence": [
                    {"returncode": 1, "source_evidence": deepcopy(row), "output": "retained raw diagnostic"}]}}]}
        corrected = deepcopy(old)
        corrected.update(kind="instrumentation", reason="Scoped coverage INCOMPLETE: internal request budget reached: " + row["slug"])
        corrected["evidence"][1] = classified
        corrected["evidence"][2] = {"automated_recovery": {"attempted": False, "reason": "Instrumentation limit is not a demonstrated source failure"}}
        corrected["evidence"][0]["failure_hash"] = "b" * 64
        old_report = {"reason": old["reason"], "blockers": [old], "evidence": old["evidence"],
            "real_failure": {"kind": "source_runtime", "source_slug": row["slug"], "verified": True, "source_url": "https://source.test/listing"}}
        corrected_report = {"reason": corrected["reason"], "blockers": [corrected], "evidence": corrected["evidence"]}
        before = deepcopy(old_report)
        self.assertEqual(runner.problem_hash(old_report), runner.problem_hash(corrected_report))
        self.assertEqual(old_report, before)
        normalized = runner.problem_semantic(old_report)
        self.assertEqual(normalized["blockers"][0]["kind"], "instrumentation")
        self.assertEqual(normalized["reason"], "Scoped source coverage incomplete: " + row["slug"])
        self.assertNotIn("real_failure", normalized)
        self.assertTrue(old_report["real_failure"]["verified"])
        self.assertEqual(old_report["blockers"][0]["evidence"][0]["returncode"], 1)
        self.assertEqual(old_report["blockers"][0]["evidence"][0]["status"], "FAIL")
        unknown_url = deepcopy(old_report)
        unknown_url["real_failure"]["source_url"] = "https://source.test/independent-new-url"
        self.assertNotEqual(runner.problem_hash(unknown_url), runner.problem_hash(corrected_report))

    def test_guard_canonicalization_preserves_mixed_failures_and_opaque_independent_repair(self):
        for actual in ("HTTPError: HTTP Error 403: Forbidden", "UnicodeEncodeError: ascii URL encoding failed",
                "ValueError: parser assertion date 2026-10-11", "ValueError: parser assertion bounded_probe_budget: 24 requests per source"):
            row = self.source_row()
            if actual.startswith("ValueError"):
                row["error"] = actual
            else:
                row["requests"].append({"url": "https://source.test/real-failure", "status": "FAIL", "error": actual})
            component = {"kind": "technical", "reason": "Real source failure", "evidence": [row,
                {"automated_recovery": {"status": "BLOCKED", "blocker": "Model disabled"}}]}
            corrected = deepcopy(component)
            corrected["evidence"][1] = {"automated_recovery": {"attempted": False, "reason": "Skipped"}}
            with self.subTest(actual=actual):
                self.assertFalse(runner.source_probe_incomplete(row))
                self.assertEqual(runner.classify_source_probe(row)["technical_status"], "error")
                self.assertNotEqual(runner.problem_hash(component), runner.problem_hash(corrected))
                status_changed = deepcopy(row)
                status_changed["technical_status"] = "incomplete"
                self.assertNotEqual(runner.source_problem_hash(row), runner.source_problem_hash(status_changed))
        guarded = {"kind": "technical", "reason": "Our guard", "evidence": [self.source_row()]}
        opaque = {"kind": "technical", "reason": "Independent repair", "evidence": [{"automated_recovery": {"failure_hash": "unknown-a"}}]}
        report = {"blockers": [guarded, opaque]}
        changed = deepcopy(report)
        changed["blockers"][1]["evidence"][0]["automated_recovery"]["failure_hash"] = "unknown-b"
        self.assertNotEqual(runner.problem_hash(report), runner.problem_hash(changed))

    def test_actual_source_worker_enforces_cap_and_records_incomplete_scope(self):
        for mixed in (False, True):
            scouts = SimpleNamespace()
            def fetch(url, *args, **kwargs):
                if mixed and url.endswith("/1"):
                    raise HTTPError(url, 403, "Forbidden", None, None)
                return "<html>controlled source response</html>"
            original = Mock(side_effect=fetch)
            scouts.fetch_html = original
            class ControlledScout:
                def discover(self):
                    rows = []
                    for index in range(30):
                        url = "https://source.test/item/" + str(index)
                        try:
                            scouts.fetch_html(url)
                        except (RuntimeError, HTTPError):
                            continue
                        rows.append(SimpleNamespace(url=url, title="Controlled scoped item", event_date="2026-10-10", raw_text="body"))
                    return rows
            names = ("DfHealthScout", "FonasaNewsScout", "FonasaDataHubScout", "IspAnamedAlertScout", "IspSurveillanceScout", "DeisResourceScout", "SusesoFiscalizacionScout")
            source_scouts = SimpleNamespace(**{name: ControlledScout for name in names})
            package = SimpleNamespace(source_scouts=source_scouts, scouts=scouts, beta_sources=SimpleNamespace(),
                beta_sources_fast=SimpleNamespace(FastCuratedBetaSourceScout=lambda slug: ControlledScout()),
                superintendencia_fiscalizacion=SimpleNamespace(SuperintendenciaFiscalizacionScout=ControlledScout))
            output = io.StringIO()
            with patch.dict(sys.modules, {"radar_salud": package}), redirect_stdout(output):
                code = runner.source_worker("diario_financiero")
            row = json.loads(output.getvalue().partition("=")[2])
            with self.subTest(mixed=mixed):
                self.assertEqual(code, 1)
                self.assertEqual(original.call_count, 24)
                self.assertEqual(row["technical_status"], "error" if mixed else "incomplete")
                self.assertEqual(row["dated"], 23 if mixed else 24)
                self.assertEqual(row["probe_budget"], {"max_requests": 24, "executed_requests": 24, "unexecuted_requests": 6})
                self.assertEqual(sum(request["status"] == "FAIL" for request in row["requests"]), int(mixed))
                if mixed:
                    self.assertIn("HTTP Error 403", row["requests"][1]["error"])

    def test_runner_budget_scope_never_creates_verified_source_failure_or_recovery_credit(self):
        for mixed in (False, True):
            self.install_gate("media")
            base = self.fake_commands()
            def commands(command, workspace, timeout=180, **kwargs):
                result = base(command, workspace, timeout, **kwargs)
                if "--diagnose-source" in command:
                    row = self.source_row(command[-1])
                    if mixed:
                        row["requests"].append({"url": "https://source.test/real-failure", "status": "FAIL", "error": "HTTPError: HTTP Error 403: Forbidden"})
                    result.update(returncode=1, stdout="AUTONOMY_SOURCE_JSON=" + json.dumps(row))
                return result
            recover = Mock(return_value={"status": "BLOCKED", "validated": False, "blocker": "External HTTP 403"})
            with patch.object(runner, "tracked_hashes", return_value={"src/product.py": "same"}), \
                patch.object(runner, "recovery_module", return_value=SimpleNamespace(recover=recover)):
                report = runner.execute_lane("media", self.root, self.task, self.report, command_runner=commands)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertFalse(report["validated"])
            self.assertFalse(report["live_validated"])
            if mixed:
                self.assertTrue(report["real_failure"]["verified"])
                self.assertEqual(report["real_failure"]["source_url"], "https://source.test/real-failure")
                self.assertEqual(recover.call_count, 2)
            else:
                self.assertFalse(report.get("real_failure", {}).get("verified", False))
                self.assertEqual(recover.call_count, 0)
                self.assertTrue(all(row["technical_status"] == "incomplete" for row in report["source_results"]))
                self.assertTrue(any(b["kind"] == "instrumentation" and "INCOMPLETE" in b["reason"] for b in report["blockers"]))

    def test_actual_git_clock_only_json_edit_is_not_a_publishable_mutation(self):
        payload = {"generated_at": "2026-10-11T04:00:00Z", "signals": [{"title": "Unchanged material signal", "event_date": "2026-10-10"}]}
        path = self.tracked_json(payload)
        self.install_gate("editorial")
        def change_clock(workspace):
            path.write_text(json.dumps({**payload, "generated_at": "2026-10-11T05:00:00Z"}, indent=2))
            return {"operation": "controlled_clock_update", "changed_paths": ["web/data/snapshot.json"]}
        with patch.object(runner, "sync_reviewed_editorial", side_effect=change_clock):
            report = runner.execute_lane("editorial", self.root, self.task, self.report, command_runner=self.fake_commands())
        self.assertEqual(report["before_hash"], report["after_hash"])
        self.assertNotEqual(report["raw_before_hash"], report["raw_after_hash"])
        self.assertEqual(report["raw_changed_paths"], ["web/data/snapshot.json"])
        self.assertEqual(report["ignored_observation_paths"], ["web/data/snapshot.json"])
        self.assertTrue(report["semantic_noop"])
        self.assertFalse(report["changed_paths"])
        self.assertFalse(report["material_progress"]["mutation_candidate"])
        self.assertNotEqual(report["status"], "REPAIRED")

    def test_actual_git_meaningful_signal_edit_retains_material_identity(self):
        payload = {"generated_at": "2026-10-11T04:00:00Z", "signals": [{"title": "Original signal", "event_date": "2026-10-10"}]}
        path = self.tracked_json(payload)
        self.install_gate("editorial")
        def change_signal(workspace):
            path.write_text(json.dumps({**payload, "signals": [{"title": "Verified additional context", "event_date": "2026-10-10"}]}))
            return {"operation": "controlled_material_update", "changed_paths": ["web/data/snapshot.json"]}
        with patch.object(runner, "sync_reviewed_editorial", side_effect=change_signal):
            report = runner.execute_lane("editorial", self.root, self.task, self.report, command_runner=self.fake_commands())
        self.assertNotEqual(report["before_hash"], report["after_hash"])
        self.assertEqual(report["changed_paths"], ["web/data/snapshot.json"])
        self.assertFalse(report["semantic_noop"])
        self.assertFalse(report["ignored_observation_paths"])

    def test_json_formatting_and_order_only_are_semantically_unchanged(self):
        path = self.tracked_json({"signals": [{"title": "Stable", "event_date": "2026-10-10"}], "generated_at": "old"})
        before_raw = runner.tracked_hashes(self.root)
        before, _ = runner.material_file_hashes(self.root, before_raw)
        path.write_text('{\n  "generated_at": "old",\n  "signals": [{"event_date": "2026-10-10", "title": "Stable"}]\n}\n')
        after_raw = runner.tracked_hashes(self.root)
        after, _ = runner.material_file_hashes(self.root, after_raw)
        self.assertNotEqual(before_raw, after_raw)
        self.assertEqual(before, after)

    def test_material_json_preserves_publication_dates_deadlines_strings_and_hashes(self):
        payload = {"generated_at": "observation", "signal": {"event_date": "2026-10-10", "published_at": "2026-10-10T04:00:00Z",
                    "effective_at": "2026-11-01T04:00:00Z", "deadline": "2026-12-01T04:00:00Z", "source_content": "Content at 2026-10-10T04:00:00Z",
                    "content_hash": "a" * 64, "response_sha256": "b" * 64}}
        path = self.tracked_json(payload)
        original, _ = runner.material_file_hashes(self.root, runner.tracked_hashes(self.root))
        for field, value in (("event_date", "2026-10-11"), ("published_at", "2026-10-10T05:00:00Z"),
                             ("effective_at", "2026-11-01T05:00:00Z"), ("deadline", "2026-12-01T05:00:00Z"),
                             ("source_content", "Content at 2026-10-10T05:00:00Z"), ("content_hash", "c" * 64), ("response_sha256", "d" * 64)):
            with self.subTest(field=field):
                path.write_text(json.dumps({**payload, "signal": {**payload["signal"], field: value}}))
                changed, _ = runner.material_file_hashes(self.root, runner.tracked_hashes(self.root))
                self.assertNotEqual(original, changed)

    def test_invalid_json_and_source_code_keep_raw_identity(self):
        path = self.tracked_json({"signals": []})
        path.write_text('{"signals": invalid json}')
        raw = runner.tracked_hashes(self.root)
        material, unknown = runner.material_file_hashes(self.root, raw)
        self.assertEqual(material["web/data/snapshot.json"], raw["web/data/snapshot.json"])
        self.assertEqual(unknown, ["web/data/snapshot.json"])
        code = self.root / "src/radar_salud/source.py"
        code.parent.mkdir(parents=True, exist_ok=True)
        code.write_text('published_at = "2026-10-10T04:00:00Z"\n')
        self.git("add", "src/radar_salud/source.py")
        self.git("commit", "-m", "controlled source module")
        first, _ = runner.material_file_hashes(self.root, runner.tracked_hashes(self.root))
        code.write_text('published_at = "2026-10-10T05:00:00Z"\n')
        second, _ = runner.material_file_hashes(self.root, runner.tracked_hashes(self.root))
        self.assertNotEqual(first["src/radar_salud/source.py"], second["src/radar_salud/source.py"])

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
        self.assertEqual(report["acceptance_proof"][0]["staging_merge_sha"], self.sha)
        self.assertEqual(report["acceptance_proof"][0]["origin_staging_sha"], self.sha)
        self.assertFalse(report["blockers"])

    def test_isolated_candidate_cannot_close_sources_despite_complete_manifest(self):
        self.staging_reference(incorporated=False)
        self.acceptance()
        report = self.execute()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["acceptance_proof"])
        self.assertTrue(any("not incorporated" in item["reason"] for item in report["blockers"]))

    def test_source_closure_requires_available_staging_reference_and_merge_sha(self):
        self.acceptance()
        self.git("update-ref", "-d", "refs/remotes/origin/staging")
        proof, reason = runner.verify_acceptance(self.root, self.task, "media", self.sha)
        self.assertFalse(proof)
        self.assertIn("unavailable", reason)
        self.git("update-ref", "refs/remotes/origin/staging", self.sha)
        self.acceptance(staging_merge_sha="b" * 40)
        proof, reason = runner.verify_acceptance(self.root, self.task, "media", self.sha)
        self.assertFalse(proof)
        self.assertIn("staging_merge_sha", reason)
        self.acceptance(checks={name: True for name in runner.SOURCE_ACCEPTANCE if name != "runtime_after_merge_pass"})
        proof, reason = runner.verify_acceptance(self.root, self.task, "media", self.sha)
        self.assertFalse(proof)
        self.assertIn("runtime_after_merge_pass", reason)

    def test_source_closure_rejects_missing_after_merge_execution_or_incomplete_trace(self):
        cases = [
            lambda runtime: runtime.update(execution_after_merge=False),
            lambda runtime: runtime.update(staging_sha="b" * 40),
            lambda runtime: runtime.update(trace=[]),
            lambda runtime: runtime.update(trace=runtime["trace"][:1]),
            lambda runtime: runtime["trace"][0].update(runtime_evidence={}),
            lambda runtime: runtime["trace"][0].update(staging_sha="b" * 40),
            lambda runtime: runtime["trace"][0].update(returncode=1),
            lambda runtime: runtime["trace"][0].update(log_sha256="b" * 64),
        ]
        for index, modify in enumerate(cases):
            with self.subTest(case=index):
                self.acceptance()
                self.rewrite_acceptance_runtime(modify)
                proof, reason = runner.verify_acceptance(self.root, self.task, "media", self.sha)
                self.assertFalse(proof)
                self.assertTrue(reason)

    def test_source_closure_rejects_only_command_metadata_or_unbound_runtime_log(self):
        self.acceptance()
        self.rewrite_acceptance_runtime(lambda runtime: runtime.update(trace=[{"command": ["echo", "PASS"], "returncode": 0}]))
        proof, reason = runner.verify_acceptance(self.root, self.task, "media", self.sha)
        self.assertFalse(proof)
        self.assertIn("substantive", reason)
        self.acceptance()
        runtime = json.loads((self.root / "runtime-after-merge.json").read_text())
        log_path = self.root / runtime["trace"][0]["log_path"]
        log_path.write_text("Successful command, no source or staging identity\n")
        self.rewrite_acceptance_runtime(lambda value: value["trace"][0].update(log_sha256=runner.digest(log_path.read_bytes())))
        proof, reason = runner.verify_acceptance(self.root, self.task, "media", self.sha)
        self.assertFalse(proof)
        self.assertIn("bind actual source execution", reason)

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
        self.assertIn(proof["source_slug"], runner.FAMILIES["media"])
        technical = next(item for item in report["blockers"] if item["kind"] == "technical")
        self.assertIn("log_sha256", technical["evidence"][0])
        self.assertIn("source_urls", technical["evidence"][0])
        self.assertFalse(technical["human_required"])

    def test_full_recovered_source_binds_actual_live_gate_to_failure_slug(self):
        self.install_gate("media")
        first = self.fake_commands(source_failure=True)
        passed = self.fake_commands()
        probes = {}
        def command(command, workspace, timeout=180, **kwargs):
            if "--diagnose-source" in command:
                slug = command[-1]
                probes[slug] = probes.get(slug, 0) + 1
                return (first if probes[slug] == 1 else passed)(command, workspace, timeout=timeout)
            return passed(command, workspace, timeout=timeout)
        recovery = Mock(return_value={"status": "REPAIRED", "validated": True, "changed_paths": ["src/radar_salud/source_scouts.py"]})
        with patch.object(runner, "recovery_module", return_value=SimpleNamespace(recover=recovery)), \
             patch.object(runner, "tracked_hashes", return_value={"src/radar_salud/source_scouts.py": "same"}):
            report = runner.execute_lane("media", self.root, self.task, self.report, command_runner=command)
        self.assertEqual(report["failure_action"], "repaired")
        self.assertTrue(report["live_validated"])
        self.assertEqual(report["live_scope"], [report["real_failure"]["source_slug"]])
        self.assertEqual(report["live_gate"]["status"], "PASS")
        self.assertEqual(report["live_gate"]["returncode"], 0)
        self.assertEqual(report["live_gate"]["command"][-1], report["real_failure"]["source_slug"])
        self.assertTrue(report["directed_gates"])
        self.assertTrue(all(gate["status"] == "PASS" for gate in report["directed_gates"]))
        live = report["live_gate"]
        self.assertEqual(live["log_sha256"], runner.digest(Path(live["log_path"]).read_bytes()))

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
