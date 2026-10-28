"""Daily Global feed: headline + link cards from licensed/public sources (no bodies, no AI).

Built after the daily discovery steps from two inputs that already exist:

* ``data/global_intelligence/feed_discovery.json`` (RSS/Atom feeds declared in
  ``config/global_discovery.json`` ``feeds``, each with a rights basis), and
* ``data/global_intelligence/discovery.json`` (WHO/PAHO metadata crawl), used only
  for a publisher whose ``publication_activation`` is true (two consecutive daily
  live runs, Dirección 27-oct).

Each card keeps the publisher's own title verbatim, its link, date, attribution
(and byline when the licence asks for it) plus a deterministic Spanish relevance
line built from fixed templates. Nothing else from the publisher is stored. Cards
are explicitly "titular de fuente", never an Alicanto analysis or a Chile effect.

The output keeps a rolling history (``retention_days``) so the 14/30-day views do
not empty when a feed only exposes its latest entries.
"""
from __future__ import annotations

import json
from hashlib import sha256
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .global_feed_discovery import PERMITTED_USE, SEGMENTS, classify_relevance

SCHEMA_VERSION = 1
SUMMARY_METHOD = "deterministic_template_v1"
SEGMENT_ES = {
    "payers": "Aseguradores y financiamiento",
    "providers": "Prestadores",
    "pharma": "Medicamentos y farma",
    "regulation": "Regulación",
    "healthtech": "Salud digital y dispositivos",
    "ai_in_health": "IA en salud",
}
# WHO/PAHO discovery categories -> executive segments (shared with scripts/discover_global_sources.py).
WHO_CATEGORY_SEGMENTS = {"emergency": ["providers", "regulation"], "policy_guidelines": ["regulation"], "financing_systems": ["payers", "providers"],
                         "epidemiology": ["providers"], "technical_document": ["regulation"]}
OFFICIAL_SOURCES = {
    "who": {"label": "OMS", "attribution": "Organización Mundial de la Salud (OMS)", "kind_es": "Organismo multilateral de salud",
            "hosts": {"www.who.int", "who.int"}},
    "paho": {"label": "OPS", "attribution": "Organización Panamericana de la Salud (OPS)", "kind_es": "Organismo regional de salud (Américas)",
             "hosts": {"www.paho.org", "paho.org", "iris.paho.org"}},
}


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def summary_es(kind_es: str, segments: list[str]) -> str:
    """One deterministic Spanish line: who publishes + why a Chilean health executive may care."""
    tags = [SEGMENT_ES[s] for s in segments if s in SEGMENT_ES]
    # A label ending in an abbreviation ("EE. UU.") already carries its period: never print "EE. UU..".
    head = kind_es.rstrip() if kind_es.rstrip().endswith(".") else kind_es.rstrip() + "."
    return f"{head} Relevante para: {', '.join(tags)}." if tags else head


def _card(*, item_id, source, label, attribution, kind_es, title, url, published_at, segments, priority, bylines, rights_basis, as_of):
    segments = [s for s in SEGMENTS if s in set(segments)]
    return {"id": item_id, "source": source, "source_label": label, "attribution": attribution, "bylines": bylines,
            "title": title, "url": url, "published_at": published_at, "segments": segments,
            "tags_es": [SEGMENT_ES[s] for s in segments], "summary_es": summary_es(kind_es, segments),
            "summary_method": SUMMARY_METHOD, "ai_used": False, "priority": int(priority or 0),
            "kind": "headline", "content_use": "metadata_and_link_only", "body_stored": False,
            "chile_transfer": "hypothesis_only", "rights_basis": rights_basis, "first_seen_on": as_of.isoformat()}


def paid_tier_eligible(feed: dict | None) -> bool:
    """PREMIUM eligibility comes from the feed's rights in config, never from a row default (fail closed)."""
    rights = (feed or {}).get("rights") or {}
    if not rights:
        return False
    if rights.get("paid_tier_requires_publisher_confirmation") is False:
        return True
    if rights.get("paid_tier_requires_publisher_confirmation"):
        return bool(str(rights.get("paid_tier_confirmation") or "").strip())
    return False


def authorization(policy: dict) -> tuple[bool, str | None]:
    """Recorded Dirección authorization: non-blank authorized_by and a valid, non-future authorized_at."""
    by = str(policy.get("authorized_by") or "").strip()
    at = _day(policy.get("authorized_at"))
    if not policy.get("enabled") or not by or at is None or str(policy.get("authorized_at")).strip() != at.isoformat() or at > date.today():
        return False, None
    return True, by


