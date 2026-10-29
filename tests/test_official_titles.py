import json
import re
import unicodedata
from pathlib import Path

import pytest

from radar_salud.official_titles import (
    ABBREVIATION_WORDS, ELLIPSIS, EXTENDED_MAX_CHARS, FORBIDDEN_END, MAX_CHARS,
    apply_short_title, numbers, operative_part, short_official_title,
)

HISTORY = Path(__file__).resolve().parents[1] / "data" / "history" / "superintendencia_signals.json"

# Real Diario Oficial titles (data/history/superintendencia_signals.json), index noise trimmed.
D45 = ("Decreto exento número 45, de 2026.- Aprueba prestadores de salud para otorgar las prestaciones sujetas "
       "al Sistema de Protección Financiera del que trata la ley N° 20.850")
D69 = ("Decreto exento número 69, de 2026.- Aprueba Norma Técnica Operativa N° 264 que establece los requisitos "
       "generales y específicos de las especialidades de la medicina y de la odontología que se indican, de acuerdo "
       "al artículo segundo del decreto N° 8, de 2013, de los Ministerios de Salud y de Educación, sobre certificación "
       "de las especialidades de los prestadores individuales de salud y de las entidades que las otorgan")
R17665 = ("Resolución exenta número CP 17.665, de 2026.- Actualiza Arsenal Farmacológico para establecimientos de "
          "Atención Primaria pertenecientes a la jurisdicción del Servicio de Salud Viña del Mar - Quillota - Petorca "
          "2026-2028")
R732 = ("Resolución exenta número 732, de 2026.- Fija metas sanitarias y de mejoramiento de la atención para las "
        "entidades administradoras de salud municipal para el año 2027")
SUBROGANCIA = {
    46: ("Decreto exento número 46, de 2026.- Pone término y establece nuevo orden de subrogancia en el cargo de "
         "Subsecretaria/o de Salud Pública", "Subsecretaria/o de Salud Pública"),
    47: ("Decreto exento número 47, de 2026.- Pone término y establece nuevo orden de subrogancia al cargo de "
         "Secretario/a Regional Ministerial de Salud de la Región de Coquimbo", "Región de Coquimbo"),
    51: ("Decreto exento número 51, de 2026.- Pone término y establece nuevo orden de subrogancia al cargo de "
         "Director/a del Fondo Nacional de Salud", "Fondo Nacional de Salud"),
    56: ("Decreto exento número 56, de 2026.- Pone término y establece nuevo orden de subrogancia al cargo de "
         "Director/a del Servicio de Salud Viña del Mar-Quillota-Petorca", "Servicio de Salud Viña del Mar-Quillota-Petorca"),
    61: ("Decreto exento número 61, de 2026.- Pone término y establece nuevo orden de subrogancia al cargo de "
         "Director/a del Servicio de Salud Metropolitano Sur", "Servicio de Salud Metropolitano Sur"),
}
D65 = ("Decreto exento número 65, de 2026.- Modifica decreto N° 4 exento, de 2026, que dispone vacunación obligatoria "
       "contra influenza para el año 2026 a grupo de población que indica")
D50 = ("Decreto exento número 50, de 2026.- Modifica decreto Nº 59 exento, de 2024, que constituye nueva Comisión de "
       "Enfermedades Raras, Huérfanas o Poco Frecuentes Ver PDF (CVE-2848208) Subsecretaría de Redes Asistenciales "
       "Decreto número 17, de 2026.- Regulariza renovación <a target=\"")
D58 = ("Subsecretaría de Salud Pública Decreto número 58, de 2026.- Modifica decreto Nº 28, de 2023, que decreta "
       "alerta sanitaria por período que señala y otorga facultades extraordinarias que indica por enfermedades "
       "vectoriales y zoonóticas emergentes que señala Ver PDF (CVE-2838436)")
R895 = ("Subsecretaría de Salud Pública Resolución exenta número 895, de 2026.- Modifica resolución N° 403 exenta, de "
        "2013, que aprueba Norma General Técnica N° 151 sobre Estándares de Acreditación de los Comités Ético "
        "Científicos Ver PDF (CVE-2858369)")
