import importlib.util
from pathlib import Path
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest


spec = importlib.util.spec_from_file_location(
    "public_recovery", Path(__file__).parents[1] / "scripts/recover_public_sources_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


@pytest.mark.parametrize("exc,stage", [
    (URLError("Tunnel connection failed: 403 Forbidden"), "proxy_connect"),
    (URLError(socket.gaierror(-2, "Name or service not known")), "dns"),
    (URLError(ssl.SSLCertVerificationError("certificate verify failed")), "tls"),
    (URLError(TimeoutError("timed out")), "timeout"),
    (HTTPError("https://www.ispch.cl/boletin/", 403, "Forbidden", {}, None), "http"),
])
def test_distinguishes_origin_http_from_proxy_dns_tls_timeout(exc, stage):
    assert runtime.error_stage(exc) == stage


def test_redirect_to_unofficial_host_is_recorded_and_blocked_before_request():
    rows = []
    handler = runtime.TraceRedirects(rows)
    with pytest.raises(ValueError, match="official HTTPS"):
        handler.redirect_request(Request("https://www.ispch.cl/boletin/"), None,
                                 302, "Found", {}, "https://example.org/secret")
    assert rows == [{"from": "https://www.ispch.cl/boletin/", "status": 302,
                     "to": "https://example.org/secret"}]


def test_network_failure_preserves_original_url_without_marking_tls(monkeypatch, tmp_path):
    class Opener:
        def open(self, request, timeout):
            raise URLError("Tunnel connection failed: 403 Forbidden")
    monkeypatch.setattr(runtime, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(runtime.socket, "getaddrinfo", lambda *_: [(2, 1, 6, "", ("192.0.2.1", 443))])
    row = runtime.probe("fonasa", "https://www.fonasa.gob.cl/noticias/", tmp_path)
    assert row["outcome"] == "proxy_connect"
    assert row["http_status"] is None
    assert row["origin_tls_observed"] is False
    assert not list(tmp_path.iterdir())


def test_capture_is_hashed_and_does_not_export_set_cookie(monkeypatch, tmp_path):
    class Response:
        code = 200
        headers = {"Content-Type": "text/html", "Set-Cookie": "private", "Server": "nginx"}
        def geturl(self): return "https://www.ispch.cl/boletin/"
        def read(self, size): return b"<h1>Official bulletin</h1>"
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Opener:
        def open(self, request, timeout): return Response()
    monkeypatch.setattr(runtime, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(runtime.socket, "getaddrinfo", lambda *_: [])
    row = runtime.probe("isp_surveillance", "https://www.ispch.cl/boletin/", tmp_path)
    assert row["outcome"] == "captured"
    assert row["origin_tls_observed"]
    assert "Set-Cookie" not in row["headers"]
    assert (tmp_path / row["body_path"]).read_bytes() == b"<h1>Official bulletin</h1>"
