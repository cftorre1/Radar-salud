"""Targeted state-machine tests; none of these simulations prove live autonomy."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from scripts.autonomy_engine import (
    EDITORIAL_TASK, EDITORIAL_REPAIR_TASK, SOURCE_TASKS, LeaseError, ReportError, claim,
    candidate_validated, evaluate_acceptance, finish, heartbeat, plan, reconcile,
)


BASE = datetime(2026, 10, 10, tzinfo=timezone.utc)
SHA = "a" * 40
MEDIA = next(task for task, family in SOURCE_TASKS.items() if family == "media")
PUBLIC = next(task for task, family in SOURCE_TASKS.items() if family == "public_data")


def queue(*families):
    selected = families or tuple(SOURCE_TASKS.values())
    return {"input_sha": SHA, "tasks": [
        {"id": task, "status": "approved", "priority": "critical",
         "objective": "Repair " + family, "depends_on": [], "evidence_revision": "v1"}
        for task, family in SOURCE_TASKS.items() if family in selected]}


def gates():
    return [{"name": "targeted", "status": "PASS", "command": "python -m unittest",
             "returncode": 0, "log_path": "evidence/test.log", "log_sha256": "f" * 64}]


def blocked(reason="failed", fingerprint="stable", evidence=None):
    return {"status": "BLOCKED", "blockers": [{"fingerprint": fingerprint,
        "reason": reason, "evidence": evidence or [{"path": "evidence/failure.json", "sha256": "f" * 64}]}]}


def mutation(**overrides):
    report = {"status": "REPAIRED", "candidate_commit": "b" * 40,
        "changed_paths": ["config/source.json"], "validated": True, "gates": gates(),
        "before_hash": "1" * 64, "after_hash": "2" * 64,
        "evidence": [{"path": "evidence/test.log", "sha256": "f" * 64}]}
    report.update(overrides)
    return report


def passed(task_id=MEDIA):
    proof = {
        "verified": True, "task_id": task_id, "candidate_sha": SHA, "verdict": "PASS",
        "path": "evidence/acceptance.json", "sha256": "d" * 64,
        "checks": ["publication_trace", "editorial_acceptance"],
        "evidence": [{"path": "evidence/source.json", "sha256": "e" * 64}]}
    if task_id in SOURCE_TASKS:
        runtime = {"kind": "runtime_after_merge", "path": "evidence/runtime-after-merge.json",
                   "sha256": "9" * 64}
        proof.update(staging_merge_sha=SHA, origin_staging_sha=SHA,
                     runtime_after_merge=[runtime], checks={name: True for name in (
                         "external_reconciliation_30d", "external_reconciliation_90d",
                         "publication_trace", "source_health", "qa_pass",
                         "independent_review_pass", "runtime_after_merge_pass")})
        proof["evidence"].append(deepcopy(runtime))
    return {"status": "PASS", "validated": True, "gates": gates(), "acceptance_proof": [proof]}


def failure(run_id="123"):
    return {"run_id": run_id, "conclusion": "failure", "head_sha": SHA,
            "run_url": "https://github.com/cftorre1/Radar-salud/actions/runs/" + run_id}


def source_failure():
    return {"kind": "source_runtime", "verified": True,
            "source_url": "https://source.example/news", "source_slug": "diario_financiero",
            "failure_signature": "parser-failure", "trace_path": "trace.json",
            "trace_sha256": "7" * 64, "observed_at": BASE.isoformat()}


def partial():
    baseline = {**gates()[0], "status": "FAIL", "returncode": 1, "log_sha256": "3" * 64}
    candidate = {**gates()[0], "status": "FAIL", "returncode": 1, "log_sha256": "4" * 64}
    return mutation(validated=False, partial_candidate=True, targeted_validated=True,
        no_new_failures=True, candidate_scope="isolated", directed_gates=gates(),
        live_validated=True, live_gate=gates()[0],
        gates=[gates()[0], candidate], non_regression={
            "baseline_failures": ["5" * 64], "candidate_failures": ["5" * 64],
            "baseline_gate": baseline, "candidate_gate": candidate})


class AutonomyEngineTests(unittest.TestCase):
    def test_reducers_do_not_mutate_inputs(self):
        q = queue()
        original = deepcopy(q)
        initial = {}
        state, lease = claim(initial, q, "media", "worker-1", BASE)
        self.assertEqual(q, original)
        self.assertEqual(initial, {})
        preserved = deepcopy(state)
        heartbeat(state, MEDIA, lease["token"], BASE + timedelta(seconds=60))
        self.assertEqual(state, preserved)

    def test_parallel_family_claims_and_same_family_exclusion(self):
        q = queue()
        state, first = claim({}, q, "media", "one", BASE)
        state, duplicate = claim(state, q, "media", "one", BASE)
        self.assertIsNone(duplicate)
        state, other = claim(state, q, "public_data", "two", BASE)
        self.assertIsNotNone(first)
        self.assertIsNotNone(other)
        self.assertEqual(len(state["material_events"]), 0)
        self.assertEqual(len(state["lease_events"]), 2)

    def test_pickup_and_heartbeat_are_not_material_progress(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        state = heartbeat(state, MEDIA, lease["token"], BASE + timedelta(minutes=1))
        self.assertEqual(state["material_events"], [])
        self.assertNotIn("material_progress_at", state["tasks"][MEDIA])

    def test_expiration_rejects_late_heartbeat_and_finish(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        expired = BASE + timedelta(minutes=10)
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, lease["token"], expired)
        with self.assertRaises(LeaseError):
            finish(state, MEDIA, lease["token"], mutation(), expired)

    def test_reclaim_fences_late_old_worker_even_with_same_owner(self):
        q = queue("media")
        state, old = claim({}, q, "media", "worker", BASE)
        later = BASE + timedelta(minutes=11)
        state, new = claim(state, q, "media", "worker", later)
        self.assertNotEqual(old["token"], new["token"])
        self.assertGreater(new["fence"], old["fence"])
        with self.assertRaises(LeaseError):
            finish(state, MEDIA, old["token"], blocked(), later)
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, old["token"], later)
        self.assertEqual(len(state["material_events"]), 0)

    def test_heartbeats_cannot_hide_thirty_minute_material_stall(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        for minute in range(1, 30):
            state = heartbeat(state, MEDIA, lease["token"], BASE + timedelta(minutes=minute))
        at_stall = BASE + timedelta(minutes=30)
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, lease["token"], at_stall)
        state = reconcile(state, q, at_stall)
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["tasks"][MEDIA]["reason"], "no_material_progress_30m")
        self.assertEqual(state["material_events"], [])

    def test_verified_twenty_minute_work_does_not_emit_stall_or_recovery_blocker(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        for minute in range(1, 21):
            state = heartbeat(state, MEDIA, lease["token"], BASE + timedelta(minutes=minute))
        state = finish(state, MEDIA, lease["token"], mutation(), BASE + timedelta(minutes=20))
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=21))
        for minute in range(22, 41):
            state = heartbeat(state, MEDIA, lease["token"], BASE + timedelta(minutes=minute))
        state = finish(state, MEDIA, lease["token"], mutation(candidate_commit="c" * 40,
            before_hash="2" * 64, after_hash="3" * 64), BASE + timedelta(minutes=40))
        self.assertEqual([event["kind"] for event in state["material_events"]], ["mutation", "mutation"])
        self.assertFalse(any(event["kind"] == "stalled" for event in state["lease_events"]))
        self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], 0)

    def test_missing_heartbeat_stalls_before_ten_minute_lease(self):
        q = queue("media")
        state, _ = claim({}, q, "media", "worker", BASE)
        state, candidates = plan(state, q, BASE + timedelta(minutes=3))
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertIn("media", candidates)

    def test_ready_without_pickup_stalls_after_thirty_minutes_without_material_credit(self):
        q = queue("media", "public_data")
        state, candidates = plan({}, q, BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertIn("media", candidates)
        started = state["tasks"][MEDIA]["pickup_ready_since"]
        state, _ = plan(state, q, BASE + timedelta(minutes=29, seconds=59))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertEqual(state["tasks"][MEDIA]["pickup_ready_since"], started)
        state, candidates = plan(state, q, BASE + timedelta(minutes=30))
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["tasks"][MEDIA]["reason"], "no_pickup_30m")
        self.assertEqual(state["material_events"], [])
        self.assertFalse(any(event["kind"] == "pickup" for event in state["lease_events"]))
        self.assertIn("media", candidates)
        self.assertIn("public_data", candidates)

    def test_unmet_dependency_does_not_start_no_pickup_watch_until_actionable(self):
        q = queue("media", "public_data")
        media = next(task for task in q["tasks"] if task["id"] == MEDIA)
        public = next(task for task in q["tasks"] if task["id"] == PUBLIC)
        media["depends_on"] = [PUBLIC]
        state, candidates = plan({}, q, BASE)
        self.assertNotIn("media", candidates)
        self.assertFalse(state["tasks"][MEDIA].get("pickup_ready_since"))
        released = BASE + timedelta(minutes=40)
        state, candidates = plan(state, q, released)
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertNotIn("media", candidates)
        self.assertFalse(state["tasks"][MEDIA].get("pickup_ready_since"))
        public["status"] = "validated"
        state, candidates = plan(state, q, released)
        self.assertIn("media", candidates)
        ready_since = state["tasks"][MEDIA]["pickup_ready_since"]
        self.assertEqual(datetime.fromisoformat(ready_since.replace("Z", "+00:00")), released)
        state, _ = plan(state, q, released + timedelta(minutes=29, seconds=59))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        state, candidates = plan(state, q, released + timedelta(minutes=30))
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["tasks"][MEDIA]["reason"], "no_pickup_30m")
        self.assertIn("media", candidates)
        self.assertEqual(state["material_events"], [])

    def test_reclaims_preserve_absolute_material_watch_and_exhaust_without_blocking_other_family(self):
        q = queue("media", "public_data")
        state, first = claim({}, q, "media", "worker-0", BASE)
        baseline = state["tasks"][MEDIA]["material_watch_started_at"]
        previous = first
        for attempt, minute in enumerate((11, 22, 33), start=1):
            at = BASE + timedelta(minutes=minute)
            state, lease = claim(state, q, "media", "worker-" + str(attempt), at)
            self.assertIsNotNone(lease)
            self.assertNotEqual(lease["token"], previous["token"])
            self.assertGreater(lease["fence"], previous["fence"])
            self.assertEqual(state["tasks"][MEDIA]["material_watch_started_at"], baseline)
            self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], attempt)
            self.assertEqual(state["material_events"], [])
            previous = lease
        # Heartbeats extend ownership but cannot extend the recovery grace.
        for minute in range(34, 43):
            state = heartbeat(state, MEDIA, previous["token"], BASE + timedelta(minutes=minute))
            self.assertEqual(state["tasks"][MEDIA]["material_watch_started_at"], baseline)
        exhausted = BASE + timedelta(minutes=43)
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, previous["token"], exhausted)
        state = reconcile(state, q, exhausted)
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["material_events"], [])
        episode = state["tasks"][MEDIA]["recovery_episode"]
        input_fingerprint = state["tasks"][MEDIA]["input_fingerprint"]
        state, candidates = plan(state, q, exhausted)
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertNotIn("media", candidates)
        self.assertIn("public_data", candidates)
        blocker = state["tasks"][MEDIA]["blocker"]
        self.assertEqual(blocker["kind"], "stall_recovery_budget")
        self.assertIn("recovery_budget_exhausted", blocker["fingerprint"])
        self.assertEqual(blocker["reason"], "Three lease recovery pickups without material progress are exhausted.")
        self.assertFalse(blocker["human_required"])
        self.assertEqual(len(blocker["evidence"]), 1)
        evidence = blocker["evidence"][0]
        self.assertEqual(evidence["task_id"], MEDIA)
        self.assertEqual(evidence["recovery_episode"], episode)
        self.assertEqual(evidence["recovery_reclaims"], 3)
        self.assertEqual(evidence["input_fingerprint"], input_fingerprint)
        self.assertEqual(evidence["material_watch_started_at"], baseline)
        self.assertEqual(len(evidence["stalled_leases"]), 4)
        self.assertTrue(all(event["fenced_token"] for event in evidence["stalled_leases"]))
        self.assertEqual([event["kind"] for event in state["material_events"]], ["blocker"])
        again, denied = claim(state, q, "media", "worker-4", exhausted + timedelta(minutes=1))
        self.assertIsNone(denied)
        self.assertEqual(again["material_events"], state["material_events"])
        q["input_sha"] = "c" * 40
        again, denied = claim(again, q, "media", "worker-after-unrelated-staging", exhausted + timedelta(minutes=2))
        self.assertIsNone(denied)
        self.assertEqual(again["material_events"], state["material_events"])

    def test_missing_heartbeat_reclaims_preserve_absolute_watch_across_generations(self):
        q = queue("media")
        state, _ = claim({}, q, "media", "worker-0", BASE)
        baseline = state["tasks"][MEDIA]["material_watch_started_at"]
        for attempt, minute in enumerate((3, 6, 9), start=1):
            state, lease = claim(state, q, "media", "worker-" + str(attempt),
                                 BASE + timedelta(minutes=minute))
            self.assertIsNotNone(lease)
            self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], attempt)
            self.assertEqual(state["tasks"][MEDIA]["material_watch_started_at"], baseline)
            self.assertEqual(state["material_events"], [])
        state = reconcile(state, q, BASE + timedelta(minutes=12))
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["material_events"], [])
        state, denied = claim(state, q, "media", "worker-4", BASE + timedelta(minutes=12))
        self.assertIsNone(denied)
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertEqual([event["kind"] for event in state["material_events"]], ["blocker"])

    def test_verified_mutation_resets_absolute_watch_and_recovery_episode(self):
        q = queue("media")
        state, _ = claim({}, q, "media", "worker-0", BASE)
        for attempt, minute in enumerate((11, 22), start=1):
            state, lease = claim(state, q, "media", "worker-" + str(attempt),
                                 BASE + timedelta(minutes=minute))
        previous_episode = state["tasks"][MEDIA]["recovery_episode"]
        repaired_at = BASE + timedelta(minutes=23)
        state = finish(state, MEDIA, lease["token"], mutation(), repaired_at)
        task = state["tasks"][MEDIA]
        self.assertEqual(task["status"], "READY")
        self.assertEqual(task["recovery_reclaims"], 0)
        self.assertNotEqual(task["recovery_episode"], previous_episode)
        self.assertEqual(datetime.fromisoformat(task["material_watch_started_at"].replace("Z", "+00:00")),
                         repaired_at)
        self.assertEqual([event["kind"] for event in state["material_events"]], ["mutation"])
        state, lease = claim(state, q, "media", "worker-after-repair", repaired_at)
        state, new = claim(state, q, "media", "worker-after-expiry", BASE + timedelta(minutes=34))
        self.assertIsNotNone(new)
        self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], 1)
        self.assertEqual(datetime.fromisoformat(state["tasks"][MEDIA]["material_watch_started_at"].replace("Z", "+00:00")),
                         repaired_at)
        self.assertEqual([event["kind"] for event in state["material_events"]], ["mutation"])

    def test_rotating_audit_fingerprints_cannot_reset_absolute_material_watch(self):
        q = queue("media")
        state = {}
        baseline = None
        for minute in range(0, 30, 5):
            at = BASE + timedelta(minutes=minute)
            state, lease = claim(state, q, "media", "worker-" + str(minute), at)
            self.assertIsNotNone(lease)
            if baseline is None:
                baseline = state["tasks"][MEDIA]["material_watch_started_at"]
            state = finish(state, MEDIA, lease["token"], {
                "status": "SUCCESS", "audit_fingerprint": "different-observation-" + str(minute)}, at)
            self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
            self.assertEqual(state["tasks"][MEDIA]["material_watch_started_at"], baseline)
            self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], 0)
            self.assertEqual(state["material_events"], [])
        at_stall = BASE + timedelta(minutes=30)
        state, candidates = plan(state, q, at_stall)
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["tasks"][MEDIA]["reason"], "no_material_progress_30m")
        self.assertIn("media", candidates)
        self.assertEqual(state["material_events"], [])
        state, recovery = claim(state, q, "media", "recovery-worker", at_stall)
        self.assertIsNotNone(recovery)
        self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], 1)
        self.assertEqual(state["tasks"][MEDIA]["material_watch_started_at"], baseline)

    def test_queue_approval_revocation_fences_worker(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        q["tasks"][0]["status"] = "paused"
        state = reconcile(state, q, BASE + timedelta(seconds=1))
        self.assertEqual(state["tasks"][MEDIA]["status"], "REVOKED")
        with self.assertRaises(LeaseError):
            finish(state, MEDIA, lease["token"], mutation(), BASE + timedelta(seconds=2))

    def test_unrelated_staging_sha_does_not_revoke_running_parallel_lease(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        q["input_sha"] = "c" * 40
        state = reconcile(state, q, BASE + timedelta(seconds=1))
        self.assertEqual(state["tasks"][MEDIA]["input_sha"], SHA)
        self.assertEqual(state["tasks"][MEDIA]["lease"]["token"], lease["token"])
        state = finish(state, MEDIA, lease["token"], mutation(), BASE + timedelta(seconds=2))
        state = reconcile(state, q, BASE + timedelta(seconds=3))
        self.assertEqual(state["tasks"][MEDIA]["input_sha"], "c" * 40)

    def test_relevant_evidence_change_fences_running_worker(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        q["tasks"][0]["evidence_revision"] = "v2"
        state = reconcile(state, q, BASE + timedelta(seconds=1))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, lease["token"], BASE + timedelta(seconds=2))

    def test_unsupported_approved_task_is_blocked_not_completed(self):
        q = {"tasks": [{"id": "unknown_product_task", "status": "approved"}]}
        state, candidates = plan({}, q, BASE)
        self.assertEqual(candidates, {})
        self.assertEqual(state["tasks"]["unknown_product_task"]["status"], "BLOCKED")
        self.assertIn("unsupported_executor", state["tasks"]["unknown_product_task"]["blocker"]["fingerprint"])
        second = reconcile(state, q, BASE + timedelta(minutes=5))
        self.assertEqual(len(second["material_events"]), 1)

    def test_staging_qa_requires_real_failed_run_metadata(self):
        q = queue("media")
        q["tasks"].append({"id": "staging_qa_failed_run_123", "family": "staging_qa",
                           "status": "approved", "failure": failure()})
        state, candidates = plan({}, q, BASE)
        self.assertIn("media", candidates)
        self.assertIn("staging_qa", candidates)
        q["tasks"][-1]["failure"]["conclusion"] = "success"
        state, candidates = plan({}, q, BASE)
        self.assertNotIn("staging_qa", candidates)
        self.assertEqual(state["tasks"]["staging_qa_failed_run_123"]["status"], "BLOCKED")

    def test_editorial_dependency_is_not_bypassed_by_blocked_parent(self):
        parent = "source_audit_issue5_iteration1_recovery_2026_10_09"
        q = queue("media")
        q["tasks"] += [{"id": parent, "status": "in_progress"},
            {"id": EDITORIAL_TASK, "status": "in_progress", "depends_on": [parent]}]
        state, candidates = plan({}, q, BASE)
        self.assertNotIn("editorial", candidates)
        self.assertIn("media", candidates)
        q["tasks"][-2]["status"] = "validated"
        _, candidates = plan(state, q, BASE)
        self.assertIn("editorial", candidates)

    def test_independent_editorial_subtask_does_not_close_parent(self):
        q = queue("media")
        q["tasks"] += [{"id": EDITORIAL_TASK, "status": "in_progress", "depends_on": [MEDIA]},
                       {"id": EDITORIAL_REPAIR_TASK, "status": "approved", "depends_on": [],
                        "provenance": {"parent_task_id": EDITORIAL_TASK}}]
        state, lease = claim({}, q, "editorial", "worker", BASE)
        self.assertEqual(lease["task_id"], EDITORIAL_REPAIR_TASK)
        state = finish(state, EDITORIAL_REPAIR_TASK, lease["token"], passed(EDITORIAL_REPAIR_TASK), BASE)
        self.assertEqual(state["tasks"][EDITORIAL_REPAIR_TASK]["status"], "CLOSED")
        self.assertEqual(state["tasks"][EDITORIAL_TASK]["status"], "READY")

    def test_queue_blocked_by_revokes_lease_and_removal_releases_task(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        q["tasks"][0]["blocked_by"] = ["legal_review"]
        state, candidates = plan(state, q, BASE + timedelta(seconds=1))
        self.assertNotIn("media", candidates)
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, lease["token"], BASE + timedelta(seconds=2))
        q["tasks"][0]["blocked_by"] = []
        _, candidates = plan(state, q, BASE + timedelta(seconds=3))
        self.assertIn("media", candidates)

    def test_blocker_leaves_independent_families_available(self):
        q = queue()
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(), BASE + timedelta(seconds=1))
        state, candidates = plan(state, q, BASE + timedelta(seconds=2))
        self.assertNotIn("media", candidates)
        self.assertEqual(set(candidates), {"public_data", "fiscalization", "mutualities"})

    def test_three_identical_audits_block_without_crediting_success(self):
        q = queue("media")
        state = {}
        for attempt in range(3):
            at = BASE + timedelta(minutes=attempt)
            state, lease = claim(state, q, "media", "worker", at)
            state = finish(state, MEDIA, lease["token"], {"status": "SUCCESS",
                "audit_fingerprint": "same-findings", "generated_at": str(at)}, at)
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertEqual([e["kind"] for e in state["material_events"]], ["blocker"])
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=4))
        self.assertIsNone(lease)
        q["tasks"][0]["evidence_revision"] = "changed-proof"
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=5))
        self.assertIsNotNone(lease)

    def test_observation_timestamp_changes_do_not_reopen_auditor_loop(self):
        q = queue("media")
        q["tasks"][0].pop("evidence_revision")
        q["tasks"][0]["independent_review"] = {"artifact": "audit.json", "reviewed_at": "old"}
        state = {}
        for attempt in range(3):
            state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=attempt))
            state = finish(state, MEDIA, lease["token"], {"status": "SUCCESS"},
                           BASE + timedelta(minutes=attempt))
        q["tasks"][0]["independent_review"]["reviewed_at"] = "new"
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=4))
        self.assertIsNone(lease)

    def test_same_blocker_not_new_material_after_unrelated_input_change(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(), BASE)
        q["input_sha"] = "c" * 40
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=1))
        state = finish(state, MEDIA, lease["token"], blocked(), BASE + timedelta(minutes=1))
        self.assertEqual(len(state["material_events"]), 1)
        q["input_sha"] = "d" * 40
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=2))
        state = finish(state, MEDIA, lease["token"], blocked(evidence=[{"http_status": 503}]),
                       BASE + timedelta(minutes=2))
        self.assertEqual(len(state["material_events"]), 2)

    def test_alias_and_reordering_identical_blockers_cannot_manufacture_progress(self):
        q = queue("media")
        one = blocked(fingerprint="one")["blockers"][0]
        two = blocked(fingerprint="two", evidence=[{"status": 503}])["blockers"][0]
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], {"status": "BLOCKED", "blocker": one,
                       "blockers": [one, two]}, BASE)
        q["input_sha"] = "c" * 40
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=1))
        state = finish(state, MEDIA, lease["token"], {"status": "BLOCKED", "blocker": two,
                       "blockers": [two, one]}, BASE + timedelta(minutes=1))
        self.assertEqual(len(state["material_events"]), 1)

    def test_mutation_requires_durable_commit_hashes_and_executed_gates(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        for invalid in (mutation(candidate_commit=None), mutation(after_hash="1" * 64),
                        mutation(gates=["PASS"]), mutation(validated=False)):
            with self.assertRaises(ReportError):
                finish(state, MEDIA, lease["token"], invalid, BASE)
        state = finish(state, MEDIA, lease["token"], mutation(), BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertEqual(state["material_events"][0]["kind"], "mutation")
        self.assertEqual(state["material_events"][0]["details"]["parent_input_sha"], SHA)
        self.assertEqual(state["material_events"][0]["details"]["input_fingerprint"],
                         state["tasks"][MEDIA]["input_fingerprint"])

    def test_isolated_candidate_with_baseline_failure_can_make_durable_progress(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        report = partial()
        state = finish(state, MEDIA, lease["token"], report, BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertEqual(state["material_events"][0]["details"]["candidate_scope"], "isolated")
        self.assertNotIn("closure", [event["kind"] for event in state["material_events"]])

    def test_partial_candidate_requires_hashed_non_regression_and_live_directed_pass(self):
        report = partial()
        report["family"] = "media"
        self.assertTrue(candidate_validated(report))
        for field, invalid in (("non_regression", "tests unchanged"), ("directed_gates", ["PASS"]),
                               ("live_gate", None), ("candidate_scope", "staging")):
            changed = {**report, field: invalid}
            self.assertFalse(candidate_validated(changed))
        changed = deepcopy(report)
        changed["non_regression"]["candidate_failures"] = ["6" * 64]
        self.assertFalse(candidate_validated(changed))
        changed = deepcopy(report)
        changed["non_regression"]["baseline_gate"].pop("log_sha256")
        self.assertFalse(candidate_validated(changed))
        changed = deepcopy(report)
        changed["non_regression"]["candidate_failures"] = []
        changed["non_regression"]["candidate_gate"]["returncode"] = 0
        self.assertTrue(candidate_validated(changed))

    def test_generic_explicit_approved_executor_family_can_pick_next_task(self):
        q = {"input_sha": SHA, "tasks": [{"id": "source_repair_media_new_scope", "status": "approved",
                                             "executor_family": "media", "depends_on": []}]}
        _, lease = claim({}, q, "media", "worker", BASE)
        self.assertEqual(lease["task_id"], "source_repair_media_new_scope")

    def test_failure_budget_is_shared_across_new_github_run_ids(self):
        q = queue("media")
        state = {}
        for attempt in range(3):
            run_id = str(123 + attempt)
            proof = {**failure(run_id), "failure_signature": "same-test-contract"}
            q["tasks"].append({"id": "staging_qa_failed_run_" + run_id, "family": "staging_qa",
                "status": "approved", "failure": proof, "input_fingerprint": "same-relevant-code"})
            at = BASE + timedelta(minutes=attempt)
            state, lease = claim(state, q, "staging_qa", "worker", at)
            state = finish(state, lease["task_id"], lease["token"], blocked(), at)
        run_id = "126"
        q["tasks"].append({"id": "staging_qa_failed_run_" + run_id, "family": "staging_qa",
            "status": "approved", "failure": {**failure(run_id), "failure_signature": "same-test-contract"},
            "input_fingerprint": "same-relevant-code"})
        state, candidates = plan(state, q, BASE + timedelta(minutes=4))
        self.assertNotIn("staging_qa", candidates)
        self.assertIn("media", candidates)
        # The same real failure is not repeatedly credited as new progress.
        failures = [event for event in state["material_events"] if event["kind"] == "blocker"
                    and event["details"].get("fingerprint") == state["tasks"]["staging_qa_failed_run_123"]["blocker"]["fingerprint"]]
        self.assertEqual(len(failures), 1)
        q["tasks"][-1]["input_fingerprint"] = "repaired-relevant-code"
        _, candidates = plan(state, q, BASE + timedelta(minutes=5))
        self.assertIn("staging_qa", candidates)

    def test_known_source_failure_budget_does_not_reset_on_unrelated_staging_sha(self):
        q = queue("media")
        q["tasks"][0]["input_fingerprint"] = "same-media-parser"
        real = {"kind": "source_runtime", "verified": True, "source_url": "https://source.example/news",
                "failure_signature": "same-request-failure", "trace_path": "trace.json",
                "trace_sha256": "7" * 64, "observed_at": BASE.isoformat()}
        state = {}
        for attempt in range(3):
            q["input_sha"] = str(attempt) * 40
            at = BASE + timedelta(minutes=attempt)
            state, lease = claim(state, q, "media", "worker", at)
            report = {**blocked(), "real_failure": real, "failure_action": "blocked"}
            state = finish(state, MEDIA, lease["token"], report, at)
        q["input_sha"] = "9" * 40
        state, candidates = plan(state, q, BASE + timedelta(minutes=4))
        self.assertNotIn("media", candidates)
        self.assertIn("failure_budget_exhausted", state["tasks"][MEDIA]["blocker"]["fingerprint"])

    def test_same_candidate_or_unchanged_semantic_result_is_not_new_mutation(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], mutation(), BASE)
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=1))
        state = finish(state, MEDIA, lease["token"], mutation(candidate_commit="c" * 40),
                       BASE + timedelta(minutes=1))
        self.assertEqual(len(state["material_events"]), 1)

    def test_pass_requires_hash_bound_explicit_acceptance_artifact(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        for proof in ([], ["tests green"], [{"verified": True, "path": "fake"}]):
            invalid = passed()
            invalid["acceptance_proof"] = proof
            with self.assertRaises(ReportError):
                finish(state, MEDIA, lease["token"], invalid, BASE)
        report = passed()
        report["acceptance_proof"][0]["candidate_sha"] = "wrong-input"
        with self.assertRaises(ReportError):
            finish(state, MEDIA, lease["token"], report, BASE)
        state = finish(state, MEDIA, lease["token"], passed(), BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "CLOSED")

    def test_source_closure_rejects_legacy_generic_proof_without_staging_runtime_binding(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        legacy = passed()
        proof = legacy["acceptance_proof"][0]
        for field in ("staging_merge_sha", "origin_staging_sha", "runtime_after_merge"):
            proof.pop(field)
        proof["checks"] = ["publication_trace", "editorial_acceptance"]
        with self.assertRaises(ReportError):
            finish(state, MEDIA, lease["token"], legacy, BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "RUNNING")
        self.assertEqual(state["material_events"], [])

    def test_source_closure_requires_full_staging_sha_and_identical_hashed_runtime_reference(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        invalid_proofs = []
        for field, value in (("staging_merge_sha", "b" * 40), ("staging_merge_sha", "abc123"),
                             ("origin_staging_sha", "abc123"), ("runtime_after_merge", []),
                             ("runtime_after_merge", [{"kind": "runtime_after_merge", "path": "run.json"}]),
                             ("runtime_after_merge", [{"kind": "candidate_live", "path": "run.json", "sha256": "9" * 64}])):
            report = passed()
            report["acceptance_proof"][0][field] = value
            invalid_proofs.append(report)
        for field in ("staging_merge_sha", "origin_staging_sha", "runtime_after_merge"):
            report = passed()
            report["acceptance_proof"][0].pop(field)
            invalid_proofs.append(report)
        report = passed()
        report["acceptance_proof"][0]["checks"]["runtime_after_merge_pass"] = False
        invalid_proofs.append(report)
        for change in ({"path": "different-runtime.json"}, {"sha256": "8" * 64},
                       {"kind": "candidate_live"}):
            report = passed()
            report["acceptance_proof"][0]["evidence"][-1].update(change)
            invalid_proofs.append(report)
        for report in invalid_proofs:
            with self.subTest(proof=report["acceptance_proof"][0]):
                with self.assertRaises(ReportError):
                    finish(state, MEDIA, lease["token"], report, BASE)
        self.assertEqual(state["material_events"], [])

    def test_source_closure_carries_actual_last_failure_as_verified_repair(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        actual = source_failure()
        state["tasks"][MEDIA]["last_failure"] = deepcopy(actual)
        state = finish(state, MEDIA, lease["token"], passed(), BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "CLOSED")
        self.assertEqual([event["kind"] for event in state["material_events"]], ["closure"])
        details = state["material_events"][0]["details"]
        self.assertEqual(details["real_failure"], actual)
        self.assertEqual(details["failure_action"], "repaired")
        self.assertEqual(details["acceptance_proof"][0]["staging_merge_sha"], SHA)
        result = evaluate_acceptance(state, BASE, wall_now=BASE)
        self.assertNotIn("real_failure_verified_repair_not_observed", result["reasons"])

    def test_transition_credited_once_after_terminal_to_different_independent_task(self):
        q = queue()
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(), BASE)
        state, _ = claim(state, q, "public_data", "worker2", BASE + timedelta(seconds=1))
        state, _ = claim(state, q, "fiscalization", "worker3", BASE + timedelta(seconds=2))
        transitions = [e for e in state["material_events"] if e["kind"] == "transition"]
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]["details"]["from_task_id"], MEDIA)
        self.assertEqual(transitions[0]["task_id"], PUBLIC)

    def test_real_failed_run_blocker_carries_recovery_proof(self):
        q = {"input_sha": SHA, "tasks": [{"id": "staging_qa_failed_run_123",
             "status": "approved", "family": "staging_qa", "failure": failure()}]}
        state, lease = claim({}, q, "staging_qa", "worker", BASE)
        state = finish(state, lease["task_id"], lease["token"], blocked(), BASE)
        details = state["material_events"][0]["details"]
        self.assertEqual(details["real_failure"]["run_id"], "123")
        self.assertEqual(details["failure_action"], "blocked")

    def test_partial_staging_candidate_is_material_without_claiming_failed_gate_repaired(self):
        q = {"input_sha": SHA, "tasks": [{"id": "staging_qa_failed_run_123",
             "status": "approved", "family": "staging_qa", "failure": failure()}]}
        state, lease = claim({}, q, "staging_qa", "worker", BASE)
        state = finish(state, lease["task_id"], lease["token"], partial(), BASE)
        event = state["material_events"][0]
        self.assertEqual(event["kind"], "mutation")
        self.assertNotEqual(event["details"].get("failure_action"), "repaired")
        result = evaluate_acceptance(state, BASE, wall_now=BASE)
        self.assertIn("real_failure_verified_repair_not_observed", result["reasons"])

    def test_source_isolated_candidate_keeps_target_bound_progress_without_claiming_staging_repair(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        real = source_failure()
        report = partial()
        report.update(real_failure=real, failure_action="repaired", live_scope=["diario_financiero"])
        for override in ({"live_scope": ["unrelated_source"]}, {"live_gate": None}, {"targeted_validated": False}):
            invalid = {**report, **override}
            if override != {"live_scope": ["unrelated_source"]}:
                with self.assertRaises(ReportError):
                    finish(state, MEDIA, lease["token"], invalid, BASE)
            else:
                unbound = finish(state, MEDIA, lease["token"], invalid, BASE)
                self.assertNotEqual(unbound["material_events"][0]["details"].get("failure_action"), "repaired")
        candidate = finish(state, MEDIA, lease["token"], report, BASE)
        self.assertEqual(candidate["tasks"][MEDIA]["status"], "READY")
        self.assertEqual([event["kind"] for event in candidate["material_events"]], ["mutation"])
        self.assertEqual(candidate["material_events"][0]["details"]["failure_action"], "candidate_failure_resolved")
        self.assertEqual(candidate["material_events"][0]["details"]["real_failure"], real)
        result = evaluate_acceptance(candidate, BASE, wall_now=BASE)
        self.assertIn("real_failure_verified_repair_not_observed", result["reasons"])

    def test_blocked_requires_evidence_and_not_just_reason(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        for invalid in ({"status": "BLOCKED"}, {"status": "BLOCKED", "blockers": ["error"]},
                        {"status": "BLOCKED", "blockers": [{"fingerprint": "x", "reason": "y"}]}):
            with self.assertRaises(ReportError):
                finish(state, MEDIA, lease["token"], invalid, BASE)


class AcceptanceTests(unittest.TestCase):
    def observed_state(self, mode="live"):
        state = {"acceptance": {"mode": mode, "started_at": BASE.isoformat(),
                                "owner_restarts": [], "owner_prompts": [],
                                "owner_observation": {
                                    "verified": True, "started_at": BASE.isoformat(),
                                    "observed_until": (BASE + timedelta(hours=4)).isoformat(),
                                    "channels": ["github_actions", "owner_prompt_events"],
                                    "evidence": {"path": "data/autopilot/evidence/owner-window.json",
                                                 "sha256": "e" * 64}}},
                 "material_events": [], "lease_events": [{"kind": "pickup", "autonomous": True,
                                                           "at": BASE.isoformat()}]}
        for minute in range(0, 241, 20):
            event = {"kind": "mutation", "at": (BASE + timedelta(minutes=minute)).isoformat(),
                     "details": {}}
            state["material_events"].append(event)
        state["material_events"][1]["details"] = {"real_failure": failure(), "failure_action": "repaired",
                                                "validated": True, "gates": gates()}
        state["material_events"][2]["kind"] = "transition"
        state["material_events"][2]["details"] = {"independent": True}
        return state

    def test_four_real_hours_with_full_evidence_pass_evaluator(self):
        end = BASE + timedelta(hours=4)
        result = evaluate_acceptance(self.observed_state(), end, wall_now=end)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["metrics"]["max_material_gap_seconds"], 1200)
        self.assertTrue(result["metrics"]["owner_observation_verified"])

    def test_empty_owner_lists_without_observation_do_not_prove_absence(self):
        state = self.observed_state()
        del state["acceptance"]["owner_observation"]
        end = BASE + timedelta(hours=4)
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertEqual(result["status"], "NOT_PROVEN")
        self.assertEqual(result["reasons"], ["owner_intervention_observation_not_verified"])
        self.assertFalse(result["metrics"]["owner_observation_verified"])

    def test_actions_only_or_unverified_owner_observation_does_not_pass(self):
        end = BASE + timedelta(hours=4)
        for patch in ({"channels": ["github_actions"]},
                      {"channels": ["owner_prompt_events"]},
                      {"channels": "github_actions owner_prompt_events"},
                      {"verified": False}, {"verified": 1}):
            with self.subTest(patch=patch):
                state = self.observed_state()
                state["acceptance"]["owner_observation"].update(patch)
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertIn("owner_intervention_observation_not_verified", result["reasons"])

    def test_owner_observation_must_cover_the_entire_real_window(self):
        end = BASE + timedelta(hours=4)
        for patch in ({"started_at": (BASE + timedelta(seconds=1)).isoformat()},
                      {"observed_until": (end - timedelta(seconds=1)).isoformat()},
                      {"observed_until": (end + timedelta(seconds=1)).isoformat()},
                      {"started_at": (end + timedelta(seconds=1)).isoformat()}):
            with self.subTest(patch=patch):
                state = self.observed_state()
                state["acceptance"]["owner_observation"].update(patch)
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertIn("owner_intervention_observation_not_verified", result["reasons"])

    def test_owner_observation_must_have_immutable_evidence_binding(self):
        end = BASE + timedelta(hours=4)
        for evidence in (None, {},
                         {"path": "data/autopilot/evidence/owner.json", "sha256": "short"},
                         {"path": "data/autopilot/owner_latest.json", "sha256": "e" * 64},
                         {"path": "/data/autopilot/evidence/owner.json", "sha256": "e" * 64},
                         {"path": "data/autopilot/evidence/../owner.json", "sha256": "e" * 64},
                         {"path": "data/autopilot/evidence/", "sha256": "e" * 64},
                         {"path": "data/autopilot/evidence/owner\\window.json", "sha256": "e" * 64}):
            with self.subTest(evidence=evidence):
                state = self.observed_state()
                state["acceptance"]["owner_observation"]["evidence"] = evidence
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertIn("owner_intervention_observation_not_verified", result["reasons"])

    def test_malformed_owner_observation_times_fail_closed(self):
        end = BASE + timedelta(hours=4)
        for patch in ({"started_at": "invalid"}, {"observed_until": None},
                      {"observed_until": "2026-10-10T04:00:00"}):
            with self.subTest(patch=patch):
                state = self.observed_state()
                state["acceptance"]["owner_observation"].update(patch)
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertIn("owner_intervention_observation_not_verified", result["reasons"])

    def test_four_hour_block_only_window_remains_material_but_does_not_pass_stage_a(self):
        end = BASE + timedelta(hours=4)
        state = self.observed_state()
        state["material_events"][1]["kind"] = "blocker"
        state["material_events"][1]["details"] = {"real_failure": failure(), "failure_action": "blocked"}
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertEqual(result["status"], "NOT_PROVEN")
        self.assertEqual(result["reasons"], ["real_failure_verified_repair_not_observed"])
        self.assertEqual(result["metrics"]["material_event_count"], len(state["material_events"]))

    def test_legacy_partial_staging_repaired_label_does_not_prove_actual_repair(self):
        end = BASE + timedelta(hours=4)
        state = self.observed_state()
        state["material_events"][1]["details"].update(validated=False, gates=partial()["gates"], partial_candidate=True)
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertIn("real_failure_verified_repair_not_observed", result["reasons"])

    def test_legacy_source_premerge_repaired_events_cannot_pass_stage_a(self):
        end = BASE + timedelta(hours=4)
        for kind in ("mutation", "closure"):
            with self.subTest(kind=kind):
                state = self.observed_state()
                report = partial()
                legacy_proof = passed()["acceptance_proof"][0]
                for field in ("staging_merge_sha", "origin_staging_sha", "runtime_after_merge"):
                    legacy_proof.pop(field)
                state["material_events"][1].update(kind=kind, family="media", task_id=MEDIA,
                    details={**report, "real_failure": source_failure(), "failure_action": "repaired",
                             "live_scope": ["diario_financiero"], "input_sha": SHA,
                             "acceptance_proof": [legacy_proof]})
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertEqual(result["reasons"], ["real_failure_verified_repair_not_observed"])

    def test_actual_isolated_source_candidate_is_material_but_does_not_pass_stage_a(self):
        at = BASE + timedelta(minutes=20)
        control, lease = claim({}, queue("media"), "media", "worker", at)
        report = partial()
        report.update(real_failure=source_failure(), failure_action="repaired", live_scope=["diario_financiero"])
        control = finish(control, MEDIA, lease["token"], report, at)
        event = control["material_events"][0]
        self.assertEqual(event["kind"], "mutation")
        self.assertEqual(event["details"]["failure_action"], "candidate_failure_resolved")
        state = self.observed_state()
        state["material_events"][1] = event
        end = BASE + timedelta(hours=4)
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertEqual(result["status"], "NOT_PROVEN")
        self.assertEqual(result["reasons"], ["real_failure_verified_repair_not_observed"])
        self.assertEqual(result["metrics"]["material_event_count"], len(state["material_events"]))

    def test_actual_postmerge_source_closure_can_satisfy_stage_a_repair_requirement(self):
        at = BASE + timedelta(minutes=20)
        control, lease = claim({}, queue("media"), "media", "worker", at)
        control["tasks"][MEDIA]["last_failure"] = source_failure()
        control = finish(control, MEDIA, lease["token"], passed(), at)
        event = control["material_events"][0]
        self.assertEqual(event["kind"], "closure")
        self.assertEqual(event["details"]["failure_action"], "repaired")
        self.assertEqual(event["details"]["real_failure"], source_failure())
        state = self.observed_state()
        state["material_events"][1] = event
        end = BASE + timedelta(hours=4)
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["reasons"], [])

    def test_simulation_never_satisfies_live_acceptance(self):
        end = BASE + timedelta(hours=4)
        result = evaluate_acceptance(self.observed_state("simulation"), end, wall_now=end)
        self.assertIn("simulation_is_not_live_acceptance", result["reasons"])

    def test_future_clock_cannot_fake_four_elapsed_hours(self):
        result = evaluate_acceptance(self.observed_state(), BASE + timedelta(hours=4), wall_now=BASE)
        self.assertIn("four_real_wall_hours_not_observed", result["reasons"])
        self.assertIn("observation_time_is_in_the_future", result["reasons"])

    def test_owner_followup_or_material_gap_invalidates_acceptance(self):
        end = BASE + timedelta(hours=4)
        state = self.observed_state()
        state["acceptance"]["owner_prompts"] = ["novedades?"]
        state["material_events"] = state["material_events"][:3]
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertIn("owner_restart_or_followup_in_window", result["reasons"])
        self.assertIn("material_progress_gap_exceeded_30m", result["reasons"])

    def test_heartbeat_success_only_does_not_prove_acceptance(self):
        end = BASE + timedelta(hours=4)
        state = self.observed_state()
        state["material_events"] = []
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertIn("durable_verified_mutation_not_observed", result["reasons"])
        self.assertIn("real_failure_verified_repair_not_observed", result["reasons"])
        self.assertIn("automatic_independent_transition_not_observed", result["reasons"])


if __name__ == "__main__":
    unittest.main()
