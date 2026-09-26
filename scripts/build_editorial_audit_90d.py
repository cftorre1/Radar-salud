from __future__ import annotations

import json
import hashlib
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "web" / "data" / "radar_today.json"
OUTPUT = ROOT / "data" / "editorial_audit_90d_2026_09_26.json"
FROZEN_SNAPSHOT_SHA256 = "6a1f92e06f6d5a1aef6d5d179ecae1886b40bdc5be3e9a03df47eac61bdd2506"

# Deliberately human-reviewed decisions. The script joins them to the frozen
# snapshot; it does not infer value from URLs, source prestige or persuasive copy.
ASSESSMENTS = {
    0: ("accept", 72, "care_network_operations", "El piloto cambia dispensación y puede informar una decisión de escala, aunque su alcance sigue acotado."),
    1: ("degrade", 48, "context_without_action", "Una segunda sesión sin medidas, metas ni presupuesto no demuestra impacto operativo o financiero."),
    2: ("accept", 91, "regulatory_obligation", "Existe obligación, flujo, plazo y consecuencia operativa verificable para las isapres."),
    3: ("accept", 70, "capacity_supply", "La acreditación confirma capacidad habilitada con porcentajes y obligaciones registrales verificables."),
    4: ("accept", 86, "investment_ma", "US$15 millones, adquisición y nueva capacidad permiten evaluar competencia e inversión."),
    5: ("accept", 78, "portfolio_competition", "El convenio nacional cambia red efectiva, bonificación y fricción de acceso."),
    6: ("degrade", 51, "risk_enforcement", "El listado es útil para consulta, pero no informa cambio, universo ni variación que justifique elevarlo."),
    7: ("group", 62, "risk_enforcement", "Tres sanciones históricas forman un pulso; no deben presentarse como tres novedades LIVE."),
    8: ("degrade", 50, "care_network_operations", "La propuesta municipal carece de adopción sectorial y evidencia comparable más allá de un caso."),
    9: ("reject", 28, "context_without_action", "El anuncio no detalla medidas, cobertura, financiamiento ni plazo; no permite una decisión."),
    10: ("accept", 87, "financial_impact", "La prohibición de compensación cambia cuentas por pagar/cobrar y tiene efecto exigible."),
    11: ("accept", 84, "care_network_operations", "La regla exige un fallback de identificación, registros y protocolo fiscalizable."),
    12: ("accept", 72, "financial_impact", "La recuperación financiera afecta capital y posición competitiva, con atribución explícita al ejecutivo."),
    13: ("degrade", 54, "epidemiology_care_pressure", "Es un hito sanitario, pero no cambia por sí solo una decisión ejecutiva inmediata."),
    14: ("accept", 78, "regulatory_obligation", "La circular sigue vigente mientras se resuelve la jerarquía; cambia el calendario de control EMP."),
    15: ("accept", 88, "financial_impact", "El tratamiento contable del aporte y la revocación del mandato alteran plan, siniestralidad y permanencia."),
    16: ("degrade", 58, "portfolio_competition", "El punto de inflexión puede ser material, pero faltan cifra, base, causas y desglose por isapre."),
    17: ("accept", 84, "capacity_supply", "US$45 millones, alta complejidad y más de 1.000 empleos muestran magnitud regional verificable."),
    18: ("degrade", 53, "financial_impact", "La dirección del cambio es relevante, pero faltan resultados y base comparativa para dimensionarlo."),
    19: ("accept", 76, "care_network_operations", "Campos, formatos y frecuencia mensual exigen una adecuación concreta del reporte SIL."),
    20: ("accept", 86, "portfolio_competition", "El pulso combina cartera, cargas y movimientos con límites causales y una decisión de seguimiento explícita."),
    21: ("group", 60, "portfolio_competition", "Una actualización mensual de movilidad es insumo; debe consolidarse con cartera y flujos, no competir como señal aislada."),
    22: ("group", 58, "portfolio_competition", "Suscripciones y desahucios forman parte del mismo paquete mensual y requieren variación, no mera publicación."),
    23: ("group", 57, "portfolio_competition", "El corte regional es una dimensión del paquete de cartera; elevar el archivo duplica el hecho base."),
    24: ("group", 55, "portfolio_competition", "El archivo nacional duplica la actualización de cartera y debe alimentar un único pulso analítico."),
    25: ("accept", 80, "investment_ma", "Marcha blanca y aplazamiento de emisión conectan capacidad nueva con ejecución del financiamiento."),
    26: ("degrade", 59, "capacity_supply", "Hay expansión de oferta, pero faltan inversión, camas, cobertura y plazo para dimensionar materialidad."),
    27: ("accept", 74, "regulatory_obligation", "La negativa a suspender mantiene exigencias de afiliación electrónica vigentes durante la impugnación."),
    28: ("accept", 78, "capacity_supply", "$10 mil millones y apertura regional sustentan impacto de capacidad y competencia."),
    29: ("degrade", 47, "portfolio_competition", "La estrategia de masificación carece de producto, meta, cobertura, inversión y calendario."),
    30: ("accept", 74, "innovation_technology", "El ensayo y la reacción bursátil son materiales para competencia e inversión, sin convertir éxito clínico en aprobación."),
    31: ("accept", 79, "care_network_operations", "SAFED desplaza demanda ambulatoria con población, prestaciones, redes y condición de elegibilidad cuantificadas."),
    32: ("degrade", 46, "financial_impact", "El monto está documentado, pero no propósito, partes ni efecto en propiedad, control u operación."),
    33: ("group", 49, "context_without_action", "La publicación rutinaria de un boletín sin variación identificada es insumo de contexto, no señal."),
    34: ("accept", 82, "regulatory_obligation", "La circular cambia autenticación, trazabilidad, conservación y control de afiliación electrónica."),
    35: ("degrade", 55, "regulatory_obligation", "El cambio mueve el momento del informe, pero no altera metas; sirve como contexto de seguimiento."),
    36: ("accept", 77, "regulatory_obligation", "La suspensión modifica temporalmente el marco CAEC y debe distinguirse del resultado de fondo."),
    37: ("degrade", 52, "capacity_supply", "Existe proyecto de capacidad, pero faltan monto, tamaño, plazo y modelo asistencial."),
    38: ("group", 50, "care_network_operations", "El cambio de casilla y periodicidad es obligación administrativa menor; agrupar en cambios operativos."),
    39: ("accept", 89, "financial_impact", "La derivación CAEC oportuna determina cobertura y financiamiento de urgencias graves."),
    40: ("accept", 75, "epidemiology_care_pressure", "Las tasas GES por problema y seguro permiten dimensionar presión asistencial y financiera comparable."),
    41: ("group", 45, "context_without_action", "Actualizar una serie histórica sin hallazgo o variación es disponibilidad de fuente, no una señal."),
    42: ("accept", 83, "financial_impact", "Resultados, balance e indicadores oficiales permiten comparar sostenibilidad y presión de costos."),
}

