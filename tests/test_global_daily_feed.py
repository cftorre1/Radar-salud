"""Daily Global headlines (web/data/global_feed.json): rights gates, activation, history and freshness.

Feed bodies are the CONSTRUCTED fixtures in tests/fixtures/global_feeds (no live route from the sandbox)."""
import copy
import json
from datetime import date
from pathlib import Path

from radar_salud.global_daily_feed import build, export, summary_es
from radar_salud.global_feed_discovery import collect_feeds, parse_feed
from scripts import discover_global_feeds

AS_OF = date(2026, 10, 28)
FIX = Path("tests/fixtures/global_feeds")
CONFIG = json.loads(Path("config/global_discovery.json").read_text())
BODIES = {
    "https://kffhealthnews.org/feed/": "kff_feed.xml",
    "https://kffhealthnews.org/topics/health-industry/feed/": "kff_health_industry_feed.xml",
    "https://www.ema.europa.eu/en/news.xml": "ema_news.xml",
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml": "fda_press.xml",
    "https://theconversation.com/us/health/articles.atom": "conversation_health.atom",
    "https://www.federalregister.gov/api/v1/documents.rss?conditions[agencies][]=centers-for-medicare-medicaid-services&order=newest": "federal_register_cms.xml",
}


class FeedClient:
    network_requests = 0

    def fetch(self, url):
        if url not in BODIES:
            raise ValueError("http_404")
        return (FIX / BODIES[url]).read_bytes(), {"body_sha256": "x", "fetched_at": "2026-10-28T10:00:00+00:00", "http_status": 200, "tls_verified": True}


def authorized(config=CONFIG, **extra):
    config = copy.deepcopy(config)
    config["daily_feed"].update(authorized_by="Dirección (test)", authorized_at="2026-10-28", **extra)
    return config


def feed_payload(config=CONFIG):
    items, _, _ = collect_feeds(config, FeedClient(), AS_OF)
    return {"items": items}


def who_discovery(active=True):
    def item(url, title, day, category="financing_systems", materiality="candidate"):
        return {"url": url, "title": title, "source": "who" if "who.int" in url else "paho", "published_at": day, "detail_verified": True,
                "classification": {"materiality": materiality, "priority": 90, "category": category}, "event_id": None, "source_aliases": [url]}
    return {"source_health": {"who": {"publication_activation": active}, "paho": {"publication_activation": False}},
            "items": [item("https://www.who.int/news/item/27-10-2026-health-financing", "WHO report on health financing and insurance coverage", "2026-10-27"),
                      item("https://www.who.int/news/item/20-10-2026-routine", "WHO staff anniversary", "2026-10-20", materiality="routine"),
                      item("https://www.paho.org/es/noticias/x", "OPS: cobertura de vacunas", "2026-10-26")]}


def test_daily_feed_stays_off_without_recorded_direccion_authorization():
    assert CONFIG["daily_feed"]["authorized_by"] is None  # CLAUDE.md §3: showing headlines is a publication decision
    payload = build(feed_payload(), who_discovery(), CONFIG, None, AS_OF)
    assert payload["enabled"] is False and payload["items"] == [] and "daily_feed_awaiting_direccion_authorization" in payload["held"]


def test_cards_are_headline_link_and_deterministic_spanish_line_only():
    payload = build(feed_payload(), who_discovery(), authorized(), None, AS_OF)
    assert payload["enabled"] and payload["paid_ai_calls"] == 0 and payload["body_stored"] is False
    cards = {c["title"]: c for c in payload["items"]}
    fda = cards["FDA Approves First Biosimilar for Treatment of Rare Blood Disorder"]
    assert fda["source_label"] == "FDA" and fda["kind"] == "headline" and fda["ai_used"] is False
    assert fda["summary_es"].startswith("Regulador de medicamentos y dispositivos de EE. UU.") and fda["chile_transfer"] == "hypothesis_only"
    assert set(fda) >= {"title", "url", "published_at", "attribution", "tags_es", "rights_basis"}
    blob = json.dumps(payload)
    assert "Body not stored" not in blob and "Body must never be stored" not in blob
    # Noise and consumer items never reach the page.
    assert "FDA Warns Consumers Not to Use Certain Tattoo Inks" not in cards and "Why do we yawn? A doctor explains" not in cards
    # The Conversation (CC BY-ND) keeps its byline and verbatim headline; it needs two segment matches.
    conv = cards["Medicare Advantage insurers use AI to deny coverage – what the data shows"]
    assert conv["bylines"] == ["Ana Researcher, University of Somewhere"] and conv["source_label"] == "The Conversation"
    assert {"payers", "ai_in_health"} <= set(conv["segments"])
    assert "Medicare Program; Hospital Outpatient Prospective Payment System: Final Rule" in cards
    assert "Privacy Act of 1974; Matching Program" not in cards


