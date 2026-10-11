"""Publish truthful autonomy projections from pinned Git inputs and fresh CAS state.

Observation never reconciles approval, repairs product, closes a task or earns
material progress. Owner prompt events have no connected authoritative source.
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
import uuid

try:
    from . import autonomy_engine as engine
    from .autonomy_state_store import GitStateStore, Mutation
except ImportError:
    import autonomy_engine as engine
    from autonomy_state_store import GitStateStore, Mutation


STATE = "data/autopilot/control_v2.json"
QUEUE = "config/orchestrator_queue.json"
LEDGER = "data/autopilot/learning_ledger.json"
QUEUE_PROJECTION = "data/autopilot/queue_projection_v2.json"
PMO_EVIDENCE = "data/autopilot/pmo_evidence_v2.json"
SHA = re.compile(r"^[a-fA-F0-9]{40}$")
OPERATION = re.compile(r"^[a-f0-9]{32}$")
MAX_TASKS = 5000
RECENT_EVENTS = 256


class ObservationError(ValueError):
    """An observation lacks a verifiable Git input or supported ledger schema."""


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def git(workspace, *arguments):
    result = subprocess.run(["git", *arguments], cwd=workspace, capture_output=True, check=False, timeout=30)
    if result.returncode:
        # Neither remote URLs nor authentication diagnostics belong in public evidence.
        raise ObservationError("Pinned Git input unavailable: " + arguments[0])
    return result.stdout


def capture_authority(infrastructure, workspace):
    """Read approved inputs from exact Git blobs, rejecting dirty authority files."""
    infrastructure, workspace = Path(infrastructure).resolve(), Path(workspace).resolve()
    infra_sha = git(infrastructure, "rev-parse", "HEAD").decode().strip()
    staging_sha = git(workspace, "rev-parse", "HEAD").decode().strip()
    if not SHA.fullmatch(infra_sha) or not SHA.fullmatch(staging_sha):
        raise ObservationError("Infrastructure and staging authority require full commit SHAs")
    if git(workspace, "status", "--porcelain", "--untracked-files=no", "--", QUEUE, LEDGER):
        raise ObservationError("Queue and ledger authority must be clean tracked Git inputs")
    result = {"infra_sha": infra_sha, "staging_sha": staging_sha}
    for name, relative in (("queue", QUEUE), ("learning_ledger", LEDGER)):
        content = git(workspace, "show", staging_sha + ":" + relative)
        if len(content) > 8 * 1024 * 1024:
            raise ObservationError("Authority input exceeds the observation bound")
        blob = git(workspace, "rev-parse", staging_sha + ":" + relative).decode().strip()
        if not SHA.fullmatch(blob):
            raise ObservationError("Authority input requires an exact Git blob")
        try:
            value = json.loads(content)
        except (ValueError, UnicodeError) as error:
            raise ObservationError("Authority JSON is unreadable: " + relative) from error
        result.update({name: value, name + "_blob_sha": blob, name + "_sha256": digest(content)})
    if not isinstance(result["queue"], dict) or not isinstance(result["queue"].get("tasks"), list):
        raise ObservationError("Approved queue must contain a task list")
    if len(result["queue"]["tasks"]) > MAX_TASKS:
        raise ObservationError("Queue exceeds the bounded task projection")
    if not isinstance(result["learning_ledger"], list):
        raise ObservationError("Existing learning ledger must retain its list schema")
    if git(workspace, "rev-parse", "HEAD").decode().strip() != staging_sha:
        raise ObservationError("Staging checkout moved while authority was captured")
    return result


def _safe(value):
    """Retain evidence identities without exposing bearer lease tokens."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == "token" or key.endswith("_token"):
                result[key + "_sha256"] = digest(str(item)) if item is not None else None
            elif key == "tokens":
                result["tokens_sha256"] = [digest(str(token)) for token in item] if isinstance(item, list) else None
            elif key.lower() not in {"api_key", "password", "authorization", "access_token", "client_secret"}:
                result[key] = _safe(item)
        return result
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


