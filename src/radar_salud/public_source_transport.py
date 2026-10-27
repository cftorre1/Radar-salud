"""Verified HTTPS transport restricted to the public-source lanes in scope."""
from __future__ import annotations

import io
import hashlib
from datetime import datetime, timezone
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import quote, urlsplit, urlunsplit

from .public_source_evidence import official_url


def normalized_official_url(url, slug):
    """Encode the publisher's literal spaces/Unicode without double encoding.

    DEIS currently publishes hrefs with unescaped PDF filenames. Authority is
    checked before normalization; this never broadens the official allowlist.
    """
    if not official_url(url, slug):
        raise ValueError("Public-source URL must be official HTTPS")
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc,
                      quote(parts.path, safe="/%:@!$&'()*+,;=-._~"),
                      quote(parts.query, safe="%:@!$&'()*+,;=/?-._~"), ""))


class OfficialRedirectHandler(HTTPRedirectHandler):
    def __init__(self, slug):
        super().__init__()
        self.slug = slug

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official_url(newurl, self.slug):
            raise ValueError("Public-source redirect left the official HTTPS allowlist")
        return super().redirect_request(req, fp, code, msg, headers,
                                        normalized_official_url(newurl, self.slug))


_AIA_CONTEXTS = {}


def _aia_context(host, timeout=20):
    """TLS context that completes a server chain missing its intermediate (AIA "CA Issuers").

    Browsers fetch the missing intermediate named by the leaf certificate; Python does not.
    Verification stays fully on: the intermediate is only an extra candidate, and the chain
    must still end in a trusted root and match the hostname (ISP, audit 27-oct-2026)."""
    if host in _AIA_CONTEXTS:
        return _AIA_CONTEXTS[host]
    import ssl
    from urllib.request import urlopen
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID
    leaf = x509.load_pem_x509_certificate(ssl.get_server_certificate((host, 443), timeout=timeout).encode())
    aia = leaf.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
    issuers = [d.access_location.value for d in aia if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS]
    if not issuers:
        raise ValueError("certificate has no AIA CA Issuers URL")
    with urlopen(issuers[0], timeout=timeout) as response:
        raw = response.read(200_000)
    try:
        intermediate = x509.load_der_x509_certificate(raw)
    except ValueError:
        intermediate = x509.load_pem_x509_certificate(raw)
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=intermediate.public_bytes(Encoding.PEM).decode())
    _AIA_CONTEXTS[host] = context
    return context


def _is_missing_issuer(exc):
    import ssl
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, ssl.SSLCertVerificationError) and "local issuer" in str(reason)


def download_official(url, slug, *, timeout=25, max_bytes=20 * 1024 * 1024, capture_metadata=None):
    if not official_url(url, slug):
        raise ValueError("Public-source URL must be official HTTPS")
    requested_url = normalized_official_url(url, slug)
    request = Request(requested_url, headers={"User-Agent": "RadarSaludBot/0.3 (+public-source-monitor)",
                                    "Accept": "text/html,application/pdf,application/xml;q=0.9,*/*;q=0.5"})
    # The default ProxyHandler and HTTPSHandler preserve runtime proxy and CA
    # trust. Redirects are checked before the next HTTP request is issued.
    try:
        response = build_opener(OfficialRedirectHandler(slug)).open(request, timeout=timeout)
    except Exception as exc:
        if not _is_missing_issuer(exc):
            raise
        from urllib.request import HTTPSHandler
        context = _aia_context(urlsplit(requested_url).hostname)
        response = build_opener(OfficialRedirectHandler(slug), HTTPSHandler(context=context)).open(request, timeout=timeout)
    with response:
        if not official_url(response.geturl(), slug):
            raise ValueError("Public-source response left the official HTTPS allowlist")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("Public-source capture exceeds the byte limit")
        if capture_metadata is not None:
            capture_metadata.update(url=url,requested_url=requested_url,final_url=response.geturl(),sha256=hashlib.sha256(body).hexdigest(),
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
