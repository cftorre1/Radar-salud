"""Licensed Global feeds and WHO/PAHO activation guard.

Fixtures in tests/fixtures/global_feeds are CONSTRUCTED, not live captures: the sandbox had
no network route to the publishers on 2026-10-27. They follow the standard WordPress RSS 2.0
output of kffhealthnews.org/feed/ (dc:creator, category, guid isPermaLink=false,
content:encoded) and the Drupal RSS 2.0 output of ema.europa.eu / fda.gov. Replace them
with a recorded capture from the first live run (work/global-runtime-captures/feeds).
"""
import copy
import json
from datetime import date
from pathlib import Path

import pytest

from radar_salud.global_discovery_common import FEED_HOSTS, HOSTS, CaptureClient, canonical_url
from radar_salud.global_feed_discovery import classify_relevance, collect_feeds, feed_day, parse_feed, validate_feed_config
from scripts import discover_global_feeds
from scripts.discover_global_sources import apply_publication_activation, publication_activation_decision

AS_OF = date(2026, 10, 27)
FIX = Path("tests/fixtures/global_feeds")
CONFIG = json.loads(Path("config/global_discovery.json").read_text())
FEEDS = {feed["id"]: feed for feed in CONFIG["feeds"]}
BODIES = {
    "https://kffhealthnews.org/feed/": "kff_feed.xml",
    "https://kffhealthnews.org/topics/health-industry/feed/": "kff_health_industry_feed.xml",
    "https://www.ema.europa.eu/en/news.xml": "ema_news.xml",
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml": "fda_press.xml",
}


class FeedClient:
    def __init__(self, fail=()):
        self.network_requests = 0
        self.fail = set(fail)

    def fetch(self, url):
        self.network_requests += 1
        if url in self.fail or url not in BODIES:
            raise ValueError("http_404")
        raw = (FIX / BODIES[url]).read_bytes()
        return raw, {"body_sha256": "sha-" + BODIES[url], "fetched_at": "2026-10-27T12:00:00+00:00", "http_status": 200, "tls_verified": True}


def kff_rows():
    feed = FEEDS["kff_health_news"]
    return parse_feed((FIX / "kff_feed.xml").read_bytes(), feed["routes"][0], feed, AS_OF)


def test_every_feed_declares_a_rights_basis_that_permits_metadata_and_link_only():
    assert {f["id"] for f in CONFIG["feeds"]} == {"kff_health_news", "ema", "fda", "cdc", "nih", "federal_register_cms", "ecdc", "ec_health", "the_conversation", "uk_dhsc", "uk_mhra"}
    for feed in CONFIG["feeds"]:
        validate_feed_config(feed)
        assert feed["rights"]["permitted_use"] == "metadata_title_link_byline_only"
        assert set(feed["allowed_link_hosts"]) <= FEED_HOSTS
        assert all(route["url"].startswith("https://") for route in feed["routes"])
    assert FEEDS["kff_health_news"]["rights"]["license"] == "CC BY-NC-ND 4.0"
    assert FEEDS["kff_health_news"]["attribution"] == "KFF Health News"
    kff = FEEDS["kff_health_news"]["rights"]
    assert kff["basis"] == "headline + link only; CC BY-NC-ND 4.0 covers attribution; ask KFF before paid/commercial use"
    assert kff["paid_tier_requires_publisher_confirmation"] is True and not kff["paid_tier_confirmation"]
    ema = FEEDS["ema"]["rights"]
    assert "EMA information should not be displayed alongside advertising" in ema["restrictions"]
    assert "https://www.ema.europa.eu/en/about-us/legal-notice" in ema["evidence_urls"]
    assert not any("/hu/" in url for url in ema["evidence_urls"])
    registry = json.loads((Path(__file__).resolve().parents[1] / "config/global_source_candidates.json").read_text())
    excluded = {row["name"].split(" ")[0] for row in registry["sources"] if row["status"] == "rejected"}
    assert "STAT" in excluded and CONFIG["reuters"]["enabled"] is False