R846 = ("Ver PDF (CVE-2868756) MINISTERIO DE SALUD Secretaría Regional Ministerial Región de Aysén del General Carlos "
        "Ibáñez del Campo Resolución exenta número 846, de 2026.- Dispone medidas sanitarias extraordinarias para "
        "prevenir la propagación de virus respiratorios en la Región de Aysén <a target=\"_blank\"")
D3 = ("Subsecretaría de Redes Asistenciales Decreto número 3, de 2025.- Renueva designación de doña Susan Porras "
      "Fernández en el cargo de Directora del Servicio de Salud Aconcagua Ver PDF (CVE-2855172)")
D22 = ("Decreto número 22, de 2026.- Acepta renuncia no voluntaria de don Francisco de Paula Grisolia Cirera al cargo "
       "de Director del Servicio de Salud Antofagasta Ver PDF (CVE-2855168)")
R5188 = ("Resolución exenta número E 5.188, de 2026.- Modifica folletos de información al profesional y al paciente, "
         "en la forma que se indica, para los productos farmacéuticos que contienen metamizol en su composición")


def _words(text):
    norm = unicodedata.normalize("NFC", text.lower()).replace("nº", "n°")
    return set(re.findall(r"n°|[a-záéíóúüñ]+", norm))


def _last_word(text):
    words = re.findall(r"[\wáéíóúüñÁÉÍÓÚÜÑ°º/]+", text.rstrip(ELLIPSIS + " ,;:").lower())
    return words[-1] if words else ""


def _history_titles():
    data = json.loads(HISTORY.read_text(encoding="utf-8"))
    items = next(iter(data.values())) if isinstance(data, dict) else data
    titles = []
    for s in items:
        if s.get("source_name") != "Diario Oficial":
            continue
        t = s.get("source_title_full") or s.get("title")
        if short_official_title(t):
            titles.append(t)
    return titles


HISTORY_TITLES = _history_titles()


def _assert_faithful(title, short):
    body = operative_part(title)
    # (a) every ID, number and year of the operative part survives (with multiplicity)
    assert not (numbers(body) - numbers(short)), (short, numbers(body) - numbers(short))
    # (b) no invented words
    assert _words(short) <= _words(title) | ABBREVIATION_WORDS, _words(short) - _words(title)
    # (c) never ends on a verb, article, preposition, conjunction or "de"
    assert _last_word(short) not in FORBIDDEN_END, short
    for boiler in ("Ver PDF", "<a", "CVE-"):
        assert boiler not in short
    # length: 110 target, 140 extended, otherwise the full operative title uncut
    assert len(short) <= EXTENDED_MAX_CHARS or (short.endswith(body) and ELLIPSIS not in short)


def test_history_has_all_diario_oficial_act_titles():
    assert len(HISTORY_TITLES) == 47


@pytest.mark.parametrize("title", HISTORY_TITLES, ids=range(len(HISTORY_TITLES)))
def test_every_history_title_is_faithful(title):
    _assert_faithful(title, short_official_title(title))


# 1. IDs, law numbers and year ranges are never dropped.
def test_keeps_law_number_45():
    s = short_official_title(D45)
    assert "ley N° 20.850" in s and len(s) <= MAX_CHARS
    assert s == "Decreto exento 45/2026 · Aprueba prestadores de salud del Sistema de Protección Financiera de la ley N° 20.850"


def test_keeps_cited_decree_69_and_does_not_delete_tail_by_rule():
    s = short_official_title(D69)
    assert "decreto N° 8/2013" in s and "N° 264" in s and len(s) <= EXTENDED_MAX_CHARS
    assert s.endswith(ELLIPSIS)  # trailing "sobre certificación…" is cut by fitting, not erased by a rule
    assert "Ministerios" not in s


def test_keeps_year_range_17665():
    s = short_official_title(R17665)
    assert "2026-2028" in s and "Viña del Mar" in s and "Petorca" in s


