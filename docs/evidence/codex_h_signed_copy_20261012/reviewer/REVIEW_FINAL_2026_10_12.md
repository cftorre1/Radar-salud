# Reviewer independiente · cierre de copy v3 firmado

**PASS_SCOPED técnico sobre `6048a1d5def99e060dd973fd9640c508d1ec853d`. P0 abiertos: 0. P1 abiertos: 0 en este alcance.** P1-SIGNED-TITLE cerrado. Los HOLD editoriales/de fuentes y los P2 anteriores permanecen; esta revisión no aprueba publicación, merge, beta, producción ni gasto.

Base exacta: `74da1c6d33b9e5746e79e0f481be3057f33d45df`. Rama revisada: `codex/h-contract-followup-20261012`. La base ya integra PR33, cuyo código y handoffs se conciliaron antes de buscar el defecto. La revisión no reimplementó el contrato ni realizó una auditoría histórica.

## Defecto y cierre corroborado

En la base, una pieza v3 válida sin `display_title` podía mantener su hash y receipt PASS mientras `card_what` legacy sustituía el título firmado. El repro conservó «Resolución IF/N°1 rechaza reposición» en el campo firmado y añadió sólo «Resolución IF/N°1 acoge reposición y levanta la sanción.» en `card_what`. Backend/hash/gate/export siguieron PASS; Chromium mostró «acoge» en tarjeta, Ponte al día y ficha, en desktop y mobile. Esa evidencia se preserva en `REVIEW_BASELINE_2026_10_12.md` y en los probes/resultados `baseline`.

El candidato cambia únicamente las salidas v3 de `triageTitle` y `triageSummary` en producción: título desde `display_title || title`, resumen desde `brief_deck` opcional. Ambos campos ya pertenecen a la firma. Las reglas legacy se conservan. No cambia `PUBLIC_FIELDS`, el backend, el esquema de lectura ni los cinco receipts editoriales existentes.

El probe browser independiente sirvió `app.js` directamente desde el blob `6048a1d5`, con el mismo registro adversarial exportado que reprodujo el fallo en la base. En 1440×900 y 390×844:

- Tarjeta, Ponte al día y h2 de ficha conservan «rechaza reposición».
- Etiqueta ARIA del sobre y título de compartir conservan el mismo texto firmado.
- Título y Más info abren una ficha equivalente; el texto no firmado no aparece en las superficies inspeccionadas.
- La ficha se abre correctamente y se conserva la lógica de lectura existente.

Resultados: `signed-title-browser-final-6048a1d5.json`; capturas: `signed-title-final-6048a1d5-1440.png` y `signed-title-final-6048a1d5-390.png`. La captura desktop del SHA final y la captura mobile del working tree de idéntica corrección fueron inspeccionadas visualmente. No hubo navegación externa: rutas interceptadas de fixture y archivos locales, sin modificar datos vivos.

## Validación independiente y compatibilidad

- **Reviewer:** 47 PASS Python focal (`test_product_editorial_v3.py`) y 50 PASS Node directo en el código del candidato. No se reejecutó la suite integral.
- **Reviewer:** comparación de las 165 señales legacy del snapshot entre blobs base/candidato: cero diferencias en `triageTitle`, `triageSummary`, `card` o `detailHtml` (`legacy-compatibility-6048a1d5.json`).
- **Reviewer:** los cinco candidatos editoriales conservan exactamente los bytes de su fixture y receipt previo; sus cinco hashes coinciden con `review.content_version` y `validate_depth` devuelve `ok:true` (`receipt-integrity-6048a1d5.json`). Esto acredita integridad, no una nueva revisión de originales ni nueva aprobación semántica/publicación.
- **Reviewer:** los árboles Git `data`, `config`, `.github` y `web/data` son idénticos entre base/candidato. El único código productivo cambiado es `web/app.js`; el resto del delta son regresiones y un fixture sintético.
- **Builder, informado:** 28 pruebas browser focales PASS de product-v3/editorial-v3/signed-copy en desktop/mobile. Se atribuyen al Builder, separadas de los dos probes propios anteriores.

El primer intento Python baseline resolvió el editable de main instalado en otro checkout y falló en collection. Se preservó el log y se corrigió la ruta antes de importar pytest; ese fallo no se atribuye al candidato. La prueba CLI sin PYTHONPATH del cierre PR33 no se volvió a certificar mediante la instalación ajena. Ningún código CLI cambió en este delta.

## Límites conservados

IF10670 legacy mantiene el dictamen editorial REVISE/de publicación del Commander. Los cinco candidatos siguen como fixtures; su integridad no publica overlays. FEFI mantiene HOLD_COVERAGE_ESENCIAL pese al PASS aritmético. BCBSA/método, SE37 contradictorio, Reuters/licencia y preflight de fuentes continúan bajo sus responsables y HOLD previos.

W6-02 tiene cobertura técnica focal de Decimal/enteros/residual/tolerancia en PR33. La política general por familia permanece P2; no se afirma que este delta valide `source_precision` arbitrario ni nuevas tolerancias. W6-04 conserva el P2 de fixtures jurídicos IF7312/IF11076 y decisiones sustituidas; no se contabilizó como cierre por ausencia de tests focales. Selector genérico de tablas/KPI y adapters sin verificación mantienen los límites anteriores. AT real, zoom nativo y estudio humano no se ejecutaron.

Un `display_title` de sólo espacios puede producir título vacío por el criterio truthy anterior. Se comunicó como borde heredado de input/receipt, sin reproducir una pieza semánticamente aprobada vigente afectada ni elevarlo a un P1 de este cierre. Un fallback que recorte `display_title` y use `title` seguiría dentro de campos firmados; no es una condición adicional inventada para cerrar el P1 material.

El cálculo `triageSummary` de un fixture cambió con campos legacy en la base, pero el HTML actual de Ponte no inserta esa síntesis. El informe distingue ese cálculo no visible del escape de título público confirmado.

Reviewer escribió únicamente probes/reportes propios bajo `/workspace/work/reviewer-contract`, con cero cambios de código o datos del Builder, cero recapturas y cero llamadas IA pagadas. El PASS está ligado al SHA de código exacto anterior; un head posterior documental requiere conciliación explícita de su delta. La decisión de integración/publicación corresponde al Integration Commander.