def test_feed_without_rights_or_with_forbidden_automated_access_is_refused():
    feed = copy.deepcopy(FEEDS["kff_health_news"])
    feed["rights"].pop("license")
    with pytest.raises(ValueError, match="rights basis incomplete"):
        validate_feed_config(feed)
    feed = copy.deepcopy(FEEDS["kff_health_news"])
    feed["rights"]["automated_access"] = "prohibited_by_terms"
    with pytest.raises(ValueError, match="do not permit"):
        validate_feed_config(feed)


def test_feed_hosts_never_widen_who_paho_identity_checks(tmp_path):
    with pytest.raises(ValueError):
        canonical_url("https://kffhealthnews.org/news/x/")
    assert canonical_url("https://kffhealthnews.org/news/x/?utm_source=rss", hosts=FEED_HOSTS) == "https://kffhealthnews.org/news/x/"
    assert not FEED_HOSTS & HOSTS
    client = CaptureClient(tmp_path, hosts=FEED_HOSTS, delay=0)
    with pytest.raises(ValueError, match="unapproved"):
        client.fetch("https://www.who.int/news")


def test_kff_wordpress_rss_keeps_title_link_date_byline_and_never_the_body():
    rows = {r["guid"]: r for r in kff_rows()}
    first = rows["https://kffhealthnews.org/?p=2000001"]
    assert first["title"] == "Insurers’ AI Tools Deny Prior Authorization Requests at Scale, Doctors Say"
    assert first["url"] == "https://kffhealthnews.org/news/article/insurers-ai-prior-authorization-denials/"
    assert first["published_at"] == "2026-10-26" and first["bylines"] == ["Jane Doe"]
    assert first["attribution"] == "KFF Health News" and first["categories"] == ["Health Industry", "Insurance"]
    assert first["body_stored"] is False
    serialized = json.dumps(list(rows.values()))
    assert "must never be stored" not in serialized and "Excerpt." not in serialized
    assert rows["https://kffhealthnews.org/?p=2000002"]["bylines"] == ["John Roe", "Ann Poe"]  # feed order
    # Publisher's own offset day is kept (08:00 -0400 stays 21 Oct).
    assert rows["https://kffhealthnews.org/?p=2000006"]["published_at"] == "2026-10-21"
    assert rows["https://kffhealthnews.org/?p=2000008"]["published_at"] is None
    assert rows["https://kffhealthnews.org/?p=2000008"]["publication_date_error"] == "future_feed_publication_date"
    off = rows["https://kffhealthnews.org/?p=2000007"]
    assert off["status"] == "rejected" and off["reason"] == "link_outside_licensed_publisher_hosts" and off["url"] is None


@pytest.mark.parametrize("body,error", [
    (b"<html><body>Just a moment...</body></html>", "not_a_feed_document"),
    (b"<?xml version='1.0'?><!DOCTYPE x [<!ENTITY a 'b'>]><rss/>", "doctype_or_entity"),
    # A padded prolog (long comment / PIs past any fixed head window) cannot hide a DOCTYPE.
    (b"<?xml version='1.0'?><!--" + b"x" * 9000 + b"--><?pi a?>\n<!DOCTYPE x [<!ENTITY a 'b'>]><rss/>", "doctype_or_entity"),
    ("\ufeff<?xml version='1.0'?>".encode() + b" " * 8000 + b"<!ENTITY a 'b'><rss/>", "doctype_or_entity"),
    (b"<rss><channel><item>", "xml_parse_error"),
    (b"<rss version='2.0'></rss>", "rss_channel_missing"),
])
def test_challenge_pages_entities_and_truncated_feeds_fail_closed(body, error):
    feed = FEEDS["kff_health_news"]
    with pytest.raises(ValueError, match=error):
        parse_feed(body, feed["routes"][0], feed, AS_OF)


