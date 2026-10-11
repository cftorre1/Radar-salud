"""Bound, saved public documents; no inferred dates or automatic reassessment."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree
from zipfile import ZipFile

from .occupational_sources import Article, SourceDiscoveryError, fold
from .paths import project_root
from .processing import DeferredProcessing

ACHS_NEWS = "https://www.achs.cl/centro-de-noticias/noticia/2026/"
DOCUMENTS = {
    ACHS_NEWS + "nueva-guia-entrega-orientaciones-basadas-en-evidencia-para-el-abordaje-de-la-salud-mental-laboral":
        ("achs_seguro_laboral", "2026-09-24", "https://www.achs.cl/docs/librariesprovider2/2026/achs-437334/guia-tratamiento-psicologico.pdf?sfvrsn=fbec0931_1"),
    ACHS_NEWS + "accidentes-de-trayecto-en-scooter-aumentan-cerca-de-un-37-durante-el-primer-semestre-de-2026":
        ("achs_seguro_laboral", "2026-09-15", "https://www.achs.cl/docs/librariesprovider2/2026/achs-435774/achs-infografia-scooter.pdf?sfvrsn=fe766532_1"),
    ACHS_NEWS + "achs-virtual-estrena-modulo-que-anticipa-accidentes-graves-y-fatales-con-inteligencia-artificial":
        ("achs_seguro_laboral", "2026-07-15", "https://www.achs.cl/docs/librariesprovider2/2026/achs-422711/ppt-lgf.pptx?sfvrsn=7908d12d_1"),
    "https://ist.cl/reporte-sostenibilidad-2025/":
        ("ist", "2026-07-14", "https://ist.cl/wp-content/uploads/2026/07/Reporte-de-sostenibilidad-2025.pdf"),
}
MAX_BYTES, MAX_PAGES, MAX_TEXT = 20_000_000, 40, 30_000
IST_REPORT_URL = "https://ist.cl/reporte-sostenibilidad-2025/"
IST_DOCUMENT_URL = DOCUMENTS[IST_REPORT_URL][2]
IST_FINANCIAL_PROFILE = "ist_2025_financial_context_v1"
IST_SELECTED_PAGES = tuple(range(53, 61)) + tuple(range(1, 33))


class _ArticleLinks(HTMLParser):
    """Links after the article H1, excluding navigation and related sections."""
    def __init__(self, url):
        super().__init__()
        self.url, self.links = url, []
        self.active = self.stopped = False
        self.ignored, self.heading, self.parts, self.href = [], None, [], None

    def handle_starttag(self, tag, attrs):
        if tag in Article.IGNORE:
            self.ignored.append(tag)
            return
        if self.ignored:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self.heading, self.parts = tag, []
        if tag == "a" and self.active and not self.stopped:
            self.href = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.pop()
            return
        if tag == self.heading:
            if tag == "h1" and not self.active:
                self.active = True
            elif fold(" ".join(self.parts)) in Article.STOP:
                self.stopped = True
            self.heading = None
        if tag == "a" and self.href is not None:
            self.links.append(urljoin(self.url, self.href))
            self.href = None

    def handle_data(self, data):
        if self.heading and not self.ignored:
            self.parts.append(" ".join(data.split()))


def _public(url, hosts):
    from .occupational_evidence import _public as public
    return public(url, hosts)


def _parent(raw, hosts, evidence):
    from .occupational_evidence import _captured, verify_capture
    verify_capture(raw, hosts)
    html = _captured(evidence, raw.url, hosts)
    links = _ArticleLinks(raw.url)
    links.feed(html)
    return set(links.links)


def _binary(evidence, url, hosts):
    """Re-read both the saved response record and its exact binary bytes."""
    if (not isinstance(evidence, dict) or evidence.get("url") != url or not _public(url, hosts)
            or not _public(evidence.get("final_url"), hosts)
            or evidence.get("http_status") != 200 or evidence.get("tls_verified") is not True):
        raise DeferredProcessing("supporting_document_capture_authority_unverified")
    root = project_root().resolve()
    path = Path(evidence.get("artifact", ""))
    path = path.resolve() if path.is_absolute() else (root / path).resolve()
    match = re.fullmatch(r"([0-9a-f]{20})-\d+\.body", path.name)
    if (not match or not path.is_relative_to(root / "data/audits/source_e_recovery")
            or not path.is_file()):
        raise DeferredProcessing("supporting_document_artifact_unavailable")
    try:
        record_path = path.with_name(match[1] + ".json")
        if not record_path.resolve().is_relative_to(root / "data/audits/source_e_recovery"):
            raise ValueError("record outside audit root")
        record = json.loads(record_path.read_text())
        hops = record["hops"]
        last = hops[-1]
        identity = hashlib.sha256((url + "\n" + record["user_agent"]).encode()).hexdigest()[:20]
        if (identity != match[1] or record["url"] != url or record["final_url"] != evidence["final_url"]
                or record.get("stop_reason") != "response_captured" or record.get("waf")
                or record.get("http_status") != 200 or last["url"] != record["final_url"]
                or last["body_file"] != path.name or last["sha256"] != evidence["sha256"]
                or any(not _public(h["url"], hosts) or h.get("curl_exit") != 0
                       or h.get("waf") or h.get("tls", {}).get("verified") is not True for h in hops)
                or any(h["http_status"] not in (301, 302, 303, 307, 308) for h in hops[:-1])
                or last["http_status"] != 200):
            raise ValueError("saved response chain differs from capture evidence")
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        raise DeferredProcessing("supporting_document_saved_response_unverified") from exc
    if path.stat().st_size > MAX_BYTES:
        raise DeferredProcessing("supporting_document_capture_bytes_mismatch")
    data = path.read_bytes()
    if (len(data) > MAX_BYTES or len(data) != last.get("bytes")
            or hashlib.sha256(data).hexdigest() != evidence.get("sha256")):
        raise DeferredProcessing("supporting_document_capture_bytes_mismatch")
    suffix = urlsplit(url).path.rsplit(".", 1)[-1].lower()
    media = (last.get("content_type") or "").split(";", 1)[0].strip().lower()
    allowed = {"pdf": {"application/pdf", "application/octet-stream"},
               "pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        "application/octet-stream", "application/zip"}}
    if (suffix not in allowed or media not in allowed[suffix]
            or (suffix == "pdf" and not data.startswith(b"%PDF-"))
            or (suffix == "pptx" and not data.startswith(b"PK\x03\x04"))):
        raise DeferredProcessing("supporting_document_media_unverified")
    return data, suffix


def _extract(data, kind, *, document_url=None):
    pages = []
    financial_profile = kind == "pdf" and document_url == IST_DOCUMENT_URL
    try:
        if kind == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise ValueError("encrypted PDF")
            count = len(reader.pages)
            if financial_profile:
                # Exact official report only: prioritize financial context while
                # retaining the same forty-page and thirty-thousand-char limits.
                numbers = [number for number in IST_SELECTED_PAGES if number <= count]
                pages = [(number, (reader.pages[number - 1].extract_text(extraction_mode="layout")
                                  if 53 <= number <= 60 else reader.pages[number - 1].extract_text()) or "")
                         for number in numbers]
            else:
                pages = [(index + 1, reader.pages[index].extract_text() or "")
                         for index in range(min(count, MAX_PAGES))]
        else:
            with ZipFile(BytesIO(data)) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                if (len(names) > 5_000 or len(names) != len(set(names)) or sum(entry.file_size for entry in entries) > 40_000_000
                        or any(entry.flag_bits & 1 for entry in entries)):
                    raise ValueError("unsafe OOXML archive")
                slides = sorted((int(match[1]), entry) for entry in entries
                                if (match := re.fullmatch(r"ppt/slides/slide(\d+)\.xml", entry.filename)))
                count = len(slides)
                for number, entry in slides[:MAX_PAGES]:
                    if entry.file_size > 2_000_000:
                        raise ValueError("slide XML exceeds extraction limit")
                    xml = archive.read(entry)
                    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                        raise ValueError("XML entities are not allowed")
                    tree = ElementTree.fromstring(xml)
                    pages.append((number, " ".join(node.text or "" for node in tree.iter()
                                  if node.tag == "{http://schemas.openxmlformats.org/drawingml/2006/main}t")))
        text = "\n\n".join(f"Página {number}:\n{value.strip()}" for number, value in pages if value.strip())
        if not text:
            raise ValueError("no extractable document text")
    except Exception as exc:
        raise DeferredProcessing(f"supporting_document_text_unavailable: {type(exc).__name__}: {str(exc)[:200]}") from exc
    bounded = text[:MAX_TEXT]
    result = {"extracted_text": bounded, "text_sha256": hashlib.sha256(bounded.encode()).hexdigest(),
              "page_count": count, "extracted_pages": len(pages), "truncated": count > len(pages) or len(text) > MAX_TEXT}
    if financial_profile:
        result.update(extraction_profile=IST_FINANCIAL_PROFILE,
                      extracted_page_numbers=[number for number, _ in pages],
                      retained_page_numbers=[int(number) for number in re.findall(r"(?:^|\n)Página (\d+):", bounded)],
                      selection="financial_pages53_to60_then_first32; bounded40_pages30000_characters")
    return result


def attach_documents(raw, loader):
    """Attach optional saved evidence; leave primary HTML and dates unchanged."""
    binding = DOCUMENTS.get(raw.url)
    if not binding or raw.source_slug != binding[0]:
        return raw
    from .beta_sources import CuratedBetaSourceScout
    hosts = CuratedBetaSourceScout.SOURCES[raw.source_slug]["hosts"]
    document_url = binding[2]
    raw.metadata["supporting_documents_required"] = raw.source_slug == "ist"
    raw.metadata["supporting_documents"] = []
    diagnostics = raw.metadata["supporting_document_diagnostics"] = []
    try:
        if not raw.metadata.get("capture_evidence"):
            raw.metadata["capture_evidence"] = loader.evidence(raw.url)
        links = _parent(raw, hosts, raw.metadata["capture_evidence"])
        if raw.event_date != binding[1] or document_url not in links:
            raise DeferredProcessing("supporting_document_parent_binding_unverified")
        loader(document_url)  # Apply the existing robots/capture policy; do not use UTF-8 decoded binary.
        evidence = loader.evidence(document_url)
        data, kind = _binary(evidence, document_url, hosts)
        raw.metadata["supporting_documents"].append({
            "parent_url": raw.url, "parent_date": raw.event_date,
            "parent_publication_evidence": raw.metadata.get("publication_evidence") or raw.metadata.get("publication_date_evidence"),
            "parent_capture_evidence": dict(raw.metadata["capture_evidence"]),
            "document_url": document_url, "document_publication_date": None,
            "capture_evidence": evidence, "format": kind, "status": "verified", **_extract(data, kind, document_url=document_url),
        })
        raw.metadata["supporting_document_status"] = "verified"
    except Exception as exc:
        code = exc.code if isinstance(exc, SourceDiscoveryError) else str(exc) if isinstance(exc, DeferredProcessing) else "supporting_document_capture_unavailable"
        diagnostics.append({"code": code, "parent_url": raw.url, "document_url": document_url,
                            "detail": f"{type(exc).__name__}: {exc}"})
        raw.metadata["supporting_document_status"] = "pending_document"
    return raw


def verified_document_text(raw, hosts):
    """Return only re-extracted, byte-verified text linked by the primary article."""
    binding = DOCUMENTS.get(raw.url)
    documents = raw.metadata.get("supporting_documents", [])
    required = bool(binding and binding[0] == "ist" and raw.source_slug == "ist")
    if not documents:
        if required:
            raise DeferredProcessing("required_supporting_document_pending")
        return ""
    if (not binding or binding[0] != raw.source_slug or len(documents) != 1
            or raw.event_date != binding[1]):
        raise DeferredProcessing("supporting_document_static_binding_unverified")
    links = _parent(raw, hosts, raw.metadata.get("capture_evidence"))
    output = []
    for document in documents:
        if (document.get("status") != "verified" or document.get("parent_url") != raw.url
                or document.get("parent_date") != raw.event_date or document.get("document_url") != binding[2]
                or binding[2] not in links or document.get("document_publication_date") is not None
                or document.get("parent_capture_evidence") != raw.metadata.get("capture_evidence")
                or document.get("parent_publication_evidence") != (raw.metadata.get("publication_evidence") or raw.metadata.get("publication_date_evidence"))):
            raise DeferredProcessing("supporting_document_parent_binding_unverified")
        data, kind = _binary(document.get("capture_evidence"), document["document_url"], hosts)
        extracted = _extract(data, kind, document_url=document["document_url"])
        if (document["document_url"] == IST_DOCUMENT_URL
                and document.get("extraction_profile") != extracted.get("extraction_profile")):
            raise DeferredProcessing("supporting_document_extraction_profile_outdated")
        if document.get("format") != kind or any(document.get(key) != value for key, value in extracted.items()):
            raise DeferredProcessing("supporting_document_extracted_text_mismatch")
        output.append(f"Documento oficial asociado: {document['document_url']}\n{extracted['extracted_text']}")
    return "\n\n".join(output)


def additional_document_facts(primary_text, document_text, *, max_chars=1900):
    """Conservative numeric operational excerpts, preserving adjacent context.

    Covers, years, page labels and repeated infographic values do not create
    a new editorial input. This is an excerpt selector, not a summary or a
    claim that all facts in a long report were read.
    """
    if document_text.startswith(f"Documento oficial asociado: {IST_DOCUMENT_URL}\n"):
        financial = _ist_financial_facts(document_text, max_chars=max_chars)
        if financial:
            return financial
    def number(value):
        value = value.rstrip("%")
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", value):
            return re.sub(r"[.,]", "", value)
        return value.replace(",", ".")
    existing = {number(value) for value in re.findall(r"\b\d+(?:[.,]\d+)*%?", primary_text)}
    lines = [line.strip() for line in document_text.splitlines() if line.strip()
             and not line.startswith("Documento oficial asociado:")
             and not re.fullmatch(r"Página \d+:", line.strip())]
    operational = (r"\b(?:atenciones?|casos?|accidentes?|siniestralidad|accidentabilidad|trabajadores?|"
                   r"empleadoras?|cotizaciones?|ingresos?|excedentes?|sesiones?|tratamiento|"
                   r"evaluaciones?|pacientes?|personas?|reintegro|prestaciones?|espera|camas?|boxes|horas?|capacitacion)\b")
    units = r"(?:%|mil\b|millones?\b|casos?\b|accidentes?\b|atenciones?\b|evaluaciones?\b|trabajadores?\b|pacientes?\b|personas?\b|sesiones?\b|horas?\b|meses?\b|semanas?\b|camas?\b)"
    selected, used = [], set()
    for index, line in enumerate(lines):
        # Exclude bare page numbers and numbered headings rather than turning
        # them into measurements through their neighboring text.
        if (re.fullmatch(r"\d{1,2}", line)
                or re.match(r"^\d+(?:\.\d+){1,4}\.?\s+[A-Za-zÁÉÍÓÚáéíóú]", line)
                or re.search(r"\b(?:ley|articulo|proyecto|pagina|capitulo|seccion)\s+(?:n[o°º.]?\s*)?\d", fold(line))
                or re.fullmatch(r"\d+\s+\d+[.,]\d+\s*%", line)):
            continue
        context = " ".join(lines[max(0, index - 1):min(len(lines), index + 2)])
        if not re.search(operational, fold(context)):
            continue
        novel = False
        for value in re.findall(r"\b\d+(?:[.,]\d+)*%?", line):
            parsed = number(value)
            if re.fullmatch(r"(?:19|20)\d{2}", parsed) or parsed in existing:
                continue
            following = fold(line + " " + (lines[index + 1] if index + 1 < len(lines) else ""))
            if not re.search(re.escape(fold(value).rstrip("%")) + r"\s*" + units, following):
                continue
            novel = True
            break
        if not novel:
            continue
        # PDF line wrapping often places attribution and the data period a few
        # lines before a measurement. Keep that context with the actual value.
        for neighbor in range(max(0, index - 3), min(len(lines), index + 3)):
            if neighbor not in used:
                selected.append(lines[neighbor])
                used.add(neighbor)
    return "\n".join(selected)[:max_chars]


def _ist_financial_facts(document_text, *, max_chars):
    """Literal contextual excerpts; no arithmetic or inferred net result."""
    matches = list(re.finditer(r"(?:^|\n)Página (\d+):\n", document_text))
    pages = {int(match[1]): document_text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(document_text)]
             for index, match in enumerate(matches)}
    blocks = []
    for number, indicator in ((54, "Ingresos ordinarios"), (55, "Egresos ordinarios")):
        lines = [" ".join(line.split()) for line in pages.get(number, "").splitlines() if line.strip()]
        heading = next((line for line in lines if line.startswith("Tabla ") and indicator.lower() in line.lower()), None)
        header = next((line for line in lines if "Indicador Financiero" in line and "2025" in line and "2024" in line), None)
        row = next((line for line in lines if line.startswith(indicator) and "$" in line and "MM" in line), None)
        if heading and header and row:
            blocks.append(f"Página {number}:\n{heading}\n{header}\n{row}")
    for number, start, width in ((58, "Durante 2025, IST no registr", 2), (59, "Los fondos de reserva de IST", 4)):
        lines = [" ".join(line.split()) for line in pages.get(number, "").splitlines() if line.strip()]
        index = next((index for index, line in enumerate(lines) if fold(line).startswith(fold(start))), None)
        if index is not None:
            blocks.append(f"Página {number}:\n" + "\n".join(lines[index:index + width]))
    # Keep every table's periods, heading and values together. Never cut a
    # financial row away from its column labels to satisfy the context budget.
    selected = []
    for block in blocks:
        if len("\n\n".join(selected + [block])) <= max_chars:
            selected.append(block)
    return "\n\n".join(selected)


def documentary_materiality(raw, body, verified_text):
    from .occupational_sources import materiality
    result = materiality(raw.metadata.get("market_role") or "provider", raw.title, body)
    if result[0]:
        return result
    # The annual dataset is eligible only after actual report values were
    # captured. Its release date and the 2025 period remain separate fields.
    if (raw.source_slug == "ist" and raw.url == "https://ist.cl/reporte-sostenibilidad-2025/"
            and additional_document_facts(raw.metadata.get("page_text", ""), verified_text)):
        return True, "published_operational_study"
    return result
