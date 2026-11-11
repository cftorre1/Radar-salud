"""Normativa phase 1 (Dirección, 10–11-nov-2026): standing registry, literal effective dates, manual review."""
import json
import re
from datetime import date
from pathlib import Path

from radar_salud import normativa_index as ni

ROOT = Path(__file__).resolve().parents[1]


def sig(label, typ, src="Superintendencia de Salud", validity=None, ev="2026-11-02", url=None, title=None):
    return {"normative_document_label": label, "normative_document_type": typ, "source_name": src, "event_type": "REGULATION",
            "signal_types": ["Normativa"], "validity_text": validity, "event_date": ev, "source_url": url or f"https://x/{label}",
            "display_title": title or f"{label} · Asunto de {label}"}


def test_parse_validity_is_literal_only():
    p = ni.parse_validity
    assert p("Las disposiciones comenzarán a regir a partir del 1° de enero de 2027 .") == {"kind": "date", "eff": "2027-01-01", "prec": "day", "target": None}
    assert p("Las disposiciones comienzan a regir a contar del mes de marzo de 2027. Dentro de ese plazo…")["prec"] == "month"
    assert p("desde su publicación. Contiene disposiciones transitorias")["kind"] == "on_publication"
    # Review of #180: notification and the Diario Oficial are their own triggers, also OCR-spaced.
    assert p("Las disposiciones de la presente Circular entrarán en vigencia a contar de su notificación.")["kind"] == "on_notification"
    assert p("a contar de la fecha de su not ificació n")["kind"] == "on_notification"
    assert p("desde la fecha de notificación de la Circular")["kind"] == "on_notification"
    assert p("Las disposiciones de la presente Circular entrarán en vigencia a contar de la fecha de su publ icació n en el Diario Oficial")["kind"] == "on_publication_do"
    assert p("a contar de su fecha de publicación")["kind"] == "on_publication"
    assert p("a contar de esta fecha")["kind"] == "on_emission"
    # Never an entry into force: operational starts, deadlines, expiries, impossible dates, relative terms.
    for t in ("Inicio operativo informado: 30 de septiembre de 2026", "Las Isapres deberán remitir el archivo hasta el 15 de enero de 2027.",
              "La autorización tiene vigencia hasta el 30 de junio de 2029.", "Entra en vigencia el 31 de febrero de 2027.",
              "6 meses corridos contados desde su publicación. Contiene disposiciones transitorias.", None, ""):
        assert p(t)["kind"] == "none", t
    # «desde su notificación» wins over a later expiry date; exceptions and several dates are partial.
    r = p("Las instrucciones rigen desde su notificación y se mantiene hasta el 31 de diciembre de 2026.")
    assert r["kind"] == "on_notification" and r["partial"]
    assert p("A partir del 1° de octubre de 2026, salvo aquellas que constan en el numeral 10.2, cuya")["partial"]
    assert p("Capítulo I de esta Circular, desde 30 de enero de 2026 y el Capítulo II desde el 30 de abril de 2026,")["partial"]
    # A date after a cue, not the emission date that precedes it.
    assert p("La Circular IF N°505, de 13 de agosto de 2025, entrará en vigencia el 1 de enero de 2026.")["eff"] == "2026-01-01"
    assert p("4 de enero de 2027")["eff"] == "2027-01-04"
    r = p("La Circular IF/N° 532 difirió su entrada en vigencia hasta el 1 de enero de 2027.")
    assert r["target"] == "Circular IF/N°532" and r["eff"] == "2027-01-01"


def test_every_historical_date_has_an_entry_into_force_cue():
    """Every date the parser takes from the real captured texts follows a cue or is the whole text (review of #180)."""
    sig = json.loads((ROOT / "data/history/superintendencia_signals.json").read_text(encoding="utf-8"))["signals"]
    for t in {s["validity_text"] for s in sig if s.get("validity_text")}:
        r = ni.parse_validity(t)
        if r["kind"] == "date":
            assert not re.search(r"(?i)^\s*Inicio operativo|deber[aá]n remitir", t), t

def test_registry_never_drops_by_age_and_keeps_literal_text():
    reg = ni.update_registry({"items": {}}, [sig("Circular IF/N°534", "Circular", validity="Las disposiciones entran en vigencia el 1 de diciembre de 2026.")], date(2026, 11, 11))
    key = next(iter(reg["items"]))
    later = ni.update_registry(reg, [], date(2027, 6, 1))  # out of the 90-day feed: still there
    assert key in later["items"]
    again = ni.update_registry(later, [sig("Circular IF/N°534", "Circular", validity=None)], date(2027, 6, 2))
    assert again["items"][key]["validity"].startswith("Las disposiciones entran") and again["items"][key]["first_seen"] == "2026-11-11"


