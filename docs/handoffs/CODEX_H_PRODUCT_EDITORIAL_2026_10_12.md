# Codex H · implementación del contrato de producto y editorial

Fecha: 12-oct-2026. Destino exclusivo: PR hacia `staging`. Integración reservada al Integration Commander.

Actualización posterior: [cierre del gate CI](CODEX_H_CI_GATE_2026_10_12.md), con causa raíz, corrección focal y condiciones de PASS sobre el candidato final. Las validaciones siguientes corresponden a la entrega original; el estado definitivo está en PR33.

Contrato: [PR32](https://github.com/cftorre1/Radar-salud/pull/32), SHA `a3e254d9ada6d2750787b416d7a9ee2253c08334`. Base reconciliada: `ef8cbe3938623d493872ff5f3e717153f176d1be`. Rama: `codex/h-product-editorial-20261012`. El SHA final de entrega figura en la descripción de la PR; los receipts identifican separadamente el SHA del código revisado y los hashes de cada candidato editorial.

Estado: PASS_SCOPED técnico y editorial del Reviewer independiente sobre el código final, sin P0/P1 abiertos en su alcance; QA local completo más rechecks focales. Actions del head final se registra en la PR. No implica autorización de publicación, beta, producción ni merge. Los HOLD de fuentes y contenido continúan vigentes.

## Reconciliación previa

Se leyeron PR32 completo y comentarios, Issue5 y decisiones recientes, handoff/evidencia/Reviewer Work5, auditoría Work6 (`469b491caba94b281f4ab31844d4e8eb827ff594`) y recheck W6-01 (`46366282d5316c100fadd2048c6a8c0b3bdfae87`), contratos vigentes, queue y PMO. W6-01 está cerrado en especificación sobre el SHA del contrato. La autorización explícita de Dirección en esta tarea permite implementar en rama aislada.

Se reconcilió staging posterior a Work5: incorpora los frentes recientes de fuentes y conserva feed de 165 señales e historia de 992 registros. Último preview consultado: [Actions38208484632](https://github.com/cftorre1/Radar-salud/actions/runs/38208484632), SHA de base `ef8cbe39`, success. No se contabilizan las señales y llamadas de PR29 como staging. Se conservan su NO MERGE y los controles de captura/frescura pendientes del Commander.

Antes de la entrega, los refs remotos siguen siendo main `54174c5d690daa29f75b6956d6e90c90ee5cd177`, staging `ef8cbe3938623d493872ff5f3e717153f176d1be` y production-stable `06831243d83705777f6a916fcc86a7896d6522da`.

## Paquetes y checkpoints

| Paquete | Comportamiento entregado | Evidencia focal |
|---|---|---|
| A · UX | Título y Más info abren una ficha canónica directamente. Sobre compacto y acciones accesibles. Filtrar u ordenar junto a +; Radar/Global claros; Volver arriba flotante fuera de fichas. Ponte al día muestra filas completas y permite expansión sin scroll interior rígido. | Browser1440×900 / 390×844, probes320px y195px, capturas Home/Global. |
| A · lectura | IndexedDB `alicanto_read_v3`, registros por pieza, false explícito, migraciones transaccionales con marcadores; sincronización entre pestañas y recuperación en pageshow/visibility. Leer sólo tras render y showModal exitosos. | Probes independientes de alias/tombstone, foco, expansión y nueva edición semanal; regresiones browser. |
| A · fuentes | Exportación pública con allowlist nombre/URL/grupo/alcance, sin bloqueadas/pausadas/no verificadas. Fecha inválida o futura no acredita consulta. Administración y diagnósticos originales conservados. | Catálogo separado `public_sources.json`, pruebas de límites de payload y5.671 archivos protegidos idénticos. |
| B · editorial | Esquema v3 de claims/evidence, decisiones por párrafo y módulos opcionales. Hash del artefacto público y receipt independiente final. QA determinista bloquea falta de soporte, conclusiones sin premisas, ciclos y revisión desactualizada. | Casos adversariales y cinco receipts editoriales independientes. |
| B · presentación | Ficha sin encabezados obligatorios que repiten. Proyección legacy conserva hechos, fuentes y contexto histórico secundario. Global mantiene atribución, cifra y límites; Home y ficha usan el mismo titular BCBSA. | Casos normativos/noticiosos, Global y fuentes originales en browser. |
| C · normativa | Fechas de emisión/publicación/fiscalización/período/vigencia separadas; sanciones requieren revisión primaria para ancla de emisión. Identidad jurídica, materia y efecto de títulos conservados. | IF534/IF10670, fechas de sanción y registros nativos de fiscalización. |
| C · estadísticas | Decimal, dominios y comparabilidad explícitos, sin porcentaje ordinario con base negativa/cero o cambio de signo. Revisiones de base separadas. Selector por hallazgo, sin cuota ni plantilla universal. Adapter Pulso con KPI/serie/entidades cuando hay filas verificadas; otras familias nativas sin adapter verificado quedan HOLD con fuente, y las tablas legacy existentes se conservan; contratos y movilidad separados por unidades y libros. | FEFI aritmética+HOLD, cartera, contratos/movilidad y SE37 como prueba negativa; pruebas responsive y tablas equivalentes. |
| D · gobernanza | Planeación determinista; reutilización sólo de receipt válido. Modelo potente requiere configuración y reserva monetaria. Sin llamadas pagadas automáticas, fuentes nuevas ni pilotos. | Regresiones de budgets/gates; manifest de integridad. |

Checkpoints: `07b34730` UX/lectura; `6d968b05` migración/foco/catálogo; `d738d215` contratos editorial/estadístico; `5bf2e651` browser y regresiones; `1d9fcaa1` integridad de copy y accesibilidad; `4de1dbd7` frontera de evidencia legacy y proyección Global atribuida; `8f6039dc` HOLD de familias sin adapter verificado y scroll accesible. Código final revisado: `8f6039dca843fda5903e5e0684ce524e0146bebe`. El commit final de documentación añade evidencia sin alterar código ni contratos.

## PASS técnico y PASS editorial

La suite Python integral obtuvo3.885 PASS, 2 FAIL, 1 SKIP y 94 subtests PASS. Los dos fallos eran hashes de extracción de PDF IST con pypdf6.10.0 del sistema. Con `pypdf[crypto]==6.20.0`, versión fijada en el proyecto, los tres tests de IST pasan; no se cambiaron originales ni oráculos. QA focal final:75 PASS. Node final:49 PASS.

Browser integral:84/94 PASS inicialmente. Se diagnosticaron los diez fallos y se revalidaron sus rutas: conservación de cálculos complementarios de Pulso, metadata de publicación/validación, límite0..89días, catálogo sin Reuters y nuevas ubicaciones de hechos en ficha. Rechecks focales dejan los94 casos cubiertos en PASS; no se afirma una única ejecución94/94 verde. La evidencia distingue cada ejecución y el caso cubierto. Tras los cambios finales se ejecutaron de nuevo las rutas de Home/Global/Pulso afectadas; no se repitió la suite completa por documentación.

Reviewer determinista sobre preview de 165 señales: 0 findings. Es un chequeo estructural separado de la revisión semántica independiente. El informe del Reviewer independiente, sus probes adversariales y receipts están en [evidencia](../evidence/codex_h_20261012/). Las limitaciones de esa revisión forman parte del candidato. P2 abiertos: adapter nativo especializado en cartera; lector de pantalla/zoom nativo200% y estudio humano no ejecutados; políticas generales de tolerancia Work6 conservadas.

Cinco candidatos editoriales conservan original/base_version, identidad, evidencia y fecha observada con su precisión real. Permanecen en `tests/fixtures/product_editorial_v3_cases.json`, sin activar overlays, modificar history/feed/latest/approved ni publicar contenido:

| Caso | Profundidad y límite preservados |
|---|---|
| IF10670 | Alcance del informe EMP tras concluir octubre; suspensión y artículo57; recursos jerárquicos remitidos, sin afirmar pendencia actual. Peticiones atribuidas a lo que recoge el regulador, sin fingir lectura de los escritos completos. |
| IF534 | Vigencia futura1-dic-2026 separada de publicación; identidad y efecto normativo. |
| Félix Bulnes | Intervención realizada el 30-sep, separada de publicación el 7-oct; técnica y alcance verificables. |
| Presupuesto2027 | Publicación6-oct; fecha del acto no conocida permanece null, sin conversión ficticia en hecho ocurrido ese día. |
| San Carlos | Continuidad y capacidad de reemplazo con fuentes DF/LaTercera/UCCHRISTUS ya registradas; sin inventar nueva captura. |

El gate semántico verifica un receipt independiente ligado al hash final. Similitud léxica sólo diagnostica; no es un juez universal del significado. El comité automático se identifica como structured_check y no se presenta como Reviewer independiente.

## Límites, HOLD y consumo

FEFI: −273,285→34.090,653 millones, diferencia+34.363,938 millones y porcentaje N/A. El PASS aritmético no elimina `HOLD_COVERAGE_ESENCIAL`: nota A18 contradice filas institucionales. No se publican tabla financiera, ranking ni agregados afectados. Los originales y fuente quedan disponibles.

Global BCBSA: el registro histórico atribuye US$942millones a BCBSA vía Reuters. Se conserva la carencia explícita de informe técnico primario, método y denominadores: `HOLD_SOURCE_METHOD`. No se aprobó el borrador de overlay ni se presenta efecto causal de IA o efecto en Chile comprobado. Reuters sigue pausado por licencia y excluido del catálogo público.

SE37 respiratoria: fixture negativo de indicador contradictorio53,7%/56,7%; selector devuelve HOLD y ningún módulo, sin inventar serie ni sumar porcentajes de universos distintos. No hay nueva revisión del PDF ni promoción epidemiológica. Pulso utiliza versión histórica julio y sus hashes registrados, sin actualización silenciosa a agosto. El desglose institucional sólo se habilita cuando se retienen y concilian las filas originales; en el snapshot base sin esas filas se muestra «desglose no verificado». Los diez extremos institucionales de Work5 se prueban como fixture separado.

HOLD y límites de fuentes, PR29, cobertura esencial, recurrencia24 h/48 h, acceso/licencia y beta pertenecen a sus responsables existentes. CENS/iHEALTH no activados: siguen sujetos a preflight de permisos, acceso y materialidad.

Pipeline:0 llamadas pagadas nuevas,0 resets de presupuesto y0 receipts históricos reescritos. Se usó una sesión Builder y un Reviewer independiente; tokens y costo de las sesiones no están expuestos por el entorno y no se inventa una estimaciónUSD. El manifest compara5.671 archivos históricos/configuración/workflows/payloads existentes con la base: todos idénticos, incluidos PMO/queue, paid receipts, usage/budgets, banderas de fuentes y snapshot original.

## Handoff para Integration Commander

1. Comprobar el head exacto de la PR y su base contra los SHA arriba. Si staging avanzó, conciliar el delta y volver a vincular la revisión al código resultante; no reutilizar un PASS de otro SHA.
2. Revisar `validation.json`, `protected-files.json`, reporte independiente y capturas1440×900 / 390×844. Comprobar Actions del head exacto y distinguir QA técnico de receipts editoriales.
3. Mantener los cinco overlays como fixtures. Una publicación posterior requiere proceso autorizado: original exacto, `source_version(base)==base_version`, `apply_overlay` aprobado, receipt del hash final y gate de publicación. La función conserva original_record y rechaza cambios en campos de lineage/pago.
4. Para generar preview en un checkout de integración, usar las dependencias fijadas, construir las estadísticas vigentes, exportar offline y ejecutar product_report. `export_web_snapshot.py` produce el catálogo público en su directorio de salida. `scripts/export_public_sources.py` puede regenerar sólo ese catálogo a partir de salud de fuentes existente.
5. Revalidar navegación, lectura, fuentes y estadísticas sobre el artefacto compilado. Los estados leídos se migran al primer inicio sin borrar localStorage legacy; las nuevas ediciones semanales son piezas independientes.
6. Integrar exclusivamente mediante el proceso del Commander hacia staging. No se solicita ni ejecuta cambio de main, producción, activación de fuentes o levantamiento de HOLD con esta entrega.

Reproducción local focal:

```bash
python -m pytest -q tests/test_product_editorial_v3.py tests/test_isapre_pulse.py tests/test_quality_editorial.py tests/test_editorial_rules_v2.py tests/test_statistics_reviewer.py
node tests/web.test.cjs
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser
```

El override de Chromium sólo se usa donde hay navegador del sistema; el workflow mantiene su instalación normal. Las capturas de casos v3 son previews de fixtures revisados, claramente identificadas en `screenshots.json`; las de Home/fuentes/Global utilizan la recuración offline del snapshot vigente. No acreditan nuevo polling ni despliegue.
