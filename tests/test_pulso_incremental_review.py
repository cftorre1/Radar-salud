"""Review application is constrained to verified evidence and three legacy holds."""
import gzip
import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar_salud import pulso_incremental_review as review
from radar_salud.models import RawItem
from radar_salud.pending_queue import fingerprint
from pulso_editorial_test_support import valid_assessment


AUDIT = json.loads(review.REVIEW_PATH.read_text(encoding="utf-8"))
ENTRIES = {entry["publication_date"]: entry for entry in AUDIT["reviews"]}
BODIES = {
    "2026-10-05": "La ministra aborda el presupuesto 2027 y el alza de 4,7%, junto a las prioridades ya anunciadas. ",
    "2026-10-07": "La propuesta de Presupuesto 2027 considera APS y Ley Ricarte Soto: $189.696 millones frente a $166.951 millones. ",
    "2026-07-14": "En mayo las isapres registraron 17.539 contratos suscritos frente a 17.487 desahucios y 52 suscripciones netas. ",
}


def candidate(day="2026-10-07"):
    entry = ENTRIES[day]
    body = BODIES[day] * 3
    return RawItem(
        "pulso_latercera", "Artículo sintético para aplicar revisión de evidencia",
        entry["source_url"], "Pulso / La Tercera", "press_high_trust", day,
        raw_text=body[:100], metadata={
            "article_verified": True, "source_quality_gate": "passed", "market_role": "media",
            "canonical_url": entry["source_url"], "publication_date": day,
            "publication_date_source": "visible_article_byline", "visible_publication_date": day,
            "publication_timestamp": day + "T12:00:00-03:00",
            "publication_evidence": [{"source": "json_ld_datePublished",
                                      "timestamp": day + "T15:00:00Z", "publisher_day": day}],
            "captured_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            "html_sha256": hashlib.sha256(b"synthetic URL-bound verified HTML fixture").hexdigest(),
            "article_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "page_text": body, "editorial_hold": review.LEGACY_HOLD,
            "editorial_assessment": {"decision": "pending", "reason": "awaiting_verification"},
            "event_equivalence_review": [{"source_url": entry["compared_signal"]["source_url"],
                                          "publication_date": entry["compared_signal"]["publication_date"]}],
            "ingestion_mode": "BACKFILL", "detected_at": "2026-10-11T04:36:44.044688+00:00",
            "attempts": 3, "retry_at": "2026-10-11T07:00:00+00:00",
        })


def test_verified_review_enters_real_editorial_processor_with_comparison_and_unchanged_gate(monkeypatch):
    from radar_salud import llm_analysis
    from radar_salud.beta_sources import process_curated_beta_source
    raw = candidate()
    calls = []
    def analysis(**kwargs):
        calls.append(kwargs)
        return valid_assessment({"relevance_score": 71, "what_happened": "", "why_it_matters": "",
                "reason": "No supera el gate editorial vigente."}, kwargs)
    monkeypatch.setattr(llm_analysis, "analyze_news", analysis)
    assert process_curated_beta_source(raw, {}) is None
    assert len(calls) == 1
    assert "budget_proposal_not_enacted" in calls[0]["kind"]
    assert "2026-10-01" in calls[0]["kind"]
    assert "no aprueba publicación" in calls[0]["kind"]
    assert raw.metadata["editorial_assessment"]["threshold"] == 72
    assert raw.metadata["rejection_reason"] == "editorial_relevance_below_threshold"


def test_legacy_detail_verification_records_provenance_before_review_and_analysis(monkeypatch):
    from radar_salud import beta_sources, llm_analysis
    raw = candidate()
    body = raw.metadata["page_text"]
    raw.metadata["article_verified"] = False
    for field in ("page_text", "html_sha256", "article_body_sha256", "captured_at"):
        del raw.metadata[field]
    node = {"@type": "NewsArticle", "url": raw.url,
            "headline": "Presupuesto de salud 2027: cambios en APS y Ley Ricarte Soto",
            "datePublished": "2026-10-07T12:00:00-03:00", "articleBody": body}
    html = (f'<link rel="canonical" href="{raw.url}">'
            + '<script type="application/ld+json">' + json.dumps(node) + '</script>')
    monkeypatch.setattr(beta_sources, "fetch_html", lambda url: html)
    monkeypatch.setattr(llm_analysis, "analyze_news", lambda **kwargs: valid_assessment({
        "relevance_score": 71, "what_happened": "", "why_it_matters": "", "reason": "reviewed"}, kwargs))
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert raw.metadata["html_sha256"] == hashlib.sha256(html.encode()).hexdigest()
    assert raw.metadata["article_body_sha256"] == hashlib.sha256(" ".join(body.split()).encode()).hexdigest()
    assert raw.metadata["incremental_review"]["publication_approved"] is False
    assert "editorial_hold" not in raw.metadata


