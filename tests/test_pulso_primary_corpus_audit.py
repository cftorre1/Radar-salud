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

EXPANDED_REVIEW = json.loads((ROOT / "data/audits/pulso_expanded_editorial_originals_independent_review_2026_10_11.json").read_text())
REVIEWED_EMPTY_VIDEO_ORIGINALS = [
    row for row in EXPANDED_REVIEW["all_31_new_url_original_semantic_reviews"]["all_new_originals"]
    if row.get("video_route") and row["primary_body_characters"] == 0
]
EMPTY_VIDEO_RAW_HASHES = {
    "d9910df6cfc7da3453f5459150c2bc04ded5e6693781efbb3cd537e60c387555",
    "42c828d610897ef20ad6327b93daf986d6d82a1630df8761b545ca74c27da694",
    "736160560bd26df1a6cec68ff4b640d1f8adda12a7668809adc6ffed1888f961",
    "fba430e4300cb136e8378f317b2d1652ab905fd41d57216a82ee7d2c0cfa2b04",
    "c7aff3a2469b7f681a7cdadb00d3d09d802bc594bef877cd8834faf96abb62b8",
    "a37697148aaae76a559e5b8760610a981388275d17cd626e67a935ea3f566d2a",
    "8ff0eba1a8c050424df5a89f9b907f69ff4dfe65da00092994d8308d2aa1dd84",
    "885e48ad40591653d7da068260397258dede667601b672a8bd6ef98e1d758b7b",
    "deb6707161e18cfe425f25222ccf2d190a21c82a1deefe1573ce9f6478ca3a37",
    "a5f69d072a0572c2b30f828c865b1cb5a3b31b64c41adbff2cf04ace3ae9d553",
}


def reviewed_original_payload(row):
    """Use durable originals first; scratch is an exact captured-byte fallback."""
    relative = Path(row["gzip_file"])
    assert not relative.is_absolute() and ".." not in relative.parts
    bases = (ROOT / "tests/fixtures/pulso_editorial_exception_real",
             Path("/workspace/work/pulso-originals-73e23e4"))
    original = next((base / relative for base in bases if (base / relative).is_file()), None)
    if original is None:
        pytest.skip("Independently reviewed original HTML unavailable: " + row["url"])
    compressed = original.read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == row["gzip_sha256"]
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == row["capture_sha256"]
    assert len(payload) == row["raw_byte_length"]
    return payload


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
    assert projection["primary_body_unavailable_reason"] == "primary_text_missing_in_original"
    assert not projection["body_complete_as_original"]
    assert projection["current_parser"]["status"] == "error"


@pytest.mark.parametrize("json_body", ["", None])
def test_video_wrapper_length_never_substitutes_for_missing_primary_text(json_body):
    url = "https://www.latercera.com/videos/noticia/unit-video-wrapper/"
    html = synthetic_unit_html(url, body="", section="Videos").decode()
    if json_body is None:
        html = html.replace('"articleBody": ""', '"articleBody": null')
    wrapper = ("Por autor Compartir Twitter Facebook Whatsapp LinkedIn Email Comentarios " * 8)
    html = html.replace("<article>", f'<article><div class="article-body"><span>{wrapper}</span></div>')
    parser = corpus._Article()
    parser.feed(html)
    assert len(" ".join(parser.body)) > 160 and parser.body_paragraphs == []
    projection = corpus.primary_projection(html, url)
    assert projection["full_primary_body"] == "" and projection["primary_body_chars"] == 0
    assert projection["primary_body_sha256"] == hashlib.sha256(b"").hexdigest()
    assert not projection["primary_body_available"] and not projection["body_complete_as_original"]
    assert projection["primary_body_unavailable_reason"] == "primary_text_missing_in_original"
    assert projection["primary_document_diagnosis"] == "publisher_video_route_with_primary_article_text_below_160"


def test_missing_json_body_can_use_primary_html_paragraphs_without_wrapper_text():
    url = "https://www.latercera.com/nacional/noticia/unit-html-body/"
    body = "La clínica amplía su red de hospitales y atiende pacientes. " * 5
    html = synthetic_unit_html(url, body="").decode().replace('"articleBody": ""', '"articleBody": null')
    html = html.replace("<article>", '<article><div class="article-body"><span>Compartir Twitter Whatsapp</span>'
                        f'<p class="article-body__paragraph">{body}</p></div>')
    projection = corpus.primary_projection(html, url)
    assert projection["full_primary_body"] == body.strip()
    assert projection["primary_body_source"] == "article_html_primary_paragraphs"
    assert projection["primary_body_unavailable_reason"] is None
    assert projection["body_complete_as_original"]


def test_independent_empty_video_regression_set_contains_all_ten_original_identities():
    assert len(REVIEWED_EMPTY_VIDEO_ORIGINALS) == 10
    assert {row["capture_sha256"] for row in REVIEWED_EMPTY_VIDEO_ORIGINALS} == EMPTY_VIDEO_RAW_HASHES


@pytest.mark.parametrize("original", REVIEWED_EMPTY_VIDEO_ORIGINALS,
                         ids=lambda row: row["url"].split("/noticia/")[-1].rstrip("/"))
