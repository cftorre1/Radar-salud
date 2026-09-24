"""Create missing auxiliary branches only from a verified production main commit."""
import json
import os
import subprocess


def is_accepted_main(sha, payload):
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
        return False
    return any(run.get("head_sha") == sha and run.get("conclusion") == "success"
               and run.get("head_branch") == "main"
               for run in payload.get("workflow_runs", []))


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def ensure_branches():
    branches = ("production-stable", "autopilot-state")
    presence = {}
    for branch in branches:
        status = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", "origin", branch],
                                stdout=subprocess.DEVNULL, check=False).returncode
        if status not in (0, 2):
            raise RuntimeError(f"Unable to check remote branch: {branch}")
        presence[branch] = status == 0
    # An isolation-only main commit need not itself be deployed to keep using
    # the existing, previously accepted production backup and state branches.
    if all(presence.values()):
        return

    main_sha = command("git", "rev-parse", "origin/main")
    repo = os.environ["GITHUB_REPOSITORY"]
    runs = json.loads(command("gh", "api", f"repos/{repo}/actions/workflows/static.yml/runs?branch=main&status=success&per_page=30"))
    if not is_accepted_main(main_sha, runs):
        raise RuntimeError("Current main is not a successfully deployed production commit")
    for branch in branches:
        if presence[branch]:
            continue
        # Fetch once more to refuse creation if production changed during setup.
        command("git", "fetch", "origin", "main")
        if command("git", "rev-parse", "FETCH_HEAD") != main_sha:
            raise RuntimeError("main moved while preparing branches")
        command("git", "push", "origin", f"{main_sha}:refs/heads/{branch}")


if __name__ == "__main__":
    ensure_branches()
