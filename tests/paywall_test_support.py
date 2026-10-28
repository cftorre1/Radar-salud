"""Replay expectations for premium La Tercera pieces under the rights policy (Dirección 28-oct-2026).

Pinned paid-revalidation fixtures predate the policy. For an OPEN section their
exact historical expectations still hold. For a PREMIUM section (Pulso, Pulso PM,
La Tercera PM, LT Board...) the processor keeps only title + public lead from its
first line: the locked body never reaches a model or a validator, and the pinned
full-body revalidation paths are not entered. What must still hold is checked here:
no model call without AI budget, no body in any request, the paid answer kept
unchanged, and a pulso_paywall outcome (budget deferral or a public-text reject).
"""
from __future__ import annotations

from copy import deepcopy

from radar_salud.processing import DeferredProcessing
from radar_salud.source_rights import paywall_policy

PREMIUM_OUTCOMES = {
    "pulso_paywalled_reanalysis_budget_deferred",  # needs its single teaser analysis; no budget in tests
    "media_materiality_prefilter",                # title + lead alone are not material
    "paywalled_without_public_teaser",            # no public lead: title only, terminal
    # A legacy duplicate hold is released only by checking reviewed facts against the
    # body; without the body (and never feeding body-derived review context to a model)
    # the hold stays.
    "Pulso pending incremental-value review",
}


def premium_under_path_scope(url: str) -> bool:
    """Premium by the 1.2.0 path/section rule (the scope the pinned replays run under; see conftest).

    For module-level selections computed at import, before the per-test policy fixture applies.
    """
    from urllib.parse import urlsplit
    from radar_salud.source_rights import load_policy
    path = urlsplit(url).path
    for rule in load_policy()["sources"]:
        if rule.get("metered_sections_paywalled") and urlsplit(url).hostname in rule["hosts"]:
            return any(path.startswith(p) for p in rule.get("path_prefixes", []))
    return paywall_policy(url, None) is not None


def is_premium(raw) -> bool:
    return paywall_policy(raw.url, raw.metadata) is not None


def assert_premium_replay(process, raw, calls=None):
    """Run ``process(raw, {})`` for a premium piece and check the policy outcome; returns it."""
    before_output = deepcopy(raw.metadata.get("analysis_model_output"))
    before_calls = len(calls) if calls is not None else 0
    try:
        row = process(raw, {})
        assert row is None, "a premium replay cannot publish from a body-bound paid answer"
        outcome = raw.metadata.get("rejection_reason")
    except DeferredProcessing as exc:
        outcome = str(exc)
    assert outcome in PREMIUM_OUTCOMES, outcome
    assert calls is None or len(calls) == before_calls, "no model request without AI budget"
    assert raw.metadata.get("analysis_model_output") == before_output, "the paid answer is preserved"
    assert raw.metadata["paywalled"] is True
    assert raw.metadata["page_text"] == raw.metadata["public_teaser"] == raw.raw_text
    return outcome
