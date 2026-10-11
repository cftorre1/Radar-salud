"""Exact original retention and parser replay, independent of discovery inventory."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from radar_salud.pulso_source import extract_article
from radar_salud.pulso_source import _public_feed_url

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("retain_pulso_runtime_fixtures", ROOT / "scripts/retain_pulso_runtime_fixtures.py")
retain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retain)


def original_capture(tmp_path, date="2026-10-10"):
    # Genuine bytes captured by permitted Actions; never label synthetic HTML an original.
    fixture = next(row for row in json.loads((ROOT / "tests/fixtures/pulso_real/manifest.json").read_text())["fixtures"]
                   if "senior-housing" in row["url"])
    compressed = (ROOT / fixture["path"]).read_bytes()
    payload = gzip.decompress(compressed)
    base = tmp_path / "capture"
    base.mkdir()
    (base / "original.gz").write_bytes(compressed)
    record = dict(url=fixture["url"], status=200, captured_at="2026-10-11T05:00:00Z", charset="utf-8",
                  sha256=hashlib.sha256(payload).hexdigest(), gzip_sha256=hashlib.sha256(compressed).hexdigest(),
                  bytes=len(payload), gzip_file="original.gz")
    manifest = base / "manifest.json"
    manifest.write_text(json.dumps({"source": "pulso_latercera", "requests": [record]}))
    control = tmp_path / "control.json"
    control.write_text(json.dumps({"window_90": {"start": "2026-07-13", "end": "2026-10-10"},
                                  "articles": [{"url": record["url"], "recall_expected": True, "publication_date": date,
                                                "section": "pulso", "topic": "providers_investment"}]}))
    return manifest, control, record, compressed


def test_preserves_verbatim_real_original_hashes_and_replays_primary_parser(tmp_path):
    source, control, record, compressed = original_capture(tmp_path)
    output = tmp_path / "fixtures"
    result = retain.retain(control, source, output)
    assert result["counts"] == {"verified_original": 1}
    assert result["status"] == "ORIGINAL_FIXTURES_AVAILABLE_NOT_SOURCE_ACCEPTANCE"
    fixture = result["fixtures"][0]
    assert (output / fixture["path"]).read_bytes() == compressed
    assert fixture["sha256"] == record["sha256"]
    title, body, metadata = extract_article(gzip.decompress(compressed).decode(), record["url"])
    assert fixture["title"] == title
    assert fixture["publication_date"] == metadata["publication_date"] == "2026-10-10"
    assert fixture["primary_body_chars"] == len(body)
    assert fixture["captured_at"] == record["captured_at"]


@pytest.mark.parametrize("field,bad,reason", [
    ("sha256", "0" * 64, "original_sha256_mismatch"),
    ("gzip_sha256", "0" * 64, "gzip_sha256_mismatch"),
    ("bytes", 1, "original_size_mismatch"),
    ("gzip_file", "../outside.gz", "unsafe_capture_path"),
    ("gzip_file", "/tmp/outside.gz", "unsafe_capture_path"),
])
def test_invalid_hash_or_capture_path_cannot_become_verified_original(tmp_path, field, bad, reason):
    source, control, record, _ = original_capture(tmp_path)
    record[field] = bad
    source.write_text(json.dumps({"source": "pulso_latercera", "requests": [record]}))
    result = retain.retain(control, source, tmp_path / "fixtures")
    assert result["status"] == "ORIGINAL_FIXTURES_PARTIAL"
    assert result["fixtures"][0]["reason"] == reason
    assert not result["requests"]


def test_symlink_cannot_read_original_outside_capture_folder(tmp_path):
    source, control, record, compressed = original_capture(tmp_path)
    outside = tmp_path / "outside.gz"
    outside.write_bytes(compressed)
    (source.parent / "original.gz").unlink()
    (source.parent / "original.gz").symlink_to(outside)
    result = retain.retain(control, source, tmp_path / "fixtures")
    assert result["fixtures"][0]["reason"] == "unsafe_capture_path"


def test_warm_cache_retains_prior_exact_bytes_provenance_and_missing_controls(tmp_path):
    source, control, record, _ = original_capture(tmp_path)
    output = tmp_path / "fixtures"
    first = retain.retain(control, source, output)
    frozen = json.loads(control.read_text())
    frozen["articles"].append(dict(frozen["articles"][0], url="https://www.latercera.com/nacional/noticia/missing/"))
    control.write_text(json.dumps(frozen))
    source.write_text(json.dumps({"source": "pulso_latercera", "requests": []}))
    second = retain.retain(control, source, output)
    assert second["counts"] == {"missing_original_capture": 1, "verified_original": 1}
    assert second["status"] == "ORIGINAL_FIXTURES_PARTIAL"
    kept = next(row for row in second["fixtures"] if row["url"] == record["url"])
    assert kept["captured_at"] == record["captured_at"]
    assert kept["original_capture_manifest_sha256"] == first["fixtures"][0]["original_capture_manifest_sha256"]
    assert second["unique_original_payloads"] == 1


def real_metadata_observations(tmp_path):
    """Caller-unit traces over ALL genuine video bytes; never a discovery seed."""
    source, control, senior, _ = original_capture(tmp_path)
    original_folder = ROOT / "tests/fixtures/pulso_editorial_exception_real"
    original_manifest = json.loads((original_folder / "manifest.json").read_text())
    videos = [row for row in original_manifest["requests"] if row.get("url_bound_video_objects")]
    assert len(videos) >= 44  # Regression must exceed the incidental debug quota.
    records, traces = [senior], []
    for index, witness in enumerate(videos):
        compressed = (original_folder / witness["gzip_file"]).read_bytes()
        payload = gzip.decompress(compressed)
        assert hashlib.sha256(payload).hexdigest() == witness["sha256"]
        assert hashlib.sha256(compressed).hexdigest() == witness["gzip_sha256"]
        text = payload.decode(witness.get("charset") or "utf-8", errors="replace")
        try:
            _, _, metadata = extract_article(text, witness["url"])
        except ValueError as error:
            metadata = getattr(error, "metadata", None)
            assert metadata is not None  # Actual URL-bound editorial exception.
        primary_sha = hashlib.sha256(text.encode()).hexdigest()
        filename = f"real-held-{index}.gz"
        (source.parent / filename).write_bytes(compressed)
        records.append(dict(witness, gzip_file=filename, returned_text_utf8_sha256=primary_sha))
        traces.append(dict(metadata, url=witness["url"], status="discovered_metadata_only", html_sha256=primary_sha))
    source.write_text(json.dumps({"source": "pulso_latercera", "requests": records}))
    discovery = tmp_path / "discovery_run.json"
    discovery.write_text(json.dumps({"at": "2026-10-11T08:00:00Z", "source_details": {"pulso_latercera": traces}}))
    return source, control, discovery, records[1:]


def test_all_real_current_metadata_originals_are_retained_without_debug_quota(tmp_path):
    source, control, discovery, observed = real_metadata_observations(tmp_path)
    output = tmp_path / "fixtures"
    result = retain.retain(control, source, output, max_debug=1, discovery_path=discovery, original_fixture_manifests=[])
    assert result["current_metadata_hold_expected_unique_urls"] == len(observed)
    assert len(result["current_metadata_hold_originals"]) == len(observed)
    assert result["current_metadata_hold_original_status"] == "ALL_CURRENT_METADATA_HOLD_ORIGINALS_RETAINED_NOT_EDITORIAL_ACCEPTANCE"
    for row in result["current_metadata_hold_originals"]:
        original = next(entry for entry in observed if entry["url"] == row["url"])
        assert row["sha256"] == original["sha256"] and row["captured_at"] == original["captured_at"]
        assert (output / row["path"]).read_bytes() == (source.parent / original["gzip_file"]).read_bytes()
        assert row["fixture_status"] == "hash_verified_current_metadata_hold_original"
        assert row["editorial_acceptance"] is False
        request = next(entry for entry in result["requests"] if entry["url"] == row["url"] and entry["sha256"] == row["sha256"])
        assert request["capture_provenance"] == "preserved_original_http_response"
    source.write_text(json.dumps({"source": "pulso_latercera", "requests": []}))
    warm = retain.retain(control, source, output, discovery_path=discovery, original_fixture_manifests=[])
    assert warm["current_metadata_hold_original_status"] == result["current_metadata_hold_original_status"]
    assert {row["url"]: row["captured_at"] for row in warm["current_metadata_hold_originals"]} == {
        row["url"]: row["captured_at"] for row in result["current_metadata_hold_originals"]}


def test_same_url_older_original_cannot_satisfy_changed_current_metadata_primary_sha(tmp_path):
    source, control, discovery, observed = real_metadata_observations(tmp_path)
    snapshot = json.loads(discovery.read_text())
    snapshot["source_details"]["pulso_latercera"] = [dict(snapshot["source_details"]["pulso_latercera"][0], html_sha256="0" * 64)]
    discovery.write_text(json.dumps(snapshot))
    result = retain.retain(control, source, tmp_path / "fixtures", discovery_path=discovery, original_fixture_manifests=[])
    row, = result["current_metadata_hold_originals"]
    assert row["fixture_status"] == "missing_current_metadata_hold_original"
    assert result["current_metadata_hold_original_status"] == "CURRENT_METADATA_HOLD_ORIGINAL_RETENTION_PARTIAL"
    assert not any(entry["url"] == observed[0]["url"] for entry in result["requests"])


def test_original_date_conflict_is_explicit_not_fixture_acceptance(tmp_path):
    source, control, _, _ = original_capture(tmp_path, date="2026-10-09")
    result = retain.retain(control, source, tmp_path / "fixtures")
    assert result["fixtures"][0]["fixture_status"] == "original_date_conflict"
    assert result["fixtures"][0]["publication_date"] == "2026-10-10"
    assert result["fixtures"][0]["expected_publication_date"] == "2026-10-09"
    assert result["status"] == "ORIGINAL_FIXTURES_PARTIAL"


@pytest.mark.parametrize("prefix", ["audits", "data/audits"])
def test_downloaded_artifact_restores_only_selected_raw_originals_not_runtime_state(tmp_path, prefix):
    source, control, record, compressed = original_capture(tmp_path)
    artifact = tmp_path / "artifact"
    capture = artifact / prefix / "pulso_runtime_capture"
    capture.mkdir(parents=True)
    (capture / "manifest.json").write_bytes(source.read_bytes())
    (capture / "original.gz").write_bytes(compressed)
    state = artifact / "state/pending_queue.json"
    state.parent.mkdir()
    state.write_text('{"sentinel":"do not restore"}')
    output = tmp_path / "fixtures"
    result = retain.retain(control, tmp_path / "no-current-manifest.json", output, artifact)
    assert result["counts"] == {"verified_original": 1}
    assert result["fixtures"][0]["sha256"] == record["sha256"]
    assert not (output / "pending_queue.json").exists()
    assert state.read_text() == '{"sentinel":"do not restore"}'


def api_capture_chain(tmp_path, first_publish="2026-07-09T10:00:00Z", inventory_day="2026-07-09"):
    """Synthetic unit input exercises retention; it is never saved as an original fixture."""
    source, control, article, _ = original_capture(tmp_path)
    records, pages = [article], []
    for offset in range(0, 144, 24):
        document = {"content_elements": [{"_id": str(offset), "first_publish_date": first_publish}],
                    "count": 500, "next": offset + 24}
        payload = json.dumps(document).encode()
        compressed = gzip.compress(payload, mtime=0)
        filename = f"api-{offset}.gz"
        (source.parent / filename).write_bytes(compressed)
        records.append(dict(url=_public_feed_url("tag", "salud", offset), status=200,
                            captured_at="2026-10-11T05:00:00Z", charset="utf-8", bytes=len(payload),
                            sha256=hashlib.sha256(payload).hexdigest(), returned_text_utf8_sha256=hashlib.sha256(payload).hexdigest(),
                            gzip_sha256=hashlib.sha256(compressed).hexdigest(), gzip_file=filename))
        pages.append(dict(status="public_feed_page", feed="tag:salud", offset=offset, next=offset+24,
                          primary_entries=1, count=500, json_sha256=records[-1]["sha256"],
                          inventory_day_min=inventory_day, inventory_day_max=inventory_day))
    source.write_text(json.dumps({"source": "pulso_latercera", "requests": records}))
    discovery = tmp_path / "discovery_run.json"
    discovery.write_text(json.dumps({"at": "2026-10-11T06:00:00Z", "source_details": {"pulso_latercera": pages + [
        {"status": "public_feed_coverage", "feed": "tag:salud", "pages_attempted": 6, "coverage_complete": True},
        {"status": "runtime_coverage", "required_feeds": ["tag:salud"], "coverage_complete": True}]}}))
    return source, control, discovery, records, pages


def test_public_api_preserves_exact_first_last_three_and_compact_interior_http_chain(tmp_path):
    source, control, discovery, observed, _ = api_capture_chain(tmp_path)
    output = tmp_path / "fixtures"
    result = retain.retain(control, source, output, discovery_path=discovery)
    proof = result["public_api_proof"]
    assert proof["status"] == "PUBLIC_API_HTTP_AND_BOUNDARY_PROOF_AVAILABLE_NOT_SOURCE_ACCEPTANCE"
    assert proof["discovery_run_sha256"] == hashlib.sha256(discovery.read_bytes()).hexdigest()
    assert proof["feeds"][0]["proof_payload_offsets"] == [0, 72, 96, 120]
    api = [row for row in result["requests"] if retain.api_page_key(row["url"])]
    assert len(api) == 6
    assert {row["offset"] for row in api if row["raw_payload_retained"]} == {0, 72, 96, 120}
    assert {row["offset"] for row in api if row["gzip_file"] is None} == {24, 48}
    for row in api:
        original = next(entry for entry in observed if entry["url"] == row["url"])
        assert row["sha256"] == original["sha256"] and row["captured_at"] == original["captured_at"]
        assert row["original_capture_manifest_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
        if row["gzip_file"]:
            assert (output / row["gzip_file"]).read_bytes() == (source.parent / original["gzip_file"]).read_bytes()
    assert result["unique_original_payloads"] == 5  # Article plus four JSON payloads; interior metadata is not raw retention.


def test_public_api_chain_proof_survives_warm_cache_without_refetch_or_new_capture_times(tmp_path):
    source, control, discovery, _, _ = api_capture_chain(tmp_path)
    output = tmp_path / "fixtures"
    first = retain.retain(control, source, output, discovery_path=discovery)
    source.write_text(json.dumps({"source": "pulso_latercera", "requests": []}))
    second = retain.retain(control, source, output, discovery_path=discovery)
    assert second["public_api_proof"]["http_chain_sha256"] == first["public_api_proof"]["http_chain_sha256"]
    assert second["public_api_proof"]["status"] == first["public_api_proof"]["status"]
    assert second["counts"] == {"verified_original": 1}


def test_midnight_api_inventory_uses_santiago_without_rewriting_original_timestamp_or_primary_date(tmp_path):
    timestamp = "2026-07-10T00:30:00Z"
    source, control, discovery, records, _ = api_capture_chain(tmp_path, first_publish=timestamp,
                                                             inventory_day="2026-07-09")
    output = tmp_path / "fixtures"
    result = retain.retain(control, source, output, discovery_path=discovery)
    proof = result["public_api_proof"]
    assert proof["status"] == "PUBLIC_API_HTTP_AND_BOUNDARY_PROOF_AVAILABLE_NOT_SOURCE_ACCEPTANCE"
    assert proof["inventory_calendar"].startswith("America/Santiago for API")
    for page in proof["feeds"][0]["pages"]:
        if page["raw_payload_required"]:
            assert page["original_first_publish_timestamps"] == [timestamp]
            assert page["original_inventory_days_santiago"] == ["2026-07-09"]
            observed = next(row for row in records if row["url"] == page["http"]["url"])
            assert page["http"]["sha256"] == observed["sha256"]
            assert (output / page["http"]["gzip_file"]).read_bytes() == (source.parent / observed["gzip_file"]).read_bytes()
    assert result["fixtures"][0]["publication_date"] == "2026-10-10"
    assert result["fixtures"][0]["expected_publication_date"] == "2026-10-10"


@pytest.mark.parametrize("failure", ["missing_http", "wrong_cursor", "wrong_boundary_date", "wrong_raw_hash"])
def test_missing_or_inconsistent_original_public_api_proof_is_explicit_partial(tmp_path, failure):
    source, control, discovery, records, pages = api_capture_chain(tmp_path)
    if failure == "missing_http":
        records = [row for row in records if retain.api_page_key(row["url"]) != ("tag:salud", 24)]
    elif failure == "wrong_cursor":
        pages[1]["next"] = 999
    elif failure == "wrong_boundary_date":
        pages[-1]["inventory_day_max"] = "2026-07-10"
    else:
        records[-1]["gzip_sha256"] = "0" * 64
    source.write_text(json.dumps({"source": "pulso_latercera", "requests": records}))
    value = json.loads(discovery.read_text())
    value["source_details"]["pulso_latercera"][:6] = pages
    discovery.write_text(json.dumps(value))
    result = retain.retain(control, source, tmp_path / "fixtures", discovery_path=discovery)
    proof = result["public_api_proof"]
    assert proof["status"] == "PUBLIC_API_PROOF_PARTIAL"
    assert not proof["feeds"][0]["http_and_boundary_proof_complete"]


def test_api_originals_and_source_traces_can_be_read_from_artifact_without_state_restore(tmp_path):
    source, control, discovery, _, _ = api_capture_chain(tmp_path)
    artifact = tmp_path / "artifact"
    captures = artifact / "audits/pulso_runtime_capture"
    captures.mkdir(parents=True)
    for path in source.parent.iterdir():
        (captures / path.name).write_bytes(path.read_bytes())
    snapshot = artifact / "state/discovery_run.json"
    snapshot.parent.mkdir()
    snapshot.write_bytes(discovery.read_bytes())
    result = retain.retain(control, tmp_path / "missing.json", tmp_path / "fixtures", artifact)
    assert result["public_api_proof"]["status"] == "PUBLIC_API_HTTP_AND_BOUNDARY_PROOF_AVAILABLE_NOT_SOURCE_ACCEPTANCE"
    assert snapshot.read_bytes() == discovery.read_bytes()
    assert not (tmp_path / "fixtures/discovery_run.json").exists()


def test_durable_runtime_originals_replay_when_the_permitted_capture_is_available():
    path = ROOT / "tests/fixtures/pulso_runtime_real/manifest.json"
    if not path.exists():
        pytest.skip("Runtime original fixture artifact has not yet been retained; this is not an acceptance PASS")
    manifest = json.loads(path.read_text())
    requests = {(row["url"], row["sha256"]): row for row in manifest["requests"]}
    for fixture in manifest["fixtures"]:
        if fixture["fixture_status"] not in {"verified_original", "original_date_conflict"}:
            continue
        record = requests[(fixture["url"], fixture["sha256"])]
        _, text = retain.verify_original(path.parent, record)
        title, body, metadata = extract_article(text, fixture["url"])
        assert title == fixture["title"]
        assert metadata["publication_date"] == fixture["publication_date"]
        assert len(body) == fixture["primary_body_chars"]


def test_durable_original_api_boundaries_and_http_chain_replay_when_available():
    path = ROOT / "tests/fixtures/pulso_runtime_real/manifest.json"
    if not path.exists():
        pytest.skip("Original runtime API artifact has not yet been retained; this is not an acceptance PASS")
    manifest = json.loads(path.read_text())
    proof = manifest.get("public_api_proof", {})
    if not proof.get("feeds"):
        pytest.skip("Original API pagination proof has not yet been retained")
    chain_bytes = json.dumps([row.get("http") for feed in proof["feeds"] for row in feed["pages"]],
                            sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(chain_bytes).hexdigest() == proof["http_chain_sha256"]
    for feed in proof["feeds"]:
        for page in feed["pages"]:
            if page["proof_status"] != "verified_original_boundary_json":
                continue
            _, text = retain.verify_original(path.parent, page["http"])
            document = json.loads(text)
            document = document.get("data", document)
            assert len(document["content_elements"]) == page["primary_entries"]
            assert document["count"] == page["count"]
            assert document.get("next") == page["next"]
