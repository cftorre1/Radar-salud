"""Real Git bundle replay without network, and mandatory tamper rejection."""
import base64
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pulso_review_transport", ROOT / "scripts/pulso_review_transport.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


def command(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).stdout.decode().strip()


def repository(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    command(repo, "init", "-b", transport.BRANCH)
    command(repo, "config", "user.name", "Offline transport test")
    command(repo, "config", "user.email", "offline-transport@example.invalid")
    (repo / "baseline.json").write_text('{"baseline":true}\n')
    command(repo, "add", "baseline.json")
    command(repo, "commit", "-m", "base")
    base = command(repo, "rev-parse", "HEAD")
    (repo / "original-evidence.html.gz").write_bytes(bytes(range(256)) * 25)
    command(repo, "add", "original-evidence.html.gz")
    command(repo, "commit", "-m", "tracked evidence")
    # Prove that untracked files and Git configuration are not transported.
    (repo / "untracked-private-input").write_text("unit-only-private-untracked-value")
    command(repo, "config", "transport.privateUnitValue", "unit-only-private-config-value")
    return repo, base, command(repo, "rev-parse", "HEAD")


def receiver(tmp_path, source, base):
    repo = tmp_path / "receiver"
    repo.mkdir()
    command(repo, "init")
    command(repo, "fetch", str(source), base)
    return repo


def rewrite_manifest(directory, mutate):
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    mutate(manifest)
    payload = (json.dumps(manifest, indent=2) + "\n").encode()
    path.write_bytes(payload)
    (directory / "manifest.sha256").write_text(hashlib.sha256(payload).hexdigest() + "  manifest.json\n")


def test_real_incremental_bundle_reconstructs_exact_head_with_existing_base_only(tmp_path):
    source, base, head = repository(tmp_path)
    destination = receiver(tmp_path, source, base)
    chunks = tmp_path / "chunks"
    manifest = transport.create(source, chunks, base, chunk_bytes=128)
    assert manifest["snapshot_commit"] == head and manifest["base_commit"] == base
    assert manifest["chunk_count"] > 1
    assert all(0 < len((chunks / row["file"]).read_bytes()) <= 128 for row in manifest["chunks"])
    bundle = tmp_path / "verified.bundle"
    transport.reassemble(chunks, bundle, destination)
    command(destination, "fetch", str(bundle), "HEAD:refs/heads/review-evidence")
    assert command(destination, "rev-parse", "review-evidence") == head
    assert subprocess.check_output(["git", "-C", str(destination), "show", "review-evidence:original-evidence.html.gz"]) == bytes(range(256)) * 25
    assert "untracked-private-input" not in command(destination, "ls-tree", "--name-only", "review-evidence")
    assert "unit-only-private-config-value" not in (destination / ".git/config").read_text()
    assert manifest["bundle_sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()


def test_chunk_corruption_never_writes_partial_bundle(tmp_path):
    source, base, _ = repository(tmp_path)
    chunks = tmp_path / "chunks"
    manifest = transport.create(source, chunks, base)
    part = chunks / manifest["chunks"][0]["file"]
    data = part.read_bytes()
    part.write_bytes((b"A" if data[:1] != b"A" else b"B") + data[1:])
    target = tmp_path / "bad.bundle"
    with pytest.raises(ValueError, match="chunk_sha256"):
        transport.reassemble(chunks, target)
    assert not target.exists()


def test_manifest_checksum_is_required_before_reassembly(tmp_path):
    source, base, _ = repository(tmp_path)
    chunks = tmp_path / "chunks"
    transport.create(source, chunks, base)
    path = chunks / "manifest.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="manifest_sha256"):
        transport.reassemble(chunks, tmp_path / "bad.bundle")


@pytest.mark.parametrize("unsafe", ["../outside.b64", "/tmp/outside.b64", "bundle.part-00001.b64"])
def test_traversal_and_missing_or_reordered_chunks_are_rejected(tmp_path, unsafe):
    source, base, _ = repository(tmp_path)
    chunks = tmp_path / "chunks"
    transport.create(source, chunks, base)
    rewrite_manifest(chunks, lambda value: value["chunks"][0].update(file=unsafe))
    with pytest.raises(ValueError, match="unsafe_or_out_of_order"):
        transport.reassemble(chunks, tmp_path / "bad.bundle")


def test_final_bundle_hash_and_advertised_snapshot_are_both_verified(tmp_path):
    source, base, _ = repository(tmp_path)
    destination = receiver(tmp_path, source, base)
    chunks = tmp_path / "chunks"
    transport.create(source, chunks, base)
    rewrite_manifest(chunks, lambda value: value.update(bundle_sha256="0" * 64))
    with pytest.raises(ValueError, match="bundle_sha256"):
        transport.reassemble(chunks, tmp_path / "bad.bundle", destination)
    transport.create(source, chunks, base)
    rewrite_manifest(chunks, lambda value: value.update(snapshot_commit="0" * 40))
    with pytest.raises(ValueError, match="advertised_head"):
        transport.reassemble(chunks, tmp_path / "bad.bundle", destination)
    assert not (tmp_path / "bad.bundle").exists()


def test_missing_prerequisite_does_not_publish_an_unverified_bundle(tmp_path):
    source, base, _ = repository(tmp_path)
    empty = tmp_path / "empty-receiver"
    empty.mkdir()
    command(empty, "init")
    chunks = tmp_path / "chunks"
    transport.create(source, chunks, base)
    with pytest.raises(subprocess.CalledProcessError):
        transport.reassemble(chunks, tmp_path / "bad.bundle", empty)
    assert not (tmp_path / "bad.bundle").exists()


def test_creation_rejects_other_branches_and_non_sha_base(tmp_path):
    source, base, _ = repository(tmp_path)
    with pytest.raises(ValueError, match="invalid_base_commit"):
        transport.create(source, tmp_path / "chunks", "HEAD~1")
    command(source, "checkout", "-b", "unrelated")
    with pytest.raises(ValueError, match="exclusive_isolated_branch"):
        transport.create(source, tmp_path / "chunks", base)
