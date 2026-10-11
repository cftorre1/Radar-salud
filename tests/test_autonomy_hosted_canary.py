"""Injected unit clocks and local Git authorities never prove hosted acceptance."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from scripts import autonomy_hosted_canary as canary
from scripts.autonomy_state_store import GitStateStore, Mutation, Snapshot


BASE = datetime(2026, 10, 11, tzinfo=timezone.utc)
SHA = "a" * 40
CONTEXT = {"repository": canary.REPOSITORY, "run_id": 123, "run_attempt": 1,
           "run_url": "https://github.com/cftorre1/Radar-salud/actions/runs/123",
           "infrastructure_sha": SHA, "execution_environment": "unit_test"}


class CanaryReducerTests(unittest.TestCase):
    def setUp(self):
        self.ids = canary.identifiers(canary.VERSION)
        self.snapshot = Snapshot(SHA, {})

    def advance(self, snapshot, at, context=None):
        return canary._advance(snapshot, version=canary.VERSION,
                               context=context or CONTEXT, observed_at=at)

    def pickup(self):
        return self.advance(self.snapshot, BASE)

    def test_isolated_pickup_omits_heartbeat_and_cannot_supply_live_material(self):
        mutation = self.pickup()
        state = mutation.value
        self.assertEqual(state["status"], "WAITING_HEARTBEAT")
        self.assertEqual(set(mutation.writes), {self.ids["state"], self.ids["pickup"]})
        self.assertEqual(state["engine_state"]["material_events"], [])
        self.assertEqual(state["engine_state"]["acceptance"]["mode"], "hosted_fault_injection")
        self.assertEqual(state["engine_state"]["tasks"][self.ids["task"]]["status"], "RUNNING")
        self.assertEqual(state["parent_task_id"], canary.PARENT_TASK)
        self.assertTrue(state["fault_injection"])
        self.assertFalse(state["live_acceptance_evidence"])

    def test_early_observation_has_no_writes_or_heartbeat_refresh(self):
        pickup = self.pickup()
        snapshot = Snapshot("b" * 40, {name: data.encode() for name, data in pickup.writes.items()})
        observation = self.advance(snapshot, BASE + timedelta(seconds=179))
        self.assertEqual(observation.writes, {})
        self.assertEqual(observation.value, pickup.value)

    def test_actual_elapsed_grace_detects_stall_reclaims_and_rejects_old_finish(self):
        pickup = self.pickup()
        snapshot = Snapshot("b" * 40, {name: data.encode() for name, data in pickup.writes.items()})
        result = self.advance(snapshot, BASE + timedelta(seconds=180))
        state = result.value
        self.assertEqual(state["status"], "PASS")
        self.assertEqual(state["stall_reason"], "heartbeat_missing")
        self.assertTrue(all(state["checks"].values()))
        self.assertEqual(state["engine_state"]["tasks"][self.ids["task"]]["status"], "CLOSED")
        self.assertEqual(state["engine_state"]["material_events"], [])
        self.assertEqual(state["engine_state"]["pending_transitions"], [])
        events = state["engine_state"]["lease_events"]
        self.assertEqual([event["kind"] for event in events], ["pickup", "stalled", "pickup"])
        self.assertTrue(all(event["fault_injection"] for event in events))
        proof = json.loads(result.writes[self.ids["result"]])
        self.assertEqual(proof["context"]["execution_environment"], "unit_test")
        self.assertEqual(proof["log_sha256"], canary.digest(result.writes[self.ids["log"]]))
        self.assertEqual(proof["manifest_sha256"], canary.digest(result.writes[self.ids["manifest"]]))
        self.assertEqual(proof["state_parent_sha"], snapshot.commit)

    def test_scheduled_detection_after_lease_expiry_preserves_original_pinned_sha(self):
        pickup = self.pickup()
        snapshot = Snapshot("b" * 40, {name: data.encode() for name, data in pickup.writes.items()})
        changed_context = {**CONTEXT, "infrastructure_sha": "c" * 40, "run_id": 124}
        result = self.advance(snapshot, BASE + timedelta(minutes=10), changed_context)
        self.assertEqual(result.value["status"], "PASS")
        self.assertEqual(result.value["stall_reason"], "lease_expired")
        self.assertEqual(result.value["pinned_infrastructure_sha"], SHA)
        self.assertEqual(result.value["engine_state"]["tasks"][self.ids["task"]]["attempts"], 2)

    def test_terminal_episode_never_reinjects_or_writes(self):
        pickup = self.pickup()
        files = {name: data.encode() for name, data in pickup.writes.items()}
        result = self.advance(Snapshot("b" * 40, files), BASE + timedelta(seconds=180))
        files.update({name: data.encode() for name, data in result.writes.items()})
        for hour in (1, 4, 24):
            repeated = self.advance(Snapshot("c" * 40, files), BASE + timedelta(hours=hour))
            self.assertEqual(repeated.writes, {})
            self.assertEqual(repeated.value, result.value)

    def test_unexpected_engine_failure_is_bounded_terminal_blocker(self):
        pickup = self.pickup()
        files = {name: data.encode() for name, data in pickup.writes.items()}
        with patch.object(canary.engine, "reconcile", side_effect=lambda state, queue, now: deepcopy(state)):
            result = self.advance(Snapshot("b" * 40, files), BASE + timedelta(seconds=180))
        self.assertEqual(result.value["status"], "BLOCKED")
        self.assertFalse(result.value["checks"]["stalled_detected"])
        files.update({name: data.encode() for name, data in result.writes.items()})
        self.assertEqual(self.advance(Snapshot("c" * 40, files), BASE + timedelta(hours=4)).writes, {})

    def test_invalid_version_clock_or_state_cannot_reset_authority(self):
        for version in ("../state", "", "a/b", "a" * 81):
            with self.subTest(version=version), self.assertRaises(canary.CanaryError):
                canary.identifiers(version)
        pickup = self.pickup()
        files = {name: data.encode() for name, data in pickup.writes.items()}
        with self.assertRaises(canary.CanaryError):
            self.advance(Snapshot(SHA, files), BASE - timedelta(seconds=1))
        state = json.loads(files[self.ids["state"]])
        state["fault_injection"] = False
        files[self.ids["state"]] = canary.encode(state).encode()
        with self.assertRaises(canary.CanaryError):
            self.advance(Snapshot(SHA, files), BASE + timedelta(seconds=180))

    def test_terminal_result_cannot_be_reused_without_exact_immutable_proof(self):
        pickup = self.pickup()
        files = {name: data.encode() for name, data in pickup.writes.items()}
        result = self.advance(Snapshot("b" * 40, files), BASE + timedelta(seconds=180))
        files.update({name: data.encode() for name, data in result.writes.items()})
        for path in (self.ids["pickup"], self.ids["result"], self.ids["manifest"], self.ids["log"]):
            with self.subTest(path=path):
                changed = {**files, path: b"changed"}
                with self.assertRaises(canary.CanaryError):
                    self.advance(Snapshot("c" * 40, changed), BASE + timedelta(hours=4))

    def test_unit_timestamp_episode_cannot_be_promoted_to_hosted_evidence(self):
        pickup = self.pickup()
        files = {name: data.encode() for name, data in pickup.writes.items()}
        with self.assertRaises(canary.CanaryError):
            self.advance(Snapshot(SHA, files), BASE + timedelta(seconds=180),
                         {**CONTEXT, "execution_environment": "github_actions"})

    def test_unhosted_or_invalid_run_identity_never_creates_remote_store(self):
        valid = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": canary.REPOSITORY,
                 "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
        for override in ({"GITHUB_ACTIONS": "false"}, {"GITHUB_REPOSITORY": "other/repo"},
                         {"GITHUB_RUN_ID": "abc"}, {"GITHUB_RUN_ID": "0"},
                         {"GITHUB_RUN_ATTEMPT": "0"}):
            with self.subTest(override=override), patch.dict(os.environ, {**valid, **override}), \
                 patch.object(canary, "GitStateStore") as store:
                with self.assertRaises(canary.CanaryError):
                    canary.observe_canary(".", "/tmp/canary-never-written.json")
                store.assert_not_called()


class CanaryGitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="autonomy-canary-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / "remote.git"
        self.seed = self.root / "seed"
        self.git("init", "--bare", "--quiet", str(self.remote))
        self.git("init", "--quiet", "-b", "main", str(self.seed))
        self.git("-C", str(self.seed), "config", "user.name", "Canary Unit Test")
        self.git("-C", str(self.seed), "config", "user.email", "canary@example.invalid")
        self.seed.mkdir(exist_ok=True)
        (self.seed / "product.txt").write_text("untouched\n")
        self.git("-C", str(self.seed), "add", "product.txt")
        self.git("-C", str(self.seed), "commit", "--quiet", "-m", "unit seed")
        self.git("-C", str(self.seed), "remote", "add", "origin", self.remote.as_uri())
        self.git("-C", str(self.seed), "push", "--quiet", "origin", "main", "main:staging", "main:autopilot-state")
        self.product_sha = self.git("--git-dir", str(self.remote), "rev-parse", "main")
        self.store = GitStateStore(self.remote.as_uri(), initial_backoff=0)

    @staticmethod
    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()

    def transact_at(self, at):
        return self.store.transact(lambda snapshot: canary._advance(snapshot, version=canary.VERSION,
            context={**CONTEXT, "infrastructure_sha": self.product_sha}, observed_at=at))

    def test_real_git_keeps_live_state_and_product_refs_untouched_and_terminal_noop(self):
        live = "data/autopilot/control_v2.json"
        self.store.transact(lambda snapshot: Mutation({live: '{"real_tasks":"preserved"}\n'}))
        first = self.transact_at(BASE)
        waiting = self.transact_at(BASE + timedelta(seconds=179))
        self.assertFalse(waiting.changed)
        self.assertEqual(waiting.commit, first.commit)
        last = self.transact_at(BASE + timedelta(seconds=180))
        self.assertTrue(last.changed)
        terminal = self.transact_at(BASE + timedelta(hours=4))
        self.assertFalse(terminal.changed)
        self.assertEqual(terminal.commit, last.commit)
        snapshot = self.store.read_snapshot()
        self.assertEqual(snapshot.read_json(live), {"real_tasks": "preserved"})
        ids = canary.identifiers(canary.VERSION)
        self.assertEqual(snapshot.read_json(ids["state"])["status"], "PASS")
        for branch in ("main", "staging"):
            self.assertEqual(self.git("--git-dir", str(self.remote), "rev-parse", branch), self.product_sha)

    def test_terminal_observer_does_not_even_transact(self):
        self.transact_at(BASE)
        self.transact_at(BASE + timedelta(seconds=180))
        with patch.object(canary, "hosted_context", return_value=CONTEXT), \
             patch.object(self.store, "transact", wraps=self.store.transact) as transaction:
            report = canary.observe_canary(self.seed, self.root / "report.json", store=self.store)
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["remote_changed"])
        transaction.assert_not_called()

    def test_real_concurrent_pickups_converge_to_one_fixed_episode(self):
        barrier = threading.Barrier(2)
        calls = {"first": 0, "second": 0}

        def writer(name):
            store = GitStateStore(self.remote.as_uri(), initial_backoff=0)
            def reduce(snapshot):
                calls[name] += 1
                if calls[name] == 1:
                    barrier.wait(timeout=10)
                return canary._advance(snapshot, version=canary.VERSION,
                    context={**CONTEXT, "infrastructure_sha": self.product_sha}, observed_at=BASE)
            return store.transact(reduce)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(writer, name) for name in calls]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(sum(result.changed for result in results), 1)
        self.assertEqual(sorted(result.attempts for result in results), [1, 2])
        state = self.store.read_snapshot().read_json(canary.identifiers(canary.VERSION)["state"])
        self.assertEqual(state["engine_state"]["tasks"][state["task_id"]]["attempts"], 1)
        self.assertEqual(len(state["engine_state"]["lease_events"]), 1)

    def test_hosted_identity_requires_attached_main_checkout(self):
        valid = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": canary.REPOSITORY,
                 "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
        self.git("-C", str(self.seed), "remote", "set-url", "origin",
                 "https://github.com/" + canary.REPOSITORY + ".git")
        with patch.dict(os.environ, valid):
            self.assertEqual(canary.hosted_context(self.seed)["infrastructure_sha"], self.product_sha)
            self.git("-C", str(self.seed), "checkout", "--detach", "--quiet")
            with self.assertRaises(canary.CanaryError):
                canary.hosted_context(self.seed)

    def test_hosted_environment_cannot_write_a_different_origin(self):
        valid = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": canary.REPOSITORY,
                 "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
        for origin in (self.remote.as_uri(), "https://github.com/other/repo.git",
                       "https://example.invalid/cftorre1/Radar-salud.git"):
            self.git("-C", str(self.seed), "remote", "set-url", "origin", origin)
            with self.subTest(origin=origin), patch.dict(os.environ, valid), \
                 patch.object(canary, "GitStateStore") as store:
                with self.assertRaises(canary.CanaryError):
                    canary.observe_canary(self.seed, self.root / "never.json")
                store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
