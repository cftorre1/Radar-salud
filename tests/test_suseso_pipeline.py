from src.radar_salud.models import RawItem
from src.radar_salud.scouts import SusesoScout
from src.radar_salud.suseso_pipeline import extract_suseso_detail, process_suseso_detail

LISTING = """
<html><body>
<a href="https://www.suseso.cl/609/w3-article-768587.html">Circular N° 3900 - Plan anual de prevención 2026</a>
<a href="https://sisesat.suseso.cl/login">SISESAT</a>
<a href="https://www.suseso.cl/607/articles-765116_archivo_01.pdf">Gestión Financiera Económica Mutualidades</a>
</body></html>
"""

DETAIL = """
<html><body>
<h1>Circular N° 3900 - Plan anual de prevención 2026</h1>
<p>Fecha de publicación: 30 de enero de 2026</p>
<p>Imparte instrucciones a las Mutualidades de Empleadores e Instituto de Seguridad Laboral sobre metas y reportes del Plan Anual de Prevención 2026.</p>
<p>Incluye seguimiento semestral y reportes trimestrales para sectores priorizados.</p>
<a href="/609/articles-768587_archivo_01.pdf">Descargar Circular PDF</a>
</body></html>
"""

CFG = {
    "base_confidence": 100,
    "default_category": "Salud Laboral & Seguridad Social",
    "system_domain": "OCCUPATIONAL_HEALTH",
    "force_category": True,
}


def test_suseso_scout_ignores_restricted_systems():
    items = SusesoScout().discover_from_html(LISTING)
    assert len(items) == 2
    assert all("login" not in x.url for x in items)
    assert all(x.source_slug == "suseso" for x in items)


def test_suseso_extractor_gets_date_and_attachment():
    raw = RawItem("suseso", "Circular", "https://www.suseso.cl/609/w3-article-768587.html", "SUSESO", "official")
    enriched = extract_suseso_detail(raw, DETAIL)
    assert enriched.event_date == "2026-01-30"
    assert len(enriched.metadata["attachments"]) == 1
    assert "Mutualidades" in enriched.raw_text


def test_suseso_pipeline_builds_regulatory_signal():
    raw = RawItem("suseso", "Circular", "https://www.suseso.cl/609/w3-article-768587.html", "SUSESO", "official")
    signal = process_suseso_detail(raw, DETAIL, CFG)
    assert signal.category == "Salud Laboral & Seguridad Social"
    assert signal.subcategory == "Regulación"
    assert signal.system_domain == "OCCUPATIONAL_HEALTH"
    assert signal.confidence_score >= 90
    assert "mutualidades" in signal.watch_tags
    assert "regulación" in signal.watch_tags
    assert signal.radar_score >= 70
