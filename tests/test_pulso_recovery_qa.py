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
        controls.append(dict(url=url, publication_date=day, recall_expected=True))
        metadata = dict(article_verified=True, source_quality_gate="passed", canonical_url=url,
                        publication_date=day, page_text="El hospital amplía capacidad para reducir listas de espera. " * 5,
                        html_sha256=sha, publication_date_source="json_ld_datePublished", publication_timestamp=day + "T15:00:00Z")
        queue[str(i)] = dict(source=qa.SOURCE, status="pending", lane="BACKFILL", attempts=0,
                             detected_at="2026-10-11T10:30:00Z", raw=dict(url=url, event_date=day, metadata=metadata))
        details.append(dict(url=url, status="discovered", publication_date=day))
        matrix.append(dict(url=url, publication_date=day, current_core_detected=True,
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
                  unresolved_pending_operational_reasons=[])
    workflow = tmp_path / ".github/workflows"
    workflow.mkdir(parents=True)
    env = "env:\n  RADAR_FAST_PER_RUN: 120\n  RADAR_DEEP_PER_RUN: 15\n  RADAR_FAST_PER_MONTH: 1500\n  RADAR_DEEP_PER_MONTH: 180\n"
    for name in ("daily-radar.yml", "pulso-runtime-recovery.yml"):
        (workflow / name).write_text(env)
    return dict(report=report, control=control, root=tmp_path, discovery={"source_details": {qa.SOURCE: details}},
                queue=queue, history=[], snapshot={"signals": []}, telemetry=[], captures=captures)


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


def test_internal_complete_summary_cannot_replace_original_api_boundary_json(evidence):
    evidence["captures"] = []
    assert "public_api_http_chain_unproven" in codes(evidence)
    assert qa.evaluate(**evidence)["discovery_qa"] == "FAIL"


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
