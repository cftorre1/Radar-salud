"""Publisher page meta descriptions as summary input for WHO and EMA (Dirección 30-oct-2026).

WHO's daily items come from the metadata crawl and carry no description, so Alicanto's Spanish summary could only be
written from the title. For items without a feed description, the item page's OWN declared description
(``<meta name="description">`` or ``<meta property="og:description">``) is read through the existing capture path
(``CaptureClient``: robots.txt fail-closed, cooldowns, live budget) and kept as ``description`` with
``description_source = "publisher_page_meta_description"``. Rules (``config/global_discovery.json``
``daily_feed.page_meta_description``):

* host allowlist: who.int and ema.europa.eu only (config may narrow it, never widen it: ``ALLOWED_DOMAINS``);
* robots.txt checked before the page request; a denial records the URL and fetches nothing;
* size cap (``max_bytes``) and timeout (``timeout_seconds``) per page; at most ``max_new_fetches_per_run`` page
  requests per run (default 30); results (and failures, retried after ``retry_failed_after_days``) cached by URL in
  ``data/global_intelligence/page_descriptions.json``;
* only the meta tag attribute text is used: the parser never reads text nodes, so the article body is never stored;
  capped at 600 characters.

The description feeds the existing summary path (``global_translation``: budget, two-layer verification, run cap).
It is summary input only: the public feed never shows it verbatim (WHO is CC BY-NC-SA; the feed contract keeps
publisher text to the feed's own <= 300-character summary), see ``global_daily_feed.export``.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

DESCRIPTION_SOURCE = "publisher_page_meta_description"
# Hard ceiling: config can only narrow these (Dirección 30-oct: who.int, ema.europa.eu).
ALLOWED_DOMAINS = ("who.int", "ema.europa.eu")
DEFAULT_SOURCES = ("who", "ema")
DEFAULT_MAX_FETCHES = 30
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_TIMEOUT = 15
DEFAULT_RETRY_DAYS = 7
MAX_CHARS = 600
CACHE_PATH = "data/global_intelligence/page_descriptions.json"
_META_KEYS = ("description", "og:description")


class _MetaParser(HTMLParser):
    """Collects <meta name|property=description|og:description content=...> only; text nodes are ignored."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        attrs = {k.lower(): (v or "") for k, v in attrs}
        key = (attrs.get("name") or attrs.get("property") or "").strip().lower()
        if key in _META_KEYS and key not in self.found and attrs.get("content", "").strip():
            self.found[key] = attrs["content"]

    handle_startendtag = handle_starttag


def _clean(text: str) -> str:
    # Some CMSs put markup inside the attribute; drop tags, decode entities once, collapse whitespace.
    text = unescape(re.sub(r"<[^>]{0,500}>", " ", text or ""))
    return " ".join(text.split())


