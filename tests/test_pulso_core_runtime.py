"""Core replay with synthetic article HTML and mocked editorial analysis.

This proves registration, queue outcomes and feed propagation, not live coverage.
"""
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar_salud import engine_cli, llm_analysis, paths
from radar_salud.beta_sources import CuratedBetaSourceScout, media_gate_accepts
from radar_salud.history import load_history
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue

ROOT = Path(__file__).resolve().parents[1]
BODY = "La clínica suspendió operaciones y trasladó sus pacientes a otros establecimientos de su red asistencial. El cierre temporal reduce capacidad y obliga a redistribuir consultas, procedimientos y prestaciones para asegurar continuidad."


@pytest.mark.parametrize("partial", [False, True])
def test_core_pulso_publication_rejection_pending_and_feed_trace(tmp_path, monkeypatch, partial):
    now = datetime.now(timezone.utc)
    day = (now - timedelta(days=1)).date().isoformat()
    (tmp_path / "config").mkdir()
    (tmp_path / "config/sources.json").write_bytes((ROOT / "config/sources.json").read_bytes())
    state = tmp_path / "data/state"
    state.mkdir(parents=True)
    # There is no real poll watermark for a newly integrated source: BACKFILL.
    urls = [f"https://www.latercera.com/nacional/noticia/clinica-cierre-{suffix}/"
            for suffix in ("material", "below", "pending")]
    titles = [f"Clínica suspende operaciones y traslada pacientes: {suffix}" for suffix in ("material", "below", "pending")]
    listing = "".join(f'<a href="{url}">{title}</a>' for url, title in zip(urls, titles))
    def detail(url):
        title = titles[urls.index(url)]
        node = {"@type": "NewsArticle", "url": url, "headline": title, "datePublished": day}
        return (f'<link rel="canonical" href="{url}"><script type="application/ld+json">'
                f'{json.dumps(node)}</script><article><h1>{title}</h1><p>{BODY}</p></article>')
    items = CuratedBetaSourceScout("pulso_latercera").discover_from_html(listing, detail)
    unrelated = RawItem("pulso_latercera", "Banco aumenta capital para inversión inmobiliaria",
                        "https://www.latercera.com/pulso/noticia/banco-capital/", "Pulso / La Tercera", "press_high_trust",
                        day, "La inversión y el capital bancario financian proyectos inmobiliarios. " * 4,
                        {"page_text": "La inversión y el capital bancario financian proyectos inmobiliarios. " * 4,
                         "article_verified": True, "market_role": "media", "source_quality_gate": "passed"})
    class Pulso:
        def __init__(self, slug):
            assert slug == "pulso_latercera"
            self.discovery_audit = [{"url": urls[0], "status": "discovered", "publication_date": day}]
            if partial:
                self.discovery_audit.append({"url": "https://www.latercera.com/pulso/noticia/clinica-unreadable/",
                                             "status": "detail_error", "reason": "missing_or_invalid_publication_date"})
        def discover(self):
            return items + [unrelated]
    monkeypatch.setattr(engine_cli, "CuratedBetaSourceScout", Pulso)
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setattr(engine_cli, "seed_from_history", lambda root: None)
    monkeypatch.setattr(engine_cli, "has_capacity", lambda kind: True)
    calls = []
    def analysis(**args):
        calls.append(args["title"])
        if args["title"].endswith("pending"):
            return None
        return dict(relevance_score=71 if args["title"].endswith("below") else 80,
                    what_happened="La clínica reporta un cierre temporal y el traslado de pacientes a otros establecimientos de su red.",
                    why_it_matters="La suspensión reduce capacidad asistencial disponible y redistribuye la demanda entre los centros de la red.")
    monkeypatch.setattr(llm_analysis, "analyze_news", analysis)
    monkeypatch.setattr(sys, "argv", ["engine_cli", "--sources", "pulso_latercera"])
    other = RawItem("minsal", "Noticia que debe permanecer intacta", "https://example.org/other", "Minsal", "official", day)
    queue = PendingQueue(state / "pending_queue.json")
    queue.discover("minsal", [other])
    preserved = json.loads(json.dumps(next(iter(queue.items.values()))))
    engine_cli.main()
    discovery = json.loads((state / "discovery_run.json").read_text())
    assert discovery["runtime"] == "daily_core"
    assert discovery["sources"]["pulso_latercera"]["discovered"] == 4
    assert set(discovery["sources"]) == {"pulso_latercera"}
    assert discovery["sources"]["pulso_latercera"]["error_type"] == ("partial_discovery" if partial else None)
    queue = PendingQueue(state / "pending_queue.json")
    by_url = {item["raw"]["url"]: item for item in queue.items.values()}
    assert by_url[urls[0]]["status"] == "published"
    assert by_url[urls[0]]["lane"] == "BACKFILL"
    assert by_url[urls[1]]["reason"] == "editorial_relevance_below_threshold"
    assert by_url[urls[1]]["raw"]["metadata"]["editorial_assessment"]["threshold"] == 72
    assert by_url[urls[2]]["status"] == "retry"
    assert by_url[urls[2]]["raw"]["metadata"]["editorial_assessment"]["reason"] == "analysis_unavailable"
    assert by_url[unrelated.url]["reason"] == "media_materiality_prefilter"
    assert unrelated.title not in calls
    assert by_url[other.url] == preserved
    history = load_history(tmp_path / "data/history/superintendencia_signals.json")
    assert len(history) == 1
    row = history[0]
    assert row["evidence_maturity"] == "media_reported"
    assert row["what_happened"].startswith("Según Pulso / La Tercera,")
    assert row["publication_date"] == day
    assert row["scopes"] == ["Prestadores"]
    spec = importlib.util.spec_from_file_location("pulso_snapshot", ROOT / "scripts/export_web_snapshot.py")
    curator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(curator)
    feed = curator.curate(history, resolve_external=False)
    assert len(feed) == 1 and feed[0]["source_url"] == urls[0]
    assert feed[0]["evidence_maturity"] == "media_reported"
    assert feed[0]["publication_date"] == day
    detected = by_url[urls[0]]["detected_at"]
    engine_cli.main()
    queue = PendingQueue(state / "pending_queue.json")
    assert len(load_history(tmp_path / "data/history/superintendencia_signals.json")) == 1
    assert next(item for item in queue.items.values() if item["raw"]["url"] == urls[0])["detected_at"] == detected
    health = json.loads((tmp_path / "data/source_health.json").read_text())["sources"]["pulso_latercera"]
    assert health["pending"] == 1 and health["rejected"] == 2


def test_generic_finance_excluded_and_strategic_health_prefilter_kept():
    assert not media_gate_accepts("Inversión inmobiliaria y capital bancario", "Bonos, utilidad y financiamiento")
    for title in ("Clínica anuncia cierre temporal y traslado de pacientes",
                  "Fonasa actualiza planes y financiamiento",
                  "Isapres ajustan tarifas y fuerza de ventas",
                  "Senior housing: residencias para adultos mayores reciben inversión",
                  "Presupuesto de salud y listas de espera",
                  "Clínica anuncia adquisición de control"):
        assert media_gate_accepts(title)
