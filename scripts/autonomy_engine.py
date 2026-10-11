"""Pure, fenced reducers for the GitHub-native autonomy control plane.

The caller serializes these reducers through the state store's compare-and-swap
transaction.  Workflow success, pickup, and heartbeats are deliberately excluded
from ``material_events``.  Evidence verification is the worker/controller's
responsibility; this module enforces the evidence contract before crediting it.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re


LEASE_SECONDS = 600
HEARTBEAT_SECONDS = 60
HEARTBEAT_GRACE_SECONDS = 180
STALL_SECONDS = 1800
MAX_IDENTICAL_AUDITS = 3
MAX_STALL_RECOVERIES = 3
SOURCE_TASKS = {
    "source_repair_media_lane_2026_10_11": "media",
    "source_repair_public_data_lane_2026_10_11": "public_data",
    "source_repair_fiscalization_lane_2026_10_11": "fiscalization",
    "source_repair_mutualities_lane_2026_10_11": "mutualities",
}
SOURCE_SLUGS = {"diario_financiero", "pulso_latercera", "fonasa", "fonasa_datos_abiertos",
                "isp_anamed", "isp_surveillance", "deis", "superintendencia_fiscalizacion",
                "suseso_fiscalizacion", "clinicas_achs_salud", "achs_seguro_laboral", "mutual_seguridad", "ist"}
EDITORIAL_TASK = "source_audit_issue5_iteration3_editorial_2026_10_09"
EDITORIAL_REPAIR_TASK = "editorial_repair_lane_2026_10_11"
FAMILIES = tuple(SOURCE_TASKS.values()) + ("editorial", "staging_qa")
APPROVED = {"approved", "in_progress"}
VERIFIED_QUEUE = {"validated", "completed", "closed"}
SHA_RE = re.compile(r"^[a-fA-F0-9]{40}$")
HASH_RE = re.compile(r"^[a-fA-F0-9]{64}$")


class LeaseError(ValueError):
    """An expired, revoked or fenced-out worker attempted to write."""


class ReportError(ValueError):
    """A report claims material progress without the required proof."""


def _time(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)):
        result = datetime.fromtimestamp(value, timezone.utc)
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def _iso(value):
    return _time(value).isoformat().replace("+00:00", "Z")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def _semantic(value):
    """Discard observation clocks, keeping evidence/input identities intact."""
    if isinstance(value, dict):
        return {key: _semantic(item) for key, item in value.items()
                if key not in {"timestamp", "at", "updated_at", "recorded_at", "reviewed_at",
                               "supplement_recorded_at", "generated_at", "observed_at", "checked_at",
                               "started_at", "finished_at", "heartbeat_at", "last_heartbeat_at",
                               "duration", "duration_seconds", "elapsed_seconds", "log_path", "log_sha256",
                               "trace_path", "trace_sha256", "operation_id", "response_bytes"}}
    if isinstance(value, list):
        return [_semantic(item) for item in value]
    if isinstance(value, str):
        if value.startswith("--junitxml="):
            return "--junitxml=<artifact>"
        value = re.sub(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b",
                       "<timestamp>", value)
        return re.sub(r"\bin \d+(?:\.\d+)?s\b", "in <duration>", value)
    return value


def _event(state, task, kind, now, details):
    event = {"family": task.get("family"), "task_id": task["id"],
             "at": _iso(now), "kind": kind, "details": deepcopy(details)}
    event["id"] = _hash(event)
    if not any(e["id"] == event["id"] for e in state["material_events"]):
        state["material_events"].append(event)
        task["material_progress_at"] = event["at"]
        task["material_watch_started_at"] = event["at"]
        task["recovery_reclaims"] = 0
        task["recovery_episode"] = event["id"]
        if task.get("lease"):
            task["lease"].pop("recovery_deadline_at", None)
    return event


def _failure_proof(value):
    if not isinstance(value, dict):
        return False
    if value.get("kind") == "source_runtime":
        return (value.get("verified") is True
                and str(value.get("source_url", "")).startswith("https://")
                and value.get("failure_signature") and value.get("trace_path")
                and HASH_RE.fullmatch(str(value.get("trace_sha256", "")))
                and value.get("observed_at"))
    return (str(value.get("run_id", "")).isdigit()
            and value.get("conclusion") in {"failure", "timed_out"}
            and str(value.get("run_url", "")).startswith(
                "https://github.com/cftorre1/Radar-salud/actions/runs/")
            and str(value["run_id"]) == value["run_url"].rstrip("/").split("/")[-1])


def _unexecuted_capability_overlay(value):
    """Remove only the exact no-plan diagnostic added to legacy recovery.

    A typed UNSUPPORTED label does not establish a new problem. Executed
    plans, paid attempts and unknown fields stay meaningful, as do all retained
    baseline commands, outputs, source facts and validation evidence.
    """
    if not isinstance(value, dict):
        return value
    allowed = {"baseline_full_gate", "blocker", "blocker_kind", "changed_paths", "context",
               "deterministic_planning", "evidence", "failure_sha256", "live_baseline",
               "material_progress", "signature", "source_run_id", "source_slug", "status", "validated"}
    planning = value.get("deterministic_planning")
    expected = {"diagnostic", "evidence", "material_progress", "paid_calls", "plan",
                "product_files_written", "status", "strategy"}
    diagnostic = planning.get("diagnostic") if isinstance(planning, dict) else None
    if (set(value) - allowed or not isinstance(planning, dict) or set(planning) != expected
            or value.get("status") != "BLOCKED" or value.get("validated") is not False
            or value.get("material_progress") is not False or value.get("changed_paths") != []
            or not isinstance(value.get("changed_paths"), list)
            or value.get("blocker_kind") != "executor_capability_missing"
            or value.get("blocker") != "No supported deterministic repair strategy for the reproduced failure; model lane disabled"
            or value.get("signature") is not None or value.get("source_run_id") is not None
            or not HASH_RE.fullmatch(str(value.get("failure_sha256")))
            or not isinstance(value.get("baseline_full_gate"), dict)
            or not isinstance(value.get("evidence"), list) or not value["evidence"]
            or planning.get("status") != "UNSUPPORTED" or planning.get("plan") is not None
            or planning.get("strategy") is not None or planning.get("evidence") != []
            or not isinstance(planning.get("evidence"), list)
            or planning.get("material_progress") is not False
            or planning.get("product_files_written") is not False
            or type(planning.get("paid_calls")) is not int or planning["paid_calls"] != 0
            or not isinstance(diagnostic, dict)
            or set(diagnostic) != {"human_required", "kind", "reason"}
            or diagnostic.get("human_required") is not False
            or diagnostic.get("kind") != "executor_capability_missing"
            or diagnostic.get("reason") != "No deterministic strategy is registered for this source/failure"):
        return value
    normalized = {key: item for key, item in value.items()
                  if key not in {"blocker_kind", "deterministic_planning"}}
    normalized["blocker"] = "Reproduced failure requires a bounded repair plan; model lane disabled"
    return normalized


def _staging_problem(value, failure, path=()):
    """Material identity, separate from retained transport/validation evidence.

    A fresh raw log digest is not evidence of a new problem when the report
    already contains its structured verdict or actual output. Browser aggregate
    proof alone cannot prove a *new* assertion; detailed cases, when supplied,
    remain part of this identity. Artifact/content hashes remain unchanged.
    """
    if isinstance(value, dict):
        value = _unexecuted_capability_overlay(value)
        structured = any(key in value for key in (
            "output", "stdout", "pytest", "browser_proof", "reviewer_proof", "evidence"))
        result = {}
        for key, item in value.items():
            if key in {"timestamp", "at", "updated_at", "recorded_at", "reviewed_at", "supplement_recorded_at",
                       "generated_at", "observed_at", "checked_at", "started_at", "finished_at", "heartbeat_at",
                       "last_heartbeat_at", "duration", "duration_seconds", "elapsed_seconds",
                       "log_path", "log_sha256", "trace_path", "trace_sha256", "operation_id", "response_bytes"}:
                continue
            if key == "startTime" and path[-2:] == ("browser_proof", "stats"):
                continue
            if (key == "fingerprint" and "reason" in value and "evidence" in value) or (structured and key in {
                    "captured_stdout_sha256", "captured_stdout_bytes", "failure_sha256", "failure_hash"}):
                continue
            if key == "task_id" and str(item) == "staging_qa_failed_run_" + str(failure["run_id"]):
                item = "<staging-failure-task>"
            elif key in {"candidate_sha", "head_sha"} and item == failure.get("head_sha"):
                item = "<bound-staging-product>"
            elif key == "command" and isinstance(item, list):
                item = list(item)
                for index in range(1, len(item)):
                    if item[index - 1] == "--sha" and item[index] == failure.get("head_sha"):
                        item[index] = "<bound-staging-product>"
            elif key in {"output", "stdout"} and isinstance(item, str):
                # Test duration is an observation. Assertion values and actual
                # publication/effective dates in strings remain exact evidence.
                item = re.sub(r"\bin \d+(?:\.\d+)?s\b", "in <duration>", item)
            result[key] = _staging_problem(item, failure, path + (key,))
        return result
    if isinstance(value, list):
        return [_staging_problem(item, failure, path) for item in value]
    if isinstance(value, str) and path[-1:] == ("command",) and value.startswith("--junitxml="):
        return "--junitxml=<artifact>"
    return value


def _staging_blocker_identity(blocker, product_fingerprint, failure):
    if (not _failure_proof(failure) or failure.get("kind") == "source_runtime"
            or not failure.get("failure_signature") or not product_fingerprint
            or not isinstance(blocker.get("evidence"), list) or not blocker["evidence"]):
        return None
    components = blocker.get("blockers") or [blocker]
    problems = []
    for component in components:
        problem = {key: component[key] for key in ("kind", "reason", "source_urls", "human_required")
                   if key in component}
        problem["evidence"] = sorted({_hash(_staging_problem(evidence, failure))
                                      for evidence in component["evidence"]})
        problems.append(problem)
    return {"failure_signature": failure["failure_signature"],
            "product_input_fingerprint": product_fingerprint,
            "problems": sorted({_hash(problem) for problem in problems})}


def _staging_event_binding(event, state):
    if event.get("kind") != "blocker" or event.get("family") != "staging_qa":
        return None
    details = event.get("details", {})
    failure = details.get("real_failure")
    task = state.get("tasks", {}).get(event.get("task_id"), {})
    product = details.get("product_input_fingerprint")
    if not product:
        # Legacy events have no frozen product binding. Infer it only from the
        # still-bound original failed run; a changed failure cannot rewrite it.
        current_failure = task.get("failure") or task.get("last_failure") or {}
        if (not isinstance(failure, dict)
                or task.get("status") != "BLOCKED"
                or _hash(task.get("blocker")) != _hash(details)
                or any(current_failure.get(key) != failure.get(key)
                       for key in ("run_id", "head_sha", "failure_signature"))):
            return None
        product = task.get("product_input_fingerprint")
    return {"task_id": event["task_id"], "product_input_fingerprint": product,
            "failure": deepcopy(failure)}


def _source_row(value):
    return (isinstance(value, dict) and value.get("slug") in SOURCE_SLUGS
            and isinstance(value.get("requests"), list) and "technical_status" in value
            and all(isinstance(request, dict) and request.get("url") and request.get("status")
                    for request in value["requests"])
            and isinstance(value.get("discovered"), int) and isinstance(value.get("dated"), int)
            and (isinstance(value.get("inventory_hash"), str) or isinstance(value.get("samples"), list)))


def _source_rows(value):
    if _source_row(value):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _source_rows(item)
    elif isinstance(value, list):
        for item in value:
            yield from _source_rows(item)


def _probe_budget_error(value):
    return bool(re.fullmatch(r"(?:RuntimeError:\s*)?bounded_probe_budget:\s*\d+(?: requests per source)?", str(value or "")))


def _source_probe_incomplete(row):
    if not _source_row(row):
        return False
    return (any(request.get("status") == "UNVERIFIED"
                and _probe_budget_error(request.get("error")) for request in row["requests"])
            and not any(request.get("status") == "FAIL" for request in row["requests"])
            and not (row.get("error") and not _probe_budget_error(row["error"])))


def source_failure_evidenced(failure, evidence=None):
    """Known incomplete instrumentation is not a publisher/parser failure.

    Historical verified flags are retained. Structured source diagnostics,
    when present, must demonstrate a failure independent of the probe guard.
    """
    if not _failure_proof(failure):
        return False
    if failure.get("kind") != "source_runtime":
        return True
    if (failure.get("failure_origin") == "instrumentation_limit"
            or _probe_budget_error(failure.get("error"))):
        return False
    rows = [row for row in _source_rows(evidence)
            if row.get("slug") == failure.get("source_slug")]
    if not rows:
        return True
    for row in rows:
        independent_error = row.get("error") and not _probe_budget_error(row["error"])
        if independent_error or any(
                request.get("status") == "FAIL"
                and not _probe_budget_error(request.get("error"))
                for request in row["requests"] if isinstance(request, dict)):
            return True
    return False


def _source_problem(value, *, covered=False, request_capture=False, path=()):
    """Retain parsed source meaning; capture churn alone cannot prove novelty."""
    if isinstance(value, dict):
        value = _unexecuted_capability_overlay(value)
        covered = covered or _source_row(value) or any(_source_rows(value))
        incomplete = _source_probe_incomplete(value)
        result = {}
        observation = (_source_row(value) or path[-1:] in {("requests",), ("real_failure",)}
                       or "command" in value or "automated_recovery" in value)
        for key, item in value.items():
            if _source_row(value) and key in {"probe_complete", "probe_budget", "failure_origin"}:
                # These classifications are derived from the exact requests,
                # retained below; correcting a label is no new source problem.
                continue
            if incomplete and key == "technical_status":
                item = "incomplete"
            if observation and key in {"observed_at", "generated_at", "checked_at", "reviewed_at", "started_at", "finished_at",
                       "duration", "duration_seconds", "elapsed_seconds", "log_path", "log_sha256", "trace_path", "trace_sha256"}:
                continue
            if key == "fingerprint" and "reason" in value and "evidence" in value:
                continue
            if key in {"captured_stdout_sha256", "captured_stdout_bytes", "failure_sha256", "failure_hash", "source_evidence_sha256"}:
                if covered or isinstance(value.get("output"), str):
                    continue
            if (key in {"response_sha256", "response_bytes"} and request_capture and path[-1:] == ("requests",)
                    and isinstance(value.get("url"), str) and value.get("status")):
                continue
            if key in {"output", "stdout"} and isinstance(item, str):
                if _source_row(value.get("source_evidence")) and "--diagnose-source" in value.get("command", []):
                    item = "<retained-structured-source-evidence>"
                else:
                    item = re.sub(r"\bin \d+(?:\.\d+)?s\b", "in <duration>", item)
            normalized = _source_problem(item, covered=covered,
                request_capture=request_capture or (key == "requests" and _source_row(value)), path=path + (key,))
            if key in {"requests", "evidence", "source_urls"} and isinstance(normalized, list):
                normalized = sorted(normalized, key=_hash)
            result[key] = normalized
        return result
    if isinstance(value, list):
        return [_source_problem(item, covered=covered, request_capture=request_capture, path=path) for item in value]
    if isinstance(value, str) and path[-1:] == ("command",) and value.startswith("--junitxml="):
        return "--junitxml=<artifact>"
    return value


def _source_blocker_identity(blocker, product_fingerprint, family):
    if (family not in SOURCE_TASKS.values() or not HASH_RE.fullmatch(str(product_fingerprint))
            or not any(_source_rows(blocker.get("evidence", [])))):
        return None
    problems = []
    for component in blocker.get("blockers") or [blocker]:
        evidence = component.get("evidence", [])
        rows = list(_source_rows(evidence))
        covered = bool(rows)
        incomplete = bool(rows) and all(_source_probe_incomplete(row) for row in rows)
        problem = {key: component[key] for key in ("kind", "reason", "human_required") if key in component}
        if incomplete:
            problem.update(kind="instrumentation", reason="Scoped source coverage incomplete: " + ",".join(sorted({row["slug"] for row in rows})))
        if "source_urls" in component:
            problem["source_urls"] = sorted(component["source_urls"])
        problem["evidence"] = sorted({_hash(_source_problem(item, covered=covered)) for item in evidence
                                      if not (incomplete and isinstance(item, dict) and "automated_recovery" in item)})
        problems.append(_hash(problem))
    return {"family": family, "product_input_fingerprint": product_fingerprint,
            "source_problem_signature": _hash(sorted(set(problems))), "problems": sorted(set(problems))}


def _source_event_binding(event, state):
    if event.get("kind") != "blocker" or event.get("family") not in SOURCE_TASKS.values():
        return None
    details = event.get("details", {})
    product = details.get("product_input_fingerprint")
    if product:
        return {"task_id": event["task_id"], "family": event["family"], "product_input_fingerprint": product}
    # Legacy product identity must come from immutable historical state and its
    # original worker report, verified by the trusted caller before this reducer.
    binding = state.get("material_event_product_bindings", {}).get(event.get("id"))
    if not isinstance(binding, dict):
        return None
    proof = binding.get("proof") or {}
    worker = proof.get("worker_result") or {}
    path = worker.get("path", "")
    if (binding.get("schema_version") != 1 or binding.get("verified") is not True
            or binding.get("task_id") != event.get("task_id") or binding.get("family") != event.get("family")
            or binding.get("event_sha256") != _hash(event)
            or not SHA_RE.fullmatch(str(binding.get("input_sha")))
            or not HASH_RE.fullmatch(str(binding.get("product_input_fingerprint")))
            or not SHA_RE.fullmatch(str(proof.get("state_commit")))
            or not HASH_RE.fullmatch(str(proof.get("control_sha256")))
            or not HASH_RE.fullmatch(str(worker.get("sha256")))
            or not re.fullmatch(r"data/autopilot/evidence/[A-Za-z0-9][A-Za-z0-9_.-]*\.json", str(path))):
        return None
    return deepcopy(binding)


def _event_blocker_binding(event, state):
    return _staging_event_binding(event, state) if event.get("family") == "staging_qa" else _source_event_binding(event, state)


def _bound_blocker_identity(event, binding):
    if event.get("family") == "staging_qa":
        return _staging_blocker_identity(event["details"], binding.get("product_input_fingerprint"), binding.get("failure"))
    return _source_blocker_identity(event["details"], binding.get("product_input_fingerprint"), event.get("family"))


def effective_material_events(state):
    """Return original events excluding only verifiable append-only corrections."""
    events = state.get("material_events", [])
    by_id = {event.get("id"): (index, event) for index, event in enumerate(events)}
    removed = set()
    for correction in state.get("material_event_corrections", []):
        if not isinstance(correction, dict) or correction.get("kind") not in {"duplicate_staging_blocker", "duplicate_source_blocker"}:
            continue
        invalid = by_id.get(correction.get("event_id"))
        retained = by_id.get(correction.get("retained_event_id"))
        if (not invalid or not retained or invalid[0] <= retained[0]
                or _hash(invalid[1]) != correction.get("event_sha256")
                or _hash(retained[1]) != correction.get("retained_event_sha256")):
            continue
        bindings = correction.get("bindings", [])
        if (not isinstance(bindings, list) or len(bindings) != 2
                or any(not isinstance(binding, dict) for binding in bindings)
                or (correction["kind"] == "duplicate_source_blocker"
                    and correction.get("bindings_sha256") != _hash(bindings))):
            continue
        identities = []
        for event, binding in zip((retained[1], invalid[1]), bindings):
            source = correction["kind"] == "duplicate_source_blocker"
            if (event.get("kind") != "blocker"
                    or (source and event.get("family") not in SOURCE_TASKS.values())
                    or (source and binding.get("family") != event.get("family"))
                    or (not source and event.get("family") != "staging_qa")
                    or binding.get("task_id") != event.get("task_id")
                    or (not source and binding.get("failure") != event.get("details", {}).get("real_failure"))
                    or (event.get("details", {}).get("product_input_fingerprint")
                        and event["details"]["product_input_fingerprint"] != binding.get("product_input_fingerprint"))):
                break
            if source and not event.get("details", {}).get("product_input_fingerprint"):
                frozen = _source_event_binding(event, {"material_event_product_bindings": {event["id"]: binding}})
                if not frozen:
                    break
            identities.append(_bound_blocker_identity(event, binding))
        if (len(bindings) == len(identities) == 2 and identities[0]
                and identities[0] == identities[1]
                and _hash(identities[0]) == correction.get("canonical_signature")
                and identities[0]["product_input_fingerprint"] == correction.get("product_input_fingerprint")
                and identities[0].get("failure_signature") == correction.get("failure_signature")
                and identities[0].get("source_problem_signature") == correction.get("source_problem_signature")):
            removed.add(invalid[1]["id"])
    return [event for event in events if event.get("id") not in removed]


def _correct_duplicate_staging_blockers(state, now):
    """Migrate proven historical transport duplicates without minting progress."""
    corrections = state.setdefault("material_event_corrections", [])
    already_corrected = {event.get("id") for event in state.get("material_events", [])} - {
        event.get("id") for event in effective_material_events(state)}
    seen = {}
    for event in state.get("material_events", []):
        if not event.get("id") or event["id"] in already_corrected:
            continue
        binding = _event_blocker_binding(event, state)
        if not binding:
            continue
        identity = _bound_blocker_identity(event, binding)
        if not identity:
            continue
        signature = _hash(identity)
        if signature not in seen:
            seen[signature] = (event, binding)
            continue
        retained, retained_binding = seen[signature]
        source = event.get("family") in SOURCE_TASKS.values()
        correction = {"kind": "duplicate_source_blocker" if source else "duplicate_staging_blocker", "event_id": event["id"],
            "retained_event_id": retained["id"], "at": _iso(now),
            "event_sha256": _hash(event), "retained_event_sha256": _hash(retained),
            "canonical_signature": signature,
            "product_input_fingerprint": identity["product_input_fingerprint"],
            "bindings": [deepcopy(retained_binding), deepcopy(binding)],
            "reason": "Same product and structured evidenced problem; capture aliases do not earn new progress."}
        correction["source_problem_signature" if source else "failure_signature"] = identity["source_problem_signature" if source else "failure_signature"]
        if source:
            correction["bindings_sha256"] = _hash(correction["bindings"])
        correction["id"] = _hash({key: correction[key] for key in ("kind", "event_id", "retained_event_id", "canonical_signature")})
        if not any(item.get("id") == correction["id"] for item in corrections):
            corrections.append(correction)
    effective = effective_material_events(state)
    invalid_ids = {event.get("id") for event in state.get("material_events", [])} - {event.get("id") for event in effective}
    state["pending_transitions"] = [item for item in state.get("pending_transitions", [])
                                    if item.get("event_id") not in invalid_ids]
    for task in state.get("tasks", {}).values():
        invalid_times = {event["at"] for event in state.get("material_events", [])
                         if event["id"] in invalid_ids and event["task_id"] == task["id"]}
        if (task.get("recovery_episode") not in invalid_ids
                and task.get("material_progress_at") not in invalid_times
                and task.get("material_watch_started_at") not in invalid_times):
            continue
        valid = [event for event in effective if event["task_id"] == task["id"]]
        latest = max(valid, key=lambda item: _time(item["at"])) if valid else None
        if latest:
            task["material_progress_at"] = latest["at"]
            task["material_watch_started_at"] = latest["at"]
            task["recovery_episode"] = latest["id"]
        else:
            task.pop("material_progress_at", None)
            pickups = [event["at"] for event in state.get("lease_events", [])
                       if event.get("task_id") == task["id"] and event.get("kind") == "pickup"]
            baseline = min(pickups, key=_time) if pickups else task["created_at"]
            task["material_watch_started_at"] = baseline
            task["recovery_episode"] = _hash([task["id"], baseline, task.get("input_fingerprint")])


def _family(task):
    if task["id"] in SOURCE_TASKS:
        return SOURCE_TASKS[task["id"]]
    if task["id"] in {EDITORIAL_TASK, EDITORIAL_REPAIR_TASK}:
        return "editorial"
    explicit = task.get("executor_family")
    if explicit in FAMILIES and explicit != "staging_qa":
        return explicit
    failure = task.get("failure")
    if ((task.get("family") == "staging_qa" or explicit == "staging_qa")
            and _failure_proof(failure) and failure.get("run_id")):
        return "staging_qa"
    return None


def _revision(task, queue):
    input_sha = task.get("input_sha", queue.get("input_sha", queue.get("source_sha", "")))
    inferred = _semantic({
        key: task.get(key) for key in ("objective", "instructions", "constraints",
                                     "evidence", "independent_review", "depends_on", "failure")
    })
    declared = _semantic({key: task[key] for key in (
        "acceptance_artifact", "repair_patch", "executor_family", "sources", "source_urls", "approved_at")
        if key in task})
    # Approval authority is a declared input, unlike an audit observation clock.
    if "approved_at" in task:
        declared["approved_at"] = task["approved_at"]
    evidence = task.get("evidence_revision")
    if evidence:
        # An externally declared revision token must not hide a new approved
        # patch or an acceptance artifact added after the task was blocked.
        if declared:
            evidence = _hash([evidence, declared])
    else:
        evidence = _hash({**inferred, **declared})
    if task.get("input_fingerprint"):
        evidence = _hash([evidence, task["input_fingerprint"]])
    return str(input_sha), str(evidence)


def _invalidate(task, status, now, reason):
    task["fence"] = task.get("fence", 0) + 1
    task["status"] = status
    task["lease"] = None
    task["state_changed_at"] = _iso(now)
    task["reason"] = reason
    if status == "READY":
        task["last_ready_at"] = _iso(now)
        task["pickup_ready_since"] = _iso(now)


def _material_baseline(task, state):
    if task.get("material_watch_started_at"):
        return _time(task["material_watch_started_at"])
    if task.get("material_progress_at"):
        return _time(task["material_progress_at"])
    pickups = [_time(event["at"]) for event in state.get("lease_events", [])
               if event.get("task_id") == task["id"] and event.get("kind") == "pickup"]
    if pickups:
        return min(pickups)
    lease = task.get("lease") or {}
    return _time(lease.get("claimed_at", task["created_at"]))


def _material_deadline_exceeded(task, state, now):
    if (_time(now) - _material_baseline(task, state)).total_seconds() < STALL_SECONDS:
        return False
    deadline = (task.get("lease") or {}).get("recovery_deadline_at")
    return not deadline or _time(now) >= _time(deadline)


def _block(state, task, blocker, now, *, terminal=False):
    # A moving branch or audit observation clock cannot turn the same blocker
    # into new progress. Credit only a changed problem/evidence identity.
    signature = _hash({"fingerprint": blocker["fingerprint"],
                       "evidence": sorted({_hash(_semantic(evidence)) for evidence in blocker["evidence"]})})
    actual_failure = blocker.get("real_failure", {}).get("failure_signature")
    global_signature = _hash([actual_failure, blocker["fingerprint"]]) if actual_failure else signature
    global_seen = state.setdefault("global_blocker_signatures", [])
    new = signature not in task.setdefault("blocker_signatures", []) and global_signature not in global_seen
    if task.get("family") == "staging_qa":
        identity = _staging_blocker_identity(blocker, task.get("product_input_fingerprint"), blocker.get("real_failure"))
        if identity:
            # Legacy opaque signatures can also hide a genuinely new product
            # or assertion. The canonical historical comparison owns credit.
            new = True
            for event in effective_material_events(state):
                binding = _staging_event_binding(event, state)
                if binding and identity == _staging_blocker_identity(event["details"],
                        binding["product_input_fingerprint"], binding["failure"]):
                    new = False
                    break
            blocker = {**blocker, "product_input_fingerprint": task["product_input_fingerprint"],
                       "canonical_material_signature": _hash(identity)}
    elif task.get("family") in SOURCE_TASKS.values():
        identity = _source_blocker_identity(blocker, task.get("product_input_fingerprint"), task["family"])
        if identity:
            new = True
            for event in effective_material_events(state):
                binding = _source_event_binding(event, state)
                if binding and identity == _bound_blocker_identity(event, binding):
                    new = False
                    break
        # Freeze every new source blocker product binding, including a blocked
        # executor without structured source evidence. Never reinterpret it
        # using a later task fingerprint.
        blocker = {**blocker, "product_input_fingerprint": task.get("product_input_fingerprint")}
    task["status"] = "BLOCKED"
    task["lease"] = None
    task["blocker"] = deepcopy(blocker)
    task["blocked_revision"] = [task["input_sha"], task["evidence_revision"]]
    task["state_changed_at"] = _iso(now)
    if new:
        task["blocker_signatures"].append(signature)
        global_seen.append(global_signature)
        event = _event(state, task, "blocker", now, blocker)
        if terminal:
            state["pending_transitions"].append({"task_id": task["id"],
                "family": task["family"], "event_id": event["id"], "at": event["at"]})
    return new


def reconcile(state, queue, now):
    """Overlay approved queue tasks, revoke paused tasks and reclaim stalls.

    Closed tasks never reopen merely because the clock or repository SHA moves.
    Blocked tasks reopen only when their input/evidence revision changes.
    Unknown approved tasks become explicit unsupported-executor blockers.
    """
    now = _time(now)
    result = deepcopy(state or {})
    result.setdefault("schema_version", 2)
    result.setdefault("tasks", {})
    result.setdefault("material_events", [])
    result.setdefault("lease_events", [])
    result.setdefault("pending_transitions", [])
    result.setdefault("failure_history", {})
    _correct_duplicate_staging_blockers(result, now)
    result.setdefault("acceptance", {"mode": "live", "started_at": _iso(now),
                                      "owner_restarts": [], "owner_prompts": []})
    tasks = queue.get("tasks", []) if isinstance(queue, dict) else queue
    if not isinstance(tasks, list):
        raise ValueError("queue.tasks must be a list")
    queue_meta = queue if isinstance(queue, dict) else {}
    by_id = {item["id"]: item for item in tasks}
    for task_id, current in result["tasks"].items():
        if current["status"] in {"RUNNING", "READY", "STALLED"}:
            source = by_id.get(task_id)
            if not source or source.get("status") not in APPROVED:
                _invalidate(current, "REVOKED", now, "queue_approval_removed")
    for source in tasks:
        if source.get("status") not in APPROVED:
            continue
        task_id = source["id"]
        input_sha, evidence_revision = _revision(source, queue_meta)
        family = _family(source)
        task = result["tasks"].setdefault(task_id, {
            "id": task_id, "status": "READY", "fence": 0, "lease": None,
            "created_at": _iso(now), "last_ready_at": _iso(now), "pickup_ready_since": _iso(now),
            "attempts": 0, "audit_counts": {},
            "blocker_signatures": [],
        })
        previous_evidence_revision = task.get("evidence_revision")
        # A sibling lane can push staging while this worker is still running.
        # Pin the active lease's input; evidence/approval changes still fence it.
        if (task["status"] == "RUNNING" and task.get("evidence_revision") == evidence_revision
                and task.get("input_sha") != input_sha):
            task["pending_input_sha"] = input_sha
            input_sha = task["input_sha"]
        changed = (task.get("input_sha"), task.get("evidence_revision")) != (
            input_sha, evidence_revision)
        # A scoped fingerprint identifies the files that can affect this task.
        # Keep observing the latest branch SHA, but do not retry a terminal task
        # when only a sibling lane changed that branch. Legacy unscoped tasks
        # still use the repository SHA as their relevant input revision.
        relevant_changed = (previous_evidence_revision != evidence_revision
                            or (not source.get("input_fingerprint")
                                and task.get("input_sha") != input_sha))
        task.update({"family": family, "input_sha": input_sha,
                     "evidence_revision": evidence_revision,
                     "queue_status": source["status"],
                     "priority": source.get("priority", "normal"),
                     "depends_on": deepcopy(source.get("depends_on", [])),
                     "objective": source.get("objective", ""),
                     "failure": deepcopy(source.get("failure")),
                     "input_fingerprint": source.get("input_fingerprint", evidence_revision),
                     "product_input_fingerprint": source.get("product_input_fingerprint", source.get("input_fingerprint", evidence_revision)),
                     "executor_fingerprint": source.get("executor_fingerprint"),
                     "approved": True})
        policy_blockers = source.get("blocked_by")
        if policy_blockers:
            _block(result, task, {"fingerprint": "queue_blocked_by:" + _hash(_semantic(policy_blockers)),
                "reason": "Approved task has an unresolved queue policy/dependency blocker.",
                "evidence": [{"queue_task_id": task_id, "blocked_by": deepcopy(policy_blockers)}]}, now)
            continue
        if (task["status"] == "BLOCKED"
                and task.get("blocker", {}).get("fingerprint", "").startswith("queue_blocked_by:")):
            _invalidate(task, "READY", now, "queue_policy_blocker_removed")
        if changed and task["status"] == "RUNNING":
            _invalidate(task, "READY", now, "input_changed_fenced_previous_worker")
        elif relevant_changed and task["status"] == "BLOCKED":
            exhausted = task.get("blocker", {}).get("kind") == "stall_recovery_budget"
            _invalidate(task, "READY", now, "input_or_evidence_changed")
            if exhausted:
                task["recovery_reclaims"] = 0
                task["material_watch_started_at"] = _iso(now)
                task["recovery_episode"] = _hash([task_id, evidence_revision, _iso(now)])
        elif relevant_changed and task["status"] == "CLOSED" and source.get("reopen_on_input_change"):
            _invalidate(task, "READY", now, "explicit_repeatable_task_input_changed")
        elif task["status"] == "REVOKED":
            _invalidate(task, "READY", now, "queue_approval_restored")
        if family is None:
            _block(result, task, {"fingerprint": "unsupported_executor:" + task_id,
                "reason": "No installed executor for this approved task; task remains open.",
                "evidence": [{"queue_task_id": task_id, "queue_status": source["status"],
                              "supported_families": list(FAMILIES)}]}, now)
            continue
        if task["status"] == "RUNNING":
            lease = task["lease"]
            reason = None
            if _material_deadline_exceeded(task, result, now):
                reason = "no_material_progress_30m"
            elif now >= _time(lease["expires_at"]):
                reason = "lease_expired"
            elif (now - _time(lease["heartbeat_at"])).total_seconds() >= HEARTBEAT_GRACE_SECONDS:
                reason = "heartbeat_missing"
            if reason:
                old_token = lease["token"]
                _invalidate(task, "STALLED", now, reason)
                result["lease_events"].append({"task_id": task_id, "family": family,
                    "at": _iso(now), "kind": "stalled", "reason": reason,
                    "fenced_token": old_token})
        elif task["status"] == "READY":
            if not _dependencies_satisfied(task, result, queue):
                task["awaiting_dependencies"] = True
                task["pickup_ready_since"] = None
                continue
            if task.pop("awaiting_dependencies", False):
                task["last_ready_at"] = _iso(now)
            ready_since = task.get("last_ready_at", task["created_at"])
            task["pickup_ready_since"] = ready_since
            reason = None
            if (now - _time(ready_since)).total_seconds() >= STALL_SECONDS:
                reason = "no_pickup_30m"
            elif task.get("material_watch_started_at") and _material_deadline_exceeded(task, result, now):
                reason = "no_material_progress_30m"
            if reason:
                _invalidate(task, "STALLED", now, reason)
                result["lease_events"].append({"task_id": task_id, "family": family,
                    "at": _iso(now), "kind": "stalled", "reason": reason,
                    "ready_since": ready_since})
    return result


def _dependencies_satisfied(task, state, queue):
    sources = {t["id"]: t for t in (queue.get("tasks", []) if isinstance(queue, dict) else queue)}
    for dep in task.get("depends_on", []):
        control = state["tasks"].get(dep)
        if control and control["status"] == "CLOSED":
            continue
        if sources.get(dep, {}).get("status") in VERIFIED_QUEUE:
            continue
        return False
    return True


def plan(state, queue, now):
    """Return independent per-family candidates; no global QA/branch blocker."""
    result = reconcile(state, queue, now)
    candidates = {}
    priority = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    running = {t["family"] for t in result["tasks"].values() if t["status"] == "RUNNING"}
    for task in sorted(result["tasks"].values(),
                       key=lambda t: (priority.get(t["priority"], 2), t["created_at"], t["id"])):
        family = task["family"]
        if (family not in FAMILIES or family in running or family in candidates
                or task["status"] not in {"READY", "STALLED"}
                or not _dependencies_satisfied(task, result, queue)):
            continue
        if task["status"] == "STALLED" and task.get("recovery_reclaims", 0) >= MAX_STALL_RECOVERIES:
            episode = task.get("recovery_episode")
            reclaims = task["recovery_reclaims"]
            _block(result, task, {"kind": "stall_recovery_budget",
                "fingerprint": "recovery_budget_exhausted:" + _hash([task["id"], episode, task["input_fingerprint"]]),
                "reason": "Three lease recovery pickups without material progress are exhausted.",
                "evidence": [{"task_id": task["id"], "recovery_episode": episode,
                    "recovery_reclaims": reclaims, "input_fingerprint": task["input_fingerprint"],
                    "material_watch_started_at": task.get("material_watch_started_at"),
                    "stalled_leases": [deepcopy(event) for event in result["lease_events"]
                                       if event.get("task_id") == task["id"] and event.get("kind") == "stalled"]}],
                "human_required": False}, now, terminal=task.get("attempts", 0) > 0)
            # Keep the exhausted count visible after the evidenced terminal event.
            task["recovery_reclaims"] = reclaims
            continue
        known_failure = task.get("failure") or task.get("last_failure") or {}
        failure_signature = known_failure.get("failure_signature")
        if failure_signature:
            key = _hash([failure_signature, task["input_fingerprint"]])
            history = result["failure_history"].get(key, {})
            if history.get("attempts", 0) >= MAX_IDENTICAL_AUDITS:
                _block(result, task, {"fingerprint": "failure_budget_exhausted:" + key,
                    "reason": "Three repair attempts for the same failure and relevant inputs are exhausted.",
                    "evidence": [{"failure_signature": failure_signature,
                                  "input_fingerprint": task["input_fingerprint"],
                                  "attempts": history["attempts"]}],
                    "real_failure": deepcopy(known_failure), "failure_action": "blocked"}, now)
                continue
        candidates[family] = {"task_id": task["id"], "family": family,
            "input_sha": task["input_sha"], "evidence_revision": task["evidence_revision"],
            "reason": task.get("reason", "approved_available"),
            "failure": deepcopy(task.get("failure"))}
    return result, candidates


def claim(state, queue, family, owner, now):
    """Claim one task with a unique fencing token inside the caller's CAS."""
    if family not in FAMILIES:
        raise ValueError("unsupported family: " + str(family))
    if not owner:
        raise ValueError("owner is required")
    now = _time(now)
    result, candidates = plan(state, queue, now)
    if family not in candidates:
        return result, None
    task = result["tasks"][candidates[family]["task_id"]]
    recovering = task["status"] == "STALLED" and task.get("attempts", 0) > 0
    if not task.get("material_watch_started_at"):
        task["material_watch_started_at"] = _iso(now) if not task.get("attempts", 0) else _iso(_material_baseline(task, result))
    task.setdefault("recovery_reclaims", 0)
    task.setdefault("recovery_episode", _hash([task["id"], task["material_watch_started_at"], task["input_fingerprint"]]))
    if recovering:
        task["recovery_reclaims"] += 1
    task["fence"] += 1
    task["attempts"] += 1
    token = _hash({"task_id": task["id"], "fence": task["fence"],
                   "owner": owner, "now": _iso(now)})
    task["lease"] = {"token": token, "fence": task["fence"], "owner": owner,
        "claimed_at": _iso(now), "heartbeat_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=LEASE_SECONDS))}
    if recovering and (now - _material_baseline(task, result)).total_seconds() >= STALL_SECONDS:
        task["lease"]["recovery_deadline_at"] = _iso(now + timedelta(seconds=LEASE_SECONDS))
    task["status"] = "RUNNING"
    task["state_changed_at"] = _iso(now)
    result["lease_events"].append({"task_id": task["id"], "family": family,
        "at": _iso(now), "kind": "pickup", "owner": owner, "fence": task["fence"],
        "autonomous": not str(owner).lower().startswith(("owner", "toba", "manual"))})
    # Credit a terminal-to-different-task transition once. Initial fan-out is
    # not a transition, and a retry of the same task cannot manufacture one.
    for terminal in list(result["pending_transitions"]):
        if terminal["task_id"] == task["id"] or terminal["task_id"] in task["depends_on"]:
            continue
        _event(result, task, "transition", now, {
            "from_task_id": terminal["task_id"], "from_family": terminal["family"],
            "terminal_event_id": terminal["event_id"], "independent": True})
        result["pending_transitions"].remove(terminal)
        break
    payload = deepcopy(candidates[family])
    payload.update({"token": token, "fence": task["fence"], "owner": owner,
                    "lease_expires_at": task["lease"]["expires_at"],
                    "heartbeat_seconds": HEARTBEAT_SECONDS})
    return result, payload


def _leased(state, task_id, token, now):
    task = state.get("tasks", {}).get(task_id)
    lease = task.get("lease") if task else None
    if (not task or task["status"] != "RUNNING" or not lease
            or lease["token"] != token or lease["fence"] != task["fence"]
            or _time(now) >= _time(lease["expires_at"])):
        raise LeaseError("lease is expired, revoked or fenced: " + task_id)
    if _time(now) < _time(lease["heartbeat_at"]):
        raise LeaseError("worker timestamp moved backwards")
    if _material_deadline_exceeded(task, state, now):
        raise LeaseError("task is STALLED without material progress for 30m")
    return task


def heartbeat(state, task_id, token, now):
    """Renew a valid lease, without changing its material-progress clock."""
    result = deepcopy(state)
    task = _leased(result, task_id, token, now)
    task["lease"]["heartbeat_at"] = _iso(now)
    expires = _time(now) + timedelta(seconds=LEASE_SECONDS)
    if task["lease"].get("recovery_deadline_at"):
        expires = min(expires, _time(task["lease"]["recovery_deadline_at"]))
    task["lease"]["expires_at"] = _iso(expires)
    return result


def _gate_evidenced(value):
    return (isinstance(value, dict) and value.get("command") and value.get("log_path")
            and HASH_RE.fullmatch(str(value.get("log_sha256", "")))
            and isinstance(value.get("returncode"), int))


def _gates_pass(report):
    gates = report.get("gates")
    if not gates:
        return False
    values = list(gates.values()) if isinstance(gates, dict) else gates
    return isinstance(values, list) and all(
        _gate_evidenced(value) and value.get("status") == "PASS" and value.get("returncode") == 0
        for value in values)


def candidate_validated(report):
    """Accept full PASS, or an isolated repair with proven baseline non-regression.

    The latter may be stored durably on its own candidate branch. It does not
    permit integration into staging or a task closure. Raw strings, skipped
    tests and declarations without hashed command logs provide no proof.
    """
    if report.get("validated") is True and _gates_pass(report):
        return True
    if not (report.get("partial_candidate") is True and report.get("targeted_validated") is True
            and report.get("no_new_failures") is True and report.get("candidate_scope") == "isolated"
            and _gates_pass({"gates": report.get("directed_gates")})):
        return False
    proof = report.get("non_regression")
    if not isinstance(proof, dict):
        return False
    baseline = proof.get("baseline_failures")
    candidate = proof.get("candidate_failures")
    if not (isinstance(baseline, list) and baseline and isinstance(candidate, list)
            and all(HASH_RE.fullmatch(str(item)) for item in baseline + candidate)
            and len(baseline) == len(set(baseline)) and len(candidate) == len(set(candidate))
            and set(candidate) <= set(baseline)):
        return False
    baseline_gate, candidate_gate = proof.get("baseline_gate"), proof.get("candidate_gate")
    if not (_gate_evidenced(baseline_gate) and _gate_evidenced(candidate_gate)
            and baseline_gate["command"] == candidate_gate["command"]
            and baseline_gate["returncode"] != 0
            and ((candidate and candidate_gate["returncode"] != 0)
                 or (not candidate and candidate_gate["returncode"] == 0))):
        return False
    if report.get("family") in SOURCE_TASKS.values():
        if not (report.get("live_validated") is True
                and _gates_pass({"gates": [report.get("live_gate")]})):
            return False
    return True


def _source_repair_proven(report):
    failure = report.get("real_failure") or {}
    slug = failure.get("source_slug")
    return (source_failure_evidenced(failure, report.get("evidence"))
            and failure.get("kind") == "source_runtime" and slug
            and slug in (report.get("live_scope") or [])
            and report.get("targeted_validated") is True and report.get("live_validated") is True
            and _gates_pass({"gates": report.get("directed_gates") or report.get("gates")})
            and _gates_pass({"gates": [report.get("live_gate")]}))


def _repaired_failure_event(event):
    details = event.get("details", {})
    failure = details.get("real_failure")
    if not (source_failure_evidenced(failure, details.get("failure_evidence", details.get("evidence")))
            and details.get("failure_action") == "repaired"):
        return False
    if failure.get("kind") == "source_runtime":
        return bool(event.get("kind") == "closure" and details.get("validated") is True
                    and _gates_pass(details) and _source_postmerge_proven(
                        details.get("acceptance_proof"), details.get("input_sha")))
    # A partial isolated candidate can retain the original staging failure.
    # Old events with an optimistic repaired label must not satisfy Stage A.
    return bool(event.get("kind") == "mutation" and details.get("validated") is True and _gates_pass(details))


def _source_postmerge_proven(proofs, input_sha):
    if not isinstance(input_sha, str) or not SHA_RE.fullmatch(input_sha):
        return False
    if not isinstance(proofs, list) or not proofs:
        return False
    for proof in proofs:
        if not (isinstance(proof, dict) and proof.get("verified") is True
                and proof.get("candidate_sha") == input_sha and proof.get("staging_merge_sha") == input_sha
                and SHA_RE.fullmatch(str(proof.get("origin_staging_sha", "")))
                and isinstance(proof.get("checks"), dict)
                and proof["checks"].get("runtime_after_merge_pass") is True):
            return False
        runtime = proof.get("runtime_after_merge")
        evidence = proof.get("evidence")
        if not isinstance(runtime, list) or not runtime or not isinstance(evidence, list):
            return False
        for reference in runtime:
            if not (isinstance(reference, dict) and reference.get("kind") == "runtime_after_merge"
                    and reference.get("path") and HASH_RE.fullmatch(str(reference.get("sha256", "")))
                    and any(isinstance(item, dict) and item.get("kind") == "runtime_after_merge"
                            and item.get("path") == reference["path"]
                            and item.get("sha256") == reference["sha256"] for item in evidence)):
                return False
    return True


def _closure_proven(report, task):
    proofs = report.get("acceptance_proof")
    generic = (report.get("status", "").upper() == "PASS"
            and report.get("validated") is True and _gates_pass(report)
            and isinstance(proofs, list) and bool(proofs) and all(
                isinstance(proof, dict) and proof.get("verified") is True
                and proof.get("task_id") == task["id"] and proof.get("verdict") == "PASS"
                and proof.get("candidate_sha") == task["input_sha"]
                and proof.get("path") and HASH_RE.fullmatch(str(proof.get("sha256", "")))
                and proof.get("checks") and isinstance(proof.get("evidence"), list)
                and bool(proof["evidence"]) and all(isinstance(evidence, dict)
                    and evidence.get("path") and HASH_RE.fullmatch(str(evidence.get("sha256", "")))
                    for evidence in proof["evidence"])
                for proof in proofs))
    if not generic:
        return False
    if task["family"] in SOURCE_TASKS.values():
        return _source_postmerge_proven(proofs, task["input_sha"])
    return True


def _mutation(report):
    before = report.get("before_hash", report.get("input_hash"))
    after = report.get("after_hash", report.get("semantic_hash"))
    return (candidate_validated(report)
            and SHA_RE.fullmatch(str(report.get("candidate_commit", "")))
            and isinstance(report.get("changed_paths"), list) and report["changed_paths"]
            and HASH_RE.fullmatch(str(before)) and HASH_RE.fullmatch(str(after)) and before != after)


def _blockers(report):
    blockers = report.get("blockers", [])
    if report.get("blocker"):
        blockers = [report["blocker"]] + blockers
    if not isinstance(blockers, list):
        raise ReportError("blockers must be a list of evidenced objects")
    for item in blockers:
        if (not isinstance(item, dict) or not item.get("fingerprint")
                or not item.get("reason") or not isinstance(item.get("evidence"), list)
                or not item["evidence"]):
            raise ReportError("blocker requires fingerprint, reason and nonempty evidence")
    unique = {_hash(_semantic(item)): item for item in blockers}
    return [unique[key] for key in sorted(unique)]


def finish(state, task_id, token, report, now):
    """Finalize a worker report; an unsupported SUCCESS earns zero progress.

    A REPAIRED mutation can leave a task READY for further acceptance work.
    PASS closes only with explicit acceptance_proof plus passed validation.
    Identical audits are bounded by input SHA and evidence revision, then the
    task blocks until those inputs change. Reports are immutable caller assets.
    """
    result = deepcopy(state)
    task = _leased(result, task_id, token, now)
    if report.get("task_id", task_id) != task_id or report.get("family", task["family"]) != task["family"]:
        raise ReportError("report does not match leased task/family")
    # Bind family-based proof requirements even when the caller omits family.
    report = {**report, "family": task["family"]}
    real_failure = task.get("failure") if _failure_proof(task.get("failure")) else report.get("real_failure")
    if source_failure_evidenced(real_failure, report.get("evidence") or report.get("blockers")) and real_failure.get("failure_signature"):
        task["last_failure"] = deepcopy(real_failure)
        if real_failure.get("kind") == "source_runtime":
            task["last_failure_evidence"] = deepcopy(report.get("evidence") or report.get("blockers"))
        key = _hash([real_failure["failure_signature"], task["input_fingerprint"]])
        history = result.setdefault("failure_history", {}).setdefault(key, {
            "failure_signature": real_failure["failure_signature"],
            "input_fingerprint": task["input_fingerprint"], "attempts": 0,
            "task_ids": [], "tokens": []})
        if token not in history["tokens"]:
            history["tokens"].append(token)
            history["attempts"] += 1
            history["last_attempt_at"] = _iso(now)
            if task_id not in history["task_ids"]:
                history["task_ids"].append(task_id)
    status = report.get("status", "SUCCESS").upper()
    blockers = _blockers(report)
    if status == "BLOCKED" and not blockers:
        raise ReportError("BLOCKED requires an evidenced blocker")
    valid_mutation = bool(_mutation(report))
    if report.get("changed_paths") and not valid_mutation:
        raise ReportError("mutation requires durable candidate_commit, unequal hashes and PASS gates")
    mutation_signature = _hash({key: report.get(key) for key in (
        "candidate_commit", "changed_paths", "before_hash", "after_hash", "input_hash", "semantic_hash")})
    after_hash = report.get("after_hash", report.get("semantic_hash"))
    mutation = (valid_mutation and mutation_signature not in task.setdefault("mutation_signatures", [])
                and after_hash != task.get("last_mutation_hash"))
    closure = _closure_proven(report, task)
    if status == "PASS" and not closure:
        raise ReportError("PASS closure requires explicit acceptance_proof and PASS gates")
    if mutation:
        task["mutation_signatures"].append(mutation_signature)
        task["last_mutation_hash"] = after_hash
        details = {key: deepcopy(report.get(key)) for key in (
            "candidate_commit", "candidate_branch", "changed_paths", "before_hash",
            "after_hash", "input_hash", "semantic_hash", "gates", "evidence",
            "partial_candidate", "candidate_scope", "directed_gates", "non_regression", "live_gate",
            "validated", "targeted_validated", "live_validated", "live_scope")}
        details["input_fingerprint"] = task["input_fingerprint"]
        details["product_input_fingerprint"] = task["product_input_fingerprint"]
        details["executor_fingerprint"] = task.get("executor_fingerprint")
        details["parent_input_sha"] = task["input_sha"]
        if (task["family"] == "staging_qa" and _failure_proof(task.get("failure"))
                and (task["failure"] or {}).get("kind") != "source_runtime" and report.get("validated") is True
                and _gates_pass(report)):
            details["real_failure"] = deepcopy(task["failure"])
            details["failure_action"] = "repaired"
        elif (_failure_proof(report.get("real_failure")) and report.get("failure_action") == "repaired"
              and _source_repair_proven(report)):
            details["real_failure"] = deepcopy(report["real_failure"])
            details["failure_action"] = "candidate_failure_resolved"
        _event(result, task, "mutation", now, details)
    if blockers:
        # One terminal event is enough for a subsequent independent transition.
        combined = {"fingerprint": _hash(sorted(str(b["fingerprint"]) for b in blockers)),
                    "reason": "; ".join(b["reason"] for b in blockers),
                    "evidence": [e for b in blockers for e in b["evidence"]],
                    "blockers": deepcopy(blockers)}
        if _failure_proof(task.get("failure")):
            combined["real_failure"] = deepcopy(task["failure"])
            combined["failure_action"] = "blocked"
        elif _failure_proof(report.get("real_failure")) and report.get("failure_action") == "blocked":
            combined["real_failure"] = deepcopy(report["real_failure"])
            combined["failure_action"] = "blocked"
        _block(result, task, combined, now, terminal=True)
    elif closure:
        task["status"] = "CLOSED"
        task["lease"] = None
        task["closed_at"] = _iso(now)
        closure_details = {
            "acceptance_proof": deepcopy(report["acceptance_proof"]),
            "gates": deepcopy(report["gates"]), "candidate_commit": report.get("candidate_commit"),
            "validated": True, "input_sha": task["input_sha"]}
        last_failure = task.get("last_failure")
        failure_evidence = task.get("last_failure_evidence") or (task.get("blocker") or {}).get("evidence")
        if (task["family"] in SOURCE_TASKS.values() and source_failure_evidenced(last_failure, failure_evidence)
                and last_failure.get("kind") == "source_runtime"
                and _source_postmerge_proven(report["acceptance_proof"], task["input_sha"])):
            closure_details["real_failure"] = deepcopy(last_failure)
            closure_details["failure_action"] = "repaired"
            closure_details["failure_evidence"] = deepcopy(failure_evidence)
        event = _event(result, task, "closure", now, closure_details)
        result["pending_transitions"].append({"task_id": task_id, "family": task["family"],
            "event_id": event["id"], "at": event["at"]})
    elif mutation:
        task["status"] = "READY"
        task["lease"] = None
        task["reason"] = "mutation_durable_acceptance_not_yet_proven"
    else:
        fingerprint = str(report.get("audit_fingerprint") or _hash({
            key: report.get(key) for key in ("status", "semantic_hash", "findings", "blockers")}))
        signature = _hash([task["input_sha"], task["evidence_revision"], fingerprint])
        count = task["audit_counts"].get(signature, 0) + 1
        task["audit_counts"][signature] = count
        task["last_audit_fingerprint"] = fingerprint
        task["status"] = "READY"
        task["lease"] = None
        task["reason"] = "no_material_progress"
        if count >= MAX_IDENTICAL_AUDITS:
            _block(result, task, {"fingerprint": "identical_audit:" + signature,
                "reason": "Three identical audits on unchanged inputs produced no material progress.",
                "evidence": [{"audit_fingerprint": fingerprint, "attempts": count,
                              "input_sha": task["input_sha"],
                              "evidence_revision": task["evidence_revision"]}]}, now, terminal=True)
    task["state_changed_at"] = _iso(now)
    if task["status"] == "READY":
        task["last_ready_at"] = _iso(now)
        task["pickup_ready_since"] = _iso(now)
    return result


def _owner_observation_verified(observation, start, end, real_now):
    """Require a verified, evidence-bound observation across both owner channels.

    The observation producer must verify the immutable document and its hash.
    This pure reducer checks the attestation contract; empty event lists alone
    cannot prove that owner interventions were observed and absent.
    """
    if not isinstance(observation, dict) or observation.get("verified") is not True:
        return False
    channels = observation.get("channels")
    if (not isinstance(channels, list) or not all(isinstance(item, str) for item in channels)
            or not {"github_actions", "owner_prompt_events"}.issubset(channels)):
        return False
    evidence = observation.get("evidence")
    if not isinstance(evidence, dict) or not HASH_RE.fullmatch(str(evidence.get("sha256", ""))):
        return False
    path = evidence.get("path")
    prefix = "data/autopilot/evidence/"
    if not isinstance(path, str) or not path.startswith(prefix):
        return False
    components = path[len(prefix):].split("/")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", part)
           or part in {".", ".."} for part in components):
        return False
    try:
        observed_start = _time(observation["started_at"])
        observed_until = _time(observation["observed_until"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    return observed_start <= start <= end <= observed_until <= real_now


def _owner_events_in_window(records, start, end, real_now):
    """Retain unknown interventions; only verified event clocks exclude history."""
    if records is None:
        return []
    if not isinstance(records, list):
        return [records]
    result = []
    for record in records:
        try:
            if not isinstance(record, dict):
                raise ValueError("Owner intervention has no event timestamp")
            recorded_at = next(record[key] for key in ("at", "timestamp", "observed_at") if key in record)
            if isinstance(recorded_at, bool):
                raise ValueError("Boolean is not an owner event timestamp")
            at = _time(recorded_at)
            if at > real_now:
                raise ValueError("Future owner intervention is not observed evidence")
        except (StopIteration, KeyError, TypeError, ValueError, OverflowError):
            result.append(record)
            continue
        if start <= at <= end:
            result.append(record)
    return result


def evaluate_acceptance(state, now, *, wall_now=None):
    """Evaluate Stage A using real elapsed time; simulation never yields PASS.

    ``wall_now`` is injectable only for tests. The production caller must omit
    it. Material gaps include both edges of the observation window. Absence of
    owner intervention requires verified coverage of Actions and owner prompts.
    The latest actual four-hour window can qualify after an earlier stall;
    the original first-pickup authority and complete raw history stay intact.
    """
    now = _time(now)
    real_now = _time(wall_now) if wall_now is not None else datetime.now(timezone.utc)
    acceptance = state.get("acceptance", {})
    reasons = []
    if acceptance.get("mode") != "live":
        reasons.append("simulation_is_not_live_acceptance")
    original_start = _time(acceptance.get("started_at", now))
    end = min(now, real_now)
    start = max(original_start, end - timedelta(hours=4))
    total_elapsed = max(0, (end - original_start).total_seconds())
    elapsed = max(0, (end - start).total_seconds())
    if now > real_now + timedelta(seconds=60):
        reasons.append("observation_time_is_in_the_future")
    if elapsed < 4 * 3600:
        reasons.append("four_real_wall_hours_not_observed")
    owner_observation_verified = _owner_observation_verified(
        acceptance.get("owner_observation"), start, end, real_now)
    if not owner_observation_verified:
        reasons.append("owner_intervention_observation_not_verified")
    restarts = _owner_events_in_window(acceptance.get("owner_restarts"), start, end, real_now)
    prompts = _owner_events_in_window(acceptance.get("owner_prompts"), start, end, real_now)
    if restarts or prompts:
        reasons.append("owner_restart_or_followup_in_window")
    events = [e for e in effective_material_events(state) if start <= _time(e["at"]) <= end]
    pickups = [e for e in state.get("lease_events", []) if e["kind"] == "pickup"
               and e.get("autonomous") and start <= _time(e["at"]) <= end]
    if not pickups:
        reasons.append("autonomous_pickup_not_observed")
    if not any(e["kind"] == "mutation" for e in events):
        reasons.append("durable_verified_mutation_not_observed")
    if not any(_repaired_failure_event(event) for event in events):
        reasons.append("real_failure_verified_repair_not_observed")
    if not any(e["kind"] == "transition" and e["details"].get("independent") for e in events):
        reasons.append("automatic_independent_transition_not_observed")
    points = [start] + sorted(_time(e["at"]) for e in events) + [end]
    max_gap = max(((b - a).total_seconds() for a, b in zip(points, points[1:])), default=elapsed)
    if max_gap > STALL_SECONDS:
        reasons.append("material_progress_gap_exceeded_30m")
    return {"status": "PASS" if not reasons else "NOT_PROVEN", "reasons": reasons,
            "metrics": {"observed_seconds": elapsed, "total_elapsed_seconds": total_elapsed,
                        "original_started_at": _iso(original_start), "window_started_at": _iso(start),
                        "material_event_count": len(events),
                        "autonomous_pickups": len(pickups), "max_material_gap_seconds": max_gap,
                        "owner_restarts": len(restarts), "owner_prompts": len(prompts),
                        "owner_observation_verified": owner_observation_verified,
                        "mode": acceptance.get("mode")},
            "observed_until": _iso(end)}
