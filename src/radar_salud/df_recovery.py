"""Conservative DF queue recovery. Retain the original capture and terminal reason."""
from copy import deepcopy
from dataclasses import asdict

from .df_article import article_url


def published_history_urls(history):
    """A retained but withdrawn capture is evidence, not a published verdict."""
    return [row['source_url'] for row in history if row.get('source_url') and not (
        row.get('df_body_reaudit_observations') and row.get('editorial_decision')=='reject')]


def resume_withdrawn_reassessments(queue, history, now):
    """Recover exact old acknowledgements that mistakenly treated withdrawn history as published."""
    withdrawn={article_url(row['source_url']) for row in history if row.get('df_body_reaudit_status')=='pending'
               and row.get('df_body_reaudit_reason')=='df_primary_body_reassessment_required'}
    changed=[]
    for key,item in queue.items.items():
        if (item.get('source')=='diario_financiero' and item['status']=='superseded'
                and item.get('reason')=='already_published_in_history'
                and item['raw'].get('metadata',{}).get('df_body_reaudit_version')==1
                and article_url(item['raw']['url']) in withdrawn):
            _remember(item,now,'withdrawn_history_is_not_published')
            item.update(status='pending',reason='df_primary_body_reassessment_required',retry_at=None,updated_at=now.isoformat())
            changed.append(key)
    if changed:queue.save()
    return changed


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
    rank = {"published": 0, "processing": 1, "pending": 2, "retry": 3, "deferred": 4, "rejected": 5, "archived": 6, "superseded": 7}
    matches.sort(key=lambda pair: (rank.get(pair[1]["status"], 7), pair[1]["detected_at"]))
    primary_key, item = matches[0]
    dated = (raw.event_date and raw.metadata.get("publication_date_source")
                and (not raw.metadata.get("publication_date_conflict") or raw.metadata.get("publication_date_conflict_resolution"))
                and not raw.metadata.get("fetch_error"))
    verified=dated and len(raw.metadata.get('page_text',''))>=160
    legacy_reject = (item["status"] == "rejected" and item.get("reason") == "processor_rejected"
                     and not item["raw"].get("event_date"))
    resume_format = item["status"] == "deferred" and verified
    active = item["status"] in ("pending", "retry", "processing") or resume_format
    if published and item["status"] not in ("published", "superseded"):
        _remember(item, now, "already_published_in_history")
        item.update(status="superseded", reason="already_published_in_history", updated_at=now.isoformat(), retry_at=None)
    elif (dated and active) or (verified and legacy_reject):
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
        capture_repaired=(verified and item["status"]=="retry" and item.get("reason") in
                          ("df_detail_fetch_failed","df_missing_publication_date","df_publication_date_conflict","df_insufficient_article_evidence")
                          and (original.get("event_date")!=raw.event_date
                               or original.get('metadata',{}).get('fetch_error')
                               or len(original.get('metadata',{}).get('page_text',''))<160))
        new_status = "pending" if legacy_reject or capture_repaired or resume_format else item["status"]
        reason = None if legacy_reject or capture_repaired or resume_format else item.get("reason")
        if beyond_backfill_horizon(raw, now):
            new_status, reason = "archived", "outside_90_day_backfill"
        if original != enriched or item["lane"] != new_lane or item["status"] != new_status:
            _remember(item, now, "verified_publisher_evidence_rehydration")
            item.update(raw=enriched, lane=new_lane, status=new_status, reason=reason, updated_at=now.isoformat(),
                        classification_watermark=basis,
                        classification_basis="stored_watermark" if item.get("classification_watermark") else "original_detection_day_conservative")
            if resume_format:
                item['df_resolution'] = {**item.get('df_resolution', {}), 'state': 'RESUMED_VERIFIED_TEXT'}
            if legacy_reject or capture_repaired or resume_format:
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


def repair_contaminated_evidence(queue, originals, history, now):
    """One-time, traced re-audit of decisions made with the old broad body parser.

    Original assessments remain in recovery_observations and history review
    snapshots. A score from another story is not a legitimate terminal verdict.
    Hide affected publications until the real processor evaluates primary text.
    """
    from .df_media_gate import exclusion, material
    from .public_source_pipeline import _health_relevance
    from .pending_queue import beyond_backfill_horizon
    by_url = {article_url(raw.url): raw for raw in originals}
    decisions = []
    for key, item in queue.items.items():
        if item.get("source") != "diario_financiero" or item["status"] == "superseded":
            continue
        raw = by_url.get(article_url(item["raw"]["url"]))
        if not raw or raw.metadata.get("fetch_error"):
            continue
        old = item["raw"].get("metadata", {})
        affected = old.get("article_content_source") == "visible_article" or (
            item["status"] == "rejected" and item.get("reason") == "processor_rejected" and not item["raw"].get("event_date"))
        if not affected or old.get("df_body_reaudit_version"):
            continue
        _remember(item, now, "primary_body_capture_defect_reaudit")
        enriched = asdict(raw)
        enriched["title"] = item["raw"]["title"]
        enriched["metadata"]["df_body_reaudit_version"] = 1
        body = raw.metadata.get("page_text", "")
        title = raw.metadata.get("article_title") or raw.title
        reason = exclusion(raw)
        if not reason and len(body) >= 160 and not _health_relevance(title, body):
            reason = "df_unrelated_to_health"
        if not reason and len(body) >= 160 and not material(title, body):
            reason = "media_no_material_event"
        if reason:
            status = "rejected"
            enriched["metadata"]["rejection_reason"] = reason
        elif beyond_backfill_horizon(raw, now):
            status, reason = "archived", "outside_90_day_backfill"
        else:
            status, reason = "pending", "df_primary_body_reassessment_required"
        previous_status = item["status"]
        item.update(raw=enriched, status=status, reason=reason, retry_at=None, updated_at=now.isoformat())
        for row in history:
            if article_url(row.get("source_url", "")) != article_url(raw.url):
                continue
            if previous_status == "published":
                snapshot = deepcopy(row)
                row.setdefault("df_body_reaudit_observations", []).append({"at": now.isoformat(), "before": snapshot})
                row.update(editorial_decision="reject", feed_visibility=False,
                           df_body_reaudit_reason=reason, df_body_reaudit_status=status)
        decisions.append({"fingerprint": key, "url": raw.url, "previous_status": previous_status,
                          "status": status, "reason": reason, "primary_body_characters": len(body),
                          "original_sha256": raw.metadata.get("original_sha256")})
    queue.save()
    return decisions
