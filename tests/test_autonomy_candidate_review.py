"""Actual isolated Git candidates, mandatory commands and durable review state."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.autonomy_candidate_review import (
    STATE, ReviewError, digest, encode, project_commands, pytest_summary, review_candidate,
)
from scripts.autonomy_state_store import GitStateStore, Mutation


class CandidateReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="candidate-review-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / "remote.git"
        self.workspace = self.root / "candidate"
        self.seed = self.root / "state-seed"
        self.branch = "autonomy/media/worker1"
        self.task_id = "source_repair_media_lane_2026_10_11"
        self.git("init", "--bare", "--quiet", str(self.remote))
        self.git("init", "--quiet", "-b", self.branch, str(self.workspace))
        self.identify(self.workspace)
        (self.workspace / "source.py").write_text("value = 2\n")
        self.git("-C", str(self.workspace), "add", "source.py")
        self.git("-C", str(self.workspace), "commit", "--quiet", "-m", "isolated repair")
        self.sha = self.git("-C", str(self.workspace), "rev-parse", "HEAD")
        self.git("-C", str(self.workspace), "remote", "add", "origin", self.remote.as_uri())
        self.git("-C", str(self.workspace), "push", "--quiet", "origin", self.branch)
        self.state = {"schema_version": 2, "tasks": {self.task_id: {"id": self.task_id, "family": "media", "status": "BLOCKED", "input_sha": "a" * 40}}, "material_events": [{"id": "initial-mutation", "kind": "mutation", "task_id": self.task_id, "family": "media", "details": {"candidate_commit": self.sha, "candidate_branch": self.branch, "candidate_scope": "isolated", "changed_paths": ["source.py"]}}]}
        self.git("init", "--quiet", "-b", "autopilot-state", str(self.seed))
        self.identify(self.seed)
        state_path = self.seed / STATE
        state_path.parent.mkdir(parents=True)
        state_path.write_text(encode(self.state))
        self.git("-C", str(self.seed), "add", STATE)
        self.git("-C", str(self.seed), "commit", "--quiet", "-m", "canonical mutation")
        self.git("-C", str(self.seed), "remote", "add", "origin", self.remote.as_uri())
        self.git("-C", str(self.seed), "push", "--quiet", "origin", "autopilot-state")
        self.store = GitStateStore(self.remote.as_uri(), initial_backoff=0)
        self.report = self.root / "artifacts/review.json"

    @staticmethod
    def git(*arguments):
        return subprocess.run(["git", *arguments], text=True, capture_output=True, check=True).stdout.strip()

    def identify(self, directory):
        self.git("-C", str(directory), "config", "user.name", "Candidate Review Test")
        self.git("-C", str(directory), "config", "user.email", "candidate@example.invalid")

    def update_state(self, update):
        def reducer(snapshot):
            state = snapshot.read_json(STATE)
            update(state)
            return Mutation({STATE: encode(state)})
        self.store.transact(reducer)

    def review(self, commands=None, **arguments):
        commands = commands or [[sys.executable, "-c", "import source; assert source.value == 2"]]
        return review_candidate(self.workspace, self.workspace, self.task_id, "media", self.sha, self.report,
                                store=self.store, command_planner=lambda infra, work: commands, **arguments)

    def test_actual_pass_is_durable_and_does_not_close_source_task(self):
        report = self.review()
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["technical_review_pass"])
        self.assertEqual(report["next_action"], "source_acceptance_reconciliation")
        gate = report["gates"][0]
        self.assertEqual(digest(Path(gate["log_path"]).read_bytes()), gate["log_sha256"])
        snapshot = self.store.read_snapshot()
        state = snapshot.read_json(STATE)
        self.assertEqual(state["tasks"][self.task_id]["status"], "BLOCKED")
        self.assertEqual(state["material_events"], self.state["material_events"])
        self.assertEqual(state["tasks"][self.task_id]["candidate_review"]["candidate_commit"], self.sha)
        immutable = snapshot.read_json(report["review_evidence_path"])
        self.assertTrue(immutable["technical_review_pass"])
        self.assertFalse(immutable["production_promoted"])
        self.assertFalse(immutable["closure"])

    def test_real_failed_gate_retains_candidate_and_exact_blocker(self):
        report = self.review([[sys.executable, "-c", "import source; assert source.value == 3"], [sys.executable, "-c", "raise RuntimeError('must not run after failed prerequisite')"]])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(len(report["gates"]), 1)
        self.assertEqual(report["next_action"], "repair_review_failure")
        self.assertIn("AssertionError", Path(report["gates"][0]["log_path"]).read_text())
        state = self.store.read_snapshot().read_json(STATE)
        review = state["tasks"][self.task_id]["candidate_review"]
        self.assertEqual(review["candidate_branch"], self.branch)
        self.assertFalse(review["blocker"]["human_required"])
        self.assertEqual(state["material_events"], self.state["material_events"])
        self.assertEqual(self.git("--git-dir", str(self.remote), "rev-parse", "refs/heads/" + self.branch), self.sha)

    def test_rejects_unrecorded_candidate_before_running_commands(self):
        self.update_state(lambda state: state.update(material_events=[]))
        with self.assertRaisesRegex(ReviewError, "No durable mutation"):
            self.review()
        self.assertFalse(self.report.exists())

    def test_rejects_checkout_sha_mismatch(self):
        changed = "b" * 40
        self.update_state(lambda state: state["material_events"][0]["details"].update(candidate_commit=changed))
        with self.assertRaisesRegex(ReviewError, "HEAD differs"):
            review_candidate(self.workspace, self.workspace, self.task_id, "media", changed, self.report, store=self.store)

    def test_rejects_production_checkout_and_nonisolated_scope(self):
        self.git("-C", str(self.workspace), "checkout", "-b", "production-stable")
        with self.assertRaisesRegex(ReviewError, "isolated candidate branch"):
            self.review()
        self.git("-C", str(self.workspace), "checkout", self.branch)
        self.update_state(lambda state: state["material_events"][0]["details"].update(candidate_scope="staging"))
        with self.assertRaisesRegex(ReviewError, "outside its isolated"):
            self.review()

    def test_review_race_cannot_replace_a_newer_candidates_pointer(self):
        newer = "b" * 40
        original_pointer = {"candidate_commit": newer, "status": "PENDING"}
        def planner(infrastructure, workspace):
            def change(state):
                event = deepcopy(state["material_events"][0])
                event["id"] = "newer-mutation"
                event["details"].update(candidate_commit=newer, candidate_branch="autonomy/media/worker2")
                state["material_events"].append(event)
                state["tasks"][self.task_id]["candidate_review"] = original_pointer
                state["tasks"][self.task_id]["sibling_heartbeat"] = "retained"
            self.update_state(change)
            return [[sys.executable, "-c", "import source; assert source.value == 2"]]
        report = review_candidate(self.workspace, self.workspace, self.task_id, "media", self.sha, self.report,
                                  store=self.store, command_planner=planner)
        self.assertTrue(report["superseded"])
        state = self.store.read_snapshot().read_json(STATE)
        self.assertEqual(state["tasks"][self.task_id]["candidate_review"], original_pointer)
        self.assertEqual(state["tasks"][self.task_id]["sibling_heartbeat"], "retained")
        self.assertTrue(state["tasks"][self.task_id]["candidate_reviews"][self.sha]["superseded"])

    def test_validation_cannot_use_paid_or_github_credentials(self):
        command = [sys.executable, "-c", "import os; assert not any(os.getenv(k) for k in ('OPENAI_API_KEY','GH_TOKEN','GITHUB_TOKEN'))"]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-paid-key-only", "GH_TOKEN": "test-gh-key-only", "GITHUB_TOKEN": "test-token-only"}):
            report = self.review([command])
        self.assertTrue(report["technical_review_pass"])

    def test_no_gate_execution_cannot_claim_pass(self):
        report = review_candidate(self.workspace, self.workspace, self.task_id, "media", self.sha, self.report,
                                  store=self.store, command_planner=lambda infra, work: [])
        self.assertFalse(report["technical_review_pass"])
        self.assertEqual(report["status"], "BLOCKED")

    def test_skipped_only_pytest_is_unverified(self):
        xml = self.root / "skipped-live.xml"
        xml.write_text('<testsuites><testsuite><testcase name="live_runtime"><skipped message="credential unavailable"/></testcase></testsuite></testsuites>')
        counts = pytest_summary(xml)
        self.assertFalse(counts["proof"])
        self.assertEqual(counts["passed"], 0)
        self.assertEqual(counts["skipped"], 1)

    def test_project_planner_preserves_canonical_build_and_reviewer_contract(self):
        (self.workspace / "package.json").write_text("{}")
        scripts = self.workspace / "scripts"
        scripts.mkdir()
        names = ("build_statistics_deep_analysis.py", "build_epidemiology_snapshot.py", "export_web_snapshot.py", "export_global_intelligence.py", "product_report.py", "review_candidate.py")
        for name in names:
            (scripts / name).write_text("pass\n")
        commands = project_commands(self.root / "no-infrastructure", self.workspace)
        self.assertIn(["npm", "test"], commands)
        self.assertIn(["npm", "run", "test:browser"], commands)
        self.assertIn([sys.executable, "scripts/review_candidate.py", "--web", "web", "--sha", self.sha], commands)
        (scripts / "build_statistics_deep_analysis.py").unlink()
        with self.assertRaisesRegex(ReviewError, "contract is incomplete"):
            project_commands(self.root / "no-infrastructure", self.workspace)


if __name__ == "__main__":
    unittest.main()
