"""Daily Global feed: headline + link cards from licensed/public sources (no bodies, no AI).

Built after the daily discovery steps from two inputs that already exist:

* ``data/global_intelligence/feed_discovery.json`` (RSS/Atom feeds declared in
  ``config/global_discovery.json`` ``feeds``, each with a rights basis), and
* ``data/global_intelligence/discovery.json`` (WHO/PAHO metadata crawl), used only
  for a publisher whose ``publication_activation`` is true (two consecutive daily
  live runs, Dirección 27-oct).

Each card keeps the publisher's own title verbatim, its link, date, attribution
(and byline when the licence asks for it), the publisher's own short summary when
the feed's rights allow it (verbatim, <= 300 characters; otherwise ``None`` and the
card shows the title only) plus a deterministic Spanish relevance line built from
fixed templates. Nothing else from the publisher is stored. Cards are explicitly
"titular de fuente", never an Alicanto analysis or a Chile effect.

The output is one inbox ordered by date with a rolling 90-day history
(``retention_days``), so the view does not empty when a feed only exposes its
latest entries. The same announcement reaching us through two publishers or routes
(same canonical URL, or the same headline within ``DUPLICATE_TITLE_DAYS``) is kept once;
the other copies are recorded (``also_reported_by`` / ``duplicates``), never silently
dropped, and a card id already shown keeps its id (read state survives).
"""
from __future__ import annotations

import json
import re
import unicodedata
from hashlib import sha256
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .global_feed_discovery import PERMITTED_USE, SEGMENTS, classify_relevance, enabled_routes
from .global_relevance import global_interest, source_rules

SCHEMA_VERSION = 2
DEFAULT_WINDOW_DAYS = 90
DUPLICATE_TITLE_DAYS = 3
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


def _card(*, item_id, source, label, attribution, kind_es, title, url, published_at, segments, priority, bylines, rights_basis, as_of,
          description=None, description_truncated=False, sections=()):
    segments = [s for s in SEGMENTS if s in set(segments)]
    return {"id": item_id, "source": source, "source_label": label, "attribution": attribution, "bylines": bylines,
            "title": title, "url": url, "published_at": published_at, "segments": segments,
            # Publisher's own summary, verbatim (<= 300 chars) or None -> title only. Never generated.
            "description": description or None, "description_truncated": bool(description and description_truncated),
            # A cut summary is an excerpt (the UI shows "… (extracto)"), never claimed as the unaltered summary.
            "description_source": (None if not description else "publisher_feed_summary_excerpt"
                                   if description_truncated else "publisher_feed_summary_verbatim"),
            "tags_es": [SEGMENT_ES[s] for s in segments], "summary_es": summary_es(kind_es, segments),
            "summary_method": SUMMARY_METHOD, "ai_used": False, "priority": int(priority or 0),
            "kind": "headline", "content_use": "metadata_and_link_only", "body_stored": False,
            "chile_transfer": "hypothesis_only", "rights_basis": rights_basis, "sections": sorted(set(sections)),
            "first_seen_on": as_of.isoformat()}


def rights_basis_for(feed: dict) -> dict:
    """The card's rights record, from today's config. ``attribution`` carries the licence's required
    attribution statement (OGL v3.0 requires it on every reuse)."""
    rights = feed.get("rights") or {}
    return {"basis": rights.get("basis"), "license": rights.get("license"), "license_url": rights.get("license_url"),
            "license_label": rights.get("license_label"), "attribution": rights.get("attribution"),
            "evidence_urls": rights.get("evidence_urls", []), "verified_on": rights.get("verified_on")}


