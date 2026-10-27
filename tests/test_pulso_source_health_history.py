"""Actual ALL37 Pulso history + ALL897 Native records; no AI or live publisher."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sys

import pytest

from radar_salud import engine_cli, paths
from radar_salud.source_health import record

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/pulso_source_health_real"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_bytes())
PACKED = (FIXTURES / MANIFEST["path"]).read_bytes()
assert hashlib.sha256(PACKED).hexdigest() == MANIFEST["gzip_sha256"]
ENCODED = gzip.decompress(PACKED)
assert hashlib.sha256(ENCODED).hexdigest() == MANIFEST["uncompressed_sha256"]
OBSERVED = json.loads(ENCODED)


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def poll(tmp_path, history=None, queue=None, rows=None, published=0):
    health = tmp_path / "data/source_health.json"
    if not health.exists():
        write_json(health, OBSERVED["source_health_document"])
    record(tmp_path, "pulso_latercera", name="Pulso / La Tercera", discovered=1741,
           new=0, published=published, rows=rows or [], pending=0,
           published_history=OBSERVED["history_document"]["signals"] if history is None else history,
           source_queue=list(OBSERVED["pulso_queue"].values()) if queue is None else queue,
           latest_original_at="2026-10-11", evaluation_performed=published > 0)
    return json.loads(health.read_bytes())["sources"]["pulso_latercera"]


def test_all37_actual_history_removes_withdrawn_oct11_and_keeps17_publications_without_new_ai(tmp_path):
    history = deepcopy(OBSERVED["history_document"]["signals"])
    queue = deepcopy(list(OBSERVED["pulso_queue"].values()))
    assert len(history) == 934
    pulso = [row for row in history if row.get("source_name") == "Pulso / La Tercera"]
    native = [row for row in history if row.get("source_name") != "Pulso / La Tercera"]
    assert len(pulso) == 37 and len(native) == 897
    assert canonical_sha(native) == MANIFEST["native_history_canonical_sha256"]
    assert canonical_sha(pulso) == MANIFEST["pulso_history_canonical_sha256"]
    before = deepcopy((history, queue))
    original_health = OBSERVED["source_health_document"]["sources"]
    assert original_health["pulso_latercera"]["last_signal_at"] == "2026-10-11"
    current = poll(tmp_path, history, queue)
    assert current["last_signal_at"] == "2026-10-10"
    # 16 since Dirección 27-oct-2026: "Senadores de oposición … infraestructura crítica" fails the health-nexus rule.
    assert current["published_total"] == 16
    assert current["published"] == 0 and current["new"] == 0
    assert current["last_signal_at_basis"] == "effective_verified_published_history"
    assert current["latest_original_at"] == "2026-10-11"
    assert current["editorial_outcome"] == "not_evaluated"
    assert (history, queue) == before
    after_sources = json.loads((tmp_path / "data/source_health.json").read_bytes())["sources"]
    assert {key:row for key,row in after_sources.items() if key != "pulso_latercera"} == {
        key:row for key,row in original_health.items() if key != "pulso_latercera"}
    assert len(after_sources) == len(original_health)
    # A repeat with no newly produced publication cannot resurrect Oct11.
    assert poll(tmp_path, history, queue)["last_signal_at"] == "2026-10-10"


def test_later_withdrawal_recalculates_backwards_and_empty_effective_history_clears_stale_signal(tmp_path):
    history = deepcopy(OBSERVED["history_document"]["signals"])
    assert poll(tmp_path, history)["last_signal_at"] == "2026-10-10"
    # Explicit unit editorial-withdrawal scenarios; observed fixture bytes and
    # actual recorded publisher/model decisions are never modified.
    for row in history:
        if row.get("source_name") == "Pulso / La Tercera" and row.get("event_date") == "2026-10-10":
            row["feed_visibility"] = False
    assert poll(tmp_path, history)["last_signal_at"] == "2026-10-09"
    for row in history:
        if row.get("source_name") == "Pulso / La Tercera":
            row["editorial_decision"] = "group"
    empty = poll(tmp_path, history)
    assert empty["last_signal_at"] is None and empty["published_total"] == 0
    assert empty["content_freshness"] == "unknown" and empty["latest_original_at"] == "2026-10-11"


def actual_published_pair():
    row = next(row for row in OBSERVED["history_document"]["signals"]
               if row.get("source_name") == "Pulso / La Tercera" and row.get("feed_visibility") is True)
    entry = next(entry for entry in OBSERVED["pulso_queue"].values()
                 if entry["raw"]["url"] == row["source_url"])
    return deepcopy(row), deepcopy(entry)


@pytest.mark.parametrize("mutate", [
    lambda row, entry: row.update(source_name="Other source"),
    lambda row, entry: row.update(source_type="official"),
    lambda row, entry: row.update(evidence_maturity="official_confirmed"),
    lambda row, entry: row.update(editorial_relevance=71),
    lambda row, entry: row.update(editorial_relevance=True),
    lambda row, entry: row.update(source_quality_gate="pending"),
    lambda row, entry: row.update(feed_visibility=False),
    lambda row, entry: row.update(editorial_decision="group"),
    lambda row, entry: row["editorial_review"].update(decision="reject"),
    lambda row, entry: row.update(source_url="https://fake.example/pulso/noticia/news/"),
    lambda row, entry: row.update(event_date="2026-10-11"),
    lambda row, entry: row.update(publication_date=None),
    lambda row, entry: row.update(why_it_matters="Describe un cambio material para una parte relevante del sistema de salud"),
    lambda row, entry: entry.update(status="retry"),
    lambda row, entry: entry["raw"].update(source_slug="other_source"),
    lambda row, entry: entry["raw"]["metadata"]["editorial_assessment"].update(decision="pending"),
    lambda row, entry: entry["raw"]["metadata"].update(editorial_hold="unresolved_editorial_review"),
    lambda row, entry: entry["raw"]["metadata"].update(analysis_input_complete=False),
    lambda row, entry: entry["raw"]["metadata"].update(pulso_editorial_proof_validation={"decision":"deferred"}),
    lambda row, entry: entry["raw"].update(event_date="2026-10-11"),
    lambda row, entry: entry["raw"]["metadata"].update(article_verified=False),
    lambda row, entry: entry["raw"]["metadata"].update(primary_identity_verified=False),
    lambda row, entry: entry["raw"]["metadata"].update(publication_date_verified=False),
    lambda row, entry: entry["raw"]["metadata"].update(article_body_complete=False),
    lambda row, entry: entry["raw"]["metadata"].update(article_body_sha256="0" * 64),
    lambda row, entry: entry["raw"]["metadata"].update(canonical_url="https://www.latercera.com/pulso/noticia/unrelated/"),
    lambda row, entry: entry["raw"]["metadata"].update(primary_item_binding={"verified":False}),
])
def test_unverified_identity_dates_gate_or_editorial_withdrawal_cannot_set_last_signal(tmp_path, mutate):
    row, entry = actual_published_pair()
    mutate(row, entry)
    before = deepcopy((row, entry))
    current = poll(tmp_path, [row], [entry], rows=[row], published=1)
    assert current["last_signal_at"] is None and current["published_total"] == 0
    assert (row, entry) == before


def test_only_pulso_uses_effective_history_and_other_source_monotonic_semantics_remain(tmp_path):
    write_json(tmp_path / "data/source_health.json", {"sources":{"deis":{"last_signal_at":"2026-10-11"}}})
    record(tmp_path, "deis", name="DEIS", discovered=1, new=0, published=0,
           rows=[{"event_date":"2026-10-10"}], published_history=[], source_queue=[])
    health = json.loads((tmp_path / "data/source_health.json").read_bytes())["sources"]["deis"]
    assert health["last_signal_at"] == "2026-10-11"
    assert "published_total" not in health and "last_signal_at_basis" not in health


def test_core_empty_poll_passes_full934_history_and_preserves_all897_native_records(tmp_path, monkeypatch):
    write_json(tmp_path / "config/sources.json", json.loads((ROOT / "config/sources.json").read_bytes()))
    history_path = tmp_path / "data/history/superintendencia_signals.json"
    write_json(history_path, OBSERVED["history_document"])
    history_bytes = history_path.read_bytes()
    write_json(tmp_path / "data/state/pending_queue.json", OBSERVED["pulso_queue"])
    write_json(tmp_path / "data/source_health.json", OBSERVED["source_health_document"])
    received = {}
    original_record = engine_cli.health_record

    class EmptyUnitScout:
        def __init__(self, slug):
            assert slug == "pulso_latercera"
            self.discovery_audit = []

        def discover(self):
            return []

    def observe_arguments(root, slug, **kwargs):
        assert slug == "pulso_latercera"
        received.update(kwargs)
        original_record(root, slug, **kwargs)

    monkeypatch.setattr(engine_cli, "CuratedBetaSourceScout", EmptyUnitScout)
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setattr(engine_cli, "ai_budget_status", lambda: {})
    monkeypatch.setattr(engine_cli, "health_record", observe_arguments)
    monkeypatch.setattr(sys, "argv", ["engine_cli", "--sources", "pulso_latercera", "--discovery-only"])
    engine_cli.main()
    assert received["published_history"] == OBSERVED["history_document"]["signals"]
    assert len(received["published_history"]) == 934 and len(received["source_queue"]) == 37
    assert received["rows"] == [] and received["published"] == 0
    assert history_path.read_bytes() == history_bytes
    actual = json.loads(history_path.read_bytes())["signals"]
    native = [row for row in actual if row.get("source_name") != "Pulso / La Tercera"]
    assert len(native) == 897 and canonical_sha(native) == MANIFEST["native_history_canonical_sha256"]
    assert json.loads((tmp_path / "data/state/pending_queue.json").read_bytes()) == OBSERVED["pulso_queue"]
    current = json.loads((tmp_path / "data/source_health.json").read_bytes())["sources"]["pulso_latercera"]
    assert current["last_signal_at"] == "2026-10-10" and current["published_total"] == 16
    assert current["latest_original_at"] == "2026-10-11"


def test_same_url_different_actual_primary_with_consistent_self_hash_cannot_claim_old_publication(tmp_path):
    row, entry = actual_published_pair()
    alternate = next(item for item in OBSERVED["pulso_queue"].values()
                     if item["raw"]["metadata"].get("publisher_document_type") == "liveblog")
    metadata = entry["raw"]["metadata"]
    # Actual retained bodies are used; only this isolated queue copy is
    # transplanted to reproduce the independent review's identity attack.
    metadata["page_text"] = alternate["raw"]["metadata"]["page_text"]
    metadata["article_body_sha256"] = hashlib.sha256(metadata["page_text"].encode()).hexdigest()
    metadata["article_body_characters"] = len(metadata["page_text"])
    assert metadata["article_body_sha256"] != row["editorial_review"]["original_body_sha256"]
    current = poll(tmp_path, [row], [entry])
    assert current["last_signal_at"] is None and current["published_total"] == 0


@pytest.mark.parametrize("field", ["analysis_base", "history_review", "queue_review", "request", "model_text"])
def test_any_existing_editorial_body_or_request_pin_conflict_blocks_current_signal(tmp_path, field):
    row, entry = actual_published_pair()
    metadata = entry["raw"]["metadata"]
    if field == "analysis_base":
        metadata["analysis_base_article_body_sha256"] = "0" * 64
    elif field == "history_review":
        row["editorial_review"]["original_body_sha256"] = "0" * 64
    elif field == "queue_review":
        metadata["editorial_review"]["original_body_sha256"] = "0" * 64
    elif field == "request":
        metadata["analysis_request_input_sha256"] = "0" * 64
    else:
        metadata["analysis_input_body_sha256"] = "0" * 64
    current = poll(tmp_path, [row], [entry])
    assert current["last_signal_at"] is None and current["published_total"] == 0


def test_actual_legacy_without_new_binding_and_liveblog_augmented_request_remain_eligible(tmp_path):
    row, entry = actual_published_pair()
    assert "primary_item_binding" not in entry["raw"]["metadata"]
    assert poll(tmp_path / "legacy", [row], [entry])["published_total"] == 1
    live_entry = deepcopy(next(item for item in OBSERVED["pulso_queue"].values()
                              if item["raw"]["metadata"].get("publisher_document_type") == "liveblog"
                              and item["status"] == "published"))
    live_row = deepcopy(next(row for row in OBSERVED["history_document"]["signals"]
                             if row.get("source_url") == live_entry["raw"]["url"]))
    metadata = live_entry["raw"]["metadata"]
    assert metadata["analysis_input_body_sha256"] != metadata["analysis_base_article_body_sha256"]
    assert metadata["analysis_base_article_body_sha256"] == live_row["editorial_review"]["original_body_sha256"]
    assert poll(tmp_path / "liveblog", [live_row], [live_entry])["published_total"] == 1
