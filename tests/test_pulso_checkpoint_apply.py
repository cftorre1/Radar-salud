"""Offline real git-am replay and fail-closed payload/path/state validation."""
import base64
import gzip
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pulso_checkpoint_apply", ROOT / "scripts/pulso_checkpoint_apply.py")
checkpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoint)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def init(repo):
    repo.mkdir()
    git(repo, "init", "-b", checkpoint.BRANCH)
    git(repo, "config", "user.name", "Offline checkpoint test")
    git(repo, "config", "user.email", "offline@example.invalid")


def write(repo, name, value):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def commit(repo, message):
    git(repo, "add", ".")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").decode().strip()


def stack(tmp_path, changed="src/radar_salud/pulso_source.py"):
    source = tmp_path / "source"
    init(source)
    write(source, "config/orchestrator_queue.json", '{"tasks":[{"id":"other","state":"pending"}]}\n')
    write(source, "config/sources.json", '{"source":"preserve"}\n')
    write(source, "data/state/pending_queue.json", '{"published":"preserve"}\n')
    write(source, "data/ai_usage/month.json", '{"successful":31}\n')
    write(source, "src/radar_salud/pulso_source.py", "baseline = True\n")
    base = commit(source, "base with actual runtime state")
    write(source, changed, "validated_repair = True\n")
    selected = commit(source, "validated selected repair")
    receiver = tmp_path / "receiver"
    init(receiver)
    git(receiver, "fetch", str(source), base)
    git(receiver, "reset", "--hard", "FETCH_HEAD")
    # Upstream changed independently after the code-compatible expected base.
    write(receiver, "config/orchestrator_queue.json", '{"tasks":[{"id":"other","state":"reviewed"}]}\n')
    commit(receiver, "preserve another task advanced independently")
    patch = git(source, "format-patch", "--stdout", "-1", selected)
    folder = tmp_path / "payload"
    folder.mkdir()
    compressed = gzip.compress(patch, mtime=0)
    encoded = base64.b64encode(compressed)
    chunks = []
    for index, start in enumerate(range(0, len(encoded), 128)):
        name = f"patch.part-{index:05d}.b64"
        value = encoded[start:start + 128]
        (folder / name).write_bytes(value)
        chunks.append(dict(file=name, bytes=len(value), sha256=hashlib.sha256(value).hexdigest()))
    manifest = dict(branch=checkpoint.BRANCH, expected_source_base_sha=base, selected_commit_shas=[selected],
                    gzip_bytes=len(compressed), gzip_sha256=hashlib.sha256(compressed).hexdigest(),
                    patch_bytes=len(patch), patch_sha256=hashlib.sha256(patch).hexdigest(), base64_bytes=len(encoded), chunks=chunks)
    save_manifest(folder, manifest)
    return receiver, folder, manifest, patch


def save_manifest(folder, manifest):
    payload = (json.dumps(manifest, indent=2) + "\n").encode()
    (folder / "manifest.json").write_bytes(payload)
    (folder / "manifest.sha256").write_text(hashlib.sha256(payload).hexdigest() + "  manifest.json\n")


def test_real_selected_patch_applies_and_preserves_newer_other_queue_state_and_paid_ledger(tmp_path):
    repo, payload, manifest, _ = stack(tmp_path)
    before = checkpoint.protected_snapshot(repo)
    result = checkpoint.apply_payload(repo, payload, tmp_path / "result.json", tmp_path / "scratch/baseline.json")
    assert result["protected_hashes_unchanged"]
    assert checkpoint.protected_snapshot(repo) == before
    assert json.loads((repo / "config/orchestrator_queue.json").read_text())["tasks"][0]["state"] == "reviewed"
    assert json.loads((repo / "data/ai_usage/month.json").read_text())["successful"] == 31
    assert (repo / "src/radar_salud/pulso_source.py").read_text() == "validated_repair = True\n"
    applied = result["commit_map"][manifest["selected_commit_shas"][0]]
    assert applied == git(repo, "rev-parse", "HEAD").decode().strip()


