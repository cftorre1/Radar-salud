"""Dirección 9-nov-2026: SIS circulars IF/N°538-541 were easy to miss (raw titles) and carried the
listing's publication date (5-nov) instead of their emission date; AI outage was silent."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from radar_salud import ai_health, regulatory
from radar_salud.daily_window import item_date
from radar_salud.models import RawItem
from radar_salud.normative_minimal import minimal_card, minimal_title, short_subject
from radar_salud.pending_queue import lane

SIS = "Superintendencia de Salud"
BASE = "https://www.superdesalud.gob.cl/normativa/"
# Official listing rows as SIS posted them on 5-nov-2026 ("Fecha de publicación" is the first column).
ROWS = [
    ("circular-if-n538-emision-26-10-2026", "Circular IF/N°538 - Emisión: 26/10/2026",
     "Instruye sobre la incorporación de la cobertura de Terapia Ocupacional en los formatos uniformes obligatorios "
     "de planes de salud. Fecha de emisión: 26 de octubre de 2026.", "2026-10-26"),
    ("circular-if-n539-emision-30-10-2026", "Circular IF/N°539 - Emisión: 30/10/2026",
     "Aclara el inicio del cómputo del plazo para informar pacientes en urgencia por riesgo de muerte o riesgo de "
     "secuela grave GES y personas beneficiarias de la ley N.º 20.850. Fecha de emisión: 30 de octubre de 2026.",
     "2026-10-30"),
    ("circular-if-n540-emision-4-11-2026", "Circular IF/N°540 - Emisión: 4/11/2026",
     "Actualiza la estructura del Formato Único del Plan de Salud Complementario en todas sus modalidades. "
     "Fecha de emisión: 4 de noviembre de 2026.", "2026-11-04"),
    ("circular-if-n541-emision-5-11-2026", "Circular IF/N°541 - Emisión: 5/11/2026",
     "Aclara la determinación de la base de cálculo del deducible de la Cobertura Adicional para Enfermedades "
     "Catastróficas (CAEC). Fecha de emisión: 5 de noviembre de 2026.", "2026-11-05"),
]
TITLES = {
    "Circular IF/N°538": "Circular IF/N°538 · Instruye sobre la incorporación de la cobertura de Terapia Ocupacional",
    "Circular IF/N°539": "Circular IF/N°539 · Aclara el inicio del cómputo del plazo para informar pacientes en urgencia",
    "Circular IF/N°540": "Circular IF/N°540 · Actualiza la estructura del Formato Único del Plan de Salud Complementario",
    "Circular IF/N°541": "Circular IF/N°541 · Aclara la determinación de la base de cálculo del deducible de la CAEC",
}


def _listing_html():
    head = "<table><tr><th>Fecha de publicación</th><th>Título</th><th>Resumen y modificaciones</th></tr>"
    body = "".join(f'<tr><td>05/11/2026</td><td><a href="{BASE}{slug}/">{title}</a> '
                   f'<a href="https://www.superdesalud.gob.cl/app/uploads/2026/11/{slug}.pdf">Descargar pdf</a></td>'
                   f"<td>{subject}</td></tr>" for slug, title, subject, _ in ROWS)
    return head + body + "</table>"


def _discover(monkeypatch):
    monkeypatch.setattr(regulatory, "fetch_html", lambda url: _listing_html())
    scout = regulatory.SuperintendenciaNormativaScout()
    monkeypatch.setattr(scout, "PAGES", [("Para ISAPREs y FONASA", "https://www.superdesalud.gob.cl/x/", "Isapres / Fonasa")])
    return scout, {i.title: i for i in scout.discover()}


def test_emission_date_in_official_title_wins_over_listing_publication_column(monkeypatch):
    scout, items = _discover(monkeypatch)
    for _, title, _, emitted in ROWS:
        assert items[title].event_date == emitted, title
        assert items[title].metadata["listing_date"] == "2026-11-05"
    assert scout.listing_index["circular-if-538"]["event_date"] == "2026-10-26"


def test_row_without_emission_keeps_listing_date():
    assert regulatory.listing_event_date("Circular IF/N°534", "Complementa las normas.", "14/09/2026 Circular IF/N°534") == "2026-09-14"
    assert regulatory.listing_event_date("Circular IF/N°538", "Instruye x. Fecha de emisión: 26 de octubre de 2026.",
                                         "05/11/2026 Circular IF/N°538") == "2026-10-26"


def test_late_listed_circular_stays_live_and_in_window(monkeypatch):
    _, items = _discover(monkeypatch)
    raw = items["Circular IF/N°538 - Emisión: 26/10/2026"]
    now = datetime(2026, 11, 7, 6, 16, tzinfo=timezone.utc)
    # Listed on 5-nov: new for the reader on that day although emitted on 26-oct.
    assert lane(raw, now, "2026-11-05T18:36:18+00:00") == "LIVE"
    assert str(item_date({"raw": {"source_slug": raw.source_slug, "event_date": raw.event_date,
                                  "metadata": raw.metadata}})) == "2026-11-05"


def test_history_entries_carry_official_emission_dates():
    history = json.loads(Path("data/history/superintendencia_signals.json").read_text(encoding="utf-8"))["signals"]
    by_url = {r["source_url"]: r for r in history}
    for slug, _, _, emitted in ROWS:
        assert by_url[f"{BASE}{slug}/"]["event_date"] == emitted


def test_minimal_titles_use_shortened_official_subject():
    for slug, title, subject, emitted in ROWS:
        label = title.split(" - ")[0]
        row = {"title": title, "source_name": SIS, "source_url": f"{BASE}{slug}/", "event_date": emitted,
               "official_subject": subject, "official_listing_scope": "Isapres / Fonasa"}
        card = minimal_card(row, label)
        assert card["display_title"] == TITLES[label]
        assert len(card["display_title"]) <= 110 and "Emisión" not in card["display_title"]
        assert card["normative_context"].startswith(f"Emitida por {SIS} con fecha {emitted}.")
        assert row["title"] == title  # official listing title is kept in 'title'


def test_shortening_only_removes_words():
    long = ("Imparte instrucciones sobre el procedimiento interno de notificación de casos de urgencia vital o de "
            "secuela funcional grave GES y Ley Ricarte Soto en la aplicación informática de la Superintendencia de Salud.")
    title = minimal_title("Circular IF/N°537", long)
    assert len(title) <= 110 and title.endswith("…")
    source = set(long.replace(".", "").split())
    assert set(title.split(" · ", 1)[1].rstrip("…").split()) <= source
    assert short_subject("Modifica instrucciones sobre hospitalización domiciliaria CAEC.", 90) == \
        "Modifica instrucciones sobre hospitalización domiciliaria CAEC"


def test_reviewer_rejects_title_not_derived_from_official_subject(tmp_path):
    spec = importlib.util.spec_from_file_location("reviewer", Path("scripts/review_candidate.py"))
    reviewer = importlib.util.module_from_spec(spec); spec.loader.exec_module(reviewer)
    slug, title, subject, emitted = ROWS[3]
    row = {"title": title, "source_name": SIS, "source_url": f"{BASE}{slug}/", "event_date": emitted,
           "official_subject": subject, "event_type": "REGULATION", "signal_types": ["Normativa"],
           "normative_document_label": "Circular IF/N°541", "legal_identity": "Circular IF/N°541"}
    card = {**row, **minimal_card(row, "Circular IF/N°541")}
    (tmp_path / "data").mkdir()

    def codes(sig):
        (tmp_path / "data/radar_today.json").write_text(
            json.dumps({"generated_at": "2026-11-09T00:00:00+00:00", "signals": [sig]}), encoding="utf-8")
        return [f["code"] for f in reviewer.review(tmp_path, "sha")["findings"] if f["category"] == "editorial"]

    assert "normative_minimal_contract" not in codes(card)
    assert "normative_minimal_contract" in codes({**card, "display_title": "Circular IF/N°541 · Sube el deducible CAEC"})


def _call(at, ok, error=None):
    return {"at": at, "success": ok, "error_type": error, "model": "m"}


def test_ai_failure_alert_reports_outage_without_blocking(tmp_path, monkeypatch):
    rows = [_call("2026-11-05T10:00:00+00:00", True)] + [
        _call(f"2026-11-07T0{h}:00:00+00:00", False, "RateLimitError") for h in range(5)] + [
        _call(f"2026-11-09T1{h}:00:00+00:00", False, "RateLimitError") for h in range(6)]
    now = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)
    alert = ai_health.failure_alert(rows, now)
    assert alert["message"] == ("IA externa sin respuesta: 6/6 llamadas fallaron (RateLimitError) desde 2026-11-07; "
                                "registros normativos verificados en espera")
    assert alert["blocks_pipeline"] is False
    # Fewer than 5 calls or a healthy share of successes: no alert.
    assert ai_health.failure_alert(rows[:4], now) is None
    assert ai_health.failure_alert(rows + [_call("2026-11-09T17:00:00+00:00", True)], now) is None

    (tmp_path / "data/ai_usage").mkdir(parents=True)
    (tmp_path / "data/ai_usage/responses.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    (tmp_path / "data/source_health.json").write_text(json.dumps({"sources": {"x": {"status": "ok"}}}))
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert ai_health.report(tmp_path, now)["failed"] == 6
    assert "IA externa sin respuesta: 6/6" in summary.read_text(encoding="utf-8")
    health = json.loads((tmp_path / "data/source_health.json").read_text())
    assert health["sources"] == {"x": {"status": "ok"}} and health["ai_provider"]["status"] == "alert"
    monkeypatch.setattr(ai_health, "report", lambda root: 1 / 0)
    assert ai_health.main([str(tmp_path)]) == 0


def test_verified_record_title_drops_listing_emission_suffix():
    import scripts.export_web_snapshot as exporter
    row = exporter._normative_contract({
        "title": "Circular IF/N°540 - Emisión: 4/11/2026", "event_type": "REGULATION", "signal_types": ["Normativa"],
        "source_name": SIS, "source_url": f"{BASE}circular-if-n540-emision-4-11-2026/", "event_date": "2026-11-04",
        "official_subject": ROWS[2][2]})
    assert row["display_title"].startswith("Circular IF/N°540 · ") and "Emisión" not in row["display_title"]
