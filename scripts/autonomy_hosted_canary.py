"""One bounded hosted heartbeat fault injection, isolated from useful work.

The CLI has no clock override and writes only from validated repository Actions.
Two real observations exercise the existing CAS store and fenced engine: pickup,
then STALLED/reclaim/old-token rejection after a deliberately omitted heartbeat.
This is infrastructure fault-injection evidence, never source LIVE evidence or
four-hour useful-progress evidence. Unit reducer clocks are not hosted proof.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

try:
    from . import autonomy_engine as engine
    from .autonomy_state_store import GitStateStore, Mutation
except ImportError:
    import autonomy_engine as engine
    from autonomy_state_store import GitStateStore, Mutation


REPOSITORY = "cftorre1/Radar-salud"
VERSION = "lease-heartbeat-v1"
PARENT_TASK = "autonomy_architecture_redesign_2026_10_07"
LABELS = {"hosted_canary": True, "fault_injection": True,
          "live_acceptance_evidence": False, "source_live_evidence": False,
          "counts_as_material_progress": False}


class CanaryError(ValueError):
    """The isolated canary cannot establish its bounded hosted authority."""


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def digest(value):
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def identifiers(version):
    # Root wires a fixed version, never a run-dependent namespace. Explicit new
    # versions require a new architecture checkpoint rather than repeated runs.
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", version):
        raise CanaryError("Canary version must be a bounded canonical identifier")
    stem = "hosted_canary_" + version
    return {"state": "data/autopilot/control_canary_" + version + ".json",
            "task": stem, "pickup": "data/autopilot/evidence/" + stem + "_pickup.json",
            "result": "data/autopilot/evidence/" + stem + "_result.json",
            "log": "data/autopilot/evidence/" + stem + "_proof.log",
            "manifest": "data/autopilot/evidence/" + stem + "_manifest.json"}


def hosted_context(infrastructure):
    """Validate hosted identity before creating a store or accessing its remote."""
    run_id = os.getenv("GITHUB_RUN_ID", "")
    attempt = os.getenv("GITHUB_RUN_ATTEMPT", "")
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("GITHUB_REPOSITORY") != REPOSITORY
            or not re.fullmatch(r"[1-9][0-9]*", run_id)
            or not re.fullmatch(r"[1-9][0-9]*", attempt)):
        raise CanaryError("Canary remote writes require this repository's numeric hosted Actions identity")
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=infrastructure,
                              text=True, capture_output=True, timeout=15, check=False)
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=infrastructure,
                                text=True, capture_output=True, timeout=15, check=False)
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=infrastructure,
                                text=True, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CanaryError("Canary infrastructure checkout could not be verified") from error
    sha = head.stdout.strip()
    if head.returncode or not re.fullmatch(r"[a-f0-9]{40}", sha) or branch.returncode or branch.stdout.strip() != "main":
        raise CanaryError("Canary requires a pinned main infrastructure checkout")
    origin = remote.stdout.strip()
    if origin.startswith("git@github.com:"):
        repository = origin.removeprefix("git@github.com:").removesuffix(".git")
    else:
        parsed = urlsplit(origin)
        repository = (parsed.path.strip("/").removesuffix(".git")
                      if parsed.scheme == "https" and parsed.hostname == "github.com"
                      and not parsed.query and not parsed.fragment else None)
    if remote.returncode or repository != REPOSITORY:
        raise CanaryError("Canary state origin must be the authorized repository")
    return {"repository": REPOSITORY, "run_id": int(run_id), "run_attempt": int(attempt),
            "run_url": "https://github.com/" + REPOSITORY + "/actions/runs/" + run_id,
            "infrastructure_sha": sha, "execution_environment": "github_actions"}


def queue_for(ids, pinned_sha, version):
    return {"input_sha": pinned_sha, "tasks": [{**LABELS, "id": ids["task"],
        "parent_task_id": PARENT_TASK, "status": "approved", "priority": "low",
        # A generic editorial family exercises the engine without claiming
        # source implementation. This isolated control is never read by lanes.
        "executor_family": "editorial", "depends_on": [], "blocked_by": [],
        "authorization": "Owner-authorized infrastructure fault injection; no product acceptance",
        "input_sha": pinned_sha, "input_fingerprint": digest(version),
        "evidence_revision": version, "objective": "Bounded infrastructure heartbeat fault injection"}]}


def marked_control(control):
    control.update(LABELS)
    control["acceptance"]["mode"] = "hosted_fault_injection"
    # The canary must not supply useful material events even within its own
    # namespace. Task closure is retained, but engine closure credit is removed.
    control["material_events"] = []
    control["pending_transitions"] = []
    for task in control.get("tasks", {}).values():
        task.update(LABELS)
        if task.get("lease"):
            task["lease"].update(LABELS)
    for event in control.get("lease_events", []):
        event.update(LABELS)
    return control


def evidence_document(snapshot, path, sha256):
    raw = snapshot.read(path)
    if not isinstance(raw, bytes) or digest(raw) != sha256:
        raise CanaryError("Canary immutable evidence is missing or changed")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise CanaryError("Canary immutable evidence is invalid") from error
    if not isinstance(value, dict) or any(value.get(key) != expected for key, expected in LABELS.items()):
        raise CanaryError("Canary evidence lacks its fault-injection boundary")
    return value


def _advance(snapshot, *, version, context, observed_at):
    """Pure CAS reducer; injected unit timestamps here are not hosted evidence."""
    ids = identifiers(version)
    at = engine._time(observed_at)
    observed = engine._iso(at)
    state = snapshot.read_json(ids["state"])
    if state is not None:
        if (not isinstance(state, dict) or state.get("version") != version
                or state.get("task_id") != ids["task"] or state.get("parent_task_id") != PARENT_TASK
                or any(state.get(key) != value for key, value in LABELS.items())
                or not re.fullmatch(r"[a-f0-9]{40}", str(state.get("pinned_infrastructure_sha", "")))):
            raise CanaryError("Existing canary authority is invalid; it cannot be reset")
        pickup = evidence_document(snapshot, ids["pickup"], state.get("pickup_evidence_sha256"))
        if (pickup.get("task_id") != ids["task"] or pickup.get("version") != version
                or pickup.get("observed_at") != state.get("started_at")
                or pickup.get("context") != state.get("pickup_context")
                or pickup["context"].get("execution_environment") != context.get("execution_environment")):
            raise CanaryError("Canary pickup evidence is not bound to this episode/environment")
        if state.get("status") in {"PASS", "BLOCKED"}:
            result = evidence_document(snapshot, ids["result"], state.get("result_evidence_sha256"))
            if (result.get("task_id") != ids["task"] or result.get("version") != version
                    or result.get("status") != state["status"]
                    or result.get("manifest_path") != ids["manifest"] or result.get("log_path") != ids["log"]):
                raise CanaryError("Canary terminal evidence is not bound to this result")
            evidence_document(snapshot, ids["manifest"], result.get("manifest_sha256"))
            raw_log = snapshot.read(ids["log"])
            if not isinstance(raw_log, bytes) or digest(raw_log) != result.get("log_sha256"):
                raise CanaryError("Canary terminal execution log is missing or changed")
            return Mutation({}, deepcopy(state))
        if state.get("status") != "WAITING_HEARTBEAT":
            raise CanaryError("Existing canary episode has an unknown phase")
        started = engine._time(state["started_at"])
        if at < started:
            raise CanaryError("Canary observation time moved backwards")
        if (at - started).total_seconds() < engine.HEARTBEAT_GRACE_SECONDS:
            return Mutation({}, deepcopy(state))
    else:
        control = {"acceptance": {"mode": "hosted_fault_injection", "started_at": observed,
                                  "owner_restarts": [], "owner_prompts": []}}
        owner = "canary-" + str(context["run_id"]) + "-" + str(context["run_attempt"])
        control, lease = engine.claim(control, queue_for(ids, context["infrastructure_sha"], version),
                                      "editorial", owner, at)
        if not lease:
            raise CanaryError("Canary initial isolated lease was not acquired")
        state = {**LABELS, "version": version, "task_id": ids["task"], "parent_task_id": PARENT_TASK,
                 "status": "WAITING_HEARTBEAT", "started_at": observed,
                 "pinned_infrastructure_sha": context["infrastructure_sha"],
                 "pickup_context": deepcopy(context), "pickup_state_parent_sha": snapshot.commit,
                 "original_token": lease["token"], "original_fence": lease["fence"],
                 "fault": "heartbeat_deliberately_omitted", "heartbeat_grace_seconds": engine.HEARTBEAT_GRACE_SECONDS,
                 "engine_state": marked_control(control), "pickup_evidence_path": ids["pickup"]}
        pickup = {**LABELS, "kind": "hosted_canary_pickup", "observed_at": observed,
                  "version": version, "task_id": ids["task"], "parent_task_id": PARENT_TASK,
                  "state_parent_sha": snapshot.commit, "context": deepcopy(context),
                  "lease": {**deepcopy(lease), **LABELS}, "fault": state["fault"],
                  "source_live_claimed": False, "next_hypothesis": "A later real observation detects STALLED and rejects the old token"}
        state["pickup_evidence_sha256"] = digest(encode(pickup))
        return Mutation({ids["state"]: encode(state), ids["pickup"]: encode(pickup)}, deepcopy(state))

    queue = queue_for(ids, state["pinned_infrastructure_sha"], version)
    control = engine.reconcile(state["engine_state"], queue, at)
    stalled = control["tasks"][ids["task"]]
    checks = {"real_heartbeat_grace_elapsed": True,
              "stalled_detected": stalled["status"] == "STALLED",
              "stall_fenced_original_token": stalled.get("fence", 0) > state["original_fence"]}
    reason = stalled.get("reason")
    new_lease = None
    if checks["stalled_detected"]:
        control, new_lease = engine.claim(control, queue, "editorial",
            "canary-recovery-" + str(context["run_id"]) + "-" + str(context["run_attempt"]), at)
    checks["reclaimed_with_new_generation"] = bool(new_lease and
        new_lease["fence"] > state["original_fence"] and new_lease["token"] != state["original_token"])
    before_rejection = encode(control)
    try:
        engine.finish(control, ids["task"], state["original_token"], {"status": "SUCCESS"}, at)
        checks["old_token_finish_rejected"] = False
    except engine.LeaseError:
        checks["old_token_finish_rejected"] = True
    checks["old_worker_did_not_mutate_state"] = encode(control) == before_rejection
    log = encode({**LABELS, "observed_at": observed, "context": context,
                  "task_id": ids["task"], "pinned_infrastructure_sha": state["pinned_infrastructure_sha"],
                  "elapsed_real_seconds": (at - engine._time(state["started_at"])).total_seconds(),
                  "stall_reason": reason, "checks": checks,
                  "proof_calls": ["autonomy_engine.reconcile", "autonomy_engine.claim",
                                  "autonomy_engine.finish(original_token) -> LeaseError"]})
    manifest = {**LABELS, "task_id": ids["task"], "verdict": "PASS" if all(checks.values()) else "BLOCKED",
                "verified": all(checks.values()), "candidate_sha": state["pinned_infrastructure_sha"],
                "checks": checks, "evidence": [{"path": ids["log"], "sha256": digest(log)}]}
    manifest_raw = encode(manifest)
    if all(checks.values()):
        report = {**LABELS, "status": "PASS", "validated": True,
                  "gates": [{"command": "autonomy_hosted_canary._advance: actual engine calls",
                             "returncode": 0, "status": "PASS", "log_path": ids["log"], "log_sha256": digest(log)}],
                  "acceptance_proof": [{**manifest, "path": ids["manifest"], "sha256": digest(manifest_raw)}]}
        control = engine.finish(control, ids["task"], new_lease["token"], report, at)
    else:
        # Terminal after this bounded episode. No repeat injection, retries or
        # use of the main task/lease namespace when the control fails its test.
        control["tasks"][ids["task"]].update(status="BLOCKED", lease=None,
            reason="hosted_infrastructure_canary_failed")
    result = {**LABELS, "kind": "hosted_canary_result", "version": version,
              "task_id": ids["task"], "parent_task_id": PARENT_TASK,
              "observed_at": observed, "started_at": state["started_at"], "context": deepcopy(context),
              "state_parent_sha": snapshot.commit, "pinned_infrastructure_sha": state["pinned_infrastructure_sha"],
              "status": manifest["verdict"], "checks": checks, "stall_reason": reason,
              "log_path": ids["log"], "log_sha256": digest(log),
              "manifest_path": ids["manifest"], "manifest_sha256": digest(manifest_raw),
              "live_acceptance": "NOT_APPLICABLE", "next_hypothesis": "Verify organic independent workers and useful progress separately"}
    state.update(status=result["status"], observed_until=observed, checks=checks, stall_reason=reason,
                 result_evidence_path=ids["result"], result_evidence_sha256=digest(encode(result)),
                 engine_state=marked_control(control))
    return Mutation({ids["state"]: encode(state), ids["result"]: encode(result),
                     ids["log"]: log, ids["manifest"]: manifest_raw}, deepcopy(state))


def observe_canary(infrastructure, report_path, *, version=VERSION, store=None):
    infrastructure = Path(infrastructure).resolve()
    report_path = Path(report_path).resolve()
    ids = identifiers(version)
    context = hosted_context(infrastructure)
    authority = store or GitStateStore(repository=infrastructure)
    snapshot = authority.read_snapshot()
    observed_at = datetime.now(timezone.utc)
    # Validate the fixed episode, and avoid even a transaction for waiting or
    # terminal calls. A CAS replay rechecks the same conditions if another call
    # wins before this write.
    preview = _advance(snapshot, version=version, context=context, observed_at=observed_at)
    if preview.writes:
        transaction = authority.transact(lambda fresh: _advance(fresh, version=version,
            context=context, observed_at=datetime.now(timezone.utc)), message="autonomy: bounded hosted heartbeat canary")
        state, commit, changed = transaction.value, transaction.commit, transaction.changed
    else:
        state, commit, changed = preview.value, snapshot.commit, False
    report = {**LABELS, "version": version, "status": state["status"], "state_path": ids["state"],
              "state_commit": commit, "remote_changed": changed, "started_at": state["started_at"],
              "observed_until": state.get("observed_until"), "checks": state.get("checks", {}),
              "stall_reason": state.get("stall_reason"), "live_acceptance": "NOT_APPLICABLE"}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(encode(report), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--infrastructure", required=True)
    parser.add_argument("--report", default="artifacts/hosted-canary.json")
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()
    try:
        report = observe_canary(args.infrastructure, args.report, version=args.version)
    except CanaryError as error:
        parser.exit(2, str(error) + "\n")
    print(encode(report))
    return 1 if report["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