def test_atom_and_rfc822_timezone_names_are_supported():
    feed = FEEDS["fda"]
    rows = parse_feed((FIX / "atom_sample.xml").read_bytes(), feed["routes"][0], feed, AS_OF)
    assert rows[0]["title"] == "Telehealth & digital health rules extended"
    assert rows[0]["published_at"] == "2026-10-24" and rows[0]["categories"] == ["Digital Health"]
    assert feed_day("Mon, 26 Oct 2026 15:12:00 EDT", AS_OF) == ("2026-10-26", None)
    assert feed_day("not a date", AS_OF) == (None, "invalid_feed_publication_date")
    assert feed_day("", AS_OF) == (None, "missing_feed_publication_date")


@pytest.mark.parametrize("title,segments", [
    ("Insurers' AI Tools Deny Prior Authorization Requests", {"payers", "ai_in_health"}),
    ("Hospital Mergers Drive Up Prices for Employers", {"providers"}),
    ("GLP-1 Drug Costs Strain State Medicaid Budgets", {"payers", "pharma"}),
    ("Ransomware Attack Disrupts Electronic Health Records at Clinics", {"healthtech", "providers"}),
    ("FDA issues new rule on laboratory-developed tests", {"regulation"}),
])
def test_relevance_segments_for_chilean_health_executives(title, segments):
    result = classify_relevance(title)
    assert result["relevant"] and segments <= set(result["segments"])
    assert result["ai_gate"] == {"invoked": False, "reason": "paid_ai_calls_contract_0"}
    assert result["chile_transfer"] == "hypothesis_only"


@pytest.mark.parametrize("title,category", [
    ("KFF Health News' 'What the Health?': Open Enrollment Begins", "podcast_or_multimedia"),
    ("Morning Briefing: Hurricane Recovery, Local Elections", "newsletter_digest"),
    ("A Small Town Mourns Its Beloved Diner", "no_segment_match"),
    ("FDA Warns Consumers Not to Use Certain Tattoo Inks", "out_of_scope_consumer_product"),
    ("Event: stakeholder registration open for annual conference", "institutional_routine"),
])
def test_irrelevant_items_are_excluded_deterministically(title, category):
    result = classify_relevance(title, default_segments=["regulation"] if "FDA" in title or "Event" in title else [])
    assert not result["relevant"] and result["category"] == category and result["materiality"] == "excluded"


def test_drug_recall_is_not_excluded_as_consumer_product():
    assert classify_relevance("FDA announces recall of contaminated insulin pens")["relevant"]


def test_collect_feeds_merges_routes_excludes_noise_and_keeps_window():
    items, failures, routes = collect_feeds(CONFIG, FeedClient(), AS_OF)
    by_title = {r["title"]: r for r in items}
    merged = by_title["Hospital Mergers Drive Up Prices for Employers, Study Finds"]
    assert merged["sections"] == ["all", "health_industry"] and len(merged["index_evidence"]) == 2
    assert "Private Equity" in merged["categories"]
    assert "Old Medicare Story Outside Window" not in by_title
    assert by_title["Morning Briefing: Hurricane Recovery, Local Elections"]["status"] == "rejected"
    assert by_title["A Small Town Mourns Its Beloved Diner"]["status"] == "rejected"
    assert by_title["Future-Dated Embargoed Item"]["status"] == "pending"
    chmp = by_title["Meeting highlights from the Committee for Medicinal Products for Human Use (CHMP) 19-22 October 2026"]
    # Dirección 28-oct 09:58: routine committee highlights and FDA roundups are not Global interest (source rules).
    for routine in (chmp, by_title["FDA Roundup: October 22, 2026"]):
        assert routine["classification"]["relevant"] is False and routine["status"] == "rejected"
        assert routine["classification"]["category"] == "source_rule_exclusion" and routine["global_interest"]["relevant"] is False
    assert by_title["FDA Warns Consumers Not to Use Certain Tattoo Inks"]["status"] == "rejected"
    assert all(r["publication_ready"] is False and r["content_use"] == "metadata_and_link_only" for r in items)
    # EMA new-medicines fixture missing -> technical failure, never silent success.
    assert any(f["source"] == "ema" and f["section"] == "new_human_medicines" for f in failures)
    assert routes["ema/new_human_medicines"]["status"] == "error"
    assert any(f.get("rejected_entry") for f in failures)
    # KFF (CC BY-NC-ND) items are held out of paid tiers until KFF confirms; FDA/EMA are not.
    assert merged["paid_tier_eligible"] is False and merged["paid_tier_hold"].startswith("publisher_confirmation")
    assert chmp["paid_tier_eligible"] is True and "paid_tier_hold" not in chmp


