"""Runtime integration with real Git authorities and real child processes."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
with patch.object(sys, "path", [str(SCRIPTS), *sys.path]):
    SPEC = importlib.util.spec_from_file_location("autonomy_runtime_test_module", SCRIPTS / "autonomy_runtime.py")
    runtime = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(runtime)


MEDIA = "source_repair_media_lane_2026_10_11"
PUBLIC = "source_repair_public_data_lane_2026_10_11"


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="autonomy-runtime-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / "remote.git"
        self.workspace = self.root / "workspace"
        self.git("init", "--bare", "--quiet", str(self.remote))
        self.git("init", "--quiet", "-b", "main", str(self.workspace))
        self.git("config", "user.name", "Runtime Test", cwd=self.workspace)
        self.git("config", "user.email", "runtime@example.invalid", cwd=self.workspace)
        files = {
            "src/product.py": "def value():\n    return 1\n",
            "src/radar_salud/press_pipeline.py": "def source_value():\n    return 1\n",
            "src/radar_salud/editorial_gate.py": "gate = True\n",
            "src/radar_salud/ai_budget.py": "budget = 1\n",
            "config/auth.json": "{}\n",
            "scripts/autonomy_lane_runner.py": "# fixture control\n",
            ".github/workflows/production.yml": "name: production\n",
            "tests/test_product.py": "# fixture test boundary\n",
            "web/data/free_value.json": '{"original": true}\n',
        }
        self.queue = {"tasks": [
            {"id": MEDIA, "family": "media", "status": "approved", "priority": "critical",
             "objective": "Repair source evidence", "depends_on": []},
            {"id": PUBLIC, "family": "public_data", "status": "approved", "priority": "normal",
             "objective": "Repair public source evidence", "depends_on": []},
        ]}
        files["config/orchestrator_queue.json"] = json.dumps(self.queue)
        for name, content in files.items():
            path = self.workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.git("add", "--", *files, cwd=self.workspace)
        self.git("commit", "--quiet", "-m", "fixture source", cwd=self.workspace)
        self.product_sha = self.git("rev-parse", "HEAD", cwd=self.workspace)
        self.git("remote", "add", "origin", self.remote.as_uri(), cwd=self.workspace)
        self.git("push", "--quiet", "origin", "main", cwd=self.workspace)
        self.git("checkout", "--quiet", "-b", "staging", cwd=self.workspace)
        self.git("push", "--quiet", "origin", "staging", cwd=self.workspace)
        self.git("checkout", "--quiet", "-b", "autopilot-state", cwd=self.workspace)
        state = self.workspace / runtime.STATE
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text("{}\n")
        self.git("add", "--", runtime.STATE, cwd=self.workspace)
        self.git("commit", "--quiet", "-m", "fixture state authority", cwd=self.workspace)
        self.git("push", "--quiet", "origin", "autopilot-state", cwd=self.workspace)
        self.git("checkout", "--quiet", "staging", cwd=self.workspace)
        self.control_scripts = self.root / "controlled-runner"
        self.control_scripts.mkdir()
        self.report = self.root / "artifacts/result.json"
        self.environment = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                            "GITHUB_REPOSITORY": "cftorre1/Radar-salud", "GITHUB_ACTIONS": "false"}

    @staticmethod
    def git(*args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()

    def remote_show(self, branch, path):
        return self.git("--git-dir", str(self.remote), "show", f"{branch}:{path}")

    def state(self):
        return json.loads(self.remote_show("autopilot-state", runtime.STATE))

    def product_refs(self):
        return {branch: self.git("--git-dir", str(self.remote), "rev-parse", "refs/heads/" + branch)
                for branch in ("main", "staging")}

    def evidenced_gate(self, command, label):
        result = subprocess.run(command, cwd=self.workspace, capture_output=True, text=True, timeout=10)
        log = self.root / "gate-evidence" / (label + ".log")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(result.stdout + result.stderr)
        return {"command": command, "returncode": result.returncode,
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "log_path": str(log), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()}

    def candidate_report(self, paths):
        gate = self.evidenced_gate([sys.executable, "-c",
            "import sys; sys.path.insert(0, 'src'); from product import value; assert value() == 2"], "directed")
        self.assertEqual(gate["returncode"], 0, "The candidate fixture itself must actually pass validation")
        return {"validated": True, "changed_paths": paths, "family": "media", "gates": [gate]}

    def invoke(self, action, family=None, **options):
        argv = ["autonomy_runtime.py", action, "--infrastructure", str(self.workspace),
                "--workspace", str(self.workspace), "--report", str(self.report)]
        if family:
            argv += ["--family", family]
        for option, value in options.items():
            argv += ["--" + option.replace("_", "-"), str(value)]
        output = io.StringIO()
        with patch.object(sys, "argv", argv), patch.dict(os.environ, self.environment), \
             patch.object(runtime, "__file__", str(self.control_scripts / "autonomy_runtime.py")), \
             contextlib.redirect_stdout(output):
            runtime.main()
        return json.loads(output.getvalue())

    def install_runner(self, mode="blocker"):
        # The runtime launches an actual Python child. The fixture performs an
        # actual source change and executable validation in mutation mode.
        runner = self.control_scripts / "autonomy_lane_runner.py"
        runner.write_text('''import argparse, hashlib, json, subprocess, sys
from pathlib import Path
p = argparse.ArgumentParser()
for name in ("family", "workspace", "task-json", "report"):
    p.add_argument("--" + name, required=True)
p.add_argument("--allow-llm", action="store_true")
p.add_argument("--input-sha")
a = p.parse_args()
w = Path(a.workspace)
t = json.loads(Path(a.task_json).read_text())
report = {"task_id": t["id"], "family": a.family, "status": "BLOCKED", "validated": False,
          "changed_paths": [], "semantic_hash": "b" * 64,
          "blockers": [{"fingerprint": "fixture-source-unavailable:" + a.family,
                        "reason": "The independent source returned an evidenced failure",
                        "evidence": [{"source_url": "https://fixture.invalid/source", "http_status": 503}]}]}
mode = ''' + repr(mode) + '''
if mode in {"mutation", "pass"}:
    source = w / "src/product.py"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    if mode == "mutation":
        source.write_text("def value():\\n    return 2\\n")
    expected = 2 if mode == "mutation" else 1
    command = [sys.executable, "-c", "import sys; sys.path.insert(0, 'src'); from product import value; assert value() == " + str(expected)]
    gate = subprocess.run(command, cwd=w, capture_output=True, text=True)
    log = Path(a.report).parent / "gate.log"
    log.write_text(gate.stdout + gate.stderr)
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    report.update(status="REPAIRED" if mode == "mutation" else "PASS", validated=gate.returncode == 0,
                  changed_paths=["src/product.py"] if mode == "mutation" else [], blockers=[],
                  before_hash=before, after_hash=after,
                  gates=[{"status": "PASS" if gate.returncode == 0 else "FAIL", "command": command,
                          "returncode": gate.returncode, "log_path": str(log),
                          "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()}])
    if mode == "pass":
        origin = subprocess.run(["git", "rev-parse", "origin/staging"], cwd=w, check=True,
                                capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "merge-base", "--is-ancestor", t["input_sha"], origin], cwd=w, check=True)
        runtime_ref = {"kind": "runtime_after_merge", "path": str(log),
                       "sha256": hashlib.sha256(log.read_bytes()).hexdigest()}
        report["acceptance_proof"] = [{"verified": True, "task_id": t["id"], "verdict": "PASS",
            "candidate_sha": t["input_sha"], "path": "src/product.py", "sha256": after,
            "staging_merge_sha": t["input_sha"], "origin_staging_sha": origin,
            "runtime_after_merge": [runtime_ref],
            "checks": {"fixture_contract": True, "runtime_after_merge_pass": True},
            "evidence": [{"path": "src/product.py", "sha256": after}, runtime_ref]}]
if mode == "failed-validation":
    (w / "src/product.py").write_text("def value():\\n    return 99\\n")
    report["changed_paths"] = ["src/product.py"]
if mode == "crash":
    print("controlled crash evidence", flush=True)
    raise RuntimeError("controlled child failure")
Path(a.report).write_text(json.dumps(report))
''')

    def test_cli_plan_dispatches_independent_families_and_writes_actions_matrix(self):
        actions_output = self.root / "github-output"
        actions_output.write_text("existing=value\n")
        self.environment["GITHUB_OUTPUT"] = str(actions_output)
        result = self.invoke("plan")
        self.assertEqual({entry["family"] for entry in result["matrix"]["include"]},
                         {"media", "public_data"})
        outputs = dict(line.split("=", 1) for line in actions_output.read_text().splitlines())
        self.assertEqual(outputs["existing"], "value")
        self.assertEqual(outputs["has_work"], "true")
        self.assertEqual(json.loads(outputs["matrix"]), result["matrix"])
        self.assertEqual(self.state()["material_events"], [])
        self.assertEqual(self.state()["acceptance"]["mode"], "simulation")
        self.assertEqual(result["acceptance"]["status"], "NOT_PROVEN")
        filtered = self.invoke("plan", "public_data")
        self.assertEqual(filtered["matrix"]["include"], [{"family": "public_data", "task_id": PUBLIC}])

    def test_controller_persists_no_pickup_stall_and_keeps_independent_recovery_dispatch(self):
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=31)
        with patch.object(runtime, "now", return_value=start.isoformat()):
            self.invoke("plan")
        initial = self.state()
        self.assertEqual(initial["tasks"][MEDIA]["status"], "READY")
        self.assertEqual(initial["tasks"][PUBLIC]["status"], "READY")
        self.assertEqual(initial["material_events"], [])
        self.assertEqual(json.loads(self.report.read_text())["stalled_tasks"], [])

        with patch.object(runtime, "now", return_value=end.isoformat()):
            result = self.invoke("plan")
        report = json.loads(self.report.read_text())
        state = self.state()
        self.assertEqual({row["task_id"] for row in report["stalled_tasks"]}, {MEDIA, PUBLIC})
        self.assertTrue(all(row["reason"] == "no_pickup_30m" for row in report["stalled_tasks"]))
        self.assertEqual({row["family"] for row in result["matrix"]["include"]}, {"media", "public_data"})
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["tasks"][PUBLIC]["status"], "STALLED")
        self.assertEqual(state["material_events"], [])
        self.assertEqual([event["kind"] for event in state["lease_events"]], ["stalled", "stalled"])
        self.assertEqual(report["acceptance"]["status"], "NOT_PROVEN")
        self.assertEqual(report["acceptance"]["metrics"]["material_event_count"], 0)
        self.assertEqual(report["acceptance"]["metrics"]["autonomous_pickups"], 0)

    def test_hosted_activation_excludes_simulated_history_and_local_read_preserves_live_window(self):
        hosted_at = datetime.now(timezone.utc)
        simulated_at = hosted_at - timedelta(hours=2)
        with patch.object(runtime, "now", return_value=simulated_at.isoformat()):
            self.invoke("plan")
        self.assertEqual(self.state()["acceptance"]["mode"], "simulation")
        store = runtime.GitStateStore(repository=self.workspace, initial_backoff=0)
        def seed_history(snapshot):
            state = snapshot.read_json(runtime.STATE)
            state["material_events"].append({"id": "old-fixture-mutation", "task_id": MEDIA, "family": "media",
                "kind": "mutation", "at": simulated_at.isoformat(), "details": {}})
            state["lease_events"].append({"task_id": MEDIA, "family": "media", "kind": "pickup",
                "at": simulated_at.isoformat(), "autonomous": True})
            state["acceptance"].update(owner_restarts=["fixture"], owner_prompts=["fixture"])
            return runtime.Mutation(runtime.state_write(state))
        store.transact(seed_history)
        self.environment["GITHUB_ACTIONS"] = "true"
        with patch.object(runtime, "now", return_value=hosted_at.isoformat()):
            report = self.invoke("plan")
        state = self.state()
        self.assertEqual(state["acceptance"]["mode"], "live")
        self.assertEqual(datetime.fromisoformat(state["acceptance"]["controller_started_at"]), hosted_at)
        self.assertNotIn("started_at", state["acceptance"])
        self.assertEqual(state["acceptance"]["owner_prompts"], [])
        self.assertEqual(state["acceptance"]["owner_restarts"], [])
        self.assertEqual(report["acceptance"]["metrics"]["material_event_count"], 0)
        self.assertEqual(report["acceptance"]["metrics"]["autonomous_pickups"], 0)
        self.assertEqual(report["acceptance"]["status"], "NOT_PROVEN")
        self.assertEqual(state["material_events"][0]["id"], "old-fixture-mutation")

        self.environment["GITHUB_ACTIONS"] = "false"
        self.invoke("plan")
        self.assertEqual(self.state()["acceptance"], state["acceptance"])

    def test_live_window_starts_in_first_durable_claim_and_later_claims_preserve_history(self):
        self.environment["GITHUB_ACTIONS"] = "true"
        self.install_runner("blocker")
        first_claim = datetime.now(timezone.utc) - timedelta(minutes=5)
        controller_start = first_claim - timedelta(hours=2)
        with patch.object(runtime, "now", return_value=controller_start.isoformat()):
            self.invoke("plan")
        self.assertNotIn("started_at", self.state()["acceptance"])
        with patch.object(runtime, "now", return_value=(first_claim - timedelta(minutes=1)).isoformat()):
            before_pickup = self.invoke("plan")
        self.assertEqual(before_pickup["acceptance"]["metrics"]["observed_seconds"], 0)
        self.assertNotIn("started_at", self.state()["acceptance"])

        store = runtime.GitStateStore(repository=self.workspace, initial_backoff=0)
        owner_history = {"owner_prompts": ["recorded owner followup"], "owner_restarts": ["recorded restart"],
                         "owner_observation": {"verified": False, "reason": "coverage not proven"}}
        def preserve_history(snapshot):
            state = snapshot.read_json(runtime.STATE)
            state["acceptance"].update(owner_history)
            return runtime.Mutation(runtime.state_write(state))
        store.transact(preserve_history)
        original_transact = store.transact
        pickups = []
        def inspect_durable_claim(mutator, *, message):
            result = original_transact(mutator, message=message)
            if message.startswith("autonomy: atomically lease"):
                pickups.append(self.state())
            return result
        with patch.object(runtime, "now", return_value=first_claim.isoformat()), \
             patch.object(runtime, "store_for", return_value=store), \
             patch.object(store, "transact", side_effect=inspect_durable_claim):
            first_report = self.invoke("execute", "media")
        self.assertEqual(pickups[0]["tasks"][MEDIA]["status"], "RUNNING")
        self.assertEqual(datetime.fromisoformat(pickups[0]["acceptance"]["started_at"]), first_claim)
        self.assertEqual(datetime.fromisoformat(pickups[0]["acceptance"]["controller_started_at"]), controller_start)
        self.assertEqual(pickups[0]["acceptance"]["first_pickup_task_id"], MEDIA)
        self.assertEqual(pickups[0]["acceptance"]["first_pickup_fence"], pickups[0]["tasks"][MEDIA]["lease"]["fence"])
        for key, value in owner_history.items():
            self.assertEqual(pickups[0]["acceptance"][key], value)
        self.assertIn("owner_intervention_observation_not_verified", first_report["acceptance"]["reasons"])
        self.assertIn("owner_restart_or_followup_in_window", first_report["acceptance"]["reasons"])
        fixed_window = self.state()["acceptance"]
        with patch.object(runtime, "now", return_value=(first_claim + timedelta(minutes=1)).isoformat()):
            second_report = self.invoke("execute", "public_data")
            self.invoke("plan")
        self.assertEqual(self.state()["acceptance"], fixed_window)
        self.assertEqual(second_report["acceptance"]["metrics"]["observed_seconds"], 60)
        self.assertEqual(second_report["acceptance"]["status"], "NOT_PROVEN")

    def test_legacy_live_clock_migrates_first_real_pickup_and_never_reanchors(self):
        observed_at = datetime.now(timezone.utc)
        activated_at = observed_at - timedelta(minutes=20)
        simulated_at = activated_at - timedelta(hours=2)
        first_claim = activated_at + timedelta(minutes=1)
        store = runtime.GitStateStore(repository=self.workspace, initial_backoff=0)
        queue = runtime.queue_for(self.workspace)
        def seed_legacy_live(snapshot):
            state, old_lease = runtime.engine.claim({}, queue, "media", "fixture-worker", simulated_at)
            state = runtime.engine.finish(state, MEDIA, old_lease["token"], {
                "task_id": MEDIA, "family": "media", "status": "BLOCKED", "changed_paths": [],
                "validated": False, "blockers": [{"fingerprint": "old-fixture", "reason": "fixture",
                    "evidence": [{"fixture": True}]}]}, simulated_at + timedelta(seconds=1))
            # A genuine relevant revision opens the task for the hosted-era claim.
            live_queue = json.loads(json.dumps(queue))
            live_queue["tasks"][0]["evidence_revision"] = "actual-hosted-executor-revision"
            state, _ = runtime.engine.claim(state, live_queue, "media", "123-1-media", first_claim)
            state["acceptance"] = {"mode": "live", "started_at": activated_at.isoformat(),
                                   "owner_prompts": ["retained"], "owner_restarts": [],
                                   "owner_observation": {"verified": False, "reason": "retained proof"}}
            return runtime.Mutation(runtime.state_write(state))
        store.transact(seed_legacy_live)
        with patch.object(runtime, "now", return_value=observed_at.isoformat()):
            self.invoke("plan")
        acceptance = self.state()["acceptance"]
        self.assertEqual(datetime.fromisoformat(acceptance["started_at"]), first_claim)
        self.assertEqual(datetime.fromisoformat(acceptance["controller_started_at"]), activated_at)
        self.assertEqual(acceptance["owner_prompts"], ["retained"])
        self.assertEqual(acceptance["owner_observation"], {"verified": False, "reason": "retained proof"})
        self.assertEqual(len([event for event in self.state()["lease_events"] if event["kind"] == "pickup"]), 2)
        with patch.object(runtime, "now", return_value=(observed_at + timedelta(minutes=1)).isoformat()):
            self.invoke("plan")
        self.assertEqual(self.state()["acceptance"], acceptance)

    def test_legacy_live_clock_can_recover_claim_from_durable_task_lease(self):
        observed_at = datetime.now(timezone.utc)
        activated_at = observed_at - timedelta(minutes=5)
        first_claim = activated_at + timedelta(minutes=1)
        store = runtime.GitStateStore(repository=self.workspace, initial_backoff=0)
        queue = runtime.queue_for(self.workspace)
        def seed_lease(snapshot):
            state, _ = runtime.engine.claim({}, queue, "media", "123-1-media", first_claim)
            state["lease_events"] = []
            state["acceptance"] = {"mode": "live", "started_at": activated_at.isoformat(),
                                   "owner_prompts": [], "owner_restarts": []}
            return runtime.Mutation(runtime.state_write(state))
        store.transact(seed_lease)
        with patch.object(runtime, "now", return_value=observed_at.isoformat()):
            self.invoke("plan")
        self.assertEqual(datetime.fromisoformat(self.state()["acceptance"]["started_at"]), first_claim)
        self.assertEqual(self.state()["acceptance"]["window_started_by"], "first_durable_pickup")

    def test_trusted_runtime_uses_exact_candidate_ancestry_for_current_staging_continuation(self):
        baseline_queue = runtime.queue_for(self.workspace)
        baseline_fingerprint = baseline_queue["tasks"][0]["input_fingerprint"]
        (self.workspace / "src/product.py").write_text("def value():\n    return 2\n")
        (self.workspace / "src/radar_salud/press_pipeline.py").write_text("def source_value():\n    return 2\n")
        candidate = runtime.persist_candidate(self.workspace, "media", "continuation-fixture",
            self.candidate_report(["src/product.py", "src/radar_salud/press_pipeline.py"]))
        commit = candidate["candidate_commit"]
        state = {"tasks": {MEDIA: {"family": "media", "candidate_review": {
            "candidate_commit": commit, "candidate_branch": candidate["candidate_branch"],
            "candidate_scope": "isolated", "status": "PASS", "technical_review_pass": True}}},
            "material_events": [{"kind": "mutation", "task_id": MEDIA, "family": "media", "details": {
                "candidate_commit": commit, "candidate_branch": candidate["candidate_branch"],
                "candidate_scope": "isolated", "parent_input_sha": self.product_sha,
                "input_fingerprint": baseline_fingerprint,
                "product_input_fingerprint": baseline_queue["tasks"][0]["product_input_fingerprint"]}}]}

        self.git("checkout", "--quiet", "--detach", self.product_sha, cwd=self.workspace)
        self.git("branch", "-f", "staging", self.product_sha, cwd=self.workspace)
        self.git("checkout", "--quiet", "staging", cwd=self.workspace)
        unmerged_queue = runtime.queue_for(self.workspace)
        self.assertEqual(runtime.integrated_candidates(self.workspace, unmerged_queue, state), set())
        unmerged = runtime.overlay_queue(unmerged_queue, state)["tasks"][0]
        self.assertEqual(unmerged["input_sha"], commit)
        self.assertFalse(unmerged["candidate_context"]["integrated_into_staging"])

        # Simulate a separately authorized integration only in this private
        # fixture's local ref. The runtime continuation never performs it.
        self.git("checkout", "--quiet", "--detach", commit, cwd=self.workspace)
        (self.workspace / "web/data/free_value.json").write_text('{"new_staging": true}\n')
        self.git("commit", "--quiet", "-am", "fixture independently integrated descendant", cwd=self.workspace)
        current = self.git("rev-parse", "HEAD", cwd=self.workspace)
        self.git("branch", "-f", "staging", current, cwd=self.workspace)
        self.git("checkout", "--quiet", "staging", cwd=self.workspace)
        current_queue = runtime.queue_for(self.workspace)
        proofs = runtime.integrated_candidates(self.workspace, current_queue, state)
        self.assertEqual(proofs, {commit})
        task = runtime.overlay_queue(current_queue, state, integrated_candidate_commits=proofs)["tasks"][0]
        self.assertNotEqual(task["candidate_context"]["baseline_input_fingerprint"],
                            task["candidate_context"]["current_input_fingerprint"])
        self.assertEqual(task["input_sha"], current)
        self.assertTrue(task["candidate_context"]["integrated_into_staging"])
        before_refs = self.product_refs()
        prepared = runtime.prepare_workspace(self.workspace, task)
        self.assertTrue(prepared["prepared"])
        self.assertFalse(prepared["rebase_required"])
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.workspace), current)
        self.assertEqual(self.git("branch", "--show-current", cwd=self.workspace), "staging")
        self.assertEqual((self.workspace / "web/data/free_value.json").read_text(), '{"new_staging": true}\n')
        self.assertEqual(self.product_refs(), before_refs)
        with self.assertRaises(runtime.CandidateContextError):
            runtime.integrated_candidates(self.workspace, unmerged_queue, state)

        # A newer unrecorded/nonexistent candidate cannot use an older proof.
        state["material_events"].append({"kind": "mutation", "task_id": MEDIA,
            "details": {"candidate_scope": "isolated", "candidate_commit": "f" * 40}})
        self.assertEqual(runtime.integrated_candidates(self.workspace, current_queue, state), set())

    def test_scoped_qa_inputs_track_product_meaning_without_snapshot_or_queue_clock_churn(self):
        source_families = set(runtime.engine.SOURCE_TASKS.values())
        present = {task["id"] for task in self.queue["tasks"]}
        for task_id, family in runtime.engine.SOURCE_TASKS.items():
            if task_id not in present:
                self.queue["tasks"].append({"id": task_id, "family": family, "status": "approved",
                                           "objective": "Fixture independent source", "depends_on": []})
        snapshot = {"generated_at": "old observation", "signals": [{"title": "Verified normative signal",
            "event_date": "2026-10-10", "publication_date": "2026-10-10", "signal_types": ["Normativa"]}]}
        fixtures = {
            "config/orchestrator_queue.json": json.dumps(self.queue),
            "config/sources.json": json.dumps([{"slug": "fixture", "listing_url": "https://fixture.invalid/old",
                                                 "updated_at": "old source observation"}]),
            "web/data/radar_today.json": json.dumps(snapshot),
            "config/normative_editorial_v2.json": '{"minimum_visible_normative_signals": 12}',
            "web/app.js": "const fixtureVersion = 1;\n",
            "docs/README.md": "Unrelated fixture documentation\n",
        }
        for path, content in fixtures.items():
            target = self.workspace / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)

        def commit(paths, message):
            self.git("add", "--", *paths, cwd=self.workspace)
            self.git("commit", "--quiet", "-m", message, cwd=self.workspace)

        commit(list(fixtures), "scoped product fingerprint fixtures")
        failure_path = self.root / "fixture-failure.json"
        failure_path.write_text(json.dumps({"run_id": "999", "conclusion": "failure", "head_branch": "staging",
            "run_url": "https://github.com/cftorre1/Radar-salud/actions/runs/999",
            "failure_signature": hashlib.sha256(b"fixture normative gate failure").hexdigest()}))

        def fingerprints():
            queue = runtime.queue_for(self.workspace, str(failure_path))
            return {runtime.engine._family(task): task["input_fingerprint"] for task in queue["tasks"]}

        baseline = fingerprints()
        before_remote_refs = self.product_refs()
        snapshot["generated_at"] = "new observation"
        (self.workspace / "web/data/radar_today.json").write_text(json.dumps(snapshot))
        commit(["web/data/radar_today.json"], "observation clock only")
        self.assertEqual(fingerprints(), baseline)

        # Working bytes cannot substitute for the committed staging authority.
        uncommitted = {**snapshot, "signals": []}
        (self.workspace / "web/data/radar_today.json").write_text(json.dumps(uncommitted))
        self.assertEqual(fingerprints(), baseline)
        (self.workspace / "web/data/radar_today.json").write_text(json.dumps(snapshot))

        previous = baseline
        for field, value in (("event_date", "2026-10-11"), ("publication_date", "2026-10-11"),
                             ("title", "Materially changed verified normative content")):
            with self.subTest(material_field=field):
                snapshot["signals"][0][field] = value
                (self.workspace / "web/data/radar_today.json").write_text(json.dumps(snapshot))
                commit(["web/data/radar_today.json"], "material product " + field)
                current = fingerprints()
                self.assertNotEqual(current["staging_qa"], previous["staging_qa"])
                self.assertEqual({family: current[family] for family in source_families},
                                 {family: baseline[family] for family in source_families})
                previous = current

        for path, content in (("config/normative_editorial_v2.json", '{"minimum_visible_normative_signals": 13}'),
                              ("web/app.js", "const fixtureVersion = 2;\n")):
            with self.subTest(product_input=path):
                (self.workspace / path).write_text(content)
                commit([path], "real product contract or UI change")
                current = fingerprints()
                self.assertNotEqual(current["staging_qa"], previous["staging_qa"])
                self.assertEqual({family: current[family] for family in source_families},
                                 {family: baseline[family] for family in source_families})
                previous = current

        self.queue["updated_at"] = "new queue observation"
        (self.workspace / "config/orchestrator_queue.json").write_text(json.dumps(self.queue))
        (self.workspace / "docs/README.md").write_text("Unrelated new documentation\n")
        commit(["config/orchestrator_queue.json", "docs/README.md"], "unrelated queue and documentation clocks")
        self.assertEqual(fingerprints(), previous)

        catalog = json.loads((self.workspace / "config/sources.json").read_text())
        catalog[0]["updated_at"] = "new source observation"
        (self.workspace / "config/sources.json").write_text(json.dumps(catalog))
        commit(["config/sources.json"], "source catalog observation clock only")
        self.assertEqual(fingerprints(), previous)
        catalog[0]["listing_url"] = "https://fixture.invalid/new"
        (self.workspace / "config/sources.json").write_text(json.dumps(catalog))
        commit(["config/sources.json"], "actual source catalog input change")
        current = fingerprints()
        for family in source_families:
            self.assertNotEqual(current[family], previous[family])
        self.assertNotEqual(current["staging_qa"], previous["staging_qa"])
        self.assertEqual(self.product_refs(), before_remote_refs)

    def test_unreadable_committed_json_retains_raw_identity_without_blocking_fingerprinting(self):
        path = "web/data/free_value.json"
        head = self.git("rev-parse", "HEAD", cwd=self.workspace)
        previous = runtime.scoped_fingerprint(self.workspace, head, [path])
        before_refs = self.product_refs()
        for content in (b"{ invalid json", b"\xff", b"\xfe"):
            with self.subTest(content=content):
                (self.workspace / path).write_bytes(content)
                self.git("add", "--", path, cwd=self.workspace)
                self.git("commit", "--quiet", "-m", "unreadable JSON raw identity fixture", cwd=self.workspace)
                head = self.git("rev-parse", "HEAD", cwd=self.workspace)
                current = runtime.scoped_fingerprint(self.workspace, head, [path])
                self.assertNotEqual(current, previous)
                previous = current
        self.assertEqual(self.product_refs(), before_refs)

    def infrastructure_fixture(self):
        infrastructure = self.root / "infrastructure"
        self.git("init", "--quiet", "-b", "main", str(infrastructure))
        self.git("config", "user.name", "Infrastructure Test", cwd=infrastructure)
        self.git("config", "user.email", "infrastructure@example.invalid", cwd=infrastructure)
        fixtures = {"scripts/autonomy_lane_runner.py": "def run():\n    return 1\n",
                    "scripts/autonomy_recovery.py": "def repair():\n    return 1\n",
                    "scripts/autonomy_observation.py": "def observe():\n    return 1\n",
                    "scripts/autonomy_hosted_canary.py": "def canary():\n    return 1\n",
                    "docs/README.md": "Infrastructure fixture\n"}
        for path, content in fixtures.items():
            target = infrastructure / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        self.git("add", "--", *fixtures, cwd=infrastructure)
        self.git("commit", "--quiet", "-m", "fixture infrastructure", cwd=infrastructure)
        return infrastructure

    def test_executor_fingerprint_uses_committed_infrastructure_code_without_main_sha_churn(self):
        infrastructure = self.infrastructure_fixture()
        before_refs = self.product_refs()
        failure_path = self.root / "failed-run.json"
        failure_path.write_text(json.dumps({"run_id": 85, "conclusion": "failure",
            "run_url": "https://github.com/cftorre1/Radar-salud/actions/runs/85"}))
        def observe():
            queue = runtime.queue_for(self.workspace, failure_path, infrastructure)
            return queue, {runtime.engine._family(task): task for task in queue["tasks"]}
        original_queue, original = observe()
        self.assertEqual(set(original), {"media", "public_data", "staging_qa"})

        for path in ("docs/README.md", "scripts/autonomy_observation.py", "scripts/autonomy_hosted_canary.py"):
            with self.subTest(unrelated_input=path):
                (infrastructure / path).write_text("# unrelated committed observer, canary or documentation change\n")
                self.git("add", "--", path, cwd=infrastructure)
                self.git("commit", "--quiet", "-m", "unrelated infrastructure change", cwd=infrastructure)
                current_queue, current = observe()
                self.assertNotEqual(current_queue["infrastructure_sha"], original_queue["infrastructure_sha"])
                self.assertEqual(current, original)

        for path in runtime.EXECUTOR_INPUTS:
            with self.subTest(executor_input=path):
                (infrastructure / path).write_text("def repaired_executor():\n    return 2\n")
                self.assertEqual(observe()[1], original, "Uncommitted infrastructure is never authority")
                self.git("add", "--", path, cwd=infrastructure)
                self.git("commit", "--quiet", "-m", "meaningful executor repair", cwd=infrastructure)
                _, current = observe()
                for family, task in current.items():
                    self.assertEqual(task["input_sha"], original[family]["input_sha"])
                    self.assertEqual(task["product_input_fingerprint"], original[family]["product_input_fingerprint"])
                    self.assertNotEqual(task["executor_fingerprint"], original[family]["executor_fingerprint"])
                    self.assertNotEqual(task["input_fingerprint"], original[family]["input_fingerprint"])
                original = current
        self.assertEqual(self.product_refs(), before_refs)

    def test_committed_executor_repair_reopens_exhausted_failure_without_erasing_history(self):
        infrastructure = self.infrastructure_fixture()
        failure_path = self.root / "failed-run.json"
        failure_path.write_text(json.dumps({"run_id": 85, "conclusion": "failure",
            "failure_signature": "fixture-repeated-browser-gate-failure",
            "run_url": "https://github.com/cftorre1/Radar-salud/actions/runs/85"}))
        at = datetime.now(timezone.utc)
        store = runtime.GitStateStore(repository=self.workspace, initial_backoff=0)
        for attempt in range(3):
            queue = runtime.queue_for(self.workspace, failure_path, infrastructure)
            qa = next(task for task in queue["tasks"] if task["family"] == "staging_qa")
            qa["evidence_revision"] = "fixture-approved-repair-attempt-" + str(attempt)
            def fail(snapshot):
                state, lease = runtime.engine.claim(runtime.initial_state(snapshot), queue,
                                                     "staging_qa", "fixture-worker", at)
                self.assertIsNotNone(lease)
                report = {"task_id": lease["task_id"], "family": "staging_qa", "status": "BLOCKED",
                          "changed_paths": [], "validated": False,
                          "blockers": [{"fingerprint": "unchanged-browser-failure", "reason": "fixture gate failure",
                                        "evidence": [{"run_url": qa["failure"]["run_url"], "failure_signature": qa["failure"]["failure_signature"]}]}]}
                state = runtime.engine.finish(state, lease["task_id"], lease["token"], report, at)
                return runtime.Mutation(runtime.state_write(state))
            store.transact(fail)
        queue = runtime.queue_for(self.workspace, failure_path, infrastructure)
        qa_id = "staging_qa_failed_run_85"
        exhausted, selected = runtime.engine.plan(self.state(), queue, at)
        self.assertNotIn("staging_qa", selected)
        self.assertEqual(set(selected), {"media", "public_data"})
        self.assertTrue(exhausted["tasks"][qa_id]["blocker"]["fingerprint"].startswith("failure_budget_exhausted:"))
        old_history = exhausted["failure_history"]
        self.assertEqual([row["attempts"] for row in old_history.values()], [3])
        before_material = exhausted["material_events"]

        (infrastructure / "scripts/autonomy_recovery.py").write_text("def repair():\n    return 'actual new fixture validation'\n")
        self.git("add", "--", "scripts/autonomy_recovery.py", cwd=infrastructure)
        self.git("commit", "--quiet", "-m", "repair executor validation", cwd=infrastructure)
        repaired_queue = runtime.queue_for(self.workspace, failure_path, infrastructure)
        reopened, selected = runtime.engine.plan(exhausted, repaired_queue, at)
        self.assertIn("staging_qa", selected)
        self.assertEqual(reopened["tasks"][qa_id]["status"], "READY")
        self.assertEqual(reopened["failure_history"], old_history)
        self.assertEqual(reopened["material_events"], before_material)
        self.assertEqual(reopened["tasks"][qa_id]["input_sha"], exhausted["tasks"][qa_id]["input_sha"])
        self.assertEqual(reopened["tasks"][qa_id]["product_input_fingerprint"], exhausted["tasks"][qa_id]["product_input_fingerprint"])
        self.assertNotEqual(reopened["tasks"][qa_id]["input_fingerprint"], exhausted["tasks"][qa_id]["input_fingerprint"])

    def test_cli_controller_automatically_reopens_worker_blocker_after_infrastructure_repair(self):
        infrastructure = self.infrastructure_fixture()
        self.git("remote", "add", "origin", self.remote.as_uri(), cwd=infrastructure)
        self.install_runner("blocker")
        before_refs = self.product_refs()
        self.invoke("execute", "media", infrastructure=infrastructure)
        blocked = self.state()
        self.assertEqual(blocked["tasks"][MEDIA]["status"], "BLOCKED")
        unchanged = self.invoke("plan", infrastructure=infrastructure)
        self.assertEqual(unchanged["matrix"]["include"], [{"family": "public_data", "task_id": PUBLIC}])
        recovery = infrastructure / "scripts/autonomy_recovery.py"
        recovery.write_text("def repair():\n    return 'corrected fixture executor'\n")
        uncommitted = self.invoke("plan", infrastructure=infrastructure)
        self.assertEqual(uncommitted["matrix"], unchanged["matrix"])
        self.git("add", "--", "scripts/autonomy_recovery.py", cwd=infrastructure)
        self.git("commit", "--quiet", "-m", "correct executor repair", cwd=infrastructure)
        next_plan = self.invoke("plan", infrastructure=infrastructure)
        self.assertEqual({entry["family"] for entry in next_plan["matrix"]["include"]}, {"media", "public_data"})
        resumed = self.state()
        self.assertEqual(resumed["tasks"][MEDIA]["status"], "READY")
        self.assertEqual(resumed["tasks"][MEDIA]["input_sha"], blocked["tasks"][MEDIA]["input_sha"])
        self.assertEqual(resumed["tasks"][MEDIA]["product_input_fingerprint"], blocked["tasks"][MEDIA]["product_input_fingerprint"])
        self.assertNotEqual(resumed["tasks"][MEDIA]["executor_fingerprint"], blocked["tasks"][MEDIA]["executor_fingerprint"])
        self.assertEqual(resumed["material_events"], blocked["material_events"])
        self.assertEqual(self.product_refs(), before_refs)

    def test_cli_claim_mutation_finish_keeps_product_refs_and_records_durable_candidate(self):
        self.install_runner("mutation")
        before = self.product_refs()
        report = self.invoke("execute", "media")
        self.assertEqual(report["status"], "REPAIRED")
        self.assertEqual(self.product_refs(), before)
        self.assertEqual(self.remote_show(report["candidate_branch"], "src/product.py"),
                         "def value():\n    return 2")
        self.assertEqual(self.git("--git-dir", str(self.remote), "rev-parse", report["candidate_branch"]),
                         report["candidate_commit"])
        state = self.state()
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertIsNone(state["tasks"][MEDIA]["lease"])
        self.assertEqual([event["kind"] for event in state["material_events"]], ["mutation"])
        self.assertEqual(state["material_events"][0]["details"]["candidate_commit"], report["candidate_commit"])
        self.assertTrue(state["lease_events"][0]["autonomous"])
        evidence_paths = self.git("--git-dir", str(self.remote), "ls-tree", "-r", "--name-only",
                                  "autopilot-state", "data/autopilot/evidence").splitlines()
        self.assertEqual(len(evidence_paths), 2)
        evidence = [json.loads(self.remote_show("autopilot-state", path)) for path in evidence_paths]
        self.assertEqual({row["kind"] for row in evidence}, {"pickup", "worker_result"})

    def test_worker_without_approved_family_persists_report_without_material_credit(self):
        before_refs = self.product_refs()
        observed_commit = self.git("--git-dir", str(self.remote), "rev-parse", "autopilot-state")
        report = self.invoke("execute", "mutualities")
        self.assertEqual(report, json.loads(self.report.read_text()))
        self.assertEqual(report["status"], "NO_EXECUTABLE_TASK")
        self.assertEqual(report["reason"], "no_approved_task_for_family")
        self.assertEqual(report["family"], "mutualities")
        self.assertEqual(report["run_url"], "https://github.com/cftorre1/Radar-salud/actions/runs/123")
        self.assertEqual(report["observed_state_commit"], observed_commit)
        self.assertEqual(report["state_commit"], self.git("--git-dir", str(self.remote), "rev-parse", "autopilot-state"))
        self.assertFalse(report["material_progress"])
        self.assertEqual(report["changed_paths"], [])
        self.assertEqual(self.state()["material_events"], [])
        self.assertEqual(self.state()["lease_events"], [])
        self.assertEqual(self.product_refs(), before_refs)
        paths = self.git("--git-dir", str(self.remote), "ls-tree", "-r", "--name-only",
                         "autopilot-state", "data/autopilot/evidence").splitlines()
        self.assertEqual(len(paths), 1)
        evidence = json.loads(self.remote_show("autopilot-state", paths[0]))
        self.assertEqual(evidence["kind"], "worker_observation")
        self.assertEqual(evidence["report"]["observed_state_commit"], observed_commit)

    def test_worker_without_available_lease_reports_existing_owner_and_preserves_task(self):
        store = runtime.GitStateStore(repository=self.workspace, initial_backoff=0)
        queue = runtime.queue_for(self.workspace)
        def acquire(snapshot):
            state, lease = runtime.engine.claim(runtime.initial_state(snapshot), queue,
                                                 "media", "other-worker", runtime.now())
            return runtime.Mutation(runtime.state_write(state), lease)
        lease = store.transact(acquire).value
        before = self.state()
        report = self.invoke("execute", "media")
        self.assertEqual(report["status"], "NO_EXECUTABLE_TASK")
        self.assertEqual(report["reason"], "family_already_leased")
        self.assertEqual(report["family_tasks"], [{"task_id": MEDIA, "status": "RUNNING",
                                                   "reason": None, "awaiting_dependencies": False}])
        self.assertEqual(self.state()["tasks"][MEDIA], before["tasks"][MEDIA])
        self.assertEqual(self.state()["tasks"][MEDIA]["lease"]["token"], lease["token"])
        self.assertEqual(self.state()["lease_events"], before["lease_events"])
        self.assertEqual(self.state()["material_events"], [])
        self.assertEqual(self.state()["tasks"][PUBLIC]["status"], "READY")

    def test_repeated_blocked_worker_report_never_counts_an_identical_blocker_as_progress(self):
        self.install_runner("blocker")
        self.invoke("execute", "media")
        before = self.state()
        report = self.invoke("execute", "media")
        self.assertEqual(report["reason"], "family_blocked")
        self.assertEqual(report["family_tasks"][0]["status"], "BLOCKED")
        self.assertFalse(report["material_progress"])
        self.assertEqual(self.state()["material_events"], before["material_events"])
        self.assertEqual(self.state()["lease_events"], before["lease_events"])

    def test_blocker_finishes_lease_and_next_independent_pickup_is_transition(self):
        self.install_runner("blocker")
        self.invoke("execute", "media")
        state = self.state()
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        next_plan = self.invoke("plan")
        self.assertEqual(next_plan["matrix"]["include"], [{"family": "public_data", "task_id": PUBLIC}])
        self.invoke("execute", "public_data")
        transitions = [event for event in self.state()["material_events"] if event["kind"] == "transition"]
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]["details"]["from_task_id"], MEDIA)
        self.assertEqual(transitions[0]["task_id"], PUBLIC)
        self.assertTrue(transitions[0]["details"]["independent"])

    def test_pass_closes_verified_task_and_automatically_dispatches_next_family(self):
        self.install_runner("pass")
        self.invoke("execute", "media")
        state = self.state()
        self.assertEqual(state["tasks"][MEDIA]["status"], "CLOSED")
        self.assertEqual([event["kind"] for event in state["material_events"]], ["closure"])
        next_plan = self.invoke("plan")
        self.assertEqual(next_plan["matrix"]["include"], [{"family": "public_data", "task_id": PUBLIC}])

    def test_failed_validation_preserves_blocker_without_publishing_candidate(self):
        self.install_runner("failed-validation")
        before = self.product_refs()
        report = self.invoke("execute", "media")
        self.assertFalse(report["validated"])
        self.assertEqual(report["changed_paths"], [])
        self.assertEqual(report["rejected_candidate_paths"], ["src/product.py"])
        self.assertEqual(report["blockers"][0]["fingerprint"], "fixture-source-unavailable:media")
        self.assertEqual(self.state()["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertEqual(self.product_refs(), before)
        self.assertFalse(any(event["kind"] == "mutation" for event in self.state()["material_events"]))
        self.assertEqual(self.git("--git-dir", str(self.remote), "for-each-ref", "--format=%(refname)",
                                 "refs/heads/autonomy/"), "")

    def test_child_crash_fallback_fingerprint_is_accepted_by_real_finish(self):
        self.install_runner("crash")
        report = self.invoke("execute", "media")
        blocker = report["blockers"][0]
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(len(blocker["fingerprint"]), 64)
        self.assertEqual(blocker["kind"], "executor_failure")
        self.assertEqual(len(blocker["evidence"][0]["log_sha256"]), 64)
        self.assertEqual(self.state()["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertIn("controlled crash evidence", (self.report.parent / "runner.log").read_text())

    def test_stale_lease_cannot_publish_candidate_or_change_task_state(self):
        self.install_runner("mutation")
        before = self.product_refs()
        store = runtime.GitStateStore(repository=self.workspace, initial_backoff=0)
        original_transact = store.transact
        revoked = {}

        def transact_with_revocation(mutator, *, message):
            if message == "autonomy: fence candidate publication":
                def reducer(snapshot):
                    state = snapshot.read_json(runtime.STATE)
                    state["tasks"][MEDIA]["status"] = "REVOKED"
                    state["tasks"][MEDIA]["fence"] += 1
                    state["tasks"][MEDIA]["lease"] = None
                    revoked["state"] = state
                    return runtime.Mutation(runtime.state_write(state))
                original_transact(reducer)
            return original_transact(mutator, message=message)

        with patch.object(runtime, "store_for", return_value=store), \
             patch.object(store, "transact", side_effect=transact_with_revocation), \
             patch.object(runtime, "persist_candidate", wraps=runtime.persist_candidate) as publish:
            report = self.invoke("execute", "media")
        publish.assert_not_called()
        self.assertTrue(report["fenced"])
        self.assertEqual(self.state(), revoked["state"])
        self.assertEqual(self.product_refs(), before)
        self.assertEqual(self.git("--git-dir", str(self.remote), "for-each-ref", "--format=%(refname)",
                                 "refs/heads/autonomy/"), "")
        evidence_paths = self.git("--git-dir", str(self.remote), "ls-tree", "-r", "--name-only",
                                  "autopilot-state", "data/autopilot/evidence").splitlines()
        evidence = [json.loads(self.remote_show("autopilot-state", path)) for path in evidence_paths]
        self.assertEqual({row["kind"] for row in evidence}, {"pickup", "fenced_worker_result"})

    def test_candidate_publication_stages_only_validated_files(self):
        (self.workspace / "src/product.py").write_text("def value():\n    return 2\n")
        (self.workspace / "web/data/free_value.json").write_text('{"unrelated": true}\n')
        (self.workspace / "untracked.secret").write_text("never publish\n")
        before = self.product_refs()
        report = runtime.persist_candidate(self.workspace, "media", "isolated",
                                           self.candidate_report(["src/product.py"]))
        self.assertEqual(self.product_refs(), before)
        changed = self.git("--git-dir", str(self.remote), "diff-tree", "--no-commit-id", "--name-only",
                           "-r", report["candidate_commit"]).splitlines()
        self.assertEqual(changed, ["src/product.py"])
        self.assertEqual(self.remote_show(report["candidate_branch"], "web/data/free_value.json"),
                         '{"original": true}')

    def test_candidate_rejects_existing_index_directory_symlink_and_critical_paths(self):
        (self.workspace / "src/product.py").write_text("def value():\n    return 2\n")
        self.git("add", "--", "src/product.py", cwd=self.workspace)
        with self.assertRaisesRegex(RuntimeError, "index"):
            runtime.persist_candidate(self.workspace, "media", "index",
                                      self.candidate_report(["src/product.py"]))
        self.git("reset", "--quiet", cwd=self.workspace)
        paths = ["src", "../outside.py", "/tmp/outside.py", ".github/workflows/production.yml",
                 "tests/test_product.py", "config/auth.json", "scripts/autonomy_lane_runner.py",
                 "src/radar_salud/editorial_gate.py", "src/radar_salud/ai_budget.py"]
        for path in paths:
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                runtime.persist_candidate(self.workspace, "media", "boundary", self.candidate_report([path]))
        source = self.workspace / "src/product.py"
        source.unlink()
        outside = self.root / "outside.py"
        outside.write_text("def value():\n    return 2\n")
        source.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            runtime.persist_candidate(self.workspace, "media", "symlink",
                                      self.candidate_report(["src/product.py"]))

    def test_product_protected_branches_are_rejected_before_any_staging(self):
        self.git("checkout", "--quiet", "main", cwd=self.workspace)
        (self.workspace / "src/product.py").write_text("def value():\n    return 2\n")
        for branch in ("main", "production-stable"):
            if branch != "main":
                self.git("checkout", "--quiet", "-b", branch, cwd=self.workspace)
            with self.subTest(branch=branch), self.assertRaisesRegex(RuntimeError, "main"):
                runtime.persist_candidate(self.workspace, "media", "production",
                                          self.candidate_report(["src/product.py"]))
            self.assertEqual(self.git("diff", "--cached", "--name-only", cwd=self.workspace), "")
            self.assertEqual(self.product_refs(), {"main": self.product_sha, "staging": self.product_sha})

    def test_declared_validation_without_actual_evidenced_pass_cannot_publish(self):
        (self.workspace / "src/product.py").write_text("def value():\n    return 2\n")
        before = self.product_refs()
        for gates in (None, [], [{"status": "PASS", "returncode": 0}],
                      [{"status": "SKIP", "returncode": 0, "command": ["fixture"],
                        "log_path": "not-an-actual-log", "log_sha256": "a" * 64}]):
            report = {"validated": True, "family": "media", "changed_paths": ["src/product.py"]}
            if gates is not None:
                report["gates"] = gates
            with self.subTest(gates=gates):
                result = runtime.persist_candidate(self.workspace, "media", "unevidenced", report)
                self.assertEqual(result["changed_paths"], [])
                self.assertEqual(result["rejected_candidate_paths"], ["src/product.py"])
                self.assertNotIn("candidate_commit", result)
                self.assertEqual(self.git("diff", "--cached", "--name-only", cwd=self.workspace), "")
        self.assertEqual(self.product_refs(), before)
        self.assertEqual(self.git("--git-dir", str(self.remote), "for-each-ref", "--format=%(refname)",
                                 "refs/heads/autonomy/"), "")

    def test_partial_candidate_survives_unrelated_baseline_failure_only_on_isolated_branch(self):
        source = self.workspace / "src/product.py"
        before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        before_refs = self.product_refs()
        full_command = [sys.executable, "-c", "assert False, 'unrelated existing normative gate'" ]
        baseline = self.evidenced_gate(full_command, "baseline-full")
        self.assertNotEqual(baseline["returncode"], 0)

        store = runtime.GitStateStore(repository=self.workspace, initial_backoff=0)
        queue = runtime.queue_for(self.workspace)
        def acquire(snapshot):
            state, lease = runtime.engine.claim(snapshot.read_json(runtime.STATE, {}), queue,
                                                 "media", "partial-worker", runtime.now())
            return runtime.Mutation(runtime.state_write(state), lease)
        lease = store.transact(acquire).value

        source.write_text("def value():\n    return 2\n")
        candidate = self.evidenced_gate(full_command, "candidate-full")
        directed = self.candidate_report(["src/product.py"])["gates"][0]
        self.assertEqual(baseline["log_sha256"], candidate["log_sha256"])
        failure_identity = baseline["log_sha256"]

        # The contract needs a distinct actual probe with a hashed command log.
        # A file endpoint makes this integration deterministic in sandboxes
        # that cannot open sockets; it proves no external source LIVE verdict.
        source_fixture = self.root / "source-endpoint.json"
        source_fixture.write_text('{"source_fixture": true, "event_date": "2026-10-11"}')
        live = self.evidenced_gate([sys.executable, "-c",
            "import json, urllib.request; response = urllib.request.urlopen(" + repr(source_fixture.as_uri()) +
            ", timeout=3); row = json.load(response); assert row['source_fixture'] and row['event_date']; print(json.dumps(row))"],
            "fixture-live-probe")
        self.assertEqual(live["status"], "PASS")
        report = {
            "task_id": MEDIA, "family": "media", "status": "BLOCKED", "validated": False,
            "changed_paths": ["src/product.py"], "before_hash": before_hash,
            "after_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
            "partial_candidate": True, "targeted_validated": True, "no_new_failures": True,
            "candidate_scope": "isolated", "directed_gates": [directed],
            "live_validated": True, "live_gate": live, "gates": [candidate],
            "non_regression": {"baseline_failures": [failure_identity],
                "candidate_failures": [failure_identity], "baseline_gate": baseline, "candidate_gate": candidate},
            "blockers": [{"fingerprint": failure_identity,
                "reason": "Unrelated normative gate fails identically before and after this bounded repair",
                "evidence": [baseline, candidate]}],
        }
        durable = runtime.persist_candidate(self.workspace, "media", "partial-worker", report)
        self.assertEqual(durable["candidate_scope"], "isolated")
        self.assertFalse(durable["validated"])
        self.assertEqual(self.product_refs(), before_refs)
        self.assertEqual(self.remote_show(durable["candidate_branch"], "src/product.py"),
                         "def value():\n    return 2")

        def complete(snapshot):
            state = runtime.engine.finish(snapshot.read_json(runtime.STATE), MEDIA, lease["token"],
                                           durable, runtime.now())
            return runtime.Mutation(runtime.state_write(state))
        store.transact(complete)
        state = self.state()
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertEqual([event["kind"] for event in state["material_events"]], ["mutation", "blocker"])
        self.assertEqual(state["material_events"][0]["details"]["candidate_commit"], durable["candidate_commit"])
        self.assertEqual(state["tasks"][MEDIA]["blocker"]["blockers"][0]["fingerprint"], failure_identity)
        self.assertEqual(self.product_refs(), before_refs)


if __name__ == "__main__":
    unittest.main()
