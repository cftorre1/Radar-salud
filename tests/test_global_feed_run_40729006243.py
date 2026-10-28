"""First live run of the licensed Global feeds (28-oct-2026 18:11 UTC, run 40729006243).

Recorded on origin/staging (data/global_intelligence/feed_discovery.json): 29 cards (EMA 17, EC 8,
ECDC 3, The Conversation 1); FDA 20/20 entries rejected as link_outside_licensed_publisher_hosts
(the run did not record the host); CDC newsroom+MMWR HTTP 406; NIH HTTP 403. Titles below are the
real headlines of that run, used verbatim as relevance cases (Dirección 28-oct 09:58: trends only).
"""
import base64
import copy
import json
from datetime import date
from pathlib import Path

import pytest

from radar_salud.global_daily_feed import feed_cards
from radar_salud.global_discovery_common import FEED_HOSTS, CaptureClient
from radar_salud.global_feed_discovery import (_fold, classify_relevance, collect_feeds, parse_feed, resolve_feed_link,
                                               validate_feed_config)
from radar_salud.global_relevance import global_interest, source_rules
from scripts import discover_global_feeds

AS_OF = date(2026, 10, 28)
CONFIG = json.loads(Path("config/global_discovery.json").read_text())
FEEDS = {feed["id"]: feed for feed in CONFIG["feeds"]}
FDA = FEEDS["fda"]
FDA_FEED = "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml"
ARTICLE = "https://www.fda.gov/news-events/press-announcements/fda-launches-pilot-program"


def _jwt(payload):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return enc({"alg": "HS256"}) + "." + enc(payload) + ".c2lnbmF0dXJl"


# --- FDA link hosts -------------------------------------------------------------------------------

@pytest.mark.parametrize("link,expected,via", [
    (ARTICLE, ARTICLE, None),
    ("/news-events/press-announcements/fda-launches-pilot-program", ARTICLE, None),  # relative to the feed
    ("http://www.fda.gov/news-events/press-announcements/fda-launches-pilot-program", ARTICLE, None),  # http upgraded
    ("https://fda.gov/news-events/press-announcements/fda-launches-pilot-program", ARTICLE, None),  # alias -> www
    ("http://fda.gov/news-events/press-announcements/fda-launches-pilot-program?utm_source=rss", ARTICLE, None),
    # GovDelivery click tracking: the official target is written in the link itself (decoded, never fetched).
    ("https://links-1.govdelivery.com/CL0/https:%2F%2Fwww.fda.gov%2Fnews-events%2Fpress-announcements%2Ffda-launches-pilot-program%3Futm_medium=email%26utm_source=govdelivery/1/0100019a-abc/XyZ=401",
     ARTICLE, "links-1.govdelivery.com"),
    ("https://lnks.gd/l/" + _jwt({"buletin_link_id": "101", "uri": "bp2:click", "url": ARTICLE + "?utm_medium=email"}) + "/s/1/br/1",
     ARTICLE, "lnks.gd"),
])
def test_fda_links_resolve_only_to_official_fda_articles(link, expected, via):
    assert resolve_feed_link(link, FDA_FEED, FDA, set(FDA["allowed_link_hosts"])) == (expected, via)


@pytest.mark.parametrize("link", [
    "https://content.govdelivery.com/accounts/USFDA/bulletins/3a1b2c4",  # bulletin hosted by GovDelivery, not fda.gov
    "https://links-1.govdelivery.com/CL0/opaque-token/1/abc",  # no decodable target
    "https://links-1.govdelivery.com/CL0/https:%2F%2Fevil.example%2Ffda.gov/1/abc",  # target off-host
    "https://lnks.gd/l/" + _jwt({"url": "https://www.fda.gov.evil.example/x"}) + "/s/1",
    "https://lnks.gd/l/" + _jwt({"url": "https://lnks.gd/l/nested"}) + "/s/1",  # one level only
    "https://lnks.gd/l/not-a-jwt",
    "http://links-1.govdelivery.com/CL0/https:%2F%2Fwww.fda.gov%2Fx/1/a",  # redirect hosts must be https
    "https://www.fda.gov:8443/news-events/x",
    "ftp://www.fda.gov/x",
    "https://www.hhs.gov/about/news/x",
])
def test_fda_rejects_everything_else(link):
    with pytest.raises(ValueError):
        resolve_feed_link(link, FDA_FEED, FDA, set(FDA["allowed_link_hosts"]))


