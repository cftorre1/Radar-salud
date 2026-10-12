"""A verified complete original can supply missing counters without a new capture."""
import copy
import gzip
import hashlib
from pathlib import Path

import pytest

from radar_salud.pulso_source import _primary_trace, _verified_detail, _project_missing_body_completeness

ROOT = Path(__file__).resolve().parents[1]
def original_cache():
    sha = "7253f5710b63fe99cf1b583195fd56487359958273150186b1caa315779aa503"
    html = gzip.decompress((ROOT / "tests/fixtures/pulso_runtime_real" / (sha + ".html.gz")).read_bytes()).decode()
    assert hashlib.sha256(html.encode()).hexdigest() == sha
    entry = dict(url="https://www.latercera.com/nacional/noticia/siete-de-cada-10-hogares-gastan-mas-de-30-mil-al-mes-en-medicamentos/", listing="captured-original", lastmod="unit-cache-change-token")
    cache = _verified_detail(entry, lambda _: html, None)
    metadata = cache["metadata"]
    assert metadata["article_body_sha256"] == "111d27e3f2b627b2054e8f1f20605141783da19315fad68098cf2d3787cf2049"
    metadata.pop("article_body_characters")
    metadata.pop("article_body_complete", None)
    return entry, cache, html


def test_real_legacy_full_primary_cache_and_trace_recover_only_missing_counters():
    entry, cache, _ = original_cache()
    before = copy.deepcopy(cache)
    assert len(cache["body"]) == 1800 and len(cache["metadata"]["page_text"]) > 1800
    result = _verified_detail(entry, lambda _: pytest.fail("Valid full original cache does not need refetch"), cache)
    assert result["cache_hit"] is True
    for key in ("captured_at", "html_sha256", "article_body_sha256", "publication_date", "publication_timestamp", "page_text"):
        assert result["metadata"][key] == before["metadata"][key]
    assert result["metadata"]["article_body_characters"] == len(cache["metadata"]["page_text"])
    assert result["metadata"]["article_body_complete"] is True
    assert _primary_trace(before["metadata"])["article_body_complete"] is True
    assert _primary_trace(before["metadata"])["article_body_characters"] == len(before["metadata"]["page_text"])
    assert cache == before


@pytest.mark.parametrize("change", ["false", "hash_missing", "hash_wrong", "excerpt", "identity_false", "date_false", "unverified", "wrong_count"])
def test_missing_fields_are_not_filled_from_excerpts_or_unverified_or_explicit_false_proof(change):
    _, cache, _ = original_cache()
    metadata = cache["metadata"]
    if change == "false": metadata["article_body_complete"] = False
    elif change == "hash_missing": metadata.pop("article_body_sha256")
    elif change == "hash_wrong": metadata["article_body_sha256"] = "0" * 64
    elif change == "excerpt": metadata["page_text"] = metadata["page_text"][:1800]
    elif change == "identity_false": metadata["primary_identity_verified"] = False
    elif change == "date_false": metadata["publication_date_verified"] = False
    elif change == "unverified": metadata["article_verified"] = False
    elif change == "wrong_count": metadata["article_body_characters"] = 1800
    before = copy.deepcopy(metadata)
    projected = _project_missing_body_completeness(metadata)
    assert projected.get("article_body_complete") is not True
    assert _primary_trace(metadata)["article_body_complete"] is False
    assert metadata == before
