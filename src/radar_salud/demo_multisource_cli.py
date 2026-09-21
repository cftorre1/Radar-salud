from __future__ import annotations

import argparse

from .models import Signal
from .multisource import merge_signals
from .personal_digest import build_personal_daily_digest
from .personalization import DEFAULT_PROFILES


def demo_signals():
    return [
        Signal(
            title="SUSESO publica circular con nuevas instrucciones",
            source_name="SUSESO", source_type="official", source_url="https://demo/suseso",
            category="Regulación & Legal", subcategory="Regulación", system_domain="OCCUPATIONAL_HEALTH",
            what_happened="Nueva circular", why_it_matters="Puede modificar obligaciones y procesos de mutualidades.",
            radar_score=80, confidence_score=100, regulatory_impact_score=95,
            watch_tags=["suseso", "circular", "mutualidades"],
        ),
        Signal(
            title="Superintendencia actualiza cartera de Isapres",
            source_name="Superintendencia de Salud", source_type="official", source_url="https://demo/isapre",
            category="Aseguramiento", subcategory="Estadísticas", system_domain="HEALTH_INSURANCE",
            what_happened="Nueva estadística", why_it_matters="Permite detectar cambios de cartera y movilidad del sistema.",
            radar_score=82, confidence_score=100, regulatory_impact_score=30,
            watch_tags=["isapres", "cartera"],
        ),
        Signal(
            title="Hospital licita servicios integrales de radioterapia",
            source_name="Mercado Público", source_type="official_api", source_url="https://demo/mp",
            category="Oportunidades & Licitaciones", subcategory="oncología", system_domain="HEALTH",
            what_happened="Nueva licitación", why_it_matters="Representa una oportunidad comercial en prestaciones oncológicas.",
            radar_score=77, confidence_score=100, regulatory_impact_score=20,
            watch_tags=["licitaciones", "oncología", "hospital"],
        ),
    ]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--profile", choices=sorted(DEFAULT_PROFILES), default="isapre")
    args = p.parse_args()
    signals = merge_signals([demo_signals()])
    print(build_personal_daily_digest(signals, DEFAULT_PROFILES[args.profile], "2026-09-21"))


if __name__ == "__main__":
    main()
