# Daily First · FONASA, ISP/ANAMED y MINSAL

PR [#29](https://github.com/cftorre1/Radar-salud/pull/29), rama `codex/daily-first-fonasa-isp-minsal-20261012`, creada desde staging `515b8809ecc391600c4093ce0435955d7d3685c5`. No hubo merge ni escritura en staging/main/producción. El SHA final y sus gates exactos se registran en el PR y el checkpoint de issue #5 después de CI; los archivos de este handoff quedan congelados antes de ese CI.

## Resultado efectivo

| Superficie | Captura/resultado | Estado |
|---|---|---|
| MINSAL Noticias | RSS oficial10 +10 originales legibles; 3 publicaciones dentro72h. Cuatro pendientes:3 aceptados/history/feed,1 rechazo específico,0 diferidos. | OPERATIVE_DEGRADED |
| FONASA Noticias | GET oficial403, servidor AWS ALB; sin inventario editorial verificable. | EXTERNAL_BLOCKER_PROVEN |
| FONASA Datos Abiertos/Noticias | GET oficial403 ALB. No confundir catálogo nacional histórico con noticias actuales. | EXTERNAL_BLOCKER_PROVEN |
| ISP/ANAMED Alertas | DNS/TCP funcionan; verificación TLS falla por cadena/local issuer en `.cl` y alias `.gob.cl`. | EXTERNAL_BLOCKER_PROVEN |
| ISP Vigilancia | Mismo fallo TLS en las dos autoridades oficiales. No sustituir período epidemiológico por publicación. | EXTERNAL_BLOCKER_PROVEN |

El corte nativo es 12-oct-2026 04:42:56 UTC (01:42 Chile); prioridad72h y límite30d. Los diez posts MINSAL del RSS van del2 al9 de octubre. **No es un censo exhaustivo30d** ni prueba de ausencia en otras superficies. FONASA/ISP: conteos de publicaciones recientes/materiales **desconocidos**, no cero. MINSAL tiene tres recientes verificadas en la superficie acotada. No se hizo backfill90d.

## Cuatro pendientes y materialidad

| Publicación original | Acto/consecuencia | Score oficial | Decisión |
|---|---|---:|---|
| 09-oct20:48:24Z | Nuevo acelerador lineal en Hospital Las Higueras, Biobío; capacidad oncológica regional. Costo/capacidad adicional exacta no publicados en el original. |78|Publicado BACKFILL|
| 09-oct20:02:50Z | Vacunación en zonas afectadas por lluvias y continuidad público-privada; dos traslados UC CHRISTUS→Hospital Metropolitano. Medida temporal/local, no cambio estructural nacional. |68|Publicado BACKFILL|
| 09-oct19:00:44Z | Laboratorio ambiental de Tarapacá: $6.000millones ($4.000infraestructura+$2.000equipamiento), capacidad local de análisis y vigilancia. |78|Publicado BACKFILL|
| 08-oct22:28:18Z | Monitoreo inicial por aluvión; no informa daños sanitarios relevantes, evacuaciones efectuadas, financiamiento ni afectación comprobada de atención. |62|Rechazado:62<65|

Gate oficial65 y controles de calidad/publicación existentes intactos. Scores del radar65/62/65 conservan sus diferencias respecto de relevance_score78/68/78. Tres señales en history y radar histórico no equivalen a tres señales LIVE ni a promoción por volumen. Las tres conservan publicación9Oct, detected_at10Oct22:15:44Z y BACKFILL. El ledger conserva razones y hashes del cuerpo propio. No se inventaron vigencias, resoluciones, montos ni fechas del incidente.

## Reparaciones implementadas

RSS público `https://www.minsal.cl/category/noticias/feed/` acepta MIME XML real y restringe autoridad/redirecciones HTTPS. Los originales se ligan por canonical, sello propio `article:published_time` y cuerpo Elementor; navegación, recomendaciones y dateModified no fechan ni resumen la noticia. RSS/detalle deben concordar. El día y lane usan calendario Chile, incluyendo medianoche UTC. Si falla RSS se recuperan hasta4 detalles ya pendientes; no se recorren los primeros enlaces de navegación.

La cola rehidrata los pendientes por URL preservando clave, detected_at, lane y decisiones terminales. La ausencia de evaluación IA se difiere con razón; no publica por keywords. El transporte scoped persiste fallos por superficie, comparte `www`/bare de un mismo dominio, conserva alternativas oficiales independientes y abre circuito tras dos fallos equivalentes. Cooldown24h, un sondeo de recuperación, TLS/proxy intactos. Los aliases ISP con una sola observación se distinguen de los aliases con dos; su hold externo está explicado, sin inventar contadores.

`source_health` separa intento, captura, discovery verificado, selección y evaluación. Registra páginas, discovered/unique/recent/material, publicados, rechazo, diferidos, parse_errors, coverage_complete/reason y edades24h/48h. Los inventarios bloqueados quedan null; un hold no renueva checked_at. El observer diario es sin red y se preserva como artefacto aun si el collector falla. El cron heredado del piloto es lunes–viernes; no se amplió ni se declara vigilancia7/7. Integration Commander debe calendarizar/verificar un observer diario autorizado y dos ciclos reales separados por24h antes de elevar recurrencia.

## Pruebas y evidencia

- Preflight real [38202905547](https://github.com/cftorre1/Radar-salud/actions/runs/38202905547): FONASA403; ISP TLS; listing/RSS/4 originales MINSAL200. ZIP durable SHA256 `472632895bf744caa0e3cd4760df08e2eb6967426834140e7f8c984653df2c9d`.
- [Runtime real38204748188](https://github.com/cftorre1/Radar-salud/actions/runs/38204748188), código `6b6ef2c6a83d8244b0338598b393760709ef0dae`: descubrimiento nativo,4 evaluaciones y replay, PASS. Reviewer read-only independiente:findings[]. ZIP durable SHA256 `f55065b15fa709aba48c831618a1cef0c2b0067fce584a98ba485dccd2c5669a`.
- Replay final sobre stock asentado:0 requests/0 IA, cola/history/usage estables y Reviewer PASS. CI posterior reutiliza originales exactos y no renueva timestamps nativos.
- QA focal Python58 de integración,79 de integridad pública y42 después de reloj Chile. Desktop/mobile específico2/2 PASS, con capturas. Reviewer global local:0 hallazgos. QA global del HEAD final sigue requerida; resultado exacto en PR/issue5.
- Fallos **introducidos**, ya reparados: MIME RSS rechazado/fallback navegación; fixture histórica Pulso acoplada a módulos actuales; writer health sustituido en test no crea archivo. Corrida RSS38203992099 y QA38203992061 quedan FAIL, no reetiquetadas.
- Baseline/preflight QA38202905475 PASS con sus gates originales. No se atribuyen esos fallos nuevos a baseline. Los tests de receipts Pulso ahora leen el productor aceptado `4a05c276` con hashes, políticas, stock, presupuesto y controles negativos intactos; el verificador y gates productivos no se modificaron. Esto no certifica un nuevo runtime Pulso sobre la rama Daily First.

Preservación comprobada:7047 registros de cola ajenos a las4 recuperadas;992 history previas;165 señales previas;22 health ajenos;86 tareas existentes. History995 y feed168. Queue/PMO agregan sólo seguimiento propio. ZIP, ledger, checkpoint, reviewer y QA están en `data/audits/daily_first_20261012/`.

Consumo API:4FAST(gpt-5.6-luna),0DEEP,4867tokens; ledger520→524FAST/14DEEP. Cuatro response_id reales, prefijo anterior intacto. USD no calculable:pricing_not_configured. No se midió costo de la sesión de chat ni facturación Actions. Fueron3 capturas nativas:preflight, fallo MIME y recuperación verificada; las verificaciones posteriores son replay sin fuentes/IA. Logs/recibos preservan los fallos de configuración local de browser y su corrección; no son pruebas de producto aprobadas.

## Acción exacta de integración y límites pendientes

1. Integration Commander verifica SHA final de PR29, mergeability contra staging vigente y todos los checks. Integra mediante merge commit a staging únicamente; no squash/rebase que pierda la ascendencia pagada de Pulso. Este frente no ejecuta ese merge.
2. Ejecuta core restringido a MINSAL y observer `python scripts/check_daily_first.py --output artifacts/daily-first-freshness.json` en staging. Las4 terminales no deben reevaluarse ni generar llamadas nuevas; history/feed deben conservar995/168 o los deltas concurrentes explícitos.
3. Mantiene MINSAL degradado hasta recurrencia24h y conciliación del perímetro adicional. No ampliar este frente a90d. Mantiene FONASA/ISP bloqueados; respeta holds/cooldown.
4. Blocker humano mínimo: FONASA debe habilitar GET público autorizado o export/feed oficial actual, con fechas/cuerpos; ISP debe servir cadena TLS completa verificable o un feed/export oficial accesible. No desactivar TLS, evadir ALB/WAF ni habilitar credenciales.

Alternativas ya revisadas del PR13 se reutilizan: datos.gob.cl tiene14 registros FONASA históricos, no newsroom actual; documentos DIPRES/MINSAL conservan su publicador. Rutas ISP/ANAMED Noticias `https://ispch.cl/categorias-noticias/noticia-anamed/` y detalle oncológico1Oct están indexados: son pistas sin captura primaria nativa y se difieren bajo bloqueo TLS; no se convierten en alertas farmacológicas ni señales publicadas. Issue5 y los gates maestros siguen abiertos.

## Conciliación de staging vigente

Staging avanzó a `c10f67812face5a62a30623d6eb418418ab0994b` integrando PR26/16/28/30. Se incorporó a esta rama sin merge a staging. Conflictos exactos:workflow diario,queue,PMO yfixturePulso. Se conservaron los pasos/política Global de staging y el observer Daily First; todas sus tareas y health ajenos; PMO como unión; y su fixture histórica optimizada con prueba negativa de módulo nuevo. Engine conserva `eligible_daily_item`30d, home30/60 yGlobal por mérito sincuota. Nuevas validaciones usan replay primario retenido, sin otra captura o modelo. El SHA final de conciliación y sus gates sustituyen b5ca6c35 en el PR/issue5.