def test_feed_run_writes_discovery_health_and_never_publishes(tmp_path):
    for relative in ("config/global_discovery.json",):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(json.dumps(CONFIG))
    for relative in ("data/source_health.json", "web/data/source_health.json", "web/data/product.json"):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(json.dumps({"sources": {"local": {"name": "x"}, "global_who": {"name": "WHO"}}}))
    payload = discover_global_feeds.run(tmp_path, tmp_path / "captures", AS_OF, "feed-test", client=FeedClient())
    assert payload["paid_ai_calls"] == 0 and payload["publication_count"] == 0 and payload["body_stored"] is False
    kff = payload["source_health"]["kff_health_news"]
    assert kff["technical_status"] == "ok" and kff["publication_activation"] is False and kff["published"] == 0
    assert kff["coverage_completeness"] == "feed_window_only_not_archive" and kff["rights"]["license"] == "CC BY-NC-ND 4.0"
    assert payload["source_health"]["ema"]["technical_status"] == "error"
    candidates = payload["editorial_candidates"]
    assert candidates and all(c["publication_ready"] is False and c["status"] == "pending_editorial" for c in candidates)
    assert all(c["attribution"] for c in candidates)
    health = json.loads((tmp_path / "web/data/product.json").read_text())["sources"]
    assert health["local"] == {"name": "x"} and health["global_who"] == {"name": "WHO"}
    assert health["global_kff_health_news"]["discovery_scope"] == "global_intelligence"
    ledger = json.loads((tmp_path / "data/global_intelligence/feed_ledger.json").read_text())
    assert [r["run_id"] for r in ledger["runs"]] == ["feed-test"]


# --- WHO/PAHO publication activation guard (Dirección 27-oct) ---------------------------------

POLICY = CONFIG["publication_activation_policy"]


def ok(checked, contract="C"):
    return {"checked_at": checked, "coverage_completeness": "complete", "technical_status": "ok",
            "source_quality_disposition": "pass_data", "coverage_contract_id": contract}


def run_row(run_id, health, mode="live_discovery", reused=0):
    return {"run_id": run_id, "mode": mode, "capture_reuse": {"reused_url_count": reused}, "sources": {"paho": health}}


def test_activation_requires_two_consecutive_successful_daily_live_runs():
    ledger = {"runs": [run_row("d1", ok("2026-10-28T10:40:00+00:00"))]}
    decision = publication_activation_decision(ledger, "paho", ok("2026-10-29T10:35:00+00:00"), "d2", "live_discovery", POLICY, "C")
    assert decision["activated"] and decision["evidence_run_ids"] == ["d1", "d2"]
    assert "editorial_approval" in decision["publication_still_requires"]


