import json
from pathlib import Path

from src.radar_salud.editorial_copy import apply_reviewed_copy, load_overrides, signal_fingerprint


def test_copy_overrides_are_audited_non_empty_and_apply_to_every_surface():
    audit = json.loads(Path("data/editorial_audit_2026_09_26.json").read_text())
    snapshot = json.loads(Path("web/data/radar_today.json").read_text())
    overrides = load_overrides()
    by_audit = {row["id"]: row for row in audit["items"]}
    by_signal = {row["source_url"]: row for row in snapshot["signals"]}
    assert len(overrides["items"]) == 11
    for override in overrides["items"]:
        reviewed = by_audit[override["source_url"]]
        assert override["proposed"] == reviewed["proposed"]
        rendered = by_signal[override["source_url"]]
        assert override["event_date"] == rendered["event_date"]
        assert override["signal_fingerprint_sha256"] == signal_fingerprint(rendered)
        for proposed_field, signal_field in {
            "title": "title", "summary": "card_what", "why": "card_why"
        }.items():
            value = override["proposed"].get(proposed_field)
            if value:
                assert rendered[signal_field] == value
        assert rendered["editorial_review_id"] == overrides["audit_id"]
        if override.get("legacy_title"):
            assert rendered["legacy_read_title"] == override["legacy_title"]


def test_unknown_urls_and_empty_proposals_never_mutate_copy():
    signal = {"source_url": "https://example.org/a", "event_date": "2026-09-26", "title": "Original", "what_happened": "Hecho"}
    overrides = {"audit_id": "x", "items": [{
        "source_url": "https://example.org/b", "event_date": "2026-09-26", "signal_fingerprint_sha256": signal_fingerprint(signal), "proposed": {"title": "Other"}
    }]}
    assert apply_reviewed_copy([signal], overrides) == [signal]


def test_reused_url_wrong_date_or_changed_body_never_receives_stale_copy():
    original = {"source_url": "https://example.org/a", "event_date": "2026-09-25", "title": "Original", "what_happened": "Hecho original"}
    override = {"source_url": original["source_url"], "event_date": original["event_date"],
                "signal_fingerprint_sha256": signal_fingerprint(original), "proposed": {"title": "Revisado"}}
    cfg = {"audit_id": "x", "items": [override]}
    changed_date = {**original, "event_date": "2026-09-26"}
    changed_body = {**original, "what_happened": "Hecho nuevo"}
    assert apply_reviewed_copy([changed_date], cfg) == [changed_date]
    assert apply_reviewed_copy([changed_body], cfg) == [changed_body]
    applied = apply_reviewed_copy([original], cfg)[0]
    assert applied["title"] == "Revisado"
    assert applied["source_title_full"] == "Original"


def test_legacy_read_title_does_not_replace_long_source_headline():
    signal = {
        "source_url": "https://example.org/a",
        "event_date": "2026-09-25",
        "title": "Titular anterior",
        "source_title_full": "Titular anterior con bajada íntegra de la fuente",
        "what_happened": "Hecho",
    }
    cfg = {"audit_id": "x", "items": [{
        "source_url": signal["source_url"],
        "event_date": signal["event_date"],
        "signal_fingerprint_sha256": signal_fingerprint(signal),
        "legacy_title": "Titular anterior",
        "proposed": {"title": "Titular revisado"},
    }]}
    applied = apply_reviewed_copy([signal], cfg)[0]
    assert applied["source_title_full"] == signal["source_title_full"]
    assert applied["legacy_read_title"] == "Titular anterior"
