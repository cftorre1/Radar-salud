# Work 4 P0 · implementación y calificación real

Rama `codex/w4-market-intelligence-expansion-20261011`; PR #16. Inicio desde staging `4ff51cf`; sincronizaciones aisladas con staging `78c3274`, `3dd964e`, `9762a11` y `ac6b31a`, preservando la integración DF/SIS/SUSESO. No se modificaron main, producción ni la rama staging.

Los tres paquetes terminan **OPERATIVE_DEGRADED**. Hay colectores ejecutados, inventarios reales, consumidores y candidatos editoriales. No se certifican recurrencia, exhaustividad de todo el ecosistema ni activación editorial. Ningún paquete requiere credencial o licencia para las superficies implementadas.

| Paquete | Inventario inicial | Disposición |
|---|---|---|
| Isapres | 10 códigos oficiales; 7 abiertas, 3 cerradas; 8 meses y 320 observaciones comparables | Datos para Benchmark/Trend; 0 noticias por fila |
| CMF | 6 identidades verificadas por RUT; 4 emisores vigentes, 2 históricos no vigentes; 9 hechos esenciales en 90 días y 3 en 30; 24 documentos contables (8 EEFF, 8 análisis razonados y 8 hechos relevantes) y 42 celdas financieras únicas | 5 eventos materiales; 7 documentos diferidos y 2 soportes rechazados como cards adicionales; 0 publicados |
| DIPRES | 116 documentos de Salud parseados; 408 observaciones; Proyecto 2027 y ejecución acumulada 2026 | 5 cambios de asignación materiales diferidos; 0 noticias por fila |

## Fuentes y contrato ejecutable

- SIS: `https://www.superdesalud.gob.cl/registro/isapres/` y publicación de cartera 2026; el Excel se descubre desde el release, no desde una ruta mensual fija.
- CMF: identificación pestaña 1, búsqueda POST de hechos esenciales pestaña 25, estados financieros pestaña 3, accionistas pestaña 5. Se preservan `row`, RUT y vigencia oficiales y se serializan consultas; una pestaña de calendario no prueba EEFF publicados. La pestaña 33 devuelve «información solicitada no disponible» para junio 2026: no se presenta como cero filiales.
- ILC: tabla primaria de propiedad `https://ilcinversiones.cl/nuestras-empresas/`, separada de resultados consolidados. Consalud 99,9% está explícitamente identificada; una incorporación histórica no se convierte en fecha de control efectivo.
- Identidades bursátiles: renta variable del emisor ILC, transacción oficial de Bolsa para CLC y nómina de market makers de Bolsa fechada 07/10/2026 para INDISA. Se conserva la fecha de referencia; no se inventan precio ni cotización actual. CLC conserva la salvedad de referencia bursátil histórica de 2025.
- DIPRES: índices oficiales de Proyecto 2027 y ejecución 2026 para Salud/FONASA/subsecretarías. Las rutas globales alternativas permiten obtener los documentos cuando un índice específico devuelve «Página no encontrada» dentro de HTTP 200.

`config/source_expansion_runtime.json` contiene los endpoints. `scripts/probe_source_expansion.py` guarda HTTP, redirects, verificación TLS, WAF/proxy, cuerpos, hashes y timestamps UTC. Los períodos y fechas para el usuario se interpretan en America/Santiago. La búsqueda CMF refresca su ventana de 90 fechas; la selección de trimestre no se convierte en fecha de publicación. El discovery tiene profundidad y cupos explícitos; jamás certifica exhaustividad por HTTP 200.

```bash
python -m radar_salud.market_sources --capture-dir CAPTURA --output-root SALIDA_AISLADA
python scripts/validate_market_source_runtime.py --capture-dir CAPTURA --output CALIFICACION_AISLADA
python scripts/poll_market_sources.py --output work/market-polls
```

El último comando implementa discovery diario, conserva el stock del último poll calificado y omite llamadas cuando no corresponde por cadencia. `--force-qualification` permite una captura adicional, pero no convierte capturas próximas en recurrencia validada. No hay cron de producción habilitado. El workflow del PR ejecuta captura, adapters, replay y Reviewer en artefactos aislados, con permiso `contents: read`.

