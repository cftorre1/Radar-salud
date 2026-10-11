"""Corpus iteration, exact retained bytes and thin diagnostics without live HTTP."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit_pulso_primary_corpus", ROOT / "scripts/audit_pulso_primary_corpus.py")
corpus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corpus)


def captured_record(folder, url, payload):
    compressed = gzip.compress(payload, mtime=0)
    digest = hashlib.sha256(payload).hexdigest()
    (folder / (digest + ".gz")).write_bytes(compressed)
    return dict(url=url, status=200, content_type="text/html; charset=utf-8", charset="utf-8", bytes=len(payload),
                captured_at="2026-10-11T06:00:00Z", sha256=digest, gzip_sha256=hashlib.sha256(compressed).hexdigest(),
                returned_text_utf8_sha256=digest, gzip_file=digest + ".gz")


def artifact(tmp_path, records, thin_urls=()):
    base = tmp_path / "artifact"
    capture = base / "audits/pulso_runtime_capture"
    capture.mkdir(parents=True, exist_ok=True)
    manifest = capture / "manifest.json"
    manifest.write_text(json.dumps({"source": "pulso_latercera", "mode": "actual_core_http_observation_no_inventory_injection",
                                    "requests": records}))
    discovery = base / "state/discovery_run.json"
    discovery.parent.mkdir(exist_ok=True)
    discovery.write_text(json.dumps({"at": "2026-10-11T06:10:00Z", "source_details": {"pulso_latercera": [
        {"url": url, "status": "detail_error", "reason": "incomplete_article_evidence"} for url in thin_urls]}}))
    return base, capture, manifest, discovery


def synthetic_unit_html(url, title="Nueva clínica amplía red de atención", body=None, section="Nacional"):
    # Synthetic in-memory unit input only; never stored as a durable publisher fixture.
    body = "La clínica amplía su red de hospitales para mejorar la atención de pacientes. " * 80 if body is None else body
    node = {"@type": "NewsArticle", "url": url, "headline": title, "datePublished": "2026-10-09T12:00:00Z",
            "articleBody": body, "articleSection": section}
    return (f'<html><link rel="canonical" href="{url}"><script type="application/ld+json">{json.dumps(node)}</script>'
            '<article><time class="byline-date">9 Octubre 2026</time></article></html>').encode()


def test_all_retained_health_html_are_audited_and_full_bodies_are_not_a_small_sample(tmp_path):
    base, captures, manifest, _ = artifact(tmp_path, [])
    records = []
    for index in range(35):
        url = f"https://www.latercera.com/nacional/noticia/unit-health-{index}/"
        records.append(captured_record(captures, url, synthetic_unit_html(url)))
    manifest.write_text(json.dumps({"source": "pulso_latercera", "mode": "actual_core_http_observation_no_inventory_injection",
                                    "requests": records}))
    report = corpus.audit(base, tmp_path / "report.json", tmp_path / "thin")
    assert report["status"] == "ALL_RETAINED_ORIGINALS_AUDITED_NOT_SOURCE_ACCEPTANCE"
    assert report["counts"]["audited_retained_original_identities"] == 35
    assert report["counts"]["health_unique_urls"] == 35
    assert len(report["all_health_originals_with_full_body"]) == 35
    assert all(row["primary_body_chars"] > 5500 and len(row["full_primary_body"]) == row["primary_body_chars"]
               for row in report["all_health_originals_with_full_body"])
    assert all(row["body_complete_as_original"] for row in report["all_health_originals_with_full_body"])
    assert report["network_requests"] == report["ai_calls"] == 0


def test_real_primary_original_replays_with_full_body_provenance_and_exact_bytes(tmp_path):
    base, captures, manifest, _ = artifact(tmp_path, [])
    fixture = next(row for row in json.loads((ROOT / "tests/fixtures/pulso_real/manifest.json").read_text())["fixtures"]
                   if "senior-housing" in row["url"])
    payload = gzip.decompress((ROOT / fixture["path"]).read_bytes())
    record = captured_record(captures, fixture["url"], payload)
    manifest.write_text(json.dumps({"source": "pulso_latercera", "mode": "actual_core_http_observation_no_inventory_injection",
                                    "requests": [record]}))
    report = corpus.audit(base, tmp_path / "report.json", tmp_path / "thin")
    row = report["all_health_originals_with_full_body"][0]
    assert row["sha256"] == fixture["sha256"]
    assert row["original_capture_manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert row["captured_at"] == record["captured_at"]
    assert row["canonical_matches_requested"]
    assert row["current_parser"]["body_matches_original_projection"]
    assert row["primary_body_sha256"] == hashlib.sha256(row["full_primary_body"].encode()).hexdigest()
    assert "Acalis" in row["full_primary_body"] and "Villa Soleares" in row["full_primary_body"]


def test_all_29_unique_thin_originals_are_retained_without_parser_success_requirement(tmp_path):
    base, captures, manifest, discovery = artifact(tmp_path, [])
    records, urls = [], []
    for index in range(29):
        url = f"https://www.latercera.com/paula/noticia/unit-thin-{index}/"
        urls.append(url)
        records.append(captured_record(captures, url, synthetic_unit_html(url, title="Vivir con TOC")))
    manifest.write_text(json.dumps({"source": "pulso_latercera", "mode": "actual_core_http_observation_no_inventory_injection",
                                    "requests": records}))
    value = json.loads(discovery.read_text())
    value["source_details"]["pulso_latercera"] = [dict(url=url, status="detail_error", reason="incomplete_article_evidence") for url in urls] + [
        dict(url=urls[0], status="detail_error", reason="incomplete_article_evidence")]
    discovery.write_text(json.dumps(value))
    output = tmp_path / "thin"
    report = corpus.audit(base, tmp_path / "report.json", output)
    thin = report["thin_originals"]
    assert thin["expected_unique_incomplete_urls"] == len(thin["requests"]) == 29
    assert thin["status"] == "ALL_COLD_THIN_ORIGINALS_RETAINED_NOT_SOURCE_ACCEPTANCE"
    for row in thin["requests"]:
        assert row["current_parser"]["status"] == "error"
        assert row["primary_document_diagnosis"] == "url_bound_complete_primary_body_rejected_by_short_headline_length_gate"
        assert gzip.decompress((output / row["gzip_file"]).read_bytes()) == synthetic_unit_html(row["url"], title="Vivir con TOC")
        assert row["capture_provenance"] == "preserved_original_cold_core_incomplete_detail"


@pytest.mark.parametrize("field,value,reason", [
    ("gzip_sha256", "0" * 64, "gzip_sha256_mismatch"),
    ("sha256", "0" * 64, "original_bytes_hash_or_size_mismatch"),
    ("gzip_file", "../outside.gz", "unsafe_capture_path"),
])
def test_invalid_original_never_fabricates_full_body_or_thin_fixture(tmp_path, field, value, reason):
    base, captures, manifest, discovery = artifact(tmp_path, [])
    url = "https://www.latercera.com/paula/noticia/unit-thin/"
    record = captured_record(captures, url, synthetic_unit_html(url))
    record[field] = value
    manifest.write_text(json.dumps({"source": "pulso_latercera", "mode": "actual_core_http_observation_no_inventory_injection",
                                    "requests": [record]}))
    d=json.loads(discovery.read_text());d["source_details"]["pulso_latercera"]=[dict(url=url,status="detail_error",reason="incomplete_article_evidence")]
    discovery.write_text(json.dumps(d))
    report = corpus.audit(base, tmp_path / "report.json", tmp_path / "thin")
    assert report["status"] == "PRIMARY_CORPUS_AUDIT_PARTIAL"
    assert report["all_health_originals_with_full_body"] == []
    assert report["original_response_audit"][0]["reason"] == reason
    assert report["thin_originals"]["requests"][0]["fixture_status"] == "missing_hash_verified_original"


def test_original_video_without_article_body_remains_explicit_incomplete_text(tmp_path):
    url = "https://www.latercera.com/videos/noticia/unit-health-video/"
    projection = corpus.primary_projection(synthetic_unit_html(url, body="", section="Videos").decode(), url)
    assert projection["canonical_matches_requested"]
    assert projection["primary_document_diagnosis"] == "publisher_video_route_with_primary_article_text_below_160"
    assert projection["full_primary_body"] == ""
    assert not projection["body_complete_as_original"]
    assert projection["current_parser"]["status"] == "error"


def test_empty_or_metadata_only_corpus_cannot_claim_original_full_body_evidence(tmp_path):
    report = corpus.audit(tmp_path / "missing", tmp_path / "report.json", tmp_path / "thin")
    assert report["status"] == "PRIMARY_CORPUS_AUDIT_PARTIAL"
    assert not report["all_health_originals_with_full_body"]
    assert report["thin_originals"]["status"] == "THIN_ORIGINAL_RETENTION_PARTIAL"