DECISION_ACTION = {
    "regulatory_obligation": "adecuar cumplimiento, sistemas o plazos",
    "financial_impact": "revisar exposición, presupuesto, capital o resultado",
    "portfolio_competition": "ajustar estrategia comercial, red o seguimiento de cartera",
    "capacity_supply": "evaluar expansión, derivación o respuesta competitiva",
    "care_network_operations": "cambiar un flujo operativo o coordinación de red",
    "risk_enforcement": "priorizar control, mitigación o fiscalización",
    "investment_ma": "evaluar inversión, financiamiento o posición competitiva",
    "innovation_technology": "evaluar adopción, alianza o exposición tecnológica",
    "epidemiology_care_pressure": "anticipar demanda, capacidad o costo asistencial",
    "workforce_capacity": "anticipar brechas de dotación y productividad",
    "context_without_action": "ninguna todavía; conservar solo como contexto",
}


def _copy_review(signal: dict, decision: str) -> dict[str, str]:
    opaque_title = signal.get("signal_types") == ["Normativa"] and len(signal.get("title", "")) < 35
    return {
        "title": "rewrite_actor_action" if opaque_title else "specific_or_attributed",
        "what_happened": "keep_with_limits" if decision == "accept" else "state_missing_evidence",
        "why_it_matters": "decision_linked" if decision == "accept" else "context_only",
    }


