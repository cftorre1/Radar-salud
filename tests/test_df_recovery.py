import json
from datetime import datetime, timezone

import pytest

from radar_salud.df_article import parse_df_article
from radar_salud.source_scouts import DfHealthScout
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, fingerprint

URL = "https://www.df.cl/economia-y-politica/actualidad/aluvion-en-las-condes-obliga-a-cerrar-por-semanas-la-clinica-san-carlos"


def test_recorded_real_publisher_metadata_samples():
    # Recorded Work3 metadata, NOT freshly fetched full original HTML.
    from pathlib import Path
    audit = json.loads((Path(__file__).resolve().parents[1] / "data/audits/work3_adversarial_2026_10_11_supplement.json").read_text())
    samples = audit["findings"][0]["evidence"]["samples"]
    for sample in samples:
        meta = sample["meta_dates"][0]
        html = f'<meta name="{meta["name"]}" content="{meta["content"]}">'
        parsed = parse_df_article(html, sample["url"])
        assert parsed["event_date"] == meta["content"][:10]
        assert parsed["metadata"]["publication_timestamp"] == meta["content"]
        assert parsed["metadata"]["publication_date_source"] == "cxenseparse:recs:publishtime"


def test_jsonld_publication_excludes_modification_recommendations_and_script_noise():
    nodes = {"@graph": [{"@type": "NewsArticle", "url": URL, "datePublished": "2026-10-10T16:29:59Z", "dateModified": "2026-10-11T03:00:00Z", "articleBody": "La clínica cerró y trasladó sus pacientes."},
                         {"@type": "NewsArticle", "url": "https://www.df.cl/other/recommendation", "datePublished": "2020-01-01"}]}
    html = '<nav>Fecha actual 2026-10-11. Inversión, capital, isapres.</nav><script>' + 'secret menu ' * 800 + '</script>'
    html += '<script type="application/ld+json">' + json.dumps(nodes) + '</script>'
    parsed = parse_df_article(html, URL)
    assert parsed["event_date"] == "2026-10-10"
    assert parsed["metadata"]["page_text"] == "La clínica cerró y trasladó sus pacientes."
    assert len(parsed["metadata"]["publication_date_candidates"]) == 1


def test_conflicting_dates_are_held_with_both_original_observations():
    html = '<meta name="cXenseParse:recs:publishtime" content="2026-10-07T22:54:15Z">'
    html += '<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-10-08T12:00:00Z"}</script>'
    parsed = parse_df_article(html, URL)
    assert parsed["event_date"] is None
    assert parsed["metadata"]["publication_date_conflict"]
    assert len(parsed["metadata"]["publication_date_candidates"]) == 2
    visible = parse_df_article('<meta name="cXenseParse:recs:publishtime" content="2026-10-07T22:54:15Z"><p>Publicado: jueves 8 de octubre de 2026</p>', URL)
    assert visible["event_date"] is None
    assert visible["metadata"]["publication_date_conflict"]


def test_chile_day_not_utc_day_and_no_nav_or_incident_date_fallback():
    html = '<meta name="cXenseParse:recs:publishtime" content="2026-10-11T01:00:00Z">'
    assert parse_df_article(html, URL)["event_date"] == "2026-10-10"
    assert parse_df_article('<nav>10 de octubre de 2026</nav><article><p>El incidente ocurrió el 9 de octubre de 2026.</p></article>', URL)["event_date"] is None


def test_listing_failure_is_not_successful_empty_discovery(monkeypatch):
    def blocked(url):
        raise OSError("CONNECT 403")
    monkeypatch.setattr("radar_salud.source_scouts.fetch_html", blocked)
    with pytest.raises(RuntimeError, match="DF listing unavailable"):
        DfHealthScout().discover()


def test_body_skips_unrelated_navigation_terms():
    html = '<nav>Salud isapres inversión</nav><article><p>Terremoto en Panamá.</p></article><aside>Inversión clínica</aside>'
    assert parse_df_article(html, URL)["metadata"]["page_text"] == "Terremoto en Panamá."


NOW = datetime(2026, 10, 11, 5, tzinfo=timezone.utc)
CAPTURE = datetime(2026, 10, 10, 22, 23, tzinfo=timezone.utc)


