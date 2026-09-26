# Portal Admin — diagnóstico experto y arquitectura

Fecha: 2026-09-26. Estado: diagnóstico solamente. No se rediseñó ni implementó el portal y la tarea propia de Admin conserva su dependencia bloqueada.

## Diagnóstico

El control operativo está distribuido entre cola/PMO, resultados de GitHub Actions, salud de fuentes y artefactos editoriales. La principal brecha no es estética: falta una vista única que separe hechos observados, valores no disponibles y decisiones pendientes. Presentar ceros donde no existe telemetría sería engañoso.

## Arquitectura propuesta

1. **Capa de evidencias**: adaptadores de solo lectura para commits/CI, cola/PMO, salud de fuentes, auditoría editorial y proveedores autorizados.
2. **Contrato de scorecard**: dimensiones y reglas fail-closed en `config/admin_scorecard_v1.json`.
3. **Vista operativa**: resumen por dimensión, freshness, enlace al artefacto fuente y estado `available/stale/not_available`.
4. **Acciones**: fuera de alcance hasta definir autorización, roles, trazabilidad y rollback. La primera versión debe ser observacional.

## Scorecard recomendado

| Dimensión | Decisión soportada | Evidencia mínima | Estado actual |
|---|---|---|---|
| Desarrollo | liberar o corregir | SHA, suite, workflow | disponible |
| Operación | recuperar una fuente | source health, run, incidente | parcialmente disponible |
| Valor editorial | conservar/degradar/agrupar/rechazar | audit + gate + Reviewer | disponible |
| Uso beta | priorizar producto | analytics aprobada | no disponible |
| Conversión | newsletter vs acceso anticipado | consentimiento + proveedor | no disponible |
| Costos / FinOps | controlar costo unitario | export de facturación autorizado | no disponible |

## Backlog priorizado

- P0: ensamblar un read-model de desarrollo, operación y valor editorial con timestamp y deep-link a evidencia.
- P0: validar esquema, freshness y representación de `not_available`; prohibir ceros inferidos.
- P1: añadir detalle de fallos/reintentos y trazabilidad de cada señal publicada.
- P1: diseñar conectores opcionales para uso beta, conversión y FinOps, desactivados hasta autorización.
- P2: evaluar acciones operativas con RBAC y auditoría; no incluirlas en el primer corte.

## Límites

No se habilitaron analytics, auth, pagos, pricing, privacidad, facturación ni secretos. Esta auditoría no desbloquea la tarea separada `admin_portal_expert_audit_2026_09_26`, cuya dependencia externa debe resolverse de forma independiente.
