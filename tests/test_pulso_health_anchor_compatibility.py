"""Preserve the existing DF clinical-investment admission contract."""
import pytest

from radar_salud.df_media_gate import material
from radar_salud.pulso_source import health_anchor


@pytest.mark.parametrize("name", ["Cesfam", "CESFAM", "cesfam"])
def test_named_primary_care_investment_reaches_existing_media_gate(name):
    # Existing staging DF regression: a specific clinical investment in Iquique.
    title = f"Iquique vuelve a licitar su quinto {name} con más del doble de inversión"
    assert health_anchor(title)
    assert material(title, "")


@pytest.mark.parametrize("word", ["precesfam", "cesfamiliar", "cesfam2"])
def test_clinical_acronym_requires_whole_word(word):
    assert not health_anchor(f"Aumenta la inversión en {word}")


def test_incidental_clinical_mention_does_not_admit_macro_investment():
    assert not material("Aumenta la inversión minera", "El Cesfam local presta atención.")
    assert not health_anchor("Banco aumenta capital para inversión inmobiliaria")
