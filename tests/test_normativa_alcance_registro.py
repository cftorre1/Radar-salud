"""Dirección 12-nov-2026 (auditoría de fichas normativas): (1) fichas rotas → ficha de registro; (3) normas sin
relación con salud salen de toda la plataforma (feed, índice Normativa, fichas archivadas); la historia se conserva."""
import importlib.util
import json
from datetime import date
from pathlib import Path

from radar_salud.health_scope import outside_health
from radar_salud import normativa_index
from radar_salud.normative_minimal import BADGE, minimal_card

ROOT = Path(__file__).parents[1]
SUSESO = "Superintendencia de Seguridad Social (SUSESO)"


def _norm(subject, issuer=SUSESO):
    return {"event_type": "REGULATION", "signal_types": ["Normativa"], "source_name": issuer, "official_subject": subject}


OUT = [
    "Imparte instrucciones a las C.C.A.F. y modifica el Libro III sobre crédito social",
    "Regula desafiliación por inactividad de una Caja de Compensación de Asignación Familiar",
    "Modifica el régimen de crédito social de las CCAF",
    "Subsidio al empleo: instruye al Servicio Nacional de Capacitación y Empleo",
    "Bono extraordinario de apoyo a la niñez. Imparte instrucciones para su implementación",
    "Modifica el libro VIII del compendio de normas que regulan a las C.C.A.F.",
    "Circular miscelánea. Modifica los títulos III y V del libro I del compendio de normas que regulan a los servicios de bienestar del sector público",
    "Instruye a los servicios de bienestar del sector público sometidos a su fiscalización",
]
KEEP = [
    "Instruye asistencia técnica para la prevención de riesgos en buceo profesional, Ley N°16.744 de accidentes del trabajo",
    "Licencias médicas: instruye a las cajas de compensación sobre el ámbito de acción para emitirlas",
    "Regula la falta de capacidad para el pago de subsidios por incapacidad laboral",
    "Vigilancia de la salud post ocupacional: imparte instrucciones",
]


def test_rule_matches_the_committee_list_only():
    assert all(outside_health(_norm(s)) for s in OUT)
    assert not any(outside_health(_norm(s)) for s in KEEP)
    assert not outside_health({"signal_types": ["Noticias"], "title": "Crédito social de las CCAF sube"})  # norms only
    # The SIS name itself never counts as health wording against an out-of-scope subject, and SIS acts stay.
    assert not outside_health(_norm("Imparte instrucciones sobre GES", "Superintendencia de Salud"))


def _ews():
    spec = importlib.util.spec_from_file_location("ews_alc", ROOT / "scripts/export_web_snapshot.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_out_of_scope_norm_is_hidden_from_the_feed():
    ews = _ews()
    rows = [dict(_norm(OUT[0]), source_url="https://www.suseso.gob.cl/612/w3-article-1.html", title="Circular 3937"),
            dict(_norm(KEEP[1]), source_url="https://www.suseso.gob.cl/612/w3-article-2.html", title="Circular 3931")]
    out, keep = ews._apply_persistent_editorial_decisions(rows)
    assert out["feed_visibility"] is False and out["editorial_exclusion"] == "fuera_del_ambito_salud"
    assert keep["feed_visibility"] is True


def test_out_of_scope_norm_leaves_the_index_but_stays_in_the_registry():
    reg = {"items": {"suseso-circular-n3937": {"id": "suseso-circular-n3937", "label": "Circular N°3937", "emisor": "SUSESO",
                                               "subject": OUT[0], "url": "https://www.suseso.gob.cl/612/w3-article-1.html"},
                     "suseso-circular-n3931": {"id": "suseso-circular-n3931", "label": "Circular N°3931", "emisor": "SUSESO",
                                               "subject": KEEP[1], "url": "https://www.suseso.gob.cl/612/w3-article-2.html"}}}
    out = normativa_index.update_registry(reg, [], date(2026, 11, 12))
    assert out["items"]["suseso-circular-n3937"]["withheld"] is True
    assert not out["items"]["suseso-circular-n3931"].get("withheld")
    assert not normativa_index.publishable(dict(_norm(OUT[0]), display_title="x", normative_document_label="Circular N°3937",
                                                source_url="https://www.suseso.gob.cl/612/w3-article-1.html"))


def test_registro_list_and_minimal_wording():
    cfg = json.loads((ROOT / "data/normativa/registro.json").read_text(encoding="utf-8"))
    assert cfg["labels"] == ["Circular IF/N°541", "Circular IF/N°540", "Circular IF/N°539", "Circular IF/N°538", "Circular N°3935"]
    assert _ews()._registro_labels() == set(cfg["labels"])
    card = minimal_card({"source_name": "Superintendencia de Salud", "event_date": "2026-11-05",
                         "source_url": "https://www.superdesalud.gob.cl/normativa/circular-if-n541/",
                         "official_subject": "Aclara la determinación de la base de cálculo del deducible de la CAEC",
                         "title": "Circular IF/N°541 - Emisión: 5/11/2026"}, "Circular IF/N°541")
    assert card["editorial_badge"] == BADGE == "Ficha de registro"
    assert card["what_happened"] == "Aclara la determinación de la base de cálculo del deducible de la CAEC."
    assert card["key_points"] is None and card["related_reference_contexts"] is None
    assert "2026-11-05" not in card["what_happened"] and "Asunto oficial" not in card["what_happened"]


def test_registro_forces_the_minimal_card_over_an_automated_record():
    src = (ROOT / "scripts/export_web_snapshot.py").read_text(encoding="utf-8")
    assert "registro=label in _registro_labels()" in src and "if registro:reviewed=False" in src


def test_decided_list_and_news_presenting_a_retired_circular():
    from radar_salud.health_scope import decided_numbers, presents_retired_norm
    assert decided_numbers() == frozenset({"3937", "3936", "3928", "3927", "3925", "3923", "3922", "3921"})
    # Decided by name: later text mentioning salud cannot bring it back.
    later = dict(_norm("Modifica el régimen de crédito social de las CCAF para gastos de salud"),
                 normative_document_label="Circular N°3928", source_url="https://www.suseso.gob.cl/612/w3-article-1.html")
    assert outside_health(later)
    news = {"source_name": SUSESO, "signal_types": ["Noticias"], "source_url": "https://www.suseso.gob.cl/605/w3-article-791717.html",
            "title": "Créditos sociales: límite de descuento podrá subir del 25% al 35% para gastos de salud",
            "what_happened": "La Circular N°3928 permite elevar el límite…"}
    assert presents_retired_norm(news) and outside_health(news)
    other = dict(news, what_happened="La Circular N°3931 instruye sobre licencias médicas.")
    assert not outside_health(other)
    assert not outside_health(dict(news, source_name="Diario Financiero", source_url="https://www.df.cl/x"))
