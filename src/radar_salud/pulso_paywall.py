"""Paid-output continuity for premium La Tercera sections (Dirección 28-oct-2026).

Premium sections (Pulso, La Tercera PM, LT Board) are now analysed from title +
public lead only. Earlier paid answers were bound to the full-body hashes, so the
pinned paid-revalidation paths can no longer verify them against the teaser
request. This module decides, deterministically and at most once per item:

1. ``teaser``: a paid answer already bound to this exact teaser request is reused.
2. ``reuse_full``: an earlier full-body paid answer stays valid with no new call
   when (a) the stored body receipt matches the body hash it was bound to at
   capture, (b) its validation was terminal (ready/rejected) and bound to the
   paid output's digest -- for an output whose body quotes became receipts, the
   recorded pre-redaction digest (``analysis_model_output_rights``) -- and (c) the
   text it would display passes the public-text check against title + lead.
3. ``reanalyse``: otherwise ONE teaser-based analysis, only with AI budget; the
   attempt is recorded before the call, so the same item is never paid twice.
   A call that failed before anything was billed (no response, no tokens, and a
   pre-generation error or no request sent) allows one bounded retry later.
4. ``exhausted``: a billed (or unknown) attempt exists and no reusable answer: terminal.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .source_rights import (public_date_text, public_text_supported, redacted_body_verified,
                            verified_model_output_digest)

STATE = "paywall_teaser_reanalysis"
REUSE = "paywall_paid_output_reuse"
BINDING_FIELDS = ("analysis_base_article_body_sha256", "analysis_base_article_body_characters",
                  "analysis_input_format", "analysis_input_body_sha256", "analysis_input_characters",
                  "analysis_input_complete", "analysis_request_input_sha256", "analysis_request_input_characters")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest(value) -> str:
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def prior_binding(metadata: dict) -> dict:
    return {key: metadata.get(key) for key in BINDING_FIELDS}


def _meta(model):
    meta = model.get("_pulso_analysis_meta") if isinstance(model, dict) else None
    return meta if isinstance(meta, dict) and isinstance(meta.get("response_id"), str) and meta["response_id"].strip() else None


def teaser_bound_output(metadata: dict, text: str, request_input: str, source_name: str):
    model = metadata.get("analysis_model_output")
    meta = _meta(model)
    if (meta and meta.get("analysis_text_sha256") == _sha(text)
            and meta.get("request_input_sha256") == _sha(request_input)
            and meta.get("source_name") == source_name):
        return model
    return None


def full_body_output(metadata: dict, prior: dict, public_text: str):
    """(paid answer, reason): the earlier full-body answer if it may stand without a new call.

    The reuse key is the digest of the paid output as it was validated. A paid
    output whose verbatim body quotes were later replaced by receipts (rights
    migration 28-oct) is identified by its recorded ``original_model_output_sha256``,
    accepted only when the stored output is exactly the recorded redacted form.
    """
    model = metadata.get("analysis_model_output")
    meta = _meta(model)
    if meta is None:
        return None, "no_paid_output"
    if not redacted_body_verified(metadata):
        return None, "body_receipt_unverified"
    if (prior.get("analysis_base_article_body_sha256") != metadata.get("article_body_sha256")
            or meta.get("analysis_text_sha256") != prior.get("analysis_input_body_sha256")
            or meta.get("request_input_sha256") != prior.get("analysis_request_input_sha256")):
        return None, "paid_output_not_bound_to_body_receipt"
    key, basis = verified_model_output_digest(metadata)
    if key is None:
        return None, basis
    validation = metadata.get("pulso_editorial_proof_validation")
    if not isinstance(validation, dict) or validation.get("model_output_sha256") != key:
        return None, "prior_validation_not_bound_to_paid_output"
    if validation.get("decision") not in ("ready", "rejected"):
        # Deferred/pending before redaction: the validator would need the locked
        # body to re-check its quotes, which is no longer stored. Not reusable.
        return None, "prior_validation_not_terminal"
    for field in ("what_happened", "why_it_matters"):
        ok, missing = public_text_supported(model.get(field), public_text)
        if not ok:
            return None, f"displayed_{field}_not_supported_by_public_text"
    return model, "reused"


def _attempts(state: dict) -> tuple[int, int]:
    """(billed-or-unknown attempts, unbilled failures) recorded for the teaser re-analysis."""
    history = state.get("history")
    if not isinstance(history, list):  # first schema: one attempt recorded before the call
        return int(state.get("attempts") or 1), 0
    billed = sum(1 for h in history if h.get("outcome") != "failed_unbilled")
    unbilled = sum(1 for h in history if h.get("outcome") == "failed_unbilled")
    return billed, unbilled


def public_text_for(title, metadata: dict, event_date) -> str:
    """Everything a reader sees without an account: title, public lead and publication date."""
    return f"{title} {metadata.get('public_teaser') or ''} {public_date_text(event_date)}"


def decide(raw, prior: dict, *, text: str, request_input: str) -> dict:
    """Return {"kind": teaser|reuse_full|reanalyse|exhausted, ...}; never calls the model."""
    md = raw.metadata
    model = teaser_bound_output(md, text, request_input, raw.source_name)
    if model is not None:
        return {"kind": "teaser", "ai": model}
    public = public_text_for(raw.title, md, raw.event_date)
    model, why = full_body_output(md, prior, public)
    if model is not None:
        return {"kind": "reuse_full", "ai": model}
    state = md.get(STATE)
    if state:
        billed, unbilled = _attempts(state)
        if billed == 0 and unbilled <= MAX_UNBILLED_RETRIES:
            # Every earlier attempt failed before anything was billed: one bounded retry.
            return {"kind": "reanalyse", "detail": why, "retry": True}
        return {"kind": "exhausted", "reason": "paywalled_teaser_reanalysis_exhausted", "detail": why}
    return {"kind": "reanalyse", "detail": why}


def record_reuse(raw, prior: dict) -> dict:
    """Restore the paid request's own binding and record why it stands without a new call."""
    md = raw.metadata
    for key, value in prior.items():
        md[key] = value
    key, basis = verified_model_output_digest(md)
    md[REUSE] = {"at": datetime.now(timezone.utc).isoformat(), "basis": "body_receipt_matches_capture_hash",
                 "article_body_sha256": md.get("article_body_sha256"),
                 "model_output_sha256": key, "model_output_basis": basis,
                 "stored_model_output_sha256": _digest(md.get("analysis_model_output")),
                 "public_text_check": "passed", "new_model_request": False}
    return md[REUSE]


