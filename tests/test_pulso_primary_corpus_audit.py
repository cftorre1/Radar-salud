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
        records.append(captured_record(captures, url, synthetic_unit_html(url, title="Vivir con TOC", body="La clínica recibe pacientes.")))
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
        assert row["primary_document_diagnosis"] == "url_bound_primary_article_text_below_160"
        assert gzip.decompress((output / row["gzip_file"]).read_bytes()) == synthetic_unit_html(row["url"], title="Vivir con TOC", body="La clínica recibe pacientes.")
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


def test_editorial_exception_selection_uses_exact_publisher_taxonomy_and_observed_dates():
    base = dict(visible_byline_day="2026-10-09", canonical_matches_requested=True, url_bound_article_nodes=1,
                health_related_original=True, current_parser={"status": "verified"}, keywords=[], section="Nacional")
    window = {"start": "2026-07-13", "end": "2026-10-10"}
    assert corpus.exceptional_categories(dict(base, title="Una opinión sobre salud"), window) == []
    assert corpus.exceptional_categories(dict(base, keywords=["Opinión"]), window) == ["explicit_opinion_or_column_keyword_under_article_path"]
    assert corpus.exceptional_categories(dict(base, keywords=["Columna"]), window) == ["explicit_opinion_or_column_keyword_under_article_path"]
    assert corpus.exceptional_categories(dict(base, section="Branded"), window) == ["explicit_commercial_publisher_section"]
    assert corpus.exceptional_categories(dict(base, section="Publirreportajes", current_parser={"status": "error", "reason": "conflicting_publication_dates"}), window) == [
        "observed_primary_publication_date_conflict", "explicit_commercial_publisher_section"]
    assert corpus.exceptional_categories(dict(base, section="Branded", visible_byline_day="2026-07-12"), window) == []
    assert corpus.exceptional_categories(dict(base, section="Branded", canonical_matches_requested=False), window) == []
    assert corpus.exceptional_categories(dict(base, publication_evidence=[{"timestamp": "2026-09-01T12:00:00Z"}]), window) == [
        "observed_primary_publication_date_conflict"]
    assert corpus.exceptional_categories(dict(base, publication_evidence=[{"timestamp": "2026-10-09T00:30:00Z"}]), window) == []
    assert corpus.exceptional_categories(dict(base, health_related_original=False,
        current_parser={"status": "verified", "metadata": {"publisher_exception_reason": "publisher_conflicting_publication_dates"}}), window) == [
        "observed_primary_publication_date_conflict"]


def test_editorial_and_all_bound_video_originals_are_retained_exactly_without_adopting_dates(tmp_path):
    base, captures, manifest, _ = artifact(tmp_path, [])
    rows = []
    fixtures = {}
    for index in range(3):
        url = f"https://www.latercera.com/videos/noticia/unit-video-{index}/"
        primary = {"@type": "NewsArticle", "url": url, "headline": "Video sanitario original con texto insuficiente",
                   "articleBody": "Hospital informa operación.", "articleSection": "Videos", "datePublished": "2026-10-09T12:00:00Z"}
        video = {"@type": "VideoObject", "@id": url+"#video", "url": url, "embedUrl": "https://www.youtube.com/embed/unit"}
        payload = (f'<html><link rel="canonical" href="{url}"><script type="application/ld+json">{json.dumps([primary,video])}</script>'
                   '<article><time class="byline-date">9 Octubre 2026</time></article></html>').encode()
        fixtures[url] = payload
        rows.append(captured_record(captures, url, payload))
    url = "https://www.latercera.com/paula/noticia/unit-opinion-conflict/"
    html = synthetic_unit_html(url).decode().replace('"articleSection": "Nacional"', '"articleSection": "Branded", "keywords": ["Opinión"]')
    html = html.replace("2026-10-09T12:00:00Z", "2026-09-01T12:00:00Z")
    fixtures[url] = html.encode()
    rows.append(captured_record(captures, url, fixtures[url]))
    manifest.write_text(json.dumps({"source": "pulso_latercera", "mode": "actual_core_http_observation_no_inventory_injection", "requests": rows}))
    output = tmp_path / "editorial"
    report = corpus.audit(base, tmp_path / "report.json", tmp_path / "thin", exception_output=output)
    exceptions = report["editorial_and_video_exception_originals"]
    assert exceptions["unique_urls"] == 4
    assert exceptions["category_counts"]["url_bound_primary_video_object"] == 3
    assert exceptions["category_counts"]["observed_primary_publication_date_conflict"] == 1
    for row in exceptions["requests"]:
        compressed = (output / row["gzip_file"]).read_bytes()
        assert gzip.decompress(compressed) == fixtures[row["url"]]
        assert hashlib.sha256(compressed).hexdigest() == row["gzip_sha256"]
        assert row["capture_provenance"] == "preserved_original_cold_core_editorial_or_video_exception"
        if "url_bound_primary_video_object" in row["retention_categories"]:
            assert row["gzip_file"].startswith("video/")
            assert row["url_bound_video_objects"] == 1
        else:
            assert row["visible_byline_day"] == "2026-10-09"
            assert row["publication_evidence"][0]["timestamp"] == "2026-09-01T12:00:00Z"
            assert row["current_parser"]["reason"] == "conflicting_publication_dates"