def test_keeps_year_732():
    s = short_official_title(R732)
    assert "año 2027" in s and len(s) <= EXTENDED_MAX_CHARS
    assert s == ("Res. exenta 732/2026 · Fija metas sanitarias y de mejoramiento de la atención de salud municipal "
                 "para el año 2027")


# 2. "Pone término y establece nuevo orden de subrogancia" keeps the operative clause.
@pytest.mark.parametrize("number", sorted(SUBROGANCIA))
def test_subrogancia_not_reduced_to_pone_termino(number):
    title, target = SUBROGANCIA[number]
    s = short_official_title(title)
    assert "subrogancia" in s and target in s, s
    assert not s.rstrip(ELLIPSIS).endswith("Pone término")
    assert ELLIPSIS not in s and len(s) <= EXTENDED_MAX_CHARS


# 3. "Modifica X" keeps X's topic; no split at " que " right after a cited act ID.
@pytest.mark.parametrize("title,ids,topic", [
    (D65, ["decreto exento N° 4/2026", "año 2026"], "vacunación obligatoria contra influenza"),
    (D50, ["decreto exento N° 59/2024"], "Comisión de Enfermedades Raras"),
    (D58, ["decreto N° 28/2023"], "zoonóticas"),
    (R895, ["N° 403/2013", "N° 151"], "Comités Ético Científicos"),
    (R846, [], "virus respiratorios en la Región de Aysén"),
])
def test_modifica_keeps_topic(title, ids, topic):
    s = short_official_title(title)
    assert topic in s, s
    for i in ids:
        assert i in s, (i, s)
    assert len(s) <= EXTENDED_MAX_CHARS
    assert not re.search(r"N° [\d\.]+/\d{4}" + re.escape(ELLIPSIS), s)  # not cut right after the ID


# 4. No mid-phrase cuts; the health service is kept.
@pytest.mark.parametrize("title,service", [
    (D3, "Servicio de Salud Aconcagua"),
    (D22, "Servicio de Salud Antofagasta"),
    (SUBROGANCIA[61][0], "Servicio de Salud Metropolitano Sur"),
])
def test_no_mid_phrase_cut_and_service_kept(title, service):
    s = short_official_title(title)
    assert service in s, s
    assert _last_word(s) not in FORBIDDEN_END


@pytest.mark.parametrize("bad", ["… al cargo de", "… de", "… la", "… para", "… y", "… establece", "… que"])
def test_forbidden_endings_are_listed(bad):
    assert _last_word(bad) in FORBIDDEN_END


def test_examples_expected_shape():
    assert short_official_title(R5188) == (
        "Res. exenta E 5.188/2026 · Modifica folletos de información de productos con metamizol")


def test_non_acts_and_fragments_untouched():
    assert short_official_title("Ley de los 60 minutos: los desafíos") is None
    assert short_official_title("decreto N° 30 de 2025, que determina aporte estatal <a target=") is None
    assert short_official_title("Decreto exento número 227, de 2026") is None


# 5. Curated display titles are never overwritten, whatever their length.
def test_apply_sets_short_title_when_no_curated_title():
    r = apply_short_title({"source_name": "Diario Oficial", "title": R5188})
    assert r["title"] == R5188 and r["source_title_full"] == R5188
    assert r["display_title"] == r["short_title"] == short_official_title(R5188)
    same = apply_short_title({"source_name": "Diario Oficial", "title": R5188, "display_title": R5188})
    assert same["short_title"] == short_official_title(R5188)


@pytest.mark.parametrize("curated", ["Folletos de metamizol", "x" * 300])
def test_apply_never_overwrites_curated_title(curated):
    rec = {"source_name": "Diario Oficial", "title": R5188, "display_title": curated}
    out = apply_short_title(rec)
    assert out["display_title"] == curated
    assert "short_title" not in out
    assert out == rec


def test_apply_ignores_non_acts():
    rec = {"source_name": "SUSESO", "title": "Circular 3926"}
    assert apply_short_title(rec) == rec
