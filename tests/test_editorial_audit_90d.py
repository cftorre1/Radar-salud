import json
from pathlib import Path


def test_audit_90d_covers_all_43_snapshot_signals_and_29_additional():
    audit = json.loads(Path("data/editorial_audit_90d_2026_09_26.json").read_text())
    snapshot = json.loads(Path("web/data/radar_today.json").read_text())
    assert audit["scope"] == {
        "previously_audited_signals": 14,
        "additional_signals_audited": 29,
        "consolidated_signals_audited": 43,
        "special_pieces": "governed separately; not counted among the 43 snapshot signals",
    }
    assert len(audit["items"]) == len(snapshot["signals"]) == 43
    assert {item["id"] for item in audit["items"]} == {
        signal["source_url"] for signal in snapshot["signals"]
    }
    assert sum(item["snapshot_index"] >= 14 for item in audit["items"]) == 29
    assert audit["frozen_snapshot_sha256"] == "6a1f92e06f6d5a1aef6d5d179ecae1886b40bdc5be3e9a03df47eac61bdd2506"


def test_audit_90d_is_individual_traceable_and_matches_simulation():
    audit = json.loads(Path("data/editorial_audit_90d_2026_09_26.json").read_text())
    required = {
        "decision", "signal_worthy", "priority", "materiality_score",
        "value_category", "actor_action_consequence", "copy_review", "key_figures",
        "validity", "attribution", "overinterpretation_risk", "relation_to_prior",
        "decision_that_may_change", "business_review",
    }
    for item in audit["items"]:
        assert required <= item.keys()
        assert item["decision"] in {"accept", "degrade", "group", "reject"}
        assert 0 <= item["materiality_score"] <= 100
        assert item["business_review"]
    counts = {
        decision: sum(item["decision"] == decision for item in audit["items"])
        for decision in ("accept", "degrade", "group", "reject")
    }
    assert counts == audit["simulation"]["after"] == {
        "accept": 23, "degrade": 11, "group": 8, "reject": 1
    }
    assert audit["simulation"]["mode"] == "manual_counterfactual_review"
