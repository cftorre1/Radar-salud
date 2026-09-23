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

def lane(raw, now):
    try:
        published = datetime.fromisoformat(raw.event_date[:10]).date()
        return "LIVE" if 0 <= (now.date() - published).days <= 7 else "BACKFILL"
    except (TypeError, ValueError):
        return "BACKFILL"

class PendingQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.items = json.loads(self.path.read_text()) if self.path.exists() else {}
        if not isinstance(self.items, dict):
            raise ValueError("Invalid pending queue; refusing to discard state")

    def save(self):
        atomic_json(self.path, self.items)

    def discover(self, source, items, seen=(), now=None):
        now = now or now_utc()
        added = 0
        for raw in items:
            key = fingerprint(raw)
            if key in self.items or key in seen:
                continue
            self.items[key] = dict(raw=asdict(raw), source=source, lane=lane(raw, now),
                status="pending", detected_at=now.isoformat(), attempts=0, reason=None)
            added += 1
        self.save()
        return added

    def ready(self, now=None):
        now = now or now_utc()
        items = [(key, item) for key, item in self.items.items()
                 if item["status"] in ("pending", "retry", "processing")
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
