"""Explicit DF format dispositions, outside automatic processing retries.

A deferred format is neither an editorial rejection nor a seen acknowledgement.
Discovery may resume it when a verified primary transcript/body becomes available.
"""
from .df_recovery import _remember


FORMAT_REASONS = {"df_image_only_requires_ocr", "df_media_transcript_unavailable"}


def defer_format(item, reason, now):
    if reason not in FORMAT_REASONS:
        return False
    resolution = {
        "state": "DEFERRED_MULTIMEDIA",
        "reason": reason,
        "original_sha256": item["raw"].get("metadata", {}).get("original_sha256"),
        "next_action": ("Obtain and verify text from primary publisher images; reassess at unchanged gate"
                        if reason == "df_image_only_requires_ocr" else
                        "Obtain official transcript or associated primary text; reassess at unchanged gate"),
    }
    if item.get("status") != "deferred" or item.get("df_resolution") != resolution:
        _remember(item, now, "explicit_nontext_format_disposition")
        item.update(status="deferred", reason=reason, retry_at=None,
                    updated_at=now.isoformat(), df_resolution=resolution)
    return True
