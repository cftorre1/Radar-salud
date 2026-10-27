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
from .editorial_gate import RELEVANCE_WITHDRAWAL_REASONS, publication_ready


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def normalized(value):
    return " ".join(str(value).split())


def validate_independent_binding(audit, independent, *, independent_sha256):
    """The correction must reproduce every decision of the separate reader."""
    proof = audit.get("independent_review") or {}
    if proof.get("sha256") != independent_sha256 or independent.get("source_id") != "pulso_latercera":
        raise ValueError("independent_review_file_hash_or_source_mismatch")
    originals = {(r["url"], r["publication_date"]): r for r in independent.get("all_signals", [])}
    records = audit.get("records") or []
    if not originals or len(records) != len(originals) or set(originals) != {
            (r.get("url"), r.get("publication_date")) for r in records}:
        raise ValueError("independent_review_complete_coverage_mismatch")
    for record in records:
        parent = originals[(record["url"], record["publication_date"])]
        original = record.get("original_signal") or {}
        if (record.get("independent_review_record_sha256") != canonical_sha(parent)
                or record.get("decision") != parent.get("decision")
                or record.get("reason") != parent.get("exact_reason")
                or record.get("original_body_sha256") != parent.get("original_body_sha256")
                or original.get("what_happened") != parent.get("original_published_what_happened")
                or original.get("why_it_matters") != parent.get("original_published_why_it_matters")
                or parent.get("full_original_body_read") is not True
                or parent.get("full_signal_read") is not True):
            raise ValueError("independent_review_decision_or_original_binding_mismatch")
        approved_quotes = {q["text"] for q in parent.get("supporting_verbatim_quotes", []) if q.get("origin") == "original"}
        if not set(record.get("evidence_quotes") or []).issubset(approved_quotes):
            raise ValueError("independent_review_did_not_supply_original_quote")
        if record["decision"] == "correct":
            approved = dict(what_happened=parent["proposed_what_happened"], why_it_matters=parent["proposed_why_it_matters"])
            if parent.get("proposed_category"):
                approved["category"] = parent["proposed_category"]
            if record.get("proposed") != approved:
                raise ValueError("copy_correction_not_independently_reviewed")
        if (record.get("previous_editorial_review") is not None
                and record["previous_editorial_review"] != parent.get("previous_editorial_review")):
            raise ValueError("review_predecessor_not_independently_bound")
        if record["decision"] == "group" and (record.get("duplicate_of") or {}).get("url") != parent.get("duplicate_of"):
            raise ValueError("group_target_not_independently_reviewed")
        if (record["decision"] == "group" and record.get("previous_editorial_review") is not None
                and record.get("duplicate_of") != parent.get("duplicate_survivor_binding")):
            raise ValueError("reviewed_group_survivor_not_independently_bound")


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
    reviewed = {}
    for record in records:
        key = (record.get("url"), record.get("publication_date"))
        if key in reviewed:
            raise ValueError("duplicate_editorial_review_identity")
        reviewed[key] = record
    # Native official sources can publish several distinct offices at one
    # listing URL on the same day. Their unrelated identities must remain
    # untouched by a publisher-specific correction. Reviewed publications and
    # explicitly named group survivors must still identify exactly one row.
    required_identities = set(reviewed)
    required_identities.update(
        (record["duplicate_of"].get("url"), record["duplicate_of"].get("event_date"))
        for record in records if record.get("decision") == "group"
        and isinstance(record.get("duplicate_of"), dict))
    indexed = {}
    for signal in output:
        key = (signal.get("source_url"), signal.get("event_date"))
        if key not in required_identities and not article_url(str(key[0] or "")):
            continue
        if key in indexed:
            raise ValueError("duplicate_history_identity")
        indexed[key] = signal
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
            survivor = deepcopy(indexed[target])
            if reviewed.get(target, {}).get("decision") == "correct":
                survivor.update(reviewed[target].get("proposed") or {})
            if (survivor.get("feed_visibility") is False or survivor.get("editorial_decision") in {"reject", "group"}
                    or not (publication_ready(deepcopy(survivor))[0]
                            or publication_ready(deepcopy(survivor))[1] in RELEVANCE_WITHDRAWAL_REASONS)
                    or int(survivor.get("editorial_relevance") or 0) < 72
                    or (article_url(target[0]) and survivor.get("evidence_maturity") != "media_reported")):
                raise ValueError("group_surviving_signal_not_eligible")
            target_queue = [(fingerprint, candidate) for fingerprint, candidate in updated_queue.items()
                            if candidate.get("raw", {}).get("url") == target[0]
                            and candidate.get("raw", {}).get("event_date") == target[1]]
            if duplicate.get("queue_fingerprint") is not None:
                target_queue = [(fingerprint, candidate) for fingerprint, candidate in target_queue
                                if fingerprint == duplicate["queue_fingerprint"]
                                and candidate.get("source") == duplicate.get("source_id")]
                if (set(duplicate) != {"url", "event_date", "queue_fingerprint", "source_id", "survivor_signal_sha256"}
                        or canonical_sha(indexed[target]) != duplicate.get("survivor_signal_sha256")):
                    raise ValueError("group_surviving_signal_binding_changed")
            if len(target_queue) != 1 or target_queue[0][1].get("status") != "published":
                raise ValueError("group_surviving_signal_not_actually_published")
        proposed = record.get("proposed") or {}
        if decision == "correct":
            if (not {"what_happened", "why_it_matters"}.issubset(proposed)
                    or not set(proposed).issubset({"what_happened", "why_it_matters", "category"})
                    or ("category" in proposed and proposed["category"] not in {"Prestadores", "Regulación & Legal"})
                    or not all(isinstance(value, str) for value in proposed.values())
                    or len(proposed["what_happened"].strip()) < 45
                    or len(proposed["why_it_matters"].strip()) < 35
                    or not re.search(r"pulso|la tercera", proposed["what_happened"], re.I)
                    or record.get("event_status") not in {"reported", "proposed", "planned", "historical"}):
                raise ValueError("invalid_reviewed_copy_correction")
            corrected = deepcopy(original)
            corrected.update(proposed)
            ok, gate_reason, _ = publication_ready(corrected)
            # A later Dirección relevance rule withdraws the card from the feed; the correction stays valid.
            if not ok and gate_reason not in RELEVANCE_WITHDRAWAL_REASONS:
                raise ValueError("reviewed_copy_fails_existing_publication_gate")
        original_assessment = record.get("original_model_assessment")
        provenance = dict(schema_version="pulso_editorial_review_v1", review_id=audit["review_id"],
                          review_file=audit_path, review_sha256=audit_sha256, record_sha256=canonical_sha(record),
                          original_signal_sha256=record["original_signal_sha256"], original_body_sha256=body_sha,
                          publication_date=day, decision=decision, reason=record["reason"],
                          evidence_quotes=quotes, original_terminal_status="published",
                          original_model_assessment=deepcopy(original_assessment),
                          original_model_what_happened=original["what_happened"],
                          original_model_why_it_matters=original["why_it_matters"])
        predecessor = record.get("previous_editorial_review")
        if predecessor is not None:
            # An independently bound follow-up may clarify an observation date
            # or group a publication against an exact surviving record. It
            # cannot undo a rejection/group,
            # alter the original score, or replace previous review evidence.
            reviewed_group = (decision == "group" and not proposed
                              and isinstance(duplicate, dict)
                              and set(duplicate) == {"url", "event_date", "queue_fingerprint", "source_id", "survivor_signal_sha256"})
            historical_correction = (decision == "correct" and record.get("event_status") == "historical"
                                     and set(proposed) == {"what_happened", "why_it_matters"}
                                     and proposed["what_happened"] == original.get("what_happened"))
            if (not isinstance(predecessor, dict)
                    or predecessor != original.get("editorial_review")
                    or predecessor.get("schema_version") != "pulso_editorial_review_v1"
                    or predecessor.get("decision") not in ({"accept", "correct"} if reviewed_group else {"accept"})
                    or predecessor.get("original_terminal_status") != "published"
                    or predecessor.get("publication_date") != day
                    or predecessor.get("original_body_sha256") != body_sha
                    or original.get("editorial_decision") != "accept"
                    or original.get("feed_visibility") is not True
                    or not (reviewed_group or historical_correction)):
                raise ValueError("invalid_observation_date_review_predecessor")
            provenance["previous_editorial_review"] = deepcopy(predecessor)
        if duplicate:
            provenance["duplicate_of"] = duplicate
        previous = signal.get("editorial_review") or {}
        chained_initial_state = predecessor is not None and previous == predecessor
        if previous and not chained_initial_state:
            if previous != provenance:
                raise ValueError("conflicting_existing_editorial_review")
            expected = deepcopy(original)
            expected.update(editorial_review=previous, editorial_decision="reject" if decision == "reject" else
                            "group" if decision == "group" else "accept",
                            editorial_review_reason=record["reason"], feed_visibility=decision not in {"reject", "group"})
            if decision == "correct":
                expected.update(proposed, event_status=record["event_status"],
                                prospective_evidence=record["event_status"] in {"proposed", "planned"})
            if signal != expected:
                raise ValueError("previous_editorial_review_state_tampered")
            # History is persisted before queue acknowledgement, as in the core.
            # Resume only the exact original published queue state after a crash.
            if (not metadata.get("editorial_review") and item.get("status") == "published"
                    and metadata.get("editorial_assessment") == record.get("original_model_assessment")
                    and metadata.get("what_happened") == original["what_happened"]
                    and metadata.get("why_it_matters") == original["why_it_matters"]
                    and item.get("attempts", 0) >= 1):
                plans.append((signal, item, record, provenance))
                continue
            if item.get("status") != ("rejected" if decision in {"reject", "group"} else "published"):
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
        if chained_initial_state and metadata.get("editorial_review") != predecessor:
            raise ValueError("queue_history_editorial_review_mismatch")
        if metadata.get("what_happened") != original["what_happened"] or metadata.get("why_it_matters") != original["why_it_matters"]:
            raise ValueError("observed_original_queue_model_prose_mismatch")
        assessment = metadata.get("editorial_assessment") or {}
        if (assessment != record.get("original_model_assessment") or assessment.get("decision") != "published"
                or assessment.get("threshold") != 72
                or assessment.get("relevance_score") != original["editorial_relevance"]
                or item.get("attempts", 0) < 1):
            raise ValueError("observed_original_model_assessment_mismatch")
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
