"""Resume durable repair candidates while retaining current staging authority.

This module never merges, promotes, repairs or closes a task. The queue remains
the source of approval and policy; the state ledger identifies the exact repair
commit to inspect after its independent review has finished.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import hashlib
import json
import re
import subprocess

try:
    from . import autonomy_engine as engine
except ImportError:
    import autonomy_engine as engine


SHA = re.compile(r"^[a-fA-F0-9]{40}$")
REMOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class CandidateContextError(ValueError):
    """The candidate cannot safely be prepared from its recorded authority."""


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _branch_valid(branch, family):
    return (family in engine.FAMILIES and isinstance(branch, str)
            and re.fullmatch(r"autonomy/" + re.escape(family) + r"/[A-Za-z0-9_-]+", branch))


def _base_revision(task):
    previous = task.get("candidate_context") or {}
    declared = previous.get("queue_evidence_revision", task.get("evidence_revision"))
    semantics = {key: task.get(key) for key in (
        "id", "objective", "instructions", "constraints", "depends_on", "evidence",
        "independent_review", "blocked_by", "acceptance_artifact", "input_fingerprint",
        "executor_family", "failure")}
    return _hash({"declared": declared, "semantics": engine._semantic(semantics)})


def overlay_queue(queue, state, *, integrated_candidate_commits=()):
    """Bind an approved task to its latest independently reviewed candidate.

    No blocker or dependency is removed, and no parent is closed. Pending,
    superseded or mismatched reviews cannot select an older candidate. Review
    clocks are omitted from the revision identity. Relevant staging changes are
    exposed in context for ``prepare_workspace`` to block without a merge.
    Only the trusted caller's exact Git ancestry proofs may select current
    staging after integration; queue-authored integration markers are ignored.
    """
    result = deepcopy(queue)
    if not isinstance(result, dict) or not isinstance(result.get("tasks"), list):
        raise CandidateContextError("queue.tasks must be a list")
    tasks = state.get("tasks", {})
    events = state.get("material_events", [])
    integrated_commits = set(integrated_candidate_commits)
    if any(not isinstance(commit, str) or not SHA.fullmatch(commit) for commit in integrated_commits):
        raise CandidateContextError("Integration proofs require full recorded candidate commit SHAs")
    for task in result["tasks"]:
        previous = task.get("candidate_context") or {}
        # Queue-authored context does not substitute for a durable state event.
        task.pop("candidate_context", None)
        if task.get("status") not in engine.APPROVED:
            continue
        family = engine._family(task)
        canonical = tasks.get(task["id"], {})
        if family not in engine.FAMILIES or canonical.get("family") != family:
            continue
        event = next((event for event in reversed(events)
                      if event.get("kind") == "mutation" and event.get("task_id") == task["id"]), None)
        if not event:
            continue
        details = event.get("details", {})
        branch, commit = details.get("candidate_branch"), details.get("candidate_commit")
        if (details.get("candidate_scope") != "isolated" or not _branch_valid(branch, family)
                or not isinstance(commit, str) or not SHA.fullmatch(commit)):
            continue
        review = canonical.get("candidate_review")
        if (not isinstance(review, dict) or review.get("candidate_commit") != commit
                or review.get("status") not in {"PASS", "BLOCKED"} or review.get("superseded")
                or review.get("candidate_branch", branch) != branch
                or review.get("candidate_scope", "isolated") != "isolated"):
            continue
        # Recover the declared revision only for a context made from this event.
        if previous.get("commit") == commit:
            task["candidate_context"] = previous
        base_revision = _base_revision(task)
        task.pop("candidate_context", None)
        declared = previous.get("queue_evidence_revision", task.get("evidence_revision")) if previous.get("commit") == commit else task.get("evidence_revision")
        latest_staging = result.get("input_sha", task.get("input_sha"))
        # Executor updates can permit another repair attempt without changing
        # the candidate's product base. Canonical legacy mutations recorded the
        # product identity in input_fingerprint; newer records keep it separate.
        baseline = details.get("product_input_fingerprint") or details.get("input_fingerprint")
        current = task.get("product_input_fingerprint") or task.get("input_fingerprint")
        parent = details.get("parent_input_sha")
        base_changed = bool(parent and latest_staging and parent != latest_staging)
        integrated = (commit in integrated_commits and isinstance(latest_staging, str)
                      and bool(SHA.fullmatch(latest_staging)))
        rebase_required = not integrated and (not baseline or not current or baseline != current)
        context = {"branch": branch, "commit": commit, "parent_input_sha": parent,
            "current_staging_sha": latest_staging, "baseline_input_fingerprint": baseline,
            "current_input_fingerprint": current, "base_changed": base_changed,
            "rebase_required": rebase_required, "queue_evidence_revision": declared,
            "integrated_into_staging": integrated}
        review_semantics = {key: review.get(key) for key in (
            "candidate_commit", "candidate_branch", "candidate_scope", "status",
            "technical_review_pass", "next_action", "blocker", "semantic_fingerprint", "superseded")}
        task["candidate_context"] = context
        task["input_sha"] = latest_staging if integrated else commit
        revision = {"queue_revision": base_revision, "candidate_commit": commit,
                    "review": engine._semantic(review_semantics)}
        if integrated:
            revision["continuation"] = "post_integration"
        task["evidence_revision"] = _hash(revision)
    return result


def _git(workspace, *args, timeout=30):
    try:
        result = subprocess.run(["git", *args], cwd=workspace, text=True,
                                capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CandidateContextError("Candidate Git operation failed or exceeded its bound") from error
    if result.returncode:
        # Git stderr may include credential-bearing remote URLs; retain command
        # identity without emitting their contents.
        raise CandidateContextError("Candidate Git precondition failed: " + args[0])
    return result.stdout.strip()


def _rebase_blocker(context):
    identity = {key: context.get(key) for key in (
        "parent_input_sha", "current_staging_sha", "baseline_input_fingerprint",
        "current_input_fingerprint")}
    identity["candidate_commit"] = context.get("commit")
    missing = not context.get("baseline_input_fingerprint") or not context.get("current_input_fingerprint")
    return {"kind": "unverifiable_candidate_base" if missing else "candidate_rebase_required",
        "fingerprint": _hash(identity),
        "reason": ("Recorded candidate lacks a verifiable scoped base; explicit revalidation is required."
                   if missing else "Relevant staging inputs changed since candidate was created; explicit rebase/revalidation is required."),
        "evidence": [identity], "human_required": False}


def prepare_workspace(workspace, task, remote="origin"):
    """Fetch and attach the exact recorded candidate, never resetting a branch.

    Dirty tracked files, unsafe authority or a moved remote/local candidate ref
    raise ``CandidateContextError``. A changed/unverifiable relevant base returns
    an evidenced blocker, leaving HEAD and all existing branches untouched.
    """
    workspace = Path(workspace).resolve()
    family = engine._family(task)
    context = task.get("candidate_context")
    if task.get("status") not in engine.APPROVED or task.get("blocked_by"):
        raise CandidateContextError("Candidate task lacks current unblocked queue approval")
    if not isinstance(context, dict):
        raise CandidateContextError("Candidate context is required")
    branch, commit = context.get("branch"), context.get("commit")
    if not _branch_valid(branch, family) or not isinstance(commit, str) or not SHA.fullmatch(commit):
        raise CandidateContextError("Candidate context has an unsafe branch or non-full commit SHA")
    integrated = context.get("integrated_into_staging") is True
    staging = context.get("current_staging_sha")
    expected_input = staging if integrated else commit
    if task.get("input_sha") != expected_input:
        raise CandidateContextError("Task input SHA is not bound to the recorded candidate")
    if not isinstance(remote, str) or not REMOTE.fullmatch(remote):
        raise CandidateContextError("Candidate remote must be a configured remote name")
    if _git(workspace, "status", "--porcelain", "--untracked-files=no"):
        raise CandidateContextError("Candidate checkout has dirty tracked files")
    if integrated:
        # The graph proof is checked again at use time. An authored marker or
        # stale queue snapshot can never silently fall back to old staging or
        # authorize an integration. Keep this current checkout unchanged.
        if not isinstance(staging, str) or not SHA.fullmatch(staging):
            raise CandidateContextError("Integrated candidate lacks a full staging authority SHA")
        if _git(workspace, "rev-parse", "HEAD") != staging:
            raise CandidateContextError("Staging checkout moved since integration was established")
        _git(workspace, "merge-base", "--is-ancestor", commit, staging)
        return {"prepared": True, "input_sha": staging, "candidate_context": deepcopy(context),
                "base_changed": bool(context.get("base_changed")), "rebase_required": False,
                "integrated_into_staging": True, "blocker": None}
    parent = context.get("parent_input_sha")
    if not isinstance(parent, str) or not SHA.fullmatch(parent):
        blocked = {**context, "baseline_input_fingerprint": None}
        return {"prepared": False, "input_sha": None, "candidate_context": deepcopy(context),
                "base_changed": bool(context.get("base_changed")), "rebase_required": True,
                "blocker": _rebase_blocker(blocked)}
    baseline, current = context.get("baseline_input_fingerprint"), context.get("current_input_fingerprint")
    rebase_required = not baseline or not current or baseline != current
    base_changed = bool(context.get("current_staging_sha") and parent != context["current_staging_sha"])
    if rebase_required:
        return {"prepared": False, "input_sha": None, "candidate_context": deepcopy(context),
                "base_changed": base_changed, "rebase_required": True,
                "blocker": _rebase_blocker(context)}
    _git(workspace, "remote", "get-url", remote)
    ref = "refs/heads/" + branch
    advertised = _git(workspace, "ls-remote", "--exit-code", "--refs", remote, ref)
    rows = [row.split() for row in advertised.splitlines()]
    if len(rows) != 1 or rows[0] != [commit, ref]:
        raise CandidateContextError("Recorded candidate branch moved or disappeared")
    scratch_ref = "refs/autonomy/candidate-context/" + _hash([branch, commit])
    _git(workspace, "fetch", "--no-tags", "--depth=1", "--no-write-fetch-head", remote,
         ref + ":" + scratch_ref)
    fetched = _git(workspace, "rev-parse", "--verify", scratch_ref + "^{commit}")
    if fetched != commit:
        raise CandidateContextError("Fetched candidate does not match its recorded full SHA")
    existing = subprocess.run(["git", "show-ref", "--verify", "--quiet", "refs/heads/" + branch],
                              cwd=workspace, text=True, capture_output=True, check=False, timeout=30)
    if existing.returncode == 0:
        if _git(workspace, "rev-parse", "--verify", "refs/heads/" + branch) != commit:
            raise CandidateContextError("Local candidate branch moved; refusing to reset it")
        _git(workspace, "switch", "--no-guess", branch)
    elif existing.returncode == 1:
        _git(workspace, "switch", "--no-guess", "-c", branch, commit)
    else:
        raise CandidateContextError("Cannot establish the local candidate branch state")
    if (_git(workspace, "rev-parse", "HEAD") != commit
            or _git(workspace, "branch", "--show-current") != branch):
        raise CandidateContextError("Prepared checkout differs from the recorded candidate authority")
    return {"prepared": True, "input_sha": commit, "candidate_context": deepcopy(context),
            "base_changed": base_changed, "rebase_required": False, "blocker": None}
