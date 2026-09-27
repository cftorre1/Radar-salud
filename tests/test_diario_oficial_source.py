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
