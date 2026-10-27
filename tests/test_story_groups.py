from radar_salud.story_groups import apply_story_groups


def _c(url, date, src="Pulso / La Tercera"):
    return {"title": url, "source_url": url, "event_date": date, "source_name": src}


def test_lead_folds_same_event_into_one_card():
    cards = [_c("a", "2026-10-20", "Diario Financiero"), _c("b", "2026-10-22"), _c("x", "2026-10-21")]
    out, sums = apply_story_groups(cards, [{"id": "g", "mode": "lead", "lead_url": "a", "member_urls": ["a", "b"]}])
    assert [c["source_url"] for c in out] == ["a", "x"] and not sums
    assert out[0]["source_alternatives"][0]["url"] == "b" and out[0]["story_group"] == "g"


def test_summary_replaces_members_and_links_them():
    cards = [_c("a", "2026-10-01"), _c("b", "2026-10-22"), _c("x", "2026-10-21")]
    g = {"id": "p", "mode": "summary", "member_urls": ["a", "b", "gone"], "card": {"title": "T", "what_happened": "W"}}
    out, sums = apply_story_groups(cards, [g])
    assert [c["source_url"] for c in out] == ["x"]
    assert sums[0]["event_date"] == "2026-10-22" and [a["url"] for a in sums[0]["source_alternatives"]] == ["b", "a"]


def test_summary_needs_two_live_members_and_lead_needs_its_lead():
    cards = [_c("a", "2026-10-01"), _c("x", "2026-10-21")]
    out, sums = apply_story_groups(cards, [{"id": "p", "mode": "summary", "member_urls": ["a"], "card": {"title": "T"}},
                                            {"id": "l", "mode": "lead", "lead_url": "zz", "member_urls": ["a", "x"]}])
    assert len(out) == 2 and not sums


def test_rejected_synthesis_keeps_members_visible():
    cards = [_c("a", "2026-10-01"), _c("b", "2026-10-22")]
    g = {"id": "p", "mode": "summary", "member_urls": ["a", "b"], "card": {"title": "T"}}
    out, sums = apply_story_groups(cards, [g], gate=lambda c: False)
    assert len(out) == 2 and not sums
    out, sums = apply_story_groups(cards, [g], gate=lambda c: True)
    assert not out and sums[0]["source_url"] == "b"


def test_overlapping_groups_are_rejected(tmp_path):
    import json
    from radar_salud.story_groups import CONFIG, load_groups
    (tmp_path / "config").mkdir()
    (tmp_path / CONFIG).write_text(json.dumps({"groups": [
        {"id": "1", "mode": "summary", "member_urls": ["a", "b"]},
        {"id": "2", "mode": "lead", "lead_url": "b", "member_urls": ["b", "c"]},
        {"id": "3", "mode": "lead", "lead_url": "z", "member_urls": ["d", "e"]}]}), encoding="utf-8")
    assert [g["id"] for g in load_groups(tmp_path)] == ["1"]
