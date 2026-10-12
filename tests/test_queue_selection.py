"""Selection changes execution membership, never discovery or editorial rules."""
import copy
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar_salud import engine_cli, paths
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, fingerprint
from radar_salud.queue_selection import load_queue_selection, select_ready

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "pulso_latercera"
FIRST = "https://www.latercera.com/pulso/noticia/primera-noticia/"
SECOND = "https://www.latercera.com/nacional/noticia/segunda-noticia/"
OUTSIDE = "https://www.latercera.com/nacional/noticia/fuera-de-cohorte/"


def manifest(tmp_path, urls, **extra):
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(dict(source=SOURCE, urls=urls, **extra)))
    return path


def raw(url):
    return RawItem(SOURCE, url.rsplit("/", 2)[-2], url, "Pulso / La Tercera", "press_high_trust",
                   datetime.now(timezone.utc).date().isoformat())


@pytest.mark.parametrize("url", [
    "http://www.latercera.com/pulso/noticia/foo/",
    "https://latercera.com/pulso/noticia/foo/",
    "https://www.latercera.com/pulso/noticia/foo",
    "https://www.latercera.com/pulso/noticia/foo/?outputType=base-amp-type",
    "https://www.latercera.com/pulso/noticia/foo/#section",
    "https://www.latercera.com/tag/salud/",
    "https://www.latercera.com.evil.invalid/pulso/noticia/foo/",
    "https://www.latercera.com:443/pulso/noticia/foo/",
    "https://user@www.latercera.com/pulso/noticia/foo/",
    7, None,
])
def test_only_exact_canonical_official_article_urls_are_accepted(tmp_path, url):
    with pytest.raises(ValueError):
        load_queue_selection(manifest(tmp_path, [url]), [SOURCE])


@pytest.mark.parametrize("sources", [None, [], ["minsal"], [SOURCE, "minsal"], [SOURCE, SOURCE]])
def test_source_scope_must_be_exactly_pulso(tmp_path, sources):
    with pytest.raises(ValueError, match="requires --sources"):
        load_queue_selection(manifest(tmp_path, [FIRST]), sources)


@pytest.mark.parametrize("value", [[], {}, dict(source=SOURCE, urls=[]),
                                  dict(source="minsal", urls=[FIRST]),
                                  dict(source=SOURCE, source_id="minsal", urls=[FIRST]),
                                  dict(source=SOURCE, urls=[FIRST, FIRST]),
                                  dict(source=SOURCE, urls=FIRST)])
def test_invalid_or_duplicate_manifest_cannot_supply_a_cohort(tmp_path, value):
    path = tmp_path / "bad.json"; path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        load_queue_selection(path, [SOURCE])


def test_selection_preserves_ready_order_due_time_and_all_queue_bookkeeping(tmp_path):
    queue = PendingQueue(tmp_path / "queue.json")
    urls = [FIRST, SECOND, OUTSIDE] + [f"https://www.latercera.com/pulso/noticia/{n}/" for n in range(4)]
    queue.discover(SOURCE, [raw(url) for url in urls])
    by_url = {item["raw"]["url"]: key for key, item in queue.items.items()}
    now = datetime.now(timezone.utc)
    queue.items[by_url[SECOND]].update(status="retry", attempts=3, retry_at=(now-timedelta(minutes=1)).isoformat())
    queue.items[by_url[urls[3]]].update(status="published", attempts=2, reason=None)
    queue.items[by_url[urls[4]]].update(status="rejected", attempts=1, reason="editorial_relevance_below_threshold")
    queue.items[by_url[urls[5]]].update(status="retry", attempts=2, retry_at=(now+timedelta(days=1)).isoformat())
    queue.items[by_url[urls[6]]].update(status="processing", attempts=4)
    queue.save()
    before = copy.deepcopy(queue.items); before_bytes = queue.path.read_bytes()
    selected_path = manifest(tmp_path, [SECOND, FIRST] + urls[3:])
    selected = load_queue_selection(selected_path, [SOURCE])
    # The manifest's reverse order cannot become scheduling priority.
    scheduled = [(by_url[FIRST], queue.items[by_url[FIRST]]),
                 (by_url[OUTSIDE], queue.items[by_url[OUTSIDE]]),
                 (by_url[SECOND], queue.items[by_url[SECOND]]),
                 (by_url[urls[6]], queue.items[by_url[urls[6]]])]
    ready, audit = select_ready(selected, queue.items, scheduled)
    assert [item["raw"]["url"] for _, item in ready] == [FIRST, SECOND]
    assert audit["skipped_terminal_urls"] == sorted(urls[3:5])
    assert audit["skipped_not_due_urls"] == [urls[5]]
    assert audit["skipped_in_progress_urls"] == [urls[6]]
    assert audit["outside_selection_pending_url_count"] == 1
    assert audit["matched_existing_url_count"] == len(selected.urls)
    assert audit["sha256"] == hashlib.sha256(selected_path.read_bytes()).hexdigest()
    assert audit["reason"] == "explicit_queue_selection"
    assert queue.items == before and queue.path.read_bytes() == before_bytes


def test_absent_wrong_source_or_ambiguous_queue_identity_is_fail_closed(tmp_path):
    selection = load_queue_selection(manifest(tmp_path, [FIRST]), [SOURCE])
    wrong_source = dict(source="minsal", raw=dict(url=FIRST), status="pending")
    with pytest.raises(ValueError, match="absent"):
        select_ready(selection, {"other": wrong_source}, [])
    item = dict(source=SOURCE, raw=dict(url=FIRST), status="pending")
    with pytest.raises(ValueError, match="multiple durable"):
        select_ready(selection, {"one": item, "two": copy.deepcopy(item)}, [])


