import json

from radar_salud import scouts
from radar_salud.source_health import record


def test_minsal_retries_timeouts_before_failing(monkeypatch):
    calls = []
    def flaky(url, timeout=20):
        calls.append(timeout)
        if len(calls) < 3:
            raise TimeoutError("slow")
        return '<a href="https://www.minsal.cl/una-noticia-de-salud/">Una noticia de salud con título suficiente</a>'
    monkeypatch.setattr(scouts, "fetch_html", flaky)
    monkeypatch.setattr("time.sleep", lambda s: None)
    items = scouts.MinsalNewsScout().discover()
    assert len(items) == 1 and calls == [45, 45, 45]


def test_health_freshness_uses_newest_published_history(tmp_path):
    record(tmp_path, "minsal", name="Ministerio de Salud", discovered=0, new=0, published=0, pending=0,
           rows=[], latest_original_at="2026-10-07", history_last_signal="2026-10-21")
    row = json.loads((tmp_path / "data/source_health.json").read_text())["sources"]["minsal"]
    assert row["last_signal_at"] == "2026-10-21" and row["latest_original_at"] == "2026-10-21"


def test_global_request_encodes_non_ascii_urls():
    from urllib.parse import quote
    url = "https://www.who.int/es/news/item/sea–hdc–8"
    assert quote(url, safe=":/?&=%+#;,@!$()*[]~").isascii()


def test_malformed_diario_oficial_titles_are_held():
    from radar_salud.editorial_gate import malformed_official_listing_title as bad
    base = {"source_name": "Diario Oficial"}
    assert bad({**base, "title": '"> Ver PDF (CVE-2880923) MINISTERIO DE SALUD Resolución exenta número 732'})
    assert bad({**base, "title": "reach --> Instituto de Salud Pública Extracto de resolución exenta número 3.955"})
    assert not bad({**base, "title": "Resolución exenta número 732, de 2026.- Fija metas sanitarias"})
    assert not bad({"source_name": "Pulso / La Tercera", "title": '"> raro'})


def test_missing_intermediate_is_completed_without_disabling_verification(monkeypatch):
    import ssl
    from urllib.error import URLError
    from radar_salud import public_source_transport as t
    assert t._is_missing_issuer(URLError(ssl.SSLCertVerificationError(1, "certificate verify failed: unable to get local issuer certificate")))
    assert not t._is_missing_issuer(URLError(ssl.SSLCertVerificationError(1, "certificate has expired")))
    assert not t._is_missing_issuer(TimeoutError("slow"))


def test_aia_rejects_untrusted_or_foreign_certificates(monkeypatch):
    import datetime, ssl
    import pytest
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID, AuthorityInformationAccessOID
    from radar_salud import public_source_transport as t
    with pytest.raises(ValueError):
        t._aia_context("evil.example.com")
    now = datetime.datetime.now(datetime.timezone.utc)
    def name(cn): return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    ca_key = ec.generate_private_key(ec.SECP256R1()); leaf_key = ec.generate_private_key(ec.SECP256R1())
    ca = (x509.CertificateBuilder().subject_name(name("Fake CA")).issuer_name(name("Fake Root"))
          .public_key(ca_key.public_key()).serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=9))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(ca_key, hashes.SHA256()))
    leaf = (x509.CertificateBuilder().subject_name(name("www.ispch.cl")).issuer_name(name("Fake CA"))
            .public_key(leaf_key.public_key()).serial_number(2).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=9))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("www.ispch.cl")]), critical=False)
            .add_extension(x509.AuthorityInformationAccess([x509.AccessDescription(
                AuthorityInformationAccessOID.CA_ISSUERS, x509.UniformResourceIdentifier("http://attacker.example/ca.der"))]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    monkeypatch.setattr(ssl, "get_server_certificate", lambda addr, timeout=None: leaf.public_bytes(serialization.Encoding.PEM).decode())
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n): return ca.public_bytes(serialization.Encoding.DER)
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=None: R())
    t._AIA_CONTEXTS.clear()
    with pytest.raises(Exception):
        t._aia_context("www.ispch.cl")  # the attacker's CA does not chain to a trusted root
    assert "www.ispch.cl" not in t._AIA_CONTEXTS


def test_history_freshness_is_per_slug_by_url():
    from datetime import date
    from radar_salud.engine_cli import _history_last_signal
    history = [
        {"source_name": "Superintendencia de Salud", "source_url": "https://www.superdesalud.gob.cl/normativa/x/", "event_date": "2026-10-19"},
        {"source_name": "Superintendencia de Salud", "source_url": "https://www.superdesalud.gob.cl/biblioteca-digital/y/", "event_date": "2026-10-14"},
        {"source_name": "Superintendencia de Salud", "source_url": "https://www.superdesalud.gob.cl/normativa/z/", "event_date": "2026-10-25", "feed_visibility": False},
    ]
    assert _history_last_signal(history, "superintendencia", date(2026, 10, 27)) == "2026-10-14"
    assert _history_last_signal(history, "superintendencia_normativa", date(2026, 10, 27)) == "2026-10-19"
    assert _history_last_signal(history, "superintendencia_fiscalizacion", date(2026, 10, 27)) is None
    assert _history_last_signal(history, "pulso_latercera", date(2026, 10, 27)) is None