@pytest.mark.parametrize("day", ["2026-10-07", "2026-07-14"])
def test_releases_only_duplicate_hold_with_context_for_unchanged_editorial_gate(day):
    raw = candidate(day)
    original = deepcopy(asdict(raw))
    queue_row = {"source": raw.source_slug, "lane": "BACKFILL", "status": "retry",
                 "detected_at": original["metadata"]["detected_at"], "attempts": 3,
                 "retry_at": original["metadata"]["retry_at"], "raw": original}
    bookkeeping = deepcopy({key: value for key, value in queue_row.items() if key != "raw"})
    original_key = fingerprint(raw)
    assert review.apply_incremental_review(raw)
    assert "editorial_hold" not in raw.metadata
    assert fingerprint(raw) == original_key
    assert {key: value for key, value in asdict(raw).items() if key != "metadata"} == {
        key: value for key, value in original.items() if key != "metadata"}
    assert raw.metadata["editorial_assessment"] == original["metadata"]["editorial_assessment"]
    for key in ("ingestion_mode", "detected_at", "attempts", "retry_at", "event_equivalence_review"):
        assert raw.metadata[key] == original["metadata"][key]
    queue_row["raw"] = asdict(raw)
    assert {key: value for key, value in queue_row.items() if key != "raw"} == bookkeeping
    resolution = raw.metadata["incremental_review"]
    assert resolution["decision"] == "release_hold_for_editorial_analysis"
    assert resolution["review_ref"] == review.REVIEW_REF
    assert resolution["review_sha256"] == review.REVIEW_SHA256
    assert resolution["verified_body_sha256"] == raw.metadata["article_body_sha256"]
    context = raw.metadata["editorial_review_context"]
    assert context["publication_approved"] is False
    assert context["evidence_maturity"] == "media_reported"
    assert context["media_materiality_threshold"] == 72
    assert context["compared_signal"] == ENTRIES[day]["compared_signal"]
    assert not {"scores", "editorial_relevance", "publication_ready_score"} & raw.metadata.keys()
    snapshot = deepcopy(raw.metadata)
    assert not review.apply_incremental_review(raw)
    assert raw.metadata == snapshot


def test_budget_context_preserves_proposal_coverage_and_nominal_real_caveats():
    raw = candidate()
    assert review.apply_incremental_review(raw)
    context = raw.metadata["editorial_review_context"]
    assert context["event_status"] == "budget_proposal_not_enacted"
    assert context["compared_signal"]["publication_date"] == "2026-10-01"
    assert {x["change_basis"] for x in context["new_incremental_fields"]} == {"real", "nominal"}
    assert any("continuity is protected" in text for text in context["interpretation_constraints"])
    assert any("Internal Error" in text for text in context["limitations"])


def test_membership_context_keeps_may_signing_flow_distinct_from_july_stock():
    raw = candidate("2026-07-14")
    assert review.apply_incremental_review(raw)
    context = raw.metadata["editorial_review_context"]
    assert context["event_status"] == "historical_reported_measurement_not_current_october_event"
    metrics = context["metric_comparison"]
    assert metrics["pulso"]["reference_month"] == "2026-05"
    assert metrics["pulso"]["net_contracts"] == 52
    assert metrics["pulso"]["effective_contributor_stock_change"] is None
    assert metrics["df"]["reference_month"] == "2026-07"
    assert metrics["df"]["stock_change"] == 525
    assert any("reject or defer" in text for text in context["interpretation_constraints"])


def test_generic_budget_remains_held_with_exact_reviewed_deferral_reason():
    raw = candidate("2026-10-05")
    assert review.apply_incremental_review(raw)
    reason = "duplicate_budget_announcement_no_verified_material_increment"
    assert raw.metadata["editorial_hold"] == reason
    assert raw.metadata["editorial_assessment"] == {"decision": "pending", "reason": reason}
    assert raw.metadata["incremental_review"]["previous_hold"] == review.LEGACY_HOLD
    snapshot = deepcopy(raw.metadata)
    assert not review.apply_incremental_review(raw)
    assert raw.metadata == snapshot


