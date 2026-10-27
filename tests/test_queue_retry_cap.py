import json

from radar_salud.pending_queue import PendingQueue


def test_items_failing_repeatedly_stop_counting_as_pending(tmp_path):
    p = tmp_path / "q.json"
    base = {"source": "clinicas_chile", "lane": "BACKFILL", "detected_at": "x", "raw": {}}
    p.write_text(json.dumps({
        "a": {**base, "status": "retry", "attempts": 4, "reason": "Clínicas de Chile without verified date", "retry_at": "z"},
        "b": {**base, "status": "retry", "attempts": 2, "reason": "transient", "retry_at": "z"},
        "c": {**base, "status": "published", "attempts": 5}}))
    q = PendingQueue(p)
    assert q.defer_exhausted(4) == 1
    assert q.items["a"]["status"] == "deferred" and q.items["a"]["reason"].startswith("retry_exhausted:Clínicas")
    assert q.items["b"]["status"] == "retry" and q.items["c"]["status"] == "published"
