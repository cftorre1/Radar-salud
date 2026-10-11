"""Reversible editorial corrections of genuine first-run outputs and originals."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from radar_salud.editorial_gate import publication_ready
from radar_salud.pulso_editorial_review import apply_review, canonical_sha, validate_independent_binding

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests/fixtures/pulso_editorial_real/first_paid_outputs.json"


@pytest.fixture
def inputs():
    original = json.loads(FIXTURE.read_bytes())
    assert original["run_id"] == 38141096276
    assert original["bot_sha"] == "90e99ad30e6eeaf470480e7847a7a814334a2b7b"
    history, queue, records = [], {}, []
    for i, row in enumerate(original["records"]):
        signal, item = row["signal"], row["queue_item"]
        history.append(deepcopy(signal))
        queue[str(i)] = deepcopy(item)
        metadata = item["raw"]["metadata"]
        decision = "reject" if "china-joyvio" in signal["source_url"] else "group" if "may-chomali-el-impensado" in signal["source_url"] else "correct" if "comite-social" in signal["source_url"] else "accept"
        record = dict(url=signal["source_url"], publication_date=signal["event_date"],
                      original_signal=deepcopy(signal), original_signal_sha256=canonical_sha(signal),
                      original_model_assessment=deepcopy(metadata["editorial_assessment"]),
                      original_body_sha256=metadata["article_body_sha256"], decision=decision,
                      reason="independent_original_body_review_" + decision,
                      evidence_quotes=[metadata["page_text"][:200]])
        if decision == "correct":
            record.update(event_status="planned", evidence_quotes=[
                "habrá un aumento de 2.624 millones de pesos, equivalente al 4,7%, para la Red Local de Apoyos y Cuidados.",
                "Esto permitirá incorporar 24 nuevas comunas y llegar a 333 de las 345 que establece la ley."],
                proposed=dict(what_happened="Según Pulso/La Tercera, Desarrollo Social anunció un aumento futuro de 2.624 millones de pesos para la Red Local de Apoyos y Cuidados, que permitiría incorporar 24 nuevas comunas y llegar a 333 de las 345 previstas por ley.",
                              why_it_matters="El aumento y la expansión proyectados podrían ampliar la atención domiciliaria una vez implementados. Las 333 comunas corresponden a una meta anunciada; el artículo no demuestra que ya se haya alcanzado."))
        if decision == "group":
            target = next(r["signal"] for r in original["records"] if "presupuesto-salud-2027" in r["signal"]["source_url"])
            record["duplicate_of"] = dict(url=target["source_url"], event_date=target["event_date"])
        records.append(record)
    audit = dict(schema_version="pulso_editorial_review_v1", review_id="real-first-run-independent-editorial-review", records=records)
    return history, queue, audit


def apply(inputs):
    history, queue, audit = inputs
    return apply_review(history, queue, audit, audit_sha256=canonical_sha(audit),
                        audit_path="data/audits/pulso_first_paid_editorial_review.json")


def test_real_outputs_keep_original_api_evidence_and_exact_gate_with_reviewed_states(inputs):
    history, queue, audit = inputs
    new_history, new_queue, report = apply(inputs)
    assert report["decisions"] == dict(accept=2, reject=1, group=1, correct=1)
    assert report["ai_calls"] == report["queue_attempt_resets"] == report["primary_evidence_mutations"] == 0
    assert report["applied_count"] == 5
    assert len(new_history) == len(history) == 5
    for original, corrected, record in zip(history, new_history, audit["records"]):
        assert corrected["editorial_relevance"] == original["editorial_relevance"] >= 72
        assert corrected["publication_date"] == corrected["event_date"] == original["event_date"]
        assert corrected["evidence_maturity"] == "media_reported"
        provenance = corrected["editorial_review"]
        assert provenance["original_model_what_happened"] == original["what_happened"]
        assert provenance["original_model_why_it_matters"] == original["why_it_matters"]
        assert provenance["original_signal_sha256"] == canonical_sha(original)
        assert publication_ready(corrected)[0] == (record["decision"] not in {"reject", "group"})
    for key, original in queue.items():
        modified = new_queue[key]
        for field in ("attempts", "lane", "detected_at", "updated_at", "next_retry_at"):
            assert modified.get(field) == original.get(field)
        for field in ("page_text", "article_body_sha256", "html_sha256", "captured_at", "analysis_input_body_sha256"):
            assert modified["raw"]["metadata"].get(field) == original["raw"]["metadata"].get(field)
    corrected = next(row for row in new_history if "comite-social" in row["source_url"])
    assert corrected["prospective_evidence"] is True and corrected["event_status"] == "planned"
    assert "una meta anunciada" in corrected["why_it_matters"]
    assert inputs == (history, queue, audit)


def test_second_application_is_identical_without_queue_or_paid_replay(inputs):
    history, queue, report = apply(inputs)
    repeated_history, repeated_queue, replay = apply((history, queue, inputs[2]))
    assert repeated_history == history
    assert repeated_queue == queue
    assert replay["applied_count"] == 0 and replay["unchanged_on_replay"] == 5


@pytest.mark.parametrize("mutation, reason", [
    ("body", "review_original_primary_body_or_date_mismatch"),
    ("date", "review_queue_identity_not_unique"),
    ("canonical", "review_original_primary_body_or_date_mismatch"),
    ("identity", "review_original_primary_body_or_date_mismatch"),
    ("quote", "editorial_review_quote_not_in_original_body"),
    ("model_hash", "original_model_output_hash_mismatch"),
    ("model_output", "observed_original_signal_or_terminal_status_changed"),
    ("terminal", "observed_original_signal_or_terminal_status_changed"),
    ("assessment", "observed_original_model_assessment_mismatch"),
    ("attempt", "observed_original_model_assessment_mismatch"),
])
def test_unverified_or_changed_originals_fail_before_any_state_mutation(inputs, mutation, reason):
    history, queue, audit = deepcopy(inputs)
    target = queue["0"]
    if mutation == "body": target["raw"]["metadata"]["page_text"] += " altered"
    if mutation == "date": target["raw"]["event_date"] = "2026-10-01"
    if mutation == "canonical": target["raw"]["metadata"]["canonical_url"] += "foreign/"
    if mutation == "identity": target["raw"]["metadata"]["primary_identity_verified"] = False
    if mutation == "quote": audit["records"][0]["evidence_quotes"] = ["This statement does not occur in the original primary body."]
    if mutation == "model_hash": audit["records"][0]["original_signal_sha256"] = "0" * 64
    if mutation == "model_output": history[0]["what_happened"] = "A different observed model summary."
    if mutation == "terminal": target["status"] = "pending"
    if mutation == "assessment": target["raw"]["metadata"]["editorial_assessment"]["threshold"] = 71
    if mutation == "attempt": target["attempts"] = 0
    before = deepcopy((history, queue, audit))
    with pytest.raises(ValueError, match=reason):
        apply((history, queue, audit))
    assert (history, queue, audit) == before


def test_group_must_have_a_surviving_existing_material_signal(inputs):
    audit = inputs[2]
    grouped = next(r for r in audit["records"] if r["decision"] == "group")
    grouped["duplicate_of"] = {"url": grouped["url"], "event_date": grouped["publication_date"]}
    with pytest.raises(ValueError, match="group_surviving_signal_missing_or_withdrawn"):
        apply(inputs)


def test_changed_effective_assessment_or_prose_cannot_hide_behind_same_review_hash(inputs):
    history, queue, _ = apply(inputs)
    queue["0"]["raw"]["metadata"]["editorial_assessment"]["decision"] = "pending"
    with pytest.raises(ValueError, match="reviewed_effective_model_output_changed"):
        apply((history, queue, inputs[2]))


@pytest.mark.parametrize("field, value", [("decision", "accept"), ("original_body_sha256", "0" * 64),
                                         ("original_model_what_happened", "A forged original model claim.")])
def test_provenance_is_reconstructed_from_immutable_record_on_replay(inputs, field, value):
    history, queue, _ = apply(inputs)
    withdrawn = next(row for row in history if row["editorial_review"]["decision"] == "reject")
    withdrawn["editorial_review"][field] = value
    item = next(v for v in queue.values() if v["raw"]["url"] == withdrawn["source_url"])
    item["raw"]["metadata"]["editorial_review"] = deepcopy(withdrawn["editorial_review"])
    with pytest.raises(ValueError, match="conflicting_existing_editorial_review"):
        apply((history, queue, inputs[2]))


def test_initial_queue_model_prose_must_match_observed_history(inputs):
    inputs[1]["0"]["raw"]["metadata"]["what_happened"] = "A different model output in the queue."
    with pytest.raises(ValueError, match="observed_original_queue_model_prose_mismatch"):
        apply(inputs)


def test_reviewed_copy_still_must_pass_existing_editorial_gate(inputs):
    correction = next(r for r in inputs[2]["records"] if r["decision"] == "correct")
    correction["proposed"]["why_it_matters"] = "El artículo no se relaciona con el sector salud y no sustenta cambios concretos."
    with pytest.raises(ValueError, match="reviewed_copy_fails_existing_publication_gate"):
        apply(inputs)


def test_group_uses_effective_corrected_target_not_unreviewed_original_copy(inputs):
    target = next(r for r in inputs[2]["records"] if "presupuesto-salud-2027" in r["url"])
    target.update(decision="correct", event_status="planned", proposed={
        "what_happened": target["original_signal"]["what_happened"],
        "why_it_matters": "El contenido no se relaciona con el sector salud y no sustenta una señal estratégica."})
    with pytest.raises(ValueError, match="reviewed_copy_fails_existing_publication_gate|group_surviving_signal_not_eligible"):
        apply(inputs)


@pytest.mark.parametrize("mutation", ["hidden", "rejected", "low_score", "unverified_media", "queue_rejected"])
def test_group_survivor_must_really_remain_eligible_and_published(inputs, mutation):
    target_record = next(r for r in inputs[2]["records"] if r["decision"] == "group")["duplicate_of"]
    survivor = next(s for s in inputs[0] if s["source_url"] == target_record["url"])
    item = next(v for v in inputs[1].values() if v["raw"]["url"] == target_record["url"])
    # Put the target outside the review: survival cannot rely only on review membership.
    inputs[2]["records"] = [r for r in inputs[2]["records"] if r["url"] != target_record["url"]]
    if mutation == "hidden": survivor["feed_visibility"] = False
    if mutation == "rejected": survivor["editorial_decision"] = "reject"
    if mutation == "low_score": survivor["editorial_relevance"] = 0
    if mutation == "unverified_media": survivor["evidence_maturity"] = "unverified"
    if mutation == "queue_rejected": item["status"] = "rejected"
    with pytest.raises(ValueError, match="group_surviving_signal_not_"):
        apply(inputs)


def test_other_source_terminal_state_is_unchanged(inputs):
    foreign = deepcopy(inputs[1]["0"])
    foreign["source"] = "minsal"
    foreign["status"] = "rejected"
    inputs[1]["other-source"] = foreign
    _, queue, _ = apply(inputs)
    assert queue["other-source"] == foreign


def independent_inputs():
    import hashlib
    path = ROOT / "data/audits/pulso_first_real_all32_semantic_review_2026_10_11.json"
    original = path.read_bytes()
    audit = json.loads((ROOT / "data/audits/pulso_first_paid_editorial_corrections_2026_10_11.json").read_bytes())
    return audit, json.loads(original), hashlib.sha256(original).hexdigest()


def test_actual_all32_corrections_match_every_independent_reader_decision_and_quote():
    audit, original, sha = independent_inputs()
    validate_independent_binding(audit, original, independent_sha256=sha)
    assert len(audit["records"]) == 32
    assert len({r["url"] for r in audit["records"]}) == 32


@pytest.mark.parametrize("change", ["coverage", "decision", "reason", "body", "summary", "quote", "copy", "group_target", "reader_sha", "partial_read"])
def test_editor_cannot_override_independent_reader_or_hide_findings(change):
    audit, original, sha = independent_inputs()
    first = audit["records"][0]
    if change == "coverage": audit["records"].pop()
    if change == "decision": first["decision"] = "accept"
    if change == "reason": first["reason"] = "Generic acceptance substituted for the actual scope finding."
    if change == "body": first["original_body_sha256"] = "0" * 64
    if change == "summary": first["original_signal"]["what_happened"] = "A fabricated summary."
    if change == "quote": first["evidence_quotes"] = ["A different quote never approved by the independent reader."]
    if change == "copy": next(r for r in audit["records"] if r["decision"] == "correct")["proposed"]["what_happened"] = "The future expansion has already occurred."
    if change == "group_target": next(r for r in audit["records"] if r["decision"] == "group")["duplicate_of"]["url"] = first["url"]
    if change == "reader_sha": audit["independent_review"]["sha256"] = "0" * 64
    if change == "partial_read": original["all_signals"][0]["full_original_body_read"] = False
    with pytest.raises(ValueError):
        validate_independent_binding(audit, original, independent_sha256=sha)
