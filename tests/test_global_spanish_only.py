"""Dirección 30-oct-2026: Global lists only items it can present in Spanish; WHO/EMA page meta descriptions feed
Alicanto's summary (robots, host allowlist, caps, URL cache, meta tags only)."""
import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar_salud import global_daily_feed as g
from radar_salud import global_page_meta as pm
from radar_salud.global_translation import SUMMARY_PROMPT_VERSION, content_key

CONFIG = json.loads(Path("config/global_discovery.json").read_text())
AS_OF = date(2026, 10, 28)
NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def card(i, source="who", status=None, day="2026-10-27", url=None, **extra):
    c = {"id": f"c{i}", "source": source, "source_label": source.upper(), "title": f"Headline {i}",
         "url": url or f"https://www.who.int/news/item/{i}", "published_at": day, "priority": 50, "segments": ["regulation"],
         "description": None, **extra}
    if status:
        c["translation"] = {"status": status}
    return c


def summarized(c):
    c.update(summary_es="La OMS publicó una guía.", translation={"status": "summarized", "kind": "summary", "verified": True})
    return c


def translated(c):
    c.update(title_es="Titular traducido", translation={"status": "translated", "kind": "translation", "verified": True})
    return c


# ------------------------------------------------------------------ display rule


def test_config_flag_is_on_with_a_recorded_authorization():
    display = CONFIG["daily_feed"]["display"]
    assert display["spanish_only"] is True and display["authorized_by"].strip() and display["authorized_at"] == "2026-10-30"
    assert "Dirección 30-oct-2026" in display["authorization_note"]


@pytest.mark.parametrize("c, shown", [
    (card(1, status="not_allowed"), False),
    (card(2, status="not_allowed", **{"translation": {"status": "not_allowed", "summary_status": "verification_failed"}}), False),
    (card(3, source="cdc", status="pending", url="https://www.cdc.gov/x"), False),
    (card(4, source="cdc", status="verification_failed", url="https://www.cdc.gov/x"), False),
    (card(5), False),  # no translation record at all (translation crashed or disabled)
    (summarized(card(6)), True),
    (translated(card(7, source="cdc", url="https://www.cdc.gov/x")), True),
    (card(8, source="paho", status="source_in_spanish", url="https://www.paho.org/es/noticias/x"), True),
    (card(9, source="paho", url="https://www.paho.org/es/noticias/y"), True),  # Spanish page, whatever the record says
    (card(10, source="paho", status="not_allowed", url="https://www.paho.org/en/news/x"), False),
])
def test_display_rule(c, shown):
    assert g.displayable(c)[0] is shown, c


def test_unverified_or_empty_spanish_text_is_hidden():
    bad = [summarized(card(1)), summarized(card(2)), translated(card(3, source="cdc")), translated(card(4, source="cdc"))]
    bad[0]["translation"]["verified"] = False
    bad[1]["summary_es"] = "  "
    bad[2]["title_es"] = ""
    bad[3]["description"], bad[3]["description_es"] = "A publisher summary", None  # summary without its translation
    assert [g.displayable(c)[0] for c in bad] == [False] * 4


def test_public_payload_lists_only_displayable_items_and_recomputes_counts():
    items = [card(1, status="not_allowed", day="2026-10-28"), summarized(card(2, day="2026-10-20")),
             translated(card(3, source="cdc", url="https://www.cdc.gov/x", day="2026-10-26")),
             card(4, source="cdc", status="pending", url="https://www.cdc.gov/y"),
             card(5, source="paho", status="source_in_spanish", url="https://www.paho.org/es/x", day="2026-10-10")]
    payload = {"items": items, "freshness": {"newest_published_at": "2026-10-28"}, "sources": [["who", "WHO"]]}
    public = g.public_payload(payload, CONFIG, AS_OF)
    assert [c["id"] for c in public["items"]] == ["c2", "c3", "c5"]
    assert all(g.displayable(c)[0] for c in public["items"])
    assert public["display"] == {"spanish_only": True, "shown": 3, "hidden": 2, "authorized_by": CONFIG["daily_feed"]["display"]["authorized_by"],
                                 "authorized_at": "2026-10-30",
                                 "hidden_by_reason": {"not_allowed_without_verified_summary": 1, "translation_pending": 1}}
    assert public["freshness"]["newest_published_at"] == "2026-10-26" and public["freshness"]["items_last_7_days"] == 1
    assert sorted(s[0] for s in public["sources"]) == ["cdc", "paho", "who"]
    assert len(payload["items"]) == 5  # the full payload (data/ state) is not modified
    off = copy.deepcopy(CONFIG)
    off["daily_feed"]["display"]["spanish_only"] = False
    assert len(g.public_payload(payload, off, AS_OF)["items"]) == 5


