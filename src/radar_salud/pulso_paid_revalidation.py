"""Reuse only an independently classified, unchanged genuine paid answer.

This module grants one processing attempt, never publication. The original
producer, model answer and API receipt remain immutable; a new validator has
its own receipt. Contract defects always require a new FAST assessment.
"""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess

from .llm_analysis import news_analysis_input
from .pulso_source import complete_article_body

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_REF = "data/audits/pulso_v5_paid_guard_revalidation_manifest_2026_10_11.json"
MANIFEST_SHA256 = "3645971793d5803c53b3a9f0f5bcb1b8e8f91ef5638b186aeaab4073645a48ff"
PRODUCER_STATE = "981b0ff25c226d47785b77944aa53c459053aa21"
PRODUCER_CODE = "03bf998a4bb5840c84da6473666e932fbc5cedd9"
PRODUCER_FINGERPRINT = "4feb04bc17ac24d37bd5cbb07f12893f5e8202de61aa7133b8fb1a8aeb6a4118"
PRODUCER_FILES = {
    "data/state/pending_queue.json": "4cf450c4e0ab8b1238af11833dcc65b037382bae5b2ff0da93bc5539e1bbbf8f",
    "data/audits/pulso_runtime_2026_10_11.json": "c42683a457229a23bf35fbc1a658af5a8617411f615d4dcb0ddcaa5b03c4f43b",
    "data/ai_usage/responses.jsonl": "d5cbef5b62630ab6f17305c29bfea987f788313e0876d15d6a02c115b2a30c30",
}
PRODUCER_HISTORY_SHA256 = "f779385fed3eccf96d0e6d95ebfece23d1e79d83d6a0a8675b80615a63c121fa"
DISPOSITIONS = {"reuse_code_fn", "reuse_below_gate_reject", "assess_contract_or_semantic_defect"}
STAMP = "paid_guard_revalidation_admission"
RECEIPT = "paid_guard_revalidation_receipt"
NEW_FAST_RECEIPTS = "paid_guard_new_fast_attempt_receipts"


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()


def paid_raw(raw):
    result = deepcopy(raw)
    result["metadata"].pop("evidence_revisions", None)
    return result


def original_pin(key, entry):
    raw, meta = entry["raw"], entry["raw"]["metadata"]
    model, validation = meta["analysis_model_output"], meta["pulso_editorial_proof_validation"]
    receipt = model["_pulso_analysis_meta"]
    return dict(url=raw["url"], queue_fingerprint=key, publication_date=raw["event_date"],
                title=raw["title"], source_name=raw["source_name"], source_type=raw["source_type"], original_attempts=entry["attempts"],
                original_html_sha256=meta["html_sha256"], body_sha256=meta["article_body_sha256"],
                body_characters=len(meta["page_text"]), request_input_sha256=meta["analysis_request_input_sha256"],
                analysis_input_sha256=meta["analysis_input_body_sha256"], original_response_id=receipt["response_id"],
                model_output_sha256=digest(model), raw_model_output_sha256=receipt["raw_model_output_sha256"],
                previous_validation_sha256=digest(validation), previous_reason=entry["reason"],
                original_paid_raw_sha256=digest(paid_raw(raw)))