@pytest.mark.parametrize("ledger_rows,current,mode,reason", [
    ([], ok("2026-10-29T10:35:00+00:00"), "live_discovery", "awaiting_second_consecutive_successful_daily_run"),
    # Back-to-back runs on the same day never prove daily cadence.
    ([run_row("d1", ok("2026-10-29T06:00:00+00:00"))], ok("2026-10-29T10:35:00+00:00"), "live_discovery", "awaiting_second_consecutive_successful_daily_run"),
    # A gap longer than two days is not consecutive.
    ([run_row("d1", ok("2026-10-25T10:00:00+00:00"))], ok("2026-10-29T10:35:00+00:00"), "live_discovery", "missed_day_breaks_consecutive_sequence"),
    # A missed day (≈47 h, inside the old 48 h window) breaks the sequence: max gap is 30 h.
    ([run_row("d1", ok("2026-10-27T11:40:00+00:00"))], ok("2026-10-29T10:35:00+00:00"), "live_discovery", "missed_day_breaks_consecutive_sequence"),
    # A failed run without checked_at (placed by generated_at) breaks the sequence.
    ([run_row("d1", ok("2026-10-28T10:40:00+00:00")),
      dict(run_row("x", {"technical_status": "error"}), generated_at="2026-10-28T22:40:00+00:00")],
     ok("2026-10-29T10:35:00+00:00"), "live_discovery", "failed_live_run_since_previous_daily_success"),
    # ...and so does a live_resume run in between, even if its coverage looked complete.
    ([run_row("d1", ok("2026-10-28T10:40:00+00:00")), run_row("r", ok("2026-10-28T22:40:00+00:00"), mode="live_resume")],
     ok("2026-10-29T10:35:00+00:00"), "live_discovery", "failed_live_run_since_previous_daily_success"),
    # A failed live run in between resets the sequence.
    ([run_row("d1", ok("2026-10-28T10:40:00+00:00")), run_row("x", dict(ok("2026-10-28T22:40:00+00:00"), technical_status="error"))],
     ok("2026-10-29T10:35:00+00:00"), "live_discovery", "failed_live_run_since_previous_daily_success"),
    # Coverage contract change invalidates the prior success.
    ([run_row("d1", ok("2026-10-28T10:40:00+00:00", contract="OLD"))], ok("2026-10-29T10:35:00+00:00"), "live_discovery", "failed_live_run_since_previous_daily_success"),
    # Reused captures never count; projection replays are ignored (not runs).
    ([run_row("d1", ok("2026-10-28T10:40:00+00:00"), reused=12)], ok("2026-10-29T10:35:00+00:00"), "live_discovery", "failed_live_run_since_previous_daily_success"),
    ([run_row("p", ok("2026-10-28T10:40:00+00:00"), mode="projection_replay")], ok("2026-10-29T10:35:00+00:00"), "live_discovery", "awaiting_second_consecutive_successful_daily_run"),
    ([run_row("d1", ok("2026-10-28T10:40:00+00:00"))], ok("2026-10-29T10:35:00+00:00"), "live_resume", "current_run_not_successful_live_complete"),
    ([run_row("d1", ok("2026-10-28T10:40:00+00:00"))], dict(ok("2026-10-29T10:35:00+00:00"), coverage_completeness="incomplete"), "live_discovery", "current_run_not_successful_live_complete"),
])
def test_activation_fails_closed(ledger_rows, current, mode, reason):
    decision = publication_activation_decision({"runs": ledger_rows}, "paho", current, "d2", mode, POLICY, "C")
    assert not decision["activated"] and decision["reason"] == reason


def test_same_day_success_neither_counts_nor_breaks_and_window_is_22_to_30h():
    ledger = {"runs": [run_row("d1", ok("2026-10-28T10:40:00+00:00")), run_row("d1b", ok("2026-10-28T16:00:00+00:00"))]}
    decision = publication_activation_decision(ledger, "paho", ok("2026-10-29T10:35:00+00:00"), "d2", "live_discovery", POLICY, "C")
    assert decision["activated"] and decision["evidence_run_ids"] == ["d1", "d2"]
    assert POLICY["paho"]["max_gap_seconds"] == 30 * 3600 and POLICY["paho"]["min_gap_seconds"] == 22 * 3600
    assert POLICY["paho"]["revoke_after_seconds"] == 48 * 3600


