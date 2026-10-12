"""Check frozen, fully read financial comparisons without granting publication."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).parents[1]
REVIEW = "data/audits/pulso_financial_market_cross_source_review_2026_10_11.json"
REVIEW_SHA = "d96210eb0530d9cd01e3b3632802d2f2476097062613f1f864754b84c04eea24"
SUPPLEMENT = "data/audits/pulso_financial_three_native_checks_2026_10_11.json"
SUPPLEMENT_SHA = "ac762ffa7c0fc7de661f523fbd83111072f65b4faab7558a21bf182a37df3e04"


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()


@pytest.fixture(scope="module")
def evidence():
    body = (ROOT / REVIEW).read_bytes()
    extra = (ROOT / SUPPLEMENT).read_bytes()
    assert digest(body) == REVIEW_SHA and digest(extra) == SUPPLEMENT_SHA
    review, supplement = json.loads(body), json.loads(extra)
    archived = {}
    for name, ref in review["inputs"].items():
        retained = subprocess.check_output(["git", "show", ref["commit"] + ":" + ref["path"]], cwd=ROOT)
        assert digest(retained) == ref["file_sha256"]
        archived[name] = json.loads(retained)
    return review, supplement, archived


def test_all_primary_model_and_effective_signal_bindings_are_exact(evidence):
    review, _, archived = evidence
    for row in review["primary_records"].values():
        entry = archived["queue"][row["queue_fingerprint"]]
        raw = entry["raw"]
        md = raw["metadata"]
        assert digest(entry) == row["original_queue_entry_sha256"]
        assert digest(raw) == row["original_raw_item_sha256"]
        assert row["queue_publication_date"] == raw.get("event_date")
        assert row["retained_primary_text"] == md.get("page_text", "")
        assert digest(row["retained_primary_text"].encode()) == row["retained_primary_text_sha256"]
        assert row["actual_model_output"] == md.get("analysis_model_output")
        assert row["actual_model_output_missing"] == (md.get("analysis_model_output") is None)
        assert all(s in archived["history"]["signals"] for s in row["effective_signals"])
        assert digest(row["effective_signals"]) == row["effective_signals_sha256"]
    assert len(review["primary_records"]) == 13


def test_all_comparisons_have_literal_full_primary_support_without_legacy_model_invention(evidence):
    review, _, _ = evidence
    records = review["primary_records"]
    assert len(review["comparisons"]) == 9
    for comparison in review["comparisons"]:
        assert comparison["specific_increment"] and comparison["maturity"] and comparison["corroboration"]
        assert comparison["denominator_limits"]
        for quote in comparison["supporting_quotes"]:
            primary = records[quote["primary_record"]]
            assert primary["full_primary_body_read"] is True
            assert quote["text"] in primary["retained_primary_text"]
    for name in ("budget_programs", "senior_housing"):
        assert records[name]["actual_model_output_missing"] is True
        assert records[name]["actual_model_output_sha256"] is None
    assert sum(r["full_primary_body_read"] for r in records.values()) == 11


def test_incomplete_official_primary_does_not_erase_unknown_date_or_certify_press(evidence):
    review, _, archived = evidence
    records = review["primary_records"]
    minsal, decree = records["minsal_budget"], records["do_percapita"]
    assert minsal["queue_publication_date"] is None
    assert minsal["effective_signals"][0]["event_date"] == "2026-10-01"
    assert len(minsal["retained_primary_text"]) == 18000
    assert not minsal["full_primary_body_read"] and minsal["body_completeness_limit"]
    assert decree["retained_primary_text"] == ""
    assert not decree["full_primary_body_read"] and decree["body_completeness_limit"]
    assert review["summary"]["official_primary_certification"] is False
    assert sum(e["source"] != "pulso_latercera" for e in archived["queue"].values()) == 5293
    assert sum(s["source_name"] != "Pulso / La Tercera" for s in archived["history"]["signals"]) == 897


def test_segment_growth_and_monthly_contract_stock_do_not_grant_core_publication(evidence):
    review, _, _ = evidence
    ilc = review["primary_records"]["ilc_results"]
    assert ilc["queue_status"] == "retry" and ilc["effective_signals"] == []
    assert review["primary_records"]["df_ilc"]["queue_status"] == "rejected"
    assert review["primary_records"]["df_isapres"]["queue_status"] == "superseded"
    comparisons = {r["id"]: r for r in review["comparisons"]}
    limits = comparisons["ilc_holding_vs_health_segment_results"]["denominator_limits"]
    assert "45% is all ILC, not healthcare-segment growth." in limits
    summary = review["summary"]
    assert summary["additional_duplicate_group_authorized_here"] == 0
    assert summary["AI_calls"] == summary["product_state_changes"] == 0
    assert summary["global_acceptance"] == "NOT_DECLARED"


def test_native_actor_keyword_matches_remain_diagnostic_candidates(evidence):
    review, supplement, _ = evidence
    assert review["related_native_financial_primary_review"]["sha256"] == SUPPLEMENT_SHA
    assert len(supplement["comparisons"]) == 6
    for comparison in supplement["comparisons"]:
        assert comparison["duplicate_proven"] is False
        assert comparison["official_corroboration_of_pulso"] is False
        assert comparison["reason"] and comparison["limitation"]
    for topic in review["native_inventory_screening"]["by_topic"].values():
        assert all(hit["lexical_hit_is_not_semantic_match"] for hit in topic["queue_candidates"])
        assert all(hit["lexical_hit_is_not_semantic_match"] for hit in topic["history_candidates"])
    circular = supplement["observations"]["native_suseso_circular3926"]
    assert circular["queue_raw_publication_date"] is None
    assert not circular["full_primary_instrument_body_read"]


def test_senior_housing_stock_and_future_pipeline_preserve_reported_maturity(evidence):
    review, _, _ = evidence
    row = next(r for r in review["comparisons"] if r["id"].startswith("senior_housing"))
    assert "993 certified ELEAM is existing stock, not 993 new authorizations." in row["denominator_limits"]
    assert "Aurum 600 beds over eight years is an ambition, not current added capacity." in row["denominator_limits"]
    assert "No retained FNE filing/decision" in row["corroboration"]
