# Improvement Review — Signal Simplification + Statistics V2

**Fecha:** 2026-09-28  
**Candidato:** `348946bfb87cac8dd045fc4f4b0e1a6ea6691c6a`  
**Actions:** [run 36429461066](https://github.com/cftorre1/Radar-salud/actions/runs/36429461066)  
**Resultado:** PASS para staging; sin autorización de promoción.

## Evaluación

| Dimensión | Resultado | Evidencia |
|---|---|---|
| Coherencia estratégica | PASS | Las cuatro publicaciones estadísticas solicitadas permanecen visibles y el orden prioriza la conclusión tabular. |
| Claridad | PASS | Se identifican variable, período, unidad y alcance; stock y flujo no se presentan como métricas equivalentes. |
| Calidad editorial | PASS | Se omiten implicancias genéricas y bloques repetidos; las conclusiones se limitan a información respaldada. |
| Integridad de datos | PASS con límite registrado | Los parsers validan hoja, nombre de variable, unidad/tipo, agregados, escala y trazabilidad. Prestaciones con valor anómalo permanece excluida fail-closed. |
| Densidad informativa | PASS | Las tablas resumen llevan los valores comparables al primer nivel; metodología y trazas quedan disponibles en una sección opcional cerrada. |
| UX responsive | PASS | Playwright desktop/móvil valida que el detalle estadístico sea accesible y que la vista móvil no desborde horizontalmente. |
| Mantenibilidad | PASS | Reglas determinísticas y corpus de regresión cubren encabezados GES multinivel, semántica de series y selección de agregados. |
| Riesgo de regresión | PASS | 244 pruebas Python, 39 Node, 46 Playwright; Reviewer completo sin hallazgos; preview y smoke PASS. |

## Cambio observado

Antes, GES mostraba identificadores opacos, la serie anual aceptaba agregados por coincidencia textual y conservaba un valor de prestaciones sin unidad defendible; las financieras mezclaban lectura y muestra auditada; el Boletín IP cubría menos categorías. En tarjetas y detalle se repetían explicación, muestra validada e implicancias.

Ahora:

- GES usa nombres oficiales de patologías y una tabla con Fonasa, Isapre, total y participación de Isapre en los casos reportados de ambos subsistemas. Se explicita que la participación no equivale a prevalencia ni cuota poblacional.
- Series ISAPRE declara tipo y unidad por variable y muestra 2024, 2025 y variaciones; beneficiarios se reconcilia contra cotizantes y cargas. El agregado GES usa la hoja oficial `Casos Resumen` y exige el rótulo exacto Total, evitando falsos positivos de Subtotal.
- El dato de prestaciones `4.784.847.384.336` continúa excluido porque no se pudo sustentar semántica/escala con evidencia disponible.
- La tabla financiera identifica montos en CLP millones y define ingresos, resultado operacional y resultado neto; la referencia apunta a la estadística oficial IFRS de marzo de 2026.
- El Boletín IP presenta acreditación, mediación, reclamos y RNPI con etiquetas de stock/flujo y períodos.
- El detalle abre desde la tabla incluso sin insights narrativos; la metodología queda colapsada por defecto y no duplica el resumen para la persona usuaria.

## Recuperaciones y aprendizaje

Se resolvieron fallas independientes en encabezados GES multinivel, selección del agregado de beneficiarios, identidad de pestaña Casos GES, confusión Total/Subtotal y acceso al detalle desde la tabla. La última corrección agregó comprobación de ausencia de “Por qué importa” genérico y de overflow móvil. El re-run final cerró la firma `statistical_summary_table_hidden_from_detail` en intento 2/3.

El hallazgo que originó esta tarea pasó inadvertido porque el pipeline medía completitud estructural y trazabilidad, pero no el valor incremental de cada bloque ni la semántica real de la fila elegida por parsers heurísticos. Se agregó un Data/Statistics Reviewer determinístico y controles de unidad, tipo, denominador, magnitud, hoja y etiqueta de agregado. El incidente y su evidencia quedaron actualizados en `data/autopilot/learning_ledger.json`.

## Límites y backlog no bloqueante

El Reviewer determinístico comprueba contratos y consistencia estructural; no sustituye validación experta clínica, contable o jurídica de las publicaciones fuente. En particular, la tabla financiera usa filas oficiales versionadas en el pipeline y debe revalidarse al actualizar la publicación. El dato de prestaciones ambiguo queda excluido hasta que una fuente permita confirmar su escala. Estos límites no afectan el cumplimiento del alcance aprobado para staging, pero deben conservarse visibles en Pato.

**Conclusión:** Improvement Review PASS; no quedan observaciones materiales para el objetivo de staging. Producción permanece protegida por la regla global y por los gates condicionales de la tarea siguiente.
