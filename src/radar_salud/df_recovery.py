"""Conservative DF queue recovery. Retain the original capture and terminal reason."""
from copy import deepcopy
from dataclasses import asdict

from .df_article import article_url


def _remember(item, now, action):
    observation = {k: deepcopy(v) for k, v in item.items() if k != "recovery_observations"}
    item.setdefault("recovery_observations", []).append({"at": now.isoformat(), "action": action, "before": observation})


def reconcile_existing(queue, raw, now, last_discovered_at, published_urls=()):
    """Return True if this URL already has a queue record, including terminal rows.

    A seen hash cannot suppress enrichment of existing rows. Only legacy undated
    processor_rejected rows are reopened, after verified dated article evidence.
    Explicit editorial decisions stay terminal. URL dedupe handles changed decks.
    """
    from .pending_queue import lane, beyond_backfill_horizon
    url = article_url(raw.url)
    matches = [(key, item) for key, item in queue.items.items()
               if item.get("source") == "diario_financiero" and article_url(item["raw"]["url"]) == url]
    if not matches:
        return False
    published = url in {article_url(u) for u in published_urls}
    rank = {"published": 0, "processing": 1, "pending": 2, "retry": 3, "rejected": 4, "archived": 5, "superseded": 6}
    matches.sort(key=lambda pair: (rank.get(pair[1]["status"], 7), pair[1]["detected_at"]))
    primary_key, item = matches[0]
    verified = (raw.event_date and raw.metadata.get("publication_date_source")
                and (not raw.metadata.get("publication_date_conflict") or raw.metadata.get("publication_date_conflict_resolution"))
                and not raw.metadata.get("fetch_error") and len(raw.metadata.get("page_text", "")) >= 160)
    legacy_reject = (item["status"] == "rejected" and item.get("reason") == "processor_rejected"
                     and not item["raw"].get("event_date"))
    active = item["status"] in ("pending", "retry", "processing")
    if published and item["status"] not in ("published", "superseded"):
        _remember(item, now, "already_published_in_history")
        item.update(status="superseded", reason="already_published_in_history", updated_at=now.isoformat(), retry_at=None)
    elif verified and (active or legacy_reject):
        # Legacy rows did not retain their discovery watermark. Use the original
        # detection day conservatively, never today's watermark to rewrite history.
        basis = item.get("classification_watermark")
        if not basis and last_discovered_at:
            basis = min(last_discovered_at, item["detected_at"])
        new_lane = lane(raw, now, basis)
        original = item["raw"]
        enriched = asdict(raw)
        # Keep the original title/key identity even if a listing deck changed.
        enriched["title"] = original["title"]
        enriched["metadata"] = {**original.get("metadata", {}), **enriched["metadata"]}
        enriched["metadata"].pop("fetch_error", None)
        capture_repaired=(item["status"]=="retry" and item.get("reason") in
                          ("df_detail_fetch_failed","df_missing_publication_date","df_publication_date_conflict","df_insufficient_article_evidence")
                          and original.get("event_date")!=raw.event_date)
        new_status = "pending" if legacy_reject or capture_repaired else item["status"]
        reason = None if legacy_reject or capture_repaired else item.get("reason")
        if beyond_backfill_horizon(raw, now):
            new_status, reason = "archived", "outside_90_day_backfill"
        if original != enriched or item["lane"] != new_lane or item["status"] != new_status:
            _remember(item, now, "verified_publisher_evidence_rehydration")
            item.update(raw=enriched, lane=new_lane, status=new_status, reason=reason, updated_at=now.isoformat(),
                        classification_watermark=basis,
                        classification_basis="stored_watermark" if item.get("classification_watermark") else "original_detection_day_conservative")
            if legacy_reject or capture_repaired:
                item["retry_at"] = None
    # Collapse changed-title duplicates only after verified evidence or history.
    if verified or published:
        for key, duplicate in matches[1:]:
            if duplicate["status"] in ("pending", "retry", "processing") or (
                duplicate["status"] == "rejected" and duplicate.get("reason") == "processor_rejected"
                and not duplicate["raw"].get("event_date")):
                _remember(duplicate, now, "duplicate_df_url")
                duplicate.update(status="superseded", reason="duplicate_df_url", duplicate_of=primary_key,
                                 updated_at=now.isoformat(), retry_at=None)
    return True
