"""Core replay with synthetic article HTML and mocked editorial analysis.

This proves registration, queue outcomes and feed propagation, not live coverage.
"""
import importlib.util
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar_salud import engine_cli, llm_analysis, paths
from radar_salud.beta_sources import CuratedBetaSourceScout, media_gate_accepts
from radar_salud.history import load_history
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, fingerprint
from pulso_editorial_test_support import valid_assessment

ROOT = Path(__file__).resolve().parents[1]
BODY = "La clínica suspendió operaciones y trasladó sus pacientes a otros establecimientos de su red asistencial. El cierre temporal reduce capacidad y obliga a redistribuir consultas, procedimientos y prestaciones para asegurar continuidad."
BODY_PROOF = {"article_body_sha256": hashlib.sha256(BODY.encode("utf-8")).hexdigest(),
              "article_body_characters": len(BODY)}


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
                         "article_body_sha256": hashlib.sha256(("La inversión y el capital bancario financian proyectos inmobiliarios. " * 4).encode()).hexdigest(),
                         "article_verified": True, "market_role": "media", "source_quality_gate": "passed"})
    unrelated.metadata.update(canonical_url=unrelated.url, publication_date=day)
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
        return valid_assessment(dict(relevance_score=71 if args["title"].endswith("below") else 80,
                    what_happened="La clínica reporta un cierre temporal y el traslado de pacientes a otros establecimientos de su red.",
                    why_it_matters="La suspensión reduce capacidad asistencial disponible y redistribuye la demanda entre los centros de la red.",
                    reason="El cierre y traslado afectan capacidad asistencial de la red."), args)
    monkeypatch.setattr(llm_analysis, "analyze_news", analysis)
    monkeypatch.setattr(sys, "argv", ["engine_cli", "--sources", "pulso_latercera"])
    other = RawItem("minsal", "Noticia que debe permanecer intacta", "https://example.org/other", "Minsal", "official",
                    (now - timedelta(days=180)).date().isoformat())
    queue = PendingQueue(state / "pending_queue.json")
    queue.discover("minsal", [other])
    # Deliberately recover an old pending row to test selected-source isolation.
    next(iter(queue.items.values()))["status"] = "pending"
    queue.save()
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
    assert by_url[urls[2]]["reason"] == "analysis_unavailable"
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


@pytest.mark.parametrize("missing,reason", [
    ("pulso_editorial_proof", "pulso_editorial_proof_missing"),
    ("_pulso_analysis_meta", "pulso_editorial_model_binding_mismatch"),
])
def test_core_pulso_without_proof_or_request_binding_remains_pending(monkeypatch, missing, reason):
    from radar_salud.beta_sources import process_curated_beta_source
    from radar_salud.processing import DeferredProcessing
    raw = RawItem("pulso_latercera", "Clínica suspende operaciones y traslada pacientes",
                  "https://www.latercera.com/nacional/noticia/clinica-missing-proof/",
                  "Pulso / La Tercera", "press_high_trust",
                  datetime.now(timezone.utc).date().isoformat(), BODY,
                  {"article_verified": True, "page_text": BODY, **BODY_PROOF,
                   "market_role": "media", "source_quality_gate": "passed"})
    raw.metadata.update(canonical_url=raw.url, publication_date=raw.event_date)
    def analysis(**request):
        result = valid_assessment({
            "relevance_score": 80,
            "what_happened": "La clínica reporta un cierre temporal y traslado de pacientes en su red.",
            "why_it_matters": "El cierre reduce capacidad y obliga a redistribuir consultas y prestaciones.",
            "reason": "La interrupción de la red requiere revisar su capacidad asistencial.",
        }, request)
        del result[missing]
        if missing == "pulso_editorial_proof":
            payload = {key: value for key, value in result.items() if key != "_pulso_analysis_meta"}
            result["_pulso_analysis_meta"]["raw_model_output_sha256"] = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return result
    monkeypatch.setattr(llm_analysis, "analyze_news", analysis)
    with pytest.raises(DeferredProcessing, match=reason):
        process_curated_beta_source(raw, {})
    assert raw.metadata["editorial_assessment"]["decision"] == "pending"
    assert raw.metadata["editorial_assessment"]["reason"] == reason
    assert raw.metadata["editorial_assessment"]["threshold"] == 72
    assert "rejection_reason" not in raw.metadata


@pytest.mark.parametrize("title,body", [
    ("Hospital regional reconoce crisis y anuncia cierre de pabellones", "Reduce capacidad y prestaciones de su red."),
    ("Salud reconoce recorte en su presupuesto hospitalario", "Cambia financiamiento de las prestaciones."),
    ("Reforma del aseguramiento sanitario", "La norma modifica cobertura y obligaciones de aseguradores."),
    ("Hospital modifica norma de acreditación", "Nuevas obligaciones operacionales para prestadores."),
])
def test_strategic_changes_are_not_rejected_as_ceremonial_before_analysis(title, body):
    assert media_gate_accepts(title, body)


