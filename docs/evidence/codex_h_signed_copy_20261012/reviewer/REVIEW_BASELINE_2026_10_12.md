# Revisión independiente del contrato PR32 sobre staging reconciliado

**REVISE: un P1 de código reproducido.** No cambia el HOLD editorial/de publicación de IF10670 legacy, FEFI, BCBSA o SE37. No autoriza integración, publicación, fuentes nuevas ni llamadas pagadas.

SHA revisado: `74da1c6d33b9e5746e79e0f481be3057f33d45df`, checkout limpio inicial en `codex/h-contract-followup-20261012`. Este SHA ya incorpora PR33 (implementación final `7ea73fba`, corrección CLI `9cb33446` y merge `c7b0ecb7`). Se leyeron los handoffs CODEX_H_PRODUCT_EDITORIAL y CODEX_H_CI_GATE y el receipt independiente previo. La revisión no replica trabajo entregado ni una auditoría histórica.

## P1-SIGNED-TITLE: el renderer v3 sustituye copy firmado por campos legacy no firmados

En `web/app.js:150`, `triageTitle` pasa por las reglas legacy aunque la pieza sea v3. Los campos `card_what`, `card_why`, `normative_subject`, `what_happened` y `why_it_matters` no pertenecen a `PUBLIC_FIELDS` (`src/radar_salud/editorial_v3.py:10`). Un título v3 sin `display_title` es válido; el registro positivo de `tests/test_product_editorial_v3.py:13` acredita ese contrato.

Repro propio: tomar ese registro, cuyo título firmado es «Resolución IF/N°1 rechaza reposición», y añadir únicamente `card_what = 'Resolución IF/N°1 acoge reposición y levanta la sanción.'`. El hash se conserva (`881b90bfe7558ae0ce75548ba1867ba3d90908c9e9e1ae6c13fde456c7e47f8f`), `validate_depth` sigue `ok:true`, `publication_ready` devuelve `(True,'ok',100)` y `curate(...,resolve_external=False)` exporta una pieza. La tarjeta, Ponte al día y el h2 de la ficha muestran «acoge» en vez de «rechaza». Chromium confirmó las tres superficies a 1440×900 y 390×844.

No hace falta modificar ni simular un receipt. El probe reutiliza el receipt válido y prueba precisamente el cambio que escapa de su hash. Tampoco se afirma que una pieza v3 haya sido publicada ya; las cinco piezas permanecen fixtures. El defecto afecta la garantía de publicación prevista cuando esas piezas o una futura pieza v3 se publiquen.

Corrección mínima recomendada: resolver el título v3 exclusivamente desde `display_title || title`, antes de cualquier regla/proyección legacy. No ampliar la firma para aceptar copy viejo ni reescribir receipts. Puede alinear `triageSummary` con `brief_deck` firmado, pero la síntesis calculada actualmente no se inserta en el HTML de Ponte al día; no constituye por sí sola otro fallo público vigente.

Evidencia independiente:

- `signed-surface-probe.py`, `signed-surface-probe.json`: hash, gates y exportación sin cambios.
- `signed-surface-probe.cjs`, `signed-surface-render-results.json`: funciones originales ejecutadas en VM.
- `signed-title-browser-probe.cjs`, `signed-title-browser-baseline.json`: app.js obtenido directamente del blob del SHA baseline y previews por rutas interceptadas sin alterar datos vivos.
- `signed-title-baseline-1440.png`, `signed-title-baseline-390.png`.

## Cobertura reconciliada y límites

UX, IndexedDB, catálogo, esquema/receipt, fechas y estadísticas v3 ya están en PR33. Los 46 tests de `test_product_editorial_v3.py` y los 49 Node directos pasan en el checkout revisado. Sus logs son `focal-python-corrected.log` y `focal-node-direct.log`. El primer intento Python resolvió accidentalmente el editable instalado de main y falló en collection; ese fallo se preserva en `focal-python.log` y no se atribuye al código de este SHA. La ejecución corregida insertó el `src` de este checkout antes de importar pytest. Los dos tests CLI no se reafirman con esa instalación ajena; el cierre CLI previo permanece evidencia de su candidato exacto.

W6-02: existe `reconcile` con Decimal, enteros para personas/casos/contratos, residual/tolerancia registrados y pruebas focales de residual monetario bajo/sobre el umbral (`test_product_editorial_v3.py:111`). Las políticas generales de precisión/tolerancia por familia están expresamente abiertas en el handoff; parsear `source_precision` o manejar tolerance malformada no se eleva aquí a P1 de publicación sin uso productivo corroborado.

W6-04: las decisiones IF7312 e IF11076 y la no suma de sanciones sustituidas, según el contexto reconciliado enviado por el Builder, siguen siendo cobertura P2 pendiente; no se encontraron fixtures focales bajo tests que permitan acreditar su cierre. No se abrió una auditoría histórica ni se alteraron sanciones.

El selector de tablas/KPI se apoya en banderas de perfil/claims verificados. Esta revisión no encontró un camino productivo de publicación que admita filas falsas mediante ese API; no convierte ese límite de validación en un P1 por analogía. FEFI mantiene HOLD de cobertura; SE37 contradictorio no crea módulos; familias sin adapter verificado conservan fuente/límite. El PASS aritmético no elimina ningún HOLD.

La revisión escribió únicamente probes/evidencia bajo `/workspace/work/reviewer-contract`, con cero mutaciones del repositorio del Builder, de datos/configuración/presupuestos, cero recapturas y cero llamadas IA pagadas. Se requiere recheck focal del P1 contra el SHA de corrección exacto antes de PASS técnico de esta nueva conciliación.
