"""GitHub-native orchestration. Infrastructure runs from main; work stays isolated."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone

from autonomy_state_store import GitStateStore, Mutation
import autonomy_engine as engine
from autonomy_candidate_context import CandidateContextError, overlay_queue, prepare_workspace

STATE = "data/autopilot/control_v2.json"
FAMILY_INPUTS = {
    "media": ["src/radar_salud/source_scouts.py", "src/radar_salud/beta_sources_fast.py", "src/radar_salud/press_pipeline.py"],
    "public_data": ["src/radar_salud/source_scouts.py", "src/radar_salud/public_source_pipeline.py"],
    "fiscalization": ["src/radar_salud/source_scouts.py", "src/radar_salud/superintendencia_fiscalizacion.py"],
    "mutualities": ["src/radar_salud/beta_sources_fast.py", "src/radar_salud/beta_sources.py"],
    "editorial": ["src/radar_salud/weekly_freshness.py", "data/weekly_insight/editorial_approved.json", "config/editorial_copy_overrides_v1.json", "src/radar_salud/free_value.py"],
    "staging_qa": ["src", "tests", "app.js", "index.html", "package.json", "package-lock.json", ".github/workflows/qa.yml"],
}


class CandidateNeedsRevalidation(RuntimeError):
    """Recorded candidate must retain its ref and scoped-base blocker."""


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def command(args, cwd, check=True):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=check)


def queue_for(workspace, failure_path=None):
    queue = json.loads((workspace / "config/orchestrator_queue.json").read_text())
    sha = command(["git", "rev-parse", "HEAD"], workspace).stdout.strip()
    queue["input_sha"] = sha
    for task in queue.get("tasks", []):
        task["input_sha"] = sha
    editorial = next((task for task in queue["tasks"] if task["id"] == "source_audit_issue5_iteration3_editorial_2026_10_09"
                      and task.get("status") in {"approved", "in_progress"} and not task.get("blocked_by")), None)
    if editorial:
        # User-authorized independent repair subfront; parent acceptance is preserved.
        queue["tasks"].append({**editorial, "id": "editorial_repair_lane_2026_10_11", "depends_on": [],
                               "parent_task_id": editorial["id"], "source": "Autonomy Architect independent editorial repair lane",
                               "objective": "Repair existing reviewed editorial artifacts; retain independent parent acceptance."})
    if failure_path:
        failure = json.loads(Path(failure_path).read_text())
        if failure.get("conclusion") in {"failure", "timed_out"}:
            queue["tasks"].append({
                "id": "staging_qa_failed_run_" + str(failure["run_id"]),
                "status": "approved", "priority": "critical", "depends_on": [],
                "family": "staging_qa", "input_sha": sha, "failure": failure,
                "objective": "Recover the demonstrated staging gate; preserve product contracts.",
            })
    for task in queue["tasks"]:
        family = engine._family(task)
        if family in FAMILY_INPUTS:
            inputs = FAMILY_INPUTS[family] + ["src/radar_salud/scouts.py", "src/radar_salud/models.py", "config/sources.json", "config/beta_source_configs.json"]
            tree = command(["git", "ls-tree", "-r", "HEAD", "--", *inputs], workspace).stdout
            task["input_fingerprint"] = hashlib.sha256(tree.encode()).hexdigest()
    return queue


def state_write(state, evidence=None):
    writes = {STATE: encode(state)}
    if evidence:
        # Unique operation id, retained across CAS retries. No mutable latest evidence.
        writes["data/autopilot/evidence/" + evidence["operation_id"] + ".json"] = encode(evidence)
    return writes


def store_for(args):
    return GitStateStore(repository=args.infrastructure)


def initial_state(snapshot):
    """Start live acceptance only from this repository's hosted Actions run.

    Local initialization is a simulation. A later hosted activation starts a
    fresh real-time window, retaining the ledger while excluding its earlier
    fixture events by the acceptance window's start. Reading existing live
    authority locally never downgrades or restarts that window.
    """
    state = snapshot.read_json(STATE, {})
    hosted = (os.getenv("GITHUB_ACTIONS") == "true"
              and os.getenv("GITHUB_REPOSITORY") == "cftorre1/Radar-salud"
              and os.getenv("GITHUB_RUN_ID", "").isdigit()
              and os.getenv("GITHUB_RUN_ATTEMPT", "").isdigit())
    acceptance = state.get("acceptance")
    if acceptance and acceptance.get("mode") == "live":
        return state
    if not acceptance or (hosted and acceptance.get("mode") == "simulation"):
        state["acceptance"] = {"mode": "live" if hosted else "simulation", "started_at": now(),
                               "owner_restarts": [], "owner_prompts": []}
    return state


def integrated_candidates(workspace, queue, state):
    """Prove exact recorded candidates already belong to pinned staging HEAD.

    This reads only local Git objects. Missing history or a non-ancestor gives
    no integration proof; it never fetches, checks out, merges or promotes.
    """
    staging = queue.get("input_sha")
    if not isinstance(staging, str) or not re.fullmatch(r"[a-fA-F0-9]{40}", staging):
        raise CandidateContextError("Current staging authority requires a full commit SHA")
    if command(["git", "rev-parse", "HEAD"], workspace).stdout.strip() != staging:
        raise CandidateContextError("Staging checkout moved before candidate continuation")
    approved = {task["id"] for task in queue.get("tasks", []) if task.get("status") in engine.APPROVED}
    seen = set()
    integrated = set()
    for event in reversed(state.get("material_events", [])):
        task_id = event.get("task_id")
        if event.get("kind") != "mutation" or task_id not in approved or task_id in seen:
            continue
        seen.add(task_id)
        details = event.get("details", {})
        commit = details.get("candidate_commit")
        if (details.get("candidate_scope") != "isolated" or not isinstance(commit, str)
                or not re.fullmatch(r"[a-fA-F0-9]{40}", commit)):
            continue
        try:
            ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", commit, staging],
                                     cwd=workspace, text=True, capture_output=True, check=False, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if ancestry.returncode == 0:
            integrated.add(commit)
    return integrated


def plan(args):
    workspace = Path(args.workspace).resolve()
    queue = queue_for(workspace, args.failure_json)
    at = now()
    operation = uuid.uuid4().hex
    def reduce(snapshot):
        previous = initial_state(snapshot)
        effective_queue = overlay_queue(queue, previous,
            integrated_candidate_commits=integrated_candidates(workspace, queue, previous))
        state, selected = engine.plan(previous, effective_queue, at)
        reviews = {}
        for event in state.get("material_events", []):
            if event.get("kind") != "mutation":
                continue
            details = event["details"]
            task_state = state["tasks"].get(event["task_id"], {})
            if details.get("candidate_scope") != "isolated" or not details.get("candidate_branch"):
                continue
            reviewed = task_state.get("candidate_reviews", {}).get(details["candidate_commit"])
            if reviewed:
                continue
            reviews[event["task_id"]] = {"task_id": event["task_id"], "family": event["family"],
                                         "candidate_commit": details["candidate_commit"], "candidate_branch": details["candidate_branch"]}
        report = {"generated_at": at, "input_sha": queue["input_sha"],
                  "families": selected, "acceptance": engine.evaluate_acceptance(state, at),
                  "stalled_tasks": [{"task_id": task["id"], "family": task.get("family"),
                                     "reason": task.get("reason"), "recovery_reclaims": task.get("recovery_reclaims", 0)}
                                    for task in state["tasks"].values() if task["status"] == "STALLED"],
                  "candidate_reviews": list(reviews.values()),
                  "operation_id": operation, "kind": "controller_observation"}
        return Mutation(state_write(state, report), report)
    result = store_for(args).transact(reduce, message="autonomy: reconcile lanes and stalls")
    report = result.value
    matrix = {"include": [{"family": f, "task_id": t["task_id"]}
                           for f, t in report["families"].items()
                           if not args.family or f == args.family]}
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(encode(report))
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write("matrix=" + json.dumps(matrix, separators=(",", ":")) + "\n")
            output.write("has_work=" + ("true" if matrix["include"] else "false") + "\n")
            output.write("review_matrix=" + json.dumps({"include": report["candidate_reviews"]}, separators=(",", ":")) + "\n")
            output.write("has_reviews=" + ("true" if report["candidate_reviews"] else "false") + "\n")
    print(encode({"matrix": matrix, "state_commit": result.commit,
                  "acceptance": report["acceptance"]}))


def persist_candidate(workspace, family, owner, report):
    paths = report.get("changed_paths") or []
    if not paths:
        return report
    if not engine.candidate_validated(report):
        # Preserve actual gate evidence; failed candidates are never published.
        return {**report, "changed_paths": [], "rejected_candidate_paths": paths}
    if command(["git", "diff", "--cached", "--name-only"], workspace).stdout.strip():
        raise RuntimeError("Candidate index must be empty before explicit staging")
    # The runner cannot stage evidence, workflow, generated state or test relaxations.
    for path in paths:
        p = Path(path)
        if p.is_absolute() or ".." in p.parts or (p.parts[0] not in {"src", "config", "scripts", "web", "data"} and path not in {"app.js", "index.html"}):
            raise RuntimeError("Candidate path outside staging work scope")
        if p.parts[0] == "scripts" and p.name.startswith("autonomy_"):
            raise RuntimeError("Worker cannot replace its own controls")
        if p.name in {"ai_budget.py", "editorial_gate.py", "quality.py", "scoring.py", "validation.py",
                      "source_quality_gate.json", "editorial_rules_v2.json", "media_early_signal_gate.json"}:
            raise RuntimeError("Candidate cannot weaken validation or budget controls")
        if any(x in path.lower() for x in ("secret", "privacy", "pricing", "auth", "autopilot", "orchestrator_queue", "ai_usage")):
            raise RuntimeError("Candidate path crosses policy boundary")
        target = workspace / p
        if not target.is_file() or any(parent.is_symlink() for parent in (target, *target.parents)):
            raise RuntimeError("Candidate paths must be regular files without symlinks")
        command(["git", "ls-files", "--error-unmatch", "--", path], workspace)
    current_branch = command(["git", "branch", "--show-current"], workspace).stdout.strip()
    if current_branch in {"main", "master", "prod", "production", "production-stable"}:
        raise RuntimeError("Product writes to main are forbidden")
    branch = "autonomy/" + family + "/" + re.sub(r"[^A-Za-z0-9_-]", "_", owner)
    command(["git", "config", "user.name", "alicanto-autonomy"], workspace)
    command(["git", "config", "user.email", "alicanto-autonomy@users.noreply.github.com"], workspace)
    command(["git", "add", "--", *paths], workspace)
    staged = command(["git", "diff", "--cached", "--name-only"], workspace).stdout.splitlines()
    if set(staged) != set(paths):
        raise RuntimeError("Staged candidate paths differ from the validated files")
    command(["git", "diff", "--cached", "--check"], workspace)
    if not command(["git", "diff", "--cached", "--quiet"], workspace, check=False).returncode:
        raise RuntimeError("Reported mutation has no staged changes")
    command(["git", "commit", "-m", "autonomy: bounded " + family + " repair candidate"], workspace)
    commit = command(["git", "rev-parse", "HEAD"], workspace).stdout.strip()
    # Unique branch and normal push: no overwrite, no production promotion.
    command(["git", "push", "origin", "HEAD:refs/heads/" + branch], workspace)
    return {**report, "candidate_commit": commit, "candidate_branch": branch, "candidate_scope": "isolated",
            "candidate_url": "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "cftorre1/Radar-salud") + "/commit/" + commit}


def execute(args):
    workspace = Path(args.workspace).resolve()
    queue = queue_for(workspace, args.failure_json)
    store = store_for(args)
    owner = os.environ.get("GITHUB_RUN_ID", "local") + "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "1") + "-" + args.family
    operation = uuid.uuid4().hex
    def acquire(snapshot):
        previous = initial_state(snapshot)
        effective_queue = overlay_queue(queue, previous,
            integrated_candidate_commits=integrated_candidates(workspace, queue, previous))
        state, lease = engine.claim(previous, effective_queue, args.family, owner, now())
        writes = state_write(state, {"operation_id": operation, "kind": "pickup", "lease": lease, "at": now()}) if lease else state_write(state)
        if lease:
            lease = {**lease, "_queue_task": next(t for t in effective_queue["tasks"] if t["id"] == lease["task_id"])}
        return Mutation(writes, lease)
    result = store.transact(acquire, message="autonomy: atomically lease " + args.family)
    lease = result.value
    if not lease:
        print(encode({"family": args.family, "status": "NO_EXECUTABLE_TASK"}))
        return
    task = lease.pop("_queue_task")
    task = {**task, **lease, "pickup_commit": result.commit}
    artifacts = Path(args.report).resolve().parent
    artifacts.mkdir(parents=True, exist_ok=True)
    task_path = artifacts / "task.json"
    if args.family == "staging_qa" and task.get("failure"):
        log = command(["gh", "run", "view", str(task["failure"]["run_id"]), "--repo",
                       os.environ.get("GITHUB_REPOSITORY", "cftorre1/Radar-salud"), "--log-failed"], workspace, check=False)
        if log.returncode == 0 and log.stdout:
            failure_log = workspace / "artifacts/autonomy/demonstrated-failure.log"
            failure_log.parent.mkdir(parents=True, exist_ok=True)
            failure_log.write_text(log.stdout)
            task["failure_log_path"] = str(failure_log)
        else:
            task["failure_log_unavailable"] = True
    task_path.write_text(encode(task))
    stop = threading.Event()
    lost = []
    process = None
    def renew():
        while not stop.wait(60):
            try:
                def reducer(snapshot):
                    state = engine.heartbeat(snapshot.read_json(STATE, {}), lease["task_id"], lease["token"], now())
                    return Mutation(state_write(state))
                store.transact(reducer, message="autonomy: renew " + args.family + " lease")
            except Exception as error:
                lost.append(type(error).__name__)
                if process is not None:
                    process.terminate()
                return
    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        if task.get("candidate_context"):
            context = prepare_workspace(workspace, task)
            if not context["prepared"]:
                report = {"task_id": lease["task_id"], "family": args.family, "status": "BLOCKED",
                          "changed_paths": [], "validated": False, "candidate_context": context,
                          "blockers": [context["blocker"]], "evidence": [context],
                          "semantic_hash": context["blocker"]["fingerprint"]}
                Path(args.report).write_text(encode(report))
                raise CandidateNeedsRevalidation(context)
        runner = Path(__file__).with_name("autonomy_lane_runner.py")
        argv = [sys.executable, str(runner), "--family", args.family, "--workspace", str(workspace),
                "--task-json", str(task_path), "--input-sha", lease["input_sha"], "--report", str(Path(args.report).resolve())]
        if args.allow_model:
            argv.append("--allow-llm")
        with (artifacts / "runner.log").open("w") as log:
            process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, cwd=workspace)
            process.wait(timeout=18 * 60)
        if lost:
            raise RuntimeError("Lease renewal failed; stale worker cannot publish")
        if not Path(args.report).exists():
            raise RuntimeError("Worker exited without durable report")
        report = json.loads(Path(args.report).read_text())
        # Revalidate lease immediately before external candidate mutation.
        store.transact(lambda snapshot: Mutation(state_write(engine.heartbeat(snapshot.read_json(STATE, {}), lease["task_id"], lease["token"], now()))), message="autonomy: fence candidate publication")
        report = persist_candidate(workspace, args.family, owner, report)
    except CandidateNeedsRevalidation:
        pass  # The exact scoped-base blocker already retains the candidate/ref.
    except Exception as error:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        failure_evidence = {"kind": "executor_failure", "error": type(error).__name__,
                            "reason": str(error)[:2000],
                            "log_sha256": hashlib.sha256((artifacts / "runner.log").read_bytes()).hexdigest() if (artifacts / "runner.log").exists() else None}
        stable_reason = re.sub(r"\b\d{4}-\d{2}-\d{2}T\S+|\bin \d+(?:\.\d+)?s", "<observation>", str(error)[:2000])
        fingerprint = hashlib.sha256((type(error).__name__ + stable_reason).encode()).hexdigest()
        report = {"task_id": lease["task_id"], "family": args.family, "status": "BLOCKED",
                  "validated": False, "changed_paths": [],
                  "blockers": [{"kind": "executor_failure", "reason": type(error).__name__ + ": " + str(error)[:2000],
                                "fingerprint": fingerprint, "evidence": [failure_evidence]}],
                  "evidence": [failure_evidence], "semantic_hash": fingerprint}
    finally:
        stop.set()
        thread.join(timeout=10)
    report["input_sha"] = lease["input_sha"]
    report["run_id"] = owner
    report["run_url"] = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "cftorre1/Radar-salud") + "/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "local")
    evidence = {"operation_id": uuid.uuid4().hex, "kind": "worker_result", "at": now(), "report": report}
    def complete(snapshot):
        state = engine.finish(snapshot.read_json(STATE, {}), lease["task_id"], lease["token"], report, now())
        return Mutation(state_write(state, evidence), engine.evaluate_acceptance(state, now()))
    try:
        completed = store.transact(complete, message="autonomy: evidence and next transition for " + args.family)
    except engine.LeaseError:
        # Keep the orphan's diagnostic evidence without changing the new owner's task.
        evidence["kind"] = "fenced_worker_result"
        evidence["fenced"] = True
        completed = store.transact(lambda snapshot: Mutation({
            "data/autopilot/evidence/" + evidence["operation_id"] + ".json": encode(evidence)
        }, {"status": "NOT_PROVEN", "reasons": ["worker_fenced_before_finish"]}),
            message="autonomy: retain fenced worker evidence")
        report["fenced"] = True
    report["state_commit"] = completed.commit
    report["acceptance"] = completed.value
    Path(args.report).write_text(encode(report))
    print(encode(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "execute"])
    parser.add_argument("--infrastructure", default=".")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--family", choices=["media", "public_data", "fiscalization", "mutualities", "editorial", "staging_qa"])
    parser.add_argument("--failure-json")
    parser.add_argument("--report", default="artifacts/autonomy_runtime.json")
    parser.add_argument("--allow-model", action="store_true")
    args = parser.parse_args()
    if args.action == "execute" and not args.family:
        parser.error("execute requires --family")
    (plan if args.action == "plan" else execute)(args)


if __name__ == "__main__":
    main()
