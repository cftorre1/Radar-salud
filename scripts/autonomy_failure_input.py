"""Canonical demonstrated staging failures shared by controller and worker.

The failure identity contains stable failed-test names, never log clocks, runner
wrappers or observation metadata. This helper performs read-only GitHub calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

WORKFLOW = "Alicanto staging preview"
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[a-fA-F0-9]{40}$")
DECISIVE = {"success", "failure", "timed_out"}
FAILURES = {"failure", "timed_out"}


class FailureInputError(ValueError):
    """GitHub evidence is unavailable or outside the staging failure scope."""


def command(arguments):
    try:
        return subprocess.run(arguments, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise FailureInputError("GitHub failure evidence command unavailable: " + type(error).__name__) from error


def github_json(arguments, runner=command):
    result = runner(arguments)
    if result.returncode:
        # Do not expose token-bearing CLI diagnostics in evidence or workflow logs.
        raise FailureInputError("GitHub workflow evidence query failed")
    try:
        return json.loads(result.stdout)
    except (TypeError, ValueError) as error:
        raise FailureInputError("GitHub workflow evidence is not valid JSON") from error


def failed_test_identities(log):
    identities = set()
    text = re.sub(r"\x1b\[[0-9;]*m", "", log)
    for line in text.splitlines():
        # pytest short-summary identities may contain parameter labels/spaces.
        pytest = re.search(r"\b(FAILED|ERROR)\s+((?:tests?/|[A-Za-z0-9_./-]+/tests?/).+)", line)
        if pytest:
            identity = pytest.group(2).split(" - ", 1)[0].strip()
            if re.fullmatch(r"[A-Za-z0-9_./-]+\.py(?:::[^\r\n]+)?", identity):
                identities.add("pytest:" + pytest.group(1).lower() + ":" + identity)
                continue
        playwright = re.search(r"(tests/browser/[A-Za-z0-9_./-]+\.(?:cjs|js|ts)):\d+(?::\d+)?\s*[›>]\s*(.+)", line)
        if playwright and not re.search(r"\b(?:passed|skipped)\b", line, re.I):
            # Source-line movement and browser duration are not a different task.
            title = re.sub(r"\s+\(\d+(?:\.\d+)?(?:ms|s)\)\s*$", "", playwright.group(2)).strip()
            identities.add("playwright:" + playwright.group(1) + "::" + title)
        node = re.search(r"\bnot ok\s+\d+\s+-\s+(.+)$", line)
        if node:
            identities.add("node:" + node.group(1).strip())
    return sorted(identities)


def failure_signature(name, conclusion, log=None):
    identity = {"workflow": name, "conclusion": conclusion,
                "failed_tests": failed_test_identities(log or "")}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def canonical_failure(repository, run, runner=command):
    if not isinstance(run, dict) or run.get("name") != WORKFLOW or run.get("head_branch") != "staging" or run.get("status") != "completed":
        raise FailureInputError("Run must be a completed staging preview on staging")
    run_id = str(run.get("id", ""))
    if not run_id.isdigit() or int(run_id) <= 0:
        raise FailureInputError("Run has no valid positive numeric ID")
    sha = str(run.get("head_sha", ""))
    if not SHA_RE.fullmatch(sha):
        raise FailureInputError("Staging preview has no valid full candidate SHA")
    run_url = "https://github.com/" + repository + "/actions/runs/" + str(int(run_id))
    if run.get("html_url") != run_url:
        raise FailureInputError("Run URL is not bound to the requested repository and run ID")
    conclusion = run.get("conclusion")
    if conclusion not in FAILURES:
        return {"conclusion": None}
    log = None
    try:
        result = runner(["gh", "run", "view", str(int(run_id)), "--repo", repository, "--log-failed"])
        if result.returncode == 0:
            log = result.stdout
    except (FailureInputError, OSError, subprocess.TimeoutExpired):
        # Missing logs cannot erase a demonstrated completed workflow failure.
        pass
    return {"run_id": int(run_id), "run_url": run_url, "head_sha": sha.lower(),
            "conclusion": conclusion, "failure_signature": failure_signature(WORKFLOW, conclusion, log)}


def build_failure_input(repository, run_id=None, *, runner=command):
    if not isinstance(repository, str) or not REPOSITORY_RE.fullmatch(repository):
        raise FailureInputError("Repository must be an owner/name GitHub identifier")
    if run_id is not None:
        if not re.fullmatch(r"[0-9]+", str(run_id)):
            raise FailureInputError("Specified run ID must be numeric")
        if int(run_id) == 0:
            return {"conclusion": None}
        run = github_json(["gh", "api", "repos/" + repository + "/actions/runs/" + str(int(run_id))], runner)
        if not isinstance(run, dict) or str(run.get("id")) != str(int(run_id)):
            raise FailureInputError("GitHub returned a different run ID")
    else:
        response = github_json(["gh", "api", "repos/" + repository + "/actions/runs?branch=staging&per_page=100"], runner)
        if not isinstance(response, dict) or not isinstance(response.get("workflow_runs"), list):
            raise FailureInputError("GitHub workflow collection is invalid")
        # GitHub lists newest first. Cancellations/skips are supersession events,
        # and must not hide the most recent conclusive PASS or failed gate.
        run = next((run for run in response["workflow_runs"] if isinstance(run, dict)
                    and run.get("name") == WORKFLOW and run.get("head_branch") == "staging"
                    and run.get("status") == "completed" and run.get("conclusion") in DECISIVE), None)
        if run is None:
            return {"conclusion": None}
    return canonical_failure(repository, run, runner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    result = build_failure_input(args.repository, args.run_id)
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
