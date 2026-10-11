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
    unrelated_iso = parse_df_article('<meta name="cXenseParse:recs:publishtime" content="2026-10-08T12:00:00Z"><p>Publicado: jueves 8 de octubre de 2026. Incidente: 2026-10-07.</p>', URL)
    assert unrelated_iso["event_date"] == "2026-10-08"


def test_chile_day_not_utc_day_and_no_nav_or_incident_date_fallback():
    html = '<meta name="cXenseParse:recs:publishtime" content="2026-10-11T01:00:00Z">'
    assert parse_df_article(html, URL)["event_date"] == "2026-10-10"
    assert parse_df_article('<nav>10 de octubre de 2026</nav><article><p>El incidente ocurrió el 9 de octubre de 2026.</p></article>', URL)["event_date"] is None


def test_reviewed_ricarte_visible_publication_provenance_preserves_conflicting_timestamps():
    url="https://www.df.cl/empresas/salud/recortes-a-la-ley-ricarte-soto-es-un-ahorro-mal-entendido"
    html='<meta name="cXenseParse:recs:publishtime" content="2026-10-07T22:54:15Z">'
    html+='<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-10-07T22:54:15Z"}</script><p>Publicado: jueves 8 de octubre de 2026 a las 04:00 hrs.</p>'
    result=parse_df_article(html,url)
    assert result["event_date"]=="2026-10-08"
    assert result["metadata"]["publication_date_source"]=="visible:published_label"
    assert result["metadata"]["publication_date_conflict"]
    assert result["metadata"]["publication_date_conflict_resolution"]["selected_visible_day"]=="2026-10-08"
    assert [x["day"] for x in result["metadata"]["publication_date_candidates"]]==["2026-10-07","2026-10-07","2026-10-08"]
    assert parse_df_article(html.replace("2026-10-07T22:54:15Z","2026-10-06T22:54:15Z"),url)["event_date"] is None


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
    empty = PendingQueue(tmp_path / "empty.json")
    empty.discover("diario_financiero", [_raw(dated=True)], now=NOW, published_urls=[URL])
    assert not empty.ready(NOW)
    assert empty.items[key]["reason"] == "already_published_in_history"


def _analysis(score=90):
    return {"relevance_score": score,
            "what_happened": "La Clínica San Carlos suspendió operaciones y trasladó a todos sus pacientes hospitalizados tras el aluvión.",
            "why_it_matters": "La suspensión reduce capacidad hospitalaria disponible y requiere reorganizar la atención mientras se recuperan las áreas afectadas.",
            "reason": "Interrupción material de capacidad hospitalaria."}


def test_configured_media_threshold_and_attribution(monkeypatch):
    from radar_salud.public_source_pipeline import process_df
    from test_press_pipeline import DF_CFG
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news", lambda **kw: _analysis(71))
    raw = _raw(dated=True)
    assert process_df(raw, DF_CFG) is None
    assert raw.metadata["rejection_reason"] == "media_score_below_72"
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news", lambda **kw: _analysis(90))
    result = process_df(_raw(dated=True), DF_CFG)
    assert result["evidence_maturity"] == "media_reported"
    assert result["what_happened"].startswith("Según Diario Financiero")
    assert result["publication_date_source"] == "cxenseparse:recs:publishtime"


def test_technical_capture_failure_and_missing_date_are_not_editorial_rejections(monkeypatch):
    from radar_salud.public_source_pipeline import process_df
    from radar_salud.processing import DeferredProcessing
    from test_press_pipeline import DF_CFG
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html", lambda url: '<article><p>Sin fecha de publicación.</p></article>')
    with pytest.raises(DeferredProcessing) as error:
        process_df(_raw(), DF_CFG)
    assert error.value.reason == "df_missing_publication_date"
    def blocked(url): raise OSError("CONNECT 403")
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html", blocked)
    with pytest.raises(DeferredProcessing) as error:
        process_df(_raw(), DF_CFG)
    assert error.value.reason == "df_detail_fetch_failed"