def test_activation_is_revoked_when_last_success_is_older_than_48h_and_must_be_re_earned(tmp_path):
    config = {"publication_activation_policy": POLICY}
    ledger = {"runs": [run_row("d1", ok("2026-10-28T10:40:00+00:00"))]}
    first = {"paho": ok("2026-10-29T10:35:00+00:00"), "who": dict(ok("2026-10-29T10:35:00+00:00"), technical_status="error")}
    apply_publication_activation(tmp_path, first, ledger, "d2", "live_discovery", config, False)
    assert first["paho"]["publication_activation"] is True
    ledger["runs"].append(run_row("d2", first["paho"]))
    # Three days without a successful run: a single fresh success does not restore the flag.
    stale = {"paho": ok("2026-11-01T10:35:00+00:00"), "who": dict(first["who"])}
    apply_publication_activation(tmp_path, stale, ledger, "d3", "live_discovery", config, False)
    assert stale["paho"]["publication_activation"] is False
    assert stale["paho"]["publication_activation_revoked_reason"] == "no_successful_live_run_within_48h"
    record = json.loads((tmp_path / "data/global_intelligence/publication_activation.json").read_text())
    assert "paho" not in record["sources"] and record["revoked"][0]["evidence_run_ids"] == ["d1", "d2"]
    # Two fresh consecutive runs re-earn it.
    ledger["runs"].append(run_row("d3", stale["paho"]))
    fresh = {"paho": ok("2026-11-02T10:30:00+00:00"), "who": dict(first["who"])}
    apply_publication_activation(tmp_path, fresh, ledger, "d4", "live_discovery", config, False)
    assert fresh["paho"]["publication_activation"] is True
    assert fresh["paho"]["publication_activation_decision"]["earned_evidence_run_ids"] == ["d3", "d4"]


def test_activation_is_revoked_on_staleness_even_when_the_current_run_fails(tmp_path):
    config = {"publication_activation_policy": POLICY}
    ledger = {"runs": [run_row("d1", ok("2026-10-28T10:40:00+00:00"))]}
    first = {"paho": ok("2026-10-29T10:35:00+00:00"), "who": dict(ok("2026-10-29T10:35:00+00:00"), technical_status="error")}
    apply_publication_activation(tmp_path, first, ledger, "d2", "live_discovery", config, False)
    late_fail = {"paho": dict(ok("2026-11-01T10:35:00+00:00"), technical_status="error"), "who": dict(first["who"])}
    apply_publication_activation(tmp_path, late_fail, ledger, "d3", "live_discovery", config, False)
    record = json.loads((tmp_path / "data/global_intelligence/publication_activation.json").read_text())
    assert "paho" not in record["sources"] and late_fail["paho"]["publication_activation"] is False


def test_activation_needs_direccion_authorization():
    ledger = {"runs": [run_row("d1", ok("2026-10-28T10:40:00+00:00"))]}
    decision = publication_activation_decision(ledger, "paho", ok("2026-10-29T10:35:00+00:00"), "d2", "live_discovery", {}, "C")
    assert not decision["activated"] and decision["reason"] == "no_direccion_authorization_for_source"


def test_activation_record_is_persisted_and_suspended_on_a_failed_run(tmp_path):
    config = {"publication_activation_policy": POLICY}
    who_fail = dict(ok("2026-10-29T10:30:00+00:00"), technical_status="error")
    ledger = {"runs": [{"run_id": "d1", "mode": "live_discovery", "capture_reuse": {"reused_url_count": 0},
                        "sources": {"paho": ok("2026-10-28T10:40:00+00:00"), "who": who_fail}}]}
    health = {"paho": ok("2026-10-29T10:35:00+00:00"), "who": dict(who_fail)}
    apply_publication_activation(tmp_path, health, ledger, "d2", "live_discovery", config, False)
    assert health["paho"]["publication_activation"] is True and health["who"]["publication_activation"] is False
    assert health["paho"]["editorial_outcome"] == "publication_activated_pending_editorial_approval"
    record = json.loads((tmp_path / "data/global_intelligence/publication_activation.json").read_text())
    assert record["sources"]["paho"]["evidence_run_ids"] == ["d1", "d2"] and "who" not in record["sources"]
    # Earned activation stays recorded, but a failed current run suspends the flag.
    later = {"paho": dict(ok("2026-10-29T14:35:00+00:00"), technical_status="error"), "who": dict(who_fail)}
    apply_publication_activation(tmp_path, later, ledger, "d3", "live_discovery", config, False)
    assert later["paho"]["publication_activation"] is False and later["paho"]["publication_activation_suspended_reason"]
    # A later successful run re-enables it without a new two-day wait.
    again = {"paho": ok("2026-10-29T18:35:00+00:00"), "who": dict(who_fail)}
    apply_publication_activation(tmp_path, again, ledger, "d4", "live_discovery", config, False)
    assert again["paho"]["publication_activation"] is True