def test_real_core_discovery_only_does_not_consume_analysis_or_processing_attempts(tmp_path, monkeypatch):
    state = tmp_path / "data/state"; state.mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/sources.json").write_text((ROOT / "config/sources.json").read_text())
    raw = RawItem("pulso_latercera", "Clínica cierra pabellones y traslada pacientes",
                  "https://www.latercera.com/pulso/noticia/clinica-cierra/", "Pulso / La Tercera", "press_high_trust",
                  datetime.now(timezone.utc).date().isoformat(), BODY,
                  {"page_text": BODY, **BODY_PROOF, "article_verified": True, "market_role": "media"})
    monkeypatch.setattr(CuratedBetaSourceScout, "discover", lambda self: [raw])
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setattr(engine_cli, "seed_from_history", lambda root: None)
    def unexpected(**kwargs):
        raise AssertionError("Discovery must consume zero analysis calls")
    monkeypatch.setattr(llm_analysis, "analyze_news", unexpected)
    monkeypatch.setattr(sys, "argv", ["engine_cli", "--sources", "pulso_latercera", "--discovery-only"])
    engine_cli.main()
    item = next(iter(PendingQueue(state / "pending_queue.json").items.values()))
    assert item["status"] == "pending" and item["attempts"] == 0
    assert json.loads((state / "discovery_run.json").read_text())["runtime"] == "daily_core"


def test_pulso_rediscovery_rehydrates_same_url_without_resetting_capture_attempts_or_lane(tmp_path):
    now = datetime.now(timezone.utc)
    url = "https://www.latercera.com/pulso/noticia/clinica-cierre/"
    old = RawItem("pulso_latercera", "Clínica anuncia cierre temporal", url, "Pulso / La Tercera", "press_high_trust",
                  metadata={"capture_method": "verified_original_byline_inventory",
                            "editorial_hold": "possible_duplicate_requires_incremental_review"})
    queue = PendingQueue(tmp_path / "queue.json")
    queue.discover("pulso_latercera", [old], now=now)
    key = fingerprint(old)
    queue.start(key)
    queue.finish(key, "retry", "article_verification_failed", now=now)
    before = dict(queue.items[key])
    verified = RawItem("pulso_latercera", "Clínica suspende operaciones y traslada pacientes", url + "?outputType=base-amp-type",
                       "Pulso / La Tercera", "press_high_trust", now.date().isoformat(), BODY,
                       {"article_verified": True, "primary_identity_verified": True,
                        "publication_date_verified": True, "canonical_url": url,
                        "publication_date": now.date().isoformat(), "page_text": BODY, **BODY_PROOF,
                        "market_role": "media", "source_quality_gate": "passed"})
    assert queue.discover("pulso_latercera", [verified], now=now, last_discovered_at=now.isoformat()) == 0
    item = queue.items[key]
    assert len(queue.items) == 1
    assert item["raw"]["event_date"] == verified.event_date
    for field in ("detected_at", "attempts", "lane", "status", "retry_at"):
        assert item[field] == before[field]
    assert item["lane"] == "BACKFILL"  # Rediscovery is not a new LIVE event.
    assert len(item["raw"]["metadata"]["evidence_revisions"]) == 1
    assert item["raw"]["metadata"]["editorial_hold"] == "possible_duplicate_requires_incremental_review"
    queue.discover("pulso_latercera", [verified], now=now)
    assert len(queue.items[key]["raw"]["metadata"]["evidence_revisions"]) == 1
    queue.finish(key, "rejected", "editorial_relevance_below_threshold", now=now)
    terminal = json.loads(json.dumps(queue.items[key]))
    queue.discover("pulso_latercera", [verified], now=now)
    assert queue.items[key] == terminal  # No automatic reopening of editorial decisions.


def test_known_possible_duplicate_waits_for_incremental_review_without_consuming_analysis(monkeypatch):
    from radar_salud.beta_sources import process_curated_beta_source
    from radar_salud.processing import DeferredProcessing
    raw = RawItem("pulso_latercera", "Presupuesto de salud para reducir listas de espera",
                  "https://www.latercera.com/nacional/noticia/presupuesto-salud/", "Pulso / La Tercera", "press_high_trust",
                  datetime.now(timezone.utc).date().isoformat(), BODY,
                  {"article_verified": True, "page_text": BODY, **BODY_PROOF, "market_role": "media",
                   "editorial_hold": "possible_duplicate_requires_incremental_review"})
    raw.metadata.update(canonical_url=raw.url, publication_date=raw.event_date)
    def unexpected(**kwargs):
        raise AssertionError("Held duplicates must not consume analysis budget")
    monkeypatch.setattr(llm_analysis, "analyze_news", unexpected)
    with pytest.raises(DeferredProcessing, match="incremental-value"):
        process_curated_beta_source(raw, {})
    assert raw.metadata["editorial_assessment"]["reason"] == "possible_duplicate_requires_incremental_review"


