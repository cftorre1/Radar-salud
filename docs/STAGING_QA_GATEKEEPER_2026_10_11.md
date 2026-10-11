# Staging QA Gatekeeper · PR #17

Paquete independiente sobre `staging` `4ff51cfe3f5b61217699eb68612a9861239b72a8`, rama `codex/staging-qa-gates-20261011`. No incorpora colectores, estados ni reparaciones de DF/Pulso/FONASA/fiscalización. Mantiene los controles Reviewer originales y sus umbrales; no modifica workflows de deployment. No se hizo merge a staging/main/producción ni se cerraron issues.

## Causa de `11 >= 12`

El [preview753](https://github.com/cftorre1/Radar-salud/actions/runs/38128983053) dejó265PASS/1FAIL/1SKIP y browser/Reviewer SKIPPED. Se reprodujo el fallo sobre los bytes de staging.

La [Circular IF/N°529 original](https://www.superdesalud.gob.cl/normativa/circular-if-n529/) dice **10-jul-2026**. Los doce actos revisados siguen en history y tienen identidades únicas. El exportador usa la última fecha de publicación elegible como referencia; en esta base es9-oct, por lo que529 tiene91días y sale correctamente del feed. Al11-oct tiene93días. No se reemplazó12por11 ni se agregó un acto por cuota.

| Hipótesis solicitada | Evidencia / disposición |
|---|---|
| A · acto válido omitido | Ninguno entre los doce originales revisados que son elegibles; todos se comprueban por identidad, no por un recuento sustituible por otras normas. No constituye auditoría exhaustiva de todo SIS. |
| B · filtro incorrecto |529 supera90días; su exclusión respeta el filtro existente. |
| C · pérdida de export |Original e historia conservados; sólo sale de la ventana visible. |
| D · expectativa obsoleta |Causa demostrada: el mínimo12y la lista browser suponían un inventario permanente. |
| E · duplicación inflaba baseline |No hay duplicados URL/identidad entre los doce actos revisados. Referencias a529desde otra resolución no son un nuevo acto529. |

La prueba exige que todos los actos revisados elegibles estén en el snapshot, ningún expirado reaparezca, no haya duplicados y los contratos correspondan a los campos efectivamente exportados. Conserva los doce originales en history y verifica el límite día90/día91 con reloj de fixture. Las normas opacas siguen requiriendo revisión; no se relajó su contrato editorial.

## Ocho findings estadísticos

Los ocho se reproducían en el boletín IP junio2026. Su history conservaba cuatro documentos oficiales, pero el replay sin el archivo efímero `data/statistical_analysis_overrides_v1.json` degradaba la presentación a un inventario sin tabla/evidencia. La copia canónica de esa información estaba ausente de git. El arreglo conserva análisis revisado en `config/statistical_analysis_verified_v1.json`, con PDF/página/métrica. Inputs malformados o que intenten cambiar identidad/fecha fallan explícitamente.

| Finding | Clasificación | Corrección comprobada |
|---|---|---|
|invalid_statistical_table|Defecto de export|Seis filas, seis columnas coherentes.|
|methodology_not_collapsed|Presentación/export|Metodología accesible en capa colapsada.|
|missing_incremental_value_gate|Export|Valor incremental de la tabla explícito; conclusión repetida omitida.|
|generic_why_required|Presentación/export|No se exige impacto genérico sin valor adicional.|
|untraceable_statistical_evidence|Export|Cuatro PDF primarios en evidencia de datos.|
|bulletin_coverage|Export|Acreditación, Mediación, Reclamos y RNPI incluidos.|
|bulletin_missing_pdf|Proyección de evidencia|Los cuatro links que ya existían en source_documents quedan trazables desde el análisis.|
|bulletin_stock_flow_confusion|Presentación/export|Stock, flujo acumulado2019–2026 y promedio mensual separados.|

La revisión original acredita971prestadores/101con observaciones/584solicitudes pendientes,175mediadores/12.067solicitudes acumuladas, promedio mensual1.996frente a1.530y1.004.982títulos RNPI. Títulos no equivale a profesionales únicos;1.034.076inscripciones por entidad habilitante usa otro denominador. Son métricas reportadas por los cuatro PDF, con cortes/periodos separados; no una nueva actividad mensual inventada. Fecha del boletín3-ago, score58 y decisión editorialgroup permanecen iguales.

Tres publicaciones exigidas en browser también expiraron: [GES](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-trimestral-de-casos-ges-auge-de-fonasa-y-sistema-isapre-a-marzo-2026/) y [series](https://www.superdesalud.gob.cl/biblioteca-digital/series-estadisticas-del-sistema-isapre-1990-2025/) publicadas10-jul, [finanzas](https://www.superdesalud.gob.cl/biblioteca-digital/estadisticas-financieras-del-sistema-isapre-a-marzo-2026/)7-jul. Los originales confirman esas fechas; no se confunden con el periodo de los datos. Builder sólo solicita releases elegibles y browser exige presencia/contrato de cada elegible, ausencia del expirado. Los tests de Reviewer siguen cubriendo las cuatro familias y rechazando errores de unidades/cálculo/documento. Un test browser con reloj histórico conserva permanentemente la cobertura de la tabla/capa metodológica, sin rejuvenecer datos en el feed real.

## Verificación y reproducción

Primer candidato94d8a7e: [CI38141940100](https://github.com/cftorre1/Radar-salud/actions/runs/38141940100), tests/staging/Reviewer PASS.270PythonPASS/1SKIP explícito por OPENAI_API_KEYausente en un test beta; no ejecución LIVE declarada por ese skip.41NodePASS,46browserPASS; Reviewer cero findings y data/editorial/statistics/UXPASS. La regresión posterior agrega dos ejecuciones desktop/mobile del fixture histórico. Ver receipt exacta actual en `data/audits/staging_qa_gates_2026_10_11.json` y checks del PR.

Orden canónico de QA: Python y Node; build estadísticas, epidemiología, export offline de history, Global Intelligence y product_report; browser desktop/mobile; Reviewer sobre esos mismos bytes. Los ocho fallos browser iniciales de Global/product fueron consecuencia de omitir esos prerrequisitos en la reproducción local; desaparecieron al ejecutar el build existente. No se modificó Global/product para ocultarlos.

El diff de feed versionado cambia únicamente el boletín;48filas ajenas se conservan exactamente. History, pending, discovery, seen y source_health no se modificaron. Outputs temporales del build Global/product/epidemiología y runtime analysis se mantienen fuera de commits. El build canónico puede retirar la epidemiología ya vencida mediante su regla preexistente; no es reparación nueva de una fuente ni nueva publicación. Captura y SHA de esos outputs están en artifacts de CI.

## Integración

Integrar **el PR #17 completo hasta su HEAD final** sobre staging actual, preservando el resto de tareas/PMO/ledger. No seleccionar sólo el test o sólo el snapshot: fuente de análisis, guardas de export, pruebas y evidencia forman un paquete. Commits materiales: `b6f5e03` (normativa), `94d8a7e` (estadísticas), regresión histórica y handoff posteriores. Sin reescribir historia.

Reejecutar el workflow canónico después del merge. Luego revalidar cada PR de fuentes contra staging actualizado; este PASS técnico no cierra las brechas de cobertura, autonomía o edición de #5/#7–#9. PR #15 fue leído sólo para distinguir sus seis fallos heredados; no se incorporó su reparación. Resolver cualquier conflicto futuro del exportador preservando ambas causas y repetir todos los gates. No se requiere decisión humana para la reparación; el merge corresponde al Integration Commander.

## Reconciliación con staging actual

Durante la validación, staging avanzó a `916fe2d4684466577ef86374cff2f4d58c377ef0` e incorporó DF mediante Integration Commander. Se integra ese staging en la rama propia, conservando sus estados de fuentes, health, queue, PMO y ledger. El diff del candidato respecto de ese staging modifica sólo gates/estadísticas: 72 filas ajenas del feed son idénticas. No se escribió una reparación DF nueva.

Staging había agregado una excepción Reviewer para `publication_inventory` que evitaba controles de tabla/evidencia/tipo del boletín. Para cumplir «NO reducir Reviewer», se restaura `scripts/statistics_reviewer.py` byte a byte al baseline `4ff51cf`. Una regresión exige los ocho findings originales aun con esa etiqueta y confirma que sólo los datos analizados desde PDF los resuelven. Se conserva también el fixture original de doce normas aportado por staging. Verificación de reconciliación: 312 Python PASS/1 SKIP y 41 Node PASS; browser/CI exacto pendiente en este checkpoint.