def test_kff_noncommercial_items_stay_out_of_premium_until_kff_confirms():
    payload = build(feed_payload(), {}, authorized(), None, AS_OF)
    assert not any(c["source"] == "kff_health_news" for c in payload["items"])
    assert payload["held"].get("paid_tier_hold_kff_health_news", 0) > 0
    config = authorized()
    next(f for f in config["feeds"] if f["id"] == "kff_health_news")["rights"]["paid_tier_confirmation"] = "KFF email 2026-11-02"
    payload = build(feed_payload(config), {}, config, None, AS_OF)
    kff = [c for c in payload["items"] if c["source"] == "kff_health_news"]
    assert kff and all(c["attribution"] == "KFF Health News" for c in kff) and any(c["bylines"] for c in kff)


def test_who_paho_cards_require_the_two_daily_run_activation():
    on = build({}, who_discovery(True), authorized(), None, AS_OF)
    assert [c["source"] for c in on["items"]] == ["who"]  # PAHO not activated, routine WHO item excluded
    assert "payers" in on["items"][0]["segments"] and on["items"][0]["source_label"] == "OMS"
    off = build({}, who_discovery(False), authorized(), None, AS_OF)
    assert off["items"] == [] and off["held"]["publication_activation_pending_who"] == 2


def test_history_is_kept_within_retention_and_freshness_is_measured():
    first = build(feed_payload(), {}, authorized(), None, AS_OF)
    later = build({"items": []}, {}, authorized(), first, date(2026, 11, 3))
    assert {c["id"] for c in later["items"]} == {c["id"] for c in first["items"]}
    assert later["freshness"]["status"] == "stale" and first["freshness"]["status"] == "fresh"
    gone = build({"items": []}, {}, authorized(), first, date(2026, 12, 20))
    assert gone["items"] == []
    # A source whose display is withdrawn disappears from history too.
    config = authorized()
    next(f for f in config["feeds"] if f["id"] == "fda")["daily_feed"]["display"] = False
    assert not any(c["source"] == "fda" for c in build({"items": []}, {}, config, first, AS_OF)["items"])


def test_per_source_daily_cap_and_weekly_signal():
    payload = build(feed_payload(), {}, authorized(max_per_source_per_day=1), None, AS_OF)
    keys = [(c["source"], c["published_at"]) for c in payload["items"]]
    assert len(keys) == len(set(keys)) and payload["capped_per_source_day"] >= 0
    assert payload["weekly_signal"] and all(s["item_ids"] for s in payload["weekly_signal"])


def test_summary_line_is_fixed_template():
    assert summary_es("Regulador", ["pharma", "regulation"]) == "Regulador. Relevante para: Medicamentos y farma, Regulación."
    assert summary_es("Regulador", []) == "Regulador."


def test_feed_run_writes_the_daily_feed_and_new_sources_parse(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/global_discovery.json").write_text(json.dumps(authorized()))
    payload = discover_global_feeds.run(tmp_path, tmp_path / "captures", AS_OF, "daily-test", client=FeedClient())
    assert payload["publication_count"] == 0
    daily = json.loads((tmp_path / "web/data/global_feed.json").read_text())
    assert daily["enabled"] and daily["items"] and daily["content_use"] == "metadata_and_link_only"
    again = export(tmp_path, AS_OF)
    assert [c["id"] for c in again["items"]] == [c["id"] for c in daily["items"]]
    conv = next(f for f in CONFIG["feeds"] if f["id"] == "the_conversation")
    rows = parse_feed((FIX / "conversation_health.atom").read_bytes(), conv["routes"][0], conv, AS_OF)
    assert rows[0]["url"] == "https://theconversation.com/medicare-advantage-insurers-use-ai-to-deny-coverage-300001"


def test_new_sources_declare_verified_rights_and_exclusions_are_explicit():
    feeds = {f["id"]: f for f in CONFIG["feeds"]}
    for fid in ("cdc", "nih", "federal_register_cms", "ecdc", "ec_health", "the_conversation"):
        rights = feeds[fid]["rights"]
        assert rights["verified_on"] == "2026-10-28" and rights["evidence_urls"] and "not fetched live" in rights["verified_how"]
        assert feeds[fid]["daily_feed"]["display"] is True
    assert "NoDerivatives" in " ".join(feeds["the_conversation"]["rights"]["restrictions"])
    excluded = " ".join(r["name"] for r in CONFIG["feed_candidates_excluded"])
    for name in ("World Bank", "Devex", "Industry Dive", "Reuters", "El País"):
        assert name in excluded