@pytest.mark.parametrize('deep_available', [True, False])
def test_fast_budget_stop_leaves_scoped_pulso_pending_without_attempt(tmp_path, monkeypatch, deep_available):
    (tmp_path/'config').mkdir()
    (tmp_path/'config/sources.json').write_bytes((ROOT/'config/sources.json').read_bytes())
    state = tmp_path/'data/state'; state.mkdir(parents=True)
    raw = RawItem('pulso_latercera', 'Clínica cierra pabellones y traslada pacientes',
                  'https://www.latercera.com/pulso/noticia/clinica-budget-stop/',
                  'Pulso / La Tercera', 'press_high_trust',
                  (datetime.now(timezone.utc)-timedelta(days=1)).date().isoformat(), BODY,
                  {'page_text': BODY, **BODY_PROOF, 'article_verified': True, 'market_role': 'media'})
    monkeypatch.setattr(CuratedBetaSourceScout, 'discover', lambda self: [raw])
    monkeypatch.setattr(paths, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(engine_cli, 'seed_from_history', lambda root: None)
    monkeypatch.setattr(engine_cli, 'has_capacity', lambda kind: deep_available if kind=='deep' else False)
    def unexpected(raw, cfg):
        raise AssertionError('Capacity stop must happen before processor/analysis')
    monkeypatch.setattr(engine_cli, 'process_curated_beta_source', unexpected)
    monkeypatch.setattr(sys, 'argv', ['engine_cli', '--sources', 'pulso_latercera'])
    engine_cli.main()
    item = next(iter(PendingQueue(state/'pending_queue.json').items.values()))
    assert item['status']=='pending' and item['attempts']==0
    assert not item.get('retry_at') and item['reason'] is None
    run = json.loads((state/'discovery_run.json').read_text())
    assert run['processing_attempts']==0
    assert run['processing_deferrals']['pulso_latercera'] == {
        'reason': 'fast_analysis_capacity_exhausted', 'required_tier': 'fast', 'before_queue_start': True,
    }


@pytest.mark.parametrize('unscoped', [False, True])
def test_pulso_fast_stop_does_not_starve_other_tier_or_consume_processing_limit(tmp_path, monkeypatch, unscoped):
    (tmp_path/'config').mkdir()
    (tmp_path/'config/sources.json').write_bytes((ROOT/'config/sources.json').read_bytes())
    state = tmp_path/'data/state'; state.mkdir(parents=True)
    day=(datetime.now(timezone.utc)-timedelta(days=1)).date().isoformat()
    pulso = RawItem('pulso_latercera', 'Clínica cierra pabellones y traslada pacientes',
                    'https://www.latercera.com/pulso/noticia/clinica-fast-unavailable/',
                    'Pulso / La Tercera', 'press_high_trust', day, BODY,
                    {'page_text': BODY, **BODY_PROOF, 'article_verified': True, 'market_role': 'media'})
    other = RawItem('diario_oficial', 'Norma sanitaria que requiere análisis de documentos',
                    'https://www.diariooficial.interior.gob.cl/other-deep-document',
                    'Diario Oficial', 'official', day, BODY)
    # Preserve real multi-source scheduling while isolating discovery/network.
    for name in dir(engine_cli):
        candidate = getattr(engine_cli, name)
        if name.endswith('Scout') and isinstance(candidate, type) and hasattr(candidate, 'discover'):
            monkeypatch.setattr(candidate, 'discover', lambda self,*args,**kwargs: [])
    monkeypatch.setattr(CuratedBetaSourceScout, 'discover', lambda self: [pulso])
    monkeypatch.setattr(engine_cli.DiarioOficialHealthScout, 'discover', lambda self,*args,**kwargs: [other])
    monkeypatch.setattr(paths, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(engine_cli, 'seed_from_history', lambda root: None)
    monkeypatch.setattr(engine_cli, 'has_capacity', lambda kind: kind=='deep')
    calls=[]
    def unexpected(raw,cfg):
        raise AssertionError('Pulso must not spend an attempt on unavailable fast capacity')
    def process_deep(raw,cfg):
        assert engine_cli.has_capacity('deep')
        calls.append(raw.source_slug)
        raw.metadata['rejection_reason']='document_not_material_after_review'
        return None
    monkeypatch.setattr(engine_cli, 'process_curated_beta_source', unexpected)
    monkeypatch.setattr(engine_cli, 'process_diario_oficial', process_deep)
    argv=['engine_cli','--limit','1']
    if not unscoped:
        argv += ['--sources','pulso_latercera','diario_oficial']
    monkeypatch.setattr(sys,'argv',argv)
    engine_cli.main()
    by_source={item['source']:item for item in PendingQueue(state/'pending_queue.json').items.values()}
    assert by_source['pulso_latercera']['status']=='pending' and by_source['pulso_latercera']['attempts']==0
    assert by_source['diario_oficial']['status']=='rejected' and by_source['diario_oficial']['attempts']==1
    assert calls==['diario_oficial']
    run=json.loads((state/'discovery_run.json').read_text())
    assert run['processing_attempts']==1
    assert run['processing_deferrals']['pulso_latercera']['reason']=='fast_analysis_capacity_exhausted'
