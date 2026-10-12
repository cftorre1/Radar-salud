"""Preserve independent ALL-original proof; passing is not source acceptance."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from pulso_fixture_witnesses import COLD_RECORDS, WITNESSES, assert_cold_witnesses


ROOT = Path(__file__).parents[1]
REPORT = ROOT / "data/audits/pulso_editorial_originals_independent_review_2026_10_11.json"
spec = importlib.util.spec_from_file_location("pulso_independent_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def test_every_retained_editorial_original_is_bound_to_bytes_and_independent_primary_body():
    report = json.loads(REPORT.read_text())
    manifest_path = ROOT / report["manifest_path"]
    manifest = json.loads(manifest_path.read_text())
    # This report binds the cold checkpoint. A subsequent verified recapture
    # can expand the live manifest without rewriting that historical proof.
    assert report["manifest_sha256"] == WITNESSES['cold_manifest_sha256']
    assert_cold_witnesses(manifest['requests'])
    records = COLD_RECORDS
    originals = report["all_originals"]
    assert len(originals) == len(records) == 58
    assert {row["url"] for row in originals} == set(records)
    for row in originals:
        compressed = (ROOT / row["gzip_file"]).read_bytes()
        raw = gzip.decompress(compressed)
        assert sha(compressed) == row["gzip_sha256"] == records[row["url"]]["gzip_sha256"]
        assert sha(raw) == row["capture_sha256"] == records[row["url"]]["sha256"]
        assert len(raw) == row["raw_byte_length"]
        body = row["primary_body_full"]
        assert len(body) == row["primary_body_characters"]
        assert sha(body.encode()) == row["primary_body_sha256"]
        parser = qa.PrimaryDates()
        parser.feed(raw.decode(records[row["url"]].get("charset") or "utf-8"))
        assert parser.canonical == row["url"]
        articles = parser.bound_nodes(row["url"], "NewsArticle")
        if len(articles) == 1 and isinstance(articles[0].get("articleBody"), str) and articles[0]["articleBody"].strip():
            assert body == " ".join(articles[0]["articleBody"].split())
        assert row["raw_sha_independently_verified"] is True
        assert row["gzip_sha_independently_verified"] is True
    assert report["proof_failures"] == []


def test_conflicts_and_videos_remain_editorial_exceptions_and_never_runtime_acceptance():
    report = json.loads(REPORT.read_text())
    originals = report["all_originals"]
    conflicts = [row for row in originals if row["genuine_complete_primary_date_conflict"]]
    videos = [row for row in originals if row["video_route"] and not row["primary_text_at_least160"]]
    assert len(conflicts) == 4
    assert all(row["publication_day_adopted"] is None and row["publication_date_verified"] is False for row in conflicts)
    assert len(videos) == 20
    assert all(row["primary_body_characters"] < 160 for row in videos)
    assert sorted(row["primary_body_characters"] for row in videos) == [0] * 19 + [84]
    assert report["frozen_external_control_sha256"] == qa.FROZEN_CONTROL_SHA256
    assert report["acceptance_pass"] is False
    assert report["checkpoint_is_fresh_runtime_claim"] is False
    assert report["source_runtime_acceptance"] == "PENDING_NEW_REAL_RUNTIME_RECONCILIATION_AND_EDITORIAL_PROCESSING"


def test_all_liveblog_entries_keep_their_own_primary_dates_body_and_identifiers():
    report = json.loads(REPORT.read_text())
    review = report["liveblog_entry_review"]
    parser = qa.PrimaryDates()
    raw = gzip.decompress((ROOT / review["gzip_file"]).read_bytes())
    assert sha(raw) == review["original_sha256"]
    parser.feed(raw.decode())
    nodes = parser.bound_nodes(review["url"], "LiveBlogPosting")
    assert len(nodes) == 1
    updates = nodes[0]["liveBlogUpdate"]
    assert len(updates) == len(review["all_updates"]) == 110
    assert len({row["url"] for row in updates}) == 110
    assert review["proof_failures"] == []
    assert review["acceptance_pass"] is False
    assert review["document_publication_does_not_replace_entry_dates"] is True
    assert {qa.publisher_day(row["datePublished"]) for row in updates} == {"2026-07-21"}
    assert review["all_body_and_updates_read"] is True
