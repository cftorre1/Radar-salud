"""Dirección 28-oct-2026 09:58: one registry of Global source candidates; only `enabled` entries run."""
import json
from datetime import date
from pathlib import Path

import pytest

from radar_salud.global_feed_discovery import collect_feeds, enabled_routes

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/global_discovery.json").read_text())
REGISTRY = json.loads((ROOT / "config/global_source_candidates.json").read_text())
ENTRIES = REGISTRY["sources"]
STATUSES = {"enabled", "disabled_pending_verification", "needs_permission", "needs_terms_review", "rejected"}


def _entry_for(feed_id, section=None):
    """The route's own entry when one exists, else the feed's entry (None when neither exists)."""
    refs = [e for e in ENTRIES if (e["config_ref"] or {}).get("feed") == feed_id]
    if section is not None:
        own = [e for e in refs if e["config_ref"].get("section") == section]
        if own:
            return own[0]
    whole = [e for e in refs if "section" not in e["config_ref"]]
    return whole[0] if whole else None


def test_every_registry_entry_has_the_required_fields():
    assert CONFIG["feed_candidates_registry"] == "config/global_source_candidates.json"
    assert set(REGISTRY["statuses"]) == STATUSES
    ids = [e["id"] for e in ENTRIES]
    assert len(ids) == len(set(ids))
    for e in ENTRIES:
        assert e["status"] in STATUSES, e["id"]
        assert e["reason"] and e["next_step"], e["id"]
        assert isinstance(e["evidence_urls"], list) and all(u.startswith("https://") for u in e["evidence_urls"]), e["id"]
        assert {"rights_page", "robots_txt", "feed_live", "on", "how"} <= set(e["verified"]), e["id"]
        assert date.fromisoformat(e["reevaluate_after"]) > date(2026, 10, 28), e["id"]
        if e["status"] != "enabled":
            assert e["published_in_global"] is False, e["id"]
    # The old lists live only in the registry now (single source of truth).
    assert "feed_candidates_excluded" not in CONFIG and "feed_candidates_pending_direccion" not in CONFIG


def test_every_configured_source_has_a_registry_entry_and_its_status_matches_what_runs():
    for feed in CONFIG["feeds"]:
        route_entries = [_entry_for(feed["id"], r["section"]) for r in feed["routes"]]
        assert all(route_entries), feed["id"]
        for route, entry in zip(feed["routes"], route_entries):
            runs = feed["enabled"] and route in enabled_routes(feed)
            assert runs is (entry["status"] == "enabled"), (feed["id"], route["section"])
        assert feed["enabled"] is any(e["status"] == "enabled" for e in route_entries), feed["id"]
    crawl = {e["config_ref"]["routes_source"]: e for e in ENTRIES if (e["config_ref"] or {}).get("routes_source")}
    for route in CONFIG["routes"]:
        assert crawl[route["source"]]["status"] == "enabled"
    # Every source with relevance rules is in the registry.
    known = {(e["config_ref"] or {}).get("feed") for e in ENTRIES} | set(crawl)
    assert set(CONFIG["global_relevance"]["sources"]) <= known


def test_direccion_28_oct_conservative_sources():
    feeds = {f["id"]: f for f in CONFIG["feeds"]}
    for fid in ("uk_dhsc", "uk_mhra", "federal_register_cms"):
        assert feeds[fid]["enabled"] is False and _entry_for(fid)["status"] == "disabled_pending_verification"
    assert _entry_for("fda", "press_releases")["status"] == "enabled"
    assert [r["section"] for r in enabled_routes(feeds["fda"])] == ["press_releases"]
    assert feeds["fda"]["name"] == "US FDA (press releases)"
    for section in ("whats_new_drugs", "whats_new_biologics", "medwatch_safety_alerts"):
        assert _entry_for("fda", section)["status"] == "disabled_pending_verification"
    kff = _entry_for("kff_health_news")
    assert kff["status"] == "enabled" and kff["published_in_global"] is False and "Dirección" in kff["reason"]
    assert feeds["kff_health_news"]["daily_feed"]["display"] is False
    names = " ".join(e["name"] for e in ENTRIES)
    for name in ("Commonwealth Fund", "NEJM", "MedPage", "IHME", "Health Canada", "World Bank blogs", "Health Affairs", "BMJ", "Lancet",
                 "Fierce", "OECD", "CMS.gov", "NHS England", "Australian", "Ministerio de Sanidad", "AEMPS", "Argentina", "Colombia",
                 "México", "Perú", "ISSA", "Federal Register", "KFF", "STAT", "Devex", "Industry Dive", "Reuters", "El País"):
        assert name in names, name
    rejected = {e["id"] for e in ENTRIES if e["status"] == "rejected"}
    assert {"commonwealth_fund", "nejm", "medpage_today", "ihme", "health_canada", "world_bank_blogs"} <= rejected


class _RecordingClient:
    def __init__(self):
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        raise RuntimeError("offline")


def test_only_enabled_registry_entries_are_fetched():
    client = _RecordingClient()
    collect_feeds(CONFIG, client, date(2026, 10, 28))
    enabled_urls = set()
    for feed in CONFIG["feeds"]:
        for route in feed["routes"]:
            entry = _entry_for(feed["id"], route["section"])
            if entry["status"] == "enabled":
                enabled_urls.add(route["url"])
    assert set(client.urls) == enabled_urls
    assert not any("gov.uk" in u or "/drugs/rss.xml" in u or "/medwatch/" in u or "federalregister" in u for u in client.urls)


def test_a_feed_with_an_always_include_rule_is_refused():
    from radar_salud.global_feed_discovery import validate_feed_config
    feed = json.loads(json.dumps(next(f for f in CONFIG["feeds"] if f["id"] == "uk_mhra")))
    feed["include_title_patterns"] = [r"\bnational patient safety alert\b"]
    with pytest.raises(ValueError, match="include_title_patterns"):
        validate_feed_config(feed)
