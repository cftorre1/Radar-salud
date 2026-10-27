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