def test_all_ten_real_empty_video_bodies_exclude_wrappers_and_keep_source_content_hold(original):
    payload = reviewed_original_payload(original)
    html = payload.decode("utf-8")
    parser = corpus._Article()
    parser.feed(html)
    assert len(" ".join(parser.body)) >= 160 and parser.body_paragraphs == []
    projection = corpus.primary_projection(html, original["url"])
    assert projection["canonical_matches_requested"]
    assert projection["url_bound_article_nodes"] == projection["url_bound_video_objects"] == 1
    assert projection["full_primary_body"] == "" and projection["primary_body_chars"] == 0
    assert projection["primary_body_sha256"] == original["primary_body_sha256"] == hashlib.sha256(b"").hexdigest()
    assert projection["primary_body_source"] == "primary_text_missing_in_original"
    assert projection["primary_body_unavailable_reason"] == "primary_text_missing_in_original"
    assert not projection["primary_body_available"] and not projection["body_complete_as_original"]
    assert projection["primary_document_diagnosis"] == "publisher_video_route_with_primary_article_text_below_160"
    assert projection["current_parser"]["status"] == "error"
    assert projection["current_parser"]["reason"] == "publisher_video_text_unavailable"


def test_real_alzheimer_original_keeps_84_primary_characters_without_wrapper_padding():
    base = ROOT / "tests/fixtures/pulso_editorial_exception_real"
    manifest = json.loads((base / "manifest.json").read_text())
    raw_sha = "6c310d175c41f476e2d54622122d63e370f5c916c4b8408587dccb2952082967"
    original = next(row for row in manifest["requests"] if row["sha256"] == raw_sha)
    compressed = (base / original["gzip_file"]).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == "f49f16a0d08fb386e724431e14d110154d9ce752afede6622d29015a9bd3a10f"
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == raw_sha
    projection = corpus.primary_projection(payload.decode(original.get("charset") or "utf-8"), original["url"])
    assert projection["primary_body_source"] == "url_bound_json_ld_articleBody"
    assert projection["primary_body_chars"] == len(projection["full_primary_body"]) == 84
    assert projection["primary_body_sha256"] == "e47fcf71c636dcefa6e0a3c186f2decccb9c3cd29f534d197f6d04a2c9056cfe"
    assert projection["primary_body_available"] and projection["primary_body_unavailable_reason"] is None
    assert projection["primary_body_below_160"]
    assert projection["current_parser"]["reason"] == "publisher_video_text_unavailable"


def test_real_bound_liveblog_preserves_original_document_and_separates_primary_paragraph_scope():
    base = ROOT / "tests/fixtures/pulso_editorial_exception_real"
    manifest = json.loads((base / 'manifest.json').read_text())
    row = next(row for row in manifest['requests'] if '/politica/noticia/minuto-a-minuto-' in row['url'])
    _, _, html = corpus.verify_original(base, row)
    projection = corpus.primary_projection(html, row['url'])
    assert projection['url_bound_article_nodes'] == 0 and projection['url_bound_liveblog_nodes'] == 1
    assert projection['primary_body_chars'] == 18955
    assert projection['primary_body_sha256'] == 'db210fa2fbe8ae4192f9e4ccdb4afb3a337e8aa9c755eda33c4948b0e641c088'
    assert projection['primary_body_source'] == 'liveblog_document_html'
    proof = projection['liveblog_document_projection']
    assert proof['timeline_temporal_evidence_verified'] and proof['primary_timeline_entries'] == 110
    assert proof['original_html_sha256'] == row['sha256']
    assert proof['paragraph_chars'] == 10312
    assert proof['paragraph_sha256'] == '2e53fa938fe73855217e4fdb0699cc302383d66c4497ece4bc67c83f4228620b'
    assert 'wrapper_controls' in proof['scope']
    assert projection['current_parser']['body_matches_original_projection']
    # Changing only the retained document's declared JSON-LD type is a test
    # mutation. An embedded video cannot authorize full document fallback.
    changed = corpus.primary_projection(html.replace('"LiveBlogPosting"', '"RelatedArticle"'), row['url'])
    assert changed['url_bound_liveblog_nodes'] == 0 and changed['liveblog_document_projection'] is None
    assert changed['primary_body_chars'] == 10312 and changed['primary_body_source'] == 'article_html_primary_paragraphs'


def test_nineteen_cold_video_wrappers_remain_hash_verified_history_without_primary_text_credit():
    import copy
    from pulso_fixture_witnesses import COLD_RECORDS, assert_cold_witnesses
    base = ROOT / 'tests/fixtures/pulso_editorial_exception_real'
    manifest = json.loads((base / 'manifest.json').read_text())
    changed = []
    for row in manifest['requests']:
        cold = COLD_RECORDS.get(row['url'])
        if not cold or '/videos/' not in row['url'] or cold['primary_body_source'] != 'article_html':
            continue
        _, _, html = corpus.verify_original(base, row)
        projection = corpus.primary_projection(html, row['url'])
        assert projection['full_primary_body'] == '' and projection['primary_body_chars'] == 0
        assert projection['html_wrapper_observation']['chars'] == cold['primary_body_chars']
        assert projection['html_wrapper_observation']['sha256'] == cold['primary_body_sha256']
        changed.append(row['url'])
    assert len(changed) == 19
    assert_cold_witnesses(manifest['requests'])
    forged = copy.deepcopy(manifest['requests'])
    row = next(row for row in forged if row['url'] == changed[0])
    row['primary_body_chars'], row['primary_body_sha256'] = 1, hashlib.sha256(b'x').hexdigest()
    with pytest.raises(AssertionError):
        assert_cold_witnesses(forged)


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
