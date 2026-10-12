# Reviewer independiente · revisión parcial de UX y persistencia

Fecha: 12-oct-2026. Base observada: ef8cbe3938623d493872ff5f3e717153f176d1be. Rama del Builder: codex/h-product-editorial-20261012. **REVISE parcial**: candidato mutable, todavía sin SHA final. No certifica editorial/estadísticas ni beta; espera revisión del candidato final. Revisor no modifica archivos del Builder. Cero llamadas pagadas del pipeline.

Se leyeron Work5_0 y Work5_1, read-state.js, app.js, global.js, public-sources.js, product-ui.css y pruebas product-v3. Chromium /usr/bin/chromium, servidor de sólo lectura localhost:8773. Probes independientes y resultados se guardan en este mismo directorio. Los hashes por archivo de la primera ejecución figuran en ux-probe-results.json; el recheck en ux-probe-results-second.json. Ninguna prueba devuelve un PASS integral.

## Hallazgos abiertos al emitir este reporte

**P1-UX-04 · Edición Insight nueva hereda lectura actual de la noticia base.** app.js migrateWeekly identifica base mediante igualdad de source_url e importa su ID v3 como alias para cada nueva approved_version_id. Repro independiente: primera carga sin weekly; marcar noticia base leída en v3; segunda carga introduce weekly con approved_version_id editorial-new y mismo source_url. Resultado: weeklyRead=true, weeklyPending=0, sin abrir nunca la nueva pieza. Contradice independencia futura de noticia/análisis y nueva edición factual. La importación legacy_shared_read debe estar vinculada a evidencia legada de esa edición; no tomar una lectura v3 corriente ni enlazar por URL. Registro: state-probe-results-initial.json.

**P1-UX-05 · Cerrar ficha desde Ponte pierde foco.** app.js close de signalDetail conserva detailOrigin, pero éste desaparece al marcar leída la fila. El fallback hace brief.focus sin garantizar que brief sea focusable. Repro: dos pendientes, abrir título de primero desde Ponte, esperar remoción, Escape. Resultado activeElement=BODY. Debe volver al siguiente elemento lógico o bandeja focusable. Registro: ux-probe-results-second.json.

**P1-CAT-01 · Proyección del catálogo descarga datos administrativos.** Home y sources.html usan fetch(data/product.json) completo y filtran después en render. Inspección del payload real confirma name, checked_at, last_signal_at, discovered, new, published, live_pending, backfill_pending, pending, deferred, rejected, status, error, technical_status, coverage_status, content_freshness y editorial_outcome. Errores reales permanecen en payload público. V2 §521–524 exige allowlist pública nombre/URL/grupo/alcance y no internos en payload ni DOM. Sanitizar en exportación, conservando source_health/history/administración originales.

**P1-CAT-02 · Fecha de consulta inválida o futura pasa como verificada.** AlicantoSources.eligible sólo comprueba checked_at truthy. Inputs checked_at=invalid y checked_at=2099-01-01 con technical_status ok / coverage_status observed devuelven true. No se inventa TTL: el defecto es admitir evidencia que no corresponde a una consulta temporal válida. Registro: ux-probe-results-second.json.

**P1-UX-06 · Persisten scroll interno rígido y filas recortadas.** Con feed real, 1440px: brief-list clientHeight330/scrollHeight3230, overflow auto, fila laboratorios parcialmente cortada. 390px: clientHeight285/scrollHeight9394, overflow hidden, fila weekly147,75px cruza borde. 320px: fila weekly175,6875px cruza borde. §3 pide quitar scroll interno rígido y cortes de medias filas. Mantener elegibles mediante expansión/paginación por filas completas, sin cortar por altura fija. Registro: state-probe-results-initial.json y ux-1440.png / ux-390.png / ux-320.png.

**P2-UX-01 · Volver arriba visible en cabecera y superpone CTA.** backTop está visible con scrollY0 y no hay IntersectionObserver. La captura390 muestra que tapa Continuar al feed en primera pantalla. V2 requiere aparecer al salir cabecera/controles, preservar CTA/foco y reduced-motion. Ocultación con modal sí está implementada vía CSS.

## Hallazgos iniciales corregidos por Builder y revalidados

- P1-UX-01: marker global signal-aliases-v1 impedía adoptar read_aliases tras corregir fecha o agregar piezas al snapshot. Repro event_date12→11 con alias de ID previo: newRead=false en primera ejecución. Builder cambia marcador a pieza+conjunto de aliases; recheck newRead=true, briefCount0.
- P1-UX-02: sobre Ponte devolvía foco antes del await; refresh removía el nodo y dejaba BODY. Builder espera mutación; recheck foco BUTTON del siguiente pendiente.
- P1-UX-03: inboxPool excluía noticia base por source_url de weekly vigente. Builder elimina exclusión; recheck basePending1, noticia e Insight mantienen IDs distintos.

## Comprobaciones independientes satisfactorias

- Escrituras concurrentes en dos pestañas a piezas distintas conservan ambos IDs.
- Alias-migration concurrente con reversión conserva false en ambas pestañas; tombstone preexistente prevalece contra alias leído y reload mantiene unread.
- Fallo forzado de HTMLDialogElement.showModal no marca noticia leída y publica aviso honesto.
- Vista real390/320 no presenta overflow horizontal de página en el estado inspeccionado.

No se inspeccionó aún la versión definitiva de selección/publicación editorial ni renderer/gates estadísticos. No se reauditaron fuentes externas ni se levantaron HOLD existentes. Pruebas futuras deben vincularse al SHA final y declarar P0/P1 abiertos/cerrados con evidencia propia.