def test_page_meta_description_is_summary_input_only_never_shown_verbatim():
    c = summarized(card(1, description="WHO meta text", description_source=pm.DESCRIPTION_SOURCE))
    out = g.public_payload({"items": [c]}, CONFIG, AS_OF)["items"][0]
    assert out["description"] is None and out["description_source"] is None and out["summary_input"] == pm.DESCRIPTION_SOURCE
    assert c["description"] == "WHO meta text"  # kept in the state


def test_themes_are_not_touched_by_the_rule():
    src = Path("src/radar_salud/global_daily_feed.py").read_text()
    assert "global_themes" not in src
    js = Path("web/global.js").read_text()
    assert "themes.map(themeEntry)" in js and "inSpanish(x)" in js


# ------------------------------------------------------------------ exporter: hidden kept in data/, never public


def _root(tmp_path, items):
    (tmp_path / "config").mkdir()
    cfg = copy.deepcopy(CONFIG)
    (tmp_path / "config/global_discovery.json").write_text(json.dumps(cfg))
    discovery = {"source_health": {"who": {"publication_activation": True}}, "items": [
        {"source": "who", "url": f"https://www.who.int/news/item/{i}", "title": title, "published_at": day, "detail_verified": True,
         "classification": {"materiality": "candidate", "priority": 80}} for i, (title, day) in enumerate(items)]}
    (tmp_path / "data/global_intelligence").mkdir(parents=True)
    (tmp_path / "data/global_intelligence/discovery.json").write_text(json.dumps(discovery))
    return tmp_path


WHO_TITLES = [("WHO issues new guidance on health financing for hospitals", "2026-10-27"),
              ("WHO report on medicines regulation and pharmaceutical pricing", "2026-10-26")]


def test_export_without_key_hides_english_items_and_keeps_them_in_state(tmp_path):
    root = _root(tmp_path, WHO_TITLES)
    public = g.export(root, AS_OF, env={})
    state = json.loads((root / "data/global_intelligence/global_feed_state.json").read_text())
    written = json.loads((root / "web/data/global_feed.json").read_text())
    assert state["items"], state["held"]
    assert public["items"] == [] and written["items"] == [] and written["display"]["hidden"] == len(state["items"])
    assert all(c["translation"]["status"] == "not_allowed" for c in state["items"])
    # Next run builds on the state: ids and first_seen_on survive although nothing was public.
    first = {c["id"]: c["first_seen_on"] for c in state["items"]}
    g.export(root, AS_OF + timedelta(days=1), env={})
    again = json.loads((root / "data/global_intelligence/global_feed_state.json").read_text())
    assert {c["id"]: c["first_seen_on"] for c in again["items"]} == first


def test_exported_public_feed_contains_no_hidden_item(tmp_path):
    root = _root(tmp_path, WHO_TITLES)

    def model(prompt, name):
        from types import SimpleNamespace
        if "independent fidelity reviewer" in prompt:
            return SimpleNamespace(output={"faithful": True, "issues": []}, model=name)
        return SimpleNamespace(output={"summary_es": "La OMS publicó una guía sobre financiamiento de la salud para hospitales."}, model=name)

    public = g.export(root, AS_OF, env={"OPENAI_API_KEY": "test-placeholder"}, call=model, allow=lambda: True, record=lambda ok: None, now=NOW)
    state = json.loads((root / "data/global_intelligence/global_feed_state.json").read_text())
    shown = {c["id"] for c in state["items"] if g.displayable(c)[0]}
    assert {c["id"] for c in public["items"]} == shown
    assert all(g.displayable(c)[0] for c in json.loads((root / "web/data/global_feed.json").read_text())["items"])
    assert len(state["items"]) >= len(public["items"])


