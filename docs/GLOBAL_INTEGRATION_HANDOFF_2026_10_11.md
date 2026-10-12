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

Se reutiliza la QA aprobada del código `aee4ed3`, [run 38156977778](https://github.com/cftorre1/Radar-salud/actions/runs/38156977778): 1.178 Python, 184 dirigidas +94 subcasos, 43 Node, 12 desktop/mobile, replay y auditor independiente PASS. Son receipts del código/superficies sin cambio, no una nueva suite sobre todo el HEAD actual. No se repitió la suite completa ni navegador: no cambió UI, contenido curado ni health público. Los límites históricos de baseline y UI Lite siguen en [el contrato original](GLOBAL_SOURCE_DISCOVERY_2026_10_11.md). El Reviewer nuevo cubre únicamente código/gate/documentación/gobernanza nuevos y conservación de evidencia previa.

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

El lector web no soporta XML: Fierce tuvo dos intentos equivalentes fallidos y se detuvo; Healthcare Dive tuvo uno, sin retry. No se infiere HTTP/WAF del publisher de esos errores del lector, ni se simulan TLS/robots verificados o fechas de feed. El siguiente piloto permitido usaría una interfaz XML en Actions sólo tras permiso y presupuesto, con un poll limitado; no es otro intento de la estrategia fallida. No se consumió una corrida nueva en Actions.

Sin ruta periodística acreditada, fallback de descubrimiento: editor aporta enlace, sin extraer título/cuerpo automáticamente, y descripción original apoyada por primarias independientes; revisión editorial/derechos antes de cualquier uso. Work Editorial decide contenidos; Codex C entrega rutas, límites y provenance. La evaluación complementa las filas `consulting`/`specialist_media` de Work 4; no repite su auditoría editorial.

## Consumo y decisión de continuidad

Este turno: cero llamadas a APIs AI pagadas, cero polls WHO/PAHO/Reuters, cero nuevos runs Actions, cero backfills, cero suites completas/browser repetidas y cero conectores nuevos. Investigación acotada: **5 llamadas al lector web, 8 queries, 10 aperturas directas, 2 clicks y 10 búsquedas internas**; las intenciones no equivalen a HTTP reales, que el proveedor no expone. QA focal inicial 30 PASS y, tras el gate, 33 PASS (<1 s cada corrida), más conservación determinística de hashes. Un Reviewer independiente focal, sin nueva investigación editorial. Tokens/coste de Codex no están expuestos; no se declaran cero ni se inventa una estimación.

Próximos owners: **Integration Commander** — merge, SHA y runtime de staging; **Source Engineering** — ventana diaria 30 y watcher/ciclo; **Work Editorial** — mérito, derechos, consecuencias y publicación; **titular de licencia** — autorización Reuters/alternativas. No se enviaron correos ni solicitudes de permiso a publishers. Issue #5 permanece abierta y PMO Global Implementado: readiness de esta integración no certifica operación diaria, beta o producción.
