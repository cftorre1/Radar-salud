"""Observer contracts use fresh Git authority; fixtures never prove hosted autonomy."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import autonomy_engine as engine
from scripts import autonomy_observation as observer
from scripts.autonomy_state_store import GitStateStore, Snapshot


BASE = datetime(2026, 10, 11, tzinfo=timezone.utc)
MEDIA = next(task for task, family in engine.SOURCE_TASKS.items() if family == "media")


def authority():
    return {"infra_sha": "a" * 40, "staging_sha": "b" * 40,
        "queue_blob_sha": "c" * 40, "queue_sha256": "d" * 64,
        "learning_ledger_blob_sha": "e" * 40, "learning_ledger_sha256": "f" * 64,
        "queue": {"tasks": [{"id": MEDIA, "status": "approved", "owner": "Source worker", "next_action": "Repair real source", "depends_on": ["parent"]}, {"id": "unobserved", "status": "approved"}]},
        "learning_ledger": [{"id": "original-owner-stall", "status": "open", "finding": "Keep historical learning intact"}]}


def state():
    queue = {"input_sha": "b" * 40, "tasks": [{"id": MEDIA, "status": "approved", "objective": "Repair source"}]}
    current, _ = engine.claim({}, queue, "media", "123-1-media", BASE)
    current["acceptance"]["mode"] = "simulation"
    return current


def snapshot(current=None, commit="1" * 40, ledger=None):
    files = {observer.STATE: observer.encode(current or state()).encode(), "data/autopilot/legacy.json": b'{"must":"survive"}\n'}
    if ledger is not None:
        files[observer.LEDGER] = observer.encode(ledger).encode()
    return Snapshot(commit=commit, files=files)


def build(current=None, existing=None, operation="1" * 32, at=BASE + timedelta(minutes=1)):
    return observer.build_mutation(snapshot(current, ledger=existing), authority(), observed_at=at.isoformat(), operation_id=operation, run={"actions": "false"})


class ObservationTests(unittest.TestCase):
    def test_snapshot_pin_token_hash_and_no_control_or_legacy_write(self):
        initial = state(); original = deepcopy(initial); result = build(initial)
        report = result.value; token = initial["tasks"][MEDIA]["lease"]["token"]
        self.assertEqual(report["authority"]["state_sha"], "1" * 40)
        self.assertEqual(report["authority"]["queue_blob_sha"], "c" * 40)
        self.assertNotIn(token, observer.encode(report))
        self.assertEqual(report["tasks"][0]["lease"]["token_sha256"], observer.digest(token))
        self.assertNotIn(observer.STATE, result.writes)
        self.assertNotIn("data/autopilot/legacy.json", result.writes)
        self.assertEqual(initial, original)
        self.assertTrue(all(path.startswith("data/autopilot/") for path in result.writes))
        self.assertFalse(report["observation_is_material_progress"])

    def test_queue_projection_preserves_approval_dependencies_and_unknown_status(self):
        result = build(); projection = json.loads(result.writes[observer.QUEUE_PROJECTION])
        self.assertEqual(projection["tasks"][0]["queue_status"], "approved")
        self.assertEqual(projection["tasks"][0]["depends_on"], ["parent"])
        self.assertEqual(projection["tasks"][0]["runtime"]["status"], "RUNNING")
        self.assertEqual(projection["tasks"][1]["runtime"]["status"], "NOT_OBSERVED")
        self.assertFalse(projection["canonical_queue_updated"])

    def test_fenced_stall_tokens_and_token_arrays_are_hashed(self):
        initial = state(); token = initial["tasks"][MEDIA]["lease"]["token"]
        initial["lease_events"].append({"kind": "stalled", "task_id": MEDIA, "at": BASE.isoformat(), "fenced_token": token, "tokens": [token]})
        report = build(initial).value
        self.assertNotIn(token, observer.encode(report))
        self.assertEqual(report["lease_stall_events"][0]["fenced_token_sha256"], observer.digest(token))
        self.assertEqual(report["lease_stall_events"][0]["tokens_sha256"], [observer.digest(token)])
        self.assertEqual(report["tasks"][0]["lease"]["claimed_at"], BASE.isoformat().replace("+00:00", "Z"))

    def test_plural_candidate_review_authority_retains_exact_proof_reference(self):
        initial = state(); initial["tasks"][MEDIA]["candidate_reviews"] = {"a" * 40: {"candidate_commit": "a" * 40,
            "candidate_branch": "autonomy/media/reviewed", "status": "BLOCKED", "evidence_path": "data/autopilot/evidence/review.json", "evidence_sha256": "2" * 64}}
        report = build(initial).value; reviews = report["tasks"][0]["candidate_reviews"]
        self.assertEqual(reviews["a" * 40]["evidence_sha256"], "2" * 64)
        self.assertEqual(reviews["a" * 40]["status"], "BLOCKED")

    def test_owner_followups_unknown_even_with_empty_lists_or_authored_attestation(self):
        initial = state(); initial["acceptance"]["owner_observation"] = {"verified": True}
        result = build(initial).value
        self.assertEqual(result["owner_followups"], "UNKNOWN")
        self.assertIsNone(result["owner_followup_count"])
        self.assertEqual(result["criteria"]["legacy_stage_a"]["status"], "NOT_PROVEN")
        self.assertIn("owner_prompt_source_not_connected", result["criteria"]["legacy_stage_a"]["reasons"])
        self.assertFalse(result["pickup_causality_verified"])

    def test_evidenced_real_failure_escalation_does_not_claim_repair(self):
        initial = state(); task = initial["tasks"][MEDIA]
        task.update(status="BLOCKED", lease=None, last_failure={"run_id": "123", "conclusion": "failure", "run_url": "https://github.com/cftorre1/Radar-salud/actions/runs/123"},
            blocker={"fingerprint": "actual-failure", "evidence": [{"path": "failure.json", "sha256": "8" * 64}]})
        report = build(initial).value; criterion = report["criteria"]["failure_repaired_or_evidenced_escalation"]
        self.assertEqual(criterion["status"], "OBSERVED")
        self.assertEqual(criterion["escalated_task_ids"], [MEDIA])
        self.assertFalse(criterion["satisfies_legacy_stage_a_repair"])
        self.assertEqual(report["criteria"]["failure_repaired"]["status"], "NOT_OBSERVED")
        task.pop("last_failure")
        self.assertEqual(build(initial).value["criteria"]["failure_repaired_or_evidenced_escalation"]["status"], "NOT_OBSERVED")

    def test_learning_append_preserves_original_rows_and_clock_only_observation_dedupes(self):
        initial = state(); initial["tasks"][MEDIA].update(status="STALLED", reason="missing_heartbeat", lease=None)
        previous = [{"id": "legacy-entry", "opaque": {"original": True}}]
        first = build(initial, previous); ledger = json.loads(first.writes[observer.LEDGER])
        self.assertEqual(ledger[0], previous[0]); self.assertEqual(ledger[1], authority()["learning_ledger"][0])
        second = build(initial, ledger, operation="2" * 32, at=BASE + timedelta(minutes=2))
        self.assertNotIn(observer.LEDGER, second.writes)
        self.assertEqual(first.value["material_signature"], second.value["material_signature"])
        self.assertEqual(first.value["material_event_count"], second.value["material_event_count"])
        self.assertNotEqual(first.value["observed_at"], second.value["observed_at"])

    def test_existing_unsupported_ledger_fails_without_overwriting_schema(self):
        with self.assertRaises(observer.ObservationError):
            build(existing={"unrecognized": ["keep"]})

    def test_material_payload_is_bounded_while_full_count_and_signature_remain(self):
        initial = state(); initial["material_events"] = [{"id": str(index), "kind": "blocker", "at": BASE.isoformat(), "details": {}} for index in range(300)]
        report = build(initial).value
        self.assertEqual(report["material_event_count"], 300)
        self.assertEqual(report["material_events_included"], observer.RECENT_EVENTS)
        self.assertEqual(report["material_signature"], observer.digest(observer.encode(initial["material_events"])))
        self.assertEqual(report["raw_material_event_count"], 300)
        self.assertEqual(report["effective_material_event_count"], 300)
        self.assertEqual(report["corrected_material_event_count"], 0)

    def test_retracted_duplicate_blocker_is_excluded_from_progress_with_raw_history_preserved(self):
        queue = {"input_sha": "b" * 40, "tasks": []}
        failure = {"run_id": "123", "conclusion": "failure",
                   "run_url": "https://github.com/cftorre1/Radar-salud/actions/runs/123",
                   "failure_signature": "fixture-identical-normative-gate"}
        for run_id in ("123", "124"):
            queue["tasks"].append({"id": "staging_qa_failed_run_" + run_id, "family": "staging_qa",
                "status": "approved", "input_sha": "b" * 40, "input_fingerprint": "8" * 64,
                "product_input_fingerprint": "9" * 64,
                "failure": {**failure, "run_id": run_id,
                            "run_url": "https://github.com/cftorre1/Radar-salud/actions/runs/" + run_id}})
        initial, lease = engine.claim({}, queue, "staging_qa", "123-1-staging_qa", BASE)
        initial["acceptance"]["mode"] = "simulation"
        report = {"task_id": lease["task_id"], "family": "staging_qa", "status": "BLOCKED",
                  "changed_paths": [], "validated": False,
                  "blockers": [{"fingerprint": "raw-first-failure-hash", "reason": "Normative gate: 11 >= 12 failed",
                      "evidence": [{"kind": "executor_failure", "reason": "Normative gate: 11 >= 12 failed",
                                    "captured_stdout_sha256": "a" * 64, "failure_hash": "a" * 64}]}]}
        initial = engine.finish(initial, lease["task_id"], lease["token"], report, BASE + timedelta(minutes=1))
        retained = initial["material_events"][0]
        duplicate = deepcopy(retained)
        duplicate.update(id="legacy-repeated-gate-event", task_id="staging_qa_failed_run_124",
                         at=(BASE + timedelta(minutes=20)).isoformat())
        duplicate["details"]["real_failure"] = queue["tasks"][1]["failure"]
        duplicate["details"]["fingerprint"] = "raw-second-failure-hash"
        for evidence in duplicate["details"]["evidence"]:
            evidence.update(captured_stdout_sha256="c" * 64, failure_hash="c" * 64,
                            run_id="124", input_sha="c" * 40)
        initial["material_events"].append(duplicate)
        initial["tasks"][duplicate["task_id"]].update(status="BLOCKED", lease=None,
            material_progress_at=duplicate["at"], blocker=deepcopy(duplicate["details"]),
            last_failure=queue["tasks"][1]["failure"])
        corrected = engine.reconcile(initial, queue, BASE + timedelta(minutes=21))
        self.assertEqual(len(corrected["material_events"]), 2)
        self.assertEqual(len(engine.effective_material_events(corrected)), 1)
        self.assertTrue(corrected["material_event_corrections"])
        original = deepcopy(corrected)
        result = build(corrected, at=BASE + timedelta(minutes=22))
        observation = result.value
        self.assertEqual(observation["material_event_count"], 1)
        self.assertEqual(observation["effective_material_event_count"], 1)
        self.assertEqual(observation["raw_material_event_count"], 2)
        self.assertEqual(observation["corrected_material_event_count"], 1)
        self.assertEqual(observation["last_material_progress_at"], retained["at"])
        self.assertEqual(observation["raw_last_material_progress_at"], duplicate["at"])
        retracted_task = next(row for row in observation["tasks"] if row["task_id"] == duplicate["task_id"])
        self.assertIsNone(retracted_task["material_progress_at"])
        self.assertEqual(retracted_task["raw_material_progress_at"], duplicate["at"])
        self.assertEqual([event["id"] for event in observation["material_events"]], [retained["id"]])
        self.assertEqual([event["id"] for event in observation["raw_material_events"]], [retained["id"], duplicate["id"]])
        self.assertEqual(observation["material_event_corrections"], observer._safe(corrected["material_event_corrections"]))
        self.assertFalse(observation["correction_is_material_progress"])
        self.assertFalse(observation["observation_is_material_progress"])
        self.assertEqual(observation["criteria"]["useful_work_window"]["metrics"]["material_event_count"], 1)
        self.assertEqual(observation["criteria"]["durable_mutation"]["status"], "NOT_OBSERVED")
        self.assertEqual(observation["criteria"]["failure_repaired"]["status"], "NOT_OBSERVED")
        pmo = json.loads(result.writes[observer.PMO_EVIDENCE])
        self.assertEqual(pmo["material_event_count"], 1)
        self.assertEqual(pmo["raw_material_event_count"], 2)
        self.assertEqual(pmo["corrected_material_event_count"], 1)
        self.assertEqual(corrected, original)
        self.assertNotIn(observer.STATE, result.writes)

    def test_missing_control_is_explicit_and_has_no_fabricated_content_hash(self):
        result = observer.build_mutation(Snapshot(commit="1" * 40, files={}), authority(),
            observed_at=BASE.isoformat(), operation_id="1" * 32, run={})
        self.assertFalse(result.value["canonical_control_present"])
        self.assertIsNone(result.value["authority"]["state_control_sha256"])
        self.assertEqual(result.value["material_event_count"], 0)
        self.assertEqual(result.value["criteria"]["legacy_stage_a"]["status"], "NOT_PROVEN")

    def test_invalid_operation_or_state_shape_cannot_write_partial_projections(self):
        for changes in ({"tasks": []}, {"material_events": {}}, {"material_event_corrections": {}},
                        {"lease_events": {}}, {"tasks": {MEDIA: []}}):
            initial = state(); initial.update(changes)
            with self.subTest(changes=changes), self.assertRaises(observer.ObservationError):
                build(initial)
        with self.assertRaises(observer.ObservationError):
            build(operation="../../unsafe")

    def test_actual_verified_repair_event_is_distinct_from_escalation(self):
        initial = state(); initial["material_events"] = [{"id": "real-staging-repair", "kind": "mutation", "at": BASE.isoformat(),
            "task_id": "staging_qa_failure", "family": "staging_qa", "details": {"real_failure": {"run_id": "123", "conclusion": "failure",
                "run_url": "https://github.com/cftorre1/Radar-salud/actions/runs/123"}, "failure_action": "repaired", "validated": True,
                "gates": [{"command": ["python", "-m", "pytest"], "returncode": 0, "status": "PASS", "log_path": "full.log", "log_sha256": "7" * 64}]}}]
        report = build(initial).value
        self.assertEqual(report["criteria"]["failure_repaired"]["event_ids"], ["real-staging-repair"])
        self.assertTrue(report["criteria"]["failure_repaired_or_evidenced_escalation"]["satisfies_legacy_stage_a_repair"])
        self.assertEqual(report["criteria"]["legacy_stage_a"]["status"], "NOT_PROVEN")

    def test_replay_uses_fresh_snapshot_and_live_time_without_state_mutation(self):
        first = snapshot(commit="1" * 40); newer = snapshot(commit="2" * 40)
        calls = []
        class ReplayStore:
            def transact(self, reducer, message):
                calls.append(reducer(first)); calls.append(reducer(newer))
                return SimpleNamespace(value=calls[-1].value, commit="3" * 40, attempts=2)
        with tempfile.TemporaryDirectory() as directory, patch.object(observer, "capture_authority", return_value=authority()):
            report = observer.observe("infra", "staging", Path(directory) / "report.json", store=ReplayStore(),
                clock=lambda: (BASE + timedelta(minutes=1)).isoformat(), run={}, operation_id="1" * 32)
        self.assertEqual(report["authority"]["state_sha"], "2" * 40)
        self.assertEqual(report["observation_state_commit"], "3" * 40)
        self.assertEqual(report["cas_attempts"], 2)
        self.assertNotEqual(calls[0].value["authority"]["state_sha"], calls[1].value["authority"]["state_sha"])


class GitObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.workspace = self.root / "candidate"; self.remote = self.root / "state.git"
        self.git("init", "--quiet", "-b", "staging", str(self.workspace))
        self.git("-C", str(self.workspace), "config", "user.name", "Observer fixture")
        self.git("-C", str(self.workspace), "config", "user.email", "observer@example.invalid")
        for relative, payload in ((observer.QUEUE, authority()["queue"]), (observer.LEDGER, authority()["learning_ledger"]), (observer.STATE, state()), ("data/autopilot/legacy.json", {"preserve": True})):
            path = self.workspace / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(observer.encode(payload))
        self.git("-C", str(self.workspace), "add", "."); self.git("-C", str(self.workspace), "commit", "--quiet", "-m", "pinned fixture")
        self.git("init", "--bare", "--quiet", str(self.remote))
        self.git("-C", str(self.workspace), "remote", "add", "origin", self.remote.as_uri())
        self.git("-C", str(self.workspace), "push", "--quiet", "origin", "HEAD:autopilot-state", "HEAD:staging", "HEAD:main")

    def git(self, *args):
        return subprocess.check_output(["git", *args], stderr=subprocess.PIPE).decode().strip()

    def test_committed_inputs_reject_dirty_queue_and_pin_blobs(self):
        pinned = observer.capture_authority(self.workspace, self.workspace)
        self.assertEqual(pinned["queue_blob_sha"], self.git("-C", str(self.workspace), "rev-parse", "HEAD:" + observer.QUEUE))
        (self.workspace / observer.QUEUE).write_text('{"tasks": []}\n')
        with self.assertRaises(observer.ObservationError):
            observer.capture_authority(self.workspace, self.workspace)

    def test_real_git_state_publication_preserves_product_refs_and_legacy_files(self):
        before = {branch: self.git("--git-dir", str(self.remote), "rev-parse", branch) for branch in ("main", "staging")}
        store = GitStateStore(self.remote.as_uri(), initial_backoff=0)
        report = observer.observe(self.workspace, self.workspace, self.root / "report.json", store=store,
            clock=lambda: (BASE + timedelta(minutes=1)).isoformat(), run={}, operation_id="1" * 32)
        after = {branch: self.git("--git-dir", str(self.remote), "rev-parse", branch) for branch in before}
        self.assertEqual(before, after)
        snapshot = store.read_snapshot()
        self.assertEqual(snapshot.read_json(observer.STATE), state())
        self.assertEqual(snapshot.read_json("data/autopilot/legacy.json"), {"preserve": True})
        self.assertEqual(snapshot.read_json(observer.PMO_EVIDENCE)["legacy_stage_a_status"], "NOT_PROVEN")
        self.assertEqual(report["authority"]["state_sha"], before["staging"])
        self.assertFalse(report["run"]["hosted"])


if __name__ == "__main__":
    unittest.main()
