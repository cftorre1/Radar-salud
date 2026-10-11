"""Document facts affect editorial input only after primary and binary proof."""
from datetime import date
from types import SimpleNamespace
import pytest

from test_occupational_documents import captured_documents, pdf_bytes, pptx_bytes
from radar_salud.occupational_documents import DOCUMENTS, attach_documents, additional_document_facts
from radar_salud.beta_sources import process_curated_beta_source
from radar_salud.occupational_recovery import _decorate
from radar_salud.processing import DeferredProcessing


def prepared(make, *, ist=True, **kwargs):
    raw, loader, path, record, evidence = make(ist=ist, **kwargs)
    raw.metadata.update(article_extraction="occupational_v1", market_role="mutuality", source_quality_gate="audit_passed")
    return raw, loader, path


def test_annual_report_missing_document_defers_before_ai(captured_documents, monkeypatch):
    raw, loader, _ = prepared(captured_documents)
    del loader.records[DOCUMENTS[raw.url][2]]
    attach_documents(raw, loader)
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", lambda **kw: pytest.fail("missing PDF reached AI"))
    with pytest.raises(DeferredProcessing, match="required_supporting_document_pending"):
        process_curated_beta_source(raw, {})


def test_verified_annual_values_have_bounded_separate_context_and_threshold(captured_documents, monkeypatch):
    raw, loader, _ = prepared(captured_documents, content=pdf_bytes("En 2025 protegimos 496 mil trabajadores y atendimos 45 mil pacientes."))
    original = raw.metadata["page_text"]
    attach_documents(raw, loader)
    calls = []
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    def analyze(**kwargs):
        calls.append(kwargs)
        return {"relevance_score": 74, "what_happened": "El informe publica cifras de actividad laboral verificadas para el año 2025.", "why_it_matters": "Permite evaluar la cobertura y la actividad asistencial de la mutualidad."}
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", analyze)
    assert process_curated_beta_source(raw, {}) is None
    assert raw.metadata["page_text"] == original
    assert raw.event_date == "2026-07-14" and raw.metadata["content_kind"] == "study"
    assert raw.metadata["materiality_reason"] == "published_operational_study"
    assert raw.metadata["editorial_assessment"]["threshold"] == 75
    assert "496 mil trabajadores" in calls[0]["text"] and "2025" in calls[0]["text"]
    assert len(calls[0]["text"]) <= 5500
    assert "2026-07-14" in calls[0]["kind"] and "2026-10-11" in calls[0]["kind"]
    assert "BACKFILL" in calls[0]["kind"] and "continúa abierta hoy" in calls[0]["kind"]


def test_tampered_document_never_reaches_ai(captured_documents, monkeypatch):
    raw, loader, _ = prepared(captured_documents)
    attach_documents(raw, loader)
    raw.metadata["supporting_documents"][0]["extracted_text"] += " 900000 trabajadores"
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", lambda **kw: pytest.fail("corrupt PDF reached AI"))
    with pytest.raises(DeferredProcessing, match="supporting_document_extracted_text_mismatch"):
        process_curated_beta_source(raw, {})


def test_document_selector_rejects_index_legal_reference_and_fragmented_percent():
    assert additional_document_facts("", "Proyecto 324-2024 para trabajadores.\n6.4.1. Retorno al trabajo 23\nLey N°16.744 accidentes del trabajo.\n5 7,9 %\nde los accidentes") == ""
    assert additional_document_facts("42,7 casos por 100.000 personas", "42,7 casos por 100.000 personas") == ""
    result = additional_document_facts("", "En 2025 protegimos 496 mil trabajadores promedio,\natendimos 45\nmil pacientes por accidentes laborales.")
    assert "2025" in result and "496" in result and "45" in result


def test_required_document_pending_remains_dated_study_in_honest_inventory(captured_documents):
    raw, loader, _ = prepared(captured_documents)
    del loader.records[DOCUMENTS[raw.url][2]]
    row = {"url": raw.url, "title": raw.title, "status": "rejected", "within_90_days": True, "within_30_days": False}
    report = {"raw_items": [raw], "rows": [row], "errors": [], "coverage_complete": True,
              "metrics": {"90": {}, "30": {}}}
    result = _decorate(report, SimpleNamespace(cfg={"hosts": ("ist.cl",)}), loader)
    assert result["rows"][0]["status"] == "pending" and result["rows"][0]["content_kind"] == "study"
    assert result["metrics"]["90"]["pending"] == 1 and not result["coverage_complete"]
    assert result["technical_status"] == "partial" and result["document_diagnostics"]


def test_legacy_required_report_cannot_bypass_document_pending_flag(captured_documents, monkeypatch):
    raw, _, _ = prepared(captured_documents)
    assert "supporting_documents_required" not in raw.metadata
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", lambda **kw: pytest.fail("legacy report reached AI"))
    with pytest.raises(DeferredProcessing, match="required_supporting_document_pending"):
        process_curated_beta_source(raw, {})


def test_optional_missing_doc_keeps_primary_materiality_and_editorial_input(captured_documents, monkeypatch):
    raw, loader, _ = prepared(captured_documents, ist=False)
    del loader.records[DOCUMENTS[raw.url][2]]
    original = raw.metadata["page_text"]
    attach_documents(raw, loader)
    calls = []
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", lambda **kw: calls.append(kw) or {"relevance_score": 74})
    assert process_curated_beta_source(raw, {}) is None
    assert calls[0]["text"] == original
    assert raw.metadata["materiality_accepted"] and raw.metadata["page_text"] == original


def test_editorial_hash_changes_for_actual_verified_new_facts_only(captured_documents):
    from copy import deepcopy
    from scripts.occupational_inventory import editorial_input
    raw, loader, _ = prepared(captured_documents, content=pdf_bytes("En 2025 protegimos 496 mil trabajadores."))
    original = editorial_input(raw)
    attach_documents(raw, loader)
    enriched = editorial_input(raw)
    assert enriched != original
    before = deepcopy(raw.metadata)
    raw.metadata["capture_checked_at"] = "2026-10-11T10:00:00Z"
    raw.metadata["editorial_assessment"] = {"score": 74}
    assert editorial_input(raw) == enriched
    raw.metadata = before
    raw.metadata["supporting_documents"][0]["extracted_text"] += " forged workers"
    assert editorial_input(raw) == original
