"""Saved document integrity, semantic parent binding and nonexecuting extraction."""
from copy import deepcopy
from datetime import date
import hashlib
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
import pytest

from radar_salud.models import RawItem
from radar_salud.occupational_documents import DOCUMENTS, _extract, attach_documents, verified_document_text
from radar_salud.occupational_sources import Article, SourceDiscoveryError
from radar_salud.processing import DeferredProcessing


def pdf_bytes(text="Atenciones laborales2025: 32522. Tiempo de espera48 horas.", *, pages=1):
    writer = PdfWriter()
    for number in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text if number == 0 else 'Pagina complementaria.'}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_metadata({"/CreationDate": "D:20990101000000", "/ModDate": "D:20250101000000"})
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def pptx_bytes(slides=None, *, extra=None):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for number, text in (slides or [(1, "Modelo predictivo de lesiones graves y fatales"), (2, "200 casos analizados")]):
            archive.writestr(f"ppt/slides/slide{number}.xml", '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                             'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>' + text + '</a:t></p:sld>')
        if extra:
            for name, content in extra.items():
                archive.writestr(name, content)
    return output.getvalue()


@pytest.fixture
def captured_documents(tmp_path, monkeypatch):
    monkeypatch.setattr("radar_salud.occupational_documents.project_root", lambda: tmp_path)
    monkeypatch.setattr("radar_salud.occupational_evidence.project_root", lambda: tmp_path)
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    output = tmp_path / "data/audits/source_e_recovery/documents"
    output.mkdir(parents=True)

    def make(*, ist=False, content=None, parent_link=True):
        parent = "https://ist.cl/reporte-sostenibilidad-2025/" if ist else next(url for url in DOCUMENTS if "estrena-modulo" in url)
        slug, published, doc = DOCUMENTS[parent]
        title = "Reporte de Sostenibilidad IST2025" if ist else "Achs Virtual estrena módulo predictivo de accidentes graves"
        narrative = "La publicación describe el desempeño de atención laboral y ofrece información verificable para los equipos de trabajo. " * 3
        href = f'<a href="{doc}">Documento oficial</a>' if parent_link else ""
        html = f'<meta property="article:published_time" content="{published}"><article><h1>{title}</h1><p>{narrative}</p>{href}</article>'
        article = Article(parent)
        article.feed(html)
        title, pub, body, kind = article.result()
        raw = RawItem(source_slug=slug, title=title, url=parent, source_name=slug, source_type="mutuality", event_date=pub,
                      raw_text=body[:1800], metadata={"page_text": body, "publication_date": pub,
                          "date_evidence": kind, "publication_evidence": article.publication_evidence()})
        records, evidences = {}, {}

        def save(url, binary, mime):
            identity = hashlib.sha256((url + "\nidentified").encode()).hexdigest()[:20]
            path = output / (identity + "-0.body")
            path.write_bytes(binary)
            hop = dict(url=url, http_status=200, curl_exit=0, content_type=mime, bytes=len(binary),
                       sha256=hashlib.sha256(binary).hexdigest(), body_file=path.name, waf=None, tls={"verified": True})
            record = dict(url=url, final_url=url, http_status=200, user_agent="identified", stop_reason="response_captured",
                          waf=None, hops=[hop], artifact_dir=str(output), captured_at="2026-10-11T06:00:00+00:00")
            (output / (identity + ".json")).write_text(json.dumps(record))
            records[url] = record
            evidences[url] = dict(url=url, final_url=url, http_status=200, tls_verified=True, sha256=hop["sha256"],
                                  artifact=str(path), captured_at=record["captured_at"], environment="github_actions")
            return path

        save(parent, html.encode(), "text/html; charset=utf-8")
        path = save(doc, content if content is not None else pdf_bytes() if ist else pptx_bytes(),
                    "application/pdf" if ist else "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        raw.metadata["capture_evidence"] = evidences[parent]

        class Loader:
            def __init__(self):
                self.records = records
            def __call__(self, url):
                if url not in self.records:
                    raise SourceDiscoveryError("replay_capture_missing", url)
                return Path(evidences[url]["artifact"]).read_bytes().decode(errors="replace")
            def evidence(self, url):
                return deepcopy(evidences[url])

        return raw, Loader(), path, records[doc], evidences
    return make


@pytest.mark.parametrize("ist", [False, True])
def test_saved_documents_attach_without_changing_primary_body_date_or_period(captured_documents, ist):
    raw, loader, _, _, _ = captured_documents(ist=ist)
    before = raw.metadata["page_text"], raw.event_date
    assert attach_documents(raw, loader) is raw
    assert (raw.metadata["page_text"], raw.event_date) == before
    document = raw.metadata["supporting_documents"][0]
    assert document["document_publication_date"] is None
    assert document["parent_date"] == raw.event_date
    text = verified_document_text(raw, ("ist.cl", "www.achs.cl"))
    assert "32522" in text if ist else "200 casos" in text
    assert "2099" not in text


@pytest.mark.parametrize("ist", [False, True])
def test_missing_optional_document_preserves_article_while_ist_report_is_pending(captured_documents, ist):
    raw, loader, _, _, _ = captured_documents(ist=ist)
    del loader.records[DOCUMENTS[raw.url][2]]
    before = raw.metadata["page_text"]
    attach_documents(raw, loader)
    assert raw.metadata["supporting_document_status"] == "pending_document"
    assert raw.metadata["supporting_document_diagnostics"][0]["code"] == "replay_capture_missing"
    assert raw.metadata["page_text"] == before
    if ist:
        with pytest.raises(DeferredProcessing, match="required_supporting_document_pending"):
            verified_document_text(raw, ("ist.cl",))
    else:
        assert verified_document_text(raw, ("www.achs.cl",)) == ""


@pytest.mark.parametrize("tamper", ["bytes", "text", "text_sha", "tls", "redirect", "docdate", "parentdate", "record_missing"])
def test_tampered_document_cannot_become_editorial_facts(captured_documents, tamper):
    raw, loader, path, record, _ = captured_documents(ist=True)
    attach_documents(raw, loader)
    document = raw.metadata["supporting_documents"][0]
    record_path = path.with_name(path.name.rsplit("-", 1)[0] + ".json")
    if tamper == "bytes":
        path.write_bytes(path.read_bytes() + b"invented results")
    elif tamper == "text":
        document["extracted_text"] += " invented results"
    elif tamper == "text_sha":
        document["text_sha256"] = "0" * 64
    elif tamper == "tls":
        record["hops"][0]["tls"]["verified"] = False
        record_path.write_text(json.dumps(record))
    elif tamper == "redirect":
        record["hops"].insert(0, dict(record["hops"][0], url="https://attacker.invalid/file.pdf", http_status=302))
        record_path.write_text(json.dumps(record))
    elif tamper == "docdate":
        document["document_publication_date"] = "2025-01-01"
    elif tamper == "parentdate":
        document["parent_date"] = "2025-01-01"
    else:
        record_path.unlink()
    with pytest.raises(DeferredProcessing):
        verified_document_text(raw, ("ist.cl",))


def test_exact_link_must_belong_to_article(captured_documents):
    raw, loader, _, _, _ = captured_documents(ist=True, parent_link=False)
    attach_documents(raw, loader)
    assert raw.metadata["supporting_documents"] == []
    assert raw.metadata["supporting_document_diagnostics"][0]["code"] == "supporting_document_parent_binding_unverified"


def test_pdf_limits_mark_partial_extraction_and_ignore_document_dates():
    extracted = _extract(pdf_bytes(pages=41), "pdf")
    assert extracted["page_count"] == 41 and extracted["extracted_pages"] == 40
    assert extracted["truncated"] and "2099" not in extracted["extracted_text"]
    long = _extract(pptx_bytes([(1, "a" * 31_000)]), "pptx")
    assert len(long["extracted_text"]) == 30_000 and long["truncated"]


def test_pptx_numeric_order_and_unexecuted_embedded_content():
    content = pptx_bytes([(10, "diez"), (2, "dos")], extra={"ppt/embeddings/evil.bin": b"DO NOT EXECUTE"})
    text = _extract(content, "pptx")["extracted_text"]
    assert text.index("dos") < text.index("diez") and "DO NOT EXECUTE" not in text
    malicious = pptx_bytes([(1, '<!DOCTYPE malicious [<!ENTITY x "unsafe">]>&x;')])
    with pytest.raises(DeferredProcessing, match="supporting_document_text_unavailable"):
        _extract(malicious, "pptx")


def test_html_disguised_as_pdf_stays_pending(captured_documents):
    raw, loader, _, _, _ = captured_documents(ist=True, content=b"<html>Access denied</html>")
    attach_documents(raw, loader)
    assert not raw.metadata["supporting_documents"]
    assert raw.metadata["supporting_document_diagnostics"][0]["code"] == "supporting_document_media_unverified"


def test_real_four_article_hrefs_are_in_scoped_saved_parent_content():
    from radar_salud.occupational_documents import _ArticleLinks
    root = Path(__file__).resolve().parents[1]
    captures = root / "data/audits/source_e_recovery/actions"
    for url, (_, _, doc) in DOCUMENTS.items():
        run = "38117675962" if url.startswith("https://ist.cl") else "38116209530"
        base = captures / run / "inventory"
        record = json.loads((base / "capture_index.json").read_text())[url]
        hop = record["hops"][-1]
        content = (base / "capture" / hop["body_file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == hop["sha256"]
        links = _ArticleLinks(url)
        links.feed(content.decode("utf-8"))
        assert doc in links.links
