"""Saved live proof, publisher separation and isolated public-feed updates."""
import copy
import json
from pathlib import Path

import pytest

from radar_salud.occupational_snapshot import export_snapshot, prepare_signal

ROOT = Path(__file__).resolve().parents[1]
SLUG = "achs_seguro_laboral"


def fixture(tmp_path):
    queue = json.loads((ROOT / "data/state/pending_queue.json").read_text())
    key, item = next((k, v) for k, v in queue.items() if v.get("source") == SLUG
                     and v.get("status") == "published" and "ley-karin" in v["raw"]["url"])
    history = json.loads((ROOT / "data/history/superintendencia_signals.json").read_text())["signals"]
    signal = next(copy.deepcopy(r) for r in history if r.get("source_url") == item["raw"]["url"])
    untouched = {"source_url": "https://official.example/unrelated", "title": "Other lane",
                 "nested": {"count": 9}, "event_date": "2026-07-15"}
    original = {"date": "2026-10-09", "generated_at": "original-time", "signals": [untouched], "extra": 42}
    for path, payload in [("data/state/pending_queue.json", {key: copy.deepcopy(item)}),
                          ("data/history/superintendencia_signals.json", {"signals": [signal]}),
                          ("web/data/radar_today.json", original)]:
        p = tmp_path / path; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload))
    reports = {SLUG: {"rows": [{"url": signal["source_url"], "status": "candidate",
                              "publication_date": signal["event_date"], "alicanto_status": "published",
                              "market_role": item['raw']['metadata']['market_role'],
                              "provider_subtype": item['raw']['metadata'].get('provider_subtype')}]}}
    return reports, original, signal, key


def test_actual_published_capture_exports_only_its_lane_and_is_idempotent(tmp_path):
    reports, original, signal, _ = fixture(tmp_path)
    result = export_snapshot(tmp_path, reports, as_of="2026-10-11")
    saved = json.loads((tmp_path / "web/data/radar_today.json").read_text())
    assert result["published"] == 1 and not result["deferred"]
    assert saved["signals"][0] == original["signals"][0]
    assert {k:v for k,v in saved.items() if k != "signals"} == {k:v for k,v in original.items() if k != "signals"}
    assert saved["signals"][1]["source_url"] == signal["source_url"]
    assert saved["signals"][1]["editorial_committee"]["verdict"] == "PASS"
    assert not export_snapshot(tmp_path, reports, as_of="2026-10-11")["snapshot_changed"]


@pytest.mark.parametrize("field,value", [("editorial_relevance", 74), ("event_date", "2026-10-12"),
    ("market_role", "provider_achs"), ("why_it_matters", "invented copy")])
def test_unproved_changed_output_is_deferred_and_original_feed_untouched(tmp_path, field, value):
    reports, original, signal, _ = fixture(tmp_path)
    signal[field] = value
    (tmp_path / "data/history/superintendencia_signals.json").write_text(json.dumps({"signals": [signal]}))
    result = export_snapshot(tmp_path, reports, as_of="2026-10-11")
    assert result["published"] == 0 and signal["source_url"] in result["deferred"]
    assert json.loads((tmp_path / "web/data/radar_today.json").read_text()) == original


def test_queue_cannot_claim_published_with_unreadable_capture(tmp_path):
    reports, original, signal, key = fixture(tmp_path)
    p = tmp_path / "data/state/pending_queue.json"
    queue = json.loads(p.read_text())
    queue[key]["raw"]["metadata"]["capture_evidence"]["artifact"] = "data/audits/missing.body"
    p.write_text(json.dumps(queue))
    result = export_snapshot(tmp_path, reports, as_of="2026-10-11")
    assert result["published"] == 0 and result["deferred"]
    assert json.loads((tmp_path / "web/data/radar_today.json").read_text()) == original


def test_fresh_same_input_preserves_accepted_copy_and_review_before_export(tmp_path):
    from radar_salud.models import RawItem
    from scripts.occupational_inventory import refresh_item
    reports, _, signal, key = fixture(tmp_path)
    p = tmp_path / "data/state/pending_queue.json"
    queue = json.loads(p.read_text()); item = queue[key]
    item["raw"]["metadata"]["editorial_review"] = {"decision": "accept", "reviewer": "independent"}
    fresh = copy.deepcopy(item["raw"])
    for name in ("what_happened", "why_it_matters", "editorial_assessment", "editorial_review"):
        fresh["metadata"].pop(name, None)
    assert not refresh_item(item, RawItem(**fresh))
    assert item["raw"]["metadata"]["editorial_review"]["decision"] == "accept"
    assert item["raw"]["metadata"]["why_it_matters"] == signal["why_it_matters"]
    p.write_text(json.dumps(queue))
    assert export_snapshot(tmp_path, reports, as_of="2026-10-11")["published"] == 1


def test_matching_queue_and_history_still_cannot_forge_the_inventory_role(tmp_path):
    reports, original, signal, key = fixture(tmp_path)
    p = tmp_path / 'data/state/pending_queue.json'
    queue = json.loads(p.read_text()); queue[key]['raw']['metadata']['market_role'] = 'provider_achs'
    p.write_text(json.dumps(queue))
    signal['market_role'] = 'provider_achs'
    (tmp_path / 'data/history/superintendencia_signals.json').write_text(json.dumps({'signals':[signal]}))
    result = export_snapshot(tmp_path, reports, as_of='2026-10-11')
    assert result['published'] == 0 and result['deferred']
    assert json.loads((tmp_path / 'web/data/radar_today.json').read_text()) == original


def test_public_gate_preserves_existing_editorial_rejection():
    signal = {"title": "An actual operational change with adequate detail", "source_url": "https://ist.cl/news/",
              "event_date": "2026-10-10", "what_happened": "A concrete operational change with more than forty five characters.",
              "why_it_matters": "An identifiable effect on employers and occupational service operations.",
              "editorial_decision": "reject"}
    accepted, reason = prepare_signal(signal)
    assert accepted is None and reason == "committee_reject"
