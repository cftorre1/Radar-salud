import re
import unicodedata

import pytest

from radar_salud.official_titles import ABBREVIATION_WORDS, MAX_CHARS, apply_short_title, short_official_title

EX1 = ("Decreto exento número 69, de 2026.- Aprueba Norma Técnica Operativa N° 264 que establece los requisitos "
       "generales y específicos de las especialidades de la medicina y de la odontología que se indican, de acuerdo "
       "al artículo segundo del decreto N° 8, de 2013, de los Ministerios de Salud y de Educación, sobre certificación "
       "de las especialidades de los prestadores individuales de salud y de las entidades que las otorgan")
EX2 = ("Resolución exenta número E 5.188, de 2026.- Modifica folletos de información al profesional y al paciente, "
       "en la forma que se indica, para los productos farmacéuticos que contienen metamizol en su composición")

# Real Diario Oficial titles from data/history/superintendencia_signals.json
REAL = [
    "Decreto exento número 65, de 2026.- Modifica decreto N° 4 exento, de 2026, que dispone vacunación obligatoria contra influenza para el año 2026 a grupo de población que indica",
    "Resolución exenta número E 5.187, de 2026.- Modifica folletos de información al profesional y al paciente, en la forma que se indica, para los productos farmacéuticos que contienen tramadol en su composición, en cualquiera de sus presentaciones",
    "Extracto de resolución exenta número 4.794, de 2026.- Aprueba Guía técnica de metrología: Directrices para el buen uso de balanzas de laboratorio",
    "Extracto de resolución exenta número 3.955, de 2026.- Requiere envío digitalizado de folletos de información que indica",
    "Decreto exento número 50, de 2026.- Modifica decreto Nº 59 exento, de 2024, que constituye nueva Comisión de Enfermedades Raras, Huérfanas o Poco Frecuentes Ver PDF (CVE-2848208) Subsecretaría de Redes Asistenciales Decreto número 17, de 2026.- Regulariza renovación <a target=\"",
    "Subsecretaría de Salud Pública Resolución exenta número 895, de 2026.- Modifica resolución N° 403 exenta, de 2013, que aprueba Norma General Técnica N° 151 sobre Estándares de Acreditación de los Comités Ético Científicos Ver PDF (CVE-2858369)",
    "Resolución exenta número CP 20.192, de 2026.- Declara zona de riesgo sanitario la comuna de Renaico Ver PDF (CVE-2862808) Instituto de Salud Pública",
    "Decreto número 29, de 2026.- Modifica decreto N° 30 de 2025, que determina aporte estatal a municipalidades que indica, para sus entidades administradoras de salud municipal Ver PDF (CVE-2879589)",
]


def _words(text):
    norm = unicodedata.normalize("NFC", text.lower())
    return set(re.findall(r"n°|[a-záéíóúüñ]+", norm.replace("nº", "n°")))


def _numbers(text):
    return set(re.findall(r"\d[\d\.]*\d|\d", text))


def test_examples_expected_shape():
    assert short_official_title(EX1) == (
        "Decreto exento 69/2026 · Aprueba Norma Técnica N° 264: requisitos de especialidades médicas y odontológicas")
    assert short_official_title(EX2) == (
        "Res. exenta E 5.188/2026 · Modifica folletos de información de productos con metamizol")


@pytest.mark.parametrize("title", [EX1, EX2, *REAL])
def test_short_title_is_faithful(title):
    short = short_official_title(title)
    assert short and len(short) <= MAX_CHARS
    assert _numbers(short) <= _numbers(title), _numbers(short) - _numbers(title)
    assert _words(short) <= _words(title) | ABBREVIATION_WORDS, _words(short) - _words(title)
    for boiler in ("de acuerdo", "en la forma que", "que se indica", "Ministerios", "Ver PDF", "<a"):
        assert boiler not in short


def test_normative_ids_kept():
    assert "N° 264" in short_official_title(EX1)
    assert "N° 403/2013" in short_official_title(REAL[5])
    assert "tramadol" in short_official_title(REAL[1])


def test_non_acts_and_fragments_untouched():
    assert short_official_title("Ley de los 60 minutos: los desafíos") is None
    assert short_official_title("decreto N° 30 de 2025, que determina aporte estatal <a target=") is None
    assert short_official_title("Decreto exento número 227, de 2026") is None


def test_apply_keeps_full_title_and_curated_titles():
    r = apply_short_title({"source_name": "Diario Oficial", "title": EX2})
    assert r["title"] == EX2 and r["source_title_full"] == EX2
    assert r["display_title"].startswith("Res. exenta E 5.188/2026")
    curated = {"source_name": "Diario Oficial", "title": EX2, "display_title": "Folletos de metamizol"}
    assert apply_short_title(curated)["display_title"] == "Folletos de metamizol"
    assert apply_short_title({"source_name": "SUSESO", "title": "Circular 3926"})["title"] == "Circular 3926"
