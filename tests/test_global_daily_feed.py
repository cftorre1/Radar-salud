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
    "https://www.gov.uk/government/organisations/department-of-health-and-social-care.atom": "govuk_dhsc.atom",
    "https://www.gov.uk/government/organisations/medicines-and-healthcare-products-regulatory-agency.atom": "govuk_mhra.atom",
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/drugs/rss.xml": "fda_drugs.xml",
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


def govuk_on(config=CONFIG):
    """DHSC/MHRA and the FDA What's New/MedWatch routes are OFF (Dirección 28-oct 09:58, pending verification).
    Tests of their parser, OGL attribution and cross-source dedup switch them on explicitly, as a verified
    re-enable would."""
    config = copy.deepcopy(config)
    for feed in config["feeds"]:
        if feed["id"] in ("uk_dhsc", "uk_mhra"):
            feed["enabled"] = True
        if feed["id"] == "fda":
            for route in feed["routes"]:
                route.pop("enabled", None)
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
    assert "Body must never be stored" not in blob and "Excerpt." not in blob
    # Public-domain FDA keeps its own short summary verbatim; nothing is generated.
    assert fda["description"] == "Publisher summary kept verbatim for the fixture." and fda["description_source"] == "publisher_feed_summary_verbatim"
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
    return {"id": f"kff{i}", "source": "kff_health_news", "source_label": "KFF Health News", "title": f"Medicare Advantage payment trends, part {i}",
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
    # 90-day inbox: still there after 53 days, gone after 90.
    assert {c["id"] for c in build({"items": []}, {}, authorized(), first, date(2026, 12, 20))["items"]} == {c["id"] for c in first["items"]}
    gone = build({"items": []}, {}, authorized(), first, date(2027, 1, 27))
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
    assert daily["enabled"] and daily["content_use"] == "metadata_and_link_only"
    # Dirección 30-oct (Spanish only): without a key nothing has Spanish text, so the public feed lists nothing;
    # every card is kept in the data/ state file and is the history of the next run.
    state = json.loads((tmp_path / "data/global_intelligence/global_feed_state.json").read_text())
    assert state["items"] and daily["items"] == [] and daily["display"]["hidden"] == len(state["items"])
    export(tmp_path, AS_OF)
    again = json.loads((tmp_path / "data/global_intelligence/global_feed_state.json").read_text())
    assert [c["id"] for c in again["items"]] == [c["id"] for c in state["items"]]
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
    registry = json.loads(Path("config/global_source_candidates.json").read_text())
    excluded = " ".join(r["name"] for r in registry["sources"] if r["status"] == "rejected")
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
    # Only the publisher's own summary (RSS description) may be kept, verbatim and markup-free.
    assert all(r.get("description") in (None, "Publisher summary kept verbatim for the fixture.") for r in rows)


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


# --- 28-oct (global-sources-more): GOV.UK OGL feeds, publisher summaries, 90-day inbox, cross-source dedup ---

def test_govuk_atom_feeds_parse_with_ogl_rights_and_routine_filters():
    feeds = {f["id"]: f for f in CONFIG["feeds"]}
    for fid in ("uk_dhsc", "uk_mhra"):
        feed = feeds[fid]
        # Dirección 28-oct 09:58: off until the organisation page and the live feed are verified.
        assert feed["enabled"] is False and "Dirección 28-oct-2026 09:58" in feed["disabled_reason"]
        assert feed["allowed_link_hosts"] == ["www.gov.uk"] and feed["store_description"] is True
        assert feed["rights"]["basis"] == "uk_open_government_licence_v3" and feed["rights"]["license_label"] == "OGL v3.0"
        assert "https://www.gov.uk/robots.txt" in feed["rights"]["evidence_urls"] and "not fetched live" in feed["rights"]["verified_how"]
        assert "/search/all" not in feed["routes"][0]["url"]  # disallowed by gov.uk robots.txt
    assert not any(r["source"] in ("uk_dhsc", "uk_mhra") for r in collect_feeds(CONFIG, FeedClient(), AS_OF)[0])
    items, failures, _ = collect_feeds(govuk_on(), FeedClient(), AS_OF)
    dhsc = {r["title"]: r for r in items if r["source"] == "uk_dhsc"}
    assert dhsc["Guidance: DHSC public appointments: 2026 to 2027"]["classification"]["relevant"] is False
    routine = dhsc["Transparency data: DHSC spending over £25,000: October 2026"]["classification"]
    assert routine["category"] == "publisher_routine_document_type"
    funding = dhsc["New NHS waiting list funding for hospitals to cut elective care backlog"]
    assert funding["classification"]["relevant"] and "providers" in funding["classification"]["segments"]
    assert funding["description"] == "Hospitals in England will receive new funding to expand elective capacity and reduce waiting times."
    assert funding["published_at"] == "2026-10-27" and funding["url"].startswith("https://www.gov.uk/government/news/")
    # A summary over 300 characters is cut at a sentence end that fits, or a word boundary with an ellipsis.
    long = dhsc["Policy paper: Joint DHSC and NHS England written evidence for the NHSPRB: pay round 2027 to 2028"]
    assert len(long["description"]) <= 300 and long["description_truncated"] is True and long["description"].endswith("…")
    assert long["description_basis"] == "publisher_feed_summary_excerpt"  # review 28-oct: a cut summary is not "verbatim"
    assert funding["description_basis"] == "publisher_feed_summary_verbatim"
    # No summary published -> title only (never invented).
    assert dhsc["Press release: AI scribes rolled out across GP practices to free up clinicians' time"]["description"] is None
    mhra = {r["title"]: r for r in items if r["source"] == "uk_mhra"}
    assert mhra["IXCHIQ chikungunya vaccine: UK marketing authorisation withdrawn after safety review"]["description"] == "The marketing authorisation has been withdrawn."
    assert mhra["Official Statistics: MHRA Performance Data"]["classification"]["relevant"] is False


def test_nd_and_noncommercial_feeds_never_keep_a_summary():
    feeds = {f["id"]: f for f in CONFIG["feeds"]}
    assert feeds["the_conversation"]["store_description"] is False and feeds["kff_health_news"]["store_description"] is False
    conv = feeds["the_conversation"]
    rows = parse_feed((FIX / "conversation_health.atom").read_bytes(), conv["routes"][0], conv, AS_OF)
    assert all("description" not in r for r in rows)
    cards = build(feed_payload(), {}, CONFIG, None, AS_OF)["items"]
    assert all(c["description"] is None for c in cards if c["source"] == "the_conversation")


def test_store_description_requires_its_own_rights_basis():
    from radar_salud.global_feed_discovery import validate_feed_config
    feed = copy.deepcopy(next(f for f in CONFIG["feeds"] if f["id"] == "uk_dhsc"))
    feed["rights"].pop("description_basis")
    with pytest.raises(ValueError, match="description_basis"):
        validate_feed_config(feed)


def test_publisher_summary_rules():
    from radar_salud.global_feed_discovery import publisher_summary
    assert publisher_summary("") == (None, False) and publisher_summary(None) == (None, False)
    assert publisher_summary("<p>Short &amp; plain.</p>") == ("Short & plain.", False)
    assert publisher_summary("x " * 700) == (None, False)  # a body, not a summary
    text = "First sentence is long enough to be kept as the summary of this item. " * 3 + "y" * 200
    cut, truncated = publisher_summary(text)
    # Cut at a sentence end: still marked with "…" so the reader knows text follows.
    assert truncated and len(cut) <= 300 and cut.endswith(". …") and cut.count("…") == 1


def test_ninety_day_single_inbox_ordered_by_date_and_deduplicated_across_sources():
    assert CONFIG["daily_feed"]["window_days"] == 90 and CONFIG["daily_feed"]["retention_days"] >= 90
    payload = build(feed_payload(), {}, CONFIG, None, AS_OF)
    assert not any(c["source"] in ("uk_dhsc", "uk_mhra") for c in payload["items"])
    on = govuk_on()
    payload = build(feed_payload(on), {}, on, None, AS_OF)
    assert payload["window_days"] == 90 and payload["retention_days"] == 90
    days = [c["published_at"] for c in payload["items"]]
    assert days == sorted(days, reverse=True)
    titles = [c["title"] for c in payload["items"]]
    # Same FDA URL in two routes -> one card; same GOV.UK story from DHSC and MHRA -> one card.
    assert titles.count("FDA Approves First Biosimilar for Treatment of Rare Blood Disorder") == 1
    scribes = [c for c in payload["items"] if "AI scribes rolled out across GP practices" in c["title"]]
    assert len(scribes) == 1 and payload["duplicates_merged"] >= 1
    assert {s["source"] for s in scribes[0].get("also_reported_by", [])} | {scribes[0]["source"]} == {"uk_dhsc", "uk_mhra"}
    # Cards from both new GOV.UK publishers reach the inbox with their OGL licence link.
    ogl = [c for c in payload["items"] if c["source"] in ("uk_dhsc", "uk_mhra")]
    assert ogl and all(c["rights_basis"]["license_label"] == "OGL v3.0" for c in ogl)


def _dcard(i, src, title, day, **extra):
    return {"id": i, "source": src, "source_label": src, "title": title, "url": "https://x/" + i, "published_at": day,
            "priority": 70, "description": None, **extra}


def test_title_dedup_needs_a_real_headline_and_a_short_gap():
    from radar_salud.global_daily_feed import dedupe
    same = _dcard("a", "uk_dhsc", "Press release: New funding for NHS hospitals announced", "2026-10-20")
    twin = _dcard("b", "uk_mhra", "Press release: New funding for NHS hospitals announced", "2026-10-22")
    late = _dcard("c", "ema", "Press release: New funding for NHS hospitals announced", "2026-10-30")
    short = [_dcard("d", "fda", "Recall", "2026-10-20"), _dcard("e", "cdc", "Recall", "2026-10-20")]
    kept, ledger = dedupe([same, twin, late] + short)
    assert [c["id"] for c in kept] == ["a", "d", "e", "c"] and len(ledger) == 1
    assert ledger[0]["reason"] == "cross_source_same_title" and kept[0]["also_reported_by"][0]["source"] == "uk_mhra"


def test_govuk_document_type_prefixes_are_part_of_the_dedup_key():
    from radar_salud.global_daily_feed import dedupe
    cards = [_dcard("g", "uk_dhsc", "Guidance: Adult social care charging reform", "2026-10-20"),
             _dcard("o", "uk_dhsc", "Consultation outcome: Adult social care charging reform", "2026-10-20"),
             _dcard("p", "uk_mhra", "Adult social care charging reform", "2026-10-21")]
    kept, ledger = dedupe(cards)
    assert {c["id"] for c in kept} == {"g", "o", "p"} and ledger == []


def test_same_source_same_title_duplicates_are_recorded_not_silently_dropped():
    from radar_salud.global_daily_feed import dedupe
    first = _dcard("a1", "fda", "FDA Roundup: October 24, 2026 regulatory actions", "2026-10-24")
    again = _dcard("a2", "fda", "FDA Roundup: October 24, 2026 regulatory actions", "2026-10-25")
    kept, ledger = dedupe([first, again])
    assert [c["id"] for c in kept] == ["a1"] and "also_reported_by" not in kept[0]
    assert ledger == [{"kept_id": "a1", "merged_id": "a2", "source": "fda", "url": "https://x/a2", "published_at": "2026-10-25",
                       "title": again["title"], "reason": "same_source_same_title"}]
    # The ledger reaches the payload next to the count.
    payload = build(feed_payload(govuk_on()), {}, govuk_on(), None, AS_OF)
    assert payload["duplicates_merged"] == len(payload["duplicates"]) >= 1


def test_visible_card_keeps_its_id_when_an_earlier_twin_arrives_later():
    from radar_salud.global_daily_feed import dedupe
    shown = _dcard("shown", "uk_dhsc", "Press release: New funding for NHS hospitals announced", "2026-10-22")
    earlier = _dcard("early", "uk_mhra", "Press release: New funding for NHS hospitals announced", "2026-10-21")
    kept, ledger = dedupe([shown, earlier], visible_ids={"shown"})
    assert [c["id"] for c in kept] == ["shown"] and kept[0]["also_reported_by"][0]["source"] == "uk_mhra"
    assert ledger[0]["kept_id"] == "shown" and ledger[0]["merged_id"] == "early"
    # Without a visible card the earliest one wins (first build).
    kept, _ = dedupe([dict(shown), dict(earlier)])
    assert [c["id"] for c in kept] == ["early"]
    # End to end: the GOV.UK card shown yesterday keeps its id when an earlier-dated twin arrives today.
    on = govuk_on()
    first = build(feed_payload(on), {}, on, None, AS_OF)
    shown = next(c for c in first["items"] if "AI scribes" in c["title"])
    row = copy.deepcopy(next(r for r in feed_payload(on)["items"] if r["source"] == "uk_mhra" and "AI scribes" in r["title"]))
    row.update(item_id="earlier-twin", url="https://www.gov.uk/government/news/ai-scribes-earlier-copy",
               published_at=(_day_minus(shown["published_at"], 1)))
    payload = build({"items": [row]}, {}, on, first, AS_OF)
    ids = {c["id"] for c in payload["items"]}
    assert shown["id"] in ids and "earlier-twin" not in ids
    kept = next(c for c in payload["items"] if c["id"] == shown["id"])
    assert any(a["url"].endswith("ai-scribes-earlier-copy") for a in kept["also_reported_by"])


def _day_minus(day, n):
    from datetime import timedelta
    return (date.fromisoformat(day) - timedelta(days=n)).isoformat()


def test_clean_strips_real_tags_first_and_decodes_entities_once():
    from radar_salud.global_feed_discovery import _clean, publisher_summary
    # Double-escaped text: markup layer decoded once, then the leftover text layer once (never re-parsed
    # as markup): readable, and the words between "<" and ">" are never lost.
    assert _clean("Children &amp;lt;5 years and adults &amp;gt;65 are at risk.") == "Children <5 years and adults >65 are at risk."
    assert publisher_summary("<p>Children &amp;lt;5 years and adults &amp;gt;65 are at risk.</p>") == ("Children <5 years and adults >65 are at risk.", False)
    assert _clean("A &amp;amp; B") == "A & B"
    # A decoded "<script>" from the text layer stays text (the UI escapes it once); it never drops words.
    assert _clean("Note &amp;lt;b&amp;gt;bold&amp;lt;/b&amp;gt; end") == "Note <b>bold</b> end"
    assert _clean("R&D & AT&T") == "R&D & AT&T"
    assert _clean("<p>Children &lt;5 years and adults &gt;65 are at risk.</p>") == "Children <5 years and adults >65 are at risk."
    assert _clean("Children <5 years and adults >65 are at risk.") == "Children <5 years and adults >65 are at risk."
    assert _clean("A &amp; B <b>bold</b><script>alert(1)</script> end") == "A & B bold end"
    assert publisher_summary("<p>Children &lt;5 years and adults &gt;65 are at risk.</p>") == ("Children <5 years and adults >65 are at risk.", False)


def test_truncated_summary_always_ends_with_an_ellipsis():
    from radar_salud.global_feed_discovery import publisher_summary
    sentence_cut, flag = publisher_summary("This first sentence is clearly long enough to be kept on its own as the cut point. " * 4)
    assert flag and sentence_cut.endswith("…") and len(sentence_cut) <= 300
    word_cut, flag = publisher_summary("word " * 100)
    assert flag and word_cut.endswith("…") and len(word_cut) <= 300
    assert publisher_summary("Short. Complete.") == ("Short. Complete.", False)


def test_ogl_cards_carry_the_licence_attribution_statement():
    on = govuk_on()
    payload = build(feed_payload(on), {}, on, None, AS_OF)
    ogl = [c for c in payload["items"] if c["source"] in ("uk_dhsc", "uk_mhra")]
    assert ogl
    for card in ogl:
        rb = card["rights_basis"]
        assert rb["basis"] == "uk_open_government_licence_v3" and rb["license_url"].startswith("https://www.nationalarchives.gov.uk/")
        assert rb["attribution"].startswith("Contains public sector information licensed under the Open Government Licence v3.0")
    # History cards get today's attribution too (re-gated with today's config).
    old = [dict(c, rights_basis={"license": "x"}) for c in ogl]
    again = build({"items": []}, {}, on, {"items": old}, AS_OF)
    assert again["items"] and all(c["rights_basis"]["attribution"].startswith("Contains public sector information") for c in again["items"])
    # While the GOV.UK feeds are off, their history leaves the inbox.
    assert build({"items": []}, {}, CONFIG, {"items": old}, AS_OF)["items"] == []


def test_medwatch_route_never_keeps_a_summary():
    fda = next(f for f in CONFIG["feeds"] if f["id"] == "fda")
    medwatch = next(r for r in fda["routes"] if r["section"] == "medwatch_safety_alerts")
    assert medwatch["store_description"] is False
    raw = (b'<?xml version="1.0"?><rss version="2.0"><channel><title>MedWatch</title><item>'
           b'<title>Acme Pharma Issues Voluntary Nationwide Recall of Metformin Extended-Release Tablets</title>'
           b'<link>https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/acme-pharma-issues-voluntary-recall</link>'
           b'<pubDate>Mon, 26 Oct 2026 10:00:00 EDT</pubDate><description>Company announcement text.</description></item></channel></rss>')
    rows = parse_feed(raw, medwatch, fda, AS_OF)
    assert rows[0]["title"] and "description" not in rows[0]
    press = next(r for r in fda["routes"] if r["section"] == "press_releases")
    assert parse_feed(raw, press, fda, AS_OF)[0]["description"] == "Company announcement text."
    from radar_salud.global_daily_feed import description_allowed
    assert description_allowed(fda, ["press_releases"]) and not description_allowed(fda, ["medwatch_safety_alerts"])
    assert description_allowed(fda, ["press_releases", "medwatch_safety_alerts"]) and not description_allowed(fda, [])


def test_history_drops_a_summary_whose_right_was_withdrawn():
    first = build(feed_payload(), {}, CONFIG, None, AS_OF)
    with_desc = [c for c in first["items"] if c["description"]]
    assert with_desc
    withdrawn = copy.deepcopy(CONFIG)
    for feed in withdrawn["feeds"]:
        feed["store_description"] = False
    later = build({"items": []}, {}, withdrawn, first, AS_OF)
    assert later["items"] and all(c["description"] is None and c["description_truncated"] is False for c in later["items"])
    # A summary withheld for the card's route (e.g. MedWatch) is dropped as well.
    fda_card = dict(with_desc[0], source="fda", sections=["medwatch_safety_alerts"], url="https://www.fda.gov/x",
                    title="FDA finalizes guidance on artificial intelligence in clinical trials")
    kept = build({"items": []}, {}, govuk_on(), {"items": [fda_card]}, AS_OF)["items"]
    assert kept and kept[0]["description"] is None
    # With the MedWatch route off (Dirección 28-oct 09:58), its history card leaves the inbox.
    assert build({"items": []}, {}, CONFIG, {"items": [fda_card]}, AS_OF)["items"] == []


# Dirección 28-oct 09:58: safety alerts and recalls are one-offs for Chile -> all excluded; no "always include" rule.
MHRA_TITLES = {
    "Class 2 Medicines Recall: Zentiva Pharma UK Limited, Diazepam 10mg Tablets, EL(26)A/41": "publisher_routine_document_type",
    "Class 3 Medicines Recall: Accord Healthcare Ltd, Amlodipine 5mg Tablets, EL(26)A/42": "publisher_routine_document_type",
    "Class 4 Medicines Defect Information: Bristol Laboratories Ltd, Lansoprazole 30mg Capsules, EL(26)A/43": "publisher_routine_document_type",
    "Field Safety Notices: 19 to 23 October 2026": "publisher_routine_document_type",
    "Field Safety Notice: Philips infusion pump software update": "publisher_routine_document_type",
    # No executive segment keyword: excluded by the base rule before the Global-interest gate (still out).
    "National Patient Safety Alert: Valproate: organisations to implement new safety measures (NatPSA/2026/007/MHRA)": "no_segment_match",
    "Medical safety alert: Insulin pens: risk of incorrect dosing when the needle is not attached": "safety_alert_or_recall",
    "Class 1 Medicines Recall: Sandoz Limited, Co-amoxiclav 625mg Tablets, EL(26)A/44": "safety_alert_or_recall",
}


def test_mhra_recalls_field_safety_notices_and_safety_alerts_are_all_excluded():
    entries = "".join(
        f'<entry><id>https://www.gov.uk/drug-device-alerts/a{i}</id><updated>2026-10-26T09:00:00+00:00</updated>'
        f'<link rel="alternate" type="text/html" href="https://www.gov.uk/drug-device-alerts/a{i}"/>'
        f'<title>{t.replace("&", "&amp;")}</title></entry>' for i, t in enumerate(MHRA_TITLES))
    raw = ('<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>MHRA</title>' + entries + '</feed>').encode()
    config = govuk_on()
    config["feeds"] = [f for f in config["feeds"] if f["id"] == "uk_mhra"]
    assert "include_title_patterns" not in config["feeds"][0]

    class Client:
        def fetch(self, url):
            return raw, {"body_sha256": "x", "fetched_at": "2026-10-28T10:00:00+00:00", "http_status": 200, "tls_verified": True}

    items, failures, _ = collect_feeds(config, Client(), AS_OF)
    got = {r["title"]: r["classification"]["category"] for r in items}
    assert got == MHRA_TITLES, got
    assert not any(r["classification"]["relevant"] for r in items) and all(r["status"] == "rejected" for r in items)
    assert build({"items": items}, {}, config, None, AS_OF)["items"] == []


def test_rights_evidence_matches_what_was_checked():
    feeds = {f["id"]: f for f in CONFIG["feeds"]}
    mhra = feeds["uk_mhra"]["rights"]
    assert "https://www.gov.uk/government/organisations/medicines-and-healthcare-products-regulatory-agency" not in mhra["evidence_urls"]
    assert "MHRA organisation page itself was NOT read" in mhra["verified_how"] and "robots VERIFIED" in mhra["verified_how"]
    for fid in ("uk_dhsc", "uk_mhra"):
        assert "feeds NOT fetched live" in feeds[fid]["rights"]["verified_how"]
    fda = feeds["fda"]["rights"]
    assert fda["website_policies_verified"] is False and "NOT verified" in fda["verified_how"]


def test_truncated_summaries_are_labelled_excerpts_and_rights_basis_never_claims_unaltered():
    """Review 28-oct (point 3): every cut summary is an excerpt; CC BY (ECDC, EC) and EMA bases say so."""
    from radar_salud.global_daily_feed import _card
    common = dict(item_id="x", source="ecdc", label="ECDC", attribution="ECDC", kind_es="", title="T", url="https://x",
                  published_at="2026-10-27", segments=[], priority=0, bylines=[], rights_basis={}, as_of=AS_OF)
    cut = _card(description="First part …", description_truncated=True, **common)
    assert cut["description_truncated"] is True and cut["description_source"] == "publisher_feed_summary_excerpt"
    whole = _card(description="Whole summary.", description_truncated=False, **common)
    assert whole["description_source"] == "publisher_feed_summary_verbatim"
    feeds = {f["id"]: f for f in CONFIG["feeds"]}
    for source in ("ecdc", "ec_health", "ema"):
        basis = feeds[source]["rights"]["description_basis"]
        assert "unaltered" not in basis and "(extracto)" in basis, (source, basis)
