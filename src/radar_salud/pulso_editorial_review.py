"""Apply reviewed original evidence to observed model outputs, without replaying AI.

This is an explicit, hash-bound editorial correction of terminal publications.
Discovery cannot invoke it, clear seen state, replace primary text, or reset queues.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from .pulso_source import article_url


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def normalized(value):
    return " ".join(str(value).split())


def apply_review(history, queue, audit, *, audit_sha256, audit_path):
    """Validate the entire review before returning any modified state.

    The caller persists returned copies; all original API outputs remain in the
    review and in correction provenance. Re-applying an identical review is inert.
    """
    if audit.get("schema_version") != "pulso_editorial_review_v1" or not audit.get("review_id"):
        raise ValueError("invalid_editorial_review_schema")
    records = audit.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("empty_editorial_review")
    output = deepcopy(history)
    updated_queue = deepcopy(queue)
    indexed = {}
    for signal in output:
        key = (signal.get("source_url"), signal.get("event_date"))
        if key in indexed:
            raise ValueError("duplicate_history_identity")
        indexed[key] = signal
    reviewed = {}
    for record in records:
        key = (record.get("url"), record.get("publication_date"))
        if key in reviewed:
            raise ValueError("duplicate_editorial_review_identity")
        reviewed[key] = record
    plans = []
    for key, record in reviewed.items():
        url, day = key
        if article_url(url) != url:
            raise ValueError("invalid_review_original_url")
        signal = indexed.get(key)
        original = record.get("original_signal")
        if not isinstance(original, dict) or canonical_sha(original) != record.get("original_signal_sha256"):
            raise ValueError("original_model_output_hash_mismatch")
        if not signal or (original.get("source_url"), original.get("event_date")) != key:
            raise ValueError("review_signal_not_found")
        if (original.get("evidence_maturity") != "media_reported"
                or original.get("publication_date") != day
                or int(original.get("editorial_relevance") or 0) < 72):
            raise ValueError("review_cannot_approve_missing_original_gate_or_media_evidence")
        candidates = [(k, item) for k, item in updated_queue.items()
                      if item.get("source") == "pulso_latercera"
                      and item.get("raw", {}).get("url") == url
                      and item.get("raw", {}).get("event_date") == day]
        if len(candidates) != 1:
            raise ValueError("review_queue_identity_not_unique")
        queue_key, item = candidates[0]
        metadata = item["raw"].get("metadata") or {}
        body = metadata.get("page_text") or ""
        body_sha = hashlib.sha256(body.encode()).hexdigest()
        if (not body or body_sha != record.get("original_body_sha256")
                or metadata.get("article_body_sha256") != body_sha
                or metadata.get("analysis_base_article_body_sha256") != body_sha
                or metadata.get("canonical_url") != url
                or metadata.get("publication_date") != day
                or any(metadata.get(field) is not True for field in
                       ("article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified"))):
            raise ValueError("review_original_primary_body_or_date_mismatch")
        decision = record.get("decision")
        if decision not in {"accept", "reject", "group", "correct"} or not normalized(record.get("reason", "")):
            raise ValueError("invalid_review_decision_or_reason")
        quotes = record.get("evidence_quotes")
        if not isinstance(quotes, list) or not quotes or any(
                not isinstance(quote, str) or len(normalized(quote)) < 20
                or normalized(quote) not in normalized(body) for quote in quotes):
            raise ValueError("editorial_review_quote_not_in_original_body")
        duplicate = record.get("duplicate_of")
        if decision == "group":
            if not isinstance(duplicate, dict):
                raise ValueError("group_requires_surviving_signal")
            target = (duplicate.get("url"), duplicate.get("event_date"))
            if target == key or target not in indexed or reviewed.get(target, {}).get("decision") in {"reject", "group"}:
                raise ValueError("group_surviving_signal_missing_or_withdrawn")
        proposed = record.get("proposed") or {}
        if decision == "correct":
            if (not {"what_happened", "why_it_matters"}.issubset(proposed)
                    or not set(proposed).issubset({"what_happened", "why_it_matters", "category"})
                    or ("category" in proposed and proposed["category"] != "Prestadores")
                    or not all(isinstance(value, str) for value in proposed.values())
                    or len(proposed["what_happened"].strip()) < 45
                    or len(proposed["why_it_matters"].strip()) < 35
                    or not re.search(r"pulso|la tercera", proposed["what_happened"], re.I)
                    or record.get("event_status") not in {"reported", "proposed", "planned", "historical"}):
                raise ValueError("invalid_reviewed_copy_correction")
        previous = signal.get("editorial_review") or {}
        if previous:
            if previous.get("review_sha256") != audit_sha256 or previous.get("record_sha256") != canonical_sha(record):
                raise ValueError("conflicting_existing_editorial_review")
            expected = deepcopy(original)
            expected.update(editorial_review=previous, editorial_decision="reject" if decision == "reject" else
                            "group" if decision == "group" else "accept",
                            editorial_review_reason=record["reason"], feed_visibility=decision not in {"reject", "group"})
            if decision == "correct":
                expected.update(proposed, event_status=record["event_status"],
                                prospective_evidence=record["event_status"] in {"proposed", "planned"})
            if signal != expected or item.get("status") != ("rejected" if decision in {"reject", "group"} else "published"):
                raise ValueError("previous_editorial_review_state_tampered")
            if metadata.get("editorial_review") != previous:
                raise ValueError("queue_history_editorial_review_mismatch")
            expected_assessment = record.get("original_model_assessment")
            if decision in {"reject", "group"}:
                reason = "independent_editorial_review:" + record["reason"]
                expected_assessment = dict(decision="rejected", reason=reason,
                                           relevance_score=original["editorial_relevance"], threshold=72,
                                           original_model_assessment=record["original_model_assessment"],
                                           review_sha256=audit_sha256)
                if item.get("last_error") != reason or metadata.get("rejection_reason") != reason:
                    raise ValueError("reviewed_rejection_reason_changed")
            elif decision == "correct":
                expected_assessment = dict(decision="published", reason="independent_editorial_copy_corrected",
                                           relevance_score=original["editorial_relevance"], threshold=72,
                                           original_model_assessment=record["original_model_assessment"],
                                           review_sha256=audit_sha256)
            if (metadata.get("editorial_assessment") != expected_assessment
                    or metadata.get("what_happened") != signal["what_happened"]
                    or metadata.get("why_it_matters") != signal["why_it_matters"]):
                raise ValueError("reviewed_effective_model_output_changed")
            continue
        if signal != original or item.get("status") != "published":
            raise ValueError("observed_original_signal_or_terminal_status_changed")
        assessment = metadata.get("editorial_assessment") or {}
        if (assessment != record.get("original_model_assessment") or assessment.get("decision") != "published"
                or assessment.get("threshold") != 72
                or assessment.get("relevance_score") != original["editorial_relevance"]
                or item.get("attempts", 0) < 1):
            raise ValueError("observed_original_model_assessment_mismatch")
        provenance = dict(schema_version="pulso_editorial_review_v1", review_id=audit["review_id"],
                          review_file=audit_path, review_sha256=audit_sha256, record_sha256=canonical_sha(record),
                          original_signal_sha256=record["original_signal_sha256"], original_body_sha256=body_sha,
                          publication_date=day, decision=decision, reason=record["reason"],
                          evidence_quotes=quotes, original_terminal_status="published",
                          original_model_assessment=deepcopy(assessment),
                          original_model_what_happened=original["what_happened"],
                          original_model_why_it_matters=original["why_it_matters"])
        if duplicate:
            provenance["duplicate_of"] = duplicate
        plans.append((signal, item, record, provenance))
    for signal, item, record, provenance in plans:
        decision = record["decision"]
        signal.update(editorial_review=provenance,
                      editorial_decision="reject" if decision == "reject" else "group" if decision == "group" else "accept",
                      editorial_review_reason=record["reason"], feed_visibility=decision not in {"reject", "group"})
        metadata = item["raw"]["metadata"]
        metadata["editorial_review"] = deepcopy(provenance)
        if decision in {"reject", "group"}:
            item.update(status="rejected", last_error="independent_editorial_review:" + record["reason"])
            metadata["rejection_reason"] = item["last_error"]
            metadata["editorial_assessment"] = dict(decision="rejected", reason=item["last_error"],
                                                    relevance_score=signal["editorial_relevance"], threshold=72,
                                                    original_model_assessment=provenance["original_model_assessment"],
                                                    review_sha256=audit_sha256)
        elif decision == "correct":
            signal.update(record["proposed"], event_status=record["event_status"],
                          prospective_evidence=record["event_status"] in {"proposed", "planned"})
            metadata.update(record["proposed"])
            metadata["editorial_assessment"] = dict(decision="published", reason="independent_editorial_copy_corrected",
                                                    relevance_score=signal["editorial_relevance"], threshold=72,
                                                    original_model_assessment=provenance["original_model_assessment"],
                                                    review_sha256=audit_sha256)
    return output, updated_queue, dict(review_id=audit["review_id"], review_sha256=audit_sha256,
                                      reviewed_count=len(records), applied_count=len(plans),
                                      unchanged_on_replay=len(records) - len(plans),
                                      decisions={d: sum(r["decision"] == d for r in records)
                                                 for d in ("accept", "reject", "group", "correct")},
                                      ai_calls=0, primary_evidence_mutations=0, queue_attempt_resets=0)
