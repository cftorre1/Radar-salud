"""The recovery manifest keeps every reviewed original and no verdict shortcut."""
import hashlib
import json
from pathlib import Path

from radar_salud.queue_selection import load_queue_selection

ROOT = Path(__file__).resolve().parents[1]
COHORT = ROOT / "data/audits/pulso_material_recovery_cohort_2026_10_11.json"


def test_all_primary_controls_and_all_additional_review_candidates_are_bound_to_original_bodies():
    cohort = json.loads(COHORT.read_text())
    selection = load_queue_selection(COHORT, ["pulso_latercera"])
    assert len(selection.urls) == len(cohort["items"]) == 113
    assert set(selection.urls) == {item["url"] for item in cohort["items"]}
    primary_path = ROOT / cohort["inputs"]["independent_primary_review"]["path"]
    primary = json.loads(primary_path.read_text())["all_controls"]
    primary_by = {row["url"]: row for row in primary}
    expanded_path = ROOT / cohort["inputs"]["expanded_negative_review"]["path"]
    expanded = json.loads(expanded_path.read_text())["all_287_initial_negative_full_body_semantic_reviews"]
    expanded_by = {row["url"]: row for row in expanded}
    assert hashlib.sha256(primary_path.read_bytes()).hexdigest() == cohort["inputs"]["independent_primary_review"]["sha256"]
    assert hashlib.sha256(expanded_path.read_bytes()).hexdigest() == cohort["inputs"]["expanded_negative_review"]["sha256"]
    materials = {row["url"] for row in expanded if row["independent_review_decision"] == "concrete_false_negative_for_editorial_analysis"}
    uncertainties = {row["url"] for row in expanded if row["independent_review_decision"] == "uncertain_requires_editorial_review"}
    # Whole independent groups, including disagreements and defensible controls.
    assert len(materials) == 20 and len(uncertainties) == 17 and len(primary_by) == 79
    assert set(selection.urls) == set(primary_by) | materials | uncertainties
    for item in cohort["items"]:
        if item["url"] in primary_by:
            original = primary_by[item["url"]]
            assert original["primary_body_sha256"] == item["body_sha256"]
            assert original["publication_day_adopted"] == item["publication_date"]
            assert original["primary_body_characters"] == item["body_characters"]
        if item["url"] in expanded_by and item["url"] in materials | uncertainties:
            original = expanded_by[item["url"]]
            assert original["full_body_read"] is True
            assert original["fullbody_sha256"] == item["body_sha256"]
            assert original["publication_date"] == item["publication_date"]
            assert original["body_characters"] == item["body_characters"]
        assert item["already_returned_to_real_core"] is True
        assert item["original_body_and_day_exact"] is True
        assert item["stored_queue_status"] == "pending" and item["stored_attempts"] == 0
        assert item["actual_gate_decision"] is None and item["relevance_score"] is None
        assert item["actual_ai_outcome"] is None and item["publication_approved"] is False
        assert item["editorial_threshold"] == 72 and item["evidence_maturity"] == "media_reported"
        for ref in item["primary_review_references"]:
            path = ROOT / ref["path"]
            assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == ref["sha256"]


def test_cohort_preserves_frozen_recall_budget_and_untouched_nonselected_backlog():
    cohort = json.loads(COHORT.read_text())
    frozen = ROOT / cohort["inputs"]["frozen_control"]["path"]
    assert hashlib.sha256(frozen.read_bytes()).hexdigest() == "b9c3ce2aea38107797fc19572581f27884d15611214fd2328d458bd35e906374"
    counts = cohort["counts"]
    assert counts["absent_core_urls"] == counts["injected_discovery_urls"] == counts["body_or_day_mismatches"] == 0
    assert counts["source_queue_total"] == counts["selected_urls"] + counts["retained_nonselected_source_queue"]
    retention = cohort["nonselected_queue_retention"]
    assert retention["count"] == 1631 and retention["state_mutation_allowed"] is False
    assert retention["reason"] == "processing_not_attempted:explicit_queue_selection_excluded"
    assert cohort["core_execution"]["source_summary"]["error_type"] == "partial_discovery"
    assert cohort["core_execution"]["partial_discovery_remains_unresolved"] is True
    policy = cohort["unchanged_policy"]
    assert policy["media_materiality_threshold"] == 72
    assert policy["daily_fast_limit"] == 120 and policy["monthly_limit"] == 1500
    assert not any(policy[name] for name in ["budget_limits_changed", "terminal_states_reset", "llm_stub",
                                            "discovery_injection", "publication_quota", "publication_approved"])
