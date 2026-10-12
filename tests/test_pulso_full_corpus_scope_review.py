"""The complete retained cold corpus is evidence, never source acceptance."""
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN_CONTROL_SHA = "b9c3ce2aea38107797fc19572581f27884d15611214fd2328d458bd35e906374"


@pytest.fixture(scope="module")
def originals_and_review():
    corpus = json.loads((ROOT / "data/audits/pulso_primary_corpus_2026_10_11.json").read_text())
    review = json.loads((ROOT / "data/audits/pulso_full_corpus_scope_review_2026_10_11.json").read_text())
    return corpus, review


def test_full_scope_reader_cannot_turn_retained_corpus_into_acceptance(originals_and_review):
    corpus, review = originals_and_review
    rows = review["all_unique_health_url_matrix"]
    assert review["schema_version"] == "1.0"
    assert review["source"] == "pulso_latercera"
    assert review["verdict"].startswith("INTERIM_NOT_ACCEPTED")
    assert review["acceptance_pass"] is False
    assert review["final_gate_status"] == "NOT_EXECUTED_IN_COLD_RUNTIME"
    assert review["publication_status"] == "NOT_EXECUTED_IN_COLD_RUNTIME"
    assert len(rows) == len({row["url"] for row in rows}) == review["counts"]["unique_health_urls"]
    assert {row["url"] for row in rows} == {row["url"] for row in corpus["all_health_originals_with_full_body"]}
    assert review["projection_consistency_errors"] == []
    assert review["version_conflicts"] == []
    assert len(review["code_sha"]) == 40
    assert all(row["independent_raw_html_recheck"] is False for row in rows)
    assert all(row["final_gate_or_publication_claimed"] is False for row in rows)


def test_every_retained_primary_body_is_rehashed_and_bound_to_the_url_identity(originals_and_review):
    corpus, review = originals_and_review
    matrix = {row["url"]: row for row in review["all_unique_health_url_matrix"]}
    witnesses, latest = [], {}
    for original in corpus["all_health_originals_with_full_body"]:
        body = original["full_primary_body"]
        sha = hashlib.sha256(body.encode()).hexdigest()
        assert sha == original["primary_body_sha256"]
        assert len(body) == original["primary_body_chars"]
        witnesses.append(dict(url=original["url"], original_sha256=original["sha256"],
                              body_sha256=sha, body_chars=len(body)))
        previous = latest.get(original["url"])
        if previous is None or (original.get("captured_at") or "") >= (previous.get("captured_at") or ""):
            latest[original["url"]] = original
    canonical = json.dumps(witnesses, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == review["full_body_projection_witness_sha256"]
    assert len(witnesses) == review["counts"]["full_body_hash_checked_rows"]
    for url, original in latest.items():
        row = matrix[url]
        assert row["original_sha256"] == original["sha256"]
        assert row["body_sha256"] == original["primary_body_sha256"]
        assert row["body_chars"] == original["primary_body_chars"]
        assert row["body_projection_hash_independently_checked"] is True


def test_complete_windows_and_frozen_controls_stay_distinct_from_broad_inventory(originals_and_review):
    _, review = originals_and_review
    control = (ROOT / "data/audits/pulso_external_control_2026_10_11.json").read_bytes()
    assert hashlib.sha256(control).hexdigest() == review["external_control_sha256"] == FROZEN_CONTROL_SHA
    assert review["complete_calendar_windows"] == dict(
        window30=dict(start="2026-09-11", end="2026-10-10"),
        window90=dict(start="2026-07-13", end="2026-10-10"), current_day="2026-10-11")
    groups = Counter(row["window"] for row in review["all_unique_health_url_matrix"])
    assert groups == review["counts"]["by_scope"]
    assert groups["complete_30"] == review["counts"]["windows"]["complete30"]["unique_urls"]
    assert groups["complete_30"] + groups["complete_90_only"] == review["counts"]["windows"]["complete90"]["unique_urls"]
    for days, expected in (("30", 29), ("90", 79)):
        join = review["independent_external_control_corpus_join"][days]
        assert join["expected_independent_frozen_controls"] == expected
        assert len(join["primary_original_rows"]) + len(join["missing_original_controls"]) == expected
        assert join["cold_control_recall"] == join["cold_core_detected"] / expected
    for row in review["unresolved_complete90_date_conflicts"]:
        assert row["publication"]["corroborated"] is False
        assert row["publication"]["verified_day"] is None
    assert review["independent_external_control_corpus_join"]["90"]["without_original_in_retained_corpus"] > 0
