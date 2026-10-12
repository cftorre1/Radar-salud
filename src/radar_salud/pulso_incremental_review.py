"""Apply three reviewed legacy duplicate holds after primary verification.

The durable review permits editorial analysis, never publication. This helper
only changes RawItem metadata and cannot change queue identity or bookkeeping.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import RawItem


REVIEW_REF = "data/audits/pulso_incremental_review_2026_10_11.json"
# Reviewed evidence is repository-owned, even when RADAR_ROOT isolates runtime
# output. A changed audit requires a new explicit implementation/review version.
REVIEW_PATH = Path(__file__).resolve().parents[2] / REVIEW_REF
REVIEW_SHA256 = "e5cee8d34839a905e391e85d6187db8bcdae09c0dde7f688cc71a9f04f093ddd"
LEGACY_HOLD = "possible_duplicate_requires_incremental_review"
ADDENDUM_REF = "data/audits/pulso_oct5_incremental_addendum_2026_10_11.json"
ADDENDUM_PATH = Path(__file__).resolve().parents[2] / ADDENDUM_REF
ADDENDUM_SHA256 = "589ba50032521924803ef8ce94f40e3854930edcadddf7fc1223d9df81714160"
_DATE_SOURCES = {
    "visible_article_byline", "json_ld_datePublished",
    "article_published_time", "article_time",
}


def _load_review():
    try:
        encoded = REVIEW_PATH.read_bytes()
        if hashlib.sha256(encoded).hexdigest() != REVIEW_SHA256:
            return None
        review = json.loads(encoded)
        policy = review["editorial_policy"]
        if (review["schema_version"] != 1
                or review["source_id"] != "pulso_latercera"
                or review["verdict"] != "PASS_INCREMENTAL_TRIAGE_NOT_PUBLICATION_APPROVAL"
                or policy["media_materiality_threshold"] != 72
                or policy["threshold_changed"] is not False
                or policy["publication_approved"] is not False
                or policy["required_evidence_maturity"] != "media_reported"
                or len(review["reviews"]) != 3):
            return None
        return review
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _publisher_day(timestamp, *, timestamp_calendar=False):
    if not isinstance(timestamp, str):
        return None
    try:
        if len(timestamp) == 10:
            return date.fromisoformat(timestamp).isoformat()
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        if timestamp_calendar:
            return parsed.date().isoformat()
        return parsed.astimezone(ZoneInfo("America/Santiago")).date().isoformat()
    except ValueError:
        return None


def _primary_evidence_matches(raw, entry, reviewed_on):
    meta = raw.metadata
    body = meta.get("page_text")
    day = entry["publication_date"]
    if (meta.get("article_verified") is not True
            or meta.get("publication_date_verified") is False
            or meta.get("source_quality_gate") != "passed"
            or meta.get("market_role") != "media"
            or meta.get("canonical_url") != raw.url
            or raw.event_date != day or meta.get("publication_date") != day
            or meta.get("publication_date_source") not in _DATE_SOURCES
            or not isinstance(body, str) or len(body.strip()) < 160
            or not re.fullmatch(r"[0-9a-f]{64}", str(meta.get("html_sha256", "")))
            or hashlib.sha256(body.encode("utf-8")).hexdigest() != meta.get("article_body_sha256")):
        return False
    evidence = meta.get("publication_evidence")
    timestamp_calendar = meta.get("publisher_date_convention") == "timestamp_calendar"
    if timestamp_calendar:
        # An original byline can corroborate the timestamp's calendar day at
        # 00:xxZ instead of Santiago's preceding day. Honor that verified
        # convention only for the complete primary evidence, never a fallback.
        if (meta.get("primary_identity_verified") is not True
                or meta.get("publication_date_verified") is not True
                or meta.get("publication_date_source") != "visible_article_byline"
                or meta.get("visible_publication_date") != day
                or meta.get("possible_publication_days")
                or meta.get("publisher_exception_reason") == "publisher_conflicting_publication_dates"):
            return False
        if (not isinstance(evidence, list) or not evidence
                or any(not isinstance(item, dict)
                       or item.get("timestamp_calendar_day") != _publisher_day(
                           item.get("timestamp"), timestamp_calendar=True)
                       or item.get("america_santiago_day") != _publisher_day(item.get("timestamp"))
                       for item in evidence)
                or not any(item.get("timestamp") == meta.get("publication_timestamp")
                           for item in evidence)):
            return False
    if (not isinstance(evidence, list) or not evidence
            or any(not isinstance(item, dict)
                   or item.get("publisher_day") != day
                   or _publisher_day(item.get("timestamp"), timestamp_calendar=timestamp_calendar) != day
                   or item.get("source") not in _DATE_SOURCES for item in evidence)
            or _publisher_day(meta.get("publication_timestamp"), timestamp_calendar=timestamp_calendar) != day
            or meta.get("visible_publication_date") not in (None, day)):
        return False
    if (meta["publication_date_source"] == "visible_article_byline"
            and meta.get("visible_publication_date") != day):
        return False
    try:
        captured = datetime.fromisoformat(meta["captured_at"].replace("Z", "+00:00"))
        if (captured.tzinfo is None
                or captured.astimezone(timezone.utc).date() < date.fromisoformat(reviewed_on)
                or captured > datetime.now(timezone.utc)):
            return False
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return True


def _body_matches_review(body, entry):
    text = "".join(character for character in unicodedata.normalize("NFKD", body.lower())
                   if not unicodedata.combining(character))
    numbers = {re.sub(r"[.,]", "", value) for value in re.findall(r"\d[\d.,]*", text)}
    path = entry["source_url"]
    if "presupuesto-salud-2027-rebajas" in path:
        return ("ricarte" in text and "soto" in text
                and "2027" in numbers and {"189696", "166951"} <= numbers
                and ("aps" in text or "atencion primaria" in text))
    if "isapres-logran-detener-la-fuga" in path:
        return ("mayo" in text and "contrat" in text
                and {"17539", "17487", "52"} <= numbers)
    if "chomali-destaca-alza-de-47" in path:
        return "presupuesto" in text and {"2027", "47"} <= numbers
    return False


def _load_addendum():
    try:
        encoded = ADDENDUM_PATH.read_bytes()
        if hashlib.sha256(encoded).hexdigest() != ADDENDUM_SHA256:
            return None
        result = json.loads(encoded)
        policy = result["editorial_policy"]
        if (result["schema_version"] != 1
                or result["source_id"] != "pulso_latercera"
                or result["prior_review"]["ref"] != REVIEW_REF
                or result["prior_review"]["sha256"] != REVIEW_SHA256
                or result["decision"] != "release_hold_for_editorial_analysis"
                or policy["media_materiality_threshold"] != 72
                or policy["threshold_changed"] is not False
                or policy["publication_approved"] is not False
                or policy["analysis_release_only"] is not True
                or policy["required_evidence_maturity"] != "media_reported"):
            return None
        return result
    except (OSError, ValueError, TypeError, KeyError):
        return None


def verified_incremental_release(raw: RawItem) -> dict | None:
    """Return bound Oct5 analysis-release evidence without mutating any state.

    This is admission evidence for an existing pending/retry queue row, never
    permission to reopen a terminal row, alter attempts or approve publication.
    The caller must also enforce the current queue status.
    """
    meta = raw.metadata
    if not isinstance(meta, dict):
        return None
    assessment = meta.get("editorial_assessment", {})
    if (raw.source_slug != "pulso_latercera" or raw.source_type != "press_high_trust"
            or not isinstance(assessment, dict)
            or assessment.get("decision") in {"published", "rejected", "accepted", "approved"}
            or meta.get("queue_status") in {"published", "rejected", "archived"}
            or meta.get("primary_identity_verified") is not True
            or meta.get("publication_date_verified") is not True
            or meta.get("article_body_complete") is not True
            or meta.get("possible_publication_days")
            or meta.get("publisher_exception_reason") == "publisher_conflicting_publication_dates"):
        return None
    addendum = _load_addendum()
    if addendum is None or _load_review() is None:
        return None
    article = addendum["article"]
    prior = meta.get("incremental_review", {})
    if (raw.url != article["source_url"]
            or not _primary_evidence_matches(raw, article, addendum["review_date"])
            or meta.get("article_body_sha256") != article["body_sha256"]
            or meta.get("html_sha256") != article["html_sha256"]
            or len(meta["page_text"]) != article["body_characters"]
            or meta.get("publication_timestamp") != article["publication_timestamp"]
            or not isinstance(prior, dict)
            or prior.get("review_ref") != REVIEW_REF
            or prior.get("review_sha256") != REVIEW_SHA256
            or prior.get("decision") != "keep_hold"
            or prior.get("reason") != addendum["prior_review"]["reason"]
            or prior.get("publication_approved") is not False
            or prior.get("verified_publication_date") != article["publication_date"]
            or prior.get("verified_body_sha256") != article["body_sha256"]
            or prior.get("verified_html_sha256") != article["html_sha256"]
            or not all(quote in meta["page_text"] for quote in addendum["new_incremental_observations"])):
        return None
    evidence = {
        "review_ref": ADDENDUM_REF, "review_sha256": ADDENDUM_SHA256,
        "schema_version": addendum["schema_version"], "review_id": addendum["review_id"],
        "review_date": addendum["review_date"], "decision": addendum["decision"],
        "reason": addendum["reason"], "previous_hold": addendum["prior_review"]["reason"],
        "prior_review_ref": REVIEW_REF, "prior_review_sha256": REVIEW_SHA256,
        "publication_approved": False, "verified_publication_date": raw.event_date,
        "verified_html_sha256": meta["html_sha256"],
        "verified_body_sha256": meta["article_body_sha256"],
        "verified_captured_at": meta["captured_at"],
    }
    hold = meta.get("editorial_hold")
    applied = meta.get("incremental_review_addendum")
    if hold == addendum["prior_review"]["reason"]:
        if applied is not None:
            return None
    elif hold is None:
        if applied != evidence:
            return None
    else:
        return None
    return evidence


def _apply_verified_addendum(raw):
    evidence = verified_incremental_release(raw)
    if evidence is None or raw.metadata.get("incremental_review_addendum") == evidence:
        return False
    addendum = _load_addendum()
    if addendum is None:
        return False
    meta = raw.metadata
    meta["incremental_review_addendum"] = evidence
    meta["editorial_review_context"] = {
        "source_url": raw.url, "publication_date": raw.event_date,
        "event_status": addendum["event_status"],
        "incremental_observations": deepcopy(addendum["new_incremental_observations"]),
        "interpretation_constraints": deepcopy(addendum["interpretation_constraints"]),
        "compared_signal": deepcopy(meta.get("editorial_review_context", {}).get("compared_signal")),
        "prior_review_ref": REVIEW_REF, "addendum_review_ref": ADDENDUM_REF,
        "addendum_review_sha256": ADDENDUM_SHA256,
        "decision": addendum["decision"], "reason": addendum["reason"],
        "evidence_maturity": "media_reported", "publication_approved": False,
        "media_materiality_threshold": 72,
    }
    del meta["editorial_hold"]
    return True


def apply_incremental_review(raw: RawItem) -> bool:
    """Resolve only a matching legacy hold; return False without mutation otherwise.

    Primary URL-bound dates, full stored body/hash and capture provenance must
    match. Truncated or revised bodies that no longer contain the reviewed
    facts keep their hold. The caller still applies its unchanged editorial and
    publication gates, including related-event incremental value.
    """
    meta = raw.metadata
    if not isinstance(meta, dict):
        return False
    if _apply_verified_addendum(raw):
        return True
    assessment = meta.get("editorial_assessment", {})
    if (not isinstance(assessment, dict)
            or raw.source_slug != "pulso_latercera" or raw.source_type != "press_high_trust"
            or meta.get("editorial_hold") != LEGACY_HOLD
            or assessment.get("decision") in {
                "published", "rejected", "accepted", "approved"}
            or meta.get("queue_status") in {"published", "rejected", "archived"}):
        return False
    review = _load_review()
    if review is None:
        return False
    matches = [entry for entry in review["reviews"] if entry["source_url"] == raw.url]
    if len(matches) != 1:
        return False
    entry = matches[0]
    if not _primary_evidence_matches(raw, entry, review["review_date"]):
        return False
    comparison = entry["compared_signal"]
    equivalences = meta.get("event_equivalence_review", [])
    if (not isinstance(equivalences, list) or not equivalences
            or not all(isinstance(item, dict)
                       and item.get("source_url") == comparison["source_url"]
                       and item.get("publication_date") == comparison["publication_date"]
                       for item in equivalences)
            or not _body_matches_review(meta["page_text"], entry)):
        return False
    if (entry["publication_approved"] is not False
            or entry["decision"] not in {"keep_hold", "release_hold_for_editorial_analysis"}):
        return False

    context_keys = (
        "source_url", "publication_date", "reference_period", "event_status",
        "compared_signal", "relationship", "incremental_observations",
        "new_incremental_fields", "metric_comparison", "interpretation_constraints",
        "decision", "reason", "editorial_outcome",
    )
    meta["editorial_review_context"] = deepcopy({key: entry[key] for key in context_keys if key in entry})
    meta["editorial_review_context"].update(
        evidence_maturity="media_reported", publication_approved=False,
        media_materiality_threshold=72, limitations=deepcopy(review["limitations"]))
    meta["incremental_review"] = {
        "review_ref": REVIEW_REF, "review_sha256": REVIEW_SHA256,
        "schema_version": review["schema_version"], "review_date": review["review_date"],
        "reviewer": review["reviewer"], "decision": entry["decision"],
        "reason": entry["reason"], "previous_hold": LEGACY_HOLD,
        "publication_approved": False, "verified_publication_date": raw.event_date,
        "verified_html_sha256": meta["html_sha256"],
        "verified_body_sha256": meta["article_body_sha256"],
        "verified_captured_at": meta["captured_at"],
    }
    if entry["decision"] == "keep_hold":
        meta["editorial_hold"] = entry["reason"]
        meta["editorial_assessment"] = {"decision": "pending", "reason": entry["reason"]}
    else:
        del meta["editorial_hold"]
    return True
