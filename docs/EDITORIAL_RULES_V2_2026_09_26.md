# Reglas editoriales y de selección v2

Fecha: 2026-09-26. Alcance: snapshot congelado de 90 días en `web/data/radar_today.json`; no autoriza producción ni modifica criterios fuera de esta especificación.

## Resultado de la auditoría

La matriz reproducible `data/editorial_audit_90d_2026_09_26.json` consolida 43/43 señales: las 14 ya revisadas y 29 señales históricas adicionales. Cada pieza se evaluó separadamente por existencia, prioridad, título, resumen, importancia, cifras, vigencia, atribución, riesgo de sobreinterpretación, relación con antecedentes y decisión que podría cambiar.

La simulación v2 es un **contrafactual manual** de los 43 juicios auditados: acepta 23 señales, degrada 11 a contexto, agrupa 8 publicaciones rutinarias y rechaza 1 anuncio sin consecuencia demostrada. No se presenta como ejecución automática de `evaluate_editorial_v2`, porque el snapshot histórico aún no contiene dimensiones v2 estructuradas. Tampoco equivale a borrar historia: `degrade` y `group` conservan trazabilidad y permiten análisis, pero evitan elevar rutina o evidencia incompleta como novedad ejecutiva.

## Taxonomía de valor de negocio

La configuración canónica está en `config/editorial_rules_v2.json`. Sus once categorías distinguen obligación regulatoria, impacto financiero, cartera/competencia, capacidad/oferta, operaciones/red, riesgo/fiscalización, inversión/M&A, innovación/tecnología, epidemiología/presión asistencial, workforce/capacidad y contexto sin acción.

El score pondera impacto financiero (20%), impacto operacional (15%), alcance (10%), magnitud (10%), horizonte (10%), accionabilidad (20%) y fortaleza de evidencia (15%). `accept` requiere 70; `degrade` parte en 45. Una pieza bajo 45 se rechaza y la rutina repetitiva bajo 70 se agrupa.

## Gates fail-closed

- Sin actor + acción + consecuencia, la pieza se rechaza; el motor no los infiere desde prosa persuasiva.
- Sin referencia que sostenga el impacto, la pieza se degrada aunque el score declarado sea alto.
- Una publicación oficial rutinaria se agrupa si no alcanza materialidad propia.
- Magnitudes, causalidad o efectos no demostrados se declaran como incertidumbre; no se completan editorialmente.
- Insight semanal requiere dos referencias declaradas con emisores distintos —o señal + indicador de origen independiente—, URL válida y una interpretación de negocio no obvia. La verificación factual sigue siendo responsabilidad del collector/revisor que suministra la estructura.
- Global Intelligence requiere dos referencias declaradas de emisores independientes con URL válida, separación explícita entre hechos internacionales e hipótesis Chile, y lectura estratégica accionable. El gate no confunde diversidad declarada con verificación factual.

## Reglas por tipo

| Tipo | Plantilla mínima |
|---|---|
| Normativa | Actor obligado + cambio exigible + fecha/plazo + consecuencia operativa o financiera |
| Legal | Decisión + alcance + estado procesal + efecto vigente, sin anticipar el fondo |
| Noticias | Actor + acción comprobada + magnitud disponible + decisión que puede cambiar |
| Datos | Indicador + período + variación comparable + límite causal + decisión de seguimiento |
| Fiscalización | Fiscalizador + conducta + sanción/magnitud + patrón, separando LIVE e histórico |
| Pieza especial | Evidencias independientes + síntesis no obvia + implicancia accionable + incertidumbre |

## Implementación revisable

`src/radar_salud/editorial_rules_v2.py` implementa decisiones configurables y `publication_ready` las aplica cuando el candidato contiene la clave `editorial_v2`; una estructura vacía, mal tipada o inválida se rechaza sin lanzar excepciones. Esta activación explícita evita reinterpretar retrospectivamente señales sin estructura v2. Las referencias declaradas deben ser objetos con `url` y `source`, y la independencia de piezas especiales se calcula por emisor, no por cantidad de strings. Los casos positivos y negativos de `tests/fixtures/editorial_rules_v2.json` cubren obligación regulatoria, anuncio ceremonial, publicación rutinaria, Insight monofuente, Global Intelligence multifuente y bypasses vacíos o mal formados.

La auditoría no entrena modelos externos ni depende de listas manuales de URL para decidir. Las URL solo identifican las 43 piezas del snapshot de evidencia; las reglas futuras operan sobre estructura, score y gates.