def description_allowed(feed: dict | None, sections=()) -> bool:
    """May this card keep the publisher's summary today? Needs feed-level ``store_description`` with its own
    ``rights.description_basis`` and at least one of the card's routes not withholding summaries (unknown
    routes: every route of the feed must allow it). Fail closed."""
    feed = feed or {}
    if not feed.get("store_description") or not (feed.get("rights") or {}).get("description_basis"):
        return False
    allowed = {r.get("section") for r in feed.get("routes", []) if r.get("store_description", True) is not False}
    sections = set(sections or ())
    if sections:
        return bool(sections & allowed)
    return len(allowed) == len(feed.get("routes", []))


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
        if not route_enabled(feed, row.get("sections") or [row.get("section")]):
            held["route_not_enabled"] += 1; continue
        interest = interest_for(row["title"], row.get("categories") or (), row["source"], config)
        if not interest["relevant"]:
            held[interest["reason"]] += 1; continue
        if not paid_tier_eligible(feed):
            # Global is PREMIUM: a NonCommercial licence (KFF) stays out until the publisher confirms in writing.
            held["paid_tier_hold_" + row["source"]] += 1; continue
        matched = [s for s in classification.get("segments", []) if s in SEGMENTS]
        # A source's 2-segment floor (opinion/explainer feeds) is waived when the headline carries one of the
        # strong Dirección 28-oct signals (AI, financing/payment, new technology, workforce): one segment suffices.
        minimum = int(display.get("min_segment_matches", 1))
        if set(interest.get("signals") or ()) & set(display.get("min_segment_matches_waived_for_signals") or ()):
            minimum = 1
        if classification.get("reason") == "segment_keyword_match" and len(matched) < minimum:
            held["below_min_segment_matches"] += 1; continue
        cards.append(_card(item_id=row["item_id"], source=row["source"], label=display.get("label") or feed["name"],
                           attribution=feed["attribution"], kind_es=display.get("kind_es") or feed["name"], title=row["title"],
                           url=row["url"], published_at=row["published_at"], segments=matched,
                           priority=classification.get("priority"), bylines=row.get("bylines", []) if display.get("show_byline") else [],
                           description=row.get("description") if description_allowed(feed, row.get("sections") or [row.get("section")]) else None,
                           description_truncated=row.get("description_truncated", False),
                           sections=row.get("sections") or ([row["section"]] if row.get("section") else []),
                           rights_basis=rights_basis_for(feed), as_of=as_of))
    return cards, held


def route_enabled(feed: dict, sections) -> bool:
    """A card shows only while at least one of its routes is enabled (a held-off route hides its history too)."""
    on = {r.get("section") for r in enabled_routes(feed)}
    known = {s for s in sections or () if s}
    # Schema-1 history cards carry no sections: they stay while the feed has an enabled route.
    return bool(on & known) if known else bool(on)


def interest_for(title: str, categories, source: str, config: dict) -> dict:
    """Dirección 28-oct 09:58 gate (trends and global interest), with the source's own rules."""
    return global_interest(title, categories, source=source, rules=source_rules(config, source))


def official_cards(discovery: dict, as_of: date, config: dict | None = None) -> tuple[list[dict], Counter]:
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
        interest = interest_for(row["title"], (), source, config or {})
        if not interest["relevant"]:
            held[interest["reason"]] += 1; continue
        segments = relevance["segments"]
        cards.append(_card(item_id=sha256(row["url"].encode()).hexdigest()[:20], source=source, label=meta["label"], attribution=meta["attribution"],
                           kind_es=meta["kind_es"], title=row["title"], url=row["url"], published_at=row["published_at"], segments=segments,
                           priority=classification.get("priority"), bylines=[],
                           rights_basis={"license": "metadata_and_link_only (Dirección 27-oct)", "attribution": None, "evidence_urls": [], "verified_on": None}, as_of=as_of))
    return cards, held


