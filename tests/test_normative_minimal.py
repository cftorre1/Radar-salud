import importlib.util
import json
from pathlib import Path

from src.radar_salud.normative_minimal import BADGE, DISCLAIMER, act_scope, minimal_card

SIS = "Superintendencia de Salud"
SUSESO = "Superintendencia de Seguridad Social (SUSESO)"


def _if537():
    return {"title": "Circular IF/N°537", "source_name": SIS, "event_date": "2026-10-19",
            "source_url": "https://www.superdesalud.gob.cl/normativa/circular-if-n537/",
            "what_happened": "Interpretación automática que no debe publicarse sin revisión.",
            "why_it_matters": "Impacto interpretado.", "scopes": ["Prestadores"],
            "related_reference_ids": ["Circular IF/N°77, de 25 de julio de 2008"],
            "related_reference_contexts": [{"id": "Circular IF/N°77, de 25 de julio de 2008",
                                            "relationship": "Compendio de Normas Administrativas en Materia de Beneficios modificado"}]}


def test_general_act_gets_only_verifiable_facts_and_badge():
    card = minimal_card(_if537(), "Circular IF/N°537")
    assert card["display_title"] == "Circular IF/N°537 · Superintendencia de Salud: modifica Circular IF/N°77"
    assert card["editorial_badge"] == BADGE and card["why_it_matters"] == DISCLAIMER == card["card_why"]
    # The automatic interpretation never reaches the card.
    assert "Interpretación" not in json.dumps(card, ensure_ascii=False)
    assert "Impacto interpretado" not in json.dumps(card, ensure_ascii=False)


def test_individual_accreditation_never_gets_a_card():
    act = {"title": "Resolución Exenta IP/N°7844", "source_name": SIS, "event_date": "2026-10-05",
           "source_url": "https://www.superdesalud.gob.cl/normativa/resolucion-exenta-ip-n7844/",
           "what_happened": "La Superintendencia de Salud mantuvo a Clínica Dávila bajo la inscripción N°2 del Registro Público de Prestadores Institucionales de Salud Acreditados."}
    assert act_scope(act, "Resolución Exenta IP/N°7844") == "particular"
    assert minimal_card(act, "Resolución Exenta IP/N°7844") is None


def test_unofficial_domain_or_diario_oficial_stay_held():
    spoof = {**_if537(), "source_url": "https://superdesalud.gob.cl.example.com/x"}
    assert minimal_card(spoof, "Circular IF/N°537") is None
    do = {**_if537(), "source_name": "Diario Oficial", "source_url": "https://www.diariooficial.interior.gob.cl/x.pdf"}
    assert minimal_card(do, "Circular IF/N°537") is None


def test_suseso_official_heading_is_used_verbatim_in_sentence_case():
    c = {"title": "Circular 3923", "source_name": SUSESO, "event_date": "2026-08-21",
         "source_url": "https://www.suseso.gob.cl/612/w3-article-788432.html", "scopes": ["Salud laboral"],
         "what_happened": "Circular 3923 MODIFICA EL LIBRO VIII DEL COMPENDIO DE NORMAS QUE REGULAN A LAS C.C.A.F., EN DIVERSOS ASPECTOS QUE INDICA."}
    card = minimal_card(c, "Circular N°3923")
    assert card["display_title"].endswith("Modifica el libro VIII del compendio de normas que regulan a las C.C.A.F., en diversos aspectos que indica")


def test_nothing_verifiable_beyond_number_stays_held():
    bare = {**_if537(), "related_reference_contexts": [], "related_reference_ids": []}
    assert minimal_card(bare, "Circular IF/N°537") is None


def test_reviewer_accepts_minimal_card_and_rejects_interpretation(tmp_path):
    spec = importlib.util.spec_from_file_location("reviewer", Path("scripts/review_candidate.py"))
    reviewer = importlib.util.module_from_spec(spec); spec.loader.exec_module(reviewer)
    base = {**_if537(), **minimal_card(_if537(), "Circular IF/N°537"), "event_type": "REGULATION",
            "signal_types": ["Normativa"], "normative_document_label": "Circular IF/N°537"}
    (tmp_path / "data").mkdir()

    def run(sig):
        (tmp_path / "data/radar_today.json").write_text(json.dumps({"generated_at": "2026-10-26T00:00:00+00:00", "signals": [sig]}), encoding="utf-8")
        return [f["code"] for f in reviewer.review(tmp_path, "sha")["findings"] if f["category"] == "editorial"]

    assert "normative_minimal_contract" not in run(base)
    assert "normative_minimal_contract" in run({**base, "why_it_matters": "Las isapres deberán cambiar procesos."})
    assert "normative_minimal_contract" in run({**base, "editorial_badge": None})
