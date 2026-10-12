"""A digest descriptor is never interchangeable with retained primary text."""
from copy import deepcopy
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("compact_body_type_units", ROOT / "tests/test_pulso_terminal_followthrough_idempotence.py")
units = importlib.util.module_from_spec(spec)
spec.loader.exec_module(units)
helper = units.helper


@lru_cache(maxsize=1)
def actual_live9_cardenas():
    raw = subprocess.check_output(["git", "show", helper.SETTLEMENT_PRODUCER + ":data/state/pending_queue.json"], cwd=ROOT)
    assert helper.digest(raw) == helper.SETTLEMENT_FILES["data/state/pending_queue.json"]
    queue = json.loads(raw)
    key = "76cdc28597009114d576b7e20314a93ed1390c31008b831ba7b2f47968ee40a7"
    row = queue[key]
    body = row["raw"]["metadata"]["page_text"]
    assert isinstance(body, str) and len(body) == 1553
    assert helper.digest(body.encode()) == "ea77802bc5bad54fb476386dc3b9b4bfb4732494feecaa8e9cfa1fc54de46c72"
    return key, row


@pytest.mark.parametrize("field", ["page_text", "raw_text"])
def test_real_live9_string_cannot_collide_with_its_old_or_typed_digest_descriptor(field):
    _, original = actual_live9_cardenas()
    body = original["raw"]["metadata"]["page_text"]
    projection = helper.compact({field: body})
    assert projection[field]["value_type"] == "str"
    for replacement in ({"utf8_sha256": helper.digest(body.encode()), "characters": len(body)}, projection[field]):
        erased = helper.compact({field: replacement})
        assert erased[field]["value_type"] == "dict"
        assert erased != projection
        assert helper.digest(erased) != helper.digest(projection)


@pytest.mark.parametrize("value,expected_type", [(None, "NoneType"), (0, "int"), (False, "bool"),
    (1.5, "float"), ([], "list"), ({}, "dict")])
@pytest.mark.parametrize("field", ["page_text", "raw_text"])
def test_nonstring_body_domain_is_explicit_and_recursive(field, value, expected_type):
    result = helper.compact({field: value})[field]
    assert result == {"value_type": expected_type, "value": helper.compact(value)}
    assert result != helper.compact({field: str(value)})[field]


def test_body_field_domains_retain_recursive_cache_exclusions():
    first = {"page_text": {"raw_text": "real text", "cache_hit": True}, "last_checked_at": "old"}
    second = {"page_text": {"raw_text": "real text", "cache_hit": False}, "last_checked_at": "new"}
    assert helper.compact(first) == helper.compact(second)
    assert helper.compact(first)["page_text"]["value"]["raw_text"]["value_type"] == "str"


def test_followthrough_preflight_rejects_real_unselected_live9_body_erasure(monkeypatch):
    # Future envelope is explicitly synthetic; the retained LIVE9 row/body is
    # copied from immutable actual d48. No Source or runtime file is mutated.
    context, proof = units.unit_context_and_proof()
    key, original = actual_live9_cardenas()
    synthetic_url = next(iter(proof["settlement_live9"]))
    synthetic_key = next(k for k, row in context["queue"].items() if row.get("raw", {}).get("url") == synthetic_url)
    context["queue"].pop(synthetic_key)
    proof["settlement_live9"].pop(synthetic_url)
    context["queue"][key] = deepcopy(original)
    url = original["raw"]["url"]
    assert url not in context["selection"]["urls"]
    proof["settlement_live9"][url] = {"status": "rejected", "attempts": 1, "actual_immutable_row": True}
    proof["launch_stock"]["source_queue_semantic_sha256s"] = {
        candidate: row["semantic_sha256"] for candidate, row in helper.source_queue(context["queue"]).items()}
    fixed = deepcopy(proof)
    from types import SimpleNamespace
    def independent_boundary(*args, **kwargs):
        result = deepcopy(fixed)
        result["current_followthrough_execution"] = deepcopy(kwargs["execution"])
        result["actual_budget_delta"] = helper.budget_delta(kwargs["execution"])
        return result
    monkeypatch.setattr(helper, "final_paid_reader", lambda root: SimpleNamespace(
        verify_terminal_followthrough_execution=independent_boundary,
        terminal_source_inventory_semantic=helper.compact))
    baseline = helper.capture_terminal_followthrough_baseline(context, now=units.NOW)
    assert helper.preflight(baseline, context, now=units.NOW)["verdict"] == "PASS"
    body = context["queue"][key]["raw"]["metadata"]["page_text"]
    context["queue"][key]["raw"]["metadata"]["page_text"] = {
        "utf8_sha256": helper.digest(body.encode()), "characters": len(body)}
    with pytest.raises(ValueError, match="runtime_state_changed_since_passing_baseline"):
        helper.preflight(baseline, context, now=units.NOW)
    result = helper.compare(baseline, units.later_core(context), now=units.NOW)
    assert "changed_existing_source_queue" in {entry["code"] for entry in result["findings"]}