@lru_cache(maxsize=2)
def _producer(root):
    objects = {}
    for path, expected in PRODUCER_FILES.items():
        result = subprocess.run(["git", "show", PRODUCER_STATE + ":" + path], cwd=root, capture_output=True)
        if result.returncode or digest(result.stdout) != expected:
            raise ValueError("paid_original_producer_blob_unavailable_or_changed")
        objects[path] = result.stdout
    report = json.loads(objects["data/audits/pulso_runtime_2026_10_11.json"])
    execution = report.get("last_core_execution") or report["execution"]
    if (execution.get("code_sha") != PRODUCER_CODE
            or execution.get("runtime_fingerprint", {}).get("sha256") != PRODUCER_FINGERPRINT
            or execution.get("mode") != "real_core_processing"
            or execution.get("engine_called") is not True or execution.get("engine_completed") is not True
            or execution.get("ai_guardrails_modified") is not False):
        raise ValueError("paid_original_execution_unverified")
    events = [json.loads(line) for line in objects["data/ai_usage/responses.jsonl"].splitlines() if line]
    start = datetime.fromisoformat(execution["started_at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(execution["finished_at"].replace("Z", "+00:00"))
    events = [event for event in events if event.get("at") and start <= datetime.fromisoformat(
        event["at"].replace("Z", "+00:00")) <= end]
    if (len(events) != 69 or any(event.get("kind") != "fast" or event.get("success") is not True for event in events)
            or len({event.get("response_id") for event in events}) != 69
            or any(not event.get("response_id") for event in events)):
        raise ValueError("paid_original_successful_response_receipts_unverified")
    for field in ("attempted", "successful"):
        if (execution["budget_after"]["month"]["fast"][field]
                - execution["budget_before"]["month"]["fast"][field] != 69):
            raise ValueError("paid_original_positive_ledger_unverified")
    queue = json.loads(objects["data/state/pending_queue.json"])
    held = {key:entry for key,entry in queue.items() if entry.get("source") == "pulso_latercera"
            and entry.get("status") == "retry"
            and entry.get("raw", {}).get("metadata", {}).get("analysis_model_output", {}).get(
                "_pulso_analysis_meta", {}).get("response_id") in {event["response_id"] for event in events}}
    if len(held) != 49:
        raise ValueError("paid_original_complete_49_pending_set_unverified")
    return held


def load_manifest(root=ROOT):
    root = Path(root)
    payload = (root / MANIFEST_REF).read_bytes()
    if digest(payload) != MANIFEST_SHA256:
        raise ValueError("paid_revalidation_manifest_unpinned")
    document = json.loads(payload)
    if (document.get("schema_version") != "pulso_v5_paid_guard_revalidation_manifest_v1"
            or document.get("source_id") != "pulso_latercera"
            or document.get("producer_state_commit") != PRODUCER_STATE
            or document.get("producer_core_checkout") != PRODUCER_CODE
            or document.get("producer_runtime_fingerprint_sha256") != PRODUCER_FINGERPRINT):
        raise ValueError("paid_revalidation_manifest_producer_invalid")
    references = document.get("semantic_references", [])
    if len(references) != 2 or len({ref.get("path") for ref in references}) != 2:
        raise ValueError("paid_revalidation_two_independent_semantic_reviews_required")
    for reference in references:
        path = (root / reference["path"]).resolve()
        if not path.is_relative_to((root / "data/audits").resolve()) or digest(path.read_bytes()) != reference["sha256"]:
            raise ValueError("paid_revalidation_semantic_review_changed")
    originals = _producer(str(root))
    rows = document.get("rows", [])
    if (len(rows) != 49 or len({row.get("url") for row in rows}) != 49
            or {row.get("queue_fingerprint") for row in rows} != set(originals)):
        raise ValueError("paid_revalidation_complete_original_49_required")
    counts = {name:0 for name in DISPOSITIONS}
    normalized_rows = []
    for row in rows:
        entry = originals[row["queue_fingerprint"]]
        raw, metadata = entry["raw"], entry["raw"]["metadata"]
        expected = original_pin(row["queue_fingerprint"], entry)
        direct = {field:expected[field] for field in ("url", "title", "queue_fingerprint", "original_attempts", "original_response_id", "original_html_sha256")}
        direct.update(original_publication_date=expected["publication_date"], original_body_sha256=expected["body_sha256"],
                      original_request_input_sha256=expected["request_input_sha256"], original_analysis_input_sha256=expected["analysis_input_sha256"],
                      original_model_output_sha256=expected["model_output_sha256"], original_raw_model_output_sha256=expected["raw_model_output_sha256"],
                      original_validation_sha256=expected["previous_validation_sha256"], original_raw_sha256=digest(raw),
                      original_metadata_sha256=digest(metadata), actual_queue_entry_sha256=digest(entry),
                      original_full_primary_body=metadata["page_text"], original_full_model_output=metadata["analysis_model_output"],
                      actual_pulso_validation=metadata["pulso_editorial_proof_validation"], actual_reason=entry["reason"],
                      actual_score=metadata["analysis_model_output"]["relevance_score"])
        if (any(row.get(field) != value for field,value in direct.items()) or row.get("disposition") not in DISPOSITIONS
                or row.get("runtime_route") != row["disposition"] or row.get("semantic_reference") not in references
                or row.get("editorial_gate") != 72 or row.get("publication_approved") is not False
                or row.get("runtime_route_is_publication_approval") is not False):
            raise ValueError("paid_revalidation_original_pin_or_disposition_changed")
        counts[row["disposition"]] += 1
        context = row.get("reassessment_context")
        if context is not None:
            _verify_novelty_context(str(root), context, raw)
            if row["disposition"] != "assess_contract_or_semantic_defect":
                raise ValueError("paid_revalidation_novelty_context_requires_new_fast")
        normalized_rows.append(dict(expected, disposition=row["disposition"], semantic_reference=row["semantic_reference"],
                                    reassessment_context=context))
    if counts != {"reuse_code_fn":18, "reuse_below_gate_reject":6, "assess_contract_or_semantic_defect":25}:
        raise ValueError("paid_revalidation_reviewed_partition_changed")
    return dict(document, rows=normalized_rows), originals


@lru_cache(maxsize=2)
def _published_target(root, key):
    queue_bytes = subprocess.run(["git", "show", PRODUCER_STATE + ":data/state/pending_queue.json"],
        cwd=root, capture_output=True, check=True).stdout
    history_bytes = subprocess.run(["git", "show", PRODUCER_STATE + ":data/history/superintendencia_signals.json"],
        cwd=root, capture_output=True, check=True).stdout
    if digest(queue_bytes) != PRODUCER_FILES["data/state/pending_queue.json"] or digest(history_bytes) != PRODUCER_HISTORY_SHA256:
        raise ValueError("paid_revalidation_comparison_producer_changed")
    entry = json.loads(queue_bytes)[key]
    history = json.loads(history_bytes)
    rows = history["signals"] if isinstance(history, dict) else history
    signals = [signal for signal in rows if signal.get("source_url") == entry["raw"]["url"]
               and signal.get("event_date") == entry["raw"]["event_date"]]
    if len(signals) != 1:
        raise ValueError("paid_revalidation_comparison_target_not_unique")
    return entry, signals[0]


def _verify_novelty_context(root, context, source_raw):
    entry, signal = _published_target(root, context["target_queue_fingerprint"])
    target_raw, target_meta = entry["raw"], entry["raw"]["metadata"]
    assessment = target_meta.get("editorial_assessment", {})
    checks = dict(producer_state_commit=PRODUCER_STATE,
        source_publication_date=source_raw["event_date"], source_body_sha256=source_raw["metadata"]["article_body_sha256"],
        source_html_sha256=source_raw["metadata"]["html_sha256"],
        target_url=target_raw["url"], target_publication_date=target_raw["event_date"],
        target_queue_entry_sha256=digest(entry), target_raw_sha256=digest(target_raw),
        target_body_sha256=target_meta["article_body_sha256"], target_html_sha256=target_meta["html_sha256"],
        target_model_output_sha256=digest(target_meta["analysis_model_output"]),
        target_response_id=target_meta["analysis_model_output"]["_pulso_analysis_meta"]["response_id"],
        target_full_primary_body=target_meta["page_text"], target_full_original_signal=signal,
        target_full_original_signal_sha256=digest(signal), target_original_model_output=target_meta["analysis_model_output"],
        publication_approved=False, rejection_approved=False)
    if (any(context.get(field) != value for field,value in checks.items()) or entry.get("status") != "published"
            or assessment.get("decision") != "published" or assessment.get("threshold") != 72
            or signal.get("evidence_maturity") != "media_reported" or signal.get("feed_visibility") is False
            or not isinstance(signal.get("editorial_relevance"), int) or signal["editorial_relevance"] < 72):
        raise ValueError("paid_revalidation_comparison_not_bound_to_actual_published_primary")
    from .pulso_editorial_proof import literal_quote_matches
    if (not all(literal_quote_matches(quote, source_raw["metadata"]["page_text"], 8)
                for quote in context.get("source_repetition_quotes", []))
            or not all(literal_quote_matches(quote, target_meta["page_text"], 8)
                       for quote in context.get("target_repetition_quotes", []))):
        raise ValueError("paid_revalidation_comparison_quotes_unverified")


def _primary_matches(raw, pin):
    meta = raw.metadata
    binding = meta.get("primary_item_binding")
    if "primary_item_binding" in meta and (not isinstance(binding, dict) or binding.get("verified") is not True
            or binding.get("raw_url") != raw.url or binding.get("primary_canonical_url") != raw.url
            or binding.get("raw_event_date") != raw.event_date or binding.get("primary_publication_date") != raw.event_date):
        return False
    request = news_analysis_input(title=raw.title, text=meta.get("page_text", ""), source_name=raw.source_name, full_text=True)
    return bool(raw.source_slug == "pulso_latercera" and raw.url == pin["url"]
                and raw.title == pin["title"] and raw.source_name == pin["source_name"]
                and raw.source_type == pin["source_type"] == "press_high_trust"
                and meta.get("market_role") == "media"
                and raw.event_date == pin["publication_date"] == meta.get("publication_date")
                and meta.get("canonical_url") == raw.url
                and all(meta.get(field) is True for field in ("article_verified", "primary_identity_verified", "publication_date_verified"))
                and meta.get("source_quality_gate") == "passed" and complete_article_body(meta)
                and meta.get("article_body_complete") is not False and meta.get("analysis_input_complete") is not False
                and not meta.get("editorial_hold") and not meta.get("publisher_exception_reason")
                and meta.get("html_sha256") == pin["original_html_sha256"]
                and meta.get("article_body_sha256") == pin["body_sha256"]
                and len(meta["page_text"]) == pin["body_characters"]
                and digest(meta["page_text"].encode()) == pin["body_sha256"] == pin["analysis_input_sha256"]
                and digest(request.encode()) == pin["request_input_sha256"])


def _admission(row):
    result = dict(schema_version="pulso_paid_guard_revalidation_admission_v1",
                  manifest_ref=MANIFEST_REF, manifest_sha256=MANIFEST_SHA256,
                  producer_state_commit=PRODUCER_STATE, producer_core_checkout=PRODUCER_CODE,
                  producer_runtime_fingerprint_sha256=PRODUCER_FINGERPRINT,
                  disposition=row["disposition"], publication_approved=False,
                  new_model_request=row["disposition"] == "assess_contract_or_semantic_defect")
    result.update({key:row[key] for key in original_pin_fields()})
    if row.get("reassessment_context") is not None:
        result["reassessment_context_sha256"] = digest(row["reassessment_context"])
    result["admission_id"] = digest(result)
    return result


def original_pin_fields():
    return ("url", "queue_fingerprint", "publication_date", "source_type", "original_html_sha256", "body_sha256",
            "body_characters", "request_input_sha256", "analysis_input_sha256", "original_response_id",
            "model_output_sha256", "raw_model_output_sha256", "previous_validation_sha256", "previous_reason",
            "original_paid_raw_sha256", "original_attempts")


def verified_paid_revalidation_admission(fresh, previous):
    """One exact nonterminal release; never reset attempts or reopen a terminal."""
    try:
        existing = previous.get("raw", {}).get("metadata", {})
        if (previous.get("status") not in {"pending", "retry"}
                or type(previous.get("attempts")) is not int or previous["attempts"] < 1
                or existing.get("analysis_model_output", {}).get("_pulso_analysis_meta", {}).get("schema_version") != "pulso_editorial_proof_v5"
                or existing.get("pulso_editorial_proof_validation", {}).get("decision") != "deferred"
                or STAMP in existing or RECEIPT in existing):
            return None
        document, originals = load_manifest()
        row = next(row for row in document["rows"] if row["url"] == fresh.url)
        original = originals[row["queue_fingerprint"]]
        meta = previous["raw"]["metadata"]
        assessment, validation = meta.get("editorial_assessment"), meta.get("pulso_editorial_proof_validation")
        if (previous.get("status") not in {"pending", "retry"}
                or type(previous.get("attempts")) is not int or previous["attempts"] != row["original_attempts"]
                or STAMP in meta or RECEIPT in meta
                or previous.get("reason") != row["previous_reason"]
                or not isinstance(assessment, dict) or assessment.get("decision") != "pending"
                or assessment.get("reason") != previous["reason"] or assessment.get("threshold") != 72
                or not isinstance(validation, dict) or validation.get("decision") != "deferred"
                or validation.get("reason") != previous["reason"]
                or digest(paid_raw(previous["raw"])) != row["original_paid_raw_sha256"]
                or previous["raw"] != original["raw"] or not _primary_matches(fresh, row)):
            return None
        return _admission(row)
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return None


def verified_paid_processing_mode(raw):
    """Validate the stamp and archived producer before any model activity."""
    document, originals = load_manifest()
    row = next(row for row in document["rows"] if row["url"] == raw.url)
    expected = _admission(row)
    if raw.metadata.get(STAMP) != expected or not _primary_matches(raw, row):
        raise ValueError("paid_revalidation_current_primary_or_admission_unverified")
    revisions = [revision for revision in raw.metadata.get("evidence_revisions", [])
                 if revision.get("reason") == "verified_paid_guard_revalidation_admission"]
    original = originals[row["queue_fingerprint"]]
    if (len(revisions) != 1 or revisions[0].get("paid_guard_revalidation_admission") != expected
            or revisions[0].get("previous_processing_raw") != paid_raw(original["raw"])
            or digest(paid_raw(original["raw"])) != row["original_paid_raw_sha256"]):
        raise ValueError("paid_revalidation_original_paid_archive_unverified")
    current = raw.metadata.get("analysis_model_output")
    current_validation = raw.metadata.get("pulso_editorial_proof_validation")
    prior_new = raw.metadata.get(NEW_FAST_RECEIPTS, [])
    original_unchanged = (current == original["raw"]["metadata"]["analysis_model_output"]
                          and digest(current) == row["model_output_sha256"]
                          and current_validation == original["raw"]["metadata"]["pulso_editorial_proof_validation"])
    if prior_new:
        from .pulso_editorial_proof import model_binding_matches
        latest = prior_new[-1]
        ids = [record.get("new_response_id") for record in prior_new]
        # A later due retry is conventional processing of the already new paid
        # output. The one-time admission stays historical and is never cleared
        # again; every subsequent response is retained in its own full receipt.
        resumed_new = bool(expected["new_model_request"] and isinstance(latest, dict)
            and len(ids) == len(set(ids)) and expected["original_response_id"] not in ids
            and all(record.get("admission_id") == expected["admission_id"]
                    and record.get("model_output_sha256") == digest(record.get("full_model_output"))
                    and record.get("new_validation_sha256") == digest(record.get("new_validation"))
                    for record in prior_new)
            and latest.get("full_model_output") == current and latest.get("new_validation") == current_validation
            and latest.get("new_response_id") == (current or {}).get("_pulso_analysis_meta", {}).get("response_id")
            and model_binding_matches(current, source_name=raw.source_name,
                input_text_sha256=expected["analysis_input_sha256"], request_input_sha256=expected["request_input_sha256"]))
    else:
        resumed_new = False
    if not (original_unchanged and not prior_new or resumed_new) or RECEIPT in raw.metadata:
        raise ValueError("paid_revalidation_original_current_answer_or_validation_changed")
    return expected, original


def verified_reassessment_context(raw):
    admission, _ = verified_paid_processing_mode(raw)
    document, _ = load_manifest()
    row = next(row for row in document["rows"] if row["url"] == raw.url)
    context = row.get("reassessment_context")
    if context is not None and (not admission["new_model_request"]
            or digest(context) != admission.get("reassessment_context_sha256")):
        raise ValueError("paid_revalidation_comparison_context_unbound")
    return deepcopy(context)


def new_fast_attempt_receipt(raw, model, validation, *, now=None):
    """Retain a real new answer without turning its historical stamp into a lock."""
    admission, _ = verified_paid_processing_mode(raw)
    from . import pulso_editorial_proof
    response_id = (model or {}).get("_pulso_analysis_meta", {}).get("response_id")
    previous_ids = {record["new_response_id"] for record in raw.metadata.get(NEW_FAST_RECEIPTS, [])}
    if (not admission["new_model_request"] or response_id == admission["original_response_id"]
            or response_id in previous_ids or not pulso_editorial_proof.model_binding_matches(model,
                source_name=raw.source_name, input_text_sha256=admission["analysis_input_sha256"],
                request_input_sha256=admission["request_input_sha256"])):
        raise ValueError("paid_revalidation_new_fast_response_unbound_or_reused")
    expected = pulso_editorial_proof.validate_pulso_editorial_proof(model, raw.metadata["page_text"])
    expected.update(primary_article_body_sha256=admission["body_sha256"],
                    request_input_sha256=admission["request_input_sha256"], model_response=model["_pulso_analysis_meta"])
    if validation != expected:
        raise ValueError("paid_revalidation_new_fast_validation_unverified")
    return dict(schema_version="pulso_paid_guard_new_fast_attempt_receipt_v1",
                admission_id=admission["admission_id"], original_response_id=admission["original_response_id"],
                new_response_id=response_id, full_model_output=deepcopy(model), model_output_sha256=digest(model),
                new_validation=deepcopy(validation), new_validation_sha256=digest(validation),
                validator_guard_sha256=digest(Path(pulso_editorial_proof.__file__).read_bytes()),
                assessed_at=(now or datetime.now(timezone.utc)).isoformat(), new_model_request=True,
                publication_approved=False)


def unchanged_paid_output(raw):
    admission, original = verified_paid_processing_mode(raw)
    if admission["new_model_request"]:
        raise ValueError("paid_revalidation_contract_defect_requires_new_fast")
    model = raw.metadata.get("analysis_model_output")
    if model != original["raw"]["metadata"]["analysis_model_output"] or digest(model) != admission["model_output_sha256"]:
        raise ValueError("paid_revalidation_model_answer_changed")
    return deepcopy(model)


def revalidation_receipt(raw, model, validation, *, now=None):
    admission, original = verified_paid_processing_mode(raw)
    original_meta = original["raw"]["metadata"]
    if admission["new_model_request"] or model != original_meta["analysis_model_output"]:
        raise ValueError("paid_revalidation_cannot_relabel_new_or_changed_model")
    from . import pulso_editorial_proof
    expected = pulso_editorial_proof.validate_pulso_editorial_proof(model, raw.metadata["page_text"])
    expected.update(primary_article_body_sha256=admission["body_sha256"],
                    request_input_sha256=admission["request_input_sha256"], model_response=model["_pulso_analysis_meta"])
    if validation != expected:
        raise ValueError("paid_revalidation_verdict_not_actual_guard_result")
    if admission["disposition"] == "reuse_below_gate_reject" and (
            type(model.get("relevance_score")) is not int or model["relevance_score"] >= 72
            or validation.get("decision") != "rejected"
            or validation.get("reason") != "editorial_relevance_below_threshold"):
        raise ValueError("paid_revalidation_conservative_rejection_unverified")
    return dict(schema_version="pulso_paid_guard_revalidation_receipt_v1", admission=deepcopy(admission),
                producer_core_checkout=PRODUCER_CODE, producer_state_commit=PRODUCER_STATE,
                producer_runtime_fingerprint_sha256=PRODUCER_FINGERPRINT,
                original_response_id=admission["original_response_id"], original_model_output_sha256=admission["model_output_sha256"],
                original_raw_model_output_sha256=admission["raw_model_output_sha256"],
                previous_validation=deepcopy(original_meta["pulso_editorial_proof_validation"]),
                previous_validation_sha256=admission["previous_validation_sha256"],
                validator_guard_sha256=digest(Path(pulso_editorial_proof.__file__).read_bytes()),
                validator_version=pulso_editorial_proof.VERSION,
                revalidated_at=(now or datetime.now(timezone.utc)).isoformat(),
                new_validation=deepcopy(validation), new_validation_sha256=digest(validation),
                new_model_request=False, original_model_output_unchanged=True,
                publication_approved=False, quote_validation_is_semantic_approval=False)