def test_standalone_bound_video_is_retained_without_fabricating_an_article(tmp_path):
    base, captures, manifest, _ = artifact(tmp_path, [])
    url = "https://www.latercera.com/videos/noticia/unit-standalone-video/"
    video = {"@type": "VideoObject", "url": url, "name": "Conversación sobre hospitales",
             "uploadDate": "2026-10-09T12:00:00Z", "embedUrl": "https://www.youtube.com/embed/unit"}
    payload = (f'<html><link rel="canonical" href="{url}"><script type="application/ld+json">{json.dumps(video)}</script>'
               '<article><time class="byline-date">9 Octubre 2026</time></article></html>').encode()
    record = captured_record(captures, url, payload)
    manifest.write_text(json.dumps({"source": "pulso_latercera", "mode": "actual_core_http_observation_no_inventory_injection",
                                   "requests": [record]}))
    output = tmp_path / "editorial"
    report = corpus.audit(base, tmp_path / "report.json", tmp_path / "thin", exception_output=output)
    row, = report["editorial_and_video_exception_originals"]["requests"]
    assert row["retention_categories"] == ["url_bound_primary_video_object"]
    assert row["url_bound_article_nodes"] == 0 and row["url_bound_video_objects"] == 1
    assert row["full_primary_body"] == "" and not row["body_complete_as_original"]
    assert row["current_parser"]["status"] == "error"
    assert gzip.decompress((output / row["gzip_file"]).read_bytes()) == payload
    assert row["visible_byline_day"] == "2026-10-09"


def test_union_of_actual_capture_runs_keeps_cold_thin_originals_after_successful_warm_parser(tmp_path):
    base, captures, manifest, discovery = artifact(tmp_path, [])
    url = "https://www.latercera.com/paula/noticia/unit-thin-cold-then-warm/"
    payload = synthetic_unit_html(url, body="La clínica recibe pacientes.")
    record = captured_record(captures, url, payload)
    manifest.write_text(json.dumps({"source": "pulso_latercera", "mode": "actual_core_http_observation_no_inventory_injection", "requests": [record]}))
    cold = json.loads(discovery.read_text())
    cold["source_details"]["pulso_latercera"] = [{"url": url, "status": "detail_error", "reason": "incomplete_article_evidence"}]
    discovery.write_text(json.dumps(cold))
    warm = base / "warm/state/discovery_run.json"
    warm.parent.mkdir(parents=True)
    warm.write_text(json.dumps({"at": "2026-10-11T07:40:00Z", "source_details": {"pulso_latercera": [
        {"url": url, "status": "discovered_metadata_only", "reason": "publisher_video_text_unavailable"}]}}))
    output = tmp_path / "thin"
    report = corpus.audit(base, tmp_path / "union.json", output)
    assert report["discovery_at"] == "2026-10-11T07:40:00Z"
    assert len(report["observed_discovery_run_sha256s"]) == 2
    assert report["thin_originals"]["expected_unique_incomplete_urls"] == 1
    row, = report["thin_originals"]["requests"]
    assert row["captured_at"] == record["captured_at"]
    assert row["original_capture_manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert gzip.decompress((output / row["gzip_file"]).read_bytes()) == payload


def test_all_observed_old_date_conflicts_are_retained_without_date_adoption_and_missing_are_explicit(tmp_path):
    base, captures, manifest, discovery = artifact(tmp_path, [])
    url = "https://www.latercera.com/nacional/noticia/unit-old-conflict/"
    missing = "https://www.latercera.com/nacional/noticia/unit-missing-old-conflict/"
    payload = synthetic_unit_html(url).replace(b"2026-10-09T12:00:00Z", b"2020-09-01T00:30:00Z").replace(
        b"9 Octubre 2026", b"9 Octubre 2020")
    record = captured_record(captures, url, payload)
    manifest.write_text(json.dumps({"source": "pulso_latercera", "mode": "actual_core_http_observation_no_inventory_injection", "requests": [record]}))
    snapshot = json.loads(discovery.read_text())
    possible = ["2020-08-31", "2020-09-01", "2020-10-09"]
    snapshot["source_details"]["pulso_latercera"] = [dict(url=value, status="excluded", reason="all_possible_publication_days_before_90_days",
        publisher_exception_reason="publisher_conflicting_publication_dates", possible_publication_days=possible,
        publication_date=None, publication_date_verified=False) for value in (url, missing)]
    discovery.write_text(json.dumps(snapshot))
    output = tmp_path / "editorial"
    report = corpus.audit(base, tmp_path / "report.json", tmp_path / "thin", exception_output=output)
    exceptions = report["editorial_and_video_exception_originals"]
    assert exceptions["status"] == "OBSERVED_EXCEPTION_ORIGINAL_RETENTION_PARTIAL"
    assert exceptions["missing_observed_current_discovery_date_conflict_originals"] == [missing]
    assert len(exceptions["observed_current_discovery_date_conflict_targets"]) == 2
    row, = exceptions["requests"]
    assert row["original_visible_byline_outside_complete_90_window"]
    assert row["retention_categories"] == ["observed_primary_publication_date_conflict"]
    assert row["visible_byline_day"] == "2020-10-09"
    assert row["observed_current_discovery_date_conflict"][0]["possible_publication_days"] == possible
    assert row["observed_current_discovery_date_conflict"][0]["publication_date"] is None
    assert gzip.decompress((output / row["gzip_file"]).read_bytes()) == payload
    assert row["sha256"] == hashlib.sha256(payload).hexdigest()