def test_multiple_selected_checkpoints_keep_commit_order_and_individual_commits(tmp_path):
    repo, payload, manifest, _ = stack(tmp_path)
    source = tmp_path / "source"
    write(source, "src/radar_salud/pulso_source.py", "validated_repair = True\nsecond_validated_repair = True\n")
    second = commit(source, "second validated selected repair")
    patch = git(source, "format-patch", "--stdout", "-2", "HEAD")
    compressed = gzip.compress(patch, mtime=0)
    encoded = base64.b64encode(compressed)
    name = "patch.part-00000.b64"
    (payload / name).write_bytes(encoded)
    manifest.update(selected_commit_shas=manifest["selected_commit_shas"] + [second],
        gzip_bytes=len(compressed), gzip_sha256=hashlib.sha256(compressed).hexdigest(),
        patch_bytes=len(patch), patch_sha256=hashlib.sha256(patch).hexdigest(), base64_bytes=len(encoded),
        chunks=[dict(file=name, bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest())])
    save_manifest(payload, manifest)
    result = checkpoint.apply_payload(repo, payload, tmp_path / "result.json", tmp_path / "scratch/baseline.json")
    assert list(result["commit_map"]) == manifest["selected_commit_shas"]
    assert len(result["commit_map"]) == 2
    subjects = git(repo, "log", "-2", "--reverse", "--format=%s").decode().splitlines()
    assert subjects == ["validated selected repair", "second validated selected repair"]


@pytest.mark.parametrize("path", ["config/orchestrator_queue.json", "data/state/pulso_discovery_cache.json",
    "data/history/superintendencia_signals.json", "data/ai_usage/month.json", "web/data/radar_today.json",
    "data/audits/pulso_primary_corpus_union_2026_10_11.json", "src/radar_salud/llm_analysis.py"])
def test_protected_patch_paths_fail_before_any_git_am_or_state_mutation(tmp_path, path):
    repo, payload, _, _ = stack(tmp_path, changed=path)
    before = git(repo, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="path_not_allowed"):
        checkpoint.apply_payload(repo, payload, tmp_path / "result.json", tmp_path / "scratch/baseline.json")
    assert git(repo, "rev-parse", "HEAD") == before
    assert not (tmp_path / "result.json").exists()


def test_corrupt_chunk_and_unsafe_name_fail_before_decoding_patch(tmp_path):
    _, payload, manifest, _ = stack(tmp_path)
    manifest["chunks"][0]["file"] = "../outside.b64"
    save_manifest(payload, manifest)
    with pytest.raises(ValueError, match="unsafe_or_unordered"):
        checkpoint.decode_payload(payload)
    manifest["chunks"][0]["file"] = "patch.part-00000.b64"
    save_manifest(payload, manifest)
    (payload / "patch.part-00000.b64").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="chunk_hash_or_size"):
        checkpoint.decode_payload(payload)


def test_selected_commit_and_uncompressed_patch_sha_are_mandatory(tmp_path):
    _, payload, manifest, _ = stack(tmp_path)
    manifest["selected_commit_shas"] = ["0" * 40]
    save_manifest(payload, manifest)
    with pytest.raises(ValueError, match="selected_commit_order"):
        checkpoint.decode_payload(payload)
    manifest["patch_sha256"] = "0" * 64
    save_manifest(payload, manifest)
    with pytest.raises(ValueError, match="patch_hash_or_size"):
        checkpoint.decode_payload(payload)


def test_wrong_branch_or_unavailable_expected_base_never_applies(tmp_path):
    repo, payload, manifest, _ = stack(tmp_path)
    manifest["expected_source_base_sha"] = "0" * 40
    save_manifest(payload, manifest)
    with pytest.raises(subprocess.CalledProcessError):
        checkpoint.apply_payload(repo, payload, tmp_path / "result.json", tmp_path / "scratch/baseline.json")
    git(repo, "checkout", "-b", "unrelated")
    with pytest.raises(ValueError, match="exclusive_isolated"):
        checkpoint.apply_payload(repo, payload, tmp_path / "result.json", tmp_path / "scratch/baseline.json")
