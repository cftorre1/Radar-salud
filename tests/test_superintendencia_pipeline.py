from src.radar_salud.models import RawItem
from src.radar_salud.extraction import extract_superintendencia_detail
from src.radar_salud.validation import validate_official_item
from src.radar_salud.superintendencia_pipeline import process_superintendencia_detail

HTML = """
<html><body>
<h1>Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE – año 2026</h1>
<p>Contiene información descriptiva de la Cartera de Beneficiarios del Sistema ISAPRE, para cada mes del año 2026: Cotizantes y Cargas vigentes por Tramo de Edad y Sexo, Cotizantes vigentes por Tipo de Trabajador, así como las Suscripciones, Desahucios y Cotización Percibida por Isapre.</p>
<p>Información actualizada a julio 2026.</p>
<p>Fecha de publicación: 7 de septiembre de 2026</p>
<a href="/files/cartera_2026.xlsx">Descargar 3 MB XLSX</a>
</body></html>
"""

RAW = RawItem(
    source_slug="superintendencia_salud",
    title="Cartera Isapre",
    url="https://www.superdesalud.gob.cl/biblioteca-digital/cartera/",
    source_name="Superintendencia de Salud",
    source_type="official",
)

CFG = {
    "base_confidence": 98,
    "default_category": "Aseguramiento",
    "system_domain": "HEALTH_INSURANCE",
}


def test_detail_extractor_gets_core_evidence():
    enriched = extract_superintendencia_detail(RAW, HTML)
    assert enriched.event_date == "2026-09-07"
    assert enriched.metadata["updated_through"] == "julio 2026"
    assert len(enriched.metadata["attachments"]) == 1
    assert "Cartera de Beneficiarios" in enriched.raw_text


def test_official_validator_is_high_confidence():
    enriched = extract_superintendencia_detail(RAW, HTML)
    result = validate_official_item(enriched, 98)
    assert result.confidence_score >= 90
    assert result.status == "automatic"


def test_full_pipeline_builds_signal():
    signal = process_superintendencia_detail(RAW, HTML, CFG)
    assert signal.category == "Aseguramiento"
    assert signal.system_domain == "HEALTH_INSURANCE"
    assert signal.confidence_score >= 90
    assert signal.radar_score >= 60
    assert "isapres" in signal.watch_tags
    assert "cartera" in signal.watch_tags
    assert signal.validation_status == "automatic"
