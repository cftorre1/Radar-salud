# WHO/PAHO · paquete para Integration Commander

PR [#26](https://github.com/cftorre1/Radar-salud/pull/26), rama `codex/global-intelligence-recurrent-20261011`, destino staging. Checkpoint del cambio de código: `a1a0e655b848c146b60762f87f60e71ea1e0db69`. El SHA final del candidato se registra en PR e issue #5 al cerrar la revisión. Ningún merge ni runtime post-merge ejecutado por Codex C.

## Dictamen y alcance

**WHO/PAHO READY_FOR_INTEGRATION para discovery de metadata**. La aceptación de operación diaria y la aprobación de contenido son gates distintos. El paquete final incluye [QA focal](../data/audits/global_integration_2026_10_11/focused_qa.json), [observación de frescura](../data/audits/global_integration_2026_10_11/freshness_preintegration.json), [matriz técnica de alternativas](../data/audits/global_integration_2026_10_11/alternatives.json), [paquete verificable](../data/audits/global_integration_2026_10_11/package.json) y el Reviewer del delta `data/audits/global_integration_2026_10_11/reviewer.json`. No equiparar candidato, merge, operación diaria o publicación.

| Fuente | Únicos con fecha verificada 30/90 | URLs del control nativo 30/90 | Disposición |
| --- | --- | --- | --- |
| WHO | 84 / 241 | 84 / 241, sin omisiones observadas | READY_FOR_INTEGRATION |
| PAHO | 185 / 530 | 243 / 673, sin omisiones observadas | READY_FOR_INTEGRATION |
| Reuters | No medible | Sin ruta autorizada | PAUSED_LICENSE; EXTERNAL_BLOCKER_PROVEN |

Son cifras del corte chileno **11 octubre**, no un nuevo poll. La unión bilingüe PAHO conserva enlaces recíprocos oficiales, títulos/fechas por idioma y receipts. Fechas originales, inventario fresco, proyecciones posteriores y ledger permanecen idénticos. El recall sólo cubre las superficies declaradas. Las diferencias índice/detalle, fechas inválidas o contradictorias, períodos de datos y fechas de evento mantienen los guards anteriores.

Los **377 candidatos materiales** —148 WHO y 229 PAHO— no son 377 tarjetas ni análisis aprobados. Los diez temas propuestos siguen pendientes. Se mantiene default 30 días, máximo 10, selección por materialidad y sin cuota. WHO/PAHO pertenecen a `WHO_UN_SYSTEM`: no contar ambas como corroboración independiente. Work Editorial conserva mérito, consecuencia empresarial, metodología, derechos, hechos/hipótesis Chile y decisión de publicación. No se revisaron otra vez sus piezas ni se alteró la colección de 14 temas aprobados.

## Qué cambió y qué QA se reutiliza

El delta añade un observador determinístico de edad y un **gate explícito de activación diaria apagado** (`daily_collection_enabled: false`). El merge ya no basta para iniciar un nuevo fetch Global de 90 días. Daily conserva su cron core y presupuestos AI; el paso elegible Global permanece después de core y lleva clave AI vacía. El observador escribe sólo un recibo nuevo de auditoría, no timestamps ni estados canónicos. Un error del observador no suprime core. Su salida tampoco acredita un poll, cadencia o publicación.

QA del delta: **33 PASS**, sin red ni IA, incluyendo límites exactos 24/48 h, captura futura/sin zona horaria, respuesta reciente con fallo técnico/cobertura/fecha, preservación de input y rechazo de sobrescritura de evidencia o datos canónicos. Los IDs de contrato WHO 2 y PAHO 4 no cambian por el gate. Se verifican hashes de inventarios, ledger, parsers, feeds, renderer y exporter.

Se reutiliza la QA aprobada del código `aee4ed3`, [run 38156977778](https://github.com/cftorre1/Radar-salud/actions/runs/38156977778): 1.178 Python, 184 dirigidas +94 subcasos, 43 Node, 12 desktop/mobile, replay y auditor independiente PASS. Son receipts del código/superficies sin cambio, no una nueva suite sobre todo el HEAD actual. No se lanzó una suite completa ni navegador manual: no cambió UI, contenido curado ni health público. La CI crítica automática y su corrección posterior se documentan al final. Los límites históricos de baseline y UI Lite siguen en [el contrato original](GLOBAL_SOURCE_DISCOVERY_2026_10_11.md). El Reviewer nuevo cubre únicamente código/gate/documentación/gobernanza nuevos y conservación de evidencia previa.

## Daily First: plan de recurrencia y frescura

Se aplican [Daily First](https://github.com/cftorre1/Radar-salud/issues/5#issuecomment-6115298820), [poda selectiva](https://github.com/cftorre1/Radar-salud/issues/5#issuecomment-6115358714) y [presupuesto/stop-loss](https://github.com/cftorre1/Radar-salud/issues/5#issuecomment-6115421155). El hook vigente de la rama tiene cron core **09:30 UTC lunes–viernes** y el collector calificado recorre **90 días**. Eso no demuestra ni configura operación Global 7/7 o discovery de sólo 30 días.

**No activar ese hook ni disparar la calificación histórica de 90 días en esta misión.** Se conserva su evidencia, sin ampliar histórico. La optimización de discovery diario a 30 días queda como cambio acotado posterior: parametrizar la ventana real de rutas/control/health/contrato, conservar el inventario anterior de 90 días, probar sólo ese delta y obtener una captura fresca de 30 días. No basta editar un número en config: el collector vigente contiene límites de 90 días. El gate evita que integración y activación se confundan mientras se califica ese cambio.

Plan ejecutable del Commander:

1. Recibir #26 y contrastar QA focal/Reviewer con sus hashes; hacer merge sólo a staging mediante su procedimiento autorizado. Registrar SHA resultante y preservar los receipts/antecesores. Reuters permanece deshabilitado; ningún candidato se publica por merge.
2. Verificar en ese SHA los datos/fuentes Global, igualdad de la colección aprobada y exclusión de Global del denominador LIVE Chile. Reutilizar QA por hash y correr únicamente checks afectados por conflictos del merge. No declarar runtime post-merge por haber pasado la rama.
3. Calificar el cambio de discovery **30 días**, metadata/enlace, sin archivo adicional ni llamadas pagadas. Primero un ciclo vivo completo en staging: URL original → discovery → disposition editorial pendiente/rechazo/aprobación trazable; history/feed sólo si hay aprobación. Capturas con robots/TLS/redirects/Retry-After; 1 solicitud/s, circuito sin rotación de identidad y stop-loss de dos estrategias equivalentes fallidas.
4. Habilitar recurrencia Global **7/7** por el orquestador/dispatch de staging aprobado, con propuesta de horario 09:30 UTC (06:30 Santiago en este corte). No modificar main para lograrlo ni atribuir ejecución al cron de una rama aislada. No aumentar la frecuencia ni presupuesto AI de core. Proponer un límite menor tras medir ese primer poll de 30 días; el techo vigente es 45 min/50 min, no consumo observado ni promesa de coste.
5. Mantener por fuente el **último ciclo diario válido completo**, separado del último job/poll fallido y de publicación material. Watcher: alerta al cumplir 24 h sin ciclo válido y degradación/recovery explícita a 48 h; fuente sana sigue aunque otra falle. Un ciclo sin material nuevo puede ser válido sólo con evidencia suficiente de cobertura. Un HTTP 200 o cero resultados sin cobertura no lo es.
6. Observar un segundo ciclo fresco completo, ID distinto, mismo contrato y al menos **86.400 segundos**. Replay, proyección y resume no cuentan. Un cambio a ventana 30 genera un contrato nuevo y reinicia la prueba; no hereda automáticamente el anchor de 90 días. Cerrar aceptación diaria por fuente con receipts, no por calendario o cron.

El anchor WHO de 90 días es **11 octubre 13:07:31 Santiago**; su siguiente bound de 24 h es **12 octubre 13:07:31**, sólo si sigue el mismo contrato. PAHO tiene cobertura calificada sobre bytes originales; aún necesita una primera captura fresca completa bajo contrato 4 y otra ≥24 h después. Ninguna se ejecutó de nuevo en este turno. La observación archivada tiene unas 9,5/9,3 h de edad de evidencia, **no un ciclo diario nuevo**.

Para observar sin red ni mutaciones canónicas:

```sh
python scripts/check_global_source_freshness.py
```

La observación usa `checked_at` original y distingue fecha/technical/coverage holds, alerta y degradación. No reemplaza el watcher externo ni el receipt de último ciclo diario válido descrito arriba. El workflow guardará observaciones en `data/audits/global_integration_2026_10_11/freshness/<run_id>.json`; sigue pendiente observar esa ejecución en staging.

## Alternativas: una expansión condicionada, sin nuevos conectores

No se halló una alternativa con **acceso, fechas y permiso de automatización comercial acreditados conjuntamente** dentro de este presupuesto. Se implementaron **cero conectores adicionales** y no se abrió otro PR. No se atribuye reemplazo equivalente de la cobertura mundial de Reuters a noticias principalmente estadounidenses o informes de consultoría.

| Fuente | Clase | Superficie / accesibilidad observada | Fecha / derechos | Mantenimiento y próxima acción |
| --- | --- | --- | --- | --- |
| Fierce Healthcare | PILOTO LIGERO, prioridad 1 | [Directorio RSS oficial](https://www.fiercehealthcare.com/fiercehealthcarecom/rss-feeds); feed general y secciones publicadas | MIME RSS observado; fechas de entradas sin verificar. [Questex §2](https://questex.com/terms-and-conditions/) restringe uso comercial; [permisos](https://www.fiercehealthcare.com/fiercehealthcarecom/request-permissions-use-fiercehealthcare-content) | XML potencialmente barato. Antes de probar collector, acreditar alcance metadata/automatización; luego un feed reciente, sin cuerpos/archivo |
| Healthcare Dive | PILOTO LIGERO, prioridad 2 | [RSS en dominio oficial](https://www.healthcaredive.com/feeds/news/), MIME observado | Fechas sin verificar. [Términos Industry Dive](https://www.industrydive.com/terms-of-use) restringen acceso automatizado; excepción RSS comercial no establecida | XML potencialmente barato; aclarar permiso específico, luego validar fecha/link/GUID. No interpretar existencia del feed como licencia |
| Deloitte | PILOTO LIGERO, prioridad 3 | [Center for Health Solutions](https://www.deloitte.com/us/en/insights/research-centers/center-for-health-solutions.html), listado legible pese a aviso JS | Listado no acredita fecha editorial de cada informe; derechos recurrentes no calificados en [ruta legal](https://www.deloitte.com/us/en/legal/terms-of-use.html) | Un informe mensual aportado por editor: fecha original, período/metodología y derechos. HTML multiformato cuesta más; no crawler |
| McKinsey | POSTERGAR | Ruta estratégica conocida; sólo se examinó [política oficial](https://www.mckinsey.com/terms-of-use/) | Recolección de datos requiere permiso escrito; uso limitado no comercial. Sin fetch de contenido/feeds/PDFs tras ese hallazgo | No gastar en reparar acceso hasta acreditar permiso; no automatizar referencias curadas |
| PwC | POSTERGAR | Se examinó [política GX vigente](https://www.pwc.com/gx/en/legal-notices/terms-and-conditions.html), actualizada junio 2026 | Restringe uso comercial, almacenamiento sistemático y extracción sin permiso. No se extrapola a toda member firm ni se reevalúa la referencia US curada | Resolver términos de la ruta exacta; solapamiento estratégico y coste de derechos. Sin fetch nuevo de informes |
| EY | POSTERGAR | [Health Global](https://www.ey.com/en_gl/industries/health) y [índice legal](https://www.ey.com/en_gl/legal-and-privacy) legibles | Fechas de informes health no verificadas en cards; fechas de navegación no sirven; permiso/API no acreditados | Regionalización/HTML y ruido promocional aumentan esfuerzo. Reabrir sólo un informe distintivo fechado aportado por editor |

**IMPLEMENTAR AHORA:** integración del paquete WHO/PAHO ya calificado, con gate diario apagado. Ninguna de las seis alternativas recibe esa clase. Las clases de piloto son recomendaciones condicionadas, no autorización de ingestión ni afirmación de licencia.

El lector web no soporta XML: Fierce tuvo dos intentos equivalentes fallidos y se detuvo; Healthcare Dive tuvo uno, sin retry. No se infiere HTTP/WAF del publisher de esos errores del lector, ni se simulan TLS/robots verificados o fechas de feed. El siguiente piloto permitido usaría una interfaz XML en Actions sólo tras permiso y presupuesto, con un poll limitado; no es otro intento de la estrategia fallida. No se consumió una corrida de investigación/discovery nueva en Actions.

Sin ruta periodística acreditada, fallback de descubrimiento: editor aporta enlace, sin extraer título/cuerpo automáticamente, y descripción original apoyada por primarias independientes; revisión editorial/derechos antes de cualquier uso. Work Editorial decide contenidos; Codex C entrega rutas, límites y provenance. La evaluación complementa las filas `consulting`/`specialist_media` de Work 4; no repite su auditoría editorial.

## Consumo y decisión de continuidad

Hasta el corte previo a la CI automática: cero llamadas a APIs AI pagadas, cero polls WHO/PAHO/Reuters, cero runs Actions manuales, cero backfills, cero suites completas/browser manuales y cero conectores nuevos. Investigación acotada: **5 llamadas al lector web, 8 queries, 10 aperturas directas, 2 clicks y 10 búsquedas internas**; las intenciones no equivalen a HTTP reales, que el proveedor no expone. QA focal inicial 30 PASS y, tras el gate, 33 PASS (<1 s cada corrida), más conservación determinística de hashes. Un Reviewer independiente focal, sin nueva investigación editorial. Tokens/coste de Codex no están expuestos; no se declaran cero ni se inventa una estimación.

Próximos owners: **Integration Commander** — merge, SHA y runtime de staging; **Source Engineering** — ventana diaria 30 y watcher/ciclo; **Work Editorial** — mérito, derechos, consecuencias y publicación; **titular de licencia** — autorización Reuters/alternativas. No se enviaron correos ni solicitudes de permiso a publishers. Issue #5 permanece abierta y PMO Global Implementado: readiness de esta integración no certifica operación diaria, beta o producción.


## Reconciliación del target durante el cierre

Staging avanzó a `88979eb5bfa7497b40a9325536637a2e06d76cdb` con el checkpoint de sprint del Commander. Se incorporó en esta rama aislada mediante merge `704d207`; no se escribió staging. El único conflicto fue un append concurrente de `evidence_catalog` en PMO: se unieron sus entradas, conservando catálogo/changelog y bloques ajenos del target. Las 83 tareas ajenas, los cuatro archivos entrantes y los 18 hashes técnicos/canónicos quedaron exactos. El nuevo checkpoint registra la suspensión histórica de #26 por hook90 sin gate; este candidato ya aporta el gate apagado. No invalida ni rejuvenece receipts previos.

Sólo esa gobernanza requirió siete pruebas PMO adicionales PASS y un suplemento Reviewer focal; no hubo otra suite completa, browser, investigación o poll. [Recibo de reconciliación](../data/audits/global_integration_2026_10_11/staging_reconciliation_88979eb.json); suplemento `data/audits/global_integration_2026_10_11/staging_reviewer_88979eb.json`. El paquete firmado inicial conserva el baseline de su corte; estos recibos posteriores documentan el target real del cierre. Consumo adicional: una revisión del merge, sin IA API pagada ni nuevos conectores.


## CI automática y corrección del límite temporal heredado

Al marcar #26 lista para review, la CI crítica automática [38195490063](https://github.com/cftorre1/Radar-salud/actions/runs/38195490063), HEAD `a44adb9` / merge de prueba `11b65c8`, dio **1.201 Python PASS, 94 subcasos PASS, 1 skip y un fallo**; Node/browser/Reviewer quedaron sin ejecutar. El fallo exclusivo `test_verified_publication_boundary_retains_old_issuance_without_changing_it` se reprodujo en el checkout aislado del staging real `88979eb`: es heredado, no una regresión del gate Global. `curate(as_of=2026-10-11)` filtraba con esa fecha, pero los pulsos consultaban el calendario UTC del runner, ya 12 octubre; julio 13 pasaba de día 90 a 91.

La corrección mínima pasa `today=as_of` a `_sanction_pulses`; si `as_of=None`, conserva la fecha del sistema y la conducta normal. No cambia fechas originales, inventarios, renderer ni datos canónicos. La prueba existente conserva el caso válido de día 90 y verifica también exclusión en día 91. **30 pruebas del exportador PASS**, sin red, IA o reconstrucción de datos; el Reviewer focal se incorpora en `data/audits/global_integration_2026_10_11/ci_boundary_reviewer.json`. El recibo `ci_boundary_qa.json` conserva hashes y la atribución del baseline. Esta corrección requiere la CI automática del nuevo candidato; su conclusión exacta se registra en PR/issue #5, sin equiparar la CI de rama con operación diaria o runtime post-merge.

Consumo posterior al paquete firmado: una CI crítica automática fallida y una nueva CI automática necesaria por el cambio real; reproducción dirigida de un test en staging aislado, 30 tests del exportador y Reviewer focal. Cero nuevas corridas de discovery, expansión histórica, navegador manual, APIs AI pagadas o conectores. Los receipts iniciales permanecen inmutables y describen su corte; no representan esta CI posterior.


## Segunda CI: fixture semanal UTC/Chile heredada

La CI [38196644883](https://github.com/cftorre1/Radar-salud/actions/runs/38196644883) sobre `42f60ab` / merge sintético `18e3ec3` pasó **1.202 Python +94 subcasos, 1 skip**; ambos árboles Git coinciden (`ee45a1652ac66f23d675a556e0616ac1a5104906`). Node pasó 42/43 y falló únicamente `Home V2 specials share read identity and suppress their base signal`; browser/Reviewer automáticos quedaron skipped. El mismo fallo se reprodujo en staging `88979eb`. La fixture usaba hoy UTC (Oct12) mientras el guard correcto valida la publicación contra Chile (todavía Oct11), de modo que la prueba inventaba una fecha futura. No es un defecto de la caducidad del producto.

Se modifica **sólo el test**: el helper VM acepta un reloj opcional (por defecto Date normal); la prueba de identidad usa reloj fijo `2026-10-12T02:30:00Z` y fecha de publicación `2026-10-11`. Conserva todas las aserciones de identidad, lectura y supresión, y los tests independientes de rechazo futuro/caducidad siguen intactos. Los **43 tests Node PASS** localmente sin red (Node24, aislamiento none requerido por sandbox; la CI usa Node22 estándar). UI, health, renderer y datos canónicos conservan sus hashes. [Recibo y TAP](../data/audits/global_integration_2026_10_11/ci_weekly_node_qa.json); Reviewer `ci_weekly_node_reviewer.json`. La conclusión de la CI necesaria del siguiente HEAD se fija en PR/issue #5.

Consumo acumulado de cierre: dos CI críticas automáticas fallidas por defectos heredados distintos, tercera necesaria tras un cambio real; no hubo retry equivalente sin reparación. Sólo QA afectada (30 tests Python/exportador; 43 Node por el helper compartido) y reproducciones de un caso en staging aislado. Sin nuevos polls, histórico, APIs AI pagadas ni navegador/suite completa de producto manual. Los receipts previos quedan como cortes inmutables, no como aprobación del nuevo HEAD.


## Tercera CI: cohorte fija frente a ventana legal que envejece

La CI [38197336548](https://github.com/cftorre1/Radar-salud/actions/runs/38197336548) sobre `0f8f604` / merge sintético `f01f912` pasó **1.202 Python +94 subcasos, 1 skip, 43 Node**. Desktop/mobile: **60 PASS, 2 fallos del mismo caso Fiscalización**; Reviewer automático skipped. El artefacto11723921791 conserva screenshots/traces/web, SHA256 `46c5dbd5ef51aca487690f0646443ec2f0ece92a208dfe61bba9e90481adc901`.

El test exigía75 recientes/17 antecedentes del corte11 octubre. El exportador baseline88979eb también produce72/20 al día12: tres oficios originales emitidos julio13 cumplieron91 días; sus suspensiones permanecen vigentes hasta octubre12. No hubo pérdida ni fecha nueva. La cohorte original de92 registros conservados en history (decision=published en el ledger Alicanto, sin fecha de publicación oficial acreditada) y sus fechas siguen intactas, incluyendo los tres IDs O-02-DFS-02485/02487/02488-2026.

Se corrige sólo ese test desktop/mobile: compara IDs exactos y fechas originales contra el ledger nativo independiente, calcula la elegibilidad30/90 con la fecha del snapshot y verifica por separado antecedentes todavía vigentes desde metadata legal durable. No deriva el esperado del contador/renderer bajo prueba. Las demás verificaciones de oficios, actores, efectos, publicación no acreditada, navegación y layout se conservan; se añade comprobación de emisión/evento originales y publicaciónnull de cada registro.

Las aserciones reales del caso (sin DOM) pasan con snapshots de octubre11 (75/17),12 (72/20) y13 (72/13, suspensiones vencidas excluidas); rechazan oficina faltante, fecha reciclada y publicación inventada. Syntax PASS. No se ejecutó browser local: paquete Playwright existe, binarioChromium ausente; no se intentó instalarlo. [QA/control durable](../data/audits/global_integration_2026_10_11/ci_register_control_qa.json), Reviewer `ci_register_control_reviewer.json`; DOM desktop/mobile exige CI del siguiente candidato.

Consumo acumulado: tres CI automáticas fallidas en capas diferentes y cuarta necesaria tras reparación real. No retry equivalente ciego. Los datos, fuentes Global, temas, renderer, históricos y18 hashes protegidos siguen exactos. Cero polls, histórico adicional, APIs AI pagadas o suite completa/browser manuales. Los dictámenes anteriores conservan su corte; el resultado final del candidato se registra en PR/issue #5 sin generar otro commit documental que repita CI aprobada.
