from datetime import datetime, timezone, timedelta
import pytest
from radar_salud.autopilot import reserve, approve, consolidate, should_attempt, CRITICAL
from radar_salud.pending_queue import PendingQueue
from radar_salud.models import RawItem

NOW=datetime(2026,9,23,12,tzinfo=timezone.utc)

def raw(title,date):
    return RawItem("source",title,"https://example.org/"+title,"Source","official",date)

def test_attempts_survive_reload_without_daily_cap(tmp_path):
    import json
    from radar_salud.autopilot import save_ledger
    path=tmp_path/"ledger.json";ledger={}
    for _ in range(5):
        attempt=reserve(ledger,"abc","builder",NOW)
        attempt.update(state="failed", progress=True)
        save_ledger(path,ledger);ledger=json.loads(path.read_text())
    assert reserve(ledger,"abc","builder",NOW)["id"].endswith("-6")
    assert reserve(ledger,"def","builder",NOW+timedelta(days=1))["state"]=="reserved"

def test_reviewer_sha_and_independence_fail_closed():
    entry=reserve({},"abc","builder",NOW);checks={k:True for k in CRITICAL}
    with pytest.raises(ValueError):approve(entry,[dict(reviewer="builder",candidate_sha="abc")],checks)
    with pytest.raises(ValueError):approve(entry,[dict(reviewer="reviewer",candidate_sha="other")],checks)
    assert not approve(entry,[dict(reviewer="reviewer",candidate_sha="abc")],{"tests":True})
    assert approve(entry,[dict(reviewer="reviewer",candidate_sha="abc")],checks)
    assert entry["state"] == "qa_passed"
    assert should_attempt({"iterations":[entry]},"abc")  # remote preview may fail

def test_three_unproductive_cycles_stop():
    ledger={}
    for _ in range(3):
        reserve(ledger,"abc","builder",NOW)["state"]="failed"
    with pytest.raises(RuntimeError,match="Three consecutive"):
        reserve(ledger,"abc","builder",NOW)

def test_feedback_consolidates_without_losing_critical():
    common=dict(category="data",path="a",code="bad")
    reports=[dict(reviewer="a",findings=[dict(common,severity="warning")]),dict(reviewer="b",findings=[dict(common,severity="critical")])]
    result=consolidate(reports)
    assert len(result)==1 and result[0]["severity"]=="critical" and len(result[0]["reviewers"])==2

def test_global_live_priority_and_crash_recovery(tmp_path):
    path=tmp_path/"queue.json";queue=PendingQueue(path)
    queue.discover("first",[raw("old","2026-08-01")],now=NOW)
    queue.discover("second",[raw("live","2026-09-23")],now=NOW,last_discovered_at="2026-09-22T10:00:00+00:00")
    key,item=queue.ready(NOW)[0]
    assert item["source"]=="second"
    queue.start(key)
    assert PendingQueue(path).ready(NOW)[0][0]==key
    queue.finish(key,"retry","budget",now=NOW)
    assert len(queue.ready(NOW))==1
    assert queue.counts()["live_pending"]==1 and queue.counts()["backfill_pending"]==1
    assert len(queue.ready(NOW+timedelta(days=1)))==2

def test_discovery_is_durable_and_deduplicated(tmp_path):
    queue=PendingQueue(tmp_path/"q.json")
    items=[raw(str(i),"2026-09-23") for i in range(100)]
    assert queue.discover("s",items,now=NOW,last_discovered_at="2026-09-22T10:00:00+00:00")==100
    assert PendingQueue(queue.path).discover("s",items,now=NOW)==0
    assert queue.counts()["live_pending"]==100

def test_first_discovery_is_backfill_even_when_item_is_recent(tmp_path):
    queue=PendingQueue(tmp_path/"q.json")
    queue.discover("source",[raw("recent","2026-09-23")],now=NOW)
    assert queue.counts()["live_pending"]==0
    assert queue.counts()["backfill_pending"]==1
    queue.discover("source",[raw("next","2026-09-23")],now=NOW+timedelta(hours=2),last_discovered_at=NOW.isoformat())
    assert queue.counts()["live_pending"]==1
    assert queue.counts()["backfill_pending"]==1

def test_scheduled_cycle_skips_unchanged_reviewed_candidate():
    ledger={}
    entry=reserve(ledger,"abc","builder",NOW)
    assert should_attempt(ledger,"abc")
    entry["state"]="blocked"
    assert not should_attempt(ledger,"abc")
    assert should_attempt(ledger,"new")

def test_backfill_over_90_days_is_retained_but_never_processes(tmp_path):
    queue=PendingQueue(tmp_path/"q.json")
    queue.discover("source",[raw("old","2026-06-01"),raw("recent","2026-09-01")],now=NOW)
    assert len(queue.items)==2
    assert len(queue.ready(NOW))==1
    old=next(x for x in queue.items.values() if x["raw"]["title"]=="old")
    assert old["status"]=="archived" and old["reason"]=="outside_90_day_backfill"
    assert queue.counts()["backfill_pending"]==1
    assert queue.enforce_backfill_horizon(NOW+timedelta(days=100))==1
    assert queue.ready(NOW+timedelta(days=100))==[]

def test_future_dated_backfill_waits_and_is_not_archived(tmp_path):
    queue=PendingQueue(tmp_path/"q.json")
    queue.discover("s",[raw("future","2026-09-24")],now=NOW)
    assert queue.ready(NOW)==[]
    assert queue.counts()["backfill_pending"]==1
    assert len(queue.ready(NOW+timedelta(days=1)))==1
