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
    "https://tools.cdc.gov/api/v2/resources/media/132608.rss": "cdc_newsroom.xml",
    "https://www.nih.gov/news-releases/feed.xml": "nih_news.xml",
    "https://www.ecdc.europa.eu/en/taxonomy/term/1307/feed": "ecdc_news.xml",
    "https://health.ec.europa.eu/node/2/rss_en": "ec_health.xml",
}


class FeedClient:
    network_requests = 0

    def fetch(self, url):
        if url not in BODIES:
            raise ValueError("http_404")
        return (FIX / BODIES[url]).read_bytes(), {"body_sha256": "x", "fetched_at": "2026-10-28T10:00:00+00:00", "http_status": 200, "tls_verified": True}


def authorized(config=CONFIG, **extra):
    config = copy.deepcopy(config)
    config["daily_feed"].update(**extra)
    return config


def with_feed(config, fid, **changes):
    config = copy.deepcopy(config)
    feed = next(f for f in config["feeds"] if f["id"] == fid)
    for key, value in changes.items():
        target, _, leaf = key.rpartition(".")
        node = feed
        for part in filter(None, target.split(".")):
            node = node[part]
        node[leaf] = value
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


def test_direccion_authorization_is_recorded_and_the_gate_fails_closed():
    policy = CONFIG["daily_feed"]
    assert policy["authorized_by"] == "Dirección (cftorre1)" and policy["authorized_at"] == "2026-10-28"
    assert "Sí, encender" in policy["authorization_note"] and "include_paid_tier_hold_items" not in policy
    ok = build(feed_payload(), who_discovery(), CONFIG, None, AS_OF)
    assert ok["enabled"] and ok["authorized_by"] == "Dirección (cftorre1)" and ok["authorized_at"] == "2026-10-28"
    for bad in ({"authorized_by": None}, {"authorized_by": "   "}, {"authorized_at": None}, {"authorized_at": ""},
                {"authorized_at": "28-10-2026"}, {"authorized_at": "2026-02-30"}, {"authorized_at": "2026-10-28T99"},
                {"authorized_at": "2999-01-01"}, {"enabled": False}):
        payload = build(feed_payload(), who_discovery(), authorized(**bad), None, AS_OF)
        assert payload["enabled"] is False and payload["items"] == [], bad
        assert "daily_feed_awaiting_direccion_authorization" in payload["held"]


def test_cards_are_headline_link_and_deterministic_spanish_line_only():
    payload = build(feed_payload(), who_discovery(), authorized(), None, AS_OF)
    assert payload["enabled"] and payload["paid_ai_calls"] == 0 and payload["body_stored"] is False
    cards = {c["title"]: c for c in payload["items"]}
    fda = cards["FDA Approves First Biosimilar for Treatment of Rare Blood Disorder"]
    assert fda["source_label"] == "FDA" and fda["kind"] == "headline" and fda["ai_used"] is False
    assert fda["summary_es"] == "Regulador de medicamentos y dispositivos de EE. UU. Relevante para: Medicamentos y farma, Regulación."
    assert ".." not in blob_of(build(feed_payload(), {}, CONFIG, None, AS_OF)) and fda["chile_transfer"] == "hypothesis_only"
    assert set(fda) >= {"title", "url", "published_at", "attribution", "tags_es", "rights_basis"}
    blob = json.dumps(payload)
    assert "Body not stored" not in blob and "Body must never be stored" not in blob
    # Noise and consumer items never reach the page.
    assert "FDA Warns Consumers Not to Use Certain Tattoo Inks" not in cards and "Why do we yawn? A doctor explains" not in cards
    # The Conversation (CC BY-ND) keeps its byline and verbatim headline; it needs two segment matches.
    conv = cards["Medicare Advantage insurers use AI to deny coverage – what the data shows"]
    assert conv["bylines"] == ["Ana Researcher, University of Somewhere"] and conv["source_label"] == "The Conversation"
    assert {"payers", "ai_in_health"} <= set(conv["segments"])
    # Federal Register stays off until robots for /api/ is verified (fail closed).
    assert not any(c["source"] == "federal_register_cms" for c in payload["items"])
    fr = with_feed(CONFIG, "federal_register_cms", enabled=True)
    fr_cards = {c["title"] for c in build(feed_payload(fr), {}, fr, None, AS_OF)["items"]}
    assert "Medicare Program; Hospital Outpatient Prospective Payment System: Final Rule" in fr_cards
    assert "Privacy Act of 1974; Matching Program" not in fr_cards


def blob_of(payload):
    return json.dumps([c["summary_es"] for c in payload["items"]], ensure_ascii=False)