## Modelo, stock y consumidores

- `data/entities/isapres.json`: código, nombre legal/comercial, alias, abierta/cerrada, vigencia observada y evidencia de grupo. `build_signal` reutiliza `EntityRef.canonical_id` en cualquier fuente. Una matriz CMF no atribuye automáticamente señales a Isapres mencionadas en su texto.
- `data/market/isapre_portfolio.json`: período del dato agosto 2026 separado del release 02/10/2026; enero–agosto reconcilian totales. Beneficiarios agosto: **2.486.683**. Benchmark separa abiertas y cerradas y usa un denominador del mismo mes.
- `data/entities/cmf_reporting_actors.json`: RUT validado con dígito, vigencia CMF, relación matriz/filial demostrada y ticker con fuente. Banmédica S.A. histórica se distingue de Isapre Banmédica, código 99.
- `data/market/cmf_disclosures.json`: identidad estable por RUT+número oficial; URL/token de descarga no identifica el evento. Se conservan primera detección y stock ante consultas parciales.
- `data/market/cmf_events.json`: cinco episodios con etapa, actor, importe cuando existe, efecto, fechas y hashes primarios. Una junta prevista no es operación aprobada; suscripción potencial no es recaudación; oferta no vinculante no es adquisición cerrada. Los documentos de soporte no crean cards adicionales.
- `data/market/cmf_financials.json`: intervalos YTD/trimestre, unidad CLP miles, emisor y perímetro. En ILC, ingresos no aseguradores/no bancarios se distinguen del resultado del holding completo; no se comparan como ingresos de Consalud ni como ingresos totales del ecosistema salud.
- `data/market/dipres_health_budget.json`: Partida, subpartida cuando corresponde, Capítulo, Programa, año fiscal, intervalo, moneda/unidad, estado presupuestario y base de precios. No se suman jerarquías anidadas ni programas financiados con transferencias entre sí. Un poll parcial conserva registros y evidencia anteriores.
- `data/market/market_intelligence.json`: consumidor ejecutado con vistas Benchmark y observaciones Trend comparables. `signal_candidates.json` conserva candidatos diferidos para la ruta editorial. No genera señales chilenas por un tema Global ni altera los gates canónicos de Trend.

FONASA **16.02.01**, proyecto 2027: **16.223.541.378 miles de CLP**. Comparación con ley 2026 expresada a precios de 2027: base **15.486.965.742**, diferencia **736.575.636 miles de CLP**, **4,7561%**. La ejecución de agosto de ese comparativo y la ejecución de julio a nivel de capítulo son observaciones distintas; no se restan para inventar un flujo mensual.

## Materialidad y health

CMF: cierre de capital CLC por CLP80.119.759.016; propuesta RedSalud/Vida Cámara con capital no dinerario; opción preferente INDISA; bono INDISA colocado UF1.000.000; oferta Bionet condicionada a contratos y aprobaciones FNE/SUSESO. La revisión aplica sólo si coinciden número, RUT, fecha del índice y hash del PDF. Cambiar cualquiera invalida la revisión.

DIPRES: umbral inicial de candidato ≥2% y ≥CLP10 mil millones en una base de precios compatible. Los cinco candidatos no se publican sin fecha de publicación verificada. Período fiscal, corte acumulado, fecha de generación y `fetched_at` no sustituyen `published_at`.

`source_health` registra páginas, descubrimientos, únicos, recientes, materiales, publicados, rechazados, diferidos, errores, coverage_complete/reason y resultados de datos. **Recencia desconocida = null**, con motivo, para registro Isapres y PDFs DIPRES. No significa cero novedades. Los tres mantienen cobertura parcial y warning, aunque los endpoints respondan 200 y el parser termine sin error.

## QA y evidencia durable

El runtime nativo #38144418936 ejecutó los tres adapters, replay idempotente y Reviewer separado que concilia las filas CMF, códigos Isapres y total primario FONASA. El runtime #38145221551 agregó períodos de filiales e identidades de Bolsa, también PASS. Sus stocks y revisiones son artefactos aislados; los ZIP primarios y los índices necesarios se preservan en `data/audits/source_expansion/`, con hashes en los informes.

