import pytest

import src.radar_salud.diario_oficial as diario


def test_fetch_with_retry_recovers_after_transient_failures(monkeypatch):
    calls = []

    def fake_fetch(url, timeout=20):
        calls.append((url, timeout))
        if len(calls) < 3:
            raise TimeoutError("temporary")
        return "<html>ok</html>"

    monkeypatch.setattr(diario, "fetch_html", fake_fetch)
    monkeypatch.setattr(diario.time, "sleep", lambda *_: None)

    html = diario._fetch_with_retry("https://example.test", attempts=3, timeout=7, backoff=0.01)

    assert html == "<html>ok</html>"
    assert len(calls) == 3
    assert all(timeout == 7 for _, timeout in calls)


def test_fetch_with_retry_fails_closed_after_bounded_attempts(monkeypatch):
    calls = []

    def fake_fetch(url, timeout=20):
        calls.append((url, timeout))
        raise TimeoutError("still unavailable")

    monkeypatch.setattr(diario, "fetch_html", fake_fetch)
    monkeypatch.setattr(diario.time, "sleep", lambda *_: None)

    with pytest.raises(RuntimeError, match="Diario Oficial unavailable after 2 attempts"):
        diario._fetch_with_retry("https://example.test", attempts=2, timeout=5, backoff=0.01)

    assert len(calls) == 2


def test_section_urls_does_not_convert_index_failure_into_zero_signals(monkeypatch):
    monkeypatch.setattr(
        diario,
        "_fetch_with_retry",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        diario._section_urls(diario.date(2026, 9, 27))


def test_titles_come_from_their_own_listing_entry(monkeypatch):
    from radar_salud import diario_oficial as do
    html = ('<table><tr><td>MINISTERIO DE SALUD</td></tr><tr><td>Instituto de Salud Pública</td></tr>'
            '<tr><td><span class="border dotted">Extracto de resolución exenta número 3.955, de 2026.- Requiere envío digitalizado de folletos de información que indica</span></td>'
            '<td><a target="_blank" href="/pdf/a.pdf">Ver PDF</a> (CVE-2885722)</td></tr><!-- reach -->'
            '<tr><td>MINISTERIO DE SALUD</td></tr><tr><td>Subsecretaría de Redes Asistenciales</td></tr>'
            '<tr><td>Resolución exenta número 732, de 2026.- Fija metas sanitarias y de mejoramiento de la atención</td>'
            '<td><a target="_blank" href="/pdf/b.pdf">Ver PDF</a> (CVE-2880923)</td></tr></table>')
    monkeypatch.setattr(do, "_section_urls", lambda d: ["https://www.diariooficial.interior.gob.cl/edicionelectronica/index.php"])
    monkeypatch.setattr(do, "_fetch_with_retry", lambda url, **kw: html)
    items = do.DiarioOficialHealthScout().discover(days_back=1)
    titles = [i.title for i in items]
    assert titles == ["Extracto de resolución exenta número 3.955, de 2026.- Requiere envío digitalizado de folletos de información que indica",
                      "Resolución exenta número 732, de 2026.- Fija metas sanitarias y de mejoramiento de la atención"]


def test_issuer_header_carries_over_and_ends_at_another_ministry(monkeypatch):
    from radar_salud import diario_oficial as do
    html = ('<p>MINISTERIO DE SALUD</p><p>Subsecretaría de Salud Pública</p>'
            '<p>Resolución exenta número 691, de 2026.- Crea el Consejo Nacional de Salud</p><a href="/a.pdf">Ver PDF</a> (CVE-1)'
            '<p>Resolución exenta número 692, de 2026.- Designa integrantes del Consejo Nacional de Salud</p><a href="/b.pdf">Ver PDF</a> (CVE-2)'
            '<p>Secretaría Regional Ministerial Región de La Araucanía</p>'
            '<p>Resolución exenta número CP 20.158, de 2026.- Declara zona de riesgo sanitario la comuna de Lumaco</p><a href="/c.pdf">Ver PDF</a> (CVE-3)'
            '<p>MINISTERIO DE TRANSPORTES Y TELECOMUNICACIONES</p>'
            '<p>Resolución exenta número 402, de 2026.- Modifica resolución que indica</p><a href="/d.pdf">Ver PDF</a> (CVE-4)')
    monkeypatch.setattr(do, "_section_urls", lambda d: ["https://www.diariooficial.interior.gob.cl/edicionelectronica/index.php"])
    monkeypatch.setattr(do, "_fetch_with_retry", lambda url, **kw: html)
    items = do.DiarioOficialHealthScout().discover(days_back=1)
    assert [i.title.split(",")[0] for i in items] == ["Resolución exenta número 691", "Resolución exenta número 692",
                                                     "Resolución exenta número CP 20.158"]
    assert items[2].metadata["issuer"] == "SEREMI de Salud"


def test_non_ministry_headers_end_the_health_block(monkeypatch):
    from radar_salud import diario_oficial as do
    html = ('<p>MINISTERIO DE SALUD</p><p>Subsecretaría de Redes Asistenciales</p>'
            '<p>Resolución exenta número 357, de 2026.- Aprueba arsenal farmacológico</p><a href="/a.pdf">Ver PDF</a> (CVE-1)'
            '<p>CONSEJO PARA LA TRANSPARENCIA</p>'
            '<p>Resolución exenta número 88, de 2026.- Aprueba instrucción general</p><a href="/b.pdf">Ver PDF</a> (CVE-2)')
    monkeypatch.setattr(do, "_section_urls", lambda d: ["https://www.diariooficial.interior.gob.cl/edicionelectronica/index.php"])
    monkeypatch.setattr(do, "_fetch_with_retry", lambda url, **kw: html)
    assert [i.title.split(",")[0] for i in do.DiarioOficialHealthScout().discover(days_back=1)] == ["Resolución exenta número 357"]