MAX_UNBILLED_RETRIES = 1
# Failures raised before the provider produced (and billed) a response.
UNBILLED_ERRORS = {"APIConnectionError", "RateLimitError", "InternalServerError", "AuthenticationError",
                   "PermissionDeniedError", "NotFoundError", "BadRequestError", "UnprocessableEntityError",
                   "ConflictError"}


def mark_reanalysis(raw, detail: str, text: str) -> None:
    """Record the teaser re-analysis BEFORE the call (crash-safe: an attempt with no
    recorded outcome counts as paid, so the same item is never paid twice)."""
    state = raw.metadata.get(STATE)
    history = list(state.get("history") or []) if isinstance(state, dict) else []
    history.append({"requested_at": datetime.now(timezone.utc).isoformat(), "outcome": "in_flight"})
    raw.metadata[STATE] = {"requested_at": history[0]["requested_at"], "reason": detail,
                           "teaser_sha256": _sha(text), "attempts": len(history), "max_attempts": 1,
                           "max_unbilled_retries": MAX_UNBILLED_RETRIES, "history": history}


def record_outcome(raw, ai, call: dict | None) -> str:
    """Close the in-flight attempt: ``paid_output``, ``failed_unbilled`` or ``failed_possibly_billed``.

    ``call`` is ``llm_analysis.last_call()``. A failure counts as unbilled only when
    no response (hence no token usage) was recorded and either no request was sent
    or the error type is raised before generation; anything else (timeouts,
    invalid JSON after a response, unknown errors) counts as billed.
    """
    state = raw.metadata.get(STATE) or {}
    history = state.get("history") or []
    if not history:
        return "untracked"
    call = call or {}
    if ai:
        outcome = "paid_output"
    elif not call.get("response") and not call.get("input_tokens") and not call.get("output_tokens") and (
            call.get("sent") is False or call.get("error_type") in UNBILLED_ERRORS):
        outcome = "failed_unbilled"
    else:
        outcome = "failed_possibly_billed"
    history[-1].update(outcome=outcome, error_type=call.get("error_type"),
                       response_id=call.get("response_id"), input_tokens=call.get("input_tokens"),
                       output_tokens=call.get("output_tokens"))
    return outcome


def capacity_available() -> bool:
    from .ai_budget import has_capacity
    from .llm_analysis import _client
    return bool(_client()) and has_capacity("fast")