def _raw(title="Clínica San Carlos suspende operaciones", dated=False):
    return RawItem("diario_financiero", title, URL, "Diario Financiero", "press_high_trust",
                   "2026-10-10" if dated else None, raw_text="La clínica trasladó todos sus pacientes.",
                   metadata={"page_text": "La clínica trasladó todos sus pacientes y suspendió operaciones. " * 5,
                             "publication_date_source": "cxenseparse:recs:publishtime"} if dated else {})


def test_seen_legacy_pending_rehydrated_live_without_erasing_capture(tmp_path):
    queue = PendingQueue(tmp_path / "q.json")
    original = _raw()
    queue.discover("diario_financiero", [original], now=CAPTURE, last_discovered_at="2026-10-09T22:00:00+00:00")
    key = fingerprint(original)
    before = json.loads(queue.path.read_text())[key]
    assert queue.discover("diario_financiero", [_raw(dated=True)], seen=[key], now=NOW,
                          last_discovered_at="2026-10-11T04:00:00+00:00") == 0
    item = PendingQueue(queue.path).items[key]
    assert (item["lane"], item["status"], item["attempts"]) == ("LIVE", "pending", 0)
    assert item["detected_at"] == before["detected_at"]
    assert item["recovery_observations"][0]["before"] == before
    queue.discover("diario_financiero", [_raw(dated=True)], now=NOW, last_discovered_at=NOW.isoformat())
    assert len(queue.items[key]["recovery_observations"]) == 1


def test_only_technical_undated_rejection_reopens_and_duplicate_url_is_retained(tmp_path):
    queue = PendingQueue(tmp_path / "q.json")
    original = _raw()
    duplicate = _raw("Otro título para el mismo artículo y bajada")
    queue.discover("diario_financiero", [original], now=CAPTURE)
    key = fingerprint(original)
    queue.start(key)
    queue.finish(key, "rejected", "processor_rejected", now=CAPTURE)
    # Simulate legacy changed-deck duplicates, before URL reconciliation existed.
    from dataclasses import asdict
    queue.items[fingerprint(duplicate)] = {**queue.items[key], "raw": asdict(duplicate), "status": "pending", "reason": None, "attempts": 0}
    queue.save()
    queue.discover("diario_financiero", [_raw(dated=True)], seen=[key], now=NOW, last_discovered_at=CAPTURE.isoformat())
    assert len(queue.ready(NOW)) == 1
    assert len(queue.items) == 2
    retained = queue.items[key]
    assert retained["status"] == "superseded"
    assert retained["recovery_observations"][0]["before"]["reason"] == "processor_rejected"
    primary = queue.ready(NOW)[0][1]
    assert primary["lane"] == "LIVE"
    queue.finish(queue.ready(NOW)[0][0], "rejected", "media_score_below_72", now=NOW)
    queue.discover("diario_financiero", [_raw(dated=True)], now=NOW, last_discovered_at=CAPTURE.isoformat())
    assert not queue.ready(NOW)


def test_generic_undated_rejection_recovers_without_resetting_attempts(tmp_path):
    queue = PendingQueue(tmp_path / "q.json")
    raw = _raw()
    queue.discover("diario_financiero", [raw], now=CAPTURE)
    key = fingerprint(raw)
    queue.start(key)
    queue.finish(key, "rejected", "processor_rejected", now=CAPTURE)
    queue.discover("diario_financiero", [_raw(dated=True)], seen=[key], now=NOW, last_discovered_at=CAPTURE.isoformat())
    assert queue.items[key]["status"] == "pending"
    assert queue.items[key]["attempts"] == 1
    assert queue.items[key]["recovery_observations"][0]["before"]["status"] == "rejected"


def test_history_prevents_republishing_and_date_conflict_never_reopens(tmp_path):
    queue = PendingQueue(tmp_path / "q.json")
    original = _raw()
    queue.discover("diario_financiero", [original], now=CAPTURE)
    key = fingerprint(original)
    conflicting = _raw(dated=True)
    conflicting.metadata["publication_date_conflict"] = True
    queue.discover("diario_financiero", [conflicting], now=NOW, last_discovered_at=CAPTURE.isoformat())
    assert queue.items[key]["raw"]["event_date"] is None
    queue.discover("diario_financiero", [_raw(dated=True)], now=NOW, published_urls=[URL])
    assert queue.items[key]["status"] == "superseded"
    assert queue.items[key]["reason"] == "already_published_in_history"
    assert not queue.ready(NOW)
