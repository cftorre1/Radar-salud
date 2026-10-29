"""Receipt resolution for synthetic paywalled-press fixtures (Dirección, 28-oct-2026).

The Diario Financiero and La Tercera fixtures under tests/fixtures are synthetic:
titles, URLs and the publisher's public description are kept, while every body and
caption word was replaced by a pseudo-word of the same length (see
tests/fixtures/README.md). Their real-capture provenance is kept as receipts in
tests/fixtures/SYNTHETIC_PAYWALLED_FIXTURES.json:

* ``files``: per fixture, the sha256 of the synthetic bytes and of the original capture.
* ``receipts``: sha256(synthetic value) -> sha256(original value) for every value whose
  original digest is pinned somewhere in the repository (file bytes, decompressed
  pages, parsed primary bodies and titles, canonical JSON objects and strings).

``install()`` makes ``hashlib.sha256`` resolve a registered synthetic digest to the
original capture digest it stands for. Every other digest is returned unchanged, so a
tampered or unknown payload still fails exactly as before; provenance checks therefore
verify "this is the registered synthetic stand-in of capture X". Tests only: the
runtime never imports this module.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent / "fixtures" / "SYNTHETIC_PAYWALLED_FIXTURES.json"
_REAL_SHA256 = hashlib.sha256


def _load() -> dict:
    try:
        with open(REGISTRY, encoding="utf-8") as handle:
            return dict(json.load(handle).get("receipts", {}))
    except (OSError, ValueError):
        return {}


RECEIPTS = _load()


class _Receipted:
    __slots__ = ("_h",)
    name = "sha256"
    digest_size = 32
    block_size = 64

    def __init__(self, h):
        self._h = h

    def update(self, data):
        self._h.update(data)

    def hexdigest(self):
        value = self._h.hexdigest()
        return RECEIPTS.get(value, value)

    def digest(self):
        return bytes.fromhex(self.hexdigest())

    def copy(self):
        return _Receipted(self._h.copy())


def sha256(data=b"", *args, **kwargs):
    return _Receipted(_REAL_SHA256(data, *args, **kwargs))


def real_sha256_hex(data: bytes) -> str:
    """Digest of the bytes themselves, without receipt resolution."""
    return _REAL_SHA256(data).hexdigest()


def install() -> None:
    if RECEIPTS and getattr(hashlib.sha256, "__module__", "") != __name__:
        hashlib.sha256 = sha256
