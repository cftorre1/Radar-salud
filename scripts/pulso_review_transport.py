"""Transport tracked isolated-branch evidence as a verified incremental git bundle.

No network, runtime, queue or AI access. Credentials and .git configuration are
not part of a bundle: it contains only reachable tracked Git objects.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BRANCH = "codex/b-pulso-runtime-20261011"
BASE = "86bfaff25fd22e76348470e374a117379301f06f"
CHUNK_BYTES = 480000
SHA = re.compile(r"[0-9a-f]{40}")
PART = re.compile(r"bundle\.part-[0-9]{5}\.b64")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()


def safe_part(directory, name):
    if not isinstance(name, str) or not PART.fullmatch(name):
        raise ValueError("unsafe_transport_chunk_name")
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("unsafe_transport_chunk_path")
    return path


def split_bundle(bundle, output, base_sha, snapshot_sha, chunk_bytes=CHUNK_BYTES):
    if (not SHA.fullmatch(base_sha) or not SHA.fullmatch(snapshot_sha)
            or not isinstance(chunk_bytes, int) or not 4 <= chunk_bytes <= 500000 or chunk_bytes % 4):
        raise ValueError("invalid_transport_parameters")
    data = bundle.read_bytes()
    encoded = base64.b64encode(data)
    output.mkdir(parents=True, exist_ok=True)
    # Replace transport files only; unrelated scratch documents are preserved.
    for path in output.iterdir():
        if PART.fullmatch(path.name):
            safe_part(output, path.name).unlink()
    chunks = []
    for index, start in enumerate(range(0, len(encoded), chunk_bytes)):
        if index >= 100000:
            raise ValueError("transport_chunk_limit_exceeded")
        name = f"bundle.part-{index:05d}.b64"
        value = encoded[start:start + chunk_bytes]
        safe_part(output, name).write_bytes(value)
        chunks.append({"file": name, "bytes": len(value), "sha256": digest(value)})
    manifest = {"schema_version": 1, "mode": "isolated_branch_tracked_git_objects_review_transport",
                "branch": BRANCH, "created_at": datetime.now(timezone.utc).isoformat(),
                "base_commit": base_sha, "snapshot_commit": snapshot_sha, "bundle_ref": "HEAD",
                "bundle_sha256": digest(data), "bundle_bytes": len(data), "base64_bytes": len(encoded),
                "chunk_bytes_max": chunk_bytes, "chunk_count": len(chunks), "chunks": chunks,
                "scope": "Tracked Git objects only; no environment variables, credentials, git configuration, runtime execution or production mutation.",
                "continuation": "Verify manifest.sha256, reassemble, git bundle verify against the existing base, then fetch HEAD into a review ref. A later transport should use an already recovered base to avoid bundling previous transport chunks."}
    payload = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    (output / "manifest.json").write_bytes(payload)
    (output / "manifest.sha256").write_text(digest(payload) + "  manifest.json\n")
    return manifest


def create(repo, output, base_sha=BASE, chunk_bytes=CHUNK_BYTES):
    if not SHA.fullmatch(base_sha):
        raise ValueError("invalid_base_commit")
    if git(repo, "symbolic-ref", "--short", "HEAD") != BRANCH:
        raise ValueError("transport_requires_exclusive_isolated_branch")
    git(repo, "cat-file", "-e", base_sha + "^{commit}")
    git(repo, "merge-base", "--is-ancestor", base_sha, "HEAD")
    snapshot = git(repo, "rev-parse", "HEAD")
    with tempfile.TemporaryDirectory(prefix="pulso-review-bundle-") as temporary:
        bundle = Path(temporary) / "review.bundle"
        git(repo, "bundle", "create", str(bundle), "HEAD", "^" + base_sha)
        git(repo, "bundle", "verify", str(bundle))
        manifest = split_bundle(bundle, output, base_sha, snapshot, chunk_bytes)
    return manifest


def reassemble(directory, output, verify_repo=None):
    payload = (directory / "manifest.json").read_bytes()
    checksum = (directory / "manifest.sha256").read_text().strip()
    if checksum != digest(payload) + "  manifest.json":
        raise ValueError("transport_manifest_sha256_mismatch")
    manifest = json.loads(payload)
    if (manifest.get("schema_version") != 1 or manifest.get("branch") != BRANCH
            or not SHA.fullmatch(manifest.get("base_commit", ""))
            or not SHA.fullmatch(manifest.get("snapshot_commit", ""))):
        raise ValueError("invalid_transport_manifest")
    chunks = manifest.get("chunks", [])
    if not chunks or len(chunks) != manifest.get("chunk_count"):
        raise ValueError("transport_chunk_count_mismatch")
    values = []
    for index, chunk in enumerate(chunks):
        if chunk.get("file") != f"bundle.part-{index:05d}.b64":
            raise ValueError("unsafe_or_out_of_order_transport_chunk")
        value = safe_part(directory, chunk["file"]).read_bytes()
        if not 0 < len(value) <= 500000 or len(value) != chunk.get("bytes") or digest(value) != chunk.get("sha256"):
            raise ValueError("transport_chunk_sha256_or_size_mismatch")
        values.append(value)
    encoded = b"".join(values)
    if len(encoded) != manifest.get("base64_bytes"):
        raise ValueError("transport_encoded_size_mismatch")
    data = base64.b64decode(encoded, validate=True)
    if len(data) != manifest.get("bundle_bytes") or digest(data) != manifest.get("bundle_sha256"):
        raise ValueError("transport_bundle_sha256_or_size_mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pulso-review-verified-", dir=output.parent) as temporary:
        candidate = Path(temporary) / "verified.bundle"
        candidate.write_bytes(data)
        if verify_repo is not None:
            git(verify_repo, "bundle", "verify", str(candidate.resolve()))
            head = git(verify_repo, "bundle", "list-heads", str(candidate.resolve()), "HEAD").split()
            if head != [manifest["snapshot_commit"], "HEAD"]:
                raise ValueError("transport_advertised_head_mismatch")
        candidate.replace(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--create", action="store_true")
    phase.add_argument("--assemble", type=Path)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("work/pulso-review-transport"))
    parser.add_argument("--base-sha", default=BASE)
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--bundle-out", type=Path, default=Path("work/pulso-review.bundle"))
    parser.add_argument("--verify-repo", type=Path)
    args = parser.parse_args()
    if args.create:
        base = json.loads(args.marker.read_text())["base_sha"] if args.marker else args.base_sha
        manifest = create(args.repo, args.output_dir, base)
    else:
        manifest = reassemble(args.assemble, args.bundle_out, args.verify_repo)
    print(json.dumps({key: manifest[key] for key in ("base_commit", "snapshot_commit", "bundle_sha256", "bundle_bytes", "chunk_count")}))


if __name__ == "__main__":
    main()