def configure_engine(tmp_path, monkeypatch, discovered, args):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/sources.json").write_bytes((ROOT / "config/sources.json").read_bytes())
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setattr(engine_cli, "seed_from_history", lambda root: None)
    calls = []
    class Scout:
        def __init__(self, source):
            assert source == SOURCE
            self.discovery_audit = []
        def discover(self):
            calls.append("complete_discovery")
            return discovered
    monkeypatch.setattr(engine_cli, "CuratedBetaSourceScout", Scout)
    monkeypatch.setattr(sys, "argv", ["engine_cli", "--sources", SOURCE, *args])
    return calls


def test_real_engine_validates_existing_urls_after_complete_discovery_before_budget_or_start(tmp_path, monkeypatch):
    path = manifest(tmp_path, [FIRST, SECOND])
    calls = configure_engine(tmp_path, monkeypatch, [raw(FIRST), raw(OUTSIDE)], ["--queue-selection", str(path)])
    def forbidden(*args):
        raise AssertionError("Invalid selection must not reach a budget or processing call")
    monkeypatch.setattr(engine_cli, "has_capacity", forbidden)
    monkeypatch.setattr(engine_cli, "process_curated_beta_source", forbidden)
    with pytest.raises(SystemExit) as exc:
        engine_cli.main()
    assert exc.value.code == 2 and calls == ["complete_discovery"]
    queue = PendingQueue(tmp_path / "data/state/pending_queue.json")
    assert {item["raw"]["url"] for item in queue.items.values()} == {FIRST, OUTSIDE}
    assert all(item["status"] == "pending" and item["attempts"] == 0 for item in queue.items.values())
    audit = json.loads((tmp_path / "data/state/discovery_run.json").read_text())
    assert audit["sources"][SOURCE]["discovered"] == 2
    assert audit["processing_attempts"] == 0
    assert SECOND in audit["processing_selection"]["validation_error"]


def test_real_engine_intersects_after_discovery_and_skips_terminal_idempotently(tmp_path, monkeypatch):
    path = manifest(tmp_path, [FIRST, SECOND])
    calls = configure_engine(tmp_path, monkeypatch, [raw(FIRST), raw(SECOND), raw(OUTSIDE)],
                             ["--queue-selection", str(path)])
    queue = PendingQueue(tmp_path / "data/state/pending_queue.json")
    queue.discover(SOURCE, [raw(SECOND)])
    terminal_key = fingerprint(raw(SECOND))
    queue.items[terminal_key].update(status="published", attempts=2)
    queue.save(); preserved_terminal = copy.deepcopy(queue.items[terminal_key])
    # This is an engine membership test; it makes no LLM/publication claim.
    def processor(item, config):
        calls.append(item.url)
        item.metadata["rejection_reason"] = "unit_membership_check"
        return None
    monkeypatch.setattr(engine_cli, "process_curated_beta_source", processor)
    monkeypatch.setattr(engine_cli, "has_capacity", lambda tier: True)
    monkeypatch.setattr(engine_cli, "ai_budget_status", lambda: {})
    engine_cli.main()
    queue = PendingQueue(tmp_path / "data/state/pending_queue.json")
    by_url = {item["raw"]["url"]: item for item in queue.items.values()}
    assert calls == ["complete_discovery", FIRST]
    assert by_url[SECOND] == preserved_terminal
    assert by_url[OUTSIDE]["status"] == "pending" and by_url[OUTSIDE]["attempts"] == 0
    assert by_url[FIRST]["attempts"] == 1 and by_url[FIRST]["reason"] == "unit_membership_check"
    audit = json.loads((tmp_path / "data/state/discovery_run.json").read_text())
    assert audit["sources"][SOURCE]["discovered"] == 3
    assert audit["processing_attempts"] == 1
    assert audit["processing_selection"]["skipped_terminal_urls"] == [SECOND]
    assert audit["processing_selection"]["ready_selected_urls"] == [FIRST]
    engine_cli.main()
    assert calls == ["complete_discovery", FIRST, "complete_discovery"]
    assert json.loads((tmp_path / "data/state/discovery_run.json").read_text())["processing_attempts"] == 0


def test_discovery_only_with_selection_retains_all_discovered_items_without_processing(tmp_path, monkeypatch):
    path = manifest(tmp_path, [FIRST])
    configure_engine(tmp_path, monkeypatch, [raw(FIRST), raw(OUTSIDE)],
                     ["--queue-selection", str(path), "--discovery-only"])
    def forbidden(*args):
        raise AssertionError("Discovery-only must not start processing or inspect budget")
    monkeypatch.setattr(engine_cli, "has_capacity", forbidden)
    monkeypatch.setattr(engine_cli, "ai_budget_status", lambda: {})
    engine_cli.main()
    queue = PendingQueue(tmp_path / "data/state/pending_queue.json")
    assert len(queue.items) == 2
    assert all(item["attempts"] == 0 and item["status"] == "pending" for item in queue.items.values())
    audit = json.loads((tmp_path / "data/state/discovery_run.json").read_text())
    assert audit["processing_selection"]["outside_selection_pending_url_count"] == 1
    assert audit["processing_attempts"] == 0