La primera base local tenía un fallo Python (11 actos Normativa frente a ≥12) y fallos browser de snapshots sin regenerar. Se reprodujo el fallo Python en la base `4ff51cf`. Staging corrigió la conciliación Normativa durante la integración DF/SIS; después de sincronizar, el workflow global **#38144418999 pasó tests, QA desktop/mobile y Reviewer**, sin cambios de gates en este PR. Los browser locales sobre el snapshot sin regenerar se registran por separado; el workflow global usa el proceso normal de build y export antes de QA.

El Reviewer de cobertura usa parser independiente de filas originales y comprobaciones de archivos/hash; el Reviewer global es el determinístico existente. No se solicita aprobación humana ni se presenta esa revisión automatizada como revisión humana.

## Brechas y siguiente paso

- Isapres: resolver contradicción documental Ltda./SpA de Isalud y fecha societaria efectiva; completar relaciones de control demostrables y monitoreo de redes/planes. El directorio vigente no acredita fechas de cambios legales.
- CMF: ampliar emisores sanitarios fuera del perímetro inicial, resolver estados independientes de filiales mediante alternativas oficiales y revalidar referencias bursátiles históricas cuando corresponda. Los estados consolidados públicos son una alternativa disponible; no autorizan atribuir automáticamente importes a una filial.
- DIPRES: completar stock de versiones/períodos fuera del inventario inicial y obtener una fecha oficial de publicación ligada a cada candidato antes de publicar.
- Los tres: segunda ejecución real al menos **24 horas** después del poll calificado; las capturas de esta sesión no cumplen esa separación. La ruta diaria es ejecutable pero no está activada en producción.
- Activación: siguen vigentes las dependencias Work 4 `source_audit_issue5_iteration1_recovery_2026_10_09` y `source_audit_issue5_iteration2_balance_2026_10_09`. No se elevan a active ni se publica BACKFILL como LIVE.

Queue y PMO conservan estados de otros frentes y las tareas P0 en progreso con outcome OPERATIVE_DEGRADED. PR #16 e issue #5 contienen el checkpoint y el siguiente paso. No existe EXTERNAL_BLOCKER_PROVEN para estos paquetes: GitHub Actions sí accedió a las superficies públicas implementadas.

