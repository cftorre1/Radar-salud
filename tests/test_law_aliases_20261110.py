"""Dirección 10-nov-2026: widely known health laws by their common name in display titles."""
import json
import re
from pathlib import Path

import pytest

from radar_salud import law_aliases
from radar_salud.editorial_gate import malformed_official_listing_title
from radar_salud.normative_minimal import minimal_title
from radar_salud.official_titles import apply_short_title

DECREE_TITLE = ("Decreto exento número 67, de 2026.- Aprueba prestadores de salud para otorgar las prestaciones "
                "sujetas al Sistema de Protección Financiera del que trata la ley N° 20.850")
DECREE_SHORT = "Decreto exento 67/2026 · Aprueba prestadores de salud del Sistema de Protección Financiera de la ley N° 20.850"
DECREE_ALIAS = "Decreto exento 67/2026 · Aprueba prestadores de la Ley Ricarte Soto (Ley 20.850)"


def _decree():
    return {"title": DECREE_TITLE, "source_name": "Diario Oficial", "signal_types": ["Legal"], "event_type": "LEGAL",
            "source_url": "https://www.diariooficial.interior.gob.cl/publicaciones/2026/11/05/x.pdf"}


def test_decree_67_2026_names_the_ley_ricarte_soto():
    card = apply_short_title(_decree())
    assert card["display_title"] == DECREE_SHORT  # official shortening unchanged
    out, = law_aliases.apply([card])
    assert out["display_title"] == out["short_title"] == DECREE_ALIAS
    assert out["title"] == DECREE_TITLE and out["source_title_full"] == DECREE_TITLE  # official title untouched
    assert out["law_alias_applied"] == ["20850"]
    assert not malformed_official_listing_title(out)


def test_idempotent_and_any_citation_format():
    assert law_aliases.apply_alias(DECREE_ALIAS) == DECREE_ALIAS
    for cited in ("ley N° 20.850", "LEY Nº20850", "ley N.º 20.850", "Ley 20.850", "ley número 20.850"):
        assert law_aliases.apply_alias(f"Circular N°2 · Beneficiarios de la {cited}") == \
            "Circular N°2 · Beneficiarios de la Ley Ricarte Soto (Ley 20.850)", cited


@pytest.mark.parametrize("title", [
    "Resolución exenta 5/2026 · Modifica norma técnica de la ley N° 19.937",  # not in the map
    "Circular IF/N°541 · Aclara la determinación de la base de cálculo del deducible de la CAEC",  # no law cited
    "Decreto 12/2026 · Modifica el reglamento de la ley N° 20.8501",  # another number
])
def test_no_change_without_a_mapped_law(title):
    assert law_aliases.apply_alias(title) == title
    card = {"display_title": title, "source_name": "Diario Oficial", "signal_types": ["Legal"]}
    assert law_aliases.apply([card])[0] is card


def test_only_curated_entries_each_with_a_bcn_source():
    data = json.loads(Path("config/law_aliases.json").read_text(encoding="utf-8"))
    numbers = [e["number"] for e in data["laws"]]
    assert len(numbers) == len(set(numbers))
    for e in data["laws"]:
        assert re.fullmatch(r"\d{1,2}\.\d{3}", e["number"]) and e["alias"].startswith("Ley ")
        if e["basis"] == "bcn_verified":
            assert "bcn.cl/leychile" in e["source"] and "idNorma" in e["source"]
        else:  # Dirección 10-nov-2026 01:03: names BCN does not record, added by decision
            assert e["basis"] == "direccion_decision" and e["bcn_id_norma"].isdigit()
            assert e["source"] == ("decisión de Dirección 10-nov-2026 (BCN no registra nombre común; "
                                   "19.966 figura como Plan AUGE)")


@pytest.mark.parametrize("cited,expected", [
    ("ley N° 19.966", "Ley GES (Ley 19.966)"),
    ("Ley Nº 21.674", "Ley Corta de Isapres (Ley 21.674)"),
    ("ley N° 21.643", "Ley Karin (Ley 21.643)"),
])
def test_direccion_decision_aliases(cited, expected):
    assert law_aliases.apply_alias(f"Circular IF/N°700 · Instruye sobre la {cited}") == \
        f"Circular IF/N°700 · Instruye sobre la {expected}"


def test_act_identity_is_never_altered():
    title = "Resolución Exenta IF/N°20850 · Instruye sobre la ley N° 20.850"
    card = {"display_title": title, "normative_document_label": "Resolución Exenta IF/N°20850",
            "signal_types": ["Normativa"], "event_type": "REGULATION",
            "normative_editorial": {"plain_language_title": title}, "editorial_committee": {"public_title": title}}
    out, = law_aliases.apply([card])
    assert out["display_title"] == "Resolución Exenta IF/N°20850 · Instruye sobre la Ley Ricarte Soto (Ley 20.850)"
    assert out["normative_editorial"]["plain_language_title"] == out["editorial_committee"]["public_title"] == out["display_title"]
    # The decree's own number/year stays exactly as the official shortening wrote it.
    assert DECREE_ALIAS.startswith("Decreto exento 67/2026 · ")


def test_length_cap_keeps_a_fitting_title():
    title = "Decreto exento 9/2026 · Fija " + "x" * 50 + " de la ley N° 20.584"
    assert len(title) <= 110
    assert len(law_aliases.apply_alias(title)) > 110
    assert law_aliases.apply_to_title(title) == title
    assert len(law_aliases.apply_to_title(DECREE_SHORT)) <= 110


def test_minimal_normative_titles_use_the_alias_and_stay_reviewer_consistent():
    title = minimal_title("Circular IF/N°600", "Instruye sobre la red de prestadores de la ley N° 20.850.")
    assert title == "Circular IF/N°600 · Instruye sobre la red de prestadores de la Ley Ricarte Soto (Ley 20.850)"
    assert title.startswith("Circular IF/N°600 · ")
