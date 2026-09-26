"""Validate and expose MINSAL respiratory pressure evidence without causal overclaim."""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlparse


def _pct(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not -100 <= value <= 100:
        raise ValueError("invalid percentage")
    return float(value)


def _count(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("invalid count")
    return value


def _change_phrase(label: str, value: float) -> str:
    if value < 0:
        return f"{label} disminuyeron {abs(value):.1f}%"
    if value > 0:
        return f"{label} aumentaron {value:.1f}%"
    return f"{label} no variaron"


def _level_direction(current: float, previous: float) -> str:
    if current < previous:
        return "bajó"
    if current > previous:
        return "subió"
    return "se mantuvo"


def build_respiratory_pressure(dataset: dict[str, Any], today: date | None = None) -> dict[str, Any] | None:
    """Return a provider-ready signal only when the complete official record reconciles."""
    try:
        today = today or date.today()
        source = dataset["source"]
        parsed = urlparse(source["url"])
        if (dataset["status"] != "validated_provider_ready"
                or parsed.scheme != "https" or parsed.netloc != "www.minsal.cl"
                or not parsed.path.endswith(".pdf")
                or source["publisher"] != "Ministerio de Salud de Chile"
                or source["material_type"] != "official_weekly_report"
                or source["integrates_isp_surveillance"] is not True):
            raise ValueError("unsupported source")
        report_day = date.fromisoformat(dataset["report_date"])
        start = date.fromisoformat(dataset["period_start"])
        end = date.fromisoformat(dataset["period_end"])
        week = dataset["epidemiological_week"]
        if report_day > today or not 1 <= week <= 53 or not start <= end < report_day:
            raise ValueError("invalid period")
        virus = dataset["virus_surveillance"]
        care = dataset["care_pressure"]
        positivity = _pct(virus["positivity_pct"])
        previous_positivity = _pct(virus["previous_positivity_pct"])
        shares = {key: _pct(value) for key, value in virus["distribution_pct"].items()}
        required_viruses = {"rhinovirus", "respiratory_syncytial_virus", "metapneumovirus"}
        if set(shares) != required_viruses or any(value < 0 for value in shares.values()):
            raise ValueError("incomplete virus distribution")
        emergency = _pct(care["respiratory_emergency_share_pct"])
        previous_emergency = _pct(care["previous_respiratory_emergency_share_pct"])
        emergency_change = _pct(care["lower_respiratory_emergency_visits_weekly_change_pct"])
        hospital_change = _pct(care["respiratory_hospitalizations_weekly_change_pct"])
        pediatric_beds = _count(care["pediatric_critical_beds"])
        adult_beds = _count(care["adult_critical_beds"])
        pediatric_occupancy = _pct(care["pediatric_critical_bed_occupancy_pct"])
        adult_occupancy = _pct(care["adult_critical_bed_occupancy_pct"])
        pediatric_respiratory = _pct(care["pediatric_respiratory_share_pct"])
        adult_respiratory = _pct(care["adult_respiratory_share_pct"])
        risk_notes = dataset["risk_notes"]
        if not isinstance(risk_notes, list) or len(risk_notes) < 2 or not all(isinstance(x, str) and x for x in risk_notes):
            raise ValueError("missing risk disclosure")
        emergency_direction = "baja" if emergency < previous_emergency else "sube" if emergency > previous_emergency else "se mantiene"
        return {
            "title": f"Urgencias respiratorias {emergency_direction}, con ocupación crítica adulta en {adult_occupancy:.1f}%",
            "source_name": "Ministerio de Salud",
            "source_type": "official",
            "source_url": source["url"],
            "event_date": report_day.isoformat(),
            "publication_date": report_day.isoformat(),
            "data_period": f"SE {week} · {start.isoformat()} a {end.isoformat()}",
            "signal_types": ["Datos"],
            "scopes": ["Salud pública", "Prestadores"],
            "ingestion_mode": "BACKFILL",
            "category": "Epidemiología y presión asistencial",
            "event_type": "DATA_PULSE",
            "distribution": "provider_ready_not_promoted",
            "radar_score": 78,
            "confidence_score": 100,
            "what_happened": (
                f"En SE {week}, la positividad respiratoria {_level_direction(positivity, previous_positivity)} de {previous_positivity:.1f}% a {positivity:.1f}% "
                f"y la proporción de urgencias respiratorias de {previous_emergency:.1f}% a {emergency:.1f}%."
            ),
            "why_it_matters": (
                f"{_change_phrase('Las consultas de urgencia respiratoria baja', emergency_change)} y "
                f"{_change_phrase('las hospitalizaciones respiratorias', hospital_change)} en la comparación semanal; "
                f"la ocupación de camas críticas fue "
                f"{pediatric_occupancy:.1f}% en pediatría y {adult_occupancy:.1f}% en adultos. La señal orienta capacidad y "
                "demanda; no atribuye causalidad entre circulación viral y uso de camas."
            ),
            "key_points": [
                f"Circulación: rinovirus {shares['rhinovirus']:.1f}%, VRS {shares['respiratory_syncytial_virus']:.1f}% y metapneumovirus {shares['metapneumovirus']:.1f}%.",
                f"Pediatría: {pediatric_beds} camas críticas, {pediatric_occupancy:.1f}% ocupadas y {pediatric_respiratory:.1f}% de ocupación respiratoria.",
                f"Adultos: {adult_beds} camas críticas, {adult_occupancy:.1f}% ocupadas y {adult_respiratory:.1f}% de ocupación respiratoria."
            ],
            "risk_notes": risk_notes,
            "editorial_v2": {
                "actor": "Ministerio de Salud de Chile",
                "action": "publica vigilancia respiratoria y presión asistencial de la semana epidemiológica",
                "consequence": "permite anticipar demanda y revisar capacidad sin atribuir causalidad",
                "value_category": "epidemiology_care_pressure",
                "materiality": {
                    "financial_impact": 40,
                    "operational_impact": 90,
                    "affected_scope": 85,
                    "magnitude": 75,
                    "time_horizon": 75,
                    "actionability": 80,
                    "evidence_strength": 90
                },
                "evidence_refs": [{"url": source["url"], "source": "Ministerio de Salud de Chile"}],
                "factuality": "official_report_with_disclosed_internal_inconsistency"
            }
        }
    except (KeyError, TypeError, ValueError):
        return None