def feed_cards(feed_payload: dict, config: dict, as_of: date) -> tuple[list[dict], Counter]:
    """Cards from licensed feeds. Every gate is recorded in ``held`` with its reason."""
    feeds = {f["id"]: f for f in config.get("feeds", [])}
    held, cards = Counter(), []
    for row in feed_payload.get("items", []):
        feed = feeds.get(row.get("source"))
        if not feed or not feed.get("enabled"):
            held["feed_not_enabled"] += 1; continue
        display = feed.get("daily_feed") or {}
        rights = feed.get("rights") or {}
        if not display.get("display") or rights.get("permitted_use") != PERMITTED_USE:
            held["feed_not_authorized_for_display"] += 1; continue
        classification = row.get("classification") or {}
        if row.get("status") != "pending" or not classification.get("relevant") or not row.get("published_at") or not row.get("url"):
            held["not_relevant_or_undated"] += 1; continue
        if (urlsplit(row["url"]).hostname or "") not in set(feed["allowed_link_hosts"]):
            held["link_outside_licensed_hosts"] += 1; continue
        if not paid_tier_eligible(feed):
            # Global is PREMIUM: a NonCommercial licence (KFF) stays out until the publisher confirms in writing.
            held["paid_tier_hold_" + row["source"]] += 1; continue
        matched = [s for s in classification.get("segments", []) if s in SEGMENTS]
        if classification.get("reason") == "segment_keyword_match" and len(matched) < int(display.get("min_segment_matches", 1)):
            held["below_min_segment_matches"] += 1; continue
        cards.append(_card(item_id=row["item_id"], source=row["source"], label=display.get("label") or feed["name"],
                           attribution=feed["attribution"], kind_es=display.get("kind_es") or feed["name"], title=row["title"],
                           url=row["url"], published_at=row["published_at"], segments=matched,
                           priority=classification.get("priority"), bylines=row.get("bylines", []) if display.get("show_byline") else [],
                           rights_basis={"license": rights.get("license"), "license_url": rights.get("license_url"), "license_label": rights.get("license_label"),
                                         "evidence_urls": rights.get("evidence_urls", []),
                                         "verified_on": rights.get("verified_on")}, as_of=as_of))
    return cards, held


def official_cards(discovery: dict, as_of: date) -> tuple[list[dict], Counter]:
    """WHO/PAHO cards, only for a publisher whose two-daily-run activation guard is currently on."""
    health = discovery.get("source_health") or {}
    held, cards, seen = Counter(), [], set()
    for row in discovery.get("items", []):
        source = row.get("source")
        meta = OFFICIAL_SOURCES.get(source)
        if not meta:
            continue
        if not (health.get(source) or {}).get("publication_activation"):
            held["publication_activation_pending_" + source] += 1; continue
        classification = row.get("classification") or {}
        if not row.get("detail_verified") or classification.get("materiality") != "candidate" or not row.get("published_at"):
            held["not_material_or_unverified"] += 1; continue
        if (urlsplit(row.get("url") or "").hostname or "") not in meta["hosts"]:
            held["link_outside_publisher_hosts"] += 1; continue
        identity = row.get("event_id") or row["url"]
        aliases = set(row.get("source_aliases") or []) | {identity}
        if aliases & seen:
            continue
        seen |= aliases
        relevance = classify_relevance(row["title"], ())
        # Daily rows need an executive keyword in the title itself; a WHO/PAHO category default alone is too broad
        # (country capacity-building news). Those items stay available to the editorial candidates.
        if not relevance["relevant"] or relevance["reason"] != "segment_keyword_match":
            held["official_title_without_executive_keyword"] += 1; continue
        segments = relevance["segments"]
        cards.append(_card(item_id=sha256(row["url"].encode()).hexdigest()[:20], source=source, label=meta["label"], attribution=meta["attribution"],
                           kind_es=meta["kind_es"], title=row["title"], url=row["url"], published_at=row["published_at"], segments=segments,
                           priority=classification.get("priority"), bylines=[],
                           rights_basis={"license": "metadata_and_link_only (Dirección 27-oct)", "evidence_urls": [], "verified_on": None}, as_of=as_of))
    return cards, held


def _cap_per_source_day(cards: list[dict], cap: int) -> tuple[list[dict], int]:
    kept, count, dropped = [], defaultdict(int), 0
    for card in sorted(cards, key=lambda c: (-c["priority"], c["published_at"], c["id"]), reverse=False):
        key = (card["source"], card["published_at"])
        if count[key] >= cap:
            dropped += 1; continue
        count[key] += 1
        kept.append(card)
    return kept, dropped