def test_opinion_and_unrelated_have_specific_reasons_without_model_call(monkeypatch):
    from radar_salud.public_source_pipeline import process_df
    from test_press_pipeline import DF_CFG
    def unexpected(**kw): raise AssertionError("Excluded content should not consume AI")
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news", unexpected)
    opinion = _raw(dated=True)
    opinion.metadata["article_section"] = "Opinión"
    assert process_df(opinion, DF_CFG) is None
    assert opinion.metadata["rejection_reason"] == "media_opinion_or_column"
    nonhealth = _raw("Terremoto de magnitud 7,7 sacude Panamá", dated=True)
    nonhealth.raw_text = "El terremoto afectó a Panamá."
    nonhealth.metadata["page_text"] = nonhealth.raw_text * 12
    assert process_df(nonhealth, DF_CFG) is None
    assert nonhealth.metadata["rejection_reason"] == "df_unrelated_to_health"


def test_daily_df_replay_real_processor_to_history_feed_and_second_run(tmp_path, monkeypatch):
    """Real DF scout/parser/queue/processor/exporter; publisher + AI are fixtures."""
    import importlib.util
    import shutil
    import sys
    from pathlib import Path
    from radar_salud import engine_cli
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / "config").mkdir()
    shutil.copyfile(repo / "config/sources.json", tmp_path / "config/sources.json")
    state = tmp_path / "data/state"
    state.mkdir(parents=True)
    (state / "discovery_watermarks.json").write_text(json.dumps({"diario_financiero": CAPTURE.isoformat()}))
    queue = PendingQueue(state / "pending_queue.json")
    queue.discover("diario_financiero", [_raw()], now=CAPTURE, last_discovered_at="2026-10-09T22:00:00+00:00")
    unrelated = RawItem("minsal", "Other source pending", "https://example.org/untouched", "MINSAL", "official", "2026-01-01")
    queue.discover("minsal", [unrelated], now=CAPTURE)
    queue.items[fingerprint(unrelated)]["status"] = "pending"  # Old retained state of a different source.
    queue.save()
    minsal_discovery={"discovered":7,"new":0,"technical_status":"ok","checked_at":CAPTURE.isoformat()}
    (state / "discovery_run.json").write_text(json.dumps({"sources":{"minsal":minsal_discovery}}))
    original_key = fingerprint(_raw())
    low_url = "https://www.df.cl/empresas/salud/inversion-secundaria"
    deferred_url = "https://www.df.cl/empresas/salud/analisis-pendiente"
    listing = f'<a href="{URL}">{_raw().title}</a><a href="{low_url}">Clínica anuncia una inversión secundaria</a><a href="{deferred_url}">Clínica con análisis pendiente de inversión</a>'
    detail = '<meta name="cXenseParse:recs:publishtime" content="2026-10-10T16:29:59Z"><article><p>' + _raw(dated=True).metadata["page_text"] + '</p></article>'
    monkeypatch.setattr("radar_salud.source_scouts.fetch_html", lambda url: listing if url in DfHealthScout.PAGES else detail)
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news", lambda **kw: None if "pendiente" in kw["title"] else _analysis(71 if "secundaria" in kw["title"] else 90))
    monkeypatch.setattr("radar_salud.paths.project_root", lambda: tmp_path)
    monkeypatch.setattr("radar_salud.pending_queue.now_utc", lambda: NOW)
    monkeypatch.setattr(sys, "argv", ["engine_cli", "--source", "diario_financiero", "--limit", "5"])
    engine_cli.main()
    queue = PendingQueue(queue.path)
    assert queue.items[original_key]["status"] == "published"
    assert queue.items[original_key]["lane"] == "LIVE"
    assert queue.items[fingerprint(unrelated)]["status"] == "pending"
    assert json.loads((state / "discovery_run.json").read_text())["sources"]["minsal"] == minsal_discovery
    rejected = next(v for v in queue.items.values() if v["raw"]["url"] == low_url)
    assert rejected["reason"] == "media_score_below_72"
    assert rejected["raw"]["metadata"]["editorial_assessment"]["score"] == 71
    history = json.loads((tmp_path / "data/history/superintendencia_signals.json").read_text())["signals"]
    assert len(history) == 1 and history[0]["ingestion_mode"] == "LIVE"
    spec = importlib.util.spec_from_file_location("df_replay_export", repo / "scripts/export_web_snapshot.py")
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    feed = exporter.curate(history, resolve_external=False)
    assert len(feed) == 1 and feed[0]["source_url"] == URL
    seen = json.loads((state / "diario_financiero_seen.json").read_text())
    assert original_key in seen
    deferred_key, deferred = next((key, value) for key, value in queue.items.items() if value["raw"]["url"] == deferred_url)
    assert deferred["status"] == "retry" and deferred["reason"] == "df_analysis_deferred"
    assert deferred["raw"]["event_date"] == "2026-10-10"
    assert deferred_key not in seen
    engine_cli.main()
    assert json.loads((state / "discovery_run.json").read_text())["sources"]["diario_financiero"]["new"] == 0
    assert PendingQueue(queue.path).items[original_key]["attempts"] == 1
    assert len(json.loads((tmp_path / "data/history/superintendencia_signals.json").read_text())["signals"]) == 1


