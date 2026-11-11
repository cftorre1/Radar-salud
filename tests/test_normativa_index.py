"""Normativa phase 1 (Dirección, 10–11-nov-2026): standing registry, literal effective dates, manual review."""
import json
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
    assert p("Las disposiciones de la presente Circular entrarán en vigencia a contar de la fecha de su publ icació n en el Diario Oficial")["kind"] == "on_publication"
    assert p("Las disposiciones entrarán en vigencia a contar de su notificación.")["kind"] == "on_publication"
    # A relative term is not a literal date: it goes to review.
    assert p("6 meses corridos contados desde su publicación. Contiene disposiciones transitorias.")["kind"] == "none"
    assert p(None)["kind"] == "none" and p("")["kind"] == "none"
    r = p("La Circular IF/N° 532 difirió su entrada en vigencia hasta el 1 de enero de 2027.")
    assert r["target"] == "Circular IF/N°532" and r["eff"] == "2027-01-01"


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
    assert by["Dictamen O-02-S-03153-2026"]["type"] == "Dictamen" and by["Dictamen O-02-S-03153-2026"]["eff"] == "2026-09-30"
    assert by["Circular N°3935"]["review"]["kind"] == "susp" and by["Circular N°3935"]["kind"] == "none"
    assert by["Circular IF/N°541"]["in_feed"] and not by["Circular N°3930"]["in_feed"]
    assert all(x["ficha"].startswith("index.html?abrir=1#sig-") for x in ix["items"])
    assert ix["review_pending"] == 0  # 3935 has a decision; the others carry a date or «desde su publicación»


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
        assert x["kind"] in ("date", "on_publication", "none") and x["emisor"] in ("SIS", "SUSESO")
        if x["kind"] == "date":
            assert x["validity"], x["label"]  # every date comes from captured literal text


def test_export_writes_normativa_next_to_the_snapshot_and_workflows_keep_the_registry():
    src = (ROOT / "scripts/export_web_snapshot.py").read_text(encoding="utf-8")
    assert "normativa_index.export(" in src
    for wf in ("daily-radar.yml", "queue-hourly.yml"):
        assert "git add data/normativa" in (ROOT / ".github/workflows" / wf).read_text(encoding="utf-8")