def _run_metadata(run):
    allowed = ("repository", "run_id", "run_attempt", "event_name", "actor", "triggering_actor", "workflow", "ref", "actions")
    result = {key: run.get(key) for key in allowed if run.get(key) is not None}
    result["hosted"] = (result.get("actions") == "true" and result.get("repository") == "cftorre1/Radar-salud"
                        and str(result.get("run_id", "")).isdigit()
                        and str(result.get("run_attempt", "")).isdigit())
    return result


def _rows(state):
    if len(state.get("tasks", {})) > MAX_TASKS:
        raise ObservationError("State exceeds the bounded task projection")
    rows = []
    review_keys = ("candidate_commit", "candidate_branch", "status", "semantic_fingerprint", "evidence_path", "evidence_sha256", "superseded")
    for task_id, task in sorted(state.get("tasks", {}).items()):
        lease = task.get("lease") or {}
        rows.append({"task_id": task_id, "family": task.get("family"), "status": task.get("status"),
            "fence": task.get("fence"), "input_sha": task.get("input_sha"),
            "input_fingerprint": task.get("input_fingerprint"), "evidence_revision": task.get("evidence_revision"),
            "lease": {key: _safe(lease).get(key) for key in ("owner", "token_sha256", "fence", "claimed_at", "heartbeat_at", "expires_at", "recovery_deadline_at")},
            "material_progress_at": task.get("material_progress_at"), "last_ready_at": task.get("last_ready_at"),
            "reason": task.get("reason"), "blocker_fingerprint": (task.get("blocker") or {}).get("fingerprint"),
            "blocker_evidence_count": len((task.get("blocker") or {}).get("evidence", [])),
            "recovery_reclaims": task.get("recovery_reclaims", 0), "recovery_episode": task.get("recovery_episode"),
            "attempts": task.get("attempts", 0), "failure_signature": (task.get("last_failure") or task.get("failure") or {}).get("failure_signature"),
            "failure_verified": bool(engine._failure_proof(task.get("failure") or task.get("last_failure") or (task.get("blocker") or {}).get("real_failure"))),
            "candidate_review": _safe({key: (task.get("candidate_review") or {}).get(key) for key in review_keys}),
            "candidate_reviews": {commit: _safe({key: review.get(key) for key in review_keys})
                for commit, review in sorted((task.get("candidate_reviews") or {}).items(),
                    key=lambda item: str(item[1].get("reviewed_at", "")))[-RECENT_EVENTS:]}})
    return rows


def _ledger(existing, baseline, rows, reference):
    if not isinstance(existing, list) or not isinstance(baseline, list):
        raise ObservationError("Learning ledger schema is not a list; refusing to replace it")
    merged = deepcopy(existing)
    def identity(item):
        return "id:" + str(item["id"]) if isinstance(item, dict) and item.get("id") else "record:" + digest(encode(item))
    seen = {identity(item) for item in merged}
    for item in baseline:
        key = identity(item)
        if key not in seen:
            merged.append(deepcopy(item)); seen.add(key)
    for row in rows:
        if row["status"] not in {"STALLED", "BLOCKED"}:
            continue
        signature = digest(encode({key: row.get(key) for key in ("task_id", "status", "blocker_fingerprint", "reason", "recovery_episode", "input_fingerprint")}))
        item = {"id": "autonomy_observed_" + signature, "source": "Autonomy hosted observation",
            "class": "observed_stall" if row["status"] == "STALLED" else "evidenced_task_blocker",
            "finding": "Observed canonical task " + row["status"] + ": " + row["task_id"],
            "root_cause": "See hashed canonical state observation; cause is not inferred from workflow conclusions.",
            "preventive_controls": ["task_lease", "heartbeat", "scoped_material_progress", "independent_family_continuation"],
            "status": "observed_open", "task_id": row["task_id"], "evidence": [reference],
            "observed_status": row["status"], "blocker_fingerprint": row["blocker_fingerprint"]}
        key = identity(item)
        if key not in seen:
            merged.append(item); seen.add(key)
    return merged


