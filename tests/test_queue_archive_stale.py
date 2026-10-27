from datetime import datetime, timezone

from src.radar_salud.models import RawItem
from src.radar_salud.pending_queue import PendingQueue


def test_items_outside_daily_window_are_archived_not_pending(tmp_path):
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    q = PendingQueue(tmp_path / "q.json")
    old = RawItem("pulso_latercera", "Nota antigua", "https://x/old", "Pulso", "press_high_trust", "2026-08-01")
    new = RawItem("pulso_latercera", "Nota reciente", "https://x/new", "Pulso", "press_high_trust", "2026-10-20")
    q.discover("pulso_latercera", [old, new], now=now)
    assert q.archive_outside_daily_window(30, now=now) == 1
    by = {i["raw"]["url"]: i for i in q.items.values()}
    assert by["https://x/old"]["status"] == "archived" and by["https://x/old"]["reason"] == "outside_daily_window_30d"
    assert by["https://x/new"]["status"] in ("pending", "retry")
