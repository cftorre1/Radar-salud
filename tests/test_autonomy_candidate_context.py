"""Candidate continuity uses durable authority, scoped inputs and actual Git refs."""
from copy import deepcopy
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.autonomy_candidate_context import (
    CandidateContextError, overlay_queue, prepare_workspace,
)


MEDIA = "source_repair_media_lane_2026_10_11"


class OverlayQueueTests(unittest.TestCase):
    def setUp(self):
        self.parent_sha = "a" * 40
        self.candidate_sha = "b" * 40
        self.fingerprint = "c" * 64
        self.queue = {
            "input_sha": self.parent_sha,
            "policy": {"production_promotion": False},
            "generated_at": "2026-10-11T00:00:00Z",
            "tasks": [{
                "id": MEDIA, "family": "media", "status": "approved",
                "input_sha": self.parent_sha, "input_fingerprint": self.fingerprint,
                "objective": "Repair source evidence", "depends_on": [],
                "blocked_by": ["preserve-existing-external-blocker"],
                "constraints": ["Never promote product"],
                "evidence": {"source_url": "https://example.invalid/source", "observed_at": "old"},
            }],
        }
        self.state = {
            "tasks": {MEDIA: {
                "id": MEDIA, "family": "media", "status": "BLOCKED",
                "candidate_review": {
                    "candidate_commit": self.candidate_sha,
                    "candidate_branch": "autonomy/media/fix",
                    "candidate_scope": "isolated", "status": "PASS",
                    "technical_review_pass": True, "reviewed_at": "2026-10-11T01:00:00Z",
                    "next_action": "source_acceptance_reconciliation", "superseded": False,
                },
            }},
            "material_events": [{
                "id": "mutation-1", "kind": "mutation", "task_id": MEDIA,
                "family": "media", "at": "2026-10-11T00:30:00Z",
                "details": {
                    "candidate_commit": self.candidate_sha,
                    "candidate_branch": "autonomy/media/fix", "candidate_scope": "isolated",
                    "parent_input_sha": self.parent_sha,
                    "input_fingerprint": self.fingerprint,
                    "changed_paths": ["src/radar_salud/press_pipeline.py"],
                },
            }],
        }

    def task(self, queue=None, state=None):
        return overlay_queue(queue or self.queue, state or self.state)["tasks"][0]

    def test_reviewed_isolated_candidate_overlays_without_changing_queue_or_policy(self):
        original_queue, original_state = deepcopy(self.queue), deepcopy(self.state)
        result = overlay_queue(self.queue, self.state)
        task = result["tasks"][0]
        self.assertEqual(task["input_sha"], self.candidate_sha)
        self.assertEqual(task["candidate_context"]["branch"], "autonomy/media/fix")
        self.assertEqual(task["candidate_context"]["commit"], self.candidate_sha)
        self.assertEqual(task["candidate_context"]["parent_input_sha"], self.parent_sha)
        self.assertEqual(task["candidate_context"]["baseline_input_fingerprint"], self.fingerprint)
        self.assertEqual(task["candidate_context"]["current_input_fingerprint"], self.fingerprint)
        self.assertFalse(task["candidate_context"]["base_changed"])
        self.assertFalse(task["candidate_context"]["rebase_required"])
        self.assertEqual(task["blocked_by"], original_queue["tasks"][0]["blocked_by"])
        self.assertEqual(result["policy"], original_queue["policy"])
        self.assertEqual(self.queue, original_queue)
        self.assertEqual(self.state, original_state)
        task["constraints"].append("new local constraint")
        self.assertEqual(self.queue, original_queue)

    def test_unrelated_staging_update_keeps_candidate_and_marks_base_change(self):
        self.queue["input_sha"] = "d" * 40
        self.queue["tasks"][0]["input_sha"] = "d" * 40
        task = self.task()
        self.assertEqual(task["input_sha"], self.candidate_sha)
        self.assertTrue(task["candidate_context"]["base_changed"])
        self.assertFalse(task["candidate_context"]["rebase_required"])

    def test_scoped_input_change_requires_explicit_rebase(self):
        self.queue["input_sha"] = "d" * 40
        self.queue["tasks"][0].update(input_sha="d" * 40, input_fingerprint="e" * 64)
        context = self.task()["candidate_context"]
        self.assertTrue(context["base_changed"])
        self.assertTrue(context["rebase_required"])
        self.assertEqual(context["baseline_input_fingerprint"], self.fingerprint)
        self.assertEqual(context["current_input_fingerprint"], "e" * 64)

    def test_evidence_revision_ignores_observation_clock_churn(self):
        first = self.task()["evidence_revision"]
        self.queue["generated_at"] = "2026-10-11T04:00:00Z"
        self.queue["tasks"][0]["evidence"]["observed_at"] = "new"
        self.state["tasks"][MEDIA]["candidate_review"]["reviewed_at"] = "2026-10-11T04:00:00Z"
        self.state["material_events"][0]["at"] = "2026-10-11T04:00:00Z"
        self.assertEqual(self.task()["evidence_revision"], first)

    def test_review_wrapper_hash_churn_is_stable_but_semantic_fingerprint_change_is_new(self):
        review = self.state["tasks"][MEDIA]["candidate_review"]
        review.update(evidence_sha256="1" * 64, semantic_fingerprint="2" * 64)
        first = self.task()["evidence_revision"]
        review.update(evidence_sha256="3" * 64, reviewed_at="2026-10-11T04:00:00Z")
        self.assertEqual(self.task()["evidence_revision"], first)
        review["semantic_fingerprint"] = "4" * 64
        self.assertNotEqual(self.task()["evidence_revision"], first)

    def test_overlay_is_idempotent_and_does_not_recursively_hash_its_revision(self):
        self.queue["tasks"][0]["evidence_revision"] = "owner-approved-evidence-v1"
        first = overlay_queue(self.queue, self.state)
        second = overlay_queue(first, self.state)
        self.assertEqual(second, first)
        self.assertEqual(second["tasks"][0]["candidate_context"]["queue_evidence_revision"],
                         "owner-approved-evidence-v1")

    def test_queue_authored_context_without_durable_authority_is_removed(self):
        self.queue["tasks"][0]["candidate_context"] = {
            "branch": "autonomy/media/unrecorded", "commit": "f" * 40,
            "queue_evidence_revision": "unrecorded-evidence",
        }
        self.state["material_events"] = []
        result = self.task()
        self.assertNotIn("candidate_context", result)
        self.assertEqual(result["input_sha"], self.parent_sha)
        self.assertEqual(result["blocked_by"], ["preserve-existing-external-blocker"])

    def test_review_verdict_and_queue_semantics_change_revision(self):
        first = self.task()["evidence_revision"]
        review = self.state["tasks"][MEDIA]["candidate_review"]
        review.update(status="BLOCKED", technical_review_pass=False, next_action="repair_review_failure",
                      blocker={"kind": "candidate_technical_review", "fingerprint": "f" * 64,
                               "reason": "Mandatory gate failed", "human_required": False})
        second = self.task()["evidence_revision"]
        self.assertNotEqual(first, second)
        self.queue["tasks"][0]["objective"] = "Repair source evidence and reconcile source acceptance"
        self.assertNotEqual(second, self.task()["evidence_revision"])

    def test_candidate_commit_and_explicit_queue_revision_change_revision(self):
        self.queue["tasks"][0]["evidence_revision"] = "source-evidence-v1"
        first = self.task()["evidence_revision"]
        self.queue["tasks"][0]["evidence_revision"] = "source-evidence-v2"
        second = self.task()["evidence_revision"]
        self.assertNotEqual(first, second)
        newer = "d" * 40
        self.state["material_events"][0]["details"]["candidate_commit"] = newer
        self.state["tasks"][MEDIA]["candidate_review"]["candidate_commit"] = newer
        task = self.task()
        self.assertEqual(task["input_sha"], newer)
        self.assertNotEqual(task["evidence_revision"], second)

    def test_pending_missing_superseded_or_wrong_commit_review_cannot_resume(self):
        for variant in (None, {"status": "PENDING"}, {"status": "PASS", "superseded": True},
                        {"status": "PASS", "candidate_commit": "f" * 40},
                        {"status": "PASS", "candidate_branch": "autonomy/media/other"},
                        {"status": "PASS", "candidate_scope": "staging"}):
            with self.subTest(variant=variant):
                state = deepcopy(self.state)
                if variant is None:
                    state["tasks"][MEDIA].pop("candidate_review")
                else:
                    state["tasks"][MEDIA]["candidate_review"].update(variant)
                task = self.task(state=state)
                self.assertEqual(task["input_sha"], self.parent_sha)
                self.assertNotIn("candidate_context", task)

    def test_latest_mutation_is_authoritative_and_never_falls_back(self):
        for details in (
            {"candidate_scope": "staging"},
            {"candidate_branch": "autonomy/public_data/fix"},
            {"candidate_branch": "autonomy/media/fix/extra"},
            {"candidate_commit": "abc123"},
        ):
            with self.subTest(details=details):
                state = deepcopy(self.state)
                event = deepcopy(state["material_events"][0])
                event["id"] = "mutation-2"
                event["details"].update(details)
                state["material_events"].append(event)
                task = self.task(state=state)
                self.assertEqual(task["input_sha"], self.parent_sha)
                self.assertNotIn("candidate_context", task)

    def test_newer_mutation_from_another_task_does_not_hide_candidate(self):
        self.state["material_events"].append({"kind": "mutation", "task_id": "other-task",
                                             "details": {"candidate_commit": "f" * 40}})
        self.assertEqual(self.task()["input_sha"], self.candidate_sha)

    def test_only_approved_or_in_progress_supported_tasks_can_resume(self):
        for status in ("completed", "blocked", "draft"):
            with self.subTest(status=status):
                queue = deepcopy(self.queue)
                queue["tasks"][0]["status"] = status
                self.assertNotIn("candidate_context", self.task(queue=queue))
        self.queue["tasks"][0]["status"] = "in_progress"
        self.assertEqual(self.task()["input_sha"], self.candidate_sha)
        queue, state = deepcopy(self.queue), deepcopy(self.state)
        queue["tasks"][0].update(id="unsupported-product-task", family="product")
        state["tasks"]["unsupported-product-task"] = state["tasks"].pop(MEDIA)
        state["material_events"][0]["task_id"] = "unsupported-product-task"
        self.assertNotIn("candidate_context", self.task(queue=queue, state=state))


class PrepareWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="autonomy-candidate-context-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / "remote.git"
        self.seed = self.root / "seed"
        self.workspace = self.root / "workspace"
        self.branch = "autonomy/media/fix"
        self.git("init", "--bare", "--quiet", str(self.remote))
        self.git("init", "--quiet", "-b", "staging", str(self.seed))
        self.git("-C", str(self.seed), "config", "user.name", "Candidate Context Test")
        self.git("-C", str(self.seed), "config", "user.email", "candidate-context@example.invalid")
        (self.seed / "source.py").write_text("repair = False\n")
        (self.seed / "editorial.txt").write_text("original editorial\n")
        self.git("-C", str(self.seed), "add", "source.py", "editorial.txt")
        self.git("-C", str(self.seed), "commit", "--quiet", "-m", "staging baseline")
        self.parent_sha = self.git("-C", str(self.seed), "rev-parse", "HEAD")
        self.fingerprint = hashlib.sha256((self.seed / "source.py").read_bytes()).hexdigest()
        self.git("-C", str(self.seed), "remote", "add", "origin", self.remote.as_uri())
        self.git("-C", str(self.seed), "push", "--quiet", "origin", "staging")
        self.git("-C", str(self.seed), "checkout", "--quiet", "-b", self.branch)
        (self.seed / "source.py").write_text("repair = True\n")
        self.git("-C", str(self.seed), "commit", "--quiet", "-am", "durable isolated source repair")
        self.candidate_sha = self.git("-C", str(self.seed), "rev-parse", "HEAD")
        self.git("-C", str(self.seed), "push", "--quiet", "origin", self.branch)
        self.git("clone", "--quiet", "--branch", "staging", self.remote.as_uri(), str(self.workspace))
        self.task = {"id": MEDIA, "family": "media", "status": "approved",
                     "input_sha": self.candidate_sha, "input_fingerprint": self.fingerprint,
                     "candidate_context": {
                         "branch": self.branch, "commit": self.candidate_sha,
                         "parent_input_sha": self.parent_sha,
                         "current_staging_sha": self.parent_sha,
                         "baseline_input_fingerprint": self.fingerprint,
                         "current_input_fingerprint": self.fingerprint,
                         "base_changed": False, "rebase_required": False,
                     }}

    @staticmethod
    def git(*arguments):
        return subprocess.run(["git", *arguments], text=True, capture_output=True, check=True).stdout.strip()

    def head(self):
        return self.git("-C", str(self.workspace), "rev-parse", "HEAD")

    def refs(self):
        return {branch: self.git("--git-dir", str(self.remote), "rev-parse", "refs/heads/" + branch)
                for branch in ("staging", self.branch)}

    def test_fetches_exact_candidate_and_retains_actual_repair(self):
        before = self.refs()
        result = prepare_workspace(self.workspace, self.task)
        self.assertTrue(result["prepared"])
        self.assertEqual(result["input_sha"], self.candidate_sha)
        self.assertEqual(self.head(), self.candidate_sha)
        self.assertEqual(self.git("-C", str(self.workspace), "branch", "--show-current"), self.branch)
        self.assertEqual((self.workspace / "source.py").read_text(), "repair = True\n")
        self.assertEqual(self.refs(), before)
        self.assertFalse(result["rebase_required"])

    def test_unrelated_staging_updates_do_not_overwrite_candidate_with_fresh_staging(self):
        self.git("-C", str(self.seed), "checkout", "--quiet", "staging")
        (self.seed / "editorial.txt").write_text("unrelated newer editorial\n")
        self.git("-C", str(self.seed), "commit", "--quiet", "-am", "independent staging progress")
        latest_staging = self.git("-C", str(self.seed), "rev-parse", "HEAD")
        self.git("-C", str(self.seed), "push", "--quiet", "origin", "staging")
        self.git("-C", str(self.workspace), "pull", "--quiet", "--ff-only", "origin", "staging")
        self.assertEqual(self.head(), latest_staging)
        self.task["candidate_context"]["base_changed"] = True
        self.task["candidate_context"]["current_staging_sha"] = latest_staging
        before = self.refs()
        result = prepare_workspace(self.workspace, self.task)
        self.assertTrue(result["prepared"])
        self.assertTrue(result["base_changed"])
        self.assertFalse(result["rebase_required"])
        self.assertEqual(self.head(), self.candidate_sha)
        self.assertEqual((self.workspace / "source.py").read_text(), "repair = True\n")
        self.assertEqual(self.refs(), before)

    def test_scoped_input_change_returns_exact_blocker_without_checkout_or_merge(self):
        changed = "f" * 64
        self.task["candidate_context"].update(current_input_fingerprint=changed, base_changed=True,
                                             current_staging_sha="e" * 40, rebase_required=True)
        before_head, before_refs = self.head(), self.refs()
        result = prepare_workspace(self.workspace, self.task)
        self.assertFalse(result["prepared"])
        self.assertTrue(result["rebase_required"])
        self.assertTrue(result["blocker"])
        self.assertEqual(result["blocker"]["kind"], "candidate_rebase_required")
        self.assertEqual(result["blocker"]["reason"],
                         "Relevant staging inputs changed since candidate was created; explicit rebase/revalidation is required.")
        self.assertFalse(result["blocker"]["human_required"])
        self.assertEqual(result["blocker"]["evidence"], [{
            "candidate_commit": self.candidate_sha, "parent_input_sha": self.parent_sha,
            "current_staging_sha": "e" * 40, "baseline_input_fingerprint": self.fingerprint,
            "current_input_fingerprint": changed,
        }])
        self.assertIn(self.fingerprint, str(result["blocker"]))
        self.assertIn(changed, str(result["blocker"]))
        self.assertEqual(self.head(), before_head)
        self.assertEqual(self.git("-C", str(self.workspace), "branch", "--show-current"), "staging")
        self.assertEqual((self.workspace / "source.py").read_text(), "repair = False\n")
        self.assertEqual(self.refs(), before_refs)

    def test_remote_candidate_ref_moved_rejected_without_checkout(self):
        (self.seed / "source.py").write_text("repair = 'newer unrecorded candidate'\n")
        self.git("-C", str(self.seed), "commit", "--quiet", "-am", "move candidate beyond durable evidence")
        self.git("-C", str(self.seed), "push", "--quiet", "origin", self.branch)
        before = self.head()
        with self.assertRaises(CandidateContextError):
            prepare_workspace(self.workspace, self.task)
        self.assertEqual(self.head(), before)
        self.assertEqual(self.git("-C", str(self.workspace), "branch", "--show-current"), "staging")

    def test_local_candidate_branch_is_never_reset_over_unrecorded_work(self):
        self.git("-C", str(self.workspace), "checkout", "--quiet", "--track", "origin/" + self.branch)
        self.git("-C", str(self.workspace), "config", "user.name", "Local Candidate Repair")
        self.git("-C", str(self.workspace), "config", "user.email", "local-candidate@example.invalid")
        (self.workspace / "source.py").write_text("repair = 'local work to preserve'\n")
        self.git("-C", str(self.workspace), "commit", "--quiet", "-am", "unrecorded local candidate work")
        local_commit = self.head()
        self.git("-C", str(self.workspace), "checkout", "--quiet", "staging")
        before = self.head()
        with self.assertRaises(CandidateContextError):
            prepare_workspace(self.workspace, self.task)
        self.assertEqual(self.head(), before)
        self.assertEqual(self.git("-C", str(self.workspace), "rev-parse", self.branch), local_commit)

    def test_missing_baseline_returns_unverifiable_blocker_without_checkout(self):
        self.task["candidate_context"].pop("baseline_input_fingerprint")
        before = self.head()
        result = prepare_workspace(self.workspace, self.task)
        self.assertFalse(result["prepared"])
        self.assertEqual(result["blocker"]["kind"], "unverifiable_candidate_base")
        self.assertEqual(self.head(), before)

    def test_invalid_family_branch_or_commit_rejected_before_checkout(self):
        for change in ({"branch": "staging"}, {"branch": "autonomy/public_data/fix"},
                       {"branch": "autonomy/media/fix/extra"},
                       {"commit": "abc123"}):
            with self.subTest(change=change):
                task = deepcopy(self.task)
                task["candidate_context"].update(change)
                before = self.head()
                with self.assertRaises(CandidateContextError):
                    prepare_workspace(self.workspace, task)
                self.assertEqual(self.head(), before)

    def test_dirty_tracked_checkout_is_rejected_and_preserved(self):
        (self.workspace / "source.py").write_text("uncommitted owner repair\n")
        before = self.head()
        with self.assertRaises(CandidateContextError):
            prepare_workspace(self.workspace, self.task)
        self.assertEqual(self.head(), before)
        self.assertEqual((self.workspace / "source.py").read_text(), "uncommitted owner repair\n")

    def test_declared_candidate_sha_must_match_context_commit(self):
        self.task["input_sha"] = "f" * 40
        with self.assertRaises(CandidateContextError):
            prepare_workspace(self.workspace, self.task)
        self.assertEqual(self.head(), self.parent_sha)


if __name__ == "__main__":
    unittest.main()