def test_committed_public_feed_lists_only_spanish_items():
    feed = json.loads(Path("web/data/global_feed.json").read_text())
    assert feed["display"]["spanish_only"] is True
    assert all(g.displayable(c)[0] for c in feed["items"])
    assert not any(c.get("description_source") == pm.DESCRIPTION_SOURCE for c in feed["items"])


# ------------------------------------------------------------------ page meta descriptions

PAGE = b"""<html><head><title>T</title><meta name="description" content="WHO publishes new &amp; updated guidance on X.">
<meta property="og:description" content="OG text"></head><body><p>Full article body that must never be stored.</p></body></html>"""


class FakeClient:
    def __init__(self, pages=None, deny=()):
        self.pages, self.deny = pages or {}, set(deny)
        self.fetched, self.robots_checked = [], []

    def check_robots(self, url):
        self.robots_checked.append(url)
        if url in self.deny:
            raise ValueError("robots_disallowed: " + url)

    def fetch(self, url):
        self.fetched.append(url)
        return self.pages.get(url, PAGE), {"http_status": 200}


def fetch(cards, client, cache=None, config=CONFIG, **kw):
    cache = cache if cache is not None else {"entries": {}}
    return pm.fetch_descriptions(cards, config, cache, client, now=NOW, **kw), cache


def test_meta_description_config_is_bounded():
    s = pm.settings(CONFIG)
    assert s["enabled"] and s["sources"] == {"who", "ema"} and s["domains"] == ["who.int", "ema.europa.eu"]
    assert s["max_fetches"] == 30 and s["max_chars"] == 600 and s["timeout"] > 0 and s["max_bytes"] > 0
    wide = copy.deepcopy(CONFIG)
    wide["daily_feed"]["page_meta_description"].update(allowed_domains=["who.int", "evil.example"], max_chars=5000)
    assert pm.settings(wide)["domains"] == ["who.int"] and pm.settings(wide)["max_chars"] == 600


def test_robots_deny_means_no_fetch():
    c = card(1)
    client = FakeClient(deny={c["url"]})
    stats, cache = fetch([c], client)
    assert client.fetched == [] and client.robots_checked == [c["url"]]
    assert cache["entries"][c["url"]]["status"] == "robots_disallowed" and stats["robots_disallowed"] == 1
    assert "description" not in cache["entries"][c["url"]]


def test_off_allowlist_host_or_source_is_never_fetched():
    cards = [card(1, url="https://www.who.int.evil.example/x"), card(2, url="http://www.who.int/news/item/2"),
             card(3, source="cdc", url="https://www.cdc.gov/x"), card(4, source="ema", url="https://www.ema.europa.eu/en/news/a"),
             card(5, source="who", url="https://who.int/news/item/5")]
    client = FakeClient()
    stats, cache = fetch(cards, client)
    assert sorted(client.fetched) == ["https://who.int/news/item/5", "https://www.ema.europa.eu/en/news/a"]
    assert client.robots_checked == client.fetched or sorted(client.robots_checked) == sorted(client.fetched)
    assert stats["off_allowlist"] == 2


def test_items_with_a_feed_description_are_not_fetched():
    client = FakeClient()
    fetch([card(1, source="ema", url="https://www.ema.europa.eu/en/news/a", description="Feed summary")], client)
    assert client.fetched == []


def test_per_run_cap_and_url_cache():
    cfg = copy.deepcopy(CONFIG)
    cfg["daily_feed"]["page_meta_description"]["max_new_fetches_per_run"] = 3
    cards = [card(i, day=f"2026-10-{20 + i:02d}") for i in range(6)]
    client = FakeClient()
    stats, cache = fetch(cards, client, config=cfg)
    assert len(client.fetched) == 3 and stats["stopped"] == "run_cap"
    assert client.fetched == [c["url"] for c in sorted(cards, key=lambda c: c["published_at"], reverse=True)[:3]]  # newest first
    second = FakeClient()
    stats2, cache = fetch(cards, second, cache=cache, config=cfg)
    assert len(second.fetched) == 3 and not set(second.fetched) & set(client.fetched) and stats2["from_cache"] == 3
    third = FakeClient()
    fetch(cards, third, cache=cache, config=cfg)
    assert third.fetched == [] and third.robots_checked == []


