from src.radar_salud.mercado_publico import raw_items_from_response, process_marketplace_item

CFG = {
    "slug": "mercado_publico",
    "name": "Mercado Público",
    "source_type": "official_api",
    "system_domain": "HEALTH",
    "base_confidence": 100,
    "default_category": "Oportunidades & Licitaciones",
}


def test_filters_health_tenders_and_keeps_transaction_category():
    payload = {"Listado": [
        {"CodigoExterno": "123-1-LR26", "Nombre": "Servicio integral de radioterapia oncológica", "Descripcion": "Prestaciones para pacientes", "NombreOrganismo": "Hospital Clínico X", "Estado": "Publicada", "FechaCierre": "2026-10-01"},
        {"CodigoExterno": "124-1-LE26", "Nombre": "Compra de resmas de papel", "Descripcion": "Papelería", "NombreOrganismo": "Municipalidad X", "Estado": "Publicada"},
    ]}
    items = raw_items_from_response(payload)
    assert len(items) == 1
    s = process_marketplace_item(items[0], CFG)
    assert s.category == "Oportunidades & Licitaciones"
    assert s.subcategory == "oncología"
    assert s.confidence_score >= 90