def kff_card(i):
    return {"id": f"kff{i}", "source": "kff_health_news", "source_label": "KFF Health News", "title": f"KFF story {i}",
            "url": f"https://kffhealthnews.org/news/article/s{i}/", "published_at": "2026-10-27", "segments": ["payers"],
            "priority": 80, "summary_es": "x", "first_seen_on": "2026-10-27"}


def test_kff_is_out_by_direccion_decision_and_eligibility_fails_closed_from_config_rights():
    kff = next(f for f in CONFIG["feeds"] if f["id"] == "kff_health_news")
    assert kff["daily_feed"]["display"] is False and "KFF" in CONFIG["daily_feed"]["kff_decision"]
    # Review case: 3 KFF rows WITHOUT a paid_tier_eligible field (older discovery output) plus 3 KFF cards in history.
    shown = with_feed(CONFIG, "kff_health_news", **{"daily_feed.display": True})
    rows = [dict(r) for r in feed_payload(shown)["items"] if r["source"] == "kff_health_news" and r["classification"]["relevant"]]
    for r in rows:
        r.pop("paid_tier_eligible", None); r.pop("paid_tier_hold", None)
    assert len(rows) >= 3
    previous = {"items": [kff_card(i) for i in range(3)]}
    payload = build({"items": rows[:3]}, {}, shown, previous, AS_OF)
    assert not any(c["source"] == "kff_health_news" for c in payload["items"])
    assert payload["held"]["paid_tier_hold_kff_health_news"] == 3
    # No rights block at all -> not eligible either.
    assert not any(c["source"] == "kff_health_news" for c in build({"items": rows[:3]}, {}, with_feed(shown, "kff_health_news", rights={}), previous, AS_OF)["items"])
    # Only a recorded written confirmation would make KFF eligible (and it still needs display on).
    confirmed = with_feed(shown, "kff_health_news", **{"rights.paid_tier_confirmation": "KFF email 2026-11-02"})
    got = [c for c in build({"items": rows[:3]}, {}, confirmed, previous, AS_OF)["items"] if c["source"] == "kff_health_news"]
    assert len(got) == 6 and all(c["attribution"] == "KFF Health News" for c in got if "attribution" in c)
    assert not any(c["source"] == "kff_health_news" for c in build({"items": rows[:3]}, {}, CONFIG, previous, AS_OF)["items"])


def test_every_displayed_feed_states_paid_tier_eligibility_explicitly():
    for feed in CONFIG["feeds"]:
        assert "paid_tier_requires_publisher_confirmation" in feed["rights"], feed["id"]


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
    assert payload["items"]
    keys = [(c["source"], c["published_at"]) for c in payload["items"]]
    assert len(keys) == len(set(keys)) and payload["capped_per_source_day"] >= 0
    assert payload["weekly_signal"] and all(s["item_ids"] for s in payload["weekly_signal"])


def test_summary_line_is_fixed_template():
    assert summary_es("Regulador", ["pharma", "regulation"]) == "Regulador. Relevante para: Medicamentos y farma, Regulación."
    assert summary_es("Regulador", []) == "Regulador."