def test_feed_config_rejects_unsafe_alias_or_redirect_hosts():
    bad = copy.deepcopy(FDA)
    bad["link_host_aliases"] = {"fda.gov": "evil.example"}
    with pytest.raises(ValueError, match="aliases"):
        validate_feed_config(bad)
    bad = copy.deepcopy(FDA)
    bad["redirect_link_hosts"] = ["www.fda.gov"]
    with pytest.raises(ValueError, match="redirect host"):
        validate_feed_config(bad)
    assert set(FDA["allowed_link_hosts"]) == {"www.fda.gov"}  # redirect/alias hosts are never fetchable hosts
    assert not set(FDA["redirect_link_hosts"]) & FEED_HOSTS and "fda.gov" not in FEED_HOSTS


def _rss(*links):
    items = "".join(f"<item><title>FDA launches pilot program {i}</title><link>{link}</link>"
                    f"<pubDate>Mon, 26 Oct 2026 10:00:00 EDT</pubDate></item>" for i, link in enumerate(links))
    return f"<?xml version='1.0'?><rss version='2.0'><channel><title>t</title>{items}</channel></rss>".encode()


class _Client:
    def __init__(self, body=b"", robots_error=None):
        self.body, self.robots_error, self.network_requests, self.hosts = body, robots_error, 0, FEED_HOSTS

    def check_robots(self, url):
        if self.robots_error:
            raise ValueError(self.robots_error)

    def fetch(self, url):
        return self.body, {"body_sha256": "x", "fetched_at": "2026-10-28T18:11:00+00:00", "http_status": 200, "tls_verified": True}


def _only(config, fid):
    config = copy.deepcopy(config)
    for feed in config["feeds"]:
        feed["enabled"] = feed["id"] == fid
    return config


def test_fda_entries_now_pass_and_any_rejection_records_its_host():
    rows = parse_feed(_rss("http://www.fda.gov/news-events/a", "https://content.govdelivery.com/accounts/USFDA/bulletins/1"),
                      FDA["routes"][0], FDA, AS_OF)
    assert rows[0]["url"] == "https://www.fda.gov/news-events/a" and rows[0]["published_at"] == "2026-10-26"
    assert rows[1]["status"] == "rejected" and rows[1]["raw_link_host"] == "content.govdelivery.com"
    items, failures, routes = collect_feeds(_only(CONFIG, "fda"), _Client(_rss("https://fda.gov/news-events/a", "https://evil.example/b")), AS_OF)
    assert [i["url"] for i in items] == ["https://www.fda.gov/news-events/a"]
    assert failures == [{"source": "fda", "section": "press_releases", "url": FDA_FEED, "error": "link_outside_licensed_publisher_hosts",
                         "rejected_entry": True, "raw_link_scheme": "https", "raw_link_host": "evil.example"}]
    assert routes["fda/press_releases"]["newest_entry"] == "2026-10-26"


# --- CDC 406 / NIH 403 ----------------------------------------------------------------------------

def test_fetch_failures_say_whether_robots_or_the_feed_failed():
    _, failures, routes = collect_feeds(_only(CONFIG, "cdc"), _Client(robots_error="http_406"), AS_OF)
    assert {f["stage"] for f in failures} == {"robots"} and {f["error"] for f in failures} == {"ValueError: http_406"}
    assert all(r["status"] == "error" for r in routes.values())
    _, failures, _ = collect_feeds(_only(CONFIG, "nih"), _Client(body=b"<html>Access Denied</html>"), AS_OF)
    assert failures[0]["stage"] == "parse"


class _Resp:
    def __init__(self, url, body):
        self.url, self.code, self.headers, self._body = url, 200, {"Content-Type": "text/plain"}, body

    def read(self, n):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_feed_client_sends_text_plain_for_robots_and_a_wildcard_for_feeds(tmp_path):
    client = CaptureClient(tmp_path, delay=0, hosts=FEED_HOSTS, accept=discover_global_feeds.FEED_ACCEPT,
                           robots_accept=discover_global_feeds.ROBOTS_ACCEPT)
    seen = []

    class Opener:
        def open(self, request, timeout):
            seen.append((request.full_url, request.get_header("Accept")))
            body = b"User-agent: *\nAllow: /\n" if request.full_url.endswith("robots.txt") else b"<rss/>"
            return _Resp(request.full_url, body)

    client.opener = Opener()
    client.fetch("https://tools.cdc.gov/api/v2/resources/media/132608.rss")
    assert seen[0] == ("https://tools.cdc.gov/robots.txt", "text/plain,*/*;q=0.1")
    assert seen[1][1].startswith("application/rss+xml") and seen[1][1].endswith("*/*;q=0.1")
    # WHO/PAHO collectors keep their historical headers (robots_accept unset).
    assert CaptureClient(tmp_path / "w", delay=0).robots_accept is None


