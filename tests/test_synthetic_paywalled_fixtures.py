"""Paywalled-press fixtures are synthetic (Dirección, 28-oct-2026).

Diario Financiero and La Tercera (Pulso, PM, LT Board and metered sections)
are treated as paywalled. Their test fixtures keep the publisher's HTML/JSON
structure but every title, lead and body word was replaced by filler, so the
public repository no longer carries their article text. This guard keeps it
that way: a fixture that mentions a paywalled host must be a registered
synthetic file with the exact pinned bytes, and, when the redaction
fingerprints are available, no fixture may contain a fingerprinted sentence.
"""
import gzip
import hashlib
import html
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"
REGISTRY_PATH = FIXTURES / "SYNTHETIC_PAYWALLED_FIXTURES.json"
README_PATH = FIXTURES / "README.md"
REGISTRY = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
DEFAULT_HOSTS = ("df.cl", "latercera.com")
_SPLIT = re.compile(r"(?<=[.!?;:»\"])\s+|\n+")


def paywalled_hosts():
    policy = ROOT / "config/paywalled_press.json"
    if not policy.exists():
        return DEFAULT_HOSTS
    hosts = {host.removeprefix("www.") for rule in json.loads(policy.read_text(encoding="utf-8"))["sources"]
             for host in rule["hosts"]}
    return tuple(sorted(hosts | set(DEFAULT_HOSTS)))


HOST_RE = re.compile(r"(?<![\w-])(?:www\.)?(?:" + "|".join(re.escape(h) for h in paywalled_hosts()) + r")(?![\w-])", re.I)


def _text(path):
    raw = path.read_bytes()
    if path.name.endswith(".gz"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def _fixture_files():
    return sorted(p for p in FIXTURES.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p not in (REGISTRY_PATH, README_PATH))


def _sha256(path):
    from synthetic_receipts import real_sha256_hex
    return real_sha256_hex(path.read_bytes())


def test_registry_declares_synthetic_content_and_readme_explains_it():
    assert REGISTRY["synthetic"] is True
    assert REGISTRY["marker"] == "[Sintético]"
    assert REGISTRY["decided_at"] == "2026-10-28"
    readme = README_PATH.read_text(encoding="utf-8")
    assert "[Sintético]" in readme and "SYNTHETIC_PAYWALLED_FIXTURES.json" in readme


def test_registered_synthetic_fixtures_exist_with_pinned_bytes():
    for rel, entry in REGISTRY["files"].items():
        path = FIXTURES / rel
        assert path.is_file(), rel
        assert _sha256(path) == entry["synthetic_sha256"], f"{rel}: bytes changed; regenerate synthetic content"
        assert path.stat().st_size == entry["bytes"]
        # Receipt: the synthetic bytes resolve to the original capture digest, never to themselves.
        assert entry["original_sha256"] != entry["synthetic_sha256"]
        assert REGISTRY["receipts"][entry["synthetic_sha256"]] == entry["original_sha256"]


def test_receipts_only_map_synthetic_to_distinct_original_digests():
    receipts = REGISTRY["receipts"]
    hexd = re.compile(r"[0-9a-f]{64}")
    assert receipts and all(hexd.fullmatch(k) and hexd.fullmatch(v) and k != v for k, v in receipts.items())
    # No original digest is itself a synthetic key (no chains).
    assert not set(receipts.values()) & set(receipts)


def test_receipt_resolution_is_installed_and_leaves_unknown_payloads_alone():
    entry = next(iter(REGISTRY["files"].values()))
    import synthetic_receipts
    path = next(FIXTURES / rel for rel, e in REGISTRY["files"].items() if e is entry)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["original_sha256"]
    tampered = path.read_bytes() + b"x"
    assert hashlib.sha256(tampered).hexdigest() == synthetic_receipts.real_sha256_hex(tampered)


def test_every_fixture_mentioning_paywalled_press_is_a_registered_synthetic_file():
    allowed = set(REGISTRY["files"]) | set(REGISTRY["no_article_text"])
    offenders = []
    for path in _fixture_files():
        rel = path.relative_to(FIXTURES).as_posix()
        if rel in allowed:
            continue
        if HOST_RE.search(_text(path)):
            offenders.append(rel)
    assert not offenders, f"Paywalled-press fixtures must be synthetic and registered: {offenders[:10]}"


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _visible_strings(path):
    text = _text(path)
    if ".json" in path.name:
        try:
            yield from _strings(json.loads(text))
            return
        except ValueError:
            pass
    for script in re.findall(r"<script[^>]*ld\+json[^>]*>(.*?)</script>", text, re.S | re.I):
        try:
            yield from _strings(json.loads(script))
        except ValueError:
            pass
    for _ in range(2):  # feeds carry entity-escaped HTML inside <description>
        text = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", "\n", text, flags=re.S | re.I)
        text = html.unescape(re.sub(r"<[^>]+>", "\n", text))
    yield text


def _segments(text):
    for part in _SPLIT.split(text):
        part = " ".join(part.split()).casefold()
        if len(part) >= 60:
            yield hashlib.sha256(part.encode("utf-8")).hexdigest()[:20]


def test_no_registered_fixture_contains_a_fingerprinted_paywalled_sentence():
    sources = sorted((ROOT / "data/audits").glob("paywalled_body_fingerprints_*.json"))
    if not sources:
        pytest.skip("paywalled body fingerprints not in this checkout (added with the source-rights migration)")
    fingerprints = set()
    for source in sources:
        fingerprints |= set(json.loads(source.read_text(encoding="utf-8"))["segment_sha256_prefix20"])
    hits = []
    for rel in REGISTRY["files"]:
        for text in _visible_strings(FIXTURES / rel):
            if any(segment in fingerprints for segment in _segments(text)):
                hits.append(rel)
                break
    assert not hits, f"Fixtures still carry paywalled sentences: {hits[:10]}"
