# Diario Financiero · evidencia y continuidad

Codex A, rama `codex/df-end-to-end-20261011`, basada en staging y actualizada con `fe3a4f779f43edfdea8edc9df2f2641dd96056c2`. [PR #11](https://github.com/cftorre1/Radar-salud/pull/11) borrador. [Issue #5](https://github.com/cftorre1/Radar-salud/issues/5) permanece abierta. Main, producción y staging no se escribieron.

## Resultado verificado

Baseline:214 capturas,181 URLs,33 duplicados por cambio de titular/bajada. Todas sin fecha;170 rechazos genéricos y44 pending BACKFILL. La reparación previa no rehidrataba fingerprints existentes y el parser no reconocía el publisher real. Además, la captura de párrafos/recomendaciones hizo que IA evaluara otro artículo.

Se repararon por separado: fecha cXense/JSON-LD y etiqueta principal Publicado; identidad `mainEntityOfPage`; calendario Chile para LIVE; cuerpo CUERPO y tarjetas principales de discovery; recuperación por URL/seen sin borrar capturas o intentos; mínimo72 aprobado y consecuencia sanitaria material; motivos editoriales/técnicos; retirada y reevaluación de decisiones contaminadas; dedupe de history retenido pero retirado. Un score72 no puede anular una evaluación explícita de contexto secundario sin señal material.

[Runtime real38114333430](https://github.com/cftorre1/Radar-salud/actions/runs/38114333430): listados nuevos05:18Z,24 candidatos principales;427 originales capturados,19 evaluaciones Fast exitosas. San Carlos10-oct LIVE82; Ricarte8-oct LIVE82; EmpresasSB/Yarur10-oct LIVE86. Biometría isapres78, maternidad Antofagasta88, MEDS-UDP74, Interclínica88, segundo centro nuclear78, laboratorioGalénica88, Indisa86 y LarrainVial78 son ejemplos de recuperación material. La captura y evaluación de cada URL, fecha/candidatos, lane, seen, intentos y destino están en `data/audits/df_reconciliation_2026_10_11.json`.

Se retiraron resultados ajenos al sector y el resumen incorrecto de SeñalDF. Fiscalía/catástrofe, antes72 con texto contaminado, fue62 con su artículo real: rechazo legítimo después de reparar captura. Estudio minero72 se retiró por evaluación explícita de contexto secundario sin cambio material. Las observaciones anteriores y las nuevas decisiones siguen en cola/history, no se borran.

Estado final:21 publicaciones aceptadas en colaDF;34 URLs DF de90 días presentes en history/feed, incluyendo stock previo.40 retry, sin pending sin evaluar: contenidos no textuales/insuficientes y4 discrepancias de fecha multimedia pendientes en el estado retenido.13 URLs sin día verificado en la matriz:4 multimedia y9 documentos/listados excluidos como ruido de captura. Las ventanas inclusivas son12-sep–11-oct y14-jul–11-oct.183 URLs fechadas en30 días y215 en90. Reconciliación total df.cl sigue **parcial**, no se afirma que un inventario de etiquetas pruebe cobertura de noticias no etiquetadas.

[Capture-only38114804287](https://github.com/cftorre1/Radar-salud/actions/runs/38114804287) no consumió IA. Preserva fronteras observadas: salud/p1 llega a31-ago, p2 a29-jul, p3 a3-jun. Se visitaron24 páginas de salud/isapres/Fonasa/SeñalDF. Los días de cards sólo documentan navegación; no reemplazan la fecha del detalle.

## Formatos restantes, con originales exactos

- SeñalDF primer Presupuesto: CUERPO contiene5 PNG y ningún texto. `df_senal_presupuesto_real.html` demuestra la causa; no es otro titular de Ricarte. Diferir como `df_image_only_requires_ocr`. El presupuesto con consecuencia sanitaria concreta ya está representado por el artículo textual30-sep (Salud+4,7%, propuesta en trámite); no se inventa el contenido de los gráficos.
- Corazón del Negocio/salud mental: iframe `https://mdstrm.com/embed/6a904fa97897765c7c70f94e`, descripción corta y ninguna transcripción. `df_health_video_real.html` demuestra el formato. Fecha principal1-sep verificada por el parser actual, discrepancias retenidas; `df_media_transcript_unavailable` conserva el fallo de lectura separado de fecha.
- El parser reconoce imágenes/media y diferencia fecha verificable de cuerpo legible. Las precisiones de formatos se probaron sobre originales retenidos después del último engine real; aún no existe runtime post-merge de ese candidato.

Evidencia: `data/audits/df_remaining_formats_2026_10_11.json`, manifest de8 fixtures con hashes/captura, artefactos Actions con HTML completo. El proxy cloud bloquea df.cl y descarga FileService; Actions sí accedió a DF y al modelo. No declarar inaccesibilidad universal del publisher. OCR/transcripción requieren otro procesamiento de contenido; no están certificados en este candidato.

## Gates de cierre: bloqueados

-52 tests mínimos PASS. Suite local ampliada298PASS,1FAIL,1skipped (live beta excluida); NodePASS. El único fallo es `tests/test_web_snapshot.py:289`:11 normativas frente a mínimo12, ya presente en staging. No se fabrican tarjetas ni se debilita el test por volumen.
-Reviewer determinístico: data/editorial/UX PASS; estadísticas FAIL con8 hallazgos críticos SIS junio2026. No equivale a revisión semántica independiente ni ReviewerPASS global.
-Browser local: Chromium ausente y mirrors403 de política cloud; cero ejecuciones de producto,46 errores de lanzamiento históricos. No presentar esos errores como46 regresiones.
-PR QA38111771457: testsFAIL, staging/Reviewer skipped. Falta QA+Reviewer+staging candidatePASS y, según gate maestro de issue5, merge seguro y runtime **posterior al merge**. Merge SHA nulo. No cerrar DF/#5/#6.

`source_health` mantiene warning/partial, última publicación aceptada10-oct, inventario incompleto. Distingue hora de sondeo real de listados, originales de detalle y runtime. Capture-only cuenta0 publicaciones en esa ejecución; conserva15 del último procesamiento y21 aceptadas en stock de cola. No renueva timestamps de otras fuentes.

## Continuación exacta

1. Resolver dependencias normativas/estadísticas del candidate con los workers correspondientes; volver a QA+Reviewer. El bloqueo de aceptación es externo al frente DF y no requiere autorización humana para continuar trabajo ya aprobado.
2. En una reparación DF separada, obtener y verificar OCR de los5 PNG y transcripción del iframe cuando exista evidencia suficiente; conservar assets/hashes y evaluar materialidad, duplicación y mínimo72. Mantener retry mientras no exista cuerpo verificable. Reauditar los4 multimedia con discrepancias usando el parser actual.
3. Actualizar la matriz después de cualquier decisión con `python scripts/reconcile_df.py --update-matrix-only`; esto conserva el SHA/hora del runtime original. `scripts/resolve_df_editorial_audit.py` usa evaluaciones reales ya registradas, sin nuevas llamadas, y preserva su ledger entre replays.
4. Para runtime real aislado: retirar `--capture-only` del workflow DF y actualizar el artefacto de cache al último run/SHA; ejecutar sondeo nuevo y processor dentro de presupuestos existentes. No usar Daily original, que escribe staging. Revisar outcomes antes de aceptación.
5. Con gatesPASS, seguir cadena issue→task→PR→merge seguro staging→runtime post-merge→source outcome→queue/PMO→cierre. Hasta entonces PR borrador, fuente parcial e issues abiertas.

Uso observado acumulado Fast165 (base31;134 llamadas de este frente), Deep14 sin cambios. Las primeras14 respuestas no se conservaron individualmente en el primer artefacto; el agregado se recuperó del log. No se inventan costes/tokens de esas respuestas. Incidentes y controles preventivos: `data/autopilot/learning_ledger.json`.
