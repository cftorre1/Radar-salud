"""One card per story (Dirección, 27-oct-2026, punto II).

Two editorial tools, both declared in config/editorial_story_groups.json:

* ``lead``: several outlets cover the same event (e.g. the first generic of
  Ozempic). The lead card stays; the others are hidden from the feed and listed
  as "otras fuentes" in its detail. History keeps every record.
* ``summary``: a running story with many pieces (e.g. Presupuesto 2027 de
  Salud). One reviewed synthesis card replaces the pieces; each piece stays
  linked as a source. The synthesis text is written in the config and must
  pass the same publication gate and committee as any visible card.

Deterministic: no AI, no new facts beyond the configured text.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

CONFIG = Path("config/editorial_story_groups.json")


def load_groups(root: Path | str = ".") -> list[dict[str, Any]]:
    try:
        data = json.loads((Path(root) / CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    groups = [g for g in data.get("groups", []) if isinstance(g, dict) and g.get("member_urls")]
    seen: set[str] = set()
    valid = []
    for g in groups:  # a URL may belong to one story only; a lead must be one of its members
        urls = set(g["member_urls"])
        if urls & seen or (g.get("mode") == "lead" and g.get("lead_url") not in urls):
            continue
        seen |= urls
        valid.append(g)
    return valid


def _alt(s: dict[str, Any]) -> dict[str, Any]:
    return {"title": s.get("title"), "source_name": s.get("source_name"), "url": s.get("source_url"),
            "event_date": s.get("event_date")}


def apply_story_groups(cards: list[dict[str, Any]], groups: list[dict[str, Any]],
                       gate: Callable[[dict[str, Any]], bool] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (cards without grouped members, synthesis cards that passed ``gate``).

    Members of a synthesis are hidden only when its card passes the gate, so a
    rejected synthesis never makes the story disappear from the feed."""
    by_url = {c.get("source_url"): c for c in cards if c.get("source_url")}
    hidden: set[str] = set()
    summaries: list[dict[str, Any]] = []
    for g in groups:
        members = [by_url[u] for u in g["member_urls"] if u in by_url]
        if g.get("mode") == "lead":
            lead = by_url.get(g.get("lead_url"))
            if not lead or not members:
                continue
            others = [m for m in members if m is not lead]
            if not others:
                continue
            seen = {a.get("url") for a in lead.get("source_alternatives") or []} | {lead.get("source_url")}
            alts = list(lead.get("source_alternatives") or [])
            for m in others:
                if m.get("source_url") not in seen:
                    alts.append(_alt(m)); seen.add(m.get("source_url"))
            lead["source_alternatives"] = alts
            lead["story_group"] = g.get("id")
            hidden |= {m.get("source_url") for m in others}
        elif g.get("mode") == "summary":
            card = dict(g.get("card") or {})
            if len(members) < 2 or not card.get("title"):
                continue  # a synthesis needs at least two live pieces
            members.sort(key=lambda m: str(m.get("event_date") or ""), reverse=True)
            latest = str(members[0].get("event_date") or "")[:10]
            card.update({
                "display_title": card["title"], "card_what": card.get("what_happened"),
                "card_why": card.get("why_it_matters"), "event_date": latest, "publication_date": latest,
                "event_type": "STORY_SUMMARY", "story_group": g.get("id"),
                "source_alternatives": [_alt(m) for m in members],
                "derived_from": "editorial_story_group",
                "source_url": card.get("source_url") or members[0].get("source_url"),
                "ingestion_mode": "LIVE" if any(m.get("ingestion_mode") == "LIVE" for m in members) else "BACKFILL",
            })
            if gate is not None and not gate(card):
                continue
            summaries.append(card)
            hidden |= {m.get("source_url") for m in members}
    return [c for c in cards if c.get("source_url") not in hidden], summaries