def test_build_groups_inputs_topics_review_and_ficha():
    s = [sig("Circular IF/N°541", "Circular", validity="desde su publicación", title="Circular IF/N°541 · Aclara el deducible CAEC"),
         sig("Circular N°3930", "Circular", src="SUSESO", validity="desde 1° de marzo de 2027", title="Circular N°3930 · Licencias médicas en papel"),
         sig("Circular N°3935", "Circular", src="SUSESO", title="Circular N°3935 · Pago de remuneraciones"),
         {**sig("Dictamen O-02-S-03153-2026", None, src="SUSESO", validity="Inicio operativo informado: 30 de septiembre de 2026"), "normative_document_type": None},
         sig("Ley 21.822", "Ley", src="Diario Oficial")]
    reg = ni.update_registry({"items": {}}, s, date(2026, 11, 11))
    assert len(reg["items"]) == 4  # the law is not a SIS/SUSESO norm
    review = {"decisions": {"suseso-circular-n3935": {"kind": "susp", "by": "Resolución Exenta N°1", "quote": "Se suspende la aplicación de la circular.", "on": "2026-11-12", "decided_by": "Dirección"},
                            "bad": {"kind": "susp", "by": "x", "quote": "corta", "on": "2026-11-12"}}}
    ix = ni.build(reg, review, {ni.signal_id(s[0])})
    by = {x["label"]: x for x in ix["items"]}
    assert by["Circular IF/N°541"]["tema"] == "Isapres: planes, GES y CAEC" and by["Circular IF/N°541"]["kind"] == "on_publication"
    assert by["Circular N°3930"]["tema"] == "Licencias médicas y SIL" and by["Circular N°3930"]["eff"] == "2027-03-01"
    assert by["Dictamen O-02-S-03153-2026"]["type"] == "Dictamen" and by["Dictamen O-02-S-03153-2026"]["kind"] == "none"  # «Inicio operativo» is not a vigencia
    assert by["Circular N°3935"]["review"]["kind"] == "susp" and by["Circular N°3935"]["kind"] == "none"
    assert by["Circular IF/N°541"]["in_feed"] and not by["Circular N°3930"]["in_feed"]
    assert all(x["ficha"].startswith(f"index.html?abrir=1&desde=normativa&n={x['id']}#sig-") for x in ix["items"])
    assert ix["review_pending"] == 1  # the Dictamen; 3935 has a decision; the others carry a literal rule


def test_signal_id_matches_al_dia():
    import base64
    s = {"source_url": "https://www.superdesalud.gob.cl/x/", "event_date": "2026-09-14", "event_type": "REGULATION"}
    assert base64.b64decode(ni.signal_id(s)).decode() == "https://www.superdesalud.gob.cl/x/|2026-09-14|REGULATION"
    assert ni.signal_id({"piece_id": "p"}) == "p"


def test_published_index_is_built_from_the_registry_and_review():
    pub = json.loads((ROOT / "web/data/normativa.json").read_text(encoding="utf-8"))
    reg = json.loads((ROOT / ni.REGISTRY).read_text(encoding="utf-8"))
    review = json.loads((ROOT / ni.REVIEW).read_text(encoding="utf-8"))
    assert pub["schema"] == ni.SCHEMA and pub["count"] == len(reg["items"]) >= 31
    rebuilt = ni.build(reg, review, {x["signal_id"] for x in pub["items"] if x.get("in_feed")}, pub.get("generated_at"))
    assert rebuilt["items"] == pub["items"]
    for x in pub["items"]:
        assert x["kind"] in ("date", "on_publication", "on_notification", "on_publication_do", "on_emission", "none") and x["emisor"] in ("SIS", "SUSESO")
        if x["kind"] == "date":
            assert x["validity"], x["label"]  # every date comes from captured literal text


def test_export_writes_normativa_next_to_the_snapshot_and_workflows_keep_the_registry():
    src = (ROOT / "scripts/export_web_snapshot.py").read_text(encoding="utf-8")
    assert "normativa_index.export(" in src
    for wf in ("daily-radar.yml", "queue-hourly.yml"):
        assert "git add data/normativa" in (ROOT / ".github/workflows" / wf).read_text(encoding="utf-8")


def test_withheld_and_withdrawn_norms_leave_the_public_index_and_offline_builds_never_write(tmp_path):
    s = sig("Circular IF/N°534", "Circular", validity="Las disposiciones entran en vigencia el 1 de diciembre de 2026.")
    reg = ni.update_registry({"items": {}}, [s], date(2026, 11, 11))
    key = next(iter(reg["items"]))
    held = ni.update_registry(reg, [{**s, "editorial_committee": {"verdict": "HOLD"}}], date(2026, 11, 12))
    assert held["items"][key]["withheld"] and ni.build(held, {}, set())["items"] == []
    back = ni.update_registry(held, [s], date(2026, 11, 13))
    assert not back["items"][key].get("withheld") and len(ni.build(back, {}, set())["items"]) == 1
    gone = {"decisions": {key: {"kind": "retirada", "on": "2026-11-14", "decided_by": "Dirección"}}}
    assert ni.build(back, gone, set())["items"] == []
    # No churn: the same capture leaves the record untouched.
    assert ni.update_registry(back, [s], date(2027, 1, 5)) == back
    # Offline / --as-of builds read the registry but never write it.
    (tmp_path / "data/normativa").mkdir(parents=True)
    (tmp_path / "web").mkdir()
    ni.export([s], tmp_path, tmp_path / "web", date(2026, 10, 12), persist=False)
    assert not (tmp_path / ni.REGISTRY).exists() and (tmp_path / "web/normativa.json").exists()