def test_original_html_hash_validation_preserves_crlf_and_rejects_tampering(tmp_path):
    import hashlib
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location("df_original_hash",Path(__file__).resolve().parents[1]/"scripts/reconcile_df.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    payload=b'<article>\r\n<p>Verified source</p>\r\n</article>'
    path=tmp_path/"original.html";path.write_bytes(payload)
    assert module.read_captured_html(path,hashlib.sha256(payload).hexdigest()).encode()==payload
    path.write_bytes(payload+b'tampered')
    with pytest.raises(ValueError,match="hash mismatch"):
        module.read_captured_html(path,hashlib.sha256(payload).hexdigest())


def test_captured_df_primary_bodies_exclude_real_recommendation_cards():
    import hashlib
    from pathlib import Path
    fixtures = Path(__file__).parent / 'fixtures'
    manifest = json.loads((fixtures / 'df_original_manifest.json').read_text())
    expected = {'df_san_carlos_real': ('2026-10-10', 1584), 'df_biometria_real': ('2026-10-01', 1612),
                'df_ricarte_real': ('2026-10-08', 3796)}
    for name, (day, size) in expected.items():
        source = manifest[name]
        payload = (fixtures / (name + '.html')).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == source['excerpt_sha256']
        parsed = parse_df_article(payload.decode(), source['url'])
        body = parsed['metadata']['page_text']
        assert parsed['event_date'] == day
        assert parsed['metadata']['article_content_source'] == 'df_primary_body'
        assert len(body) == size
        assert '{{' not in body and 'TE PUEDE INTERESAR' not in body
        if name == 'df_biometria_real':
            assert 'Ley Ricarte Soto' not in body
            assert '1 de diciembre de 2026' in body
        if name == 'df_san_carlos_real':
            assert 'permanecerá cerrada durante algunas semanas' in body
    ricarte = parse_df_article((fixtures / 'df_ricarte_real.html').read_text(), manifest['df_ricarte_real']['url'])
    assert ricarte['metadata']['publication_timestamp'] is None
    assert '04:00' in ricarte['metadata']['publication_label']


def test_df_missing_primary_body_does_not_use_newsletter_or_description():
    html = '<meta property="og:description" content="' + 'Suscriba nuestro newsletter. ' * 20 + '">'
    html += '<p>Noticias de salud, inversiones y clínicas.</p><article class="card"><p>Otra clínica inaugura un hospital.</p></article>'
    parsed = parse_df_article(html, URL)
    assert parsed['metadata']['page_text'] == ''
    assert parsed['metadata']['article_content_source'] == 'missing_primary_article'


def test_health_materiality_requires_health_event_not_unrelated_macro_context():
    from radar_salud.df_media_gate import material
    assert not material('Economía crece con nuevas inversiones', 'El banco invertirá en oficinas. La salud también fue mencionada en el discurso.')
    assert material('Clínicas cierran maternidad por baja natalidad', 'Las clínicas suspenden prestaciones obstétricas.')
    assert material('Super de Salud dicta circular sobre bonos', 'La isapre deberá emitir el bono con cédula si falla la biometría.')


def test_nonarticle_and_verified_nonhealth_rejections_do_not_require_fake_date(monkeypatch):
    from radar_salud.public_source_pipeline import process_df
    from test_press_pipeline import DF_CFG
    monkeypatch.setattr('radar_salud.public_source_pipeline.enrich', lambda raw: raw)
    monkeypatch.setattr('radar_salud.public_source_pipeline.analyze_news', lambda **kw: pytest.fail('Excluded content must not call AI'))
    raw = _raw()
    raw.url = 'https://www.df.cl/regiones/maule/empresas/p/1'
    assert process_df(raw, DF_CFG) is None
    assert raw.metadata['rejection_reason'] == 'df_not_article'
    raw = _raw('Banco compra oficinas')
    raw.metadata = {'page_text': 'El banco compra oficinas y amplía su negocio financiero. ' * 10, 'publication_date_conflict': True}
    assert process_df(raw, DF_CFG) is None
    assert raw.metadata['rejection_reason'] == 'df_unrelated_to_health'


def test_capture_defect_reaudit_withdraws_wrong_story_and_reopens_only_once(tmp_path):
    from dataclasses import asdict
    from radar_salud.df_recovery import repair_contaminated_evidence
    queue = PendingQueue(tmp_path / 'q.json')
    original = _raw(dated=True)
    original.metadata['article_content_source'] = 'visible_article'
    original.metadata['page_text'] += ' Recomendaciones sobre otro hospital.'
    queue.discover('diario_financiero', [original], now=CAPTURE)
    key = fingerprint(original)
    queue.start(key);queue.finish(key, 'published', now=CAPTURE)
    history = [{'source_url': URL, 'title': 'Otro hospital', 'editorial_assessment': {'score': 82}}]
    corrected = _raw(dated=True)
    corrected.metadata['article_content_source'] = 'df_primary_body'
    changes = repair_contaminated_evidence(queue, [corrected], history, NOW)
    assert changes[0]['status'] == 'pending'
    assert queue.items[key]['recovery_observations'][-1]['before']['status'] == 'published'
    assert history[0]['editorial_decision'] == 'reject'
    assert history[0]['df_body_reaudit_observations'][0]['before']['title'] == 'Otro hospital'
    assert repair_contaminated_evidence(queue, [corrected], history, NOW) == []
    # A valid primary-text score rejection is editorial, not a capture defect.
    queue.items[key]['status'] = 'rejected'
    queue.items[key]['reason'] = 'media_score_below_72'
    queue.items[key]['raw'] = asdict(corrected)
    assert repair_contaminated_evidence(queue, [corrected], history, NOW) == []


def test_capture_defect_reaudit_nonhealth_rejects_without_spending_ai(tmp_path):
    from radar_salud.df_recovery import repair_contaminated_evidence
    queue = PendingQueue(tmp_path / 'q.json')
    original = _raw('Banco amplía oficinas', dated=True)
    original.metadata['article_content_source'] = 'visible_article'
    queue.discover('diario_financiero', [original], now=CAPTURE)
    key = fingerprint(original);queue.finish(key, 'published', now=CAPTURE)
    corrected = _raw('Banco amplía oficinas', dated=True)
    corrected.metadata.update(article_content_source='df_primary_body', page_text='El banco amplía oficinas y compra negocios financieros. ' * 8)
    changes = repair_contaminated_evidence(queue, [corrected], [], NOW)
    assert changes[0]['reason'] == 'df_unrelated_to_health'
    assert queue.items[key]['status'] == 'rejected'


def test_live_df_watermark_uses_same_chile_calendar_as_publication():
    from radar_salud.pending_queue import lane
    raw = _raw(dated=True)
    # UTC is October 11, while the publisher's calendar still reads October 10.
    assert lane(raw, datetime(2026, 10, 11, 2, tzinfo=timezone.utc), '2026-10-11T01:00:00Z') == 'LIVE'
    raw.event_date = '2026-10-11'
    assert lane(raw, datetime(2026, 10, 11, 2, tzinfo=timezone.utc), '2026-10-11T01:00:00Z') == 'BACKFILL'


def test_conflict_resolves_only_explicit_primary_df_header_with_matching_identity():
    body = '<div id="articleLock" class="CUERPO"><p>La clínica abrirá un nuevo centro médico con inversión confirmada.</p></div>'
    meta = '<meta name="cXenseParse:recs:publishtime" content="2026-07-22T23:46:04Z">'
    node = '<script type="application/ld+json">' + json.dumps({'@type': 'NewsArticle', 'url': URL, 'datePublished': '2026-07-22T23:46:04Z'}) + '</script>'
    label = '<header class="enc-main"><p class="author__date">Publicado: Jueves 23 de julio de 2026 a las 04:00 hrs.</p></header>'
    parsed = parse_df_article(meta + node + label + body, URL)
    assert parsed['event_date'] == '2026-07-23'
    assert parsed['metadata']['publication_date_conflict']
    assert parsed['metadata']['publication_date_conflict_resolution']['rule'] == 'primary_header_explicit_publication_label'
    assert len(parsed['metadata']['publication_date_candidates']) == 3
    assert parse_df_article(meta + node.replace(URL, 'https://www.df.cl/other/article') + label + body, URL)['event_date'] is None
    assert parse_df_article(meta + node + label.replace('enc-main', 'recommendations') + body, URL)['event_date'] is None


def test_single_clock_or_incident_time_never_becomes_df_publication_date():
    assert parse_df_article('<nav><time datetime="2026-10-11">Hoy</time></nav>', URL)['event_date'] is None
    assert parse_df_article('<article><time datetime="2026-10-08">Fecha del incidente</time></article>', URL)['event_date'] is None
    assert parse_df_article('<header><time datetime="2026-10-11">Reloj</time></header>', URL)['event_date'] is None
    assert parse_df_article('<time itemprop="datePublished" datetime="2026-10-10">Publicado</time>', URL)['event_date'] == '2026-10-10'


def test_retained_withdrawn_history_does_not_acknowledge_reassessment_as_published(tmp_path):
    from radar_salud.df_recovery import repair_contaminated_evidence, published_history_urls, resume_withdrawn_reassessments
    queue = PendingQueue(tmp_path / 'q.json')
    raw = _raw(dated=True);raw.metadata['article_content_source'] = 'visible_article'
    queue.discover('diario_financiero', [raw], now=CAPTURE)
    key = fingerprint(raw);queue.finish(key, 'published', now=CAPTURE)
    history = [{'source_url': URL, 'title': 'Clínica San Carlos'}]
    corrected = _raw(dated=True);corrected.metadata['article_content_source'] = 'df_primary_body'
    repair_contaminated_evidence(queue, [corrected], history, NOW)
    queue.discover('diario_financiero', [corrected], now=NOW, published_urls=published_history_urls(history))
    assert queue.items[key]['status'] == 'pending'
    # Exact recovery of the acknowledgement seen in runtime38113493822.
    queue.items[key].update(status='superseded', reason='already_published_in_history')
    assert resume_withdrawn_reassessments(queue, history, NOW) == [key]
    assert queue.items[key]['status'] == 'pending'
    assert resume_withdrawn_reassessments(queue, history, NOW) == []
    assert published_history_urls([{'source_url': URL, 'editorial_decision': 'accept'}]) == [URL]


def test_verified_body_repair_unblocks_retry_without_changing_publication_day(tmp_path):
    queue = PendingQueue(tmp_path / 'q.json')
    raw = _raw(dated=True);raw.metadata['page_text'] = 'Short body'
    queue.discover('diario_financiero', [raw], now=CAPTURE)
    key = fingerprint(raw);queue.start(key);queue.finish(key, 'retry', 'df_insufficient_article_evidence', now=CAPTURE)
    queue.discover('diario_financiero', [_raw(dated=True)], now=NOW)
    assert queue.items[key]['status'] == 'pending'
    assert queue.items[key]['retry_at'] is None


def test_real_df_listings_select_primary_cards_and_observable_health_pagination(monkeypatch):
    from pathlib import Path
    from radar_salud.df_inventory import DfListing
    fixtures = Path(__file__).parent / 'fixtures'
    tag = DfListing();tag.feed((fixtures / 'df_health_tag_real.html').read_text())
    assert tag.has_primary_layout
    assert ('/tags/salud/p/2', '2') in tag.pagination
    assert any('clinica-san-carlos' in (u or '') for u, title in tag.primary_links)
    def fetch(url):
        if url == DfHealthScout.PAGES[0]:return (fixtures / 'df_health_listing_real.html').read_text()
        if url == DfHealthScout.PAGES[1]:return (fixtures / 'df_health_tag_real.html').read_text()
        return '<meta name="cXenseParse:recs:publishtime" content="2026-10-10"><article>Contenido</article>'
    monkeypatch.setattr('radar_salud.source_scouts.fetch_html', fetch)
    items = DfHealthScout().discover()
    assert any('clinica-san-carlos' in raw.url for raw in items)
    assert any('ricarte-soto' in raw.url for raw in items)
    assert not any('/p/1' in raw.url or raw.url.endswith('.pdf') for raw in items)
    assert not any('klap-se-suma' in raw.url for raw in items)
    assert all(raw.metadata['listing_extraction'] == 'primary_cards' for raw in items)
    assert len(items) < 40