@pytest.mark.parametrize("changes", [
    {"article_verified": False}, {"article_verified": "true"},
    {"source_quality_gate": "pending"}, {"market_role": "provider"},
    {"canonical_url": "https://www.latercera.com/nacional/noticia/other/"},
    {"publication_date": "2026-10-06"}, {"publication_date_source": "listing_date"},
    {"visible_publication_date": "2026-10-06"}, {"visible_publication_date": None},
    {"publication_evidence": []}, {"publication_evidence": None},
    {"publication_evidence": [{"source": "json_ld_datePublished", "timestamp": "2026-10-06", "publisher_day": "2026-10-07"}]},
    {"publication_timestamp": "2026-10-07T12:00:00"},
    {"page_text": "brief listing excerpt"}, {"page_text": None},
    {"article_body_sha256": "0" * 64}, {"html_sha256": "invalid"},
    {"captured_at": "2026-10-10T20:00:00Z"}, {"captured_at": "2026-10-11T06:00:00"},
    {"captured_at": "invalid"}, {"captured_at": "2099-10-11T06:00:00Z"},
    {"editorial_hold": "requires_legal_review"},
    {"editorial_assessment": {"decision": "rejected"}},
    {"editorial_assessment": {"decision": "published"}},
    {"editorial_assessment": None}, {"queue_status": "published"},
    {"event_equivalence_review": []},
    {"event_equivalence_review": [{"source_url": "https://example.org/unreviewed", "publication_date": "2026-10-01"}]},
])
def test_unverified_stale_mismatched_or_arbitrary_hold_is_untouched(changes):
    raw = candidate()
    raw.metadata.update(changes)
    original = deepcopy(asdict(raw))
    assert not review.apply_incremental_review(raw)
    assert asdict(raw) == original


@pytest.mark.parametrize("field,value", [
    ("url", "https://www.latercera.com/nacional/noticia/other/"),
    ("url", ENTRIES["2026-10-07"]["source_url"] + "?copied=1"),
    ("event_date", "2026-10-06"), ("source_slug", "df"), ("source_type", "official"),
])
def test_only_exact_reviewed_source_url_and_publication_day_can_be_applied(field, value):
    raw = candidate()
    setattr(raw, field, value)
    original = deepcopy(asdict(raw))
    assert not review.apply_incremental_review(raw)
    assert asdict(raw) == original


def test_additional_unreviewed_event_equivalence_blocks_release():
    raw = candidate()
    raw.metadata["event_equivalence_review"].append({"source_url": "https://example.org/new-hold", "publication_date": "2026-10-07"})
    original = deepcopy(raw.metadata)
    assert not review.apply_incremental_review(raw)
    assert raw.metadata == original


def test_matching_hash_of_changed_article_does_not_reuse_stale_review_facts():
    raw = candidate()
    body = "La propuesta presupuestaria 2027 fue revisada y ahora contiene otras cantidades que requieren nueva revisión. " * 3
    raw.metadata.update(page_text=body, article_body_sha256=hashlib.sha256(body.encode()).hexdigest())
    original = deepcopy(raw.metadata)
    assert not review.apply_incremental_review(raw)
    assert raw.metadata == original


def test_audit_modified_or_missing_fails_closed(tmp_path, monkeypatch):
    raw = candidate()
    original = deepcopy(raw.metadata)
    audit_path = tmp_path / "review.json"
    monkeypatch.setattr(review, "REVIEW_PATH", audit_path)
    assert not review.apply_incremental_review(raw)
    audit_path.write_bytes(review.REVIEW_SHA256.encode())
    assert not review.apply_incremental_review(raw)
    edited = deepcopy(AUDIT)
    edited["reviews"][0]["publication_approved"] = True
    audit_path.write_text(json.dumps(edited), encoding="utf-8")
    assert not review.apply_incremental_review(raw)
    assert raw.metadata == original


def original_midnight_candidate():
    """Replay the retained publisher bytes, including its July 14 byline."""
    from radar_salud.pulso_source import article_body_evidence, extract_article
    digest = "404af1941f27b1f23eeb6f9d226cb8c1e680f7fa622f527287c291d904a8f1e1"
    fixture = Path(__file__).parents[1] / "tests/fixtures/pulso_runtime_real" / (digest + ".html.gz")
    compressed = fixture.read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == "ab0f03dcd224fa94c4b91eb2e1937a38fe2ed81db00fa4f46c6da7bc81a5a70f"
    original = gzip.decompress(compressed)
    assert hashlib.sha256(original).hexdigest() == digest
    entry = ENTRIES["2026-07-14"]
    title, body, metadata = extract_article(original.decode("utf-8"), entry["source_url"])
    assert metadata["publication_date"] == metadata["visible_publication_date"] == "2026-07-14"
    assert metadata["publication_timestamp"] == "2026-07-14T00:36:58.91Z"
    assert metadata["publisher_date_convention"] == "timestamp_calendar"
    assert metadata["primary_identity_verified"] is metadata["publication_date_verified"] is True
    assert len(body) == 5432
    assert hashlib.sha256(body.encode()).hexdigest() == "35ce3696d5b7b638452ffe3aa8783bfaef251cb7809efae3962f51aac3f2dffb"
    metadata.update(article_body_evidence(body), market_role="media", source_quality_gate="passed",
                    html_sha256=digest, captured_at="2026-10-11T07:12:12.446358+00:00",
                    editorial_hold=review.LEGACY_HOLD,
                    event_equivalence_review=[{"source_url": entry["compared_signal"]["source_url"],
                                              "publication_date": entry["compared_signal"]["publication_date"]}])
    return RawItem("pulso_latercera", title, entry["source_url"], "Pulso / La Tercera",
                   "press_high_trust", metadata["publication_date"], raw_text=body[:1800], metadata=metadata)