# --- Relevance on the real headlines of run 40729006243 --------------------------------------------

def _cards(source, title, categories=()):
    feed = FEEDS[source]
    classification = classify_relevance(title, categories, default_segments=feed.get("default_segments", ()))
    interest = global_interest(title, categories, source=source, rules=source_rules(CONFIG, source))
    relevant = classification["relevant"] and interest["relevant"] and not any(
        __import__("re").search(p, _fold(title)) for p in feed.get("exclude_title_patterns", []))
    row = {"source": source, "title": title, "categories": list(categories), "url": "https://" + feed["allowed_link_hosts"][0] + "/x",
           "published_at": "2026-10-27", "status": "pending" if relevant else "rejected", "item_id": "i",
           "sections": [feed["routes"][0]["section"]], "classification": classification if relevant else {"relevant": False}}
    return feed_cards({"items": [row]}, CONFIG, AS_OF)[0]


SHOWN = [
    ("ema", "Women are missing from medicines development: EMA’s roadmap for change"),
    ("ema", "Clinical trial applications advice pilot becomes permanent"),
    ("ema", "Global regulators call for advancing alternatives to animal testing across the medicine lifecycle"),
    ("ema", "AMA and EMA issue joint guidance on Ebola vaccine development"),
    ("ec_health", "HTA Regulation - Commission selects first medical devices for joint clinical assessment"),
    ("ec_health", "Commission establishes the European Health Data Space Stakeholder Forum and Community"),
    ("ec_health", "Summary report OECD/EUPHA - Long COVID Policy Dialogue"),
    ("ec_health", "Health Technology Assessment: Updated procedural guidance for joint scientific consultations to include the role of patients"),
    ("ecdc", "Multi-model assessment of the impact of newborn RSV immunisation on hospitalisation burden in the EU/EEA"),
    ("the_conversation", "AI chatbots can be a valuable health resource for older adults – if they embrace ‘informed skepticism’"),
    ("the_conversation", "Plans with cheaper premiums are risky business for Americans seeking lower healthcare costs"),
    ("the_conversation", "1 in 4 Pennsylvanians say they paid out of pocket for their annual checkup. Why isn’t insurance covering these visits?"),    # Review 28-oct: private equity buying up care providers is a financing trend (was hidden).
    ("the_conversation", "Private equity is buying up more methadone clinics – access to the lifesaving drug isn’t getting easier"),
]
HIDDEN = [
    # EMA single-product EPARs (17 of the 29 cards were EMA; 6 were these): "report" is not a study.
    ("ema", "Human medicines European public assessment report (EPAR): Rasonque, Daraxonrasib, Status: Opinion"),
    ("ema", "Human medicines European public assessment report (EPAR): Foundayo, Orforglipron, Status: Opinion"),
    ("ema", "Human medicines European public assessment report (EPAR): Fovlussea, ranibizumab, Ophthalmologicals, Status: Opinion"),
    ("ema", "EMA recommends authorisation of Rasonque for metastatic pancreatic cancer"),
    ("ema", "Meeting highlights from the Committee for Medicinal Products for Human Use (CHMP) 12-15 October 2026"),
    ("ema", "EMA Management Board: highlights of September 2026 meeting"),
    ("ema", "Advice on ‘end-of-year’ submission dates for type I variations in 2026"),
    ("ec_health", "Registration - EUHPP Live Webinar: What shapes Digital Health adoption? (19 November 2026, 11.00-12.30 CET)"),
    ("ec_health", "Agenda - 105th meeting of the Pharmaceutical Committee (9 November 2026)"),
    ("ec_health", "SCCS - Final Opinion on the safety of Heliotropin used in cosmetic products"),
    ("ecdc", "Communicable disease threats report, 10 - 16 October, week 42"),
    ("ecdc", "ECDC to deploy experts as Ebola cases emerge in Kenya and Nigeria"),
    ("the_conversation", "I teach doctors how to interpret test results – and the labels ‘normal’ and ‘abnormal’ often hide what matters"),
    ("the_conversation", "When abortion and surrogacy law collide, contracts can’t answer the hardest questions"),
    ("kff_health_news", "Hospital Beds for the Nation’s Sickest Kids Are Disappearing"),
]


@pytest.mark.parametrize("source,title", SHOWN)
def test_trend_headlines_from_the_run_are_shown(source, title):
    assert len(_cards(source, title)) == 1, title


@pytest.mark.parametrize("source,title", HIDDEN)
def test_routine_headlines_from_the_run_are_not_shown(source, title):
    assert _cards(source, title) == [], title
