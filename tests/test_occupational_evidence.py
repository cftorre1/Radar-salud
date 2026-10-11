import hashlib
import json
from datetime import date
import pytest
from radar_salud.beta_sources import CuratedBetaSourceScout, process_curated_beta_source
from radar_salud.processing import DeferredProcessing


@pytest.fixture
def captured_raw(tmp_path, monkeypatch):
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    monkeypatch.setattr("radar_salud.occupational_evidence.project_root", lambda: tmp_path)
    html = ('<h1>Nueva guía de tratamiento de salud mental laboral</h1>'
            '<div class="publication-date">24/09/2026</div><p>'
            'Achs Seguro Laboral incorpora una nueva guía de tratamiento de patologías de salud mental laboral. '
            'La guía cambia los protocolos de evaluación y reintegro de trabajadores y se aplica en la red nacional.'
            '</p>')
    raw = CuratedBetaSourceScout("achs_seguro_laboral").discover_from_html(
        '<a href="/centro-de-noticias/noticia/2026/guia">Ver detalle</a>', lambda url: html)[0]
    identity = hashlib.sha256((raw.url + "\nidentified").encode()).hexdigest()[:20]
    path = tmp_path / "data/audits/source_e_recovery/fixture" / (identity + "-0.body")
    path.parent.mkdir(parents=True)
    path.write_text(html)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    stamp = "2026-10-11T06:00:00+00:00"
    hop = dict(url=raw.url, http_status=200, curl_exit=0, tls={"verified": True}, waf=None,
               body_file=path.name, sha256=digest, bytes=len(path.read_bytes()))
    path.with_name(identity + ".json").write_text(json.dumps(dict(url=raw.url, final_url=raw.url,
        user_agent="identified", captured_at=stamp, stop_reason="response_captured", waf=None, http_status=200, hops=[hop])))
    raw.metadata["capture_evidence"] = dict(url=raw.url, final_url=raw.url, tls_verified=True,
        http_status=200, sha256=digest, artifact=str(path), captured_at=stamp)
    calls = []
    def analyze(**kwargs):
        calls.append(kwargs)
        return dict(relevance_score=0, what_happened="", why_it_matters="", reason="below threshold")
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", analyze)
    return raw, path, calls


def test_matching_saved_publisher_bytes_reach_editorial_assessment(captured_raw):
    raw, _, calls = captured_raw
    assert process_curated_beta_source(raw, {}) is None
    assert len(calls) == 1
    assert raw.metadata["editorial_assessment"]["score"] == 0


@pytest.mark.parametrize("tamper", ["sha", "bytes", "missing", "final_url", "tls", "private", "future", "publisher", "body"])
def test_corrupted_or_unbound_capture_never_consumes_analysis(captured_raw, tamper):
    raw, path, calls = captured_raw
    capture = raw.metadata["capture_evidence"]
    if tamper == "sha":
        capture["sha256"] = "0" * 64
    elif tamper == "bytes":
        path.write_text(path.read_text() + "tampered")
    elif tamper == "missing":
        raw.metadata.pop("capture_evidence")
    elif tamper == "final_url":
        capture["final_url"] += "?different=article"
    elif tamper == "tls":
        capture["tls_verified"] = False
    elif tamper == "private":
        raw.url = "https://www.mutual.cl/portal/privado/claim"
    elif tamper == "future":
        raw.event_date = raw.metadata["publication_date"] = raw.metadata["publication_evidence"]["date"] = "2099-01-01"
    elif tamper == "publisher":
        raw.metadata["publication_evidence"]["kind"] = "datePublished"
    else:
        raw.metadata["page_text"] += " invented capacity claim"
    with pytest.raises(DeferredProcessing):
        process_curated_beta_source(raw, {})
    assert calls == []

