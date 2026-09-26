import hashlib
import json
from pathlib import Path


def test_model_quality_preflight_is_complete_and_makes_no_claimed_calls():
    plan = json.loads(Path("config/model_quality_experiment_v1.json").read_text())
    assert plan["status"] == "preflight_ready_no_calls"
    assert plan["models"] == ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-6-astra"]
    assert plan["execution"]["api_calls_made"] == plan["execution"]["outputs_generated"] == 0
    assert plan["execution"]["max_cost_usd"] is None
    assert plan["execution"]["credentials_required"] == ["OPENAI_API_KEY"]
    assert len(plan["corpus"]) == 7
    assert len({row["case_id"] for row in plan["corpus"]}) == 7
    assert {row["feature"] for row in plan["corpus"]} >= {"global_intelligence", "free_global_teaser", "weekly_candidate"}


def test_blind_rubric_and_measurement_contract_are_decision_ready():
    plan = json.loads(Path("config/model_quality_experiment_v1.json").read_text())
    rubric = plan["blind_scoring"]
    assert sum(row["weight"] for row in rubric["dimensions"]) == 100
    assert rubric["identity_mask"]
    assert rubric["automatic_fail"] == [
        "hallucinated_material_fact",
        "missing_source_for_material_claim",
        "global_hypothesis_presented_as_chile_fact",
    ]
    fields = set(plan["measurement_fields"])
    assert {"input_tokens", "output_tokens", "latency_ms", "cost_usd", "human_edit_minutes", "publishable_without_editing", "weighted_score"} <= fields
    assert plan["common_output_contract"]["format"] == "json"


def test_every_frozen_case_resolves_to_current_public_evidence():
    plan = json.loads(Path("config/model_quality_experiment_v1.json").read_text())
    themes = json.loads(Path("web/data/global_themes.json").read_text())["themes"]
    signals = json.loads(Path("web/data/radar_today.json").read_text())["signals"]
    theme_ids = {row["id"] for row in themes}
    signal_ids = {row["source_url"] for row in signals}
    for path, expected_hash in plan["input_snapshots"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected_hash
    for row in plan["corpus"]:
        path, identifier = row["input_ref"].split("#", 1)
        assert Path(path).exists()
        if path.endswith("global_themes.json"):
            assert identifier in theme_ids
        else:
            assert identifier in signal_ids

    by_id = {row["id"]: row for row in themes}
    assert len(by_id["global-workforce-pressure-2026"]["sources"]) >= 2
    assert len(by_id["global-health-ai-operating-model-2026"]["sources"]) >= 2
    c03 = next(row for row in plan["corpus"] if row["case_id"] == "C03")
    assert c03["task"] == "single_source_free_teaser"