def test_replay_never_activates_or_writes_records(tmp_path):
    ledger = {"runs": [run_row("d1", ok("2026-10-28T10:40:00+00:00"))]}
    health = {"paho": ok("2026-10-29T10:35:00+00:00"), "who": ok("2026-10-29T10:35:00+00:00")}
    apply_publication_activation(tmp_path, health, ledger, "d2", "projection_replay", {"publication_activation_policy": POLICY}, True)
    assert health["paho"]["publication_activation"] is False
    assert not (tmp_path / "data/global_intelligence/publication_activation.json").exists()


def test_current_staging_ledger_matches_the_recorded_activation():
    # The ledger grows with every daily run: a source activates once it earns the rule (WHO did on 30-oct-2026,
    # runs 40767743948 + 40969336170). The recorded activation must be exactly what the rule decides.
    ledger = json.loads(Path("data/global_intelligence/ledger.json").read_text())
    recorded = json.loads(Path("data/global_intelligence/publication_activation.json").read_text()).get("sources", {}) \
        if Path("data/global_intelligence/publication_activation.json").exists() else {}
    last = ledger["runs"][-1]
    for source in ("who", "paho"):
        decision = publication_activation_decision({"runs": ledger["runs"][:-1]}, source, last["sources"][source], last["run_id"],
                                                   last["mode"], POLICY, last["sources"][source].get("coverage_contract_id"))
        if source in recorded:  # sticky: once earned, it stays; the evidence must name two successful live runs
            assert recorded[source]["rule"] == "two_consecutive_successful_daily_live_runs" and len(recorded[source]["evidence_run_ids"]) == 2
        else:
            assert not decision["activated"], (source, decision)


def test_sticky_activation_exposes_earned_evidence_for_audits(tmp_path):
    ledger = {"runs": [run_row("d1", ok("2026-10-28T10:40:00+00:00"))]}
    first = {"paho": ok("2026-10-29T10:35:00+00:00"), "who": dict(ok("2026-10-29T10:35:00+00:00"), technical_status="error")}
    apply_publication_activation(tmp_path, first, ledger, "d2", "live_discovery", {"publication_activation_policy": POLICY}, False)
    later = {"paho": ok("2026-10-29T14:35:00+00:00"), "who": dict(first["who"])}
    apply_publication_activation(tmp_path, later, {"runs": []}, "d3", "live_discovery", {"publication_activation_policy": POLICY}, False)
    assert later["paho"]["publication_activation"] is True
    assert later["paho"]["publication_activation_decision"]["earned_evidence_run_ids"] == ["d1", "d2"]


def test_feed_publishers_are_traceable_in_global_themes_only_on_their_own_domains():
    from radar_salud.global_intelligence import ALLOWED_PUBLISHERS, _trusted_source
    assert ALLOWED_PUBLISHERS["KFF Health News"] == {"kffhealthnews.org"}
    source = {"publisher": "KFF Health News", "url": "https://kffhealthnews.org/news/article/x/", "title": "T", "evidence": "feed metadata",
              "published_at": "2026-10-26", "captured_at": "2026-10-27", "material_type": "high_trust_press"}
    _trusted_source(source, AS_OF)
    with pytest.raises(ValueError, match="domain mismatch"):
        _trusted_source(dict(source, url="https://www.statnews.com/x"), AS_OF)