def build_mutation(snapshot, authority, *, observed_at, operation_id, run):
    if not OPERATION.fullmatch(operation_id) or not SHA.fullmatch(snapshot.commit):
        raise ObservationError("Observation requires a bounded operation ID and full state commit SHA")
    at = engine._time(observed_at)
    state = snapshot.read_json(STATE, {})
    if not isinstance(state, dict):
        raise ObservationError("Canonical control state must be an object")
    if (not isinstance(state.get("tasks", {}), dict)
            or any(not isinstance(task, dict) for task in state.get("tasks", {}).values())
            or not isinstance(state.get("material_events", []), list)
            or not isinstance(state.get("lease_events", []), list)):
        raise ObservationError("Canonical state collections have an unsupported schema")
    rows = _rows(state)
    events = state.get("material_events", [])
    lease_events = state.get("lease_events", [])
    # Keep per-event signatures, not arbitrary command output or repeated logs.
    material = [{"id": event.get("id") or digest(encode(event)), "at": event.get("at"), "kind": event.get("kind"),
                 "task_id": event.get("task_id"), "family": event.get("family"),
                 "candidate_commit": event.get("details", {}).get("candidate_commit"),
                 "failure_action": event.get("details", {}).get("failure_action"),
                 "independent": event.get("details", {}).get("independent")} for event in events[-RECENT_EVENTS:]]
    repaired_all = [event.get("id") or digest(encode(event)) for event in events if engine._repaired_failure_event(event)]
    repaired = repaired_all[-RECENT_EVENTS:]
    escalated = [row["task_id"] for row in rows if row["status"] == "BLOCKED" and row["failure_verified"] and row["blocker_fingerprint"] and row["blocker_evidence_count"]]
    pickups = [event for event in lease_events if event.get("kind") == "pickup"]
    transitions = [event for event in material if event["kind"] == "transition"]
    evaluated = engine.evaluate_acceptance(state, at)
    strict = deepcopy(evaluated)
    # This observer has no independent Work/chat source to validate the absence
    # of prompts. Do not upgrade an authored state attestation into a fact.
    strict["status"] = "NOT_PROVEN"
    if "owner_prompt_source_not_connected" not in strict["reasons"]:
        strict["reasons"].append("owner_prompt_source_not_connected")
    evidence_path = "data/autopilot/evidence/observation-" + operation_id + ".json"
    pins = {key: authority[key] for key in ("infra_sha", "staging_sha", "queue_blob_sha", "queue_sha256", "learning_ledger_blob_sha", "learning_ledger_sha256")}
    control_bytes = snapshot.read(STATE)
    pins.update(state_sha=snapshot.commit, state_control_sha256=digest(control_bytes) if control_bytes is not None else None)
    observation = {"schema_version": 2, "kind": "autonomy_observation", "operation_id": operation_id,
        "observed_at": at.isoformat(), "authority": pins, "run": _run_metadata(run), "tasks": rows,
        "canonical_control_present": control_bytes is not None,
        "families": {family: [row["task_id"] for row in rows if row["family"] == family] for family in engine.FAMILIES},
        "material_events": material, "material_event_count": len(events),
        "material_events_included": len(material), "material_signature": digest(encode(events)), "pickup_count": len(pickups),
        "declared_autonomous_pickup_count": sum(event.get("autonomous") is True for event in pickups),
        "pickup_causality_verified": False, "stalls": [row["task_id"] for row in rows if row["status"] == "STALLED"],
        "lease_stall_events": _safe([event for event in lease_events if event.get("kind") == "stalled"][-RECENT_EVENTS:]),
        "transitions": transitions, "pending_transitions": _safe(state.get("pending_transitions", [])[-RECENT_EVENTS:]),
        "owner_followups": "UNKNOWN", "owner_followup_count": None,
        "criteria": {"autonomous_pickup": {"status": "NOT_PROVEN", "declared_pickups": len(pickups), "reason": "Worker event/actor causality has not been independently verified."},
            "durable_mutation": {"status": "OBSERVED" if any(event.get("kind") == "mutation" for event in events) else "NOT_OBSERVED"},
            "failure_repaired": {"status": "OBSERVED" if repaired else "NOT_OBSERVED", "event_ids": repaired},
            "failure_repaired_or_evidenced_escalation": {"status": "OBSERVED" if repaired or escalated else "NOT_OBSERVED", "repaired_event_ids": repaired, "escalated_task_ids": escalated, "satisfies_legacy_stage_a_repair": bool(repaired)},
            "independent_transition": {"status": "OBSERVED" if any(event.get("kind") == "transition" and event.get("details", {}).get("independent") for event in events) else "NOT_OBSERVED"},
            "useful_work_window": {"metrics": deepcopy(evaluated["metrics"]), "is_live_proof": False},
            "owner_followups": {"status": "UNKNOWN", "count": None}, "legacy_stage_a": strict},
        "workflow_success_is_progress": False, "observation_is_material_progress": False,
        "canonical_queue_updated": False, "canonical_pmo_updated": False, "product_refs_modified": False}
    immutable = encode(observation)
    reference = {"path": evidence_path, "sha256": digest(immutable), "state_sha": snapshot.commit, "staging_sha": authority["staging_sha"]}
    canonical = {row["task_id"]: row for row in rows}
    projected = []
    approved_ids = set()
    for task in authority["queue"]["tasks"]:
        task_id = task.get("id")
        approved_ids.add(task_id)
        current = canonical.get(task_id)
        projected.append({"task_id": task_id, "queue_status": task.get("status"), "owner": task.get("owner"),
            "next_action": task.get("next_action"), "depends_on": deepcopy(task.get("depends_on", [])),
            "runtime": deepcopy(current) if current else {"status": "NOT_OBSERVED"},
            "approval_is_unchanged": True})
    projection = {"schema_version": 2, "kind": "queue_runtime_projection", "observation": reference,
        "authority": pins, "tasks": projected, "derived_runtime_tasks": [row for row in rows if row["task_id"] not in approved_ids],
        "canonical_queue_updated": False, "owner_followups": "UNKNOWN"}
    pmo = {"schema_version": 2, "kind": "autonomy_pmo_evidence", "observation": reference, "authority": pins,
        "criteria": observation["criteria"], "task_counts": {status: sum(row["status"] == status for row in rows) for status in sorted({str(row["status"]) for row in rows})},
        "material_event_count": len(events), "material_signature": observation["material_signature"],
        "stalls": observation["stalls"], "owner_followup_count": None, "owner_followups": "UNKNOWN",
        "canonical_pmo_updated": False, "legacy_stage_a_status": "NOT_PROVEN"}
    ledger = _ledger(snapshot.read_json(LEDGER, []), authority["learning_ledger"], rows, reference)
    writes = {evidence_path: immutable, QUEUE_PROJECTION: encode(projection), PMO_EVIDENCE: encode(pmo)}
    if snapshot.read(LEDGER) != encode(ledger).encode():
        writes[LEDGER] = encode(ledger)
    return Mutation(writes, observation)


