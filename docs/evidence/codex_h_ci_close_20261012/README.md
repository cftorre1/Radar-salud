# Evidencia del cierre CI · PR33

Corrección de código: `9cb334462a852ab09e2bf4221b10497fc25b6bac`. Base del delta: `68749a93d67e871ce9aaf7dc72b8f80458a17154`.

- `failed-staging-38258425687.log`: log íntegro del job staging fallido; identifica el import no instalable y el checkout merge sintético.
- `repro-before.log` / `repro-after.log`: ejecución del mismo CLI sin PYTHONPATH, antes y después; output en carpeta temporal y sin llamadas externas.
- `focal-tests.log`:60 PASS de CLI, contratos editoriales y estadísticas.
- `protected-files.json`:5.673 archivos existentes idénticos; AST de exportación/elegibilidad sin cambios;165señales idénticas antes/después.
- `reviewer/`: dictamen independiente focal y pruebas propias, copiados sin editar.

Los resultados definitivos de la CI completa y su Reviewer automático se enlazan en la descripción de PR33 después de terminar. No se añaden commits tras esos checks para cambiar el SHA que aprobaron. Los artefactos del run verde conservan el web compilado, browser evidence y Reviewer automático.

No se acredita PASS por el run fallido ni por el Reviewer SKIPPED. Sin recaptura, publicación de candidatos, nuevos modelos o gasto.
