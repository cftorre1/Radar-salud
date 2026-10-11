"""Review application is constrained to verified evidence and three legacy holds."""
import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from radar_salud import pulso_incremental_review as review
from radar_salud.models import RawItem
from radar_salud.pending_queue import fingerprint


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