def build() -> dict:
    raw_snapshot = SNAPSHOT.read_bytes()
    actual_sha = hashlib.sha256(raw_snapshot).hexdigest()
    if actual_sha != FROZEN_SNAPSHOT_SHA256:
        raise RuntimeError(
            f"Frozen snapshot changed: expected {FROZEN_SNAPSHOT_SHA256}, got {actual_sha}"
        )
    snapshot = json.loads(raw_snapshot)
    signals = snapshot["signals"]
    if len(signals) != 43 or set(ASSESSMENTS) != set(range(43)):
        raise RuntimeError("Frozen audit expects exactly the 43-signal snapshot")

    items = []
    for index, signal in enumerate(signals):
        decision, score, category, rationale = ASSESSMENTS[index]
        types = signal.get("signal_types") or ["Noticias"]
        has_figures = any(char.isdigit() for char in " ".join([
            signal.get("title", ""), signal.get("what_happened", ""), signal.get("why_it_matters", "")
        ]))
        items.append({
            "snapshot_index": index,
            "id": signal["source_url"],
            "event_date": signal.get("event_date"),
            "source": signal.get("source_name"),
            "type": types[0],
            "decision": decision,
            "signal_worthy": decision == "accept",
            "priority": "high" if score >= 80 else "medium" if score >= 60 else "low",
            "materiality_score": score,
            "value_category": category,
            "actor_action_consequence": "complete" if decision == "accept" else "partial_or_low_materiality",
            "copy_review": _copy_review(signal, decision),
            "key_figures": "present_or_not_required" if has_figures else "missing_or_not_material",
            "validity": "historical_snapshot_with_event_date",
            "attribution": "primary" if signal.get("source_name") != "Diario Financiero" else "secondary_attributed",
            "overinterpretation_risk": "low" if decision == "accept" else "high" if decision == "reject" else "medium",
            "relation_to_prior": "evaluate_with_same-category signals; do not claim causality",
            "decision_that_may_change": DECISION_ACTION[category],
            "business_review": rationale,
        })

    counts = Counter(item["decision"] for item in items)
    return {
        "audit_id": "editorial-90d-learning-rules-2026-09-26",
        "frozen_snapshot_sha256": FROZEN_SNAPSHOT_SHA256,
        "snapshot_generated_at": snapshot.get("generated_at"),
        "scope": {
            "previously_audited_signals": 14,
            "additional_signals_audited": 29,
            "consolidated_signals_audited": 43,
            "special_pieces": "governed separately; not counted among the 43 snapshot signals",
        },
        "method": {
            "lenses": ["content_design", "health_business", "reader_decision"],
            "principle": "Official or valid does not imply signal-worthy.",
            "reviewed_dimensions": [
                "existence", "priority", "title", "what_happened", "why_it_matters",
                "key_figures", "validity", "attribution", "overinterpretation",
                "relation_to_prior", "decision_that_may_change",
            ],
        },
        "simulation": {
            "mode": "manual_counterfactual_review",
            "before": {"elevated_as_individual_signals": 43},
            "after": dict(sorted(counts.items())),
            "explanation": "Contrafactual manual de los 43 juicios auditados, no una ejecución automática del motor. Accept conserva señales materiales; degrade las deja como contexto; group consolida rutina; reject retira piezas sin consecuencia demostrada.",
        },
        "items": items,
    }


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
