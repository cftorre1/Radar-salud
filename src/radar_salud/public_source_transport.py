"""Verified HTTPS transport restricted to the public-source lanes in scope."""
from __future__ import annotations

import io
import hashlib
from datetime import datetime, timezone
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .public_source_evidence import official_url


class OfficialRedirectHandler(HTTPRedirectHandler):
    def __init__(self, slug):
        super().__init__()
        self.slug = slug

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official_url(newurl, self.slug):
            raise ValueError("Public-source redirect left the official HTTPS allowlist")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_official(url, slug, *, timeout=25, max_bytes=20 * 1024 * 1024, capture_metadata=None):
    if not official_url(url, slug):
        raise ValueError("Public-source URL must be official HTTPS")
    request = Request(url, headers={"User-Agent": "RadarSaludBot/0.3 (+public-source-monitor)",
                                    "Accept": "text/html,application/pdf,application/xml;q=0.9,*/*;q=0.5"})
    # The default ProxyHandler and HTTPSHandler preserve runtime proxy and CA
    # trust. Redirects are checked before the next HTTP request is issued.
    with build_opener(OfficialRedirectHandler(slug)).open(request, timeout=timeout) as response:
        if not official_url(response.geturl(), slug):
            raise ValueError("Public-source response left the official HTTPS allowlist")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("Public-source capture exceeds the byte limit")
        if capture_metadata is not None:
            capture_metadata.update(url=url,final_url=response.geturl(),sha256=hashlib.sha256(body).hexdigest(),
                bytes=len(body),content_type=response.headers.get_content_type(),
                captured_at=datetime.now(timezone.utc).isoformat())
        return body, response.headers


def fetch_official_html(url, slug, *, timeout=25):
    body, headers = download_official(url, slug, timeout=timeout, max_bytes=8 * 1024 * 1024)
    content_type = headers.get_content_type()
    if content_type not in {"text/html", "application/xhtml+xml"}:
        raise ValueError("Public-source HTML capture has an unexpected content type")
    return body.decode(headers.get_content_charset() or "utf-8", errors="replace")


def extract_public_source_pdf(url, slug, *, max_pages=12, capture_metadata=None):
    from pypdf import PdfReader
    body, headers = download_official(url, slug, capture_metadata=capture_metadata)
    if not body.startswith(b"%PDF-"):
        raise ValueError("Public-source document is not a PDF")
    reader = PdfReader(io.BytesIO(body))
    return "\n".join(" ".join((page.extract_text() or "").replace("\x00", " ").split())
                     for page in reader.pages[:max_pages]).strip()
