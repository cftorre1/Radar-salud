"""Bounded IST financial context changes its input without changing ACHS proofs."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import pytest

from radar_salud.models import RawItem
from radar_salud.occupational_capture import CaptureLoader
from radar_salud.occupational_documents import (DOCUMENTS, IST_REPORT_URL, IST_DOCUMENT_URL, IST_FINANCIAL_PROFILE,
    IST_SELECTED_PAGES, _extract, attach_documents, verified_document_text, additional_document_facts)
from radar_salud.occupational_sources import Article
from radar_salud.processing import DeferredProcessing
from scripts.occupational_inventory import editorial_input, refresh_item
from test_occupational_documents import pdf_bytes

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data/audits/source_e_recovery/actions/38120730741/inventory"


def actual_item(url, tmp_path):
    loader = CaptureLoader(tmp_path / "replay", replay=RUN)
    article = Article(url); article.feed(loader(url))
    title, published, body, kind = article.result(today=date(2026, 10, 11))
    raw = RawItem(source_slug=DOCUMENTS[url][0], title=title, url=url, source_name=DOCUMENTS[url][0],
                  source_type="institution_verified", event_date=published, raw_text=body[:1800],
                  metadata={"page_text": body[:18000], "publication_date": published, "date_evidence": kind,
                            "publication_evidence": article.publication_evidence(), "capture_evidence": loader.evidence(url),
                            "market_role": "mutuality", "article_extraction": "occupational_v1", "source_quality_gate": "audit_passed"})
    attach_documents(raw, loader)
    return raw


def test_actual_financial_tables_keep_columns_periods_and_non_net_categories(tmp_path, monkeypatch):
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    raw = actual_item(IST_REPORT_URL, tmp_path)
    text = verified_document_text(raw, ("ist.cl",))
    facts = additional_document_facts(raw.metadata["page_text"], text)
    document = raw.metadata["supporting_documents"][0]
    assert document["extraction_profile"] == IST_FINANCIAL_PROFILE
    assert document["extracted_page_numbers"] == list(IST_SELECTED_PAGES)
    assert document["page_count"] == 113 and document["extracted_pages"] == 40 and document["truncated"]
    assert len(document["extracted_text"]) == 30_000 and len(facts) <= 1900
    assert "Indicador Financiero 2025 2024" in facts
    assert "Ingresos ordinarios $127.894 MM $124.317 MM" in facts
    assert "Egresos ordinarios $129.140 MM $126.409 MM" in facts
    assert "Durante 2025, IST no registró excedentes" in facts
    assert "$70.600 millones en 2025" in facts
    assert "déficit" not in facts and raw.event_date == "2026-07-14"
    assert additional_document_facts(raw.metadata["page_text"], text, max_chars=150).startswith("Página 54:")
    assert "Indicador Financiero 2025 2024" in additional_document_facts("", text, max_chars=150)


def test_selector_is_static_and_only_for_exact_ist_document_binding():
    data = pdf_bytes(pages=60)
    ordinary = _extract(data, "pdf")
    scoped = _extract(data, "pdf", document_url=IST_DOCUMENT_URL)
    assert scoped["extracted_page_numbers"] == list(IST_SELECTED_PAGES)
    assert 33 not in scoped["extracted_page_numbers"] and 52 not in scoped["extracted_page_numbers"]
    assert scoped["extracted_pages"] == 40 and "Página 53:" in scoped["extracted_text"]
    assert _extract(data, "pdf", document_url=IST_DOCUMENT_URL + "?choose_pages=53") == ordinary
    assert "extraction_profile" not in ordinary


def test_actual_selector_migration_changes_only_ist_new_fact_input(tmp_path, monkeypatch):
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    raw = actual_item(IST_REPORT_URL, tmp_path)
    document = raw.metadata["supporting_documents"][0]
    old = deepcopy(raw)
    old_document = old.metadata["supporting_documents"][0]
    legacy = _extract((ROOT / document["capture_evidence"]["artifact"]).read_bytes(), "pdf")
    for key in ("extraction_profile", "extracted_page_numbers", "retained_page_numbers", "selection"):
        old_document.pop(key)
    old_document.update(legacy)
    with pytest.raises(DeferredProcessing, match="supporting_document_extraction_profile_outdated"):
        verified_document_text(old, ("ist.cl",))
    assert editorial_input(old) != editorial_input(raw)
    assert "$127.894 MM" not in legacy["extracted_text"]


@pytest.mark.parametrize("url", [url for url in DOCUMENTS if url != IST_REPORT_URL])
def test_all_actual_achs_documents_and_editorial_decisions_remain_identical(url, tmp_path, monkeypatch):
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    raw = actual_item(url, tmp_path)
    document = raw.metadata["supporting_documents"][0]
    data = (ROOT / document["capture_evidence"]["artifact"]).read_bytes()
    before = _extract(data, document["format"])
    after = _extract(data, document["format"], document_url=document["document_url"])
    assert before == after and "extraction_profile" not in after
    baseline = deepcopy(raw)
    baseline.metadata["supporting_documents"][0].update(before)
    item = {"raw": baseline.__dict__, "status": "published", "reason": "accepted",
            "editorial_assessment": {"score": 80}}
    baseline.metadata.update(what_happened="Established reviewed copy", why_it_matters="Established reviewed consequence",
                             editorial_review={"decision": "accept"})
    assert editorial_input(baseline) == editorial_input(raw)
    assert not refresh_item(item, raw)
    assert item["status"] == "published" and item["editorial_assessment"]["score"] == 80
    assert raw.metadata["what_happened"] == "Established reviewed copy"


def test_actual_ist_financial_context_reaches_ai_without_lowering_threshold(tmp_path, monkeypatch):
    from radar_salud.beta_sources import process_curated_beta_source
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    raw = actual_item(IST_REPORT_URL, tmp_path)
    primary = raw.metadata["page_text"]
    calls = []
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", lambda **kwargs: calls.append(kwargs) or {"relevance_score": 74})
    assert process_curated_beta_source(raw, {}) is None
    assert len(calls) == 1 and len(calls[0]["text"]) <= 5500
    assert "$127.894 MM $124.317 MM" in calls[0]["text"]
    assert "$129.140 MM $126.409 MM" in calls[0]["text"]
    assert "No deduzcas déficit ni resultado neto" in calls[0]["kind"]
    assert "2026-07-14" in calls[0]["kind"] and "período 2025" in calls[0]["kind"]
    assert raw.metadata["page_text"] == primary and raw.metadata["editorial_assessment"]["threshold"] == 75