def test_feed_run_writes_the_daily_feed_and_new_sources_parse(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/global_discovery.json").write_text(json.dumps(CONFIG))
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
    for fid in ("ecdc", "ec_health"):
        assert feeds[fid]["rights"]["license_url"] == "https://creativecommons.org/licenses/by/4.0/" and feeds[fid]["rights"]["license_label"] == "CC BY 4.0"
    assert "https://health.ec.europa.eu/legal-notice_en" in feeds["ec_health"]["rights"]["evidence_urls"]
    assert "17 U.S.C. §105" in feeds["nih"]["rights"]["license"] and feeds["nih"]["daily_feed"]["min_segment_matches"] == 2
    assert all(w in feeds["cdc"]["rights"]["attribution"] for w in ("CDC", "HHS", "U.S. Government"))
    fr = feeds["federal_register_cms"]
    assert fr["enabled"] is False and "robots" in fr["disabled_reason"] and not any("feeder.co" in u for u in fr["rights"]["evidence_urls"])
    assert "17 U.S.C. §105" in fr["rights"]["license"]
    assert "NoDerivatives" in " ".join(feeds["the_conversation"]["rights"]["restrictions"])
    excluded = " ".join(r["name"] for r in CONFIG["feed_candidates_excluded"])
    for name in ("World Bank", "Devex", "Industry Dive", "Reuters", "El País"):
        assert name in excluded


import pytest  # noqa: E402

from radar_salud.global_feed_discovery import classify_relevance  # noqa: E402


@pytest.mark.parametrize("fid,fixture,expected", [
    ("cdc", "cdc_newsroom.xml", {"https://www.cdc.gov/media/releases/2026/p1026-antimicrobial-resistance.html": "2026-10-26"}),
    ("nih", "nih_news.xml", {"https://www.nih.gov/news-events/news-releases/nih-study-finds-ai-tool-improves-early-sepsis-detection": "2026-10-27"}),
    ("ecdc", "ecdc_news.xml", {"https://www.ecdc.europa.eu/en/news-events/new-ecdc-guidance-antimicrobial-stewardship-hospitals": "2026-10-26"}),
    ("ec_health", "ec_health.xml", {"https://ec.europa.eu/commission/presscorner/detail/en/ip_26_5001": "2026-10-26"}),
])
def test_new_feeds_parse_title_link_date_without_body(fid, fixture, expected):
    feed = next(f for f in CONFIG["feeds"] if f["id"] == fid)
    rows = parse_feed((FIX / fixture).read_bytes(), feed["routes"][0], feed, AS_OF)
    by_url = {r["url"]: r for r in rows}
    for url, day in expected.items():
        assert by_url[url]["published_at"] == day and by_url[url]["title"] and by_url[url]["body_stored"] is False
    assert "Body not stored" not in json.dumps(rows)


def test_new_feed_cards_on_the_page():
    cards = {c["title"]: c for c in build(feed_payload(), {}, CONFIG, None, AS_OF)["items"]}
    assert "Experimental drug reverses fatty liver disease in mice" not in cards
    assert "Advisory Committee on Immunization Practices (ACIP) Meeting, October 2026" not in cards
    # NIH needs two segment matches: AI tool in hospital emergency departments passes, a lone trial does not.
    assert "NIH study finds AI tool improves early sepsis detection in hospital emergency departments" in cards
    assert "NIH-funded clinical trial will evaluate new dengue therapeutic" not in cards
    ehds = cards["European Health Data Space: Commission adopts first implementing acts on cross-border health data"]
    assert "healthtech" in ehds["segments"] and ehds["rights_basis"]["license_url"].startswith("https://creativecommons.org/licenses/by/4.0")
    gene = cards["Commission authorises first gene therapy for sickle cell disease under accelerated assessment"]
    assert {"pharma", "regulation"} <= set(gene["segments"])
    measles = cards["Measles vaccination coverage falls below 95% in most EU/EEA countries"]
    assert "payers" not in measles["segments"] and measles["rights_basis"]["license_label"] == "CC BY 4.0"


@pytest.mark.parametrize("title,present,absent", [
    ("Clinical trial shows new obesity drug cuts heart attacks", {"pharma"}, {"providers"}),
    ("Rural clinics close as Medicaid cuts bite", {"providers", "payers"}, set()),
    ("Cierre de clínica privada en Santiago", {"providers"}, set()),
    ("Vaccination coverage for HPV stalls among teenagers", set(), {"payers"}),
    ("Low coverage of measles vaccines fuels outbreaks", set(), {"payers"}),
    ("Cobertura de vacunación contra influenza llega a 70%", set(), {"payers"}),
    ("Insurers expand coverage of GLP-1 drugs for obesity", {"payers", "pharma"}, set()),
    ("European Health Data Space enters into force", {"healthtech"}, set()),
    ("EMA recommends and Commission authorises first CRISPR therapy", {"regulation", "pharma"}, set()),
])
def test_relevance_rules_on_realistic_titles(title, present, absent):
    result = classify_relevance(title)
    assert present <= set(result["segments"]) and not (absent & set(result["segments"])), result


@pytest.mark.parametrize("title,category", [
    ("Gene therapy restores hearing in mice", "preclinical_animal_study"),
    ("Study in mouse models links gut microbes to Alzheimer's", "preclinical_animal_study"),
    ("Fruit fly study reveals new insulin signaling pathway", "preclinical_animal_study"),
    ("Zebrafish model sheds light on heart regeneration drugs", "preclinical_animal_study"),
    ("Cellular, Tissue, and Gene Therapies Advisory Committee; Notice of Meeting", "advisory_panel_meeting"),
    ("Medicare Evidence Development & Coverage Advisory Committee meeting, November 2026", "advisory_panel_meeting"),
    ("FDA advisory panel meeting to review Alzheimer's drug", "advisory_panel_meeting"),
])
def test_preclinical_and_advisory_meetings_are_excluded(title, category):
    result = classify_relevance(title)
    assert result["relevant"] is False and result["category"] == category


def test_conversation_bylines_keep_feed_order():
    conv = next(f for f in CONFIG["feeds"] if f["id"] == "the_conversation")
    raw = (FIX / "conversation_health.atom").read_bytes().replace(
        b"<author><name>Ana Researcher, University of Somewhere</name></author>",
        b"<author><name>Zoe Z</name></author><author><name>Al A</name></author><author><name>Mo M</name></author>")
    rows = parse_feed(raw, conv["routes"][0], conv, AS_OF)
    assert rows[0]["bylines"] == ["Zoe Z", "Al A", "Mo M"]
