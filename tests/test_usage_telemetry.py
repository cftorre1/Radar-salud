import json
from types import SimpleNamespace
import pytest
from radar_salud import ai_budget, telemetry

def test_corrupt_budget_blocks_spending(tmp_path,monkeypatch):
    monkeypatch.setenv("RADAR_ROOT",str(tmp_path))
    path=ai_budget._path();path.parent.mkdir(parents=True);path.write_text("broken")
    with pytest.raises(RuntimeError,match="blocked"):ai_budget.allow_call("fast")

def test_response_records_actual_tokens_not_prompts_or_invented_cost(tmp_path,monkeypatch):
    monkeypatch.setenv("RADAR_ROOT",str(tmp_path))
    response=SimpleNamespace(id="resp_test",usage=SimpleNamespace(input_tokens=31,output_tokens=7,total_tokens=38,input_tokens_details=SimpleNamespace(cached_tokens=12)))
    telemetry.record_response("fast","configured-model",response,True)
    data=json.loads((tmp_path/"data/ai_usage/responses.jsonl").read_text())
    assert data["input_tokens"]==31 and data["output_tokens"]==7
    assert data["cost_usd"] is None and data["cached_input_tokens"]==12
    assert not ({"prompt","api_key","document"}&data.keys())

def test_failed_call_records_error_class_without_sensitive_text(tmp_path,monkeypatch):
    monkeypatch.setenv("RADAR_ROOT",str(tmp_path))
    telemetry.record_response("fast","configured-model",None,False,"TimeoutError")
    row=json.loads((tmp_path/"data/ai_usage/responses.jsonl").read_text())
    assert row["error_type"]=="TimeoutError" and row["model"]=="configured-model"
    assert row["input_tokens"] is None and row["cost_usd"] is None

def test_global_run_budget_cannot_exceed_attempts(tmp_path,monkeypatch):
    monkeypatch.setenv("RADAR_ROOT",str(tmp_path))
    monkeypatch.setenv("RADAR_FAST_PER_RUN","2")
    monkeypatch.setattr(ai_budget,"_RUN",ai_budget._blank())
    assert ai_budget.allow_call("fast")
    ai_budget.record_result("fast",False)
    assert ai_budget.allow_call("fast")
    assert not ai_budget.allow_call("fast") and not ai_budget.has_capacity("fast")
    assert ai_budget.status()["month"]["fast"]["attempted"]==2