def observe(infrastructure, workspace, report_path, *, store=None, clock=utcnow, run=None, operation_id=None):
    authority = capture_authority(infrastructure, workspace)
    operation_id = operation_id or uuid.uuid4().hex
    if run is None:
        run = {key: os.getenv(environment) for key, environment in (
            ("repository", "GITHUB_REPOSITORY"), ("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT"),
            ("event_name", "GITHUB_EVENT_NAME"), ("actor", "GITHUB_ACTOR"), ("triggering_actor", "GITHUB_TRIGGERING_ACTOR"),
            ("workflow", "GITHUB_WORKFLOW"), ("ref", "GITHUB_REF"), ("actions", "GITHUB_ACTIONS"))}
    authority_store = store or GitStateStore(repository=infrastructure)
    result = authority_store.transact(lambda snapshot: build_mutation(snapshot, authority,
        observed_at=clock(), operation_id=operation_id, run=run), message="autonomy: observe pinned state and publish truthful projections")
    report = {**result.value, "observation_state_commit": result.commit, "cas_attempts": result.attempts}
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(encode(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--infrastructure", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--report", default="artifacts/autonomy-observation.json")
    args = parser.parse_args()
    report = observe(args.infrastructure, args.workspace, args.report)
    print(encode({"observation_state_commit": report["observation_state_commit"], "owner_followups": "UNKNOWN",
                  "legacy_stage_a": report["criteria"]["legacy_stage_a"]["status"]}))


if __name__ == "__main__":
    main()
