"""Freeze independent full-primary semantics for two genuine reused publications."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from radar_salud.pulso_editorial_review import apply_review, canonical_sha

ROOT = Path(__file__).parents[1]
PEER = "data/audits/pulso_actual323_ilc_mask_independent_second_peer_2026_10_11.json"
PEER_SHA = "cd826b140ad60154f34bb278a08248265883313c5d0eab39eb2077dd2ce95ecd"


@pytest.fixture(scope="module")
def evidence():
    raw = (ROOT / PEER).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PEER_SHA
    peer = json.loads(raw)
    reader_bytes = (ROOT / peer["first_reader"]["path"]).read_bytes()
    template_bytes = (ROOT / peer["template"]["path"]).read_bytes()
    assert hashlib.sha256(reader_bytes).hexdigest() == peer["first_reader"]["sha256"]
    assert hashlib.sha256(template_bytes).hexdigest() == peer["template"]["sha256"]
    archived = {}
    for name in ("queue", "history", "runtime_report"):
        ref = peer["inputs"][name]
        content = subprocess.check_output(["git", "show", ref["commit"] + ":" + ref["path"]], cwd=ROOT)
        assert hashlib.sha256(content).hexdigest() == ref["file_sha256"]
        archived[name] = json.loads(content)
    return peer, json.loads(reader_bytes), json.loads(template_bytes), archived


def test_all_two_complete_actual_primary_model_signal_and_peer_pins_are_exact(evidence):
    peer, reader, _, archived = evidence
    assert len(peer["all_signals"]) == 2
    for row in peer["all_signals"]:
        parent = next(r for r in reader["all_signals"] if r["url"] == row["url"])
        entry = archived["queue"][row["queue_fingerprint"]]
        md = entry["raw"]["metadata"]
        assert entry["status"] == "published" and entry["raw"]["event_date"] == row["publication_date"] == "2026-09-01"
        assert canonical_sha(parent) == row["first_reader_record_sha256"]
        assert canonical_sha(entry) == row["original_queue_entry_sha256"]
        assert md["page_text"] == row["original_full_primary_body"]
        assert md["analysis_model_output"] == row["original_full_model_output"]
        assert row["original_full_signal"] in archived["history"]["signals"]
        assert canonical_sha(row["immutable_actual_model_primary_pin"]) == parent["immutable_actual_model_primary_pin_sha256"]
        assert all(q["text"] in row["original_full_primary_body"] for q in row["supporting_verbatim_quotes"])
        assert all(row[k] is True for k in ("full_original_body_read", "full_actual_model_output_read", "full_signal_read"))


def test_ilc_accept_and_mask_category_only_preserve_native_state_paid_bodies_scores_and_prospectivity(evidence):
    peer, _, audit, archived = evidence
    q0, h0 = archived["queue"], archived["history"]["signals"]
    before = deepcopy((q0, h0))
    h, q, result = apply_review(h0, q0, audit, audit_sha256=peer["template"]["sha256"], audit_path=peer["template"]["path"])
    assert (q0, h0) == before and result["applied_count"] == 2 and result["ai_calls"] == 0
    assert result["decisions"] == {"accept": 1, "correct": 1, "reject": 0, "group": 0}
    keys = {r["queue_fingerprint"] for r in peer["all_signals"]}
    urls = {r["url"] for r in peer["all_signals"]}
    assert all(q[key] == value for key, value in q0.items() if key not in keys)
    assert [s for s in h if s["source_url"] not in urls] == [s for s in h0 if s["source_url"] not in urls]
    assert sum(e["source"] != "pulso_latercera" for e in q.values()) == 5293
    assert sum(s["source_name"] != "Pulso / La Tercera" for s in h) == 897
    for row in peer["all_signals"]:
        old = row["original_full_signal"]
        new = next(s for s in h if s["source_url"] == row["url"])
        assert new["what_happened"] == old["what_happened"] and new["why_it_matters"] == old["why_it_matters"]
        assert new["editorial_relevance"] == old["editorial_relevance"] == row["actual_score"]
        assert new["prospective_evidence"] is old["prospective_evidence"] is True
        assert new["category"] == ("Aseguramiento" if row["decision"] == "accept" else "Regulación & Legal")
        for field in ("analysis_model_output", "page_text", "article_body_sha256", "html_sha256", "scores"):
            assert q[row["queue_fingerprint"]]["raw"]["metadata"][field] == q0[row["queue_fingerprint"]]["raw"]["metadata"][field]
    h2, q2, replay = apply_review(h, q, audit, audit_sha256=peer["template"]["sha256"], audit_path=peer["template"]["path"])
    assert (h2, q2) == (h, q) and replay["applied_count"] == 0 and replay["unchanged_on_replay"] == 2


def test_holding_growth_expired_regulatory_period_and_unpriced_cost_limits_remain_explicit(evidence):
    peer, _, _, archived = evidence
    ilc = next(r for r in peer["all_signals"] if r["decision"] == "accept")
    mask = next(r for r in peer["all_signals"] if r["decision"] == "correct")
    assert "45% is whole holding H1 growth, not health growth." in ilc["denominator_and_maturity_limits"]
    assert "Announced period endsSep30; this press article does not certify Oct11 continued obligation." in mask["denominator_and_maturity_limits"]
    assert "56,1%" in mask["original_full_signal"]["what_happened"]
    assert "no acredita que la medida siguiera vigente al 11 de octubre" in mask["original_full_signal"]["what_happened"]
    budget = peer["actual_budget_observation"]
    assert budget["month_fast_before"] == 514 and budget["month_fast_after"] == 516
    assert budget["run_fast_successful"] == 2 and budget["run_fast_failed"] == 0
    assert budget["month_deep_before"] == budget["month_deep_after"] == 14
    assert budget["reviewed_two_are_reuse_not_newFAST"] is True
    assert all(row["new_FAST_in_current_run"] is False for row in peer["all_signals"])
    assert "pricing_not_configured" in budget["pricing_limit"]
    assert peer["summary"]["global_acceptance"] == "NOT_DECLARED"
    for path, ref in peer["cost_file_bindings"].items():
        content = subprocess.check_output(["git", "show", ref["commit"] + ":" + path], cwd=ROOT)
        assert hashlib.sha256(content).hexdigest() == ref["file_sha256"]
