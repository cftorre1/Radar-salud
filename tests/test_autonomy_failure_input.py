"""Controller/worker agreement and stable identities from real log shapes."""
import json
import subprocess
import unittest
from unittest.mock import patch

from scripts.autonomy_failure_input import (
    FailureInputError, build_failure_input, failure_signature, failed_test_identities,
)

REPOSITORY = "cftorre1/Radar-salud"


class FailureInputTests(unittest.TestCase):
    def run_payload(self, *, run_id=1234, **updates):
        payload = {"id": run_id, "name": "Alicanto staging preview", "head_branch": "staging", "status": "completed",
                   "conclusion": "failure", "head_sha": "a" * 40,
                   "html_url": "https://github.com/" + REPOSITORY + "/actions/runs/" + str(run_id)}
        payload.update(updates)
        return payload

    def mocked_gh(self, payload, log, *, collection=None, logs_exit=0):
        def execute(arguments, **options):
            if arguments[:3] == ["gh", "run", "view"]:
                return subprocess.CompletedProcess(arguments, logs_exit, stdout=log, stderr="hidden diagnostics")
            body = {"workflow_runs": collection if collection is not None else [payload]} if "?" in arguments[-1] else payload
            return subprocess.CompletedProcess(arguments, 0, stdout=json.dumps(body), stderr="")
        return execute

    def test_controller_and_worker_produce_the_same_exact_failure_schema(self):
        payload = self.run_payload()
        log = "qa / tests\tUNKNOWN STEP\t2026-10-11T04:17:07.1891812Z FAILED tests/test_web_snapshot.py::test_visible_acts - AssertionError: assert 11 >= 12\n"
        with patch("scripts.autonomy_failure_input.subprocess.run", side_effect=self.mocked_gh(payload, log)):
            controller = build_failure_input(REPOSITORY)
            worker = build_failure_input(REPOSITORY, "1234")
        self.assertEqual(controller, worker)
        self.assertEqual(set(controller), {"run_id", "run_url", "head_sha", "conclusion", "failure_signature"})
        self.assertEqual(controller["run_id"], 1234)

    def test_unrelated_log_clocks_wrappers_and_summary_order_do_not_change_identity(self):
        first = "qa / tests\tstep\t2026-10-11T01:00:00Z FAILED tests/test_a.py::test_first - AssertionError\n2026-10-11T01:00:01Z FAILED tests/test_b.py::test_second[case 1] - ValueError\n1 failed in 2.12s\n"
        second = "another job\tother step\t2026-10-11T09:55:10.456Z FAILED tests/test_b.py::test_second[case 1] - ValueError\n\x1b[31mFAILED tests/test_a.py::test_first - AssertionError\x1b[0m\n1 failed in 55.31s\n"
        self.assertEqual(failed_test_identities(first), failed_test_identities(second))
        self.assertEqual(failure_signature("Alicanto staging preview", "failure", first), failure_signature("Alicanto staging preview", "failure", second))
        different = second.replace("test_first", "test_third")
        self.assertNotEqual(failure_signature("Alicanto staging preview", "failure", first), failure_signature("Alicanto staging preview", "failure", different))

    def test_newer_cancelled_preview_does_not_mask_actual_failure(self):
        failed = self.run_payload()
        cancelled = self.run_payload(run_id=1235, conclusion="cancelled")
        with patch("scripts.autonomy_failure_input.subprocess.run", side_effect=self.mocked_gh(failed, "FAILED tests/test_a.py::test_a - error", collection=[cancelled, failed])):
            result = build_failure_input(REPOSITORY)
        self.assertEqual(result["run_id"], failed["id"])

    def test_latest_real_pass_resolves_the_current_failure_input(self):
        passed = self.run_payload(run_id=1235, conclusion="success")
        with patch("scripts.autonomy_failure_input.subprocess.run", side_effect=self.mocked_gh(passed, "", collection=[passed, self.run_payload()])) as gh:
            self.assertEqual(build_failure_input(REPOSITORY), {"conclusion": None})
        self.assertEqual(gh.call_count, 1)

    def test_logs_unavailable_keep_a_stable_demonstrated_failure(self):
        payload = self.run_payload(conclusion="timed_out")
        with patch("scripts.autonomy_failure_input.subprocess.run", side_effect=self.mocked_gh(payload, "sensitive stderr discarded", logs_exit=1)):
            first = build_failure_input(REPOSITORY)
            second = build_failure_input(REPOSITORY, "1234")
        self.assertEqual(first, second)
        self.assertEqual(first["failure_signature"], failure_signature(payload["name"], "timed_out"))

    def test_specified_wrong_branch_or_incomplete_run_is_rejected(self):
        for updates in ({"head_branch": "main"}, {"status": "in_progress"}, {"name": "Deploy static content to Pages"}):
            payload = self.run_payload(**updates)
            with patch("scripts.autonomy_failure_input.subprocess.run", side_effect=self.mocked_gh(payload, "")):
                with self.assertRaisesRegex(FailureInputError, "completed staging preview"):
                    build_failure_input(REPOSITORY, "1234")

    def test_wrong_repository_url_and_invalid_sha_are_rejected(self):
        for updates in ({"html_url": "https://github.com/other/repo/actions/runs/1234"}, {"head_sha": "short"}):
            payload = self.run_payload(**updates)
            with patch("scripts.autonomy_failure_input.subprocess.run", side_effect=self.mocked_gh(payload, "")):
                with self.assertRaises(FailureInputError):
                    build_failure_input(REPOSITORY, "1234")

    def test_no_run_is_explicit_and_invalid_input_never_executes_a_command(self):
        with patch("scripts.autonomy_failure_input.subprocess.run", side_effect=AssertionError("no command allowed")):
            self.assertEqual(build_failure_input(REPOSITORY, "0"), {"conclusion": None})
            with self.assertRaises(FailureInputError):
                build_failure_input(REPOSITORY, "1234; unsafe")
            with self.assertRaises(FailureInputError):
                build_failure_input("bad repository", "1234")
        with patch("scripts.autonomy_failure_input.subprocess.run", side_effect=self.mocked_gh(self.run_payload(), "", collection=[])):
            self.assertEqual(build_failure_input(REPOSITORY), {"conclusion": None})

    def test_browser_and_node_failures_use_stable_test_names(self):
        log = "qa\t2026-10-11T04:17:00Z tests/browser/product.spec.cjs:21:4 › detail opens (1.2s)\nnot ok 14 - respects editorial contract\n"
        changed = log.replace(":21:4", ":99:8").replace("(1.2s)", "(4.1s)").replace("not ok 14", "not ok 25")
        self.assertEqual(failed_test_identities(log), failed_test_identities(changed))
        self.assertEqual(len(failed_test_identities(log)), 2)


if __name__ == "__main__":
    unittest.main()