def cap(text: str, limit: int = MAX_CHARS) -> tuple[str, bool]:
    """At most ``limit`` characters, cut at a word boundary and ended with "…" when cut."""
    if len(text) <= limit:
        return text, False
    cut = text[: limit - 1]
    if " " in cut[limit // 2:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:.-") + "…", True


def extract_meta_description(raw: bytes | str, limit: int = MAX_CHARS) -> tuple[str | None, bool]:
    """The page's own declared description (``name="description"`` first, then ``og:description``), or None."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw or "")
    parser = _MetaParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed HTML -> no description
        return None, False
    for key in _META_KEYS:
        value = _clean(parser.found.get(key, ""))
        if value:
            return cap(value, limit)
    return None, False


def settings(config: dict) -> dict:
    cfg = ((config.get("daily_feed") or {}).get("page_meta_description")) or {}
    domains = [d for d in (cfg.get("allowed_domains") or ALLOWED_DOMAINS) if d in ALLOWED_DOMAINS]
    return {"enabled": cfg.get("enabled") is True, "sources": set(cfg.get("sources") or DEFAULT_SOURCES), "domains": domains,
            "max_fetches": int(cfg.get("max_new_fetches_per_run", DEFAULT_MAX_FETCHES)),
            "max_bytes": int(cfg.get("max_bytes", DEFAULT_MAX_BYTES)), "timeout": float(cfg.get("timeout_seconds", DEFAULT_TIMEOUT)),
            "max_chars": min(int(cfg.get("max_chars", MAX_CHARS)), MAX_CHARS),
            "retry_days": int(cfg.get("retry_failed_after_days", DEFAULT_RETRY_DAYS)),
            "cache_path": cfg.get("cache_path") or CACHE_PATH}


def host_allowed(url: str, domains) -> bool:
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and not parts.username and parts.port in (None, 443) and any(
        host == d or host.endswith("." + d) for d in domains)


def load_cache(path: Path) -> dict:
    data = json.loads(path.read_text()) if path.exists() else {}
    data.setdefault("schema_version", 1)
    data.setdefault("entries", {})
    return data


def needs_description(card: dict, cfg: dict) -> bool:
    return card.get("source") in cfg["sources"] and not (card.get("description") or "").strip() and host_allowed(card.get("url"), cfg["domains"])


def fetch_descriptions(cards: list[dict], config: dict, cache: dict, client, *, now: datetime | None = None, skip=None) -> dict:
    """Fill ``cache["entries"]`` for cards that need a description. ``client`` offers ``check_robots(url)`` and
    ``fetch(url) -> (bytes, record)`` (``CaptureClient``). ``skip(card)`` -> True leaves a card alone (e.g. a verified
    title-only summary already exists: keep that paid output). Returns run stats."""
    cfg = settings(config)
    now = now or datetime.now(timezone.utc)
    stats = {"page_fetches": 0, "described": 0, "robots_disallowed": 0, "no_meta_description": 0, "errors": 0,
             "off_allowlist": 0, "from_cache": 0, "skipped": 0, "stopped": None}
    if not cfg["enabled"] or client is None:
        stats["stopped"] = "disabled" if not cfg["enabled"] else "offline"
        return stats
    entries = cache.setdefault("entries", {})
    ordered = sorted(cards, key=lambda c: (c.get("published_at") or "", c.get("priority") or 0), reverse=True)
    for card in ordered:
        if card.get("source") not in cfg["sources"] or (card.get("description") or "").strip():
            continue
        url = card.get("url") or ""
        if not host_allowed(url, cfg["domains"]):
            stats["off_allowlist"] += 1; continue
        entry = entries.get(url)
        if entry and (entry.get("status") == "ok" or now < datetime.fromisoformat(entry.get("retry_after") or entry["checked_at"])):
            stats["from_cache"] += 1; continue
        if skip and skip(card):
            stats["skipped"] += 1; continue
        if stats["page_fetches"] >= cfg["max_fetches"]:
            stats["stopped"] = "run_cap"; break
        stamp = now.isoformat()
        retry = (now + timedelta(days=cfg["retry_days"])).isoformat()
        try:
            client.check_robots(url)
        except Exception as exc:  # noqa: BLE001 - robots denied or unavailable: no page request
            status = "robots_disallowed" if "robots_disallowed" in str(exc) else "robots_unavailable"
            entries[url] = {"status": status, "checked_at": stamp, "retry_after": retry, "source": card.get("source")}
            stats["robots_disallowed" if status == "robots_disallowed" else "errors"] += 1
            if "budget_exhausted" in str(exc) or "rate_limit_deferred" in str(exc):
                stats["stopped"] = "capture_budget_or_cooldown"; break
            continue
        stats["page_fetches"] += 1
        try:
            raw, _record = client.fetch(url)
        except Exception as exc:  # noqa: BLE001 - one page failing never blocks the feed
            entries[url] = {"status": "error", "error": str(exc)[:120], "checked_at": stamp, "retry_after": retry, "source": card.get("source")}
            stats["errors"] += 1
            if "budget_exhausted" in str(exc) or "rate_limit_deferred" in str(exc):
                stats["stopped"] = "capture_budget_or_cooldown"; break
            continue
        if len(raw) > cfg["max_bytes"]:
            entries[url] = {"status": "too_large", "checked_at": stamp, "retry_after": retry, "source": card.get("source")}
            stats["errors"] += 1; continue
        text, truncated = extract_meta_description(raw, cfg["max_chars"])
        if not text:
            entries[url] = {"status": "no_meta_description", "checked_at": stamp, "retry_after": retry, "source": card.get("source")}
            stats["no_meta_description"] += 1; continue
        entries[url] = {"status": "ok", "description": text, "description_truncated": truncated, "description_source": DESCRIPTION_SOURCE,
                        "checked_at": stamp, "source": card.get("source")}
        stats["described"] += 1
    cache["last_run"] = {"at": now.isoformat(), **stats}
    return stats


def apply_descriptions(cards: list[dict], config: dict, cache: dict, skip=None) -> int:
    """Copy cached meta descriptions onto cards that have none. Offline, deterministic. Returns the count applied."""
    cfg = settings(config)
    if not cfg["enabled"]:
        return 0
    applied = 0
    for card in cards:
        if not needs_description(card, cfg) or (skip and skip(card)):
            continue
        entry = (cache.get("entries") or {}).get(card.get("url") or "")
        if entry and entry.get("status") == "ok" and str(entry.get("description") or "").strip():
            text, cut = cap(str(entry["description"]).strip(), cfg["max_chars"])
            card.update(description=text, description_truncated=bool(cut or entry.get("description_truncated")),
                        description_source=DESCRIPTION_SOURCE)
            applied += 1
    return applied


def make_client(captures: Path, root: Path, config: dict):
    """A ``CaptureClient`` limited to the allowlisted page hosts, with this feature's timeout."""
    from .global_discovery_common import CaptureClient
    cfg = settings(config)
    hosts = {h for d in cfg["domains"] for h in (d, "www." + d)}
    return CaptureClient(captures, cooldown_file=root / "data/global_intelligence/http_cooldowns.json",
                         live_budget_seconds=float(((config.get("daily_feed") or {}).get("page_meta_description") or {}).get(
                             "live_budget_seconds", 180)), hosts=hosts, accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                         robots_accept="text/plain,*/*;q=0.1", timeout=cfg["timeout"], max_body_bytes=cfg["max_bytes"])
