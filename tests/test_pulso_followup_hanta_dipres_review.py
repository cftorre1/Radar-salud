"""Actual323 bindings and one published correction; retry is never overridden."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from radar_salud.pulso_editorial_review import apply_review, canonical_sha, validate_independent_binding

ROOT = Path(__file__).parents[1]
PRODUCER = "323b73ef5fb0ec39410024c21d70e6fd99b065e2"
READER = "data/audits/pulso_actual_followup_hanta_dipres_independent_semantic_review_2026_10_11.json"
TEMPLATE = "data/audits/pulso_actual_followup_dipres_editorial_correction_2026_10_11.json"
READER_SHA = "b4c19a8bead89a2db48f2820851b25f968b9edc3c307f1189cd8419a7e8f408c"
TEMPLATE_SHA = "312cc47e9d22bedd31c783553708623aefa7dcfb30a4fa596fc6c121409788b5"


@pytest.fixture(scope="module")
def evidence():
    rb, ab = (ROOT / READER).read_bytes(), (ROOT / TEMPLATE).read_bytes()
    assert hashlib.sha256(rb).hexdigest() == READER_SHA
    assert hashlib.sha256(ab).hexdigest() == TEMPLATE_SHA
    reader, audit = json.loads(rb), json.loads(ab)
    validate_independent_binding(audit, reader, independent_sha256=READER_SHA)
    archived = {}
    assert set(reader["inputs"]) == {"history", "queue", "runtime_report", "telemetry"}
    for label, ref in reader["inputs"].items():
        b = subprocess.check_output(["git", "show", ref["commit"] + ":" + ref["path"]], cwd=ROOT)
        assert ref["commit"] == PRODUCER and hashlib.sha256(b).hexdigest() == ref["file_sha256"]
        archived[label] = [json.loads(line) for line in b.decode().splitlines()] if label == "telemetry" else json.loads(b)
    return reader, audit, archived


def test_two_complete_actual_models_and_primary_bodies_keep_exact_producer_pins(evidence):
    reader, audit, archived = evidence
    assert len(reader["rows"]) == 2 and len(reader["all_signals"]) == len(audit["records"]) == 1
    for row in reader["rows"]:
        entry = archived["queue"][row["queue_fingerprint"]]
        md = entry["raw"]["metadata"]
        assert canonical_sha(entry) == row["original_queue_entry_sha256"]
        assert md["page_text"] == row["original_full_primary_body"]
        assert md["analysis_model_output"] == row["original_full_model_output"]
        assert hashlib.sha256(md["page_text"].encode()).hexdigest() == row["original_body_sha256"]
        assert canonical_sha(md["analysis_model_output"]) == row["original_model_output_semantic_sha256"]
        assert canonical_sha(row["immutable_actual_model_primary_pin"]) == row["immutable_actual_model_primary_pin_sha256"]
        assert all(q["text"] in md["page_text"] for q in row["supporting_verbatim_quotes"])
    assert {r["actual_status"] for r in reader["rows"]} == {"published", "retry"}


def test_hanta_reports_real_increment_without_inventing_new_alert_or_approving_retry(evidence):
    reader, _, archived = evidence
    row = next(r for r in reader["rows"] if r["row_index"] == 28)
    diag = row["diagnosis"]
    comparator = diag["comparator"]
    assert len(row["supporting_verbatim_quotes"]) == 8
    assert diag["publication_approved"] is False and diag["pending_not_human_approved"] is True
    assert diag["scope_alias_fix_alone_is_sufficient"] is False
    assert comparator["original_full_primary_body"] == archived["queue"][comparator["queue_fingerprint"]]["raw"]["metadata"]["page_text"]
    assert comparator["original_full_signal"] in archived["history"]["signals"]
    assert comparator["contains_alert_background"] is True
    assert comparator["contains_46_cases_18_deaths_39_percent"] is False
    assert "la alerta como hecho central ya aparece" in row["original_full_model_output"]["reason"]
    assert "31/9/4 exposure categories overlap and must not sum as unique patients." in diag["case_denominator_limits"]
    events = [event for event in archived["telemetry"] if event.get("response_id") == row["original_model_response_binding"]["response_id"]]
    assert len(events) == 1 and events[0]["success"] is True
    assert diag["actual_fresh_successful_provider_event"] == events[0]


def test_frozen_paid_guard_exposes_both_hanta_false_negatives_and_literal_qualifications(evidence):
    reader, _, _ = evidence
    row = next(r for r in reader["rows"] if r["row_index"] == 28)
    code = subprocess.check_output(["git", "show", PRODUCER + ":src/radar_salud/pulso_editorial_proof.py"], cwd=ROOT)
    assert hashlib.sha256(code).hexdigest() == row["diagnosis"]["frozen_guard_module_sha256"]
    ns = {"__name__": "radar_salud._review_test_actual323_guard", "__package__": "radar_salud"}
    exec(compile(code, "<immutable323>", "exec"), ns)
    model = row["original_full_model_output"]
    quote = model["pulso_editorial_proof"]["human_health_scope_quote"]
    assert ns["literal_quote_matches"](quote, row["original_full_primary_body"])
    assert ns["human_health_scope_anchor"](quote) is False
    checks = row["diagnosis"]["secondary_frozen_guard_predicates"]
    assert [c["future_copy_qualified"] for c in checks] == [True, False]
    for check in checks:
        assert check["summary_quote"] == model[check["field"]]
        assert check["full_summary_quote_matches"] and check["source_quote_literal"]
        assert not ns["unqualified_achieved_copy"](check["summary_quote"])
        assert not ns["unsupported_clinical_completion"](check["summary_quote"], row["original_full_primary_body"])


def test_only_dipres_prefix_changes_and_all_native_pending_models_scores_dates_stay_exact(evidence):
    reader, audit, archived = evidence
    queue, history = archived["queue"], archived["history"]["signals"]
    before = deepcopy((queue, history))
    h, q, applied = apply_review(history, queue, audit, audit_sha256=TEMPLATE_SHA, audit_path=TEMPLATE)
    assert (queue, history) == before
    assert applied["applied_count"] == 1 and applied["ai_calls"] == 0
    parent = reader["all_signals"][0]
    old = parent["original_full_signal"]
    changed = next(s for s in h if s["source_url"] == parent["url"])
    assert changed["what_happened"].startswith("Según Pulso / La Tercera, en su nota del 21 de septiembre de 2026,")
    assert changed["what_happened"].replace("Según Pulso / La Tercera, en su nota del", "Según la nota del", 1) == old["what_happened"]
    assert changed["why_it_matters"] == old["why_it_matters"]
    assert changed["prospective_evidence"] is old["prospective_evidence"] is True
    assert changed["editorial_relevance"] == old["editorial_relevance"] == 84
    assert changed["category"] == old["category"] == "Regulación & Legal"
    assert sum(e["source"] != "pulso_latercera" for e in q.values()) == 5293
    assert all(q[key] == value for key, value in queue.items() if key != parent["queue_fingerprint"])
    assert [s for s in h if s["source_url"] != parent["url"]] == [s for s in history if s["source_url"] != parent["url"]]
    old_md, new_md = queue[parent["queue_fingerprint"]]["raw"]["metadata"], q[parent["queue_fingerprint"]]["raw"]["metadata"]
    for field in ("analysis_model_output", "page_text", "article_body_sha256", "html_sha256", "scores"):
        assert new_md[field] == old_md[field]
    assert new_md["editorial_assessment"]["original_model_assessment"] == old_md["editorial_assessment"]
    for field in ("decision", "relevance_score", "threshold"):
        assert new_md["editorial_assessment"][field] == old_md["editorial_assessment"][field]
    h2, q2, replay = apply_review(h, q, audit, audit_sha256=TEMPLATE_SHA, audit_path=TEMPLATE)
    assert (h2, q2) == (h, q) and replay["applied_count"] == 0 and replay["unchanged_on_replay"] == 1


def test_dipres_dual_provenance_reuses_actual66_without_fabricating_new_fast(evidence):
    reader, _, archived = evidence
    parent = reader["all_signals"][0]
    response = parent["original_model_response_binding"]
    binding = parent["original_output_binding"]["revalidated_followup_paid_response"]
    assert binding["original_producer"] == "66f37ca044b4cf233bc9f649b7140ff8a69855d3"
    assert binding["publication_execution_code"] == reader["execution_code_sha"]
    assert binding["proof"]["old_paid_output_reused"] is True
    assert binding["proof"]["current_response_id"] == response["response_id"]
    execution = archived["runtime_report"]["last_core_execution"]
    matching = [e for e in archived["telemetry"] if e.get("response_id") == response["response_id"]]
    assert len(matching) == 1 and matching[0]["at"] < execution["started_at"]
    assert matching[0]["success"] is True
    peer_ref = reader["provenance_peer"]
    peer_bytes = (ROOT / peer_ref["path"]).read_bytes()
    assert hashlib.sha256(peer_bytes).hexdigest() == peer_ref["sha256"]
    assert all(r["publication_approved_by_peer"] is False for r in json.loads(peer_bytes)["rows"])


def test_independent_registry_qa_verified_exact_one_and_full_context_in_memory(evidence):
    path = ROOT / "data/audits/pulso_actual_followup_dipres_schema_validation_2026_10_11.json"
    body = path.read_bytes()
    assert hashlib.sha256(body).hexdigest() == "2c02f714db7b4c25c8d3be86e6ad7c5ebf740dd1e37028c09efd14e21c705228"
    proof = json.loads(body)
    assert proof["producer_commit"] == PRODUCER
    assert proof["reader"]["sha256"] == READER_SHA and proof["template"]["sha256"] == TEMPLATE_SHA
    result = proof["validation"]
    assert result["exact_one_QA_verified"] == 1 and result["exact_one_QA_errors"] == []
    assert result["fullcontext_QA_verified"] == 60 and result["fullcontext_QA_errors"] == []
    assert result["in_memory_reapplication"]["applied_count"] == 0
    assert result["all5293_nonPulso_queue_and897_history_exact"] and result["Hanta_retry_unchanged"]
    assert proof["actual_state_writes"] == proof["AI_calls"] == 0
    assert proof["acceptance_pass"] is False
