"""Durable global queue. Discovery never consumes the AI budget.

Single writer enforced by workflow concurrency. Atomic replace protects local
checkpoints; a processing item is retryable after interruption.
"""
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

def now_utc():
    return datetime.now(timezone.utc)

def fingerprint(raw):
    return hashlib.sha256(f"{raw.source_slug}|{raw.url}|{raw.title}".encode()).hexdigest()

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)

def lane(raw, now, last_discovered_at=None):
    # Newly integrated sources remain historical until their required
    # 90-day value audit is explicitly completed and reviewed.
    if raw.metadata.get("source_quality_gate") not in (None, "passed"):
        return "BACKFILL"
    if not last_discovered_at:
        return "BACKFILL"
    try:
        published = datetime.fromisoformat(raw.event_date[:10]).date()
        watermark = datetime.fromisoformat(last_discovered_at.replace("Z", "+00:00")).date()
        return "LIVE" if watermark <= published <= now.date() and (now.date() - published).days <= 7 else "BACKFILL"
    except (TypeError, ValueError):
        return "BACKFILL"

def beyond_backfill_horizon(raw, now, days=90):
    try:
        published = datetime.fromisoformat(raw.event_date[:10]).date()
        return (now.date() - published).days > days
    except (TypeError, ValueError):
        return False

class PendingQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.items = json.loads(self.path.read_text()) if self.path.exists() else {}
        if not isinstance(self.items, dict):
            raise ValueError("Invalid pending queue; refusing to discard state")

    def save(self):
        atomic_json(self.path, self.items)

    def discover(self, source, items, seen=(), now=None, last_discovered_at=None):
        now = now or now_utc()
        added = 0
        # Pulso article titles can change between listing, byline and metadata.
        # A single canonical news URL must retain its original durable identity.
        pulso_urls = {}
        if source == "pulso_latercera":
            from .pulso_source import (article_url, complete_article_body,
                                       verified_publication_date_conflict, verified_sponsored_content,
                                       verified_video_without_text)
            pulso_urls = {article_url(item["raw"]["url"]): key for key,item in self.items.items()
                          if item["source"] == source and article_url(item["raw"]["url"])}
        for raw in items:
            key = fingerprint(raw)
            if source == "pulso_latercera":
                url = article_url(raw.url)
                previous = self.items.get(pulso_urls.get(url)) if url else None
                if previous is not None:
                    metadata = raw.metadata
                    primary_bound = bool(url and metadata.get("canonical_url") == url)
                    publisher_exception = primary_bound and (
                        (verified_publication_date_conflict(metadata) and raw.event_date is None)
                        or ((verified_video_without_text(metadata) or verified_sponsored_content(metadata))
                            and raw.event_date == metadata.get("publication_date")))
                    factual_verified = (metadata.get("article_verified") is True and primary_bound
                                        and metadata.get("primary_identity_verified") is True
                                        and metadata.get("publication_date_verified") is True
                                        and raw.event_date == metadata.get("publication_date")
                                        and complete_article_body(metadata))
                    if previous["status"] in ("pending", "retry", "processing") and (factual_verified or publisher_exception):
                        old = previous["raw"]
                        old_meta = old.get("metadata", {})
                        proof_fields = ("article_verified", "primary_identity_verified", "publication_date_verified",
                                        "canonical_url", "source_quality_gate", "article_body_complete",
                                        "article_body_sha256", "article_body_characters", "publisher_taxonomy",
                                        "publisher_content_classification", "publisher_exception_reason",
                                        "source_content_unavailable_reason", "video_identity_verified", "video_evidence",
                                        "publication_date_source", "publication_timestamp", "publication_evidence",
                                        "publisher_date_convention", "visible_publication_date", "possible_publication_days",
                                        "html_sha256", "publisher_lastmod")
                        changed = (old.get("event_date") != raw.event_date
                                   or old.get("title") != raw.title or old_meta.get("page_text") != metadata.get("page_text")
                                   or any(old_meta.get(field) != metadata.get(field) for field in proof_fields))
                        if changed:
                            revisions = old_meta.get("evidence_revisions", []) + [dict(
                                at=now.isoformat(), previous_publication_date=old.get("event_date"),
                                verified_publication_date=raw.event_date, previous_title=old.get("title"),
                                verified_title=raw.title, previous_capture_method=old_meta.get("capture_method"),
                                reason="verified_publisher_exception_rediscovery" if publisher_exception else "verified_article_rediscovery",
                                previous_publisher_exception_reason=old_meta.get("publisher_exception_reason"),
                                verified_publisher_exception_reason=metadata.get("publisher_exception_reason"),
                                lane_preserved=previous["lane"])]
                            previous["raw"] = asdict(raw)
                            for field in ("editorial_hold", "event_equivalence_review"):
                                if field in old_meta and field not in previous["raw"]["metadata"]:
                                    previous["raw"]["metadata"][field] = old_meta[field]
                            previous["raw"]["metadata"]["evidence_revisions"] = revisions
                            previous["raw"]["metadata"]["queue_identity_fingerprint"] = pulso_urls[url]
                    continue
            if key in self.items or key in seen:
                continue
            item_lane = lane(raw, now, last_discovered_at)
            archived = item_lane == "BACKFILL" and beyond_backfill_horizon(raw, now)
            self.items[key] = dict(raw=asdict(raw), source=source, lane=item_lane,
                status="archived" if archived else "pending", detected_at=now.isoformat(),
                attempts=0, reason="outside_90_day_backfill" if archived else None)
            added += 1
            if source == "pulso_latercera" and url:
                pulso_urls[url] = key
        self.save()
        return added

    def enforce_backfill_horizon(self, now=None, sources=None):
        now = now or now_utc()
        changed = 0
        for item in self.items.values():
            if sources is not None and item["source"] not in sources:
                continue
            if item.get("lane") == "BACKFILL" and item.get("status") in ("pending", "retry", "processing"):
                raw = item.get("raw", {})
                try:
                    published = datetime.fromisoformat(str(raw.get("event_date"))[:10]).date()
                except (TypeError, ValueError):
                    continue
                if (now.date() - published).days > 90:
                    item.update(status="archived", reason="outside_90_day_backfill")
                    changed += 1
        if changed:self.save()
        return changed

    def ready(self, now=None):
        now = now or now_utc()
        items = [(key, item) for key, item in self.items.items()
                 if item["status"] in ("pending", "retry", "processing")
                 and not (item.get("lane") == "BACKFILL" and item.get("raw", {}).get("event_date")
                          and str(item["raw"]["event_date"])[:10] > now.date().isoformat())
                 and (not item.get("retry_at") or item["retry_at"] <= now.isoformat())]
        return sorted(items, key=lambda pair: (
            pair[1]["lane"] != "LIVE", pair[1]["attempts"], pair[1]["detected_at"]))

    def start(self, key):
        self.items[key].update(status="processing", attempts=self.items[key]["attempts"] + 1)
        self.save()

    def finish(self, key, status, reason=None, now=None):
        item = self.items[key]
        item.update(status=status, reason=reason, updated_at=(now or now_utc()).isoformat())
        item["retry_at"] = ((now or now_utc()) + timedelta(hours=min(24, 2 ** min(item["attempts"], 5)))).isoformat() if status == "retry" else None
        self.save()

    def counts(self, source=None):
        items = [x for x in self.items.values() if source is None or x["source"] == source]
        return {"live_pending": sum(x["lane"] == "LIVE" and x["status"] in ("pending", "retry", "processing") for x in items),
                "backfill_pending": sum(x["lane"] == "BACKFILL" and x["status"] in ("pending", "retry", "processing") for x in items),
                "rejected": sum(x["status"] == "rejected" for x in items),
                "published": sum(x["status"] == "published" for x in items)}