def test_real_midnight_byline_releases_only_for_analysis_preserving_may_flow_and_july_stock():
    raw = original_midnight_candidate()
    original_key = fingerprint(raw)
    assert review._publisher_day(raw.metadata["publication_timestamp"]) == "2026-07-13"
    assert {entry["publisher_day"] for entry in raw.metadata["publication_evidence"]} == {"2026-07-14"}
    assert review.apply_incremental_review(raw)
    assert raw.event_date == "2026-07-14" and fingerprint(raw) == original_key
    assert "editorial_hold" not in raw.metadata
    assert raw.metadata["incremental_review"]["decision"] == "release_hold_for_editorial_analysis"
    context = raw.metadata["editorial_review_context"]
    assert context["metric_comparison"]["pulso"]["net_contracts"] == 52
    assert context["metric_comparison"]["df"]["stock_change"] == 525
    assert context["media_materiality_threshold"] == 72
    assert context["publication_approved"] is False
    assert "editorial_relevance" not in raw.metadata


def test_real_midnight_article_still_fails_unchanged_editorial_gate_at_71(monkeypatch):
    from radar_salud import llm_analysis
    from radar_salud.beta_sources import process_curated_beta_source
    raw = original_midnight_candidate()
    calls = []
    def analysis(**kwargs):
        calls.append(kwargs)
        return valid_assessment({"relevance_score": 71, "what_happened": "", "why_it_matters": "",
                "reason": "El antecedente no agrega un cambio material suficiente."}, kwargs)
    monkeypatch.setattr(llm_analysis, "analyze_news", analysis)
    assert process_curated_beta_source(raw, {}) is None
    assert len(calls) == 1 and calls[0]["full_text"] is True
    assert calls[0]["text"] == raw.metadata["page_text"]
    assert "net_contracts" in calls[0]["kind"] and "stock_change" in calls[0]["kind"]
    assert raw.metadata["editorial_assessment"]["threshold"] == 72
    assert raw.metadata["editorial_assessment"]["relevance_score"] == 71
    assert raw.metadata["rejection_reason"] == "editorial_relevance_below_threshold"


@pytest.mark.parametrize("changes", [
    {"publisher_date_convention": None},
    {"primary_identity_verified": False},
    {"publication_date_verified": False},
    {"publication_date_source": "json_ld_datePublished"},
    {"visible_publication_date": None},
    {"visible_publication_date": "2026-07-13"},
    {"possible_publication_days": ["2026-07-13", "2026-07-14"]},
    {"publisher_exception_reason": "publisher_conflicting_publication_dates"},
    {"publication_date": None, "publication_timestamp": None,
     "publication_date_verified": False, "source_quality_gate": "deferred_publication_date"},
])
def test_real_midnight_convention_cannot_override_missing_byline_or_conflict(changes):
    raw = original_midnight_candidate()
    raw.metadata.update(changes)
    if raw.metadata["publication_date"] is None:
        raw.event_date = None
    before = deepcopy(asdict(raw))
    assert not review.apply_incremental_review(raw)
    assert asdict(raw) == before


@pytest.mark.parametrize("field,value", [
    ("timestamp_calendar_day", "2026-07-13"),
    ("america_santiago_day", "2026-07-14"),
    ("publisher_day", "2026-07-13"),
    ("timestamp", "2026-07-15T00:36:58.91Z"),
    ("timestamp_calendar_day", None),
])
def test_real_midnight_primary_evidence_must_agree_without_per_field_date_choice(field, value):
    raw = original_midnight_candidate()
    raw.metadata["publication_evidence"][0][field] = value
    before = deepcopy(asdict(raw))
    assert not review.apply_incremental_review(raw)
    assert asdict(raw) == before
