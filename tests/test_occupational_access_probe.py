from scripts.occupational_access_probe import official_url, safe_headers, waf_kind


def test_probe_never_exposes_set_cookie_or_authorization():
    result = safe_headers("HTTP/2 200\r\nSet-Cookie: private=secret\r\nAuthorization: token\r\nServer: origin\r\nContent-Type: text/html\r\n\r\n")
    assert result == [{"status_line": "HTTP/2 200", "server": "origin", "content-type": "text/html"}]


def test_only_explicit_official_tls_routes_allowed():
    assert official_url("https://ist.cl/noticias/")
    for url in ["http://ist.cl/", "https://ist.cl.attacker.test/", "https://user:pass@ist.cl/", "https://ist.cl:8443/"]:
        assert not official_url(url)


def test_waf_is_not_successful_newsroom_content():
    assert waf_kind(b'<iframe src="/_Incapsula_Resource"></iframe>') == "incapsula_challenge"
    assert waf_kind(b"<h1>Noticias</h1><article>Contenido</article>") is None


def test_header_blocks_preserve_proxy_and_origin_separately():
    headers = safe_headers("HTTP/1.1 200 Connection established\r\n\r\nHTTP/2 302\r\nLocation: https://ist.cl/noticias/\r\nSet-Cookie: secret\r\n\r\n")
    assert len(headers) == 2
    assert headers[1]["location"] == "https://ist.cl/noticias/"
    assert "set-cookie" not in headers[1]


def test_private_portal_routes_never_enter_the_public_probe():
    assert not official_url("https://www.mutual.cl/portal/privado/empresas/sucursalvirtual/")
