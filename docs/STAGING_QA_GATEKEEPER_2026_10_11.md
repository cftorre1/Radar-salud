# Staging QA Gatekeeper · READY_FOR_INTEGRATION · PR #17

Paquete para **Integration Commander** en [PR #17](https://github.com/cftorre1/Radar-salud/pull/17), rama `codex/staging-qa-gates-20261011`. Implementación validada: `8339640f43309f908f69edae43b1b34bbbf23d24`, basada en staging actual `916fe2d4684466577ef86374cff2f4d58c377ef0`. Integrar el PR completo, incluido el commit de evidencia posterior; no seleccionar solamente el test o el snapshot.

[CI 38143298390](https://github.com/cftorre1/Radar-salud/actions/runs/38143298390) **PASS** sobre el candidato de merge `97322d083a4f4327d7a3d549cd55e24f843caf91`: **312 Python PASS / 1 SKIP justificado, 41 Node PASS, 48 browser desktop/mobile PASS, Reviewer original PASS con cero findings**. El skip corresponde al test beta LIVE que requiere `OPENAI_API_KEY`, ausente; no se presenta como ejecución LIVE. La lectura semántica de los originales complementa los controles deterministas.

Recibos, jobs, SHA de artifacts y clasificación individual: `data/audits/staging_qa_gates_2026_10_11.json`. Entrada estadística con referencias PDF/página/métrica: `config/statistical_analysis_verified_v1.json`. Queue, PMO y learning ledger registran el mismo estado y siguiente acción.

## Por qué había 11 actos frente a la expectativa de 12

El [preview 753](https://github.com/cftorre1/Radar-salud/actions/runs/38128983053), sobre staging inicial `4ff51cf`, dejó 265 PASS / 1 FAIL / 1 SKIP. El fallo detuvo browser y Reviewer. Se reprodujo sobre sus mismos datos.

La [Circular IF/N°529 original](https://www.superdesalud.gob.cl/normativa/circular-if-n529/) declara **10 de julio de 2026**. Los doce actos originales revisados permanecen en history, con identidades únicas. El exportador usa la última fecha de publicación de history como referencia de su ventana: 9 de octubre en la base inicial, cuando IF529 tenía 91 días; 10 de octubre en staging reconciliado, cuando tenía 92. Su exclusión de la ventana inclusiva de 0–90 días es correcta. Al 11 de octubre tiene 93 días. No se cambia su fecha ni se añade un acto para completar una cuota.

| Hipótesis | Evidencia y disposición |
|---|---|
| A · acto válido omitido | Ninguno entre los doce originales revisados que sean elegibles. Se exige presencia por identidad, sin permitir que otras normas sustituyan una omisión. Esta conclusión no pretende certificar cobertura exhaustiva de todo SIS. |
| B · filtro incorrecto | IF529 supera 90 días; el filtro existente la excluye correctamente. |
| C · pérdida durante export/snapshot | El original, history y fixture del conjunto de doce se conservan. Sale solamente de la ventana visible. |
| D · expectativa obsoleta | Causa demostrada: una cuota permanente y una lista browser fija sobre datos que expiran. |
| E · duplicación histórica | No hay duplicados URL/identidad entre los doce originales. Una referencia a IF529 desde otra norma no constituye un nuevo acto IF529. |

La reparación exige todas las identidades revisadas elegibles, ausencia de las expiradas, URLs únicas y contratos de los campos realmente exportados. Evita reaplicar el contrato antes de comprobarlo, lo que habría ocultado errores del snapshot. Se conserva el fixture genuino de doce actos aportado por staging y la regresión del día 90/día 91. Las normas opacas siguen requiriendo revisión editorial. **No se cambia 12 a 11 ni se baja un umbral editorial.**

## Los ocho findings estadísticos

Se reprodujeron individualmente sobre el boletín IP junio de 2026. History ya contenía los cuatro documentos oficiales. El análisis derivado dependía de `data/statistical_analysis_overrides_v1.json`, generado en CI pero ausente de un checkout limpio; al exportar sin él, se perdían tabla y evidencia. Se conserva ahora una entrada canónica revisada y el runtime puede aportar análisis posterior. JSON/esquemas malformados o patches que cambien identidad/fecha fallan explícitamente.

| Finding | Clasificación | Corrección verificable |
|---|---|---|
| `invalid_statistical_table` | Defecto de export | Seis filas con seis columnas coherentes. |
| `methodology_not_collapsed` | Presentación/export | Metodología accesible y colapsada. |
| `missing_incremental_value_gate` | Export | Valor incremental explícito de la tabla; conclusión repetida omitida. |
| `generic_why_required` | Presentación/export | Impacto genérico opcional, sin texto de relleno. |
| `untraceable_statistical_evidence` | Export | Evidencia enlazada a los cuatro PDF primarios. |
| `bulletin_coverage` | Export | Acreditación, Mediación, Reclamos y RNPI incluidos. |
| `bulletin_missing_pdf` | Proyección de evidencia | Los cuatro documentos que estaban en history quedan enlazados desde el análisis. |
| `bulletin_stock_flow_confusion` | Presentación/export | Stock, flujo acumulado 2019–2026 y promedio mensual etiquetados por separado. |

Los originales acreditan 971 prestadores, 101 con observaciones y 584 solicitudes pendientes; 175 mediadores y 12.067 solicitudes acumuladas; promedio mensual de 1.996 reclamos frente a 1.530; y 1.004.982 **títulos** RNPI. Títulos no equivale a profesionales únicos. Las 1.034.076 inscripciones por entidad habilitante tienen otro denominador. Cada cifra conserva periodo, tipo y referencia de página. No se inventa actividad mensual nueva. Fecha de publicación del boletín **3 de agosto**, score **58** y decisión editorial **group** se mantienen.

Durante esta verificación, Integration Commander incorporó DF y otra interpretación de estos gates a staging. Su excepción Reviewer para `publication_inventory` evitaba controles de tabla, evidencia y tipo. Para cumplir **«NO reducir Reviewer»**, este paquete restaura `scripts/statistics_reviewer.py` byte a byte al baseline `4ff51cf`. Una regresión exige los ocho findings originales aun con la etiqueta de inventario, y comprueba que el análisis de los PDF los resuelve. No queda ningún finding pendiente ni silenciado.

Tres publicaciones exigidas por browser también expiraron: [GES](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-trimestral-de-casos-ges-auge-de-fonasa-y-sistema-isapre-a-marzo-2026/) y [series](https://www.superdesalud.gob.cl/biblioteca-digital/series-estadisticas-del-sistema-isapre-1990-2025/), publicadas el **10 de julio**; [finanzas](https://www.superdesalud.gob.cl/biblioteca-digital/estadisticas-financieras-del-sistema-isapre-a-marzo-2026/), el **7 de julio**. Sus páginas originales confirman las fechas de publicación, distintas del periodo de datos. Builder solicita solamente releases elegibles; browser comprueba presencia/contratos de las elegibles y ausencia de las expiradas. Reviewer conserva las pruebas de las cuatro familias, unidades, cálculos y documentos.

Una regresión browser con reloj histórico conserva permanentemente la cobertura visual de la tabla y la metodología en desktop/mobile. Usa el análisis y la publicación originales; el wrapper editorial y la ruta de respuesta son fixtures de prueba. No cambia el estado editorial del feed real ni rejuvenece publicaciones.

## Reproducción y alcance

Ejecutar el workflow canónico `.github/workflows/qa.yml`: Python y Node; build estadístico, epidemiología, export offline de history, Global Intelligence y product_report; browser desktop/mobile; Reviewer sobre el mismo artifact web. El primer candidato `94d8a7e` también pasó [CI 38141940100](https://github.com/cftorre1/Radar-salud/actions/runs/38141940100), con 46 ejecuciones browser antes de añadir el fixture histórico.

Los ocho errores locales iniciales de Global/product desaparecieron al ejecutar sus prerrequisitos existentes. No se modificó ese producto para ocultarlos. Los outputs temporales del build permanecen fuera de commits. La regla existente de epidemiología puede retirar un pulso expirado durante el build canónico: no constituye una reparación nueva de una fuente.

Frente a staging `916fe2d`, **72 filas ajenas del feed son idénticas**; sólo cambia la presentación del boletín. History, pending, seen, discovery, watermarks y source_health conservan sus bytes y frescura. Queue, PMO y ledger retienen toda evidencia concurrente. Se heredan las reparaciones DF ya integradas por staging, sin escribir reparaciones nuevas de DF/Pulso/FONASA/fiscalización. PR #15 fue leído para separar sus fallos heredados; no se importa su reparación.

## Acción exacta para Integration Commander

1. Integrar **PR #17 completo hasta su HEAD final** en staging actual, preservando tareas, PMO y ledger concurrentes. Commits materiales: `b6f5e03` normativa, `94d8a7e` estadísticas, `13e2649` fixture histórico y `8339640` reconciliación con Reviewer estricto; el último commit registra el handoff. No reescribir historia.
2. Reejecutar QA canónico después del merge, sobre el SHA resultante y el mismo artifact revisado. Si staging vuelve a avanzar, reconciliar y repetir todos los gates.
3. Revalidar cada PR de fuentes restante contra ese staging. Resolver conflictos del exportador preservando ambas causas y repetir QA/Reviewer.

Este PASS resuelve los fallos heredados de gates. Las brechas de cobertura, autonomía o edición de #5 y #7–#9 permanecen separadas; no se cierran issues ni se certifica operación LIVE adicional. No se hizo merge a staging, main o producción desde esta rama. No se solicita decisión humana para la reparación; la integración corresponde a Integration Commander.