Calificación de código `a1a3a9c`: [runtime nativo #38146456406](https://github.com/cftorre1/Radar-salud/actions/runs/38146456406), 31 tests dirigidos, adapters/replay/Reviewer PASS (302 comprobaciones). [QA global #38146456378](https://github.com/cftorre1/Radar-salud/actions/runs/38146456378): 980 Python PASS/1 SKIP, 42 Node PASS, 56 browser desktop/mobile PASS, Reviewer sin hallazgos. Esta calificación histórica no certifica commits posteriores. Los fixes `aa40c05` y `2ff2c81` corrigen fallos de health: actualizan el slug canónico con errores visibles y conservan el último ledger presupuestario validado cuando un parser nuevo falla. El poll fallido queda registrado por separado. Sus pruebas positivas y adversarias elevan la suite dirigida a 32 casos.


Última calificación de código `82c50e5`: [runtime nativo #38148318253](https://github.com/cftorre1/Radar-salud/actions/runs/38148318253), **32 tests dirigidos PASS**, tres adapters, replay idempotente y **Reviewer de cobertura PASS (302 comprobaciones)**. [QA global #38148318249](https://github.com/cftorre1/Radar-salud/actions/runs/38148318249), merge de PR `0de65d2`: **1.039 Python PASS/1 SKIP, 42 Node PASS, 60 browser desktop/mobile PASS y Reviewer findings=[]**. Cero fallos introducidos observados; el warning de marca pytest no registrada pertenece al test rápido heredado. ZIP finales de runtime e índices verificados por SHA-256 y preservados, junto a los primarios iniciales, en `data/audits/source_expansion/`. La calificación de estos inventarios mantiene las tres fuentes OPERATIVE_DEGRADED y no certifica recurrencia de 24 horas.


## Integración acotada · PR #16

El paquete seguro queda **READY_FOR_INTEGRATION**, separado de los tres estados de fuente **OPERATIVE_DEGRADED**. Se reconcilió staging `bc723e0` y su checkpoint de gobernanza `88979eb` mediante merges dentro de la rama del PR; el segundo no cambia código ni datos de fuentes. El único conflicto explícito era `config/pmo_baseline.json`: se conserva íntegro el PMO de staging y se agregan exclusivamente la evidencia/changelog P0 propios. Queue y health se combinaban automáticamente y se verificaron por registro. Los inventarios `data/entities` y `data/market` permanecen byte por byte iguales al HEAD `0339dd2`; las fechas ambiguas siguen sin resolución inventada.

Calificación local: **45 tests focales PASS**, adapters sobre capturas conservadas, **replay idempotente y Reviewer separado PASS, 264 comprobaciones/9 hechos CMF**. El replay reconstruye los inputs necesarios por hash desde archivos versionados; los 38 PDFs contables/corporativos auxiliares no conservados en esos ZIP se enumeran explícitamente y no se presentan como verificados de nuevo. Los estados/celdas financieras se sustentan en HTML oficial retenido; los 9 primarios CMF y 116 documentos presupuestarios usados sí están presentes. El runtime nativo y QA del HEAD `0339dd2` siguen siendo evidencia histórica, no nueva captura.

Los PRs reutilizan evidencia guardada por defecto. Una captura nueva sólo es posible mediante workflow_dispatch con `capture_fresh=true`; no se solicitó en este frente. Los gates globales y el Reviewer existente no cambian. La CI obligatoria debe pasar sobre el HEAD final antes de fusionar; su recibo final se registra en PR #16 e issue #5.

Presupuesto adicional de recuperación: **0 solicitudes a fuentes, 0 llamadas pagadas del pipeline, 0 auditorías nuevas, 0 credenciales/servicios**. Los archivos de uso AI y cola editorial son idénticos a staging; no se declara un importe monetario de Actions o del chat que no está disponible. Evidencia y hashes: `data/audits/w4_p0_integration_readiness.json`.

Recurrencia ≥24 horas, forma legal efectiva Isalud, control/redes, perímetro CMF/filiales y versiones/fechas DIPRES se posponen como subalcances explícitos. Mantienen las fuentes degradadas y los candidatos diferidos, sin bloquear la integración del paquete de datos seguro ni elevar el readiness global.

Acción exclusiva del Integration Commander: comprobar HEAD de PR #16, base staging, checks obligatorios verdes y ausencia de conflictos; efectuar **merge commit con HEAD coincidente**, registrar SHA real de staging y verificar allí el replay/QA sin activar fuentes. Esta sesión no ejecuta merge, runtime post-merge ni promoción.


CI previa al cierre `b7306cd`: replay **PASS** (32 tests y 264 checks), pero QA global falló con **1.038 PASS/1 FAIL/1 SKIP** al cambiar el día del host UTC. El fallo se reprodujo en staging `88979eb`: el test pedía corte 11/10 y el agrupador de sanciones usaba el reloj 12/10. Se corrige exclusivamente pasando `as_of` al agrupador; sin parámetro explícito, conserva el reloj real previo. El test mantiene la emisión 07/07 y publicación 13/07, verifica inclusión con corte 11/10 y exclusión con corte 12/10 bajo host fijado al día 12. **75 pruebas focales PASS** después de la corrección. No se rebajan ventanas/gates, no se cambian fechas/registros ni se repite investigación. El FAIL original y la prueba de baseline se conservan en el recibo de integración; se valida una vez el HEAD corregido.


El siguiente HEAD `3c552fc` confirmó **1.039 Python PASS/1 SKIP**, pero apareció un segundo fallo distinto de baseline: **41 Node PASS/1 FAIL**. El fixture de identidad Home usaba día UTC 12/10 mientras en Chile seguía siendo 11/10; el gate de frescura rechazaba correctamente esa fecha futura. Se reprodujo con 41/1 en el worktree baseline y se corrige sólo el reloj/día del test: queda fijo en 12/10 01:30Z con publicación sintética 11/10, preserva todas las aserciones de identidad y añade rechazo explícito del día 12 futuro. **42 Node PASS**. El JS del producto y sus umbrales no cambian. Son dos fallos distintos con diagnóstico/progreso, no dos retries equivalentes; sus FAIL originales permanecen registrados.
