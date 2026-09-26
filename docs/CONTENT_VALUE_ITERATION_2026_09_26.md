# Iteración de valor editorial, epidemiología y Admin

Fecha: 2026-09-26. Rama: `staging`. No incluye producción.

## Copy P0/P1 y consistencia

`config/editorial_copy_overrides_v1.json` materializa los 11 cambios con propuesta no vacía de la auditoría experta. `src/radar_salud/editorial_copy.py` los aplica por URL antes de escribir la snapshot; el mismo objeto alimenta “Ponte al día”, la tarjeta y el detalle. El test de interfaz compara el copy auditado con lo que realmente renderiza Home.

La auditoría extendida `data/editorial_audit_90d_2026_09_26.json` cubre las 43 señales del snapshot y está ligada al SHA-256 `6a1f92e06f6d5a1aef6d5d179ecae1886b40bdc5be3e9a03df47eac61bdd2506`. La nota inicial de 29 señales fuera de alcance queda formalmente superada.

El preflight del experimento de modelos referencia esta misma huella para no perder integridad después del cambio de copy. Su estado sigue `preflight_ready_no_calls`: no se ejecutaron Luna, Terra ni Astra, no se generaron outputs y no se autorizó gasto.

## Insight semanal: oculto por umbral no cumplido

Se evaluaron cartera, cotizantes, cargas, suscripciones/desahucios y movilidad. Aunque son varias series y workbooks, comparten un único origen editorial e institucional —Superintendencia de Salud—. No constituyen dos señales independientes ni una señal más un indicador de origen independiente. Insight semanal permanece `null`; no se fuerza frecuencia ni se presenta el Pulso Isapre como insight.

## Global Intelligence: segunda lectura de valor

- **Qué cambió:** la OMS proyecta un déficit mundial de 11,1 millones de trabajadores de salud a 2030.
- **Por qué importa:** capacidad, continuidad, productividad clínica y dependencia de personal formado en otros países.
- **Qué vigilar:** capacidad, rotación y jubilación, sin convertir la proyección global en diagnóstico local.
- **Hipótesis Chile:** vacantes críticas, espera, rotación, costos laborales y reconocimiento de títulos; estado `not_established`.

El teaser usa ahora el hallazgo global verificado en vez de una frase genérica de importancia. Mantiene Reuters y WHO separados y etiqueta Chile como hipótesis.

## Pulso Excel: guardas ejecutivas preservadas

La lectura aprobada conserva 26.541 beneficiarios menos entre enero y julio, seis bajas mensuales y la contribución aritmética de cargas. Stock de cartera, eventos mensuales de contratos/desahucios y movilidad entre cortes siguen separados. No se infiere causa, ingreso perdido ni adquisición neta.

## Epidemiología y presión asistencial

La fuente oficial es el reporte MINSAL del 24 de septiembre de 2026 para SE37 (13–19 septiembre), que integra vigilancia de virus respiratorios ISP y presión asistencial. El paquete valida fecha, semana, origen, circulación, urgencias, hospitalizaciones y capacidad; falla cerrado ante datos futuros, host no oficial, tipo inválido o riesgo omitido.

La señal queda `provider_ready_not_promoted` en `web/data/epidemiology.json`: está técnicamente y editorialmente construida, pero no se inserta silenciosamente en Home durante esta tarea. La inconsistencia interna del PDF sobre positividad se conserva como riesgo; se usa 53,7% del resumen ejecutivo frente a 56,7% previo. ISP/ANAMED 502 no bloquea este frente porque no es su fuente.

## Admin

`docs/ADMIN_PORTAL_EXPERT_AUDIT_2026_09_26.md` y `config/admin_scorecard_v1.json` entregan diagnóstico, arquitectura, scorecard y backlog. No rediseñan el portal ni inventan métricas: uso beta, conversión y FinOps permanecen `not_available` hasta contar con proveedor, consentimiento y acceso autorizados.
