"""The complete offline review keeps quotes bound to exact official PDF bytes."""
import hashlib
import json
from pathlib import Path

import pytest
from pypdf import PdfReader


@pytest.fixture(scope="module")
def reviewed_pdf():
    root = Path(__file__).resolve().parents[1]
    audit = json.loads((root / "data/audits/source_e_recovery/ist_full_pdf_review.json").read_text())
    evidence = audit["capture_evidence"]
    path = root / evidence["artifact"]
    data = path.read_bytes()
    reader = PdfReader(path, strict=True)
    texts = {index + 1: page.extract_text() or "" for index, page in enumerate(reader.pages)}
    return audit, evidence, data, texts


def test_complete_review_has_all_113_pages_bound_to_verified_origin_bytes(reviewed_pdf):
    audit, evidence, data, texts = reviewed_pdf
    assert evidence["url"] == evidence["final_url"] == audit["document_url"]
    assert audit["document_url"] == "https://ist.cl/wp-content/uploads/2026/07/Reporte-de-sostenibilidad-2025.pdf"
    assert evidence["http_status"] == 200 and evidence["tls_verified"]
    assert len(data) == evidence["bytes"] == 4_169_202
    assert hashlib.sha256(data).hexdigest() == evidence["sha256"] == "acc895136dcfabe0ed8fd7ec2af599f5c0018b0e8288581ecc625e5ac12f53f7"
    ledger = audit["page_review_ledger"]
    assert list(texts) == [row["pdf_page"] for row in ledger] == list(range(1, 114))
    assert all(row["reviewed_offline"] for row in ledger)
    for row in ledger:
        text = texts[row["pdf_page"]]
        assert len(text) == row["text_characters"]
        assert hashlib.sha256(text.encode()).hexdigest() == row["text_sha256"]
    assert audit["offline_review"]["pages_reviewed"] == 113
    assert audit["offline_review"]["previously_unreviewed_pages_completed"] == list(range(41, 114))
    assert not texts[113].strip()


def test_every_selected_finding_is_a_literal_quote_from_its_numbered_pdf_page(reviewed_pdf):
    audit, _, _, texts = reviewed_pdf
    for finding in audit["new_findings"]:
        assert finding["citations"]
        for citation in finding["citations"]:
            text = texts[citation["pdf_page"]]
            assert citation["quote"] in " ".join(text.split())
            assert hashlib.sha256(text.encode()).hexdigest() == citation["page_text_sha256"]
            assert hashlib.sha256(citation["quote"].encode()).hexdigest() == citation["normalized_quote_sha256"]


def test_new_financial_facts_preserve_period_columns_and_differ_from_the_previous_ai_excerpt(reviewed_pdf):
    audit, _, _, texts = reviewed_pdf
    previous = audit["prior_editorial_input"]["prior_selected_additional_facts"]
    revenue = " ".join(texts[54].split())
    expenses = " ".join(texts[55].split())
    assert "Indicador Financiero 2025 2024 Ingresos ordinarios $127.894 MM $124.317 MM" in revenue
    assert "Indicador Financiero 2025 2024 Egresos ordinarios $129.140 MM $126.409 MM" in expenses
    assert "Durante 2025, IST no registró excedentes" in " ".join(texts[58].split())
    assert all(value not in previous for value in ("127.894", "124.317", "129.140", "126.409", "no registró excedentes"))
    assert audit["data_period"] == "2025"
    assert audit["parent_verified_publication_date"] == "2026-07-14"
    assert audit["document_publication_date"] is None
    assert audit["conclusion"]["current_score72_preserved_as_prior_assessment"]
    assert audit["prior_editorial_input"]["editorial_assessment"]["score"] == 72
