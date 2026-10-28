"""Paid-output continuity for premium La Tercera sections (Dirección 28-oct-2026).

Premium sections (Pulso, La Tercera PM, LT Board) are now analysed from title +
public lead only. Earlier paid answers were bound to the full-body hashes, so the
pinned paid-revalidation paths can no longer verify them against the teaser
request. This module decides, deterministically and at most once per item:

1. ``teaser``: a paid answer already bound to this exact teaser request is reused.
2. ``reuse_full``: an earlier full-body paid answer stays valid with no new call
   when (a) the stored body receipt matches the body hash it was bound to at
   capture, (b) its validation was terminal (ready/rejected), and (c) the text it
   would display passes the public-text check against title + lead.
3. ``reanalyse``: otherwise ONE teaser-based analysis, only with AI budget; the
   attempt is recorded before the call, so the same item is never paid twice.
4. ``exhausted``: a recorded attempt exists and no reusable answer: terminal.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .source_rights import public_text_supported, redacted_body_verified

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
    """(paid answer, reason): the earlier full-body answer if it may stand without a new call."""
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
    validation = metadata.get("pulso_editorial_proof_validation")
    if (not isinstance(validation, dict) or validation.get("decision") not in ("ready", "rejected")
            or validation.get("model_output_sha256") != _digest(model)):
        return None, "prior_validation_not_terminal"
    for field in ("what_happened", "why_it_matters"):
        ok, missing = public_text_supported(model.get(field), public_text)
        if not ok:
            return None, f"displayed_{field}_not_supported_by_public_text"
    return model, "reused"


def decide(raw, prior: dict, *, text: str, request_input: str) -> dict:
    """Return {"kind": teaser|reuse_full|reanalyse|exhausted, ...}; never calls the model."""
    md = raw.metadata
    model = teaser_bound_output(md, text, request_input, raw.source_name)
    if model is not None:
        return {"kind": "teaser", "ai": model}
    public = f"{raw.title} {md.get('public_teaser') or ''}"
    model, why = full_body_output(md, prior, public)
    if model is not None:
        return {"kind": "reuse_full", "ai": model}
    if md.get(STATE):
        return {"kind": "exhausted", "reason": "paywalled_teaser_reanalysis_exhausted", "detail": why}
    return {"kind": "reanalyse", "detail": why}


def record_reuse(raw, prior: dict) -> dict:
    """Restore the paid request's own binding and record why it stands without a new call."""
    md = raw.metadata
    for key, value in prior.items():
        md[key] = value
    md[REUSE] = {"at": datetime.now(timezone.utc).isoformat(), "basis": "body_receipt_matches_capture_hash",
                 "article_body_sha256": md.get("article_body_sha256"),
                 "model_output_sha256": _digest(md.get("analysis_model_output")),
                 "public_text_check": "passed", "new_model_request": False}
    return md[REUSE]


def mark_reanalysis(raw, detail: str, text: str) -> None:
    """Record the single teaser re-analysis BEFORE the call (crash-safe: never paid twice)."""
    raw.metadata[STATE] = {"requested_at": datetime.now(timezone.utc).isoformat(), "reason": detail,
                           "teaser_sha256": _sha(text), "attempts": 1, "max_attempts": 1}


def capacity_available() -> bool:
    from .ai_budget import has_capacity
    from .llm_analysis import _client
    return bool(_client()) and has_capacity("fast")