def build(feed_payload: dict, discovery: dict, config: dict, previous: dict | None, as_of: date, generated_at: str | None = None) -> dict:
    policy = config.get("daily_feed") or {}
    retention = int(policy.get("retention_days", 45))
    window = int(policy.get("window_days", 14))
    # Showing headlines is a publication decision (CLAUDE.md §3): it needs a recorded Dirección authorization.
    enabled, authorized_by = authorization(policy)
    new, held = [], Counter()
    if enabled:
        a, held_a = feed_cards(feed_payload or {}, config, as_of)
        b, held_b = official_cards(discovery or {}, as_of)
        new, held = a + b, held_a + held_b
    else:
        held["daily_feed_awaiting_direccion_authorization"] += 1
    by_id = {}
    # Keep earlier cards (history), but only while their source is still authorized for display.
    # History is re-gated with today's config: display, rights and PREMIUM eligibility (a KFF card never survives).
    authorized = {f["id"] for f in config.get("feeds", []) if f.get("enabled") and (f.get("daily_feed") or {}).get("display")
                  and (f.get("rights") or {}).get("permitted_use") == PERMITTED_USE and paid_tier_eligible(f)}
    authorized |= {s for s in OFFICIAL_SOURCES if ((discovery or {}).get("source_health") or {}).get(s, {}).get("publication_activation")
                   or any(c["source"] == s for c in new)}
    for card in (previous or {}).get("items", []) if enabled else []:
        day = _day(card.get("published_at"))
        if card.get("source") in authorized and day and 0 <= (as_of - day).days < retention:
            by_id[card["id"]] = card
    for card in new:
        if card["id"] in by_id:
            card["first_seen_on"] = by_id[card["id"]].get("first_seen_on", card["first_seen_on"])
        by_id[card["id"]] = card
    cards = [c for c in by_id.values() if (d := _day(c["published_at"])) and 0 <= (as_of - d).days < retention]
    cards, capped = _cap_per_source_day(cards, int(policy.get("max_per_source_per_day", 6)))
    cards.sort(key=lambda c: (c["published_at"], c["priority"], c["id"]), reverse=True)
    ages = [(as_of - _day(c["published_at"])).days for c in cards]
    newest = cards[0]["published_at"] if cards else None
    stale_after = int(policy.get("stale_after_days", 2))
    last7 = [c for c in cards if (as_of - _day(c["published_at"])).days < 7]
    segments7 = Counter(s for c in last7 for s in c["segments"])
    return {"schema_version": SCHEMA_VERSION, "as_of": as_of.isoformat(),
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(), "enabled": enabled,
            "authorized_by": authorized_by, "authorized_at": policy.get("authorized_at") if enabled else None,
            "access_tier": "PREMIUM", "kind": "global_daily_headlines", "content_use": "metadata_and_link_only",
            "body_stored": False, "paid_ai_calls": 0, "summary_method": SUMMARY_METHOD,
            "editorial_status": "headline_index_not_editorial_analysis", "chile_transfer": "hypothesis_only",
            "window_days": window, "retention_days": retention,
            "freshness": {"newest_published_at": newest, "items_last_2_days": sum(a < 2 for a in ages),
                          "items_last_7_days": len(last7), "status": "fresh" if newest and (as_of - _day(newest)).days < stale_after else "stale",
                          "stale_after_days": stale_after},
            "sources": sorted({(c["source"], c["source_label"]) for c in cards}),
            "held": dict(sorted(held.items())), "capped_per_source_day": capped,
            # Input for the weekly "Desde afuera" theme: the most active segments of the week, with their cards.
            "weekly_signal": [{"segment": s, "label_es": SEGMENT_ES[s], "count": n,
                               "item_ids": [c["id"] for c in sorted(last7, key=lambda c: -c["priority"]) if s in c["segments"]][:5]}
                              for s, n in segments7.most_common(3)],
            "items": cards}


def _read(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def export(root: Path, as_of: date) -> dict:
    """Read the discovery outputs, write ``web/data/global_feed.json`` atomically."""
    from .pending_queue import atomic_json
    config = json.loads((root / "config/global_discovery.json").read_text())
    target = root / "web/data/global_feed.json"
    payload = build(_read(root / "data/global_intelligence/feed_discovery.json", {}), _read(root / "data/global_intelligence/discovery.json", {}),
                    config, _read(target, None), as_of)
    atomic_json(target, payload)
    return payload
