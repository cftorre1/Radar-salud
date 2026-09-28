import json
from pathlib import Path
import pytest
from scripts.model_quality_experiment import build_experiment, make_prompt, reserve_usd, validate_output
ROOT=Path(__file__).resolve().parents[1]

def test_experiment_uses_eight_source_pieces_and_five_approved_cases():
    snapshot=json.loads((ROOT/"web/data/radar_today.json").read_text(encoding="utf-8"))
    weekly=json.loads((ROOT/"data/weekly_insight/latest.json").read_text(encoding="utf-8"))
    themes=json.loads((ROOT/"data/global/themes.json").read_text(encoding="utf-8"))
    experiment=build_experiment(snapshot,weekly,themes)
    assert len(experiment["pieces"])==8
    assert {x["id"] for x in experiment["cases"]}=={"simple_news","complex_report","multisource_chile","free_feature","global_teaser"}
    assert all(c["evidence"] and len(make_prompt(c))<20000 for c in experiment["cases"])

def test_quality_output_rejects_references_outside_case():
    output={"headline":"h","executive_thesis":"t","key_claims":[{"claim":"x","source_ids":["OUTSIDE"]}],"why_it_matters":"w","business_implications":[],"chile_watch":{"classification":"hypothesis","text":"h","source_ids":[]},"decision_use":"d","uncertainties_and_limits":[],"source_refs":["L1"]}
    result=validate_output(output,{"L1"})
    assert result["valid"] is False
    assert result["invalid_source_ids"]==["OUTSIDE"]

def test_reserve_is_computed_for_all_models_and_fails_closed_at_budget():
    assert reserve_usd(["simple prompt","complex report prompt"])>0
    with pytest.raises(ValueError,match="budget_guard"):
        reserve_usd(["x"*20001])
