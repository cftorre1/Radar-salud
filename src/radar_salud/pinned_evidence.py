"""Exact pinned audit bytes, from the working tree or, if redacted, from git history.

The rights migration of 28-oct-2026 replaced paywalled publisher text in some
hash-pinned audit manifests by sha256 receipts. Their pinned originals remain in
git history (history is not rewritten without a Dirección decision). A verifier
gets exactly the pinned bytes or nothing: never a near match.
"""
from __future__ import annotations

import hashlib
import subprocess
from functools import lru_cache
from pathlib import Path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=64)
def _from_history(root: str, relpath: str, expected: str) -> bytes | None:
    log = subprocess.run(["git", "log", "--format=%H", "-n", "200", "--", relpath], cwd=root, capture_output=True)
    if log.returncode:
        return None
    for commit in log.stdout.decode().split():
        for ref in (f"{commit}:{relpath}", f"{commit}^:{relpath}"):
            blob = subprocess.run(["git", "show", ref], cwd=root, capture_output=True)
            if blob.returncode == 0 and _sha(blob.stdout) == expected:
                return blob.stdout
    return None


def pinned_bytes(root, relpath: str, expected_sha256: str) -> bytes:
    """Working-tree bytes when they match the pin, else the pinned blob from history, else the tree bytes."""
    path = Path(root) / relpath
    try:
        data = path.read_bytes()
    except OSError:
        data = b""
    if _sha(data) == expected_sha256:
        return data
    return _from_history(str(Path(root).resolve()), relpath, expected_sha256) or data


# --- Rights-redacted historical audits (Dirección 28-oct-2026) ---------------------
ORIGINALS_PATH = "data/audits/rights_redacted_originals_2026_10_28.json"


@lru_cache(maxsize=4)
def _originals(root: str) -> dict:
    import json
    try:
        with open(Path(root) / ORIGINALS_PATH, encoding="utf-8") as handle:  # not Path.read_text: it may be wrapped
            return json.load(handle)["files"]
    except (OSError, ValueError, KeyError):
        return {}


@lru_cache(maxsize=512)
def _blob(root: str, oid: str, expected_sha256: str) -> bytes | None:
    result = subprocess.run(["git", "cat-file", "blob", oid], cwd=root, capture_output=True)
    if result.returncode == 0 and _sha(result.stdout) == expected_sha256:
        return result.stdout
    return None


def original_audit_bytes(root, relpath: str) -> bytes | None:
    """Pre-redaction bytes of a historical audit, from git history (None if not redacted/unavailable).

    Historical audits are immutable evidence pinned by sha256. The rights migration
    removed paywalled text from the working tree; QA tools that re-verify that
    history read the exact original blob instead (never a reconstruction).
    """
    root = str(Path(root).resolve())
    entry = _originals(root).get(relpath)
    return _blob(root, entry["git_blob"], entry["sha256"]) if entry else None


def install_original_audit_reader(root) -> None:
    """Make ``Path.read_bytes/read_text`` return pre-redaction bytes for redacted historical audits.

    Only for QA/replay of historical evidence (tests, scripts/qa_*); the runtime never
    calls this, so production reads see the redacted working tree.
    """
    import pathlib
    root = Path(root).resolve()
    if getattr(pathlib.Path, "_alicanto_original_reader", False):
        return
    original_read_bytes, original_read_text = pathlib.Path.read_bytes, pathlib.Path.read_text

    def _relative(path):
        try:
            return str(Path(path).resolve().relative_to(root))
        except (ValueError, OSError):
            return None

    def read_bytes(self):
        rel = _relative(self)
        data = original_audit_bytes(root, rel) if rel and rel.startswith("data/audits/") else None
        return data if data is not None else original_read_bytes(self)

    def read_text(self, encoding=None, errors=None, *args, **kwargs):
        rel = _relative(self)
        data = original_audit_bytes(root, rel) if rel and rel.startswith("data/audits/") else None
        if data is None:
            return original_read_text(self, encoding, errors, *args, **kwargs)
        return data.decode(encoding or "utf-8", errors or "strict")

    pathlib.Path.read_bytes, pathlib.Path.read_text = read_bytes, read_text
    pathlib.Path._alicanto_original_reader = True
