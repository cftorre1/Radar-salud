"""Adversarial QA-reader tests are synthetic, never a live acceptance claim."""
import gzip
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlencode

import pytest

spec = importlib.util.spec_from_file_location("qa_pulso_recovery", Path(__file__).parents[1] / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
BASE = "https://www.latercera.com/nacional/noticia/"


@pytest.fixture
def evidence(tmp_path):
    """A whole frozen benchmark fixture, not a publication sample or quota."""
    controls, matrix, details, queue = [], [], [], {}
    for i in range(79):
        url = BASE + f"verified-health-{i}/"
        day = "2026-09-11" if i < 29 else "2026-07-13"
        node = {"@type": "NewsArticle", "url": url, "datePublished": day + "T15:00:00Z",
                "headline": "Hospital amplía capacidad para reducir listas de espera",
                "articleBody": "El hospital amplía capacidad para reducir listas de espera. " * 5}
        raw = (f'<link rel="canonical" href="{url}"><script type="application/ld+json">' + json.dumps(node) + '</script>').encode()
        sha = qa.digest(raw)
        relative = f"tests/fixtures/pulso_runtime_real/{sha}.html.gz"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        compressed = gzip.compress(raw, mtime=0)
        path.write_bytes(compressed)
        capture = dict(url=url, status=200, sha256=sha, returned_text_utf8_sha256=sha,
                       gzip_file=relative, gzip_sha256=qa.digest(compressed), captured_at="2026-10-11T10:30:00Z")
        controls.append(dict(url=url, publication_date=day, recall_expected=True, section="nacional", topic="providers_capacity"))
        metadata = dict(article_verified=True, source_quality_gate="passed", canonical_url=url,
                        publication_date=day, page_text="El hospital amplía capacidad para reducir listas de espera. " * 5,
                        html_sha256=sha, publication_date_source="json_ld_datePublished", publication_timestamp=day + "T15:00:00Z")
        queue[str(i)] = dict(source=qa.SOURCE, status="pending", lane="BACKFILL", attempts=0,
                             detected_at="2026-10-11T10:30:00Z", raw=dict(url=url, event_date=day, metadata=metadata))
        details.append(dict(url=url, status="discovered", publication_date=day))
        matrix.append(dict(url=url, publication_date=day, current_core_detected=True, section="Nacional", topics=["providers"],
                           publication_date_source="json_ld_datePublished", publication_date_evidence="current_verified_detail",
                           primary_detail_sha256=sha, primary_detail_captured_at="2026-10-11T10:30:00Z",
                           primary_detail_cache_hit=False, original_http_captures=[capture],
                           exact_reason="processing_not_attempted:explicit_discovery_only", editorial_outcome="pending",
                           queue=[], history_present=False, feed_present=False))
    summaries, captures = [], []
    for name in qa.REQUIRED_FEEDS:
        summaries.append(dict(status="public_feed_coverage", feed=name, coverage_complete=True, errors=0,
                              termination="all_feed_count_delimited_articles", publisher_count=1, pages_attempted=1))
        kind, slug = name.split(":")
        query = dict(feedOffset=0, feedSize=24, fromComponent="result-list")
        query["includeSections" if kind == "section" else "tagSlug"] = "/" + slug if kind == "section" else slug
        endpoint = "story-feed-sections-fetch" if kind == "section" else "story-feed-tag-fetch"
        url = "https://www.latercera.com/pf/api/v3/content/fetch/" + endpoint + "?" + urlencode(dict(query=json.dumps(query)))
        raw = json.dumps(dict(content_elements=[dict(_id="health-story", first_publish_date="2026-09-11T15:00:00Z")], count=1, next=1)).encode()
        sha = qa.digest(raw)
        relative = f"tests/fixtures/pulso_runtime_real/{sha}.api.json.gz"
        compressed = gzip.compress(raw, mtime=0)
        (tmp_path / relative).write_bytes(compressed)
        captures.append(dict(url=url, status=200, sha256=sha, returned_text_utf8_sha256=sha, gzip_file=relative,
                             gzip_sha256=qa.digest(compressed), captured_at="2026-10-11T10:30:00Z"))
        details.append(dict(status="public_feed_page", feed=name, offset=0, primary_entries=1, count=1, next=1, json_sha256=sha))
    zero = {tier: dict(attempted=0, successful=0, failed=0) for tier in ("fast", "deep")}
    execution = dict(engine_called=True, engine_completed=True, mode="discovery_only",
                     started_at="2026-10-11T10:00:00Z", finished_at="2026-10-11T12:00:00Z",
                     ai_guardrails_modified=False, budget_before=dict(run=deepcopy(zero), month=deepcopy(zero)),
                     budget_after=dict(run=deepcopy(zero), month=deepcopy(zero)))
    control = dict(articles=controls, counts={"primary_recall_expected_30": 29, "primary_recall_expected_90": 79})
    windows = {}
    for days, (first, last, count) in qa.WINDOWS.items():
        control["window_" + days] = dict(start=first, end=last)
        windows[days] = dict(start=first, end=last, control_expected=count, control_declared_expected=count,
                             control_denominator_consistent=True, control_detected_by_current_core=count,
                             recall=1, missed=[], date_conflicts=[])
    report = dict(last_core_execution=execution, runtime="daily_core", selected_sources=[qa.SOURCE],
                  core_source_present=True, discovery_run_at="2026-10-11T11:59:00Z", unrelated_queue_unchanged=True,
                  windows=windows, matrix=matrix, coverage=summaries,
                  primary_coverage=dict(status="runtime_coverage", coverage_complete=True, required_feeds=sorted(qa.REQUIRED_FEEDS)),
                  baseline_queue=[], source_attribution_findings=[], unresolved_recent_feed_exclusions=[],
                  unresolved_pending_operational_reasons=[], external_control_sha256=qa.FROZEN_CONTROL_SHA256)
    workflow = tmp_path / ".github/workflows"
    workflow.mkdir(parents=True)
    env = "env:\n  RADAR_FAST_PER_RUN: 120\n  RADAR_DEEP_PER_RUN: 15\n  RADAR_FAST_PER_MONTH: 1500\n  RADAR_DEEP_PER_MONTH: 180\n"
    for name in ("daily-radar.yml", "pulso-runtime-recovery.yml"):
        (workflow / name).write_text(env)
    return dict(report=report, control=control, root=tmp_path,
                discovery={"source_details": {qa.SOURCE: details}, "sources": {qa.SOURCE: dict(discovered=79, error_type=None)}},
                queue=queue, history=[], snapshot={"signals": []}, telemetry=[], captures=captures,
                control_sha=qa.FROZEN_CONTROL_SHA256)


def codes(data):
    return {row["code"] for row in qa.evaluate(**data)["findings"]}


def process(data):
    execution = data["report"]["last_core_execution"]
    execution["mode"] = "real_core_processing"
    for scope in ("run", "month"):
        execution["budget_after"][scope]["fast"].update(attempted=3, successful=3)
    data["telemetry"] = [dict(at="2026-10-11T11:00:00Z", kind="fast", success=True, response_id=f"resp_real_schema_{i}") for i in range(3)]
    for i, (item, row) in enumerate(zip(data["queue"].values(), data["report"]["matrix"])):
        reason = "editorial_relevance_below_threshold" if i < 3 else "media_materiality_prefilter"
        assessment = dict(decision="rejected", reason=reason)
        if i < 3:
            assessment.update(relevance_score=71, threshold=72, analysis_reason="No nuevo cambio material verificado.")
        item.update(status="rejected", reason=reason, attempts=1)
        item["raw"]["metadata"]["editorial_assessment"] = assessment
        row.update(exact_reason=reason, editorial_outcome="rejected")
    data["report"]["feed_evidence"] = dict(serialized_feed_verified=True, generated_after_current_history=True)
    data["snapshot"]["generated_at"] = "2026-10-11T12:05:00Z"


def publish_first(data, *, url=None):
    process(data)
    row = data["report"]["matrix"][0]
    original_url = row["url"]
    item = data["queue"]["0"]
    item["status"] = "published"
    item["raw"]["metadata"]["editorial_assessment"].update(decision="published", relevance_score=84)
    published = dict(source_url=original_url, publication_date=row["publication_date"], event_date=row["publication_date"],
                     evidence_maturity="media_reported", title="Hospital anuncia expansión de capacidad",
                     what_happened="Según Pulso / La Tercera, el hospital amplía su capacidad quirúrgica.",
                     why_it_matters="La ampliación cambia la capacidad disponible para prestaciones de alta complejidad.")
    data["history"] = [published]
    data["snapshot"]["signals"] = [deepcopy(published)]
    row.update(history_present=True, feed_present=True, exact_reason="history_and_feed_present")
    if url:
        # Semantic constraint tests use the exact source slug after preserving
        # the primary fixture's binding; mutate all related evidence together.
        for value in (row, data["control"]["articles"][0], data["discovery"]["source_details"][qa.SOURCE][0]):
            value["url"] = url
        item["raw"]["url"] = url
        item["raw"]["metadata"]["canonical_url"] = url
        for value in (published, data["snapshot"]["signals"][0]):
            value["source_url"] = url
        capture = row["original_http_captures"][0]
        raw = (f'<link rel="canonical" href="{url}"><script type="application/ld+json">' + json.dumps({"@type": "NewsArticle", "url": url, "datePublished": row["publication_date"],
               "headline": "Hospital amplía capacidad para reducir listas de espera", "articleBody": item["raw"]["metadata"]["page_text"]}) + '</script>').encode()
        compressed = gzip.compress(raw, mtime=0)
        (data["root"] / capture["gzip_file"]).write_bytes(compressed)
        capture.update(url=url, sha256=qa.digest(raw), returned_text_utf8_sha256=qa.digest(raw), gzip_sha256=qa.digest(compressed))
        row["primary_detail_sha256"] = qa.digest(raw)
        item["raw"]["metadata"]["html_sha256"] = qa.digest(raw)


def test_discovery_pass_is_explicitly_separate_from_acceptance(evidence):
    result = qa.evaluate(**evidence)
    assert result["findings"] == []
    assert result["discovery_qa"] == "PASS"
    assert result["processing_qa"] == "NOT_RUN"
    assert result["acceptance"] == "NOT_ACCEPTED"


def test_legacy_queue_and_claimed_recall_cannot_hide_a_real_missed_control(evidence):
    evidence["discovery"]["source_details"][qa.SOURCE][0]["status"] = "excluded"
    evidence["report"]["matrix"][0]["omission"] = dict(reason="URL_not_enumerated_by_current_core", url_level_cause_verified=False)
    assert {"important_external_control_omissions", "reported_recall_not_supported_by_core_traces"} <= codes(evidence)


def test_changing_denominator_or_complete_window_cannot_make_small_sample_pass(evidence):
    evidence["control"]["articles"].pop()
    evidence["report"]["windows"]["90"].update(control_expected=78, control_declared_expected=78)
    evidence["control"]["window_30"]["start"] = "2026-09-12"
    assert {"frozen_control_denominator_changed", "complete_calendar_window_changed"} <= codes(evidence)


def test_denominator_preserving_control_replacement_cannot_repin_itself(evidence):
    evidence["control"]["articles"][0]["title"] = "Una identidad reemplazada conserva29/79"
    replacement_sha = qa.digest(json.dumps(evidence["control"]).encode())
    evidence["control_sha"] = replacement_sha
    evidence["report"]["external_control_sha256"] = replacement_sha
    assert "independent_control_identity_not_frozen" in codes(evidence)


def test_section_identity_uses_canonical_url_and_topic_aliases_do_not_false_fail(evidence):
    result = qa.evaluate(**evidence)
    assert result["discovery_qa"] == "PASS"
    assert result["checks"]["external_topic_comparison"][0]["independent_topic"] == "providers_capacity"
    assert result["checks"]["external_topic_comparison"][0]["publisher_topics"] == ["providers"]
    evidence["control"]["articles"][0]["section"] = "Pulso"
    assert "external_control_section_not_bound_to_original_url" in codes(evidence)


def test_complementary_sitemap_cap_does_not_override_complete_primary_pagination(evidence):
    evidence["report"]["coverage"].append(dict(status="archive_coverage", coverage_complete=False, termination="explicit_page_limit"))
    assert qa.evaluate(**evidence)["discovery_qa"] == "PASS"
    evidence["report"]["coverage"][0].update(coverage_complete=False, termination="explicit_public_feed_page_limit")
    assert "feed_incomplete_or_errors" in codes(evidence)


def test_omitting_horizontes_from_required_feeds_fails(evidence):
    evidence["report"]["primary_coverage"]["required_feeds"].remove("section:horizontes")
    assert "primary_required_public_feed_coverage_incomplete" in codes(evidence)


def test_three_old_pages_require_real_page_boundary_evidence(evidence):
    evidence["report"]["coverage"][0]["termination"] = "three_publication_ordered_detail_verified_old_pages"
    assert "three_old_pages_boundary_unproven" in codes(evidence)


def old_boundary(data):
    summary = data["report"]["coverage"][0]
    feed = summary["feed"]
    details = data["discovery"]["source_details"][qa.SOURCE]
    details[:] = [row for row in details if not (row.get("status") == "public_feed_page" and row.get("feed") == feed)]
    kind, slug = feed.split(":")
    for index in range(3):
        offset = index * 24
        entries = [dict(_id=f"old-{offset + n}", website_url=BASE + f"old-{offset + n}/", first_publish_date="2026-07-10T15:00:00Z") for n in range(24)]
        query = dict(feedOffset=offset, feedSize=24, fromComponent="result-list")
        query["includeSections" if kind == "section" else "tagSlug"] = "/" + slug if kind == "section" else slug
        endpoint = "story-feed-sections-fetch" if kind == "section" else "story-feed-tag-fetch"
        url = "https://www.latercera.com/pf/api/v3/content/fetch/" + endpoint + "?" + urlencode(dict(query=json.dumps(query)))
        raw = json.dumps(dict(content_elements=entries, count=10000, next=offset + 24)).encode()
        compressed = gzip.compress(raw, mtime=0)
        relative = f"tests/fixtures/pulso_runtime_real/{qa.digest(raw)}.api.json.gz"
        (data["root"] / relative).write_bytes(compressed)
        data["captures"].append(dict(url=url, status=200, sha256=qa.digest(raw), returned_text_utf8_sha256=qa.digest(raw),
                                     gzip_file=relative, gzip_sha256=qa.digest(compressed), captured_at="2026-10-11T10:30:00Z"))
        details.append(dict(status="public_feed_page", feed=feed, offset=offset, primary_entries=24, count=10000, next=offset + 24,
                            json_sha256=qa.digest(raw), inventory_day_max="2026-07-10", boundary_pages=index + 1, verified_details=24))
        for entry in entries:
            details.append(dict(status="excluded", url=entry["website_url"], publication_date="2026-07-10",
                                publication_date_source="json_ld_datePublished", html_sha256="a" * 64))
    summary.update(termination="three_publication_ordered_detail_verified_old_pages", publisher_count=10000, pages_attempted=3)


@pytest.mark.parametrize("change", ["recent_final_date", "search_snippet"])
def test_old_api_first_publication_cannot_override_recent_or_unverified_original_details(evidence, change):
    old_boundary(evidence)
    assert qa.evaluate(**evidence)["discovery_qa"] == "PASS"
    detail = next(row for row in evidence["discovery"]["source_details"][qa.SOURCE] if row.get("url") == BASE + "old-0/")
    if change == "recent_final_date":
        detail["publication_date"] = "2026-10-10"
        expected = "public_api_boundary_detail_dates_not_old"
    else:
        detail["publication_date_source"] = "search_snippet"
        expected = "public_api_boundary_original_detail_date_unverified"
    assert expected in codes(evidence)


def test_internal_complete_summary_cannot_replace_original_api_boundary_json(evidence):
    evidence["captures"] = []
    assert "public_api_http_chain_unproven" in codes(evidence)
    assert qa.evaluate(**evidence)["discovery_qa"] == "FAIL"


def test_small_summary_count_cannot_override_capped_original_json_count(evidence):
    """Reproduce the reviewed false PASS while keeping all HTTP hashes valid."""
    summary = evidence["report"]["coverage"][0]
    page = next(row for row in evidence["discovery"]["source_details"][qa.SOURCE]
                if row.get("status") == "public_feed_page" and row["feed"] == summary["feed"])
    capture = next(row for row in evidence["captures"] if qa.api_page_key(row["url"]) == (summary["feed"], 0))
    original = gzip.decompress((evidence["root"] / capture["gzip_file"]).read_bytes())
    document = json.loads(original)
    document["count"] = 10000
    raw = json.dumps(document).encode()
    compressed = gzip.compress(raw, mtime=0)
    relative = f"tests/fixtures/pulso_runtime_real/{qa.digest(raw)}.api.json.gz"
    (evidence["root"] / relative).write_bytes(compressed)
    capture.update(gzip_file=relative, sha256=qa.digest(raw), returned_text_utf8_sha256=qa.digest(raw), gzip_sha256=qa.digest(compressed))
    page.update(count=10000, json_sha256=qa.digest(raw))
    # Publisher proof is intact. Only the summary lies about total exhaustion.
    assert qa.verify_api_pages([page], evidence["captures"], evidence["root"]) == []
    assert summary["publisher_count"] == 1
    result = qa.evaluate(**evidence)
    assert result["discovery_qa"] == "FAIL"
    assert "count_delimited_feed_exhaustion_unproven" in {row["code"] for row in result["findings"]}


@pytest.mark.parametrize("pages", [
    [dict(offset=0, primary_entries=24, count=25), dict(offset=24, primary_entries=1, count=26)],
    [dict(offset=0, primary_entries=24, count=25), dict(offset=23, primary_entries=1, count=25)],
    [dict(offset=0, primary_entries=24, count=25), dict(offset=25, primary_entries=1, count=25)],
    [dict(offset=0, primary_entries=24, count=25), dict(offset=24, primary_entries=2, count=25)],
    [dict(offset=0, primary_entries=24, count=25)],
])
def test_terminal_count_requires_stable_total_and_complete_bounded_positions(pages):
    assert not qa.count_exhaustion_proven(dict(publisher_count=25), pages)


def test_count_terminal_accepts_complete_positions_and_genuine_empty_scope():
    assert qa.count_exhaustion_proven(dict(publisher_count=25), [
        dict(offset=0, primary_entries=24, count=25), dict(offset=24, primary_entries=1, count=25)])
    assert qa.count_exhaustion_proven(dict(publisher_count=0), [dict(offset=0, primary_entries=0, count=0)])


def test_prior_cache_requires_explicit_reuse_label_and_preserved_original_provenance(evidence):
    row = evidence["report"]["matrix"][0]
    row.update(primary_detail_cache_hit=True, primary_detail_captured_at="2026-10-11T09:00:00Z", publisher_lastmod="2026-09-11T15:00:00Z",
               publication_date_evidence="reused_verified_primary_byline_unchanged_publisher_lastmod")
    row["original_http_captures"][0].update(capture_provenance="preserved_original_http_response", original_capture_manifest_sha256="a" * 64)
    assert qa.evaluate(**evidence)["discovery_qa"] == "PASS"
    row["publication_date_evidence"] = "current_verified_detail"
    assert "cached_primary_falsely_labeled_fresh_or_unbound" in codes(evidence)


def test_raw_original_hash_and_url_bound_dates_are_independently_required(evidence):
    row = evidence["report"]["matrix"][0]
    path = evidence["root"] / row["original_http_captures"][0]["gzip_file"]
    path.write_bytes(gzip.compress(b"changed source bytes"))
    assert "original_primary_capture_not_verified" in codes(evidence)


def test_unrelated_jsonld_does_not_verify_primary_publication_date():
    parser = qa.PrimaryDates()
    parser.feed('<link rel="canonical" href="' + BASE + 'primary/"><script type="application/ld+json">' + json.dumps(
        {"@type": "NewsArticle", "url": BASE + "recommendation/", "datePublished": "2026-10-10T12:00:00Z"}) + '</script>')
    assert parser.days_for(BASE + "primary/") == set()
    assert qa.publisher_day("2026-10-11T01:00:00Z") == "2026-10-10"


@pytest.mark.parametrize("sha,day", [
    ("e322d80bbd4ba2876923944f298f6ac249f995b6e9da2f177372289acc2b66f3", "2026-09-04"),
    ("8e5e353d8694aa8a8170b595b426a0c9ee9a345bc16c8f88087bb030644eddec", "2026-08-11"),
    ("73fbc8f33b16ddbcb722b325243f68f1f8bdc535124c049ae3dc2e0aa2e27172", "2026-09-01"),
    ("30a3338f8e2e9a149a3c5c60aa488d6a3133729316b600e7f88a76bab9e47a24", "2026-10-01"),
    ("4721567cd9702ac79249356f271da2eb5bd1054486e9c044fa69f1ef9c654e06", "2026-09-04"),
    ("79558fcb7fe30603a1ad4f5e3474e574406679b8fb805b5f123afccf721d6754", "2026-07-31"),
    ("a78d7fa00eda277fad0cae0483d0fc381cdd6ed2de62b9a97ebf516f8900227a", "2026-08-05"),
    ("a6d21de71ddd00c9345a5f462fa118f091d5a70f6ff540c4de32cadf1bf78cc7", "2026-07-23"),
    ("e8753a163ed3f864807106a03925da5a8d5aab553c13420c97b9c98f8ea98e6c", "2026-08-20"),
    ("cbe1194267c167fc16c898efdb26ff19986745ba23a289f0804099d62fcd54cf", "2026-07-14"),
    ("8646b65f02a786cd7e3d434dce555f7ab10638e24db7f27fe234e8167ef2bc34", "2026-10-01"),
    ("0f7a1ed2fc769daf4ff3af88e40d4f9ea90013dea9fe01e2633792c6b17ebeae", "2026-10-09"),
])
def test_original_nighttime_controls_keep_rendered_publisher_calendar(sha, day):
    """These exact HTTP bytes caused twelve real false negative controls."""
    root = Path(__file__).parents[1]
    relative = f"tests/fixtures/pulso_runtime_real/{sha}.html.gz"
    compressed = (root / relative).read_bytes()
    parser = qa.PrimaryDates()
    raw = gzip.decompress(compressed)
    assert qa.digest(raw) == sha
    parser.feed(raw.decode())
    row = dict(url=parser.canonical, publication_date=day, primary_detail_sha256=sha,
               original_http_captures=[dict(url=parser.canonical, status=200, sha256=sha,
                                           gzip_sha256=qa.digest(compressed), gzip_file=relative)])
    evidence = {}
    assert qa.verify_primary_capture(row, root, evidence) is None
    assert evidence["publication_date"] == day
    assert evidence["publisher_date_convention"] == "timestamp_calendar"
    assert all(qa.publisher_day(value) != day for value in evidence["primary_timestamps"])


def primary_date_html(values, byline, *, byline_timestamp=None, context=""):
    url = BASE + "primary/"
    node = dict(**{"@type": "NewsArticle"}, url=url, datePublished=values[0])
    metadata = "".join(f'<meta property="article:published_time" content="{value}">' for value in values[1:])
    time = f'<time class="article-body__byline__date" datetime="{byline_timestamp or values[0]}">{byline}</time>'
    return (f'<link rel="canonical" href="{url}">{metadata}<script type="application/ld+json">' +
            json.dumps(node) + '</script><h1>Hospital amplía su capacidad quirúrgica</h1>' +
            (f'<{context}>{time}</{context.split()[0]}>' if context else time))


@pytest.mark.parametrize("context", ["nav", "aside", "footer", 'div class="latest-news"', 'div class="related"'])
def test_navigation_dates_cannot_supply_the_primary_visible_calendar(context):
    parser = qa.PrimaryDates()
    # An otherwise matching timestamp in publisher navigation cannot change
    # the primary metadata's Santiago day when no primary byline was captured.
    parser.feed(primary_date_html(["2026-10-01T00:46:24Z"], "1 OCTUBRE 2026", context=context))
    assert parser.days_for(BASE + "primary/") == {"2026-09-30"}
    assert parser.bylines == []


def test_byline_cannot_mix_calendar_conventions_or_borrow_an_unrelated_calendar():
    parser = qa.PrimaryDates()
    # Each field individually could be mapped to Oct 1, but there is no single
    # convention under which both metadata values corroborate that day.
    parser.feed(primary_date_html(["2026-10-01T00:46:24Z", "2026-10-02T01:00:00Z"], "1 OCTUBRE 2026"))
    assert parser.days_for(BASE + "primary/") == set()
    parser = qa.PrimaryDates()
    parser.feed(primary_date_html(["2026-10-01T00:46:24Z"], "1 OCTUBRE 2026", byline_timestamp="2026-10-02T13:00:00Z"))
    assert parser.days_for(BASE + "primary/") == set()


def test_same_primary_publication_day_does_not_invent_equality_of_distinct_publisher_instants():
    root = Path(__file__).parents[1]
    folder = root / "tests/fixtures/pulso_runtime_real"
    manifest = json.loads((folder / "manifest.json").read_text())
    record = next(value for value in manifest["requests"] if "minsal-conmemora-dia-nacional-del-donante" in value["url"])
    compressed = (folder / record["gzip_file"]).read_bytes()
    raw = gzip.decompress(compressed)
    assert qa.digest(compressed) == record["gzip_sha256"]
    assert qa.digest(raw) == record["sha256"]
    parser = qa.PrimaryDates()
    original = raw.decode(record.get("charset") or "utf-8")
    parser.feed(original)
    proof = parser.publication_evidence_for(record["url"])
    assert proof["publication_date"] == "2026-09-26"
    assert proof["publisher_date_convention"] == "calendar_agreement"
    assert proof["primary_byline_instants_match_metadata"] is False
    assert set(proof["primary_timestamps"]) == {"2026-09-26T17:16:04.571Z"}
    assert {value["timestamp"] for value in proof["visible_bylines"]} == {"2026-09-26T17:20:09.19Z"}
    assert parser.strict_original_projection(record["url"])["visible_publication_date"] == "2026-09-26"
    capture = dict(record, gzip_file=str(Path("tests/fixtures/pulso_runtime_real") / record["gzip_file"]))
    row = dict(url=record["url"], publication_date="2026-09-26", primary_detail_sha256=record["sha256"], original_http_captures=[capture])
    assert qa.verify_primary_capture(row, root) is None
    # A conflicting primary time cannot borrow the unchanged visible day.
    tampered = qa.PrimaryDates()
    tampered.feed(original.replace('2026-09-26T17:20:09.19Z', '2026-09-27T17:20:09.19Z'))
    assert {value["timestamp"] for value in tampered.bylines} == {"2026-09-27T17:20:09.19Z"}
    assert tampered.days_for(record["url"]) == set()


def test_queue_and_original_byline_validate_the_same_real_calendar(evidence):
    row, item = evidence["report"]["matrix"][0], evidence["queue"]["0"]
    url, day, timestamp = row["url"], row["publication_date"], "2026-09-11T00:46:24Z"
    raw = primary_date_html([timestamp, timestamp], "11 SEPTIEMBRE 2026").replace(BASE + "primary/", url)
    node = {"@type": "NewsArticle", "url": url, "datePublished": timestamp,
            "headline": "Hospital amplía capacidad para reducir listas de espera", "articleBody": item["raw"]["metadata"]["page_text"]}
    raw += '<script type="application/ld+json">' + json.dumps(node) + '</script>'
    raw = raw.encode()
    capture = row["original_http_captures"][0]
    compressed = gzip.compress(raw, mtime=0)
    (evidence["root"] / capture["gzip_file"]).write_bytes(compressed)
    capture.update(sha256=qa.digest(raw), returned_text_utf8_sha256=qa.digest(raw), gzip_sha256=qa.digest(compressed))
    row.update(primary_detail_sha256=qa.digest(raw), publication_date_source="visible_article_byline")
    item["raw"]["metadata"].update(html_sha256=qa.digest(raw), publication_timestamp=timestamp,
        publication_date_source="visible_article_byline", visible_publication_date=day,
        publication_evidence=[dict(source="json_ld_datePublished", timestamp=timestamp)])
    result = qa.evaluate(**evidence)
    assert result["discovery_qa"] == "PASS"
    validated = next(value for value in result["checks"]["original_publication_date_validation"] if value["url"] == url)
    assert validated["publisher_date_convention"] == "timestamp_calendar"
    item["raw"]["metadata"]["publication_evidence"].append(dict(timestamp="2026-09-12T01:00:00Z"))
    assert "queue_primary_detail_evidence_unverified" in codes(evidence)


@pytest.mark.parametrize("filename", ["senior_housing.html.gz", "uc_christus.html.gz"])
def test_independent_projection_verifies_verbatim_real_original_fixtures(filename):
    root = Path(__file__).parents[1]
    manifest = json.loads((root / "tests/fixtures/pulso_real/manifest.json").read_text())
    fixture = next(row for row in manifest["fixtures"] if row["path"].endswith(filename))
    row = dict(url=fixture["url"], publication_date="2026-10-10", primary_detail_sha256=fixture["sha256"],
               original_http_captures=[dict(url=fixture["url"], status=200, sha256=fixture["sha256"],
                                           gzip_sha256=fixture["gzip_sha256"], gzip_file=fixture["path"])])
    assert qa.verify_primary_capture(row, root) is None


def test_metadata_only_original_cannot_support_verified_full_article(evidence):
    row = evidence["report"]["matrix"][0]
    capture = row["original_http_captures"][0]
    raw = (f'<link rel="canonical" href="{row["url"]}"><script type="application/ld+json">' + json.dumps(
        {"@type": "NewsArticle", "url": row["url"], "datePublished": row["publication_date"], "headline": "Hospital anuncia expansión de capacidad"}) + '</script>').encode()
    compressed = gzip.compress(raw, mtime=0)
    (evidence["root"] / capture["gzip_file"]).write_bytes(compressed)
    row["primary_detail_sha256"] = qa.digest(raw)
    capture.update(sha256=qa.digest(raw), returned_text_utf8_sha256=qa.digest(raw), gzip_sha256=qa.digest(compressed))
    assert any("original_primary_title_or_body_missing" in value for value in qa.verify_primary_capture(row, evidence["root"]))


def test_stale_interrupted_core_cannot_receive_discovery_pass(evidence):
    evidence["report"]["last_core_execution"]["engine_completed"] = False
    evidence["report"]["discovery_run_at"] = "2026-10-10T12:00:00Z"
    assert {"core_did_not_complete", "stale_or_unbound_discovery_timestamp"} <= codes(evidence)


def test_discovery_budget_consumption_and_other_queue_changes_fail(evidence):
    for scope in ("run", "month"):
        evidence["report"]["last_core_execution"]["budget_after"][scope]["fast"].update(attempted=1, successful=1)
    evidence["report"]["unrelated_queue_unchanged"] = False
    assert {"discovery_consumed_analysis_budget", "other_source_queue_changed_or_unproven"} <= codes(evidence)


def test_baseline_terminal_reopening_is_not_hidden_by_preserved_fingerprint(evidence):
    evidence["report"]["baseline_queue"] = [dict(fingerprint="0", url=evidence["report"]["matrix"][0]["url"],
                                                lane="BACKFILL", detected_at="2026-10-11T10:30:00Z", attempts=0, status="rejected")]
    assert "baseline_queue_identity_or_bookkeeping_changed" in codes(evidence)


def test_processing_can_reject_every_candidate_without_a_publication_quota(evidence):
    process(evidence)
    result = qa.evaluate(**evidence)
    assert result["findings"] == []
    assert result["processing_qa"] == "PASS"
    assert result["acceptance"] == "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW"


def test_actual_api_ledger_and_response_id_are_required(evidence):
    process(evidence)
    evidence["telemetry"][0]["response_id"] = None
    evidence["telemetry"].pop()
    assert {"actual_api_telemetry_and_ledger_delta_disagree", "successful_analysis_without_actual_api_response_id"} <= codes(evidence)


def test_recent_control_pending_for_budget_is_not_end_to_end_processing(evidence):
    process(evidence)
    evidence["queue"]["0"]["status"] = "pending"
    evidence["report"]["matrix"][0]["exact_reason"] = "processing_not_attempted:fast_analysis_capacity_exhausted"
    assert "recent_important_control_not_editorially_processed" in codes(evidence)


def test_published_threshold_attribution_and_serialized_feed_presence_are_checked(evidence):
    publish_first(evidence)
    assert qa.evaluate(**evidence)["processing_qa"] == "PASS"
    evidence["queue"]["0"]["raw"]["metadata"]["editorial_assessment"]["threshold"] = 71
    evidence["history"][0]["evidence_maturity"] = "official_confirmed"
    evidence["snapshot"]["signals"] = []
    assert {"media_editorial_threshold_changed", "published_media_attribution_or_real_date_invalid", "reported_history_or_feed_presence_not_actual"} <= codes(evidence)


def test_proposed_budget_cannot_be_presented_as_enacted(evidence):
    publish_first(evidence, url=BASE + "presupuesto-salud-2027-rebajas-al-ajuar-del-recien-nacido/")
    evidence["history"][0].update(title="Presupuesto salud 2027", what_happened="Según Pulso / La Tercera, el presupuesto 2027 reduce el fondo de alto costo.")
    assert "budget_proposal_presented_as_enacted" in codes(evidence)


def test_deferred_exact_reason_and_feed_freshness_cannot_be_generic(evidence):
    process(evidence)
    evidence["queue"]["0"].update(status="retry", reason="analysis_unavailable")
    evidence["report"]["matrix"][0].update(exact_reason="budget_or_analysis_deferred", editorial_outcome="deferred")
    evidence["report"]["feed_evidence"]["generated_after_current_history"] = False
    assert {"deferred_without_exact_assessment", "actual_serialized_feed_missing_or_stale", "recent_important_control_not_editorially_processed"} <= codes(evidence)


def append_publisher_exception(data, kind):
    """Synthetic original bytes exercise reader rules, not publisher coverage."""
    video = kind == "video"
    sponsored = kind == "sponsored"
    dated = video or sponsored
    url = "https://www.latercera.com/" + ("videos" if video else "branded" if sponsored else "paula") + "/noticia/verified-exception/"
    day, timestamp = ("2026-10-07", "2026-10-07T17:55:00Z") if dated else (None, "2026-08-06T15:00:00Z")
    visible, byline = ("2026-10-07", "7 OCTUBRE 2026") if dated else ("2026-07-30", "30 JULIO 2026")
    byline_timestamp = timestamp if dated else "2026-07-30T15:00:00Z"
    reason = qa.VIDEO_HOLD if video else qa.SPONSORED_HOLD if sponsored else qa.DATE_HOLD
    body = "" if video else ("El trabajo puede afectar la salud y la atención sanitaria. " * 5).strip()
    article = {"@type": "NewsArticle", "url": url, "datePublished": timestamp,
               "headline": "Un reporte del publisher con identidad primaria", "articleBody": body}
    if sponsored:
        article.update(articleSection="Branded", keywords=["salud", "Publicidad"])
    nodes = [article]
    video_evidence = dict(type="VideoObject", url=url, id=url + "#video", embed_url="https://mdstrm.com/embed/original", upload_date=timestamp)
    if video:
        nodes.append({"@type": "VideoObject", "url": url, "@id": url + "#video",
                      "embedUrl": video_evidence["embed_url"], "uploadDate": timestamp})
    raw = (f'<link rel="canonical" href="{url}"><meta property="article:published_time" content="{timestamp}">' +
           '<script type="application/ld+json">' + json.dumps(nodes) + '</script><h1>' + article["headline"] + '</h1>' +
           f'<time class="article-body__byline__date" datetime="{byline_timestamp}">{byline}</time>' +
           ('<div class="article-body__raw-html"><iframe src="' + video_evidence["embed_url"] + '"></iframe></div>' if video else '')).encode()
    sha = qa.digest(raw)
    relative = f"tests/fixtures/pulso_runtime_real/{sha}.html.gz"
    compressed = gzip.compress(raw, mtime=0)
    (data["root"] / relative).write_bytes(compressed)
    capture = dict(url=url, status=200, sha256=sha, returned_text_utf8_sha256=sha,
                   gzip_file=relative, gzip_sha256=qa.digest(compressed), captured_at="2026-10-11T10:30:00Z")
    metadata = dict(primary_identity_verified=True, article_verified=sponsored, article_body_complete=not video,
                    publication_date_verified=dated, publication_date=day, publication_timestamp=timestamp if dated else None,
                    publication_date_source="visible_article_byline" if dated else "unresolved_primary_publisher_date_conflict",
                    visible_publication_date=visible, canonical_url=url, html_sha256=sha, page_text=body,
                    article_body_characters=len(body), article_body_sha256=qa.digest(body.encode()),
                    source_quality_gate="deferred_video_text" if video else "deferred_sponsored_content_review" if sponsored else "deferred_publication_date",
                    publication_evidence=[dict(source="json_ld_datePublished", timestamp=timestamp),
                                          dict(source="article_published_time", timestamp=timestamp)],
                    editorial_assessment=dict(decision="pending", reason=reason))
    if video:
        metadata.update(publisher_document_type="video", video_identity_verified=True,
                        source_content_unavailable_reason=reason, video_evidence=video_evidence)
    elif sponsored:
        metadata.update(publisher_exception_reason=reason, editorial_hold=reason,
                        publisher_taxonomy=qa.original_taxonomy(article, url), publisher_content_classification="sponsored")
    else:
        metadata.update(publisher_exception_reason=reason, editorial_hold=reason,
                        possible_publication_days=["2026-07-30", "2026-08-06"])
    feed = data["report"]["coverage"][0]["feed"]
    trace = dict(metadata, url=url, status="discovered_metadata_only", reason=reason, feed=feed)
    row = dict(url=url, publication_date=day, publication_date_verified=dated,
               current_core_detected=True, current_core_verified_health=False, metadata_only_candidate=True,
               primary_detail_sha256=sha, primary_detail_captured_at="2026-10-11T10:30:00Z", primary_detail_cache_hit=False,
               original_http_captures=[capture], publication_date_evidence="current_verified_detail" if dated else "unverified",
               exact_reason=reason, passed_gate=None, editorial_outcome="pending", history_present=False, feed_present=False)
    data["report"]["matrix"].append(row)
    data["report"]["publisher_editorial_exceptions"] = [row]
    data["report"]["counts"] = dict(current_core_discovered_urls=80, current_core_verified_health_urls=79, metadata_only_candidates=1)
    data["queue"]["exception"] = dict(source=qa.SOURCE, status="pending", attempts=0, lane="BACKFILL",
                                      raw=dict(url=url, event_date=day, metadata=metadata))
    data["discovery"]["source_details"][qa.SOURCE].append(trace)
    data["discovery"]["sources"][qa.SOURCE]["discovered"] = 80
    data["report"]["primary_coverage"].update(article_content_coverage_complete=sponsored,
        publication_date_coverage_complete=dated, publisher_exceptions=0 if dated else 1, enumerated_with_editorial_exceptions=not dated)
    data["report"]["coverage"][0].update(article_content_coverage_complete=sponsored,
        publication_date_coverage_complete=dated, publisher_exceptions=0 if dated else 1, enumerated_with_editorial_exceptions=not dated)
    return row, metadata, trace


@pytest.mark.parametrize("kind", ["video", "date_conflict", "sponsored"])
def test_proven_publisher_exceptions_pass_only_enumeration_with_explicit_incomplete_dimensions(evidence, kind):
    append_publisher_exception(evidence, kind)
    result = qa.evaluate(**evidence)
    assert result["findings"] == []
    assert result["discovery_qa"] == "PASS"
    assert result["acceptance"] == "NOT_ACCEPTED"
    assert result["checks"]["coverage_dimensions"]["article_content_complete"] is (kind == "sponsored")
    assert result["checks"]["coverage_dimensions"]["publication_dates_complete"] is (kind != "date_conflict")
    assert result["checks"]["window_90"]["detected"] == 79
    proof = result["checks"]["original_publisher_exception_validation"][0]
    assert proof["publication_date_verified"] is (kind != "date_conflict")
    assert proof["article_content_verified"] is (kind != "video")


def test_explicit_unresolved_primary_date_label_preserves_conflict_instead_of_claiming_verified_date(evidence):
    row, metadata, trace = append_publisher_exception(evidence, "date_conflict")
    row["publication_date_evidence"] = "unresolved_primary_publisher_date_conflict"
    result = qa.evaluate(**evidence)
    assert result["findings"] == []
    assert result["checks"]["coverage_dimensions"]["publication_dates_complete"] is False
    assert result["checks"]["original_publisher_exception_validation"][0]["publication_date"] is None
    assert row["publication_date_verified"] is False
    row["publication_date_verified"] = True
    assert "publisher_exception_original_not_verified" in codes(evidence)
    row["publication_date_verified"] = False
    row["publication_date_evidence"] = "current_verified_detail"
    assert "publisher_conflict_falsely_labeled_verified_date" in codes(evidence)


@pytest.mark.parametrize("tamper", ["missing_bytes", "wrong_original_hash", "adopted_date", "invalid_visible_byline", "invented_old_days", "verified_article", "adopted_timestamp", "borrowed_timestamp", "body_hash"])
def test_conflict_exception_cannot_hide_missing_originals_or_invent_a_convenient_date(evidence, tamper):
    row, metadata, trace = append_publisher_exception(evidence, "date_conflict")
    if tamper == "missing_bytes":
        row["original_http_captures"] = []
    elif tamper == "wrong_original_hash":
        row["original_http_captures"][0]["sha256"] = "b" * 64
    elif tamper == "adopted_date":
        metadata["publication_date"] = "2026-07-30"
    elif tamper == "invalid_visible_byline":
        metadata["visible_publication_date"] = "not-a-date"
    elif tamper == "invented_old_days":
        metadata["possible_publication_days"] = ["2020-01-01"]
    elif tamper == "verified_article":
        metadata["article_verified"] = True
    elif tamper == "adopted_timestamp":
        metadata["publication_timestamp"] = "2026-07-30T15:00:00Z"
    elif tamper == "borrowed_timestamp":
        metadata["publication_evidence"].append(dict(timestamp="2026-07-30T11:00:00Z"))
    else:
        metadata["article_body_sha256"] = "b" * 64
    assert "publisher_exception_original_not_verified" in codes(evidence)


@pytest.mark.parametrize("tamper", ["unbound_video", "shared_wrapper_body", "content_claim", "fake_date", "missing_text_hold", "published"])
def test_video_without_text_cannot_be_upgraded_to_verified_text_or_published(evidence, tamper):
    row, metadata, trace = append_publisher_exception(evidence, "video")
    if tamper == "unbound_video":
        metadata["video_evidence"]["id"] = BASE + "other/#video"
    elif tamper == "shared_wrapper_body":
        metadata["page_text"] = "Compartir: Facebook WhatsApp Twitter LinkedIn." * 5
        metadata["article_body_characters"] = len(metadata["page_text"])
        metadata["article_body_sha256"] = qa.digest(metadata["page_text"].encode())
    elif tamper == "content_claim":
        metadata["article_body_complete"] = True
    elif tamper == "fake_date":
        metadata["publication_date"] = row["publication_date"] = "2026-10-08"
    elif tamper == "missing_text_hold":
        metadata["editorial_assessment"]["reason"] = "analysis_unavailable"
    else:
        evidence["history"].append(dict(source_url=row["url"], evidence_maturity="media_reported"))
    result = qa.evaluate(**evidence)
    assert result["discovery_qa"] == "FAIL"
    assert result["acceptance"] == "NOT_ACCEPTED"


def test_publisher_exception_does_not_excuse_transport_errors_or_frozen_control_omissions(evidence):
    row, metadata, trace = append_publisher_exception(evidence, "video")
    evidence["discovery"]["source_details"][qa.SOURCE].append(dict(status="detail_error", url=BASE + "unfetched/", reason="HTTP Error 503"))
    evidence["discovery"]["source_details"][qa.SOURCE][0]["status"] = "excluded"
    assert {"unresolved_transport_or_primary_parser_errors", "important_external_control_omissions"} <= codes(evidence)


@pytest.mark.parametrize("dimension", ["article_content_coverage_complete", "publication_date_coverage_complete"])
def test_exception_coverage_cannot_claim_all_content_and_dates_verified(evidence, dimension):
    append_publisher_exception(evidence, "date_conflict")
    evidence["report"]["coverage"][0][dimension] = True
    evidence["report"]["primary_coverage"][dimension] = True
    assert qa.evaluate(**evidence)["discovery_qa"] == "FAIL"


def test_metadata_inventory_count_is_separate_from_textual_recall(evidence):
    append_publisher_exception(evidence, "video")
    assert qa.evaluate(**evidence)["discovery_qa"] == "PASS"
    evidence["report"]["counts"]["current_core_verified_health_urls"] = 80
    assert "reported_inventory_partition_not_supported_by_core" in codes(evidence)


def test_date_conflict_can_never_corroborate_old_boundary(evidence):
    old_boundary(evidence)
    detail = next(row for row in evidence["discovery"]["source_details"][qa.SOURCE] if row.get("url") == BASE + "old-0/")
    detail.update(status="discovered_metadata_only", publication_date=None, publication_date_verified=False,
                  publisher_exception_reason=qa.DATE_HOLD)
    assert "public_api_boundary_original_detail_date_unverified" in codes(evidence)


def test_verified_metadata_video_date_can_corroborate_temporal_boundary(evidence):
    old_boundary(evidence)
    detail = next(row for row in evidence["discovery"]["source_details"][qa.SOURCE] if row.get("url") == BASE + "old-0/")
    # Outside-window videos are excluded from queue but may retain verified
    # primary dates. No claim of content, materiality or publication follows.
    detail.update(publication_date_verified=True, article_body_complete=False,
                  publisher_document_type="video", source_content_unavailable_reason=qa.VIDEO_HOLD)
    assert qa.evaluate(**evidence)["discovery_qa"] == "PASS"


def original_exception_evidence(record, root):
    """Source emits a candidate; the independent reader checks the raw bytes."""
    from radar_salud.pulso_source import ConflictingPublicationArticle, SponsoredArticle, TextUnavailableArticle, extract_article
    folder = root / "tests/fixtures/pulso_editorial_exception_real"
    compressed = (folder / record["gzip_file"]).read_bytes()
    raw = gzip.decompress(compressed)
    assert qa.digest(compressed) == record["gzip_sha256"]
    assert qa.digest(raw) == record["sha256"]
    text = raw.decode(record.get("charset") or "utf-8")
    try:
        extract_article(text, record["url"])
    except (ConflictingPublicationArticle, SponsoredArticle, TextUnavailableArticle) as exception:
        metadata, body = dict(exception.metadata), exception.body
        reason = qa.DATE_HOLD if isinstance(exception, ConflictingPublicationArticle) else qa.SPONSORED_HOLD if isinstance(exception, SponsoredArticle) else qa.VIDEO_HOLD
    else:
        raise AssertionError("Expected a genuine retained publisher exception")
    sha = qa.digest(text.encode())
    metadata.update(page_text=body, article_body_characters=len(body), article_body_sha256=qa.digest(body.encode()),
                    html_sha256=sha, source_quality_gate="deferred_publication_date" if reason == qa.DATE_HOLD else "deferred_sponsored_content_review" if reason == qa.SPONSORED_HOLD else "deferred_video_text")
    capture = dict(record, gzip_file=str(Path("tests/fixtures/pulso_editorial_exception_real") / record["gzip_file"]))
    row = dict(url=record["url"], publication_date=metadata["publication_date"],
               publication_date_verified=metadata["publication_date_verified"], primary_detail_sha256=sha,
               original_http_captures=[capture])
    trace = dict(metadata, status="discovered_metadata_only", url=record["url"], reason=reason)
    return row, metadata, trace


@pytest.mark.parametrize("slug", ["desocupacion-llega-a-95-", "el-trabajo-tambien-puede-enfermar-", "asi-son-los-infartos-", "atencion-medica-domiciliaria-"])
def test_all_four_original_publisher_conflicts_preserve_distinct_primary_byline_and_metadata_instants(slug):
    root = Path(__file__).parents[1]
    manifest = json.loads((root / "tests/fixtures/pulso_editorial_exception_real/manifest.json").read_text())
    record = next(row for row in manifest["requests"] if slug in row["url"])
    row, metadata, trace = original_exception_evidence(record, root)
    proof, error = qa.verify_publisher_exception(row, metadata, [trace], root)
    assert error is None
    assert proof["publication_date"] is None
    assert proof["publication_date_verified"] is False
    assert proof["article_content_verified"] is True
    assert proof["publisher_date_convention"] is None
    assert all(value["timestamp"] not in proof["original_primary_timestamps"] for value in proof["original_primary_bylines"])
    assert metadata["publication_timestamp"] is None
    row["primary_detail_cache_hit"] = True
    assert qa.verify_publisher_exception(row, metadata, [trace], root)[1] is None
    row["original_http_captures"][0]["original_capture_manifest_sha256"] = "b" * 64
    assert qa.verify_publisher_exception(row, metadata, [trace], root)[1]
    row["original_http_captures"][0]["original_capture_manifest_sha256"] = record["original_capture_manifest_sha256"]
    # The date can only remain unresolved. Both plausible calendars survive.
    metadata["publication_date"] = proof["visible_publication_date"]
    assert qa.verify_publisher_exception(row, metadata, [trace], root)[1]


def test_all_twenty_retained_primary_videos_without_text_require_independent_original_proof():
    from radar_salud.pulso_source import TextUnavailableArticle, extract_article
    root = Path(__file__).parents[1]
    folder = root / "tests/fixtures/pulso_editorial_exception_real"
    manifest = json.loads((folder / "manifest.json").read_text())
    checked = []
    for record in manifest["requests"]:
        if "/videos/noticia/" not in record["url"]:
            continue
        raw = gzip.decompress((folder / record["gzip_file"]).read_bytes())
        try:
            extract_article(raw.decode(record.get("charset") or "utf-8"), record["url"])
        except TextUnavailableArticle:
            row, metadata, trace = original_exception_evidence(record, root)
            proof, error = qa.verify_publisher_exception(row, metadata, [trace], root)
            assert error is None, (record["url"], error)
            assert proof["publication_date_verified"] is True
            assert proof["article_content_verified"] is False
            assert proof["body_characters"] < 160
            checked.append(proof)
    assert len(checked) == 20
    alzheimer = next(row for row in checked if "descubren-doble-avance" in row["url"])
    assert alzheimer["body_characters"] == 84


def test_conflicting_byline_exception_cannot_borrow_a_navigation_or_invalid_time(evidence):
    row, metadata, trace = append_publisher_exception(evidence, "date_conflict")
    record = row["original_http_captures"][0]
    path = evidence["root"] / record["gzip_file"]
    raw = gzip.decompress(path.read_bytes()).decode()
    raw = raw.replace('<time class="article-body__byline__date"', '<nav><time class="article-body__byline__date"').replace('</time>', '</time></nav>')
    raw = raw.encode()
    compressed = gzip.compress(raw, mtime=0)
    path.write_bytes(compressed)
    sha = qa.digest(raw)
    record.update(sha256=sha, returned_text_utf8_sha256=sha, gzip_sha256=qa.digest(compressed))
    row["primary_detail_sha256"] = metadata["html_sha256"] = trace["html_sha256"] = sha
    assert "publisher_exception_original_not_verified" in codes(evidence)


def test_engine_completion_cannot_credit_source_traces_when_source_raised_before_registration(evidence):
    evidence["discovery"]["sources"][qa.SOURCE].update(discovered=0, error_type="TypeError")
    evidence["report"]["source_inventory_returned_to_core"] = False
    result = qa.evaluate(**evidence)
    assert result["discovery_qa"] == "FAIL"
    assert result["checks"]["window_90"]["detected"] == 0
    assert result["checks"]["core_inventory_registration"]["text_candidate_trace_urls"] == 79
    assert result["checks"]["core_inventory_registration"]["returned_to_core"] is False
    assert "core_source_error_or_inventory_not_registered" in {row["code"] for row in result["findings"]}


def test_partial_source_returns_actual_candidates_but_still_fails_acceptance(evidence):
    evidence["discovery"]["sources"][qa.SOURCE]["error_type"] = "partial_discovery"
    result = qa.evaluate(**evidence)
    assert result["checks"]["window_90"]["detected"] == 79
    assert result["discovery_qa"] == "FAIL"
    assert result["acceptance"] == "NOT_ACCEPTED"


def test_source_return_count_cannot_be_replaced_by_positive_candidate_trace_count(evidence):
    evidence["discovery"]["sources"][qa.SOURCE]["discovered"] = 1
    assert "source_returned_inventory_count_not_supported_by_traces" in codes(evidence)


def test_named_retention_provenance_cannot_be_invented_without_bound_real_manifest(evidence):
    row, metadata, trace = append_publisher_exception(evidence, "video")
    row["primary_detail_cache_hit"] = True
    record = row["original_http_captures"][0]
    record.update(capture_provenance="preserved_original_cold_core_editorial_or_video_exception",
                  original_capture_manifest_sha256="a" * 64)
    assert qa.verify_publisher_exception(row, metadata, [trace], evidence["root"])[1]


@pytest.mark.parametrize("slug", ["cardenal-chomali-", "revive-el-primer-capitulo-", "fundacion-coanil-"])
def test_all_three_dated_original_sponsored_articles_keep_a_distinct_commercial_editorial_hold(slug):
    root = Path(__file__).parents[1]
    manifest = json.loads((root / "tests/fixtures/pulso_editorial_exception_real/manifest.json").read_text())
    record = next(row for row in manifest["requests"] if slug in row["url"])
    row, metadata, trace = original_exception_evidence(record, root)
    proof, error = qa.verify_publisher_exception(row, metadata, [trace], root)
    assert error is None, (record["url"], error)
    assert proof["reason"] == qa.SPONSORED_HOLD
    assert proof["publication_date_verified"] is True
    assert proof["article_content_verified"] is True
    assert metadata["publisher_taxonomy"]["classification"] == "sponsored"
    assert metadata["article_verified"] is True
    assert metadata["editorial_assessment"] == dict(decision="pending", reason=qa.SPONSORED_HOLD)


@pytest.mark.parametrize("tamper", ["fake_commercial_section", "borrowed_keywords", "classification", "dropped_hold", "gate_pass", "published"])
def test_sponsor_exception_requires_exact_original_taxonomy_and_cannot_claim_editorial_approval(evidence, tamper):
    row, metadata, trace = append_publisher_exception(evidence, "sponsored")
    if tamper == "fake_commercial_section":
        metadata["publisher_taxonomy"]["section"] = "Publirreportajes"
    elif tamper == "borrowed_keywords":
        metadata["publisher_taxonomy"]["labels"].append("Opinión")
    elif tamper == "classification":
        metadata["publisher_content_classification"] = "factual"
    elif tamper == "dropped_hold":
        metadata["editorial_hold"] = ""
    elif tamper == "gate_pass":
        metadata["editorial_assessment"].update(decision="published", relevance_score=90, threshold=72)
        row["passed_gate"] = True
    else:
        evidence["snapshot"]["signals"].append(dict(source_url=row["url"], evidence_maturity="media_reported"))
    assert qa.evaluate(**evidence)["discovery_qa"] == "FAIL"


def test_incidental_opinion_or_commercial_words_in_prose_never_supply_publisher_taxonomy():
    article = {"@type": "NewsArticle", "articleSection": "Nacional", "keywords": ["salud", "opiniones de expertos"],
               "articleBody": "Una opinión sobre anuncios branded y financiación de hospitales."}
    assert qa.original_taxonomy(article, BASE + "factual/")["classification"] == "factual"
    article["articleSection"] = "Branded"
    assert qa.original_taxonomy(article, BASE + "factual/")["classification"] == "factual"
    article["keywords"].append("Columna")
    assert qa.original_taxonomy(article, BASE + "factual/")["classification"] == "opinion"


def test_full_http_capture_is_indexed_once_without_skipping_failed_or_duplicate_responses(evidence, monkeypatch):
    """Real captures contain thousands of HTML requests alongside API pages."""
    original = qa.api_page_key
    calls = []
    def counted(url):
        calls.append(url)
        return original(url)
    records = list(evidence["captures"])
    first = records[0]
    records += [dict(first, status=503), dict(first)]
    records += [dict(url=BASE + f"original-{i}/", status=200, sha256="b" * 64) for i in range(2000)]
    monkeypatch.setattr(qa, "api_page_key", counted)
    evidence["captures"] = records
    assert qa.evaluate(**evidence)["discovery_qa"] == "PASS"
    assert len(calls) == len(records)
    key = original(first["url"])
    assert len(qa.api_capture_index(records)[key]) == 3
    # The failed response does not become proof when successful bytes vanish.
    evidence["captures"] = [dict(row, status=503) if original(row["url"]) == key else row for row in records]
    assert "public_api_http_chain_unproven" in codes(evidence)
