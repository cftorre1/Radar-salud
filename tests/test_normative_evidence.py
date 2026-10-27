import json
from datetime import date

from src.radar_salud.normative_evidence import EVIDENCE_DIR, capture_missing

TEXT = "Circular IF/N°537. " + "Texto oficial de la circular con instrucciones detalladas. " * 10


def _sig(**kw):
    base = {"title": "Circular IF/N°537", "source_name": "Superintendencia de Salud", "signal_types": ["Normativa"],
            "event_date": "2026-10-19", "source_url": "https://www.superdesalud.gob.cl/normativa/circular-if-n537/",
            "source_documents": [{"url": "https://www.superdesalud.gob.cl/app/uploads/2026/10/circular-if-n-537-2026.pdf"}]}
    base.update(kw)
    return base


def test_captures_official_text_once_and_skips_mismatched_or_old(tmp_path):
    calls = []
    def pdf(url):
        calls.append(url); return TEXT
    sigs = [_sig(),
            _sig(title="Resolución Exenta IF/N°11168", source_documents=[{"url": "https://www.superdesalud.gob.cl/x/res-exenta-if-n11156-2026.pdf"}]),
            _sig(title="Circular IF/N°500", event_date="2025-01-01", source_documents=[{"url": "https://www.superdesalud.gob.cl/x/circular-if-n-500.pdf"}]),
            _sig(source_name="Diario Oficial")]
    out = capture_missing(tmp_path, sigs, today=date(2026, 10, 27), pdf_text=pdf, html_fetch=lambda u: "")
    assert out == [sigs[0]["source_documents"][0]["url"]] and len(calls) == 1
    files = list((tmp_path / EVIDENCE_DIR).glob("*.json"))
    record = json.loads(files[0].read_text())
    assert record["act"] == "Circular IF/N°537" and record["text"].startswith("Circular IF/N°537") and len(record["text_sha256"]) == 64
    # Idempotent: a second run does not download again.
    assert capture_missing(tmp_path, sigs, today=date(2026, 10, 27), pdf_text=pdf, html_fetch=lambda u: "") == []
    assert len(calls) == 1


def test_suseso_html_article_and_failures_never_raise(tmp_path):
    suseso = _sig(title="Circular 3926", source_name="Superintendencia de Seguridad Social (SUSESO)",
                  source_url="https://www.suseso.gob.cl/612/w3-article-790656.html", source_documents=[])
    html = "<html><nav>menu</nav><p>" + TEXT + "</p><script>x()</script></html>"
    out = capture_missing(tmp_path, [suseso], today=date(2026, 10, 27), pdf_text=lambda u: "", html_fetch=lambda u: html)
    assert out == [suseso["source_url"]]
    def boom(url): raise TimeoutError("down")
    assert capture_missing(tmp_path / "b", [_sig()], today=date(2026, 10, 27), pdf_text=boom, html_fetch=boom) == []