def _title_key(title: str) -> str:
    # GOV.UK document-type prefixes ("Guidance:", "Consultation outcome:", "Press release:") are part of the
    # key: "Guidance: X" and "Consultation outcome: X" are different documents and are never merged.
    text = "".join(c for c in unicodedata.normalize("NFKD", (title or "").casefold()) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def dedupe(cards: list[dict], visible_ids=frozenset()) -> tuple[list[dict], list[dict]]:
    """One card per announcement: same normalized headline within DUPLICATE_TITLE_DAYS.

    A card already shown (``visible_ids``: the previous payload) keeps its id even when an earlier-dated
    twin arrives later, so read state survives; otherwise the earliest-dated card (higher priority, then
    id, on ties) is kept. Every merged copy is recorded: other publishers in the kept card's
    ``also_reported_by``, and every copy (same publisher too) in the returned ledger."""
    kept, ledger = [], []
    by_title: dict[str, list[dict]] = defaultdict(list)
    for card in sorted(cards, key=lambda c: (c["id"] not in visible_ids, c["published_at"], -c["priority"], c["id"])):
        key = _title_key(card["title"])
        twin = next((k for k in by_title.get(key, []) if len(key) >= 20
                     and abs((_day(card["published_at"]) - _day(k["published_at"])).days) <= DUPLICATE_TITLE_DAYS), None)
        if twin is not None:
            same = card["source"] == twin["source"]
            ledger.append({"kept_id": twin["id"], "merged_id": card["id"], "source": card["source"], "url": card["url"],
                           "published_at": card["published_at"], "title": card["title"],
                           "reason": "same_source_same_title" if same else "cross_source_same_title"})
            if not same:
                also = twin.setdefault("also_reported_by", [])
                if not any(a["source"] == card["source"] for a in also):
                    also.append({"source": card["source"], "source_label": card["source_label"], "url": card["url"],
                                 "published_at": card["published_at"]})
            # Never borrow another publisher's summary: the kept card shows its own, or the title only.
            continue
        by_title[key].append(card)
        kept.append(card)
    return kept, ledger


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
    window = int(policy.get("window_days", DEFAULT_WINDOW_DAYS))
    # History must cover at least the visible window (90 days for the single Global inbox).
    retention = max(int(policy.get("retention_days", window)), window)
    # Showing headlines is a publication decision (CLAUDE.md §3): it needs a recorded Dirección authorization.
    enabled, authorized_by = authorization(policy)
    new, held = [], Counter()
    if enabled:
        a, held_a = feed_cards(feed_payload or {}, config, as_of)
        b, held_b = official_cards(discovery or {}, as_of, config)
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
    feeds = {f["id"]: f for f in config.get("feeds", [])}
    visible = set()
    for card in (previous or {}).get("items", []) if enabled else []:
        day = _day(card.get("published_at"))
        if card.get("source") in authorized and day and 0 <= (as_of - day).days < retention:
            # History follows today's rules too: a disabled route or a headline outside the Global-interest rule
            # (Dirección 28-oct 09:58) leaves the inbox; the read state of the rest is kept.
            if card["source"] in feeds and not route_enabled(feeds[card["source"]], card.get("sections") or []):
                continue
            if not interest_for(card.get("title") or "", (), card["source"], config)["relevant"]:
                continue
            card = dict(card)
            if card["source"] in feeds:
                # Re-check today's rights: licence record (incl. required attribution) and the summary right.
                card["rights_basis"] = rights_basis_for(feeds[card["source"]])
                if not description_allowed(feeds[card["source"]], card.get("sections")):
                    card.update(description=None, description_truncated=False, description_source=None)
            else:
                card.update(description=None, description_truncated=False, description_source=None)
            by_id[card["id"]] = card
            visible.add(card["id"])
    for card in new:
        if card["id"] in by_id:
            card["first_seen_on"] = by_id[card["id"]].get("first_seen_on", card["first_seen_on"])
        by_id[card["id"]] = card
    cards = [c for c in by_id.values() if (d := _day(c["published_at"])) and 0 <= (as_of - d).days < retention]
    for card in cards:
        card.pop("also_reported_by", None)  # recomputed every run from the cards still present
        card.setdefault("description", None)  # history cards from schema 1 carry no summary: title only
    cards, duplicates = dedupe(cards, visible)
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
            "held": dict(sorted(held.items())), "capped_per_source_day": capped, "duplicates_merged": len(duplicates), "duplicates": duplicates,
            "description_policy": "publisher_summary_verbatim_max_300_chars_or_title_only",
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
    from .source_rights import redact_public_payload
    payload = redact_public_payload(payload)  # paywalled press: title + public lead only
    atomic_json(target, payload)
    return payload
