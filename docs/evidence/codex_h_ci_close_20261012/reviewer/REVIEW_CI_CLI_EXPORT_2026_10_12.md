# Reviewer independiente · cierre focal CLI de PR33

**PASS_SCOPED del arreglo local del CLI. Sin nuevos P0/P1 encontrados en este delta. Código final identificado; entrega documental y CI remota pendientes.** No amplía el PASS técnico/editorial previo ni levanta HOLD; no certifica publicación, beta, producción o merge.

Base HEAD: `68749a93d67e871ce9aaf7dc72b8f80458a17154`. Código revisado: `9cb334462a852ab09e2bf4221b10497fc25b6bac`. Commit de tres archivos modificados y un test nuevo; sus cuatro contenidos coinciden con el árbol probado. Diff exacto `reviewed-code.diff` SHA256 `4735f1fb453dae888128d10d872eecc4a23000cb34fe50204adbabbc8fbdc5ed`. Manifest de los cuatro contenidos SHA256 `02398d61dab743a91ec02393987bde328c10791266e97101a52137e80ca10d1e`. Diff del commit SHA256 `4735f1fb453dae888128d10d872eecc4a23000cb34fe50204adbabbc8fbdc5ed`. El head de entrega documental se conciliará antes de la siguiente CI.

## Hallazgo y resolución

El run `38258425687` falló en staging al ejecutar `python scripts/export_web_snapshot.py --offline`: importó `scripts.export_public_sources` pese a que el entrypoint pone `scripts/` en sys.path y el paquete instalado sólo expone `radar_salud`. El snapshot ya se había escrito y el fallo ocurre al emitir el catálogo público. El pytest interno no reproduce necesariamente ese entorno.

La función `export_public_sources` pasa sin cambios de cuerpo/defaults al módulo instalable `radar_salud.public_source_catalog`; ambos scripts importan desde el paquete. AST de la función movida coincide con la anterior. AST de eligible/build_catalog permanece idéntico; snapshot cambia sólo la ruta del import. Los gates editoriales, políticas estadísticas, allowlist/fechas del catálogo, workflows, datos y paid lineage quedan fuera del delta.

## Corroboración independiente

- Export offline del CLI ejecutado como subprocess con `PYTHONPATH` eliminado y paquete instalado: exit0,165 señales. Salida en directorio propio del Reviewer, sin escribir web/data o data vivos.
- Las165 señales coinciden con la salida generada antes del fallo. Fecha coincide; generated_at es metadato de ejecución y no se exige igual. Source_health copiado byte por byte desde el original.
- Catálogo emitido:14 fuentes, filas sólo id/name/group/url/description, Reuters bloqueado excluido. No nueva captura ni llamada pagada.
- Dos regresiones subprocess ejecutadas por Reviewer:2PASS (`independent-cli-tests.log`). Standalone desde cwd temporal conserva input y excluye fuente bloqueada. No suite integral. Builder informa60tests focalesPASS, que se mantienen atribuidos al Builder.

|Archivo|SHA256 del contenido revisado|
|---|---|
|scripts/export_public_sources.py|`f11cc6aa8595f81a1daeb9aa3e9eb150429ebf405ad159ffa7b2ec7d979bde4d`|
|scripts/export_web_snapshot.py|`485f4e2c3250a98d668441bcfae4d0b566d5e7d14006d37e7e21746b47cf5419`|
|src/radar_salud/public_source_catalog.py|`3123b86cfe07e9ad7b21c420a6702464a8f9e0e3308545cb07b7ea83fc79b8b6`|
|tests/test_public_source_catalog_cli.py|`0cd6f5ed870b4407b57b1146400a20e006683d569495c99ebab2eaa24848e391`|

## Límites y siguiente comprobación

Receipt vinculado al código `9cb334462a852ab09e2bf4221b10497fc25b6bac` y diff exacto revisado. Un head documental posterior debe preservar los cuatro hashes o volver a revisar el delta. La CI completa del nuevo SHA sigue pendiente y puede descubrir fallos ajenos a este arreglo. La ausencia de nuevos P0/P1 en el patch no equivale a CI verde. Permanecen HOLD/P2 del informe editorial anterior.

Reviewer sólo escribe en ci-close/reviewer. No reabre originales, modifica implementación, autoriza llamadas pagadas, cambia gates o repite suite integral. Evidencia/logs/hash en JSON acompañante.
