"""Read-only QA using ALL5 immutable real paid originals and exact review chain.

The generic-review cases declare new temporary audits of those same originals;
they do not claim another paid run, change runtime files, or invoke the model.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from radar_salud.pulso_editorial_review import apply_review

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("additional_pulso_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
NEW5, PLAN = tuple(qa.FOLLOWUP_REVIEW_PINS)


def encoded(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return qa.digest(target.read_bytes())


def producer(path):
    return subprocess.check_output(["git", "show", qa.FOCUS_PRODUCER + ":" + path], cwd=ROOT)


@pytest.fixture
def real_originals(tmp_path):
    # Immutable producer data rather than mutable current queue/history.
    (tmp_path / ".git").symlink_to(subprocess.check_output(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True).strip(), target_is_directory=True)
    for audit_path, (_, reader_path, _) in qa.FOLLOWUP_REVIEW_PINS.items():
        for path in (audit_path, reader_path):
            target = tmp_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / path).read_bytes())
    target = tmp_path / qa.EDITORIAL_REGISTRY_PATH
    target.write_bytes((ROOT / qa.EDITORIAL_REGISTRY_PATH).read_bytes())
    audit = json.loads((tmp_path / NEW5).read_bytes())
    urls = {row["url"] for row in audit["records"]}
    queue = {key: item for key, item in json.loads(producer("data/state/pending_queue.json")).items()
             if item.get("source") == qa.SOURCE and item["raw"].get("url") in urls}
    history = [row for row in json.loads(producer("data/history/superintendencia_signals.json"))["signals"]
               if row.get("source_url") in urls]
    assert len(queue) == len(history) == 5
    return dict(root=tmp_path, queue=queue, history=history)


def apply_temporary(value, path):
    audit = json.loads((value["root"] / path).read_bytes())
    value["history"], value["queue"], _ = apply_review(value["history"], value["queue"], audit,
        audit_sha256=qa.digest((value["root"] / path).read_bytes()), audit_path=path)
    value["snapshot"] = dict(signals=[deepcopy(row) for row in value["history"] if row.get("feed_visibility") is not False])


@pytest.fixture
def reviewed(real_originals):
    apply_temporary(real_originals, NEW5)
    apply_temporary(real_originals, PLAN)
    return real_originals


def errors(value):
    return qa.verify_additional_editorial_reviews(**value)[1]


def test_all_five_paid_originals_and_exact_plan_predecessor_chain(reviewed):
    proofs, findings = qa.verify_additional_editorial_reviews(**reviewed)
    assert findings == []
    assert len(proofs) == 5
    plan = next(proof for proof in proofs.values() if proof["review_file"] == PLAN)
    assert plan["previous_editorial_review"]["review_file"] == NEW5
    assert plan["original_model_assessment"]["threshold"] == 72


@pytest.mark.parametrize("attack", ["queue_provenance", "history_provenance", "model", "body",
    "score", "date", "media", "attempt_reset", "feed_lost", "feed_copy", "predecessor", "source_flag", "scalar_proof"])
def test_current_claims_cannot_replace_paid_original_or_exact_effective_state(reviewed, attack):
    signal = next(row for row in reviewed["history"] if row["editorial_review"]["review_file"] == PLAN)
    item = next(row for row in reviewed["queue"].values() if row["raw"]["url"] == signal["source_url"])
    metadata = item["raw"]["metadata"]
    if attack == "queue_provenance": metadata["editorial_review"]["reason"] += " changed"
    elif attack == "history_provenance": signal["editorial_review"]["reason"] += " changed"
    elif attack == "model": metadata["analysis_model_output"]["what_happened"] += " fabricated"
    elif attack == "body": metadata["page_text"] += " fabricated"
    elif attack == "score": signal["editorial_relevance"] = 99
    elif attack == "date": metadata["publication_date"] = "2026-10-11"
    elif attack == "media": signal["evidence_maturity"] = "official"
    elif attack == "attempt_reset": item["attempts"] = 0
    elif attack == "feed_lost": reviewed["snapshot"]["signals"] = []
    elif attack == "feed_copy": reviewed["snapshot"]["signals"][0]["why_it_matters"] += " fabricated"
    elif attack == "predecessor": metadata["editorial_review"]["previous_editorial_review"]["decision"] = "reject"
    elif attack == "source_flag": metadata["article_body_complete"] = False
    elif attack == "scalar_proof": metadata["editorial_review"] = "approved"
    assert errors(reviewed)


def make_generic(value):
    root = value["root"]
    document = json.loads((root / NEW5).read_bytes())
    reader = json.loads((root / document["independent_review"]["path"]).read_bytes())
    paths = dict(history="data/history/superintendencia_signals.json", queue="data/state/pending_queue.json",
                 runtime_report="data/audits/pulso_runtime_2026_10_11.json", telemetry="data/ai_usage/responses.jsonl")
    reader["inputs"] = {key: dict(commit=qa.FOCUS_PRODUCER, path=path, file_sha256=qa.digest(producer(path)))
                        for key, path in paths.items()}
    reader_path, audit_path = "data/audits/pulso_temporary_independent_reader.json", "data/audits/pulso_temporary_paid_correction.json"
    reader_sha = encoded(root, reader_path, reader)
    document["independent_review"] = dict(path=reader_path, sha256=reader_sha)
    document["review_id"] = "temporary_same_actual_paid_originals"
    for row, parent in zip(document["records"], reader["all_signals"]):
        row["independent_review_record_sha256"] = qa.object_digest(parent)
    audit_sha = encoded(root, audit_path, document)
    registry = json.loads((root / qa.EDITORIAL_REGISTRY_PATH).read_bytes())
    registry["reviews"].append(dict(review_file=audit_path, review_sha256=audit_sha,
        independent_review_file=reader_path, independent_review_sha256=reader_sha))
    encoded(root, qa.EDITORIAL_REGISTRY_PATH, registry)
    return document, reader, audit_path, reader_path


def bind_generic(value, document, reader, audit_path, reader_path):
    root = value["root"]
    for record, parent in zip(document["records"], reader["all_signals"]):
        record["independent_review_record_sha256"] = qa.object_digest(parent)
    document["independent_review"]["sha256"] = encoded(root, reader_path, reader)
    audit_sha = encoded(root, audit_path, document)
    registry = json.loads((root / qa.EDITORIAL_REGISTRY_PATH).read_bytes())
    entry = next(entry for entry in registry["reviews"] if entry["review_file"] == audit_path)
    entry.update(review_sha256=audit_sha, independent_review_sha256=document["independent_review"]["sha256"])
    encoded(root, qa.EDITORIAL_REGISTRY_PATH, registry)


def test_registered_future_pair_requires_same_genuine_paid_producer_without_code_changes(real_originals):
    _, _, path, _ = make_generic(real_originals)
    apply_temporary(real_originals, path)
    proofs, failures = qa.verify_additional_editorial_reviews(**real_originals)
    assert failures == [] and len(proofs) == 5


@pytest.mark.parametrize("attack", ["no_registration", "wrong_registration", "missing_producer", "mutable_head",
    "producer_hash", "duplicate_reader", "fabricated_signal", "fabricated_assessment", "reader_copy", "empty_quotes",
    "raised_score", "extra_correction_field", "wrong_body", "wrong_response", "unacknowledged_record"])
def test_even_rehashed_dual_audits_cannot_self_authorize_or_fabricate_paid_publication(real_originals, attack):
    value = real_originals
    document, reader, path, reader_path = make_generic(value)
    if attack == "missing_producer": reader["inputs"].pop("telemetry")
    elif attack == "mutable_head": reader["inputs"]["queue"]["commit"] = "HEAD"
    elif attack == "producer_hash": reader["inputs"]["queue"]["file_sha256"] = "0" * 64
    elif attack == "duplicate_reader": reader["all_signals"].append(deepcopy(reader["all_signals"][0]))
    elif attack == "fabricated_signal":
        document["records"][0]["original_signal"]["what_happened"] += " Fabricated paid output."
        record = document["records"][0]; parent = reader["all_signals"][0]
        record["original_signal_sha256"] = qa.object_digest(record["original_signal"])
        parent.update(original_full_signal=deepcopy(record["original_signal"]), original_signal_sha256=record["original_signal_sha256"],
                      original_published_what_happened=record["original_signal"]["what_happened"])
    elif attack == "fabricated_assessment": document["records"][0]["original_model_assessment"]["analysis_reason"] = "invented"
    elif attack == "reader_copy": reader["all_signals"][1]["proposed_why_it_matters"] += " invented"
    elif attack == "empty_quotes": document["records"][0]["evidence_quotes"] = []
    elif attack == "raised_score":
        record, parent = document["records"][0], reader["all_signals"][0]
        record["original_signal"]["editorial_relevance"] = 99
        record["original_signal_sha256"] = qa.object_digest(record["original_signal"])
        parent.update(original_full_signal=deepcopy(record["original_signal"]), original_signal_sha256=record["original_signal_sha256"])
    elif attack == "extra_correction_field": document["records"][1]["proposed"]["event_date"] = "2026-10-11"
    elif attack == "wrong_body": reader["all_signals"][0]["original_full_primary_body"] += "invented"
    elif attack == "wrong_response": reader["all_signals"][0]["original_output_binding"]["model_response"]["response_id"] = "invented"
    bind_generic(value, document, reader, path, reader_path)
    # All mutations, including document hashes, are deliberately synchronized.
    # Use valid base state then reconstruct claimed proof from the mutated audit.
    try:
        apply_temporary(value, path)
    except ValueError:
        apply_temporary(value, NEW5)
        for item in value["queue"].values():
            proof = item["raw"]["metadata"]["editorial_review"]
            record = next(row for row in document["records"] if row["url"] == item["raw"]["url"])
            proof.update(review_file=path, review_sha256=qa.digest((value["root"] / path).read_bytes()),
                         review_id=document["review_id"], record_sha256=qa.object_digest(record))
        for signal in value["history"]:
            signal["editorial_review"] = deepcopy(next(item["raw"]["metadata"]["editorial_review"]
                for item in value["queue"].values() if item["raw"]["url"] == signal["source_url"]))
        value["snapshot"] = dict(signals=deepcopy(value["history"]))
    if attack in {"no_registration", "wrong_registration"}:
        registry = json.loads((value["root"] / qa.EDITORIAL_REGISTRY_PATH).read_bytes())
        if attack == "no_registration": registry["reviews"] = []
        else: registry["reviews"][-1]["review_sha256"] = "0" * 64
        encoded(value["root"], qa.EDITORIAL_REGISTRY_PATH, registry)
    elif attack == "unacknowledged_record":
        value["history"].pop()
        value["queue"].pop(next(reversed(value["queue"])))
        value["snapshot"]["signals"] = deepcopy(value["history"])
    assert errors(value)


def test_real_paid_retry_cannot_be_turned_into_publication_by_synchronized_flags_and_dual_audit(real_originals):
    value = real_originals
    document, reader, path, reader_path = make_generic(value)
    actual = json.loads(producer("data/state/pending_queue.json"))
    key, pending = next((key, row) for key, row in actual.items() if row.get("source") == qa.SOURCE
        and row.get("status") == "retry" and row["raw"].get("metadata", {}).get("analysis_model_output", {}).get("relevance_score", 0) >= 72
        and row["raw"]["metadata"].get("analysis_input_format") == "full_primary_article_body")
    item = deepcopy(pending)
    raw, metadata = item["raw"], item["raw"]["metadata"]
    model = metadata["analysis_model_output"]
    fake = deepcopy(document["records"][0]["original_signal"])
    fake.update(source_url=raw["url"], event_date=raw["event_date"], publication_date=raw["event_date"],
                title=raw["title"], what_happened=model["what_happened"], why_it_matters=model["why_it_matters"],
                editorial_relevance=model["relevance_score"])
    record = deepcopy(document["records"][0])
    assessment = dict(decision="published", relevance_score=fake["editorial_relevance"], threshold=72,
                      analysis_reason=model["reason"])
    body = metadata["page_text"]
    record.update(url=raw["url"], publication_date=raw["event_date"], original_signal=fake,
                  original_signal_sha256=qa.object_digest(fake), original_model_assessment=assessment,
                  original_body_sha256=qa.digest(body.encode()), evidence_quotes=[body[:100]], decision="accept")
    parent = deepcopy(reader["all_signals"][0])
    parent.update(url=raw["url"], publication_date=raw["event_date"], original_full_signal=fake,
        original_signal_sha256=qa.object_digest(fake), original_published_what_happened=fake["what_happened"],
        original_published_why_it_matters=fake["why_it_matters"], original_full_primary_body=body,
        original_body_sha256=record["original_body_sha256"], original_html_sha256=metadata["html_sha256"],
        decision="accept", exact_reason=record["reason"], supporting_verbatim_quotes=[dict(text=body[:100], origin="original")],
        original_output_binding=dict(signal_sha256=qa.object_digest(fake),
            retained_model_output_semantic_sha256=qa.object_digest(model), model_response=model["_pulso_analysis_meta"]))
    document["records"], reader["all_signals"] = [record], [parent]
    bind_generic(value, document, reader, path, reader_path)
    item["status"] = "published"  # The attack, not a genuine editorial outcome.
    metadata.update(editorial_assessment=assessment, what_happened=fake["what_happened"], why_it_matters=fake["why_it_matters"])
    value["queue"], value["history"] = {key: item}, [fake]
    apply_temporary(value, path)
    failures = errors(value)
    assert any(row.get("error") == "editorial_original_not_in_immutable_paid_history" for row in failures)
    assert pending["status"] == "retry" and pending["raw"]["metadata"]["editorial_assessment"]["decision"] == "pending"
