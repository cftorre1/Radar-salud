# Codex H · cierre del gate CI de PR33

PR: https://github.com/cftorre1/Radar-salud/pull/33. Base staging: `ef8cbe3938623d493872ff5f3e717153f176d1be`. Corrección de código: `9cb334462a852ab09e2bf4221b10497fc25b6bac`. El head final y los resultados de Actions/Reviewer se registran en la descripción de la PR después de terminar los checks, sin modificar el candidato comprobado.

## Causa raíz y relación de SHA

Action fallida: https://github.com/cftorre1/Radar-salud/actions/runs/38258425687. Tests PASS; staging FAIL en job `114847205681`, paso8 «Recurate current history without external lookups»; Reviewer automático SKIPPED.

El run tiene head `29287d21af55b283a46fb402223cf6bb168f4b4d`. Checkout de Actions: merge sintético `634fc08400b58bc14e05116ed641e4186325ac4e`, padres staging `ef8cbe39` y head `29287d21`; su árbol `3da9b014fd9e8534a31be83fcf4cf48ee270af95` coincide con el árbol del head. El head posterior `68749a93d67e871ce9aaf7dc72b8f80458a17154` desciende de éste y sólo corrige una frase del handoff Félix Bulnes. El código del fallo es idéntico entre ambos.

Log exacto, `scripts/export_web_snapshot.py:696`:

```text
from scripts.export_public_sources import export_public_sources
ModuleNotFoundError: No module named 'scripts'
```

**Clasificación: regresión propia de empaquetado**, introducida por `d738d215`. Setuptools instala los paquetes de `src/`; `scripts/` no es un paquete instalado. Al ejecutar `python scripts/export_web_snapshot.py ...`, el namespace raíz `scripts` no queda disponible. Pytest añade la raíz por su configuración y la validación local anterior también lo hacía mediante PYTHONPATH, enmascarando el fallo del CLI. No es una incompatibilidad del contenido histórico ni un fallo heredado de staging.

## Corrección mínima y QA focal primero

Se traslada **sin cambios de cuerpo ni firma** `export_public_sources` a `radar_salud.public_source_catalog`. Ambos scripts importan esa función desde el paquete instalado. `scripts/export_public_sources.py` conserva su ejecución directa y compatibilidad como wrapper. No se añade un PYTHONPATH al workflow ni un bypass del error.

Primero se reprodujo el fallo con la instalación editable del proyecto y sin PYTHONPATH. Después, este comando exportó correctamente165señales a una ruta temporal:

```bash
env -u PYTHONPATH python scripts/export_web_snapshot.py --input data/history/superintendencia_signals.json --offline --output /ruta/temporal/radar_today.json
```

Las señales y fecha del snapshot emitido antes de la excepción coinciden exactamente con el snapshot después de la corrección; sólo cambia generated_at. La copia de source_health conserva los bytes originales. Los AST de la función trasladada, eligible y build_catalog son idénticos a los previos.

Se añaden dos regresiones mediante subprocess sin PYTHONPATH: ejecución offline del snapshot y ejecución independiente del catálogo, con rechazo de fuente bloqueada y preservación de entrada. QA focal: **60 PASS**, incluyendo contratos editoriales/gates estadísticos. La prueba independiente adicional del Reviewer se adjunta en la evidencia.

## Integridad, consumo y stop-loss

Manifest contra el head previo `68749a93`: **5.673 archivos protegidos idénticos**, incluidos history, decisiones, fuentes/health, modelos, receipts, usage/budgets, PMO/queue, payloads existentes y workflows. Outputs focales se escriben exclusivamente fuera de datos vivos. No se modifica elegibilidad, gates editoriales, política de llamadas, HOLD ni presupuesto.

Consumo incremental del pipeline: **0 llamadas pagadas, 0 recapturas, 0 resets, 0 receipts reescritos**. El preparador estadístico vigente selecciona sólo el boletín de valores ya registrados; no selecciona fetch de originales ni análisis pagado. Tokens/costo de sesión Builder/Reviewer no están expuestos.

Un repro previo confirma el error y el primer cambio pasa la ejecución focal. No hay dos intentos equivalentes fallidos sin progreso. Si la CI final revela otro fallo, diagnosticar su log exacto y mantener el límite de dos intentos equivalentes; no relanzar sin cambio/evidencia.

## Handoff exacto al Integration Commander

1. Leer el head final y el run verde en PR33. Exigir que `run.head_sha` coincida con ese head. Para el checkout de PR, comprobar que el merge sintético incluya el head entre sus padres y que su árbol de código corresponda al candidato y a la base de staging reconciliada.
2. Exigir **tests SUCCESS, staging SUCCESS y reviewer SUCCESS** en la misma ejecución final. El Reviewer automático debe revisar el artefacto staging de ese merge, con findings críticos0. Un PASS anterior o un Reviewer SKIPPED no cierran este gate.
3. Contrastar el dictamen independiente focal, el manifest y los receipts de producto ya aceptados. La corrección de imports no cambia las cinco piezas editoriales ni sus hashes; P2 y HOLD del handoff original permanecen vigentes.
4. Mantener FEFI/Esencial, BCBSA/método, indicador respiratorioSE37, Reuters/licencia y preflight de pilotos bajo sus HOLD. La corrección de CI no habilita publicación de fixtures, nuevas fuentes, gasto, beta ni producción.
5. READY_FOR_INTEGRATION sólo se registra cuando los checks del candidato final hayan terminado en PASS y no haya P0/P1 abiertos. Integrar exclusivamente mediante el proceso del Commander a staging. Ningún merge a staging ni cambio de main/producción fue ejecutado por Codex H.

[Evidencia de cierre](../evidence/codex_h_ci_close_20261012/README.md). El handoff original se conserva como historial de los paquetes y sus validaciones previas.
