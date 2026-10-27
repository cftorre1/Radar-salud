import json
from datetime import date

from radar_salud.daily_window import eligible_daily_item, item_date
from radar_salud.pending_queue import PendingQueue


def test_undated_items_use_detection_date_instead_of_waiting_forever():
    item = {"raw": {"event_date": None}, "detected_at": "2026-10-20T10:00:00+00:00"}
    assert item_date(item) == date(2026, 10, 20)
    assert eligible_daily_item(item, today=date(2026, 10, 27), days=30)
    assert not eligible_daily_item({"raw": {}, "detected_at": "2026-08-01T00:00:00"}, today=date(2026, 10, 27), days=30)
    assert item_date({"raw": {"event_date": "2026-10-01"}, "detected_at": "2026-10-20"}) == date(2026, 10, 1)


def test_retired_sources_are_archived_not_left_pending(tmp_path):
    p = tmp_path / "q.json"
    p.write_text(json.dumps({
        "a": {"source": "red_davila", "status": "pending", "lane": "LIVE", "attempts": 0, "detected_at": "x", "raw": {}},
        "b": {"source": "minsal", "status": "pending", "lane": "LIVE", "attempts": 0, "detected_at": "x", "raw": {}}}))
    q = PendingQueue(p)
    assert q.archive_sources({"red_davila": "retirada"}, reason="source_retired") == 1
    assert q.items["a"]["status"] == "archived" and q.items["b"]["status"] == "pending"


def test_hourly_batch_shares_the_writer_lock_and_never_discovers():
    wf = open(".github/workflows/queue-hourly.yml", encoding="utf-8").read()
    daily = open(".github/workflows/daily-radar.yml", encoding="utf-8").read()
    for text in (wf, daily):
        assert "group: alicanto-staging-writer" in text and "cancel-in-progress: false" in text
    assert "--process-only" in wf and "tests/test_reviewer.py" in wf and "RADAR_MONTHLY_USD: 10" in wf
    assert "--process-only" not in daily


def test_budget_is_paced_over_the_month():
    from datetime import datetime, timezone
    from radar_salud.ai_pricing import paced_budget_usd
    assert paced_budget_usd(datetime(2026, 10, 1, tzinfo=timezone.utc)) < 1.4
    assert paced_budget_usd(datetime(2026, 10, 31, tzinfo=timezone.utc)) == 10


def test_hourly_skips_discovery_hours_and_retries_push():
    wf = open(".github/workflows/queue-hourly.yml", encoding="utf-8").read()
    assert "'15 0-9,11-13,15-17,19-21,23 * * *'" in wf and "discovery_due.py" in wf
    for path in (".github/workflows/queue-hourly.yml", ".github/workflows/daily-radar.yml"):
        assert "git pull --rebase origin staging" in open(path, encoding="utf-8").read()
