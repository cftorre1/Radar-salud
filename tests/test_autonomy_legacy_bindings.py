"""Real Git provenance and CAS checks for historical input-binding imports."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import autonomy_engine as engine
import autonomy_legacy_bindings as bindings
from autonomy_runtime import FAMILY_INPUTS, scoped_fingerprint
from autonomy_state_store import GitStateStore, Mutation, Snapshot


class HistoricalBindingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "product"
        self.remote = self.root / "state.git"
        self.git("init", "--bare", str(self.remote), cwd=self.root)
        self.repo.mkdir()
        self.git("init", cwd=self.repo)
        self.git("config", "user.name", "Binding Tests")
        self.git("config", "user.email", "bindings@example.invalid")
        self.git("remote", "add", "origin", self.remote.as_uri())
        self.write("src/radar_salud/source_scouts.py", "def discover(): return []\n")
        self.write("config/sources.json", {"sources": [{"slug": "press", "url": "https://example.invalid"}]})
        self.commit("product authority")
        self.product_sha = self.git("rev-parse", "HEAD").stdout.strip()
        self.family = "media"
        self.task_id = "source_repair_media_lane_2026_10_11"
        self.product_fp = scoped_fingerprint(self.repo, self.product_sha,
            FAMILY_INPUTS[self.family] + bindings.COMMON_INPUTS)
        self.blocker = {"fingerprint": "dated-discovery-required", "reason": "No verified dated discovery",
                        "evidence": [{"source": "press", "dated": 0, "discovered": 4}]}
        self.event = {"id": "a" * 64, "task_id": self.task_id, "family": self.family,
                      "kind": "blocker", "at": "2026-10-11T05:50:00Z",
                      "details": {"blockers": [deepcopy(self.blocker)]}}
        self.task = {"id": self.task_id, "family": self.family, "input_sha": self.product_sha,
                     "product_input_fingerprint": self.product_fp, "input_fingerprint": "c" * 64,
                     "status": "BLOCKED"}
        self.worker_path = bindings.EVIDENCE + "real-worker-finish.json"
        self.worker = {"kind": "worker_result", "at": "2026-10-11T05:49:59Z",
            "report": {"task_id": self.task_id, "family": self.family,
                       "input_sha": self.product_sha, "blockers": [deepcopy(self.blocker)]}}
        self.base = {"tasks": {self.task_id: self.task}, "material_events": [],
                     "acceptance": {"started_at": "2026-10-11T05:29:46Z", "mode": "live"},
                     "lease_events": [{"kind": "pickup", "task_id": self.task_id}],
                     "failure_history": {"preserve": {"attempts": 3}}, "revision": 9}
        self.write(bindings.CONTROL, self.base)
        self.commit("control before finish")
        self.finished = deepcopy(self.base)
        self.finished["material_events"].append(self.event)
        self.write(bindings.CONTROL, self.finished)
        self.write(self.worker_path, self.worker)
        self.commit("actual worker finish")
        self.finish_sha = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("push", "origin", "HEAD:refs/heads/autopilot-state")
        self.reader = GitStateStore(repository=self.repo,
            allowed_prefixes=(bindings.CONTROL, bindings.EVIDENCE), initial_backoff=0, max_backoff=0)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.repo, text=True,
                              check=True, capture_output=True)

    def write(self, path, value):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(bindings.encode(value) if isinstance(value, (dict, list)) else value)

    def commit(self, message):
        self.git("add", ".")  # This is a disposable test repository.
        self.git("commit", "-m", message)

    def prepare(self):
        return bindings.prepare_bindings(self.reader, [self.event["id"]])

    def snapshot(self, prepared, state=None, worker=None):
        return Snapshot("d" * 40, {bindings.CONTROL: bindings.encode(state or self.finished).encode(),
            self.worker_path: bindings.encode(worker or self.worker).encode()})

    def alter_finish(self, state=None, worker=None):
        # Construct a separate actual finish authority rather than a caller assertion.
        self.git("reset", "--hard", self.finish_sha + "^")
        self.write(bindings.CONTROL, state or self.finished)
        self.write(self.worker_path, worker or self.worker)
        self.commit("revised disposable finish fixture")
        self.git("push", "--force", "origin", "HEAD:refs/heads/autopilot-state")

    def test_actual_historical_finish_binds_scoped_product_and_preserves_raw_history(self):
        prepared = self.prepare()
        actual = prepared.bindings[self.event["id"]]
        self.assertEqual(actual["proof"]["state_commit"], self.finish_sha)
        self.assertEqual(actual["input_sha"], self.product_sha)
        self.assertEqual(actual["product_input_fingerprint"], self.product_fp)
        result = self.reader.transact(lambda snap: bindings.binding_mutation(snap, prepared), message="binding metadata")
        self.assertTrue(result.changed)
        after = self.reader.read_snapshot()
        state = after.read_json(bindings.CONTROL)
        self.assertEqual({k: v for k, v in state.items() if k != bindings.REGISTRY}, self.finished)
        self.assertEqual(state[bindings.REGISTRY], prepared.bindings)
        self.assertEqual(after.read_json(prepared.proof_path), prepared.proof)
        self.assertFalse(result.value["counts_as_material_progress"])
        self.assertEqual(result.value["acceptance"], "NOT_PROVEN")
        self.assertEqual(set(result.value["paths"]), {bindings.CONTROL, prepared.proof_path})

    def test_import_is_idempotent_and_does_not_rewrite_immutable_proof(self):
        prepared = self.prepare()
        first = self.reader.transact(lambda snap: bindings.binding_mutation(snap, prepared))
        second = self.reader.transact(lambda snap: bindings.binding_mutation(snap, prepared))
        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(first.commit, second.commit)
        self.assertEqual(second.value["paths"], [])

    def test_current_task_may_advance_without_rebinding_historical_product(self):
        prepared = self.prepare()
        fresh = deepcopy(self.finished)
        fresh["tasks"][self.task_id]["input_sha"] = "e" * 40
        fresh["tasks"][self.task_id]["product_input_fingerprint"] = "f" * 64
        fresh["lease_events"].append({"kind": "heartbeat", "at": "later"})
        mutation = bindings.binding_mutation(self.snapshot(prepared, state=fresh), prepared)
        updated = json.loads(mutation.writes[bindings.CONTROL])
        self.assertEqual(updated["tasks"], fresh["tasks"])
        self.assertEqual(updated["lease_events"], fresh["lease_events"])
        self.assertEqual(updated[bindings.REGISTRY][self.event["id"]]["input_sha"], self.product_sha)

    def test_fresh_cas_preserves_a_concurrent_unrelated_state_write(self):
        prepared = self.prepare()
        calls = []
        def replay(snapshot):
            calls.append(snapshot.commit)
            mutation = bindings.binding_mutation(snapshot, prepared)
            if len(calls) == 1:
                def concurrent(snap):
                    state = snap.read_json(bindings.CONTROL)
                    state["concurrent_lane_receipt"] = "preserve me"
                    return Mutation({bindings.CONTROL: bindings.encode(state)})
                self.reader.transact(concurrent, message="concurrent independent lane")
            return mutation
        result = self.reader.transact(replay, message="verified historical binding")
        self.assertEqual(result.attempts, 2)
        self.assertNotEqual(calls[0], calls[1])
        state = self.reader.read_snapshot().read_json(bindings.CONTROL)
        self.assertEqual(state["concurrent_lane_receipt"], "preserve me")
        self.assertEqual(state["material_events"], [self.event])

    def test_reject_worker_input_not_matching_historical_task(self):
        worker = deepcopy(self.worker)
        worker["report"]["input_sha"] = "b" * 40
        self.alter_finish(worker=worker)
        with self.assertRaises(bindings.BindingVerificationError):
            self.prepare()

    def test_reject_historical_scoped_fingerprint_not_matching_actual_product_git(self):
        state = deepcopy(self.finished)
        state["tasks"][self.task_id]["product_input_fingerprint"] = "b" * 64
        self.alter_finish(state=state)
        with self.assertRaises(bindings.BindingVerificationError):
            self.prepare()

    def test_reject_different_worker_problem_even_with_same_task_and_product(self):
        worker = deepcopy(self.worker)
        worker["report"]["blockers"][0]["evidence"][0]["dated"] = 12
        self.alter_finish(worker=worker)
        with self.assertRaises(bindings.BindingVerificationError):
            self.prepare()

    def test_reject_worker_result_rewritten_after_finish(self):
        worker = deepcopy(self.worker)
        worker["extra"] = "later observation"
        self.write(self.worker_path, worker)
        self.commit("tampered old worker evidence")
        self.git("push", "origin", "HEAD:refs/heads/autopilot-state")
        with self.assertRaises(bindings.BindingVerificationError):
            self.prepare()

    def test_reject_fresh_event_or_worker_tamper_before_import(self):
        prepared = self.prepare()
        state = deepcopy(self.finished)
        state["material_events"][0]["details"]["blockers"][0]["reason"] = "different actual issue"
        with self.assertRaisesRegex(bindings.BindingVerificationError, "raw event changed"):
            bindings.binding_mutation(self.snapshot(prepared, state=state), prepared)
        worker = deepcopy(self.worker)
        worker["report"]["input_sha"] = "b" * 40
        with self.assertRaisesRegex(bindings.BindingVerificationError, "worker evidence changed"):
            bindings.binding_mutation(self.snapshot(prepared, worker=worker), prepared)

    def test_reject_conflicting_prior_binding_or_immutable_batch_proof(self):
        prepared = self.prepare()
        state = deepcopy(self.finished)
        state[bindings.REGISTRY] = {self.event["id"]: {"verified": True, "arbitrary": True}}
        with self.assertRaisesRegex(bindings.BindingVerificationError, "existing historical binding"):
            bindings.binding_mutation(self.snapshot(prepared, state=state), prepared)
        snapshot = self.snapshot(prepared)
        with self.assertRaisesRegex(bindings.BindingVerificationError, "immutable binding proof"):
            bindings.binding_mutation(Snapshot(snapshot.commit,
                {**snapshot.files, prepared.proof_path: b'{"fake":true}'}), prepared)


if __name__ == "__main__":
    unittest.main()
