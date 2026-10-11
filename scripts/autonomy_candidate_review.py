"""Independently validate a recorded isolated candidate without merging it.

Reviews are bound to the exact candidate SHA and retained in the remote control
plane. Technical PASS never substitutes for source/editorial acceptance.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET

try:
    from .autonomy_state_store import GitStateStore, Mutation
except ImportError:
    from autonomy_state_store import GitStateStore, Mutation

STATE = "data/autopilot/control_v2.json"
FAMILIES = {"media", "public_data", "fiscalization", "mutualities", "editorial", "staging_qa"}
PRODUCTION_BRANCHES = {"main", "master", "production", "production-stable", "prod", "staging"}
SHA = re.compile(r"^[a-f0-9]{40}$")


class ReviewError(ValueError):
    """Candidate review could not establish its durable authority."""


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def redact(value):
    for key in ("OPENAI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        secret = os.environ.get(key)
        if secret and len(secret) >= 8:
            value = value.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)((?:api[_-]?key|password|authorization|access[_-]?token)\s*[=:]\s*)([^\s,;\"']+)", r"\1[REDACTED]", value)


def git(workspace, *arguments):
    result = subprocess.run(["git", *arguments], cwd=workspace, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ReviewError("Git review precondition failed: " + " ".join(arguments[:2]))
    return result.stdout.strip()


def recorded_candidate(state, task_id, family, candidate_commit):
    if family not in FAMILIES or not SHA.fullmatch(candidate_commit):
        raise ReviewError("Invalid candidate family or full commit SHA")
    task = state.get("tasks", {}).get(task_id)
    if not isinstance(task, dict) or task.get("family") != family:
        raise ReviewError("Candidate task/family is absent from the canonical state")
    events = [event for event in state.get("material_events", [])
              if event.get("kind") == "mutation" and event.get("task_id") == task_id]
    event = next((event for event in reversed(events)
                  if event.get("details", {}).get("candidate_commit") == candidate_commit), None)
    if event is None:
        raise ReviewError("No durable mutation event records this candidate for this task")
    details = event.get("details", {})
    branch = details.get("candidate_branch", "")
    if details.get("candidate_scope") != "isolated" or not isinstance(branch, str) or not branch.startswith("autonomy/" + family + "/"):
        raise ReviewError("Recorded candidate is outside its isolated family branch")
    if not re.fullmatch(r"autonomy/[a-z_]+/[A-Za-z0-9_-]+", branch):
        raise ReviewError("Recorded candidate branch is not canonical")
    if not details.get("changed_paths"):
        raise ReviewError("Recorded candidate has no durable changed-file evidence")
    return task, event, events[-1].get("details", {}).get("candidate_commit") == candidate_commit


def validate_checkout(workspace, candidate_commit, branch):
    if git(workspace, "rev-parse", "HEAD") != candidate_commit:
        raise ReviewError("Candidate checkout HEAD differs from the recorded SHA")
    actual_branch = git(workspace, "branch", "--show-current")
    if actual_branch in PRODUCTION_BRANCHES or actual_branch != branch:
        raise ReviewError("Review requires the recorded isolated candidate branch")
    if git(workspace, "status", "--porcelain", "--untracked-files=no"):
        raise ReviewError("Review must begin from a clean tracked candidate checkout")


def project_commands(infrastructure, workspace):
    """Use infrastructure-owned validation planning, never commands from a task."""
    module_path = infrastructure / "scripts/autonomy_recovery.py"
    if module_path.is_file() and not module_path.is_symlink():
        spec = importlib.util.spec_from_file_location("_autonomy_review_gates", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        planner = getattr(module, "project_gates", None) or getattr(module, "project_validation_commands", None)
        if planner:
            commands = planner(workspace)
            if not isinstance(commands, list) or not commands or any(not isinstance(command, list) or not command or any(not isinstance(part, str) for part in command) for command in commands):
                raise ReviewError("Mandatory project gate planner returned invalid commands")
            return commands
    commands = [[sys.executable, "-m", "pytest", "-q"]]
    if (workspace / "package.json").is_file():
        commands.append(["npm", "test"])
    if (workspace / "scripts/product_report.py").is_file():
        required = ("build_statistics_deep_analysis.py", "build_epidemiology_snapshot.py", "export_web_snapshot.py", "export_global_intelligence.py", "product_report.py", "review_candidate.py")
        if any(not (workspace / "scripts" / script).is_file() or (workspace / "scripts" / script).is_symlink() for script in required):
            raise ReviewError("Mandatory staging build/reviewer contract is incomplete")
        commands.extend([
            [sys.executable, "scripts/build_statistics_deep_analysis.py"],
            [sys.executable, "scripts/build_epidemiology_snapshot.py"],
            [sys.executable, "scripts/export_web_snapshot.py", "--input", "data/history/superintendencia_signals.json", "--offline"],
            [sys.executable, "scripts/export_global_intelligence.py"],
            [sys.executable, "scripts/product_report.py"],
            ["npm", "run", "test:browser"],
            [sys.executable, "scripts/review_candidate.py", "--web", "web", "--sha", git(workspace, "rev-parse", "HEAD")],
        ])
    commands.append(["git", "diff", "--check"])
    return commands


def pytest_summary(xml_path):
    cases = list(ET.parse(xml_path).getroot().iter("testcase"))
    passed = sum(case.find("failure") is None and case.find("error") is None and case.find("skipped") is None for case in cases)
    failed = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    return {"collected": len(cases), "passed": passed, "failed": failed, "skipped": skipped, "proof": bool(passed) and not failed}


def canonical_text(value, roots=()):
    value = re.sub(r"\x1b\[[0-9;]*m", "", str(value))
    for root in sorted((str(root) for root in roots), key=len, reverse=True):
        value = value.replace(root, "<workspace>")
    value = re.sub(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b", "<timestamp>", value)
    value = re.sub(r"\bin \d+(?:\.\d+)?s\b", "in <duration>", value)
    value = re.sub(r"(?m)^.*generated xml file:.*$", "<generated-junit-artifact>", value)
    return value


def canonical_command(command):
    return ["--junitxml=<artifact>" if part.startswith("--junitxml=") else
            ("<python>" if index == 0 and re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", Path(part).name) else part)
            for index, part in enumerate(command)]


def semantic_fingerprint(report, roots=()):
    identity = {key: report.get(key) for key in ("task_id", "family", "candidate_commit", "candidate_scope", "status", "technical_review_pass", "next_action")}
    identity["error"] = canonical_text(report.get("error", ""), roots)
    identity["gates"] = [{"command": canonical_command(gate["command"]),
                          "status": gate["status"], "returncode": gate["returncode"],
                          "pytest": gate.get("pytest"), "failure_fingerprint": gate.get("failure_fingerprint")}
                         for gate in report.get("gates", [])]
    return digest(encode(identity))


def completed_review(snapshot, task, candidate_commit):
    metadata = task.get("candidate_reviews", {}).get(candidate_commit) or task.get("candidate_review", {})
    if metadata.get("candidate_commit") != candidate_commit or metadata.get("status") not in {"PASS", "BLOCKED"}:
        return None
    path = metadata.get("evidence_path", "")
    if not isinstance(path, str) or not path.startswith("data/autopilot/evidence/"):
        raise ReviewError("Completed candidate review lacks immutable evidence")
    raw = snapshot.read(path)
    if not isinstance(raw, bytes) or digest(raw) != metadata.get("evidence_sha256"):
        raise ReviewError("Completed candidate review evidence is absent or changed")
    report = json.loads(raw)
    if report.get("task_id") != task["id"] or report.get("candidate_commit") != candidate_commit or report.get("status") != metadata["status"]:
        raise ReviewError("Completed review evidence is not bound to this candidate")
    return metadata, report


def reused_report(metadata, existing, commit):
    report = deepcopy(existing)
    report.update(result_status=existing["status"], status="ALREADY_REVIEWED", state_commit=commit,
                  review_evidence_path=metadata["evidence_path"], superseded=metadata.get("superseded", False))
    return report


def run_gate(command, workspace, directory, ordinal, *, timeout=600):
    """Produce a fresh log/hash; validation receives no paid model credentials."""
    executed = list(command)
    xml_path = directory / (str(ordinal) + "-pytest.xml")
    is_pytest = executed[1:3] == ["-m", "pytest"]
    if is_pytest:
        executed.append("--junitxml=" + str(xml_path))
    environment = dict(os.environ)
    for key in ("OPENAI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        environment.pop(key, None)
    environment.update({"RADAR_ROOT": str(workspace), "PYTHONPATH": str(workspace / "src") + os.pathsep + str(workspace), "PYTHONDONTWRITEBYTECODE": "1"})
    began = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="autonomy-review-cache-") as cache:
            environment["PYTHONPYCACHEPREFIX"] = cache
            result = subprocess.run(executed, cwd=workspace, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        code, output = result.returncode, redact(result.stdout)
    except (OSError, subprocess.TimeoutExpired) as error:
        code, output = 124, "Mandatory review gate unavailable or timed out: " + type(error).__name__
    log_path = directory / (str(ordinal) + "-gate.log")
    log_path.write_text(output, encoding="utf-8")
    gate = {"command": executed, "returncode": code, "status": "PASS" if code == 0 else "FAIL", "log_path": str(log_path), "log_sha256": digest(output), "elapsed_seconds": round(time.monotonic() - began, 3)}
    if is_pytest:
        try:
            counts = pytest_summary(xml_path)
            gate["pytest"] = counts
            if not counts["proof"]:
                gate["status"] = "FAIL" if counts["failed"] or code else "UNVERIFIED"
        except (OSError, ET.ParseError):
            gate["status"] = "UNVERIFIED"
    if gate["status"] != "PASS":
        gate["failure_fingerprint"] = digest(canonical_text(output, (workspace, directory)))
    return gate


def review_candidate(infrastructure, workspace, task_id, family, candidate_commit, report_path, *, store=None, command_planner=project_commands, gate_runner=run_gate):
    infrastructure, workspace, report_path = Path(infrastructure).resolve(), Path(workspace).resolve(), Path(report_path).resolve()
    authority = store or GitStateStore(repository=infrastructure)
    snapshot = authority.read_snapshot()
    initial = snapshot.read_json(STATE, {})
    task, mutation, _latest = recorded_candidate(initial, task_id, family, candidate_commit)
    candidate_branch = mutation["details"]["candidate_branch"]
    validate_checkout(workspace, candidate_commit, candidate_branch)
    completed = completed_review(snapshot, task, candidate_commit)
    if completed:
        report = reused_report(*completed, snapshot.commit)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(encode(report))
        return report
    operation = uuid.uuid4().hex
    directory = report_path.parent / ("review-" + operation)
    directory.mkdir(parents=True, exist_ok=False)
    report = {"operation_id": operation, "kind": "independent_candidate_review", "reviewed_at": now(), "task_id": task_id, "family": family, "candidate_commit": candidate_commit, "candidate_branch": candidate_branch, "candidate_scope": "isolated", "mutation_event_id": mutation.get("id"), "status": "BLOCKED", "technical_review_pass": False, "gates": [], "closure": False, "production_promoted": False}
    try:
        commands = command_planner(infrastructure, workspace)
        for ordinal, command in enumerate(commands):
            gate = gate_runner(command, workspace, directory, ordinal)
            report["gates"].append(gate)
            # A failed prerequisite invalidates dependent build/reviewer output.
            if gate["status"] != "PASS":
                break
        if git(workspace, "rev-parse", "HEAD") != candidate_commit:
            raise ReviewError("Validation altered candidate HEAD")
        report["technical_review_pass"] = bool(report["gates"]) and len(report["gates"]) == len(commands) and all(gate["status"] == "PASS" for gate in report["gates"])
        report["status"] = "PASS" if report["technical_review_pass"] else "BLOCKED"
    except Exception as error:
        report["error"] = redact(str(error)) if isinstance(error, (ReviewError, OSError, ValueError)) else type(error).__name__
    report["next_action"] = ("staging_acceptance_reconciliation" if family == "staging_qa" else "source_acceptance_reconciliation") if report["technical_review_pass"] else "repair_review_failure"
    if not report["technical_review_pass"]:
        failed = [{"command": canonical_command(gate["command"]), "failure_fingerprint": gate.get("failure_fingerprint"),
                   "returncode": gate["returncode"], "status": gate["status"], "pytest": gate.get("pytest")}
                  for gate in report["gates"] if gate["status"] != "PASS"]
        # Stable problem identity; changing review clocks/path cannot create progress.
        identity = {"candidate_commit": candidate_commit, "failed_gates": failed, "error": report.get("error")}
        report["blocker"] = {"kind": "candidate_technical_review", "fingerprint": digest(encode(identity)), "reason": "Independent mandatory candidate gates did not PASS", "evidence": deepcopy(report["gates"]) or [{"error": report.get("error", "No executed mandatory gates")}], "human_required": False}
    report["semantic_fingerprint"] = semantic_fingerprint(report, (workspace, directory))
    evidence_path = "data/autopilot/evidence/" + operation + ".json"
    immutable = encode(report)
    def save(snapshot):
        state = snapshot.read_json(STATE, {})
        task, _recorded, latest = recorded_candidate(state, task_id, family, candidate_commit)
        completed = completed_review(snapshot, task, candidate_commit)
        if completed:
            existing_metadata, existing_report = completed
            return Mutation({}, {"metadata": existing_metadata, "report": existing_report, "already_reviewed": True})
        metadata = {key: deepcopy(report.get(key)) for key in ("candidate_commit", "candidate_branch", "candidate_scope", "status", "technical_review_pass", "reviewed_at", "next_action", "blocker", "semantic_fingerprint")}
        metadata.update(evidence_path=evidence_path, evidence_sha256=digest(immutable), superseded=not latest)
        task.setdefault("candidate_reviews", {})[candidate_commit] = metadata
        if latest:
            task["candidate_review"] = metadata
        return Mutation({STATE: encode(state), evidence_path: immutable}, {"metadata": metadata, "already_reviewed": False})
    transaction = authority.transact(save, message="autonomy: independent " + family + " candidate review")
    if transaction.value["already_reviewed"]:
        report = reused_report(transaction.value["metadata"], transaction.value["report"], transaction.commit)
    else:
        report.update(state_commit=transaction.commit, review_evidence_path=evidence_path, superseded=transaction.value["metadata"]["superseded"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(encode(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--infrastructure", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--family", required=True, choices=sorted(FAMILIES))
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = review_candidate(args.infrastructure, args.workspace, args.task_id, args.family, args.candidate_commit, args.report)
    print(encode({"status": report["status"], "technical_review_pass": report["technical_review_pass"], "candidate_commit": report["candidate_commit"], "state_commit": report["state_commit"], "next_action": report["next_action"]}))


if __name__ == "__main__":
    main()