def test_failures_are_cached_and_retried_only_after_the_retry_window():
    c = card(1)
    client = FakeClient(pages={c["url"]: b"<html><body><p>No meta here, only body text.</p></body></html>"})
    _, cache = fetch([c], client)
    assert cache["entries"][c["url"]]["status"] == "no_meta_description"
    again = FakeClient()
    fetch([c], again, cache=cache)
    assert again.fetched == []
    later = FakeClient()
    pm.fetch_descriptions([c], CONFIG, cache, later, now=NOW + timedelta(days=8))
    assert later.fetched == [c["url"]] and cache["entries"][c["url"]]["status"] == "ok"


def test_only_meta_tags_are_used_never_body_text():
    text, cut = pm.extract_meta_description(PAGE)
    assert text == "WHO publishes new & updated guidance on X." and not cut
    assert pm.extract_meta_description(b"<html><body><p>Body only</p><div>description: x</div></body></html>") == (None, False)
    og = b'<head><meta property="og:description" content="OG only"></head><body>Body</body>'
    assert pm.extract_meta_description(og) == ("OG only", False)
    assert pm.extract_meta_description(b'<meta name="description" content="  "><p>Body</p>') == (None, False)
    c = card(1)
    _, cache = fetch([c], FakeClient())
    entry = cache["entries"][c["url"]]
    assert entry["description"] == "WHO publishes new & updated guidance on X." and "Full article body" not in json.dumps(cache)
    assert entry["description_source"] == "publisher_page_meta_description"


def test_description_is_capped_at_600_characters():
    long = ("word " * 400).strip()
    text, cut = pm.extract_meta_description(f'<meta name="description" content="{long}">')
    assert cut and len(text) <= 600 and text.endswith("…")


def test_size_cap_rejects_large_pages():
    cfg = copy.deepcopy(CONFIG)
    cfg["daily_feed"]["page_meta_description"]["max_bytes"] = 100
    c = card(1)
    _, cache = fetch([c], FakeClient(), config=cfg)
    assert cache["entries"][c["url"]]["status"] == "too_large"


def test_apply_sets_description_offline_and_feeds_the_summary_key():
    c = card(1)
    _, cache = fetch([c], FakeClient())
    cards = [card(1), card(2)]
    assert pm.apply_descriptions(cards, CONFIG, cache) == 1
    assert cards[0]["description"] == "WHO publishes new & updated guidance on X."
    assert cards[0]["description_source"] == "publisher_page_meta_description" and cards[1]["description"] is None
    assert content_key(cards[0]["title"], cards[0]["description"], SUMMARY_PROMPT_VERSION) != content_key(cards[0]["title"], None, SUMMARY_PROMPT_VERSION)


def test_existing_title_only_summary_is_kept_no_fetch(tmp_path):
    root = _root(tmp_path, WHO_TITLES[:1])
    title = WHO_TITLES[0][0]
    key = content_key(title, None, SUMMARY_PROMPT_VERSION)
    cache = {"schema_version": 2, "entries": {key: {"kind": "summary", "summary_es": "La OMS publicó una guía sobre financiamiento de la salud para hospitales.",
                                                    "review": {"faithful": True}, "last_used": NOW.isoformat(), "written_at": NOW.isoformat()}},
             "rejected": {}, "pending_review": {}}
    (root / "data/global_intelligence/translations.json").write_text(json.dumps(cache))
    client = FakeClient()
    public = g.export(root, AS_OF, env={}, page_client=client)
    assert client.fetched == [] and [c["title"] for c in public["items"]] == [title]
    assert public["items"][0]["translation"]["status"] == "summarized"


def test_export_with_a_page_client_fetches_caches_and_applies(tmp_path):
    root = _root(tmp_path, WHO_TITLES)
    client = FakeClient()
    g.export(root, AS_OF, env={}, page_client=client)
    assert len(client.fetched) == 2
    pages = json.loads((root / "data/global_intelligence/page_descriptions.json").read_text())
    assert {e["status"] for e in pages["entries"].values()} == {"ok"}
    state = json.loads((root / "data/global_intelligence/global_feed_state.json").read_text())
    assert all(c["description_source"] == "publisher_page_meta_description" for c in state["items"])
    # Offline re-export: no client, same descriptions from the URL cache, no request.
    g.export(root, AS_OF, env={})
    again = json.loads((root / "data/global_intelligence/global_feed_state.json").read_text())
    assert [c.get("description") for c in again["items"]] == [c.get("description") for c in state["items"]]
