"""Verify and apply selected validated checkpoints on the isolated branch.

Payload: gzip(git format-patch --stdout), ASCII base64 chunks <=400000 bytes.
Manifest fields: branch, expected_source_base_sha, selected_commit_shas,
gzip_bytes/gzip_sha256, patch_bytes/patch_sha256, base64_bytes, and ordered
chunks [{file: patch.part-00000.b64, bytes, sha256}]. manifest.sha256 binds its
exact JSON bytes. This script never fetches, pushes, merges or invokes AI.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

BRANCH = "codex/b-pulso-runtime-20261011"
SHA = re.compile(r"[0-9a-f]{40}")
PART = re.compile(r"patch\.part-[0-9]{5}\.b64")
MAX_PATCH = 64000000


def digest(value):
    return hashlib.sha256(value).hexdigest()


def git(repo, *args, input=None):
    return subprocess.run(["git", "-C", str(repo), *args], input=input, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def allowed_path(value):
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        return False
    if value.startswith("config/") or value.startswith("web/data/"):
        return False
    if value.startswith("data/"):
        return (path.parent == PurePosixPath("data/audits") and path.name.startswith("pulso_")
                and path.suffix == ".json" and not path.name.startswith(("pulso_runtime", "pulso_primary_corpus", "pulso_capture")))
    if value.startswith("tests/fixtures/"):
        return len(path.parts) >= 4 and path.parts[2].startswith("pulso_")
    if path.parent == PurePosixPath("tests"):
        return path.suffix == ".py" and (path.name.startswith("test_pulso") or path.name == "pulso_fixture_witnesses.py")
    if path.parent == PurePosixPath("scripts"):
        return path.suffix == ".py" and path.name.startswith(("pulso_", "audit_pulso", "qa_pulso", "capture_pulso", "retain_pulso"))
    if value in {"src/radar_salud/pulso_source.py", "src/radar_salud/beta_sources.py",
                 "src/radar_salud/pending_queue.py", "src/radar_salud/engine_cli.py"}:
        return True
    return ((path.parent == PurePosixPath(".github/workflows") and path.name.startswith("pulso-") and path.suffix == ".yml")
            or (path.parent == PurePosixPath(".github") and path.name.startswith("run-pulso-") and path.name.endswith("-now")))


def protected_path(value):
    return (value.startswith("config/") or value.startswith("web/data/")
            or (value.startswith("data/") and not allowed_path(value))
            or value in {"src/radar_salud/editorial_gate.py", "src/radar_salud/llm_analysis.py", "src/radar_salud/model_routing.py"})


def protected_snapshot(repo):
    paths = {value.decode() for value in git(repo, "ls-files", "-z").split(b"\0") if value}
    # Include new untracked runtime/ledger files as well as checked-in state.
    for folder in ("config", "data", "web/data"):
        base = repo / folder
        if base.exists():
            paths.update(str(path.relative_to(repo)) for path in base.rglob("*") if path.is_file())
    return {value: digest((repo / value).read_bytes()) if (repo / value).is_file() else None
            for value in sorted(paths) if protected_path(value)}


def decode_payload(directory):
    payload = (directory / "manifest.json").read_bytes()
    if (directory / "manifest.sha256").read_text().strip() != digest(payload) + "  manifest.json":
        raise ValueError("checkpoint_manifest_sha256_mismatch")
    manifest = json.loads(payload)
    commits = manifest.get("selected_commit_shas", [])
    if (manifest.get("branch") != BRANCH or not SHA.fullmatch(manifest.get("expected_source_base_sha", ""))
            or not commits or len(commits) != len(set(commits)) or any(not SHA.fullmatch(value) for value in commits)
            or not isinstance(manifest.get("patch_bytes"), int) or not 0 < manifest["patch_bytes"] <= MAX_PATCH):
        raise ValueError("invalid_checkpoint_manifest")
    chunks = manifest.get("chunks", [])
    if not chunks or len(chunks) > 1000:
        raise ValueError("invalid_checkpoint_chunk_count")
    encoded = []
    for index, record in enumerate(chunks):
        name = record.get("file", "")
        if not PART.fullmatch(name) or name != f"patch.part-{index:05d}.b64":
            raise ValueError("unsafe_or_unordered_checkpoint_chunk")
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("unsafe_checkpoint_chunk_path")
        value = path.read_bytes()
        if not 0 < len(value) <= 400000 or len(value) != record.get("bytes") or digest(value) != record.get("sha256"):
            raise ValueError("checkpoint_chunk_hash_or_size_mismatch")
        encoded.append(value)
    encoded = b"".join(encoded)
    if len(encoded) != manifest.get("base64_bytes"):
        raise ValueError("checkpoint_encoded_size_mismatch")
    compressed = base64.b64decode(encoded, validate=True)
    if len(compressed) != manifest.get("gzip_bytes") or digest(compressed) != manifest.get("gzip_sha256"):
        raise ValueError("checkpoint_gzip_hash_or_size_mismatch")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        patch = stream.read(manifest["patch_bytes"] + 1)
    if len(patch) != manifest["patch_bytes"] or digest(patch) != manifest.get("patch_sha256"):
        raise ValueError("checkpoint_patch_hash_or_size_mismatch")
    selected = re.findall(rb"^From ([0-9a-f]{40}) Mon Sep 17 00:00:00 2001$", patch, flags=re.M)
    if [value.decode() for value in selected] != commits:
        raise ValueError("checkpoint_selected_commit_order_mismatch")
    if re.search(rb"^(?:new file mode|new mode|old mode) (?:120000|160000)$", patch, flags=re.M):
        raise ValueError("checkpoint_symlinks_or_submodules_not_allowed")
    return manifest, patch


def patch_paths(repo, patch):
    records = git(repo, "apply", "--numstat", "-z", input=patch).split(b"\0")
    paths, index = set(), 0
    while index < len(records) and records[index]:
        record = records[index].split(b"\t", 2)
        if len(record) != 3:
            raise ValueError("invalid_checkpoint_numstat")
        index += 1
        names = [record[2]]
        if not record[2]:
            names, index = records[index:index + 2], index + 2
        for name in names:
            value = name.decode("utf-8")
            if not allowed_path(value):
                raise ValueError("checkpoint_path_not_allowed:" + value)
            paths.add(value)
    if not paths:
        raise ValueError("checkpoint_has_no_allowed_changes")
    return sorted(paths)


def apply_payload(repo, directory, result_path, baseline_path):
    manifest, patch = decode_payload(directory)
    if git(repo, "symbolic-ref", "--short", "HEAD").decode().strip() != BRANCH:
        raise ValueError("checkpoint_requires_exclusive_isolated_branch")
    git(repo, "merge-base", "--is-ancestor", manifest["expected_source_base_sha"], "HEAD")
    paths = patch_paths(repo, patch)
    before = git(repo, "rev-parse", "HEAD").decode().strip()
    preserved = protected_snapshot(repo)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(preserved, indent=2) + "\n")
    patch_path = baseline_path.parent / "verified-checkpoints.patch"
    patch_path.write_bytes(patch)
    git(repo, "am", "--3way", "--no-gpg-sign", str(patch_path.resolve()))
    if protected_snapshot(repo) != preserved:
        raise ValueError("checkpoint_changed_protected_runtime_config_or_budgets")
    applied = git(repo, "rev-list", "--reverse", before + "..HEAD").decode().splitlines()
    if len(applied) != len(manifest["selected_commit_shas"]):
        raise ValueError("checkpoint_applied_commit_count_mismatch")
    result = {"mode": "isolated_selected_checkpoint_apply_no_runtime_or_ai", "base_before_apply": before,
              "head_after_apply": git(repo, "rev-parse", "HEAD").decode().strip(),
              "expected_source_base_sha": manifest["expected_source_base_sha"],
              "patch_sha256": manifest["patch_sha256"], "protected_hashes_unchanged": True,
              "changed_paths": paths, "commit_map": dict(zip(manifest["selected_commit_shas"], applied)),
              "tests": "REQUIRED_AFTER_ALL_PATCHES_BEFORE_PUSH"}
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--apply", type=Path)
    phase.add_argument("--check-baseline", type=Path)
    phase.add_argument("--check-protected-ref")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--result", type=Path, default=Path("work/pulso-checkpoint-apply/result.json"))
    parser.add_argument("--baseline", type=Path, default=Path(".scratch/pulso-checkpoint-apply/protected-baseline.json"))
    args = parser.parse_args()
    if args.apply:
        result = apply_payload(args.repo, args.apply, args.result, args.baseline)
        print(json.dumps({"head_after_apply": result["head_after_apply"], "applied_commits": len(result["commit_map"])}))
    elif args.check_baseline:
        if protected_snapshot(args.repo) != json.loads(args.check_baseline.read_text()):
            raise SystemExit("Tests changed protected runtime/config/budget state")
    else:
        changes = git(args.repo, "diff", "--name-only", args.check_protected_ref, "HEAD").decode().splitlines()
        if any(protected_path(value) for value in changes):
            raise SystemExit("Rebase changed protected current upstream runtime/config/budget state")


if __name__ == "__main__":
    main()
