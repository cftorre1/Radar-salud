# WORK 5 · Product & Editorial Director

Paquete v2.0 · 12 octubre 2026 · destino inmediato: Work 6; después de aceptación de Dirección, Codex H único y Work 3 Integration Commander.

**Autoridad vigente: Addendum Final V2 al final de este archivo. Sustituye el prompt de §7 y cualquier orden incompatible; conserva los siete entregables originales.**

**Dictamen: implementar primero navegación/lectura y profundidad editorial; ampliar selectivamente después.** Este handoff especifica trabajo, no acredita su implementación. No publica señales, cambia configuración activa, fusiona PR ni toca main/producción.

## 1. Base verificada y conciliación

Staging consultado directamente: `ef8cbe3938623d493872ff5f3e717153f176d1be`. Checkout y revisión sobre ese SHA. Sin AGENTS.md en el árbol. Issues #5–#9 y comentarios leídos; queue, PMO, learning ledger, contratos, código de presentación, stock y handoffs revisados. Las observaciones antiguas de esos issues no se presentan como estado actual.

- PR28 integrado: merge `edbedf86b728e44bf3942c4c9a41495aa75818d1`, head documental reconciliado `af6c4538b76b78ee59c7b784c08f0a1288eb8c69`. Su decisión de Global sin cuota numérica se mantiene; la recomendación de San Carlos se reevalúa abajo.
- Preview [38208484632](https://github.com/cftorre1/Radar-salud/actions/runs/38208484632), SHA ef8cbe39: estado GitHub success verificado. 3.844 Python, 46 Node, 68 browser y Reviewer PASS son resultados reportados por Commander en [cierre](https://github.com/cftorre1/Radar-salud/issues/5#issuecomment-6118791722), no pruebas repetidas por Work5.
- PR29: HEAD `1d9ce05854807f545dd7aaf0ab38bd5de7b1f468`, abierto, no fusionado; API lo muestra no draft y mergeable. Su descripción dice READY, pero el cierre posterior de Commander mantiene NO MERGE por separar edad de validación/intento y captura válida vacía/bloqueo. La discrepancia no se resuelve eligiendo el estado favorable. Dueño: Commander y Builder PR29; conservar hold hasta evidencia del arreglo sobre SHA exacto. Las tres señales MINSAL de esa rama no se contabilizan como staging.
- 165 registros en `web/data/radar_today.json`; 68 con `event_date` entre 13-sep y 12-oct inclusive: Pulso23, DF12, SUSESO11, MINSAL11, SIS6, ACHS2 y uno de Clínicas de Chile/Andes/RedSalud. Es un inventario de registros por campo heredado, no 68 acontecimientos independientes ni certificación de todas sus fechas. UI mostró 69 tarjetas y estado local 67 no leídas; incorpora piezas especiales y criterios de presentación, no usar ese total como tamaño del feed.
- Global exporta 10 temas; se conserva la regla sin máximo editorial. Weekly actual anclado al 10-oct; caduca al comenzar 17-oct en Chile. No renovar por fecha de generación.
- Se revisaron las 68 filas mediante controles de texto y selección adversarial; lectura profunda con originales de los tres casos obligatorios. No se afirma auditoría semántica completa de 68 textos. Alertas adicionales: atribución doble «Según… Según…»; ELEAM y certificación de discapacidad repetidos entre emisor/prensa; titular original concatenado al editorial. Similitud léxica sólo orienta revisión y no prueba redundancia.

**Conciliación de contratos:** este mandato de Dirección reemplaza el formato público obligatorio what/why, no los umbrales de materialidad, neutralidad, derechos, evidencia ni vigencia. No se sobrescriben `orchestrator_queue.json`, `pmo_baseline.json`, ledger, revisiones pagadas o contratos activos en este PR documental. El Builder añadirá versión nueva con lectura compatible, no borrará pruebas incómodas ni resultados históricos. PR28 seguirá como antecedente, con este delta explícito.

## 2. Decisiones interdisciplinarias concretas

|Perspectiva|Decisión que cambia el producto|
|---|---|
|Producto y UX|Una misma ficha por identidad; título y Más info resuelven el mismo destino. Abrirla correctamente marca leído; fallar no marca.|
|Diseño de información|Bandeja breve, título completo, fecha/fuente; síntesis sólo con valor adicional. Quitar scroll interno rígido y recortes de medias filas.|
|Edición ejecutiva y periodismo sanitario|No rellenar dos bloques obligatorios. Hechos incrementales y atribución precisa; primera experiencia no equivale a programa clínico consolidado.|
|Estrategia y economía sanitaria|Materialidad es criterio de selección interno, no obligación de inventar un impacto empresarial. Separar presupuesto propuesto, gasto ejecutado y bases.|
|BI y datos|Cada cifra conserva unidad, universo, período, base y procedencia; agrupación por acontecimiento, no por parecido de títulos.|
|Ingeniería de fuentes|Reutilizar conector Clínicas de Chile; como máximo dos adaptaciones nuevas, candidatas y condicionadas a acceso/derechos.|
|QA independiente|PASS estructural no es aprobación editorial. Revisor del texto final distinto de su redactor y evidencia vinculada a versión.|

No se crean ocho agentes/comités permanentes ni ocho llamadas por señal. Extracción y verificaciones determinísticas una vez; un editor integra; un revisor independiente se activa para candidatos a portada, Insight, Global y cambios de alto riesgo. Especialistas de datos/clínica/legal sólo por señales que lo requieran.

## 3. UX final

Contrato exhaustivo en el anexo A. Resumen normativo de aceptación:

1. Dos acciones principales por elemento Ponte/Global: sobre y **Más info**. Título completo clicable al mismo destino. Sin Contexto general/de la señal ni salto intermedio al feed. Compartir y documentos quedan en ficha; utilidades existentes del feed no necesitan rediseño fuera de alcance.
2. Sobre cerrado = No leído; sobre abierto = Leído. Es representación del estado, no de la acción futura. Nombre accesible de acción y descripción de estado, icono decorativo; no depender de color. El mismo componente en Home, Global y feed.
3. Lectura compartida con identidad estable y actualización inmediata del documento y pestañas del mismo navegador/origen; refresh y vuelta atrás preservan. Sin promesa entre dispositivos. Evitar reescritura de Sets obsoletos.
4. Al leer, desaparece sólo de pendientes; permanece en feed. Al revertir, vuelve una vez respetando filtros/orden. Mostrar confirmación discreta accesible y foco siguiente; ficha abierta no se cierra al remover fila.
5. Noticias, Insight y Global usan el mismo resolver, con presentación de ficha existente reutilizada. Ningún elemento promovido puede ofrecer Más info que simplemente reformule su título. Registros históricos limitados conservan acceso a su fuente y limitación honesta.
6. Identidad de pieza y de evento separadas: no marcar un análisis adicional leído por leer su noticia de base. Sólo superficies de la **misma pieza** sincronizan. Cambios de copy no reinician lectura; corrección de fecha requiere alias del ID previo.
7. Desktop1440×900 y móvil390×844: título legible completo, objetivo táctil44px, teclado/foco/Escape correctos, contraste normal4,5:1; comprobación320px/zoom200%. Paginación o expansión conserva todas las elegibles y no impone cuota Global.

**QA real Work5:** navegación desktop del sitio staging; clic en Félix bajó al feed y marcó leído sin abrir ficha, luego se restauró no leído. Global mostró encabezados genéricos y acordeón. No se ejecutó nuevo QA visual móvil: se define para Builder y se distingue de los 68 browser PASS históricos. No se necesitan más pruebas del comportamiento viejo.

### Decisión final de persistencia y migración (cierra alternativas del anexo A)

Decisión cerrada: un pequeño almacén IndexedDB `alicanto_read_v3`, object store por `piece_id`, con valor explícito `{read:true|false}` y un registro de versión de migración. No requiere framework ni servicio remoto. `false` es tombstone válido. Una transacción de escritura serializa cambios; distintas piezas no sobrescriben el conjunto. Para cambios concurrentes de la misma pieza prevalece la última transacción confirmada. Mantener caché en memoria para render inmediato; si falla la persistencia, indicarlo discretamente y no certificar estado guardado.

Migrar `alicanto_read` legacy y aliases una vez dentro de una transacción que comprueba el marcador, crea únicamente registros inexistentes y confirma el marcador junto con ellos. Tombstones v3 prevalecen. Las dos primeras aperturas concurrentes no pueden reimportar un leído sobre una reversión. Todos los cambios pasan por el mismo store. Notificar mismo documento mediante suscriptores y otros documentos mediante BroadcastChannel; fallback de notificación con evento `storage` sobre una clave de aviso sin datos de lectura. El receptor vuelve a leer el store, nunca aplica un snapshot obsoleto. `pageshow`/`visibilitychange` rehidratan para bfcache. La prueba exige dos pestañas y reversión durante migración. Si IndexedDB está bloqueado, usar memoria de sesión con aviso, sin volver a usar el Set legacy como persistencia supuestamente segura.

Home y Global se entregan en el mismo bundle; pestañas de versión anterior se rehidratan al volver/recargar y no son autoridad para v3. No volver a importar legacy después del marcador. No prometer sincronización inmediata con una pestaña que sigue ejecutando un bundle antiguo: el QA de sincronización usa la misma versión del producto y el handoff declara ese límite.

Separación weekly/base: base conserva ID de señal; Insight recibe `weekly:<approved_version_id>` estable para esa edición, con aliases explícitos en su registro. Si el único dato legado era un leído compartido, migrar **ambas** piezas como leídas para preservar la acción visible previa, registrando `legacy_shared_read`; no afirmar que se conoce cuál fue efectivamente leída. Un estado específico de Insight ya existente prevalece. A partir de migración son independientes. Corrección de copy dentro de la misma edición no cambia ID; una nueva edición factual es otra pieza. No enlazar identidades por mera coincidencia de URL dinámica.

## 4. Contrato editorial v3 propuesto

### Problema sistémico demostrado

`llm_analysis.py` pide qué pasó y por qué importa; `NEWS_SCHEMA` exige ambos. `editorial_gate.quality_score` penaliza menos de35 caracteres en cada uno; `validate_publication_contract` exige ambos. `build_committee_artifact` registra nombres de roles pero PASS puede resultar sólo de ausencia de unas pocas objeciones, no de lecturas efectivas de siete expertos. No presentarlo como consenso independiente. `distinct` en frontend detecta igualdad/prefijos, no paráfrasis; `detailKind` reconoce campos, no ganancia de conocimiento. En Félix, score100 y PASS coexisten con ficha sin profundidad.

### Arquitectura informativa

|Nivel|Pregunta|Contenido admisible|Regla de salida|
|---|---|---|---|
|1 título/Ponte|¿Qué ocurrió?|Actor + acción/cambio factual + magnitud si esencial. Fecha y fuente aparte.|Debe entenderse sin entrar. No tesis vaga ni recomendación en lugar del hecho.|
|2 ficha|¿Qué sé ahora que no sabía?|Técnica, magnitud, alcance, roles, etapa, cambio, comparación válida o consecuencia verificada.|Al menos una afirmación sustantiva incremental con evidencia; no se fija número de palabras ni cuota de cifras.|
|3 profundidad opcional|¿Cómo se entiende o contrasta?|Antecedentes, documentos, relaciones y análisis reproducible con límites.|Sólo si añade valor. Hecho/interpretación/hipótesis distinguibles en texto. Sin secciones vacías.|

Eliminar encabezado visible Qué pasó/Qué ocurrió obligatorio y bloque fijo Por qué importa en ficha y feed; también su variante mecánica Implicancias. No eliminar una consecuencia comprobada: integrarla donde aporta. Por qué importa permanece en `selection_rationale` interno; puede justificar descarte aunque el hecho sea verdadero. No toda noticia relevante requiere decisión ejecutiva inmediata.

### Esquema mínimo, versionado y compatible

Propuesta de contrato, campos nuevos explícitamente no implementados:

```json
{
  "editorial_schema_version": "3",
  "piece_id": "identidad estable existente o alias auditado",
  "related_event_id": "cluster editorial, no estado de lectura",
  "title": "Hecho factual",
  "brief_deck": null,
  "detail_body": "Información incremental verificada",
  "claims": [
    {
      "id": "c1",
      "kind": "fact",
      "text": "Afirmación comprobable",
      "evidence_refs": ["e1"],
      "adds_to": "title",
      "incremental_value": "qué conocimiento incorpora"
    }
  ],
  "evidence": [{"id":"e1","url":"original","locator":"párrafo/sección/página","observed_at":"ISO8601","content_hash":"cuando hay bytes retenidos"}],
  "dates": {"published_at":null,"occurred_at":null,"observed_at":null,"data_period":null},
  "selection_rationale": "Interno: materialidad y límites",
  "review": {"content_version":"hash de texto y evidencia","author":"id","reviewer":"otro id","verdict":"REVISE","reason_codes":[]}
}
```

En cifras añadir `value`, `unit`, `population`, `period`, `comparison_base`, `price_basis` cuando corresponda; null no equivale a cero. Una ficha sin cifras puede ser excelente. Análisis enlaza premisas; hipótesis dice qué falta para contrastarla. `brief_deck` opcional no copia `detail_body` por defecto. Evidence locator obligatorio, hash sólo para bytes capturados: no fabricar hash de una página no descargada.

### Migración sin pérdida ni gasto repetido

- Mantener campos legacy en persistencia mientras lectores antiguos los necesiten; renderer v3 nunca concatena what+why indiscriminadamente. Para v2, proyección de lectura conserva información, elimina etiquetas y evita exactos duplicados, sin declarar la pieza revisada semánticamente.
- Los candidatos v3 pasan gates nuevos. El stock conserva revisión previa y `needs_depth_review` cuando corresponda; no borrar en masa165 registros ni regen90d. Corregir primero tres casos y muestra de portada, después por publicación/actualización natural.
- Eliminar penalización por longitud sólo junto con gate de soporte/profundidad v3; no bajar umbral de materialidad para compensar. Campos de selección interna no se usan como relleno público.
- No sustituir modelo, response_id, texto pagado original, linaje ni evidencias; guardar revisión editorial como overlay con base_version, nuevo content_version, motivo y diff. Pipeline normal decide publicación. Preview en fixtures de prueba, nunca escribir señales vivas en este handoff.
- Weekly: publicado, evidence_map, top3/ranking, audit y traza pertenecen a una sola versión aprobada; un intento nuevo queda aparte. Preservar corrección de #9 y no rejuvenecer con observed_at.

### Controles y consecuencias

|Control|Automático sin IA pagada|Revisión y resultado|
|---|---|---|
|Repetición|Igualdad normalizada, n-gramas/solapamiento como alerta, prefijos duplicados|Editor compara afirmaciones, no palabras. Si el detalle sólo parafrasea, REVISE `no_incremental_information`.|
|Soporte|Refs/locators resuelven, citas retenidas coinciden; ausencia bloquea|Revisor confirma que el original apoya realmente cada claim. `unsupported_claim` bloqueante.|
|Título factual|Campo actor/acción como indicio, listado de titulares vagos|¿Puede decirse qué ocurrió en5s? Normativa conserva acto/número/tema. No aprobar por regex sola.|
|Fechas|Campos separados, futuros, ventana Chile, publicación vs evento, hashes versiones|Fecha desconocida queda explícita; no usar crawling/carpeta como publicación.|
|Cifras|Unidades/bases/períodos, porcentaje vs puntos, aritmética sólo comparable|Datos/economía revisan denominador cuando hay magnitudes o comparación. `incomparable_denominator` bloquea la comparación, no obliga a descartar todo documento.|
|Implicancia genérica|Frases repetidas entre actores y plantillas son alertas|Si puede aplicarse a casi cualquier noticia cambiando nombre, eliminar o justificar con premisas concretas.|
|Duplicación|URL canónica, DOI/documento/acto/evento, alias y hash|Agrupar republicaciones; una voz nueva no es nuevo hecho. No fusionar hechos distintos sólo por tema.|
|Independencia|author!=reviewer, versión/hash revisado, campos obligatorios|`build_committee_artifact` debe decir structured_check, no independent_review. Sin segunda revisión: pendiente, no PASS semántico.|

Similitud no será un umbral mágico de publicación. Un falso positivo no puede esconder una norma: conservar actor/número puede repetir vocabulario legítimamente. Test adversarial de paráfrasis con palabras distintas y de detalle válido que comparte nombres.

El gate semántico v3 comprueba un **receipt de revisión independiente ligado al hash final**, no pretende decidir significado con regex. Las pruebas usan ejemplos etiquetados y comprueban que un receipt REVISE bloquea y uno PASS válido habilita. B1 de3–4h cubre esquema, compatibilidad y enforcement de ese recibo; no promete un evaluador semántico autónomo universal. Si falta la revisión, el candidato queda HOLD, sin nueva llamada pagada automática. La calidad del revisor se audita aparte con contraejemplos.

### Prompt editorial para futuros candidatos

> Usa sólo la evidencia entregada y conserva su atribución. Primero enumera los hechos verificables y qué añade cada uno. Redacta un título que describa el hecho. Escribe una ficha que aporte afirmaciones adicionales; elimina toda frase que sólo repita título o fecha/fuente. No escribas bloques obligatorios Qué pasó/Por qué importa. Explica el mérito de selección en un campo interno. Si una implicancia añade valor, enlázala a premisas y márcala como análisis o hipótesis. Conserva períodos, unidades, bases, etapa propuesta/aprobada/ejecutada y límites. No hay mínimo de palabras. Si la evidencia no alcanza, devuelve REVISE/HOLD con la carencia exacta, sin inventar profundidad. Devuelve claims, evidence_refs y delta informativo. No apruebes tu propia salida como revisión independiente.

Prompt revisor: «No reescribas primero: intenta refutar. Clasifica cada frase como hecho nuevo, contexto necesario, análisis sustentado o redundancia. Comprueba cifras/fechas/roles y versiones contra los originales. Rechaza cualquier claim no sustentado. PASS sólo si puedes nombrar qué aprendió el lector al abrir. Registra objeciones por frase y versión; si no pudiste leer el original, no certifiques apoyo semántico.»

## 5. Alcance FONASA/ISP definitivo del sprint

|Institución|P0 MVP|P1/fuera de recuperación inmediata|Bloqueo exacto|
|---|---|---|---|
|FONASA|`fonasa`, Noticias institucionales y comunicados materiales|`fonasa_datos_abiertos`, boletines/analysis/cuentas públicas/datos|Staging: HTTP403 en `/noticias/`; PR29 confirma frontalALB. Inventario desconocido. No resolver datos abiertos para acreditar Noticias.|
|ISP|`isp_surveillance`, virus respiratorios y alertas epidemiológicas materiales|ANAMED ordinario y catálogo completo; excepción alerta extraordinaria con riesgo sanitario material|Staging: timeouts en índices boletín/virus respiratorios y variantes oficiales. PR29: fallo cadenaTLS .cl/.gob.cl. Error distinto por entorno/observación, no contradicción ni permiso para desactivarTLS.|

Work5 abrió índice FONASA con resultado403; ISP índice y detalle SE39 con502 en lector. Son observaciones de este acceso, no runtime de GitHub. Índice oficial ISP recuperado por búsqueda muestra SE39 y detalle fechado7-oct2026: demuestra documento candidato, no captura operativa ni lectura del PDF. Ningún cero de health certifica ausencia de novedades.

**Rutas alternativas permitidas y stop-loss:**

- FONASA: esperar GET/boletín/export/feed oficial habilitado por el publicador, o una reproducción oficial MINSAL con URL/atribución propia; no hay alternativa automatizada viable acreditada en este corte. No usar un snippet de buscador como cuerpo ni cambiar a datos abiertos para maquillar la recuperación. Conservar `unknown_inventory`, cooldown y un probe permitido cuando venza, sin recapturas equivalentes.
- ISP: conservar índice anual oficial y su enlace a documento/PDF. Descargar PDF sólo desde enlace publicado y TLS válido cuando vuelva el acceso; no adivinar URLs, usar HTTP inseguro, proxies ni verify=false. Misma semana con V2 reemplaza versión con historial, no nueva señal por cuota.
- Ruta oficial complementaria comprobada: [Salud Responde / alertas](https://saludresponde.minsal.cl/alertas-de-salud/) enlaza oficios epidemiológicos MINSAL de15-sep y alertasISP. La página lista enlaces de retiradas29-sep; su fecha superior7-oct no fecha todas las alertas. Sirve para descubrimiento/atribución MINSAL, no equivale a reparar ISP ni habilita inferir vigencia de enlaces tachados. Abrir documento antes de resumir/publicar.
- [Reporte MINSAL10-sep](https://www.minsal.cl/reporte-semanal-campana-de-invierno-2026-hospitalizaciones-en-camas-criticas-pediatricas-por-causa-respiratoria-alcanzan-un-423/) anuncia cambio de modalidad de publicación; es antecedente fuera de ventana, no sustituto actual de SE39. No crear otro conector por este antecedente.
- Para virus: `reporting_week`, `publication_date`, `version`, `samples_tested`, `positive_samples`, agente/universo y distribución deben separarse. Casos detectados no incidencia poblacional; proporción entre positivos no positividad. Sin denominador/PDF, mantener candidato, no cálculo.
- Presupuesto máximo de recuperación adicional en este sprint: **0 intentos equivalentes antes del cooldown**, un probe por superficieP0 al vencer o con cambio externo acreditado;0IA pagada. P1 no consume presupuesto de P0. La excepciónANAMED se selecciona por alcance/severidad verificables, no toda retirada de lote.

Referencias exactas: `data/source_health.json`; PR29 y `docs/DAILY_FIRST_RECOVERY_HANDOFF_2026_10_12.md` en su rama; índice [ISP2026](https://www.ispch.cl/biomedico/vigilancia-de-laboratorio/ambitos-de-vigilancia/vigilancia-virus-respiratorios/informes-virus-respiratorios/?y=2026); [SE39](https://www.ispch.cl/documento/semana-39-2026/); [FONASA Noticias](https://www.fonasa.gob.cl/noticias/). No se cierra ningún blocker en este paquete.

## 6. Backlog y presupuesto de un Builder

Estimaciones de esfuerzo de implementación, no consumo ya realizado ni compromiso de calendario.

|Orden/ID|Clase|Entrega independiente|Dependencia|Presupuesto propuesto|Aceptación|
|---|---|---|---|---|---|
|1 W5-A1|Quick win|Sobres, título/Másinfo directos, retirar accesos/etiquetas redundantes|Snapshot actual; fixtures v3|2–3h|3 tipos de pieza abren mismo destino; no cambios de datos vivos|
|2 W5-A2|Arquitectura pequeña|Estado compartido por identidad, cross-tab, foco y migración|A1|2–3h|Dos pestañas no pierden cambios; persistencia y reversión|
|3 W5-B1|Arquitectura editorial|Contrato v3, gates/proyección compatibles y prompts|Lectura de contratos actuales|3–4h|Paráfrasis no pasa; detalle válido sí; lineage intacto|
|4 W5-B2|Quick win editorial|Tres overlays propuestos y fixtures; anexo B|B1 y revisión final|1–2h|Claims evidenciados; no publicador automático|
|5 W5-C1|Recuperación existente|Clínicas de Chile: fixture fecha/evento y dedupe CENS|No duplicar PR14/stock|≤1h|Sin nuevo slug ni auditoría90d|
|6 W5-C2|Pilotos|CENS e iHEALTH discovery candidates, detrás de flags|Preflight derechos/acceso|≤2h spike cada una|Si preflight no resuelve, contrato+HOLD; no bucle ni colector activo|
|7 W5-D1|Quick win alcance|Mapear prioridades/superficies FONASA/ISP y health honesto|Conciliar PR29|≤1h|P1 no bloquea gateP0; error≠sin noticias|
|8 W5-QA|Gate de entrega|Pruebas focales+desktop/mobile y revisión del diff|Tareas implementadas|≤2h|Receipt por SHA, límites explícitos|
|Después|Posterior|HL7 releases, Isapres fechadas, Colmed acceso, DOI insight, backoffice claims|Evidencia nueva|Sin presupuesto sprint|No desplaza A/B|

Techo sprint propuesto:20h de trabajo Builder; cerrar cada tarea con artefacto y bloqueo preciso al agotar su timebox, continuar independientes. No interpreta tiempo como autorización para contratar servicios. **0 llamadas IA pagadas del pipeline por defecto**: casos ya investigados y tests determinísticos. Si luego la publicación normal requiere modelo, aplicar presupuesto existente y aprobación del owner por candidato; no reiniciar contadores ni repetir outputs pagados. No se configura automation14d ni cron desde este documento.

Los pilotos de fuentes observan como máximo20 candidatos por fuente durante14d tras activación autorizada; son límite de evaluación acotada, no cuota permanente de captura/publicación. Paginación incompleta debe declararse, nunca vender recall completo. Continuidad se decide por materialidad única, fecha verificable y mantenimiento; una fuente documental infrecuente no fracasa por no producir diariamente.

## 7. Prompt ejecutable para un único Codex Builder

```text
CODEX BUILDER ÚNICO · WORK5 PRODUCTO Y EDICIÓN
Repositorio cftorre1/Radar-salud. Base staging actual. Lee este handoff completo,
sus anexos y latest issue5 antes de editar. Work3 Integration Commander integra.
No tocar main/producción, no merge ni auto-merge a staging, no publicar señales,
no ejecutar capturas/modelos pagados ni backfill90d. Trabaja en rama aislada.

1) Relee HEAD/queue/PMO/contratos/PR28/PR29. Registra SHA y cambios concurrentes.
   Si hay implementación equivalente, reutiliza y valida delta, no rehagas.
   No resuelvas discrepancia PR29 con un merge: déjala a su owner/Commander.
2) A1: unifica título y Más info con openContent por ID a ficha real; usa sobres
   de estado en Ponte/Global/feed. Quita contexto intermedio y encabezados fijos.
   No marques leído antes de mostrar ficha; falla de carga conserva pendiente.
3) A2: módulo de lectura compartido; conserva IDs y migra legacy una vez;
   notifica misma página/storage/pageshow. Prueba pérdida de actualizaciones
   entre pestañas, reversión, persistencia, foco y piezas especiales.
4) B1: implementa versión editorial3 compatible. what/why legacy no desaparecen
   de historia; selección interna separada de detail_body/claims. Sin mínimos
   de palabras. Gates de apoyo e información incremental, independencia real
   del revisor; no declarar PASS semántico por build_committee_artifact.
   Preserva materialidad, fuentes, fechasChile, normativa, licencia y weekly.
5) B2: incorpora como borradores/fixtures los tres textos anexoB con fuentes,
   base_version y diff. No alteres history/feed/latest/approved para publicarlos.
   Preparar acción exacta para publicador autorizado. Reutiliza outputs pagados.
6) C1: reusar ClinicasChileScout. C2: máximo dos spikes CENS/iHEALTH; preflight
   documentado acceso/derechos y contratos antes de habilitar. Si unknown,
   deja flags apagados y expediente pendiente. ProSalud y bloqueados: stop.
7) D1: FONASA noticiasP0; datosP1. ISP respiratorios/alertas materialesP0;
   ANAMED ordinarioP1. No repetir probes ni desactivarTLS. Conciliar ownerPR29.
8) QA: desktop1440x900/mobile390x844 y320px/zoom200%; noticias/weekly/Global,
   normativa/datos/título largo; mismas fichas y sobres, fila desaparece sólo
   de pendientes, feed permanece. Múltiples pestañas, bfcache, fallo storage,
   teclado/foco/contraste; >10Global sin pérdida. Usa negativos semánticos
   del contrato. Ajusta tests del recorrido viejo con justificación explícita.
9) Haz commits/tareas independientes y un PR a staging con checklist por SHA,
   evidencia, consumo exacto y límites. Queue/PMO sólo cambios aditivos de IDs
   propios con lectura fresca y guard; no sobrescribir owners ni cerrar #5–#9.
   Antes del commit final compara hashes de fuentes/history/feed/receipts;
   cualquier delta fuera de scope se excluye o concilia con evidencia.

Techo20h según timeboxes del backlog; no gasto API del pipeline. Una pasada
focal por tarea y QA final; repetir sólo fallo concreto. Si se agota un frente,
guardar avance y bloqueo y continuar los independientes. No pedir al usuario
que retransmita prompts. Entregar a Work3 y comentar issue5. No confundir
especificación con implementación, test verde con contenido bueno ni merge
con beta lista.
```

## 8. Anexos y autoridad

Los anexos siguientes forman parte del paquete. En conflicto, las decisiones finales de secciones1–7 prevalecen sobre opciones exploratorias de anexos. Para fuentes, IMPLEMENTAR AHORA significa trabajo técnico acotado con flags apagados hasta preflight; no permiso comercial ni estado operativo. ADIMECH sigue PILOTO condicionado; HL7 se clasifica POSTERGAR colector diario con opción posterior de observación manual; Transforma BLOQUEO EXTERNO observado y ningún colector dedicado este sprint.

San Carlos: se acredita el hecho; no retirar por inexistencia. El texto corregido aún requiere aceptación de la versión exacta por publicador/revisor. Si no llega a revisión o no supera valor incremental, retirar destaque y mantener noticia/archivo. No es mandato de conservar a toda costa hasta17-oct.


---

# Anexo A · UX y rutas reales

# Work 5 — revisión UX e información independiente

Referencia inspeccionada: staging `ef8cbe3938623d493872ff5f3e717153f176d1be`, 12 octubre 2026. Inspección estática del código y tests; NO constituye QA visual ni ejecución browser. No existe AGENTS.md en el árbol revisado. Ningún código modificado.

## Hallazgos concretos

1. **Ponte al día todavía exige dos pasos para una noticia ordinaria.** `web/app.js:openFromBrief` marca leído, desplaza al feed y muestra «Volver arriba». La ficha real está en `openDetail`, que no se llama desde el título de la bandeja. El título del feed es un h2 sin interacción. Las piezas especiales usan otra ruta, `openSpecial`; Global sí expande directamente mediante `openTheme`, pero títulos de sus tarjetas tampoco son clicables.
2. **La lectura es inconsistente y no se sincroniza entre documentos abiertos.** `readAction`, `checkIcon`, `unreadIcon` muestran check y flecha de revertir, representando la acción futura en vez del estado. Home y Global comparten `alicanto_read` y migración legacy: es una base reutilizable. Sin embargo cada página carga un Set una sola vez y no escucha `storage`, `pageshow` ni `visibilitychange`. Dos pestañas pueden pisarse: al guardar una escribe el Set entero desactualizado y borra lecturas de la otra. Home marca leído al bajar al feed; `openDetail` por sí solo no marca; Global lo hace al abrir análisis.
3. **El contexto intermedio existe realmente.** `brief` incluye details «Contexto de la señal» con la misma síntesis; CSS lo muestra en mobile. `triage-summary` también concatena el titular original cuando el título editorial difiere, multiplicando texto y ruido.
4. **Los controles editoriales son principalmente lexicales.** `distinct` solo normaliza igualdad/prefijo y diferencia de longitud <35; una paráfrasis supera este filtro. `substantivePoints` compara con `what_happened`, título y why antiguos, no necesariamente `card_what` y `display_title`. `detailKind` concede profundidad por presencia de arrays/contexto, sin acreditar información incremental.
5. **Cambiar etiquetas no resuelve el contrato.** Feed `card` presenta «Qué pasó» y «Por qué importa»; `detailHtml` presenta «Qué ocurrió» e «Implicancias», Global tiene «Por qué importa». `publicationContractOk`, `src/radar_salud/editorial_rules_v2.py` y `config/editorial_intelligence_committee_v1.json` aún requieren what/why. `editorial_gate.py` penaliza textos <35 caracteres: puede incentivar relleno. Hay que distinguir campos internos de selección de campos públicos, conservando compatibilidad de lectura histórica.
6. **Las pruebas existentes acreditan el comportamiento anterior.** `tests/browser/product.spec.cjs` espera salto al feed y botón Volver arriba, mientras `tests/web.test.cjs` 19–21 valida rechazo de copias exactas, no paráfrasis. No se observa cobertura de sincronización bidireccional entre pestañas ni restauración bfcache. Reemplazar expectativas incompatibles con la nueva decisión; no borrar protección de fechas, identidad, vigencia semanal o archivo.
7. **Densidad mobile frágil.** `web/index.html` acumula overrides del alto de la bandeja (220/285/430px), overflow oculto y expansión. Un título largo puede quedar cortado por el contenedor aunque no haya line-clamp. El cuerpo de tarjetas leídas baja opacity global a .64/.66, afectando contraste de texto, controles y fuentes.
8. **Identidad Insight/base merece decisión explícita.** `specials` une weekly con primera señal de misma source_url, sin fecha; `inboxPool` suprime esa base. La lectura del análisis puede colisionar con otro evento en URL dinámica. Reutilizar ID de evento exacto, no solo URL, y no asumir que leer una noticia equivale a leer un Insight con conocimiento adicional. Para este sprint exigir `reading_identity` explícita si ambas representaciones son equivalentes; en caso contrario mantener identidades separadas, asociadas por `related_event_id`.

## Contrato implementable

- Cada fila compacta: tipo opcional; título factual completo clicable; fecha y fuente en segunda línea; síntesis opcional solo con delta editorial aprobado. Dos acciones primarias: sobre y «Más info». El título y Más info comparten resolver/ID/destino y no requieren paso intermedio. La repetición del acceso título+Más info es deliberada por instrucción de Dirección.
- Sobre cerrado representa estado **No leído**; sobre abierto **Leído**. Tooltip/aria-label expresa la acción siguiente, por ejemplo «Marcar como leído: [título]». `aria-pressed=true` significa leído, con nombre accesible estable si se elige toggle nativo; alternativa botón de acción de nombre dinámico + descripción de estado, sin mezclar ambos modelos. SVG decorativo aria-hidden. Estado no depende solo del color.
- `openContent(id,origin)` resuelve noticia/Insight/Global a su ficha real; después de render válido y visible marca leído. Fallo de carga o ID desconocido no cambia estado. Más info y título ejecutan exactamente esa función. Desde Home, Global puede continuar usando global.html#theme-ID, siempre con análisis abierto automáticamente; no crear una nueva pantalla puente.
- Ficha puede ser breve, pero cada novedad candidata a bandeja tiene al menos un dato material adicional con soporte y no solo la reiteración de fecha/fuente. Si evidencia es insuficiente, mantener en registro histórico/contexto y no promover como pieza con profundidad. No fabricar párrafos para habilitar el botón. Ficha histórica con evidencia limitada puede mostrar lo disponible y fuente original sin prometer análisis.
- Cerrar ficha devuelve foco al disparador si sigue presente; si desapareció al leerse, al siguiente ítem de bandeja o al encabezado vacío. Al leer desde bandeja elimina solo esa fila y actualiza feed/contadores inmediatamente; mantiene el orden y scroll del feed. Marcar no leído en feed repone fila según orden activo. Cambiar estado nunca cambia los filtros.
- Implementar módulo compartido pequeño de estado: `getRead(id)`, `setRead(id,value)`, `subscribe(fn)` y claves/migración compatibles. Resolver el problema del Set completo: preferir registro por identidad en clave propia (una mutación no reescribe otras identidades), migrando `alicanto_read` una vez y manteniendo compatibilidad histórica en lectura; o read-modify-write sobre último snapshot más eventos con orden claro, probando carrera entre pestañas. `storage` para otros documentos; notificación síncrona para documento actual; recarga de estado en `pageshow` para bfcache. Escritura sin localStorage mantiene funcionamiento en memoria e informa discretamente que no se guardó si es necesario. No prometer sincronización entre dispositivos; no existe cuenta/backend requerido en este sprint.
- Reusar IDs estables actuales, migración de títulos y `global:<id>`. Cambio de fecha auditado requiere alias explícito al ID previo: no convertir cada corrección editorial en nuevo no leído.
- Mover compartir y fuente original a ficha cuando afecten las dos acciones principales en elementos Ponte/Global. No es necesario quitar utilidades secundarias del feed ordinario si no compiten con la navegación; sobre y destino ficha sí son consistentes.
- Desktop: título flexible y columna de acciones compacta. Mobile 390px: título y metadatos a todo ancho; fila compacta de dos acciones debajo si no caben. Objetivos táctiles >=44x44; título sin truncamiento. Bandeja de primeras filas completas con expansión explícita que conserva todas las elegibles, sin límite editorial numérico. No usar recorte por alto fijo que deje media fila.
- Fondo/contorno y sobre indican leído; evitar bajar opacity de toda la tarjeta. Texto normal contraste >=4.5:1 y controles >=3:1, foco visible y reduce-motion.

## QA de aceptación acotado

Correr desktop 1440×900, mobile 390×844 y chequeo de 320px/zoom200% sin overflow horizontal. Una muestra de noticia ordinaria, weekly y Global con título largo, normativa, pieza de datos y evidencia limitada.

1. Título y Más info abren misma ficha directamente; no existe «Contexto general/de la señal», Qué pasó/Qué ocurrió como encabezado obligatorio ni bloque fijo Por qué importa.
2. Bandeja tiene dos acciones principales; iconos son sobres correctos en todos los módulos; ficha entrega delta factual verificable.
3. Leer desde fila quita pendiente, conserva feed, contador correcto, foco siguiente; revertir desde feed repone sin duplicar. Apertura exitosa lee; apertura fallida no lee.
4. Refrescar conserva estado; A Home/B Global abiertos simultáneamente reflejan lectura y reversión sin refresh; mutar identidades distintas en ambos conserva ambas; volver atrás con bfcache correcto.
5. Cerrar modal/Escape restaura foco válido; operación por teclado; lector de pantalla distingue estado/acción; no foco en fila borrada. No salto de scroll al mutar leído.
6. Fecha Chile, IDs de título corregido, filtros persistidos, expiración semanal y >10 temas Global conservan gates existentes.
7. Tests de regresión de paráfrasis: título «X abre 20 camas», lead «Se anunció la apertura de veinte camas en X» no cuenta como delta; lead «El servicio comienza el lunes y funcionará con 12 especialistas» sí si ambas afirmaciones están evidenciadas. Test de cambio de denominador y de inferencia genérica no sustentada.

## Orden y presupuesto orientativo de Builder

Tarea A (bajo esfuerzo): rutas directas, sobres, eliminar contexto y encabezados; tests afectados. Tarea B (medio): estado compartido/persistencia/foco y cross-tab; no cuentas ni framework nuevo. Tarea C (medio): contrato de delta/claims y pipeline compatible, sin regenerar 90 días. Tarea D (bajo): CSS consolidado y QA de muestra. No ejecutar un LLM por evento UI ni por validación determinística; revisión semántica independiente solo en piezas candidatas, basada en claims y evidence refs.

## Evidencia browser aportada por revisión raíz

Root verificó cloud desktop aproximadamente 1348×927: Home 69 tarjetas/67 no leídas (dos lecturas locales previas); clic en fila Félix Bulnes bajó al feed y marcó leído, sin abrir ficha. Esa tarjeta no disponía de Más info ni detalle; restauró no leído. Global mostró 10 temas/9 no leídos, títulos de bandeja como botón y tarjetas con Por qué importa y acordeón Ver análisis completo. Screenshot evidencia lista Home con scroll anidado y textos largos. No extrapolar esta comprobación a móvil; móvil requiere QA en Builder.


---

# Anexo B · Correcciones editoriales

# Work 5 — Tres casos editoriales verificados

Corte: 12 octubre 2026, America/Santiago. Revisión documental de staging `ef8cbe39`, `web/data/radar_today.json`, `data/weekly_insight/latest.json`, handoff Editorial Senior integrado por PR28. Propuestas para revisión e implementación autorizada; no señales publicadas ni archivos del repositorio modificados.

## 1. Félix Bulnes: el problema sí es pérdida de información verificable

**Estado observado.** La tarjeta repite el titular en `what_happened`; `why_it_matters` describe genéricamente innovación y colaboración. `key_facts`, `key_numbers` y `key_points` vacíos, pero `publication_ready_score=100`, `confidence_score=100`, comité PASS y sin objeciones. Un score completo no está midiendo profundidad. `event_date=2026-10-07` coincide con publicación, no con intervención.

**Título propuesto:** Félix Bulnes realiza la primera mastectomía robótica reportada en Chile, junto a Barros Luco.

**Ficha propuesta:** La intervención se realizó el 30 de septiembre y combinó conservación del pezón con reconstrucción inmediata. Participaron especialistas de ambos hospitales y se utilizó el robot Da Vinci. El jefe de Patología Mamaria del Félix Bulnes explicó que esta primera experiencia busca evaluar factibilidad y resultados antes de avanzar hacia un eventual programa de cirugía mamaria mínimamente invasiva. La comunicación institucional no presenta una evaluación comparativa de resultados ni costos.

**Evidencia nueva:** técnica, fecha efectiva, equipamiento y etapa de desarrollo. El comunicado MINSAL está fechado el 7 de octubre; Hospital Barros Luco publicó el 6 de octubre y confirma técnica y colaboración.

**Omitir:** beneficios clínicos universales; ahorro, expansión de cobertura, aumento de capacidad o reducción de listas sin datos. No convertir una frase institucional ambigua sobre 24 horas en estadía medida. No usar población territorial como cantidad de beneficiarias del procedimiento. Nombre y edad de la paciente no agregan valor ejecutivo.

**Justificación:** la distinción entre primera experiencia y programa consolidado cambia la lectura sobre adopción tecnológica; aporta más que elogios de innovación. No exige análisis clínico adicional ni nuevas llamadas de IA para recuperar estos hechos.

**Fuentes originales:**
- [MINSAL, 7 octubre](https://www.minsal.cl/hospital-clinico-felix-bulnes-realiza-la-primera-cirugia-robotica-de-cancer-de-mama-en-nuestro-pais-junto-a-equipo-medico-del-hospital-barros-luco/), cuerpo leído, fecha intervención explícita.
- [Hospital Barros Luco, 6 octubre](https://www.hospitalbarrosluco.gob.cl/jefe-de-patologia-mamaria-del-hospital-barros-luco-participa-en-historica-cirugia-robotica-de-cancer-de-mama/), cuerpo leído. Ambos pertenecen a la red pública: no dos ensayos clínicos independientes.

## 2. Presupuesto 2027 / Pulso: precisar denominadores y no fabricar actualidad

**Registro exacto:** `presupuesto-2027-minuta-politica-del-gobierno-reporta-alza-del-gasto-distinta-de-la-informada`, publicación visible 6 octubre. La ficha actual contiene cifras útiles; el diagnóstico no debe afirmar que todo su texto es paráfrasis. Falla en presentar la comparación de forma inequívoca, retiene una promesa futura de IFP y añade relevancia genérica.

**Título propuesto:** Presupuesto 2027: Hacienda atribuye las distintas alzas del gasto a sus bases de comparación.

**Ficha propuesta:** Pulso reportó el 6 de octubre tres variaciones para el gasto total propuesto: 1,5% frente al cierre proyectado de 2026; 2,7% frente a la ley aprobada para ese año; y 3,5% frente al presupuesto base, que incorpora reajustes y ajustes. La minuta sitúa el aumento de Salud en 4,7% respecto de esa última base. La asignación de $18,4 billones proviene del detalle de partidas publicado por la Cámara, según el mismo reporte de Pulso. Son cifras de un proyecto en tramitación, no de gasto ejecutado ni de una ley ya aprobada.

**Detalle opcional en ficha:** tabla de tres bases anteriores; no repetir de nuevo los porcentajes en otro párrafo.

**Evidencia añadida/clarificada:** el 1,5% faltaba como comparación explícita contra cierre proyectado. Los tres porcentajes son del gasto total; el 4,7% es sectorial. No hay base para denominarlos cuatro medidas intercambiables de Salud.

**Omitir:** afirmar que IFP “será presentado” al actualizar la ficha el 12 de octubre; atribuir la diferencia a un error o engaño; confundir nominal/real si el original no lo precisa; traducir asignación en producción asistencial. No mezclar $18,3/$18,4 billones o 14,5/14,6% de otras piezas sin comparación primaria. Mantener HOLD previo sobre conciliación de Ricarte Soto.

**Justificación:** el original ya explica el contraste; basta editar. Preservar fecha 6 octubre. La revisión no convierte este evento en novedad del día ni acredita una comprobación independiente de DIPRES. Agrupar bajo familia Presupuesto2027 con otras notas, conservando señal propia sólo por el cambio sustantivo de base.

**Original leído:** [Pulso / La Tercera, Carlos Alonso, 6 octubre](https://www.latercera.com/pulso/noticia/presupuesto-2027-minuta-politica-del-gobierno-reporta-alza-del-gasto-distinta-de-la-informada/). No se consultó un nuevo IFP ni se certificó la aritmética contra tablas DIPRES. No se necesita hacerlo para publicar una síntesis atribuida y acotada del reporte existente; sí para elevarla a dato fiscal validado o actualizar cifras.

## 3. San Carlos de Apoquindo: hecho acreditado, titular inadecuado

**Estado observado.** Weekly actual titula “activar capacidad de reemplazo para sostener la continuidad”. Comunica una recomendación antes del hecho. Tiene profundidad y límites útiles; no es correcto afirmar que carece de evidencia. PR28 permite mantenerlo hasta el inicio del 17 de octubre; se respeta esa decisión. `independent_second_reviewer=false` evidencia que PASS del mismo autor no es aceptación independiente.

**Título propuesto:** Clínica San Carlos de Apoquindo suspende operaciones por semanas tras el aluvión.

**Ficha propuesta:** El 10 de octubre, UC CHRISTUS informó que concluyó el traslado de sus pacientes hospitalizados y suspendió la operación mientras recupera las áreas afectadas por el aluvión del día 8, según el comunicado recogido por La Tercera. La página oficial de contingencia, consultada el 12 de octubre, confirma el cierre de San Carlos y El Alba e incluye consultas, exámenes, procedimientos, hospitalización y urgencias. La red indica que contactará a pacientes para reagendar y mantiene alternativas en otros centros. No se informa fecha exacta de reapertura.

**Profundización propuesta, explícitamente análisis editorial:** Para un equipo de red, la pregunta verificable es cuántas atenciones afectadas tienen nueva atención efectivamente confirmada. Seguir casos pendientes y fechas por prestación; no equiparar la existencia de otro centro con disponibilidad confirmada para todos. Esta propuesta de gestión no es una medición de saturación.

**Evidencia incremental:** la comunicación primaria actual comprende hospitalización además de atención ambulatoria/urgencia; confirma alcance operativo sin transformar la consulta de hoy en nueva fecha del evento. La Tercera del 10 recoge finalización de traslados y suspensión por semanas.

**Omitir:** camas o pacientes afectados sin cifras, impacto financiero calculado, ganancia de competidores, capacidad regional perdida, recuperación clínica de pacientes. Quitar conexiones Bupa/Andes/RedSalud cuando sólo decoren el análisis sin demostrar relación operativa con esta contingencia. DF y LT replican un comunicado, no dos mediciones independientes.

**Dictamen:** mantener como Insight con título y apertura factual corregidos, sujeto a revisión independiente final. No corresponde retiro por falta de hecho: sí está acreditado. Retirar el destaque al expirar el 17 de octubre en Chile si no existe nuevo candidato revisado, o antes si se descubre contradicción material no resuelta; preservar archivo. Una reapertura sería actualización verificada, no simple renovación por `generated_at`.

**Fuentes:**
- [UC CHRISTUS contingencias](https://www.ucchristus.cl/contingencias), original dinámico leído al 12 octubre, sin fecha editorial visible; confirmar estado, no fechar anuncio.
- [La Tercera, 10 octubre](https://www.latercera.com/nacional/noticia/clinica-uc-christus-de-san-carlos-de-apoquindo-termina-traslado-de-pacientes-ante-suspension-de-operaciones-por-aluvion/), cuerpo leído; atribución explícita al comunicado. El cuerpo actual dice balance13:00, mientras el índice de buscador decía12:00: omitir hora no esencial y preferir cuerpo sobre snippet.

## Contratos de prueba derivados de los casos

1. **Félix:** con título solo no puede aprobar ficha idéntica; debe existir al menos una afirmación sustantiva nueva con evidencia localizable. No imponer número fijo de palabras ni cantidad universal de hechos.
2. **Fechas:** `published_at`, `occurred_at`, `observed_at` y `data_period` separados; parser nunca reemplaza evento por publicación sin etiqueta.
3. **Pulso:** cada cifra lleva universo, unidad, período y base cuando correspondan. No forzar datos inexistentes: marcar no especificado y abstenerse de cálculos.
4. **San Carlos:** abrir ficha debe presentar primero hecho; análisis tiene etiqueta y premisas trazables. Un responsable distinto del redactor acepta el texto final, incluso si ambos operan en una sola sesión de trabajo.
5. **Control semántico:** revisor clasifica cada frase como hecho nuevo, contexto necesario, análisis sustentado o redundancia; rechazar relleno. Similitud léxica sólo alerta, nunca juez único de calidad: dos frases con vocabulario distinto pueden no aportar nada.
6. **Identidad:** corregir por ID/URL canónico y huella de versión; misma revisión en registro, comité y exportación. No crear nueva señal o resetear leído por corrección editorial menor. Conservar historial de antes/después.
7. **Presupuesto controlado:** estas tres correcciones ya tienen evidencia; revisión determinística y editorial sin recaptura de90d ni IA pagada. Si versión concurrente cambia, comparar y conciliar antes de aplicar.


---

# Anexo C · Matriz de nueve fuentes y contratos

# Work 5 — frente C: nueve fuentes chilenas

Fecha de revisión: 12 octubre 2026. Ventana principal: 13 septiembre–12 octubre, America/Santiago. Base local: staging ef8cbe39. Investigación acotada de superficies originales; no es un censo exhaustivo. Los conteos indicados son mínimos visibles, no tasas históricas ni garantía de cobertura completa. HTTP 403/406 de la herramienta son bloqueos observados de acceso en esta revisión, no prueba universal de que el sitio prohíba todo acceso. Fecha de crawling no equivale a publicación.

## Decisión

Priorizar CENS y promover iHEALTH desde P1 a P0 de evaluación/implementación en modo candidato. Reutilizar Clínicas de Chile, ya existente. No crear nueve conectores. Pro Salud tiene restricción comercial expresa; detener implementación hasta aclaración escrita. Colmed tiene valor P0, pero acceso bloqueado aquí: promover su prioridad editorial sin fingir viabilidad técnica.

“IMPLEMENTAR AHORA” significa preparar/reutilizar el conector y sus fixtures; habilitación recurrente y tratamiento de contenido sujetos al expediente de acceso/derechos. Ninguna lectura pública ni RSS demuestra autorización comercial. En las restantes fuentes no se acreditó licencia comercial ni permiso automatizado: estado unknown, no allowed. Robots no pudo consultarse con esta herramienta; no inventar resultados. Ningún feed fue validado; no afirmar que /feed funciona.

| Fuente/prioridad inicial | Resultado | Evidencia 30 días/frecuencia observada | Valor diferencial y duplicación | Complejidad estimada/alcance |
|---|---|---|---|---|
| Clínicas de Chile/P0 | IMPLEMENTAR AHORA: verificar/reparar existente | 2-oct: jornada salud digital; 1 noticia reciente visible en primera página. No extrapolar baja frecuencia desde listado parcial | Perspectiva prestadores, documentos sectoriales. Jornada conjunta con CENS; columnas replican Pulso. No tratar agenda gremial como cambio normativo | Baja incremental; conservar slug clinicas_chile y cuatro canales actuales; este sprint noticia material y fecha, sin nuevo backfill documental |
| Asociación de Isapres/P0 | POSTERGAR con vigilancia manual | Home actual enlaza “Comunicados” directamente a PDF en /2025/10/, sin fecha interna verificable. No acreditada pieza de ventana | Posición pagadores útil, pero alto solapamiento SIS/SUSESO/Pulso. Un pronunciamiento no demuestra cifras regulatorias | Media: cambio de sitio, documentos y cronología. No desarrollar conector sin 2 piezas fechadas y ruta estable; nunca datar PDF por crawling o carpeta |
| ADIMECH/P0 | PILOTO LIGERO condicionado a acceso | Índice oficial buscable: 28-sep incorporación Johnson & Johnson; página directa timeout/406. No confundir esa fecha con HIMSS, otro título contiguo | Dispositivos/regulación/cadena suministro; incorporación de socio, sola, escasa materialidad. Eventos duplican CENS/Clínicas/ISP | Baja-media HTML si acceso permitido; stop-loss tras fallo índice y detalle; no scraping LinkedIn ni proxy evasivo |
| CENS/P0 | IMPLEMENTAR AHORA en candidatos | 6 entradas fechadas 16-sep–6-oct visibles: formación, seguridad paciente, ciberseguridad, innovación servicios, aniversario y agenda. Material fuerte 30-sep, no seis señales publicables | Implementación digital y gobernanza. Filtrar cursos/efemérides; eventos y programas compartidos con Pro Salud/Transforma/Clínicas | Baja-media, HTML fechas visibles. Noticias #MakeCENS; documentos sólo por evidencia y licencia individual |
| Pro Salud Chile/P0 | BLOQUEO EXTERNO: derechos | Noticias Salud visible hasta 6-jul; Socios hasta 14-ago; no acreditada pieza de ventana. Términos limitan uso comercial | Startups/pilotos; duplicación alta con CENS/Corfo/HL7. No sustituir falta de actualidad con fecha de modificación | No invertir desarrollo. Pedir aclaración/licencia comercial cuando Dirección autorice contacto; usar fuentes coproductoras independientes permitidas |
| Transforma Innovación en Salud CORFO/P1 | BLOQUEO EXTERNO en sitio; POSTERGAR colector dedicado | transformasalud.cl y enlace PRISMA IA responden 403. CENS 10-sep fuera ventana acredita actividad compartida. No se acredita nueva publicación fechada de ventana | Financiación y adopción tecnológica; gran solapamiento Corfo/ISP/CENS | No crawler nuevo. Enrutar tema a fuentes oficiales Corfo/CENS/ISP ya útiles; Linktree sirve localizador, no prueba de fecha ni autorización |
| HL7 Chile/P1 | POSTERGAR noticias; PILOTO LIGERO manual de releases | Última noticia visible 3-jul; home anuncia Connectathon 12–14 ene 2027, sin fecha publicación. Cero piezas de ventana acreditadas | Guías/versiones interoperabilidad, alto valor cuando cambia una versión. Duplicación eventos CENS; no confundir norma con obligatoriedad legal | Baja para observación semanal de versión estable/guías; no feed diario de eventos. Licencias por guía y terminología |
| iHEALTH/P1 | PILOTO LIGERO promovido P0 | 6 notas 14-sep–9-oct. 23-sep compras públicas; 24-sep segmentación tumores; 9-oct modelación cardíaca. No todo premio/curso material | IA clínica con metodología y compras; mayor novedad sustantiva que incorporación gremial. Dedupe DOI contra universidades/prensa | Media HTML propio; 1–2 h spike + 14 días candidatos. Priorizar trabajos con DOI y limitaciones; no confundir prueba metodológica con despliegue clínico |
| Colegio Médico/P1 | BLOQUEO EXTERNO observado; promover P0 editorial | Oficiales indexadas 1-oct carta presupuesto y posición sobre fiscalización SUSESO; superficie home/detalle 403. Consulta detecta 9-oct Consejo Presupuesto, sin detalle validado | Conflictos implementación/personal/presupuesto. Perspectiva atribuida del gremio, contrastar regulador. Duplicación medios/SUSESO | Baja-media si ruta autorizada disponible. Sin bypass; excluir bolsa laboral, beneficios, páginas test y subdominio colmedprueba |

## Hallazgos verificables para selección

iHEALTH se denomina oficialmente **Instituto Milenio en Ingeniería e Inteligencia Artificial para la Salud**. Nota 23-sep: estudio de órdenes enero2022–abril2025, 1.420 transacciones, 204 instituciones y 249 proveedores; publicación no significa datos 2026. Reporta concentración en comunidad imagenología, no en todo mercado sanitario. Enlaza DOI 10.18687/LACCEI2026.1.1.2745: el artículo científico debe verificarse antes de elevar a insight; no afirmar causalidad ni extrapolar todo Mercado Público. Nota 24-sep: segmentación de tumores con datos sintéticos y prueba clínica pequeña; no convertir resultados en disponibilidad asistencial. Evidencia diferencial suficiente para promover piloto por encima de P0 con pocas novedades.

Clínicas de Chile 2-oct documenta reunión del 1-oct sobre regulación digital. Es evidencia de preparación de prestadores, no fuente normativa primaria para fechas de entrada en vigor: enlazar texto legal correspondiente. CENS 30-sep identifica Servicios de Salud Biobío, Metropolitano Oriente y Talcahuano y sus estrategias institucionales. Puede aportar implementación concreta; rechazar si ficha sólo dice que hubo webinar.

Pro Salud: términos contienen restricción explícita de no uso comercial y atribuyen una cláusula a “AFIPA”, discrepancia editorial que requiere aclaración, no licencia tácita. Detener investigación de automatización en este sprint. No se ha contactado al titular.

## Contrato técnico compartido propuesto

Reutilizar `src/radar_salud/source_scouts.py` (`ClinicasChileScout`, `CorporateNewsroomScout`), `public_source_pipeline.py` y `pending_queue.py`. `config/sources.json` ya contiene `clinicas_chile`, `sector_multi_channel`, daily. `ClinicasChileScout.PAGES` ya cubre Noticias/Memorias/Estudios y análisis/Documentos y `process_clinicas_chile` exige fecha verificada. No crear alias ni otro collector. Para CENS/iHEALTH no forzar parser corporativo sin fixture que pruebe extracción correcta; aprovechar RawItem/cola/health/dedupe.

Campos adicionales son propuesta, no afirmar que existen: `canonical_url`, `source_slug`, `channel`, `title_original`, `published_at`, `modified_at`, `event_at`, `date_evidence{url,selector,raw}`, `rights_status`, `rights_evidence_url`, `access_status`, `retrieved_at`, `evidence_hash`, `document_doi`, `actor_role`, `candidate_cluster_id`, `materiality_reason`, `rejection_reason`. Distinguir fechas de publicación/evento/datos/release. Metadatos desconocidos permanecen null; ningún fallback a fecha de consulta. Toda pieza termina pending/rejected/deferred; este paquete no autoriza publicación.

| Adaptación | Entry point validado | Admitir | Rechazar / QA |
|---|---|---|---|
| clinicas_chile existente | https://www.clinicasdechile.cl/noticias/ | Notas materiales; documentos existentes si permiso/fecha resueltos | Fixture 2-oct con evento1-oct; no fechas de artículos vecinos; no doble señal CENS por misma jornada |
| cens propuesto | https://cens.cl/makecens/ | Implementaciones, resultados, guías y políticas con hecho concreto | Fixture30-sep y negativos aniversario/curso; feed/WordPress sólo si endpoint verificado, nunca supuesto |
| ihealth propuesto | https://i-health.cl/ y enlaces /news/ | Estudios con DOI, validación, transferencia, compras y resultados medibles | Fixture23-sep fecha publicación≠periodo datos; 24-sep conservar tamaño muestra/limitación; dedupe DOI y ES/EN |
| adimech piloto | https://adimech.org/noticias/ (descubierto índice, fetch falló) | Regulación, acceso y supply con magnitud; sólo tras preflight | Negativo28-sep nueva membresía sin cambio material; no mezclar fecha con titular contiguo |
| hl7 observación manual | https://hl7chile.cl/fhir/ig/clcore/ | Cambio versión estable, changelog fechado, alcance y licencia | Borrador ≠ versión normativa; home sin publicación no es noticia reciente |

Presupuesto: máximo dos implementaciones nuevas en este sprint (CENS e iHEALTH), 2 h spike cada una, 1 fixture positivo + 2 negativos cada una, máximo 20 candidatos por fuente, una consulta diaria tras autorización, sin backfill90d. 14 días de observación de candidatos con evidencia; aprobar continuidad si entrega al menos 2 candidatos materiales únicos verificables, ≥95% fecha correcta en muestra revisada y cero inferencias clínicas/legales sin sustento. Umbrales son decisión operativa propuesta, no validación estadística. No penalizar fuente documental válida sólo porque no publica diario: medir contra su propia cadencia. Límite dos fallos consecutivos de acceso y estado deferred_access; no nuevos mecanismos evasivos. No IA pagada para fechas, dedupe URL/DOI, clasificación de rutas o hashing.

## Registro de evidencia original y limitaciones

- E1 https://www.clinicasdechile.cl/noticias/ (listado 2-oct; fuente `turn2view6`).
- E2 https://www.clinicasdechile.cl/noticias/clinicas-de-chile-y-cens-realizan-jornada-sobre-el-nuevo-marco-de-la-salud-digital-en-chile/ (fecha/evento/contenido, `turn6view4`).
- E3 https://www.isapre.cl/ (Comunicados apunta PDF, `turn2view3`). PDF: https://www.isapre.cl/wp-content/uploads/2025/10/Declaracion_Fiscalizacion_Suseso_0710.pdf (`turn6view3`; fecha interna no acreditada, carpeta no válida para datación).
- E4 https://adimech.org/noticias/ y https://adimech.org/ (`turn10search9`, `turn10search0` oficial indexado fecha28sep/membresía; directa falló `turn11view0`).
- E5 https://cens.cl/makecens/ (`turn2view5`; seis entradas visibles en ventana, algunas no materiales).
- E6 https://cens.cl/servicios-de-salud-comparten-estrategias-y-aprendizajes-para-impulsar-la-innovacion/ (`turn6view7`;30sep).
- E7 https://prosaludchile.cl/noticias/noticias-de-salud/ (`turn6view0`) y https://prosaludchile.cl/noticias/noticias-socios-prosalud/ (`turn8view8`).
- E8 https://prosaludchile.cl/terminos-y-condiciones-de-uso-y-politicas-de-privacidad/ (`turn8view6`; sección objetivo/uso, cláusula comercial).
- E9 https://www.corfo.gob.cl/sites/cpp/nacional/corfo-apuesta-por-impulsar-ia-biomedicina-y-terapias-avanzadas-para-convertir-a-chile-en-polo-de-innovacion-en-salud/ (`turn4search0`;identidad programa, enero fuera ventana). https://linktr.ee/transforma_salud (`turn8view0`;localizador) remite https://transformasalud.cl/corfo-y-uc-christus-lanzan-prisma-ia (403 `turn11view1`).
- E10 https://hl7chile.cl/ (`turn2view8`;última noticia3jul, agenda enero2027 sin fecha publicación) y https://hl7chile.cl/fhir/ig/clcore/ (`turn1search18`;superficie guías).
- E11 https://i-health.cl/ (`turn2view7`;nombre y seis fechas recientes).
- E12 https://i-health.cl/news/network-analysis-reveals-supplier-concentration-in-public-procurement-of-medical-equipment (`turn6view5`;23sep;metodología y DOI).
- E13 https://i-health.cl/news/artificial-intelligence-to-outline-breast-tumors-in-3d-synthetic-data-as-a-starting-point-when-clinical-data-are-scarce (`turn6view6`;24sep;limitaciones y DOI).
- E14 https://www.colegiomedico.cl/colegio-medico-se-suma-a-organizaciones-de-la-sociedad-civil-para-resguardar-programas-sociales-en-el-presupuesto-2027/ (`turn4search12`;1oct, evidencia oficial indexada).
- E15 https://www.colegiomedico.cl/colmed-plantea-a-suseso-preocupacion-por-criterios-de-fiscalizacion-de-licencias-medicas/ (`turn4search15`;1oct oficial indexado, fetch403 `turn6view2`).

Sin validación de permisos recurrentes, feeds, exhaustividad mensual ni contenido completo de Colmed/ADIMECH/Transforma. Estas limitaciones permanecen como gates de implementación; no se presentan como verificaciones aprobadas.

# ADDENDUM FINAL V2 · Dirección · 12 octubre 2026

## V2.0 Autoridad, alcance y secuencia de autorización

Este delta prevalece sobre instrucciones incompatibles del cuerpo v1 y anexos. Mantiene los siete entregables, las tres correcciones originales, nueve fuentes, prioridades CENS/iHEALTH condicionadas, reutilización Clínicas de Chile, alcance FONASA/ISP y stop-loss. No repite esas investigaciones. Base documental PR32 `5163f2fff1512587726cc5a0924598d2e5fa8ff7`; staging `ef8cbe3938623d493872ff5f3e717153f176d1be`. Mandato adicional: [Dirección, issue5 comentario6120684438](https://github.com/cftorre1/Radar-salud/issues/5#issuecomment-6120684438). No se cambia queue, PMO, contratos activos, contenido ni código.

**Secuencia vinculante: candidato documental final → Work6 auditor integral independiente → aceptación de Dirección → Codex H único → QA/reviewer → Integration Commander.** READY_FOR_WORK6 sólo significa documento apto para auditar; nunca autoriza Builder, publicación o merge. El prompt de §7 queda sustituido por V2.7.

## V2.1 Diagnóstico causal y contrato de conocimiento incremental

|Capa inspeccionada en staging|Hallazgo comprobable|Cambio especificado|
|---|---|---|
|`src/radar_salud/llm_analysis.py`, NORM_SCHEMA/NEWS_SCHEMA e instrucciones|what/why obligatorios; normativa además exige key_points/review_points y pide explicar antecedente en what. Máximo3 no es mínimo3, pero obligación de campos y guion favorecen repetir el mismo efecto.|Separar selección interna de redacción; arrays vacíos válidos; redactor recibe inventario único de claims y resultado completo, no encargos aislados por sección.|
|`regulatory_pipeline.py`|Copia what a key_facts y proyecta key_points, review_points→risk_notes; acumular representaciones no aporta evidencia.|Proyectar claims una sola vez en cada nivel; mantener raw legacy y trazabilidad sin renderizar todos sus espejos.|
|`editorial_gate.py`/contrato vigente|Penalizaciones de longitud y validación what/why pueden premiar completar plantilla.|Sustituir sólo en versión nueva por soporte, precisión y delta; mantener materialidad y reglas normativas especiales.|
|`editorial_committee.py:build_committee_artifact`|Enumera miembros, pero PASS puede derivar de URL, identidad y decisión; no prueba lectura independiente de documentos ni del texto final.|Etiquetar comprobación estructural. Receipt semántico separado con hash texto+evidencia y revisor distinto del autor.|
|`web/app.js:card/detail`|Qué pasó/Por qué importa antes de Ver resumen; luego Qué ocurrió/contexto/hallazgos/implicancias/riesgos. `distinct` no prueba novedad semántica.|Una ficha canónica, sin segundo resumen del mismo contenido; eliminación de bloques obligatorios y concatenación automática.|
|`web/global.js:theme/source` y `web/data/global_themes.json`|Razón de selección, patrón, uso ejecutivo y Chile son párrafos públicos obligados; análisis de fuente repite resumen/hallazgos/implicancias.|Contrato común de claims y módulos opcionales; conservar preguntas como criterios internos.|

La causalidad es conjunta: cambiar sólo el modelo o esconder encabezados conserva la repetición. No se ha demostrado que un proveedor/modelo determinado sea causa exclusiva. Tampoco que cada campo legacy sea malo: una limitación o referencia concreta sí puede añadir conocimiento.

**Regla por párrafo:** el editor registra qué aprende el lector respecto del nivel anterior y del resto del nivel actual. Si no hay respuesta sustantiva, elimina/fusiona/reescribe. Precisión jurídica y trazabilidad justifican repetir identificadores, sujetos, cifras o una breve cláusula de enlace; no justifican repetir conclusiones completas.

- Nivel1 Radar/Ponte/Global: título factual autosuficiente, fecha y fuente; deck opcional sólo si incorpora un hecho esencial nuevo.
- Nivel2 ficha: hechos adicionales con alcance, actores, base temporal y fuentes. Se admite ficha breve. Si sólo existe el título, mostrar fuente y limitación honesta, sin reclamar profundidad ni esconder la señal material.
- Nivel3 bajo demanda: fundamentos, comparación, metodología o documentos relacionados que añaden evidencia. Sin cupo de secciones, palabras, temas Global ni cifras. Cero módulos es válido.

Extender esquema v3 de §4 con `depth_modules[]` opcional (`id`, `label` descriptivo del contenido, `claim_ids`, `evidence_refs`), `paragraph_claim_ids` y `incremental_review[]` (`paragraph_id`, `compared_with`, `new_claim_ids`, `necessary_repeat_reason`, `verdict`). Los módulos referencian claims, no copian el body. Si un claim ya está en nivel2, nivel3 puede demostrarlo con fundamento nuevo identificado, pero no presentarlo como hallazgo nuevo. No almacenar aquí razonamiento privado del modelo: sólo justificación editorial breve y auditable.

### Decisión de producto: eliminar el paso «Ver resumen»

Título y Más info abren la misma ficha por `piece_id` en Radar, Ponte y Global. No más salto al feed, Contexto general, Ver contexto disponible ni Ver análisis completo como pasos necesarios. La ficha inicia con información incremental; el título puede repetirse como orientación de la vista y no cuenta como ganancia de información. Fuentes verificadas siempre accesibles, incluso sin módulo profundo.

|Elemento actual|Destino|
|---|---|
|Qué pasó/Qué ocurrió como encabezado|Eliminar obligación; su hecho nuevo se integra en body una vez.|
|Contexto/hallazgos con la misma proposición|Fusionar; descartar paráfrasis.|
|Por qué importa/Implicancias/Puntos de atención genéricos|Eliminar de público; selección y riesgos de revisión internos. Una consecuencia comprobada se conserva como claim.|
|Ver resumen|Sustituir por Más info a ficha; no renombrar conservando otra capa repetida.|
|Fundamentos o metodología sustantivos|Módulo bajo demanda con título específico («Fundamentos de la decisión», «Cómo se estimó el gasto»); nunca módulo vacío.|
|Referencias normativas|Permanecen con función explícita: acto impugnado, antecedente, disposición modificada o decisión posterior; enlaces directos originales y relación verificada.|
|Documentos densos|Primera vista breve, expansión accesible dentro de ficha; abrir no cambia identidad de pieza ni genera otro resumen.|

### Pruebas semánticas y gate

Comparar título↔síntesis, síntesis↔contexto, contexto↔hallazgos, hallazgos↔implicancias y ficha↔profundización; también comparar el conjunto acumulado de claims. La comparación por parejas sola no detecta un párrafo compuesto de duplicaciones dispersas. Ausencia de una sección opcional significa N/A, no fallo.

Determinístico: duplicado exacto normalizado, n-gramas, referencias faltantes, hashes, fechas, denominadores y unidades. Similitud es alerta, nunca rechazo automático. Preservar negaciones, números y operadores jurídicos durante normalización; una variación «rechaza/acoge» no es duplicado equivalente. Modelo/revisor compara proposiciones y soporte; no basta cambiar vocabulario. No agregar embeddings pagados al sprint.

Fixtures de aceptación: (1) «rechaza reposición»→«no acoge reconsideración» sin otro dato: REVISE; (2) mismo ID jurídico más fundamento art57 y su aplicación al caso: incremental válido; (3) US$942m repetido con universo/base temporal antes ausentes: conservar precisión y evaluar aporte del resto; (4) rechazo de reposición confundido con rechazo jerárquico: BLOCK; (5) nuevo detalle sin evidencia: BLOCK aunque diferente; (6) módulo que combina tres frases anteriores: REVISE; (7) fuente breve sin detalle: ficha breve sin módulo y sin badge de análisis; (8) informe con metodología/limitación nuevas: PASS aunque repita indicador. Verificar claves legacy y stock sin borrar receipts históricos.

Cada candidato tiene inventario de claims, versión de originales, redacción completa y revisión independiente. PASS exige cero afirmaciones materiales sin soporte, cero contradicciones jurídicas/fechas/bases y que cada párrafo público se clasifique como nuevo, enlace necesario o limitación sustantiva. Un resultado insuficiente queda REVISE/HOLD; no «se arregla» añadiendo texto.

## V2.2 Comité y uso eficiente de modelos

Flujo: extracción/caché → inventario de hechos y faltantes → decisión de materialidad → editor único del texto completo → revisor independiente con originales → gate/versionado → publicador autorizado. Especialista legal/datos sólo por disparador concreto. Dos roles reales no implican siete llamadas ni otro comité permanente.

Situación observada: runtime `llm_analysis.py` usa `RADAR_FAST_MODEL` con default `gpt-5.6-luna` y `RADAR_DEEP_MODEL` con default `gpt-5.6-terra`. No existe evidencia aquí de evaluación comparativa que autorice reemplazar Luna o desplegar Astra. Terra/Astra son roles/candidatos de routing; Builder debe resolver identificadores API autorizados y disponibilidad real del pipeline, sin inventarlos. No se hizo benchmark ni llamada pagada nueva.

|Trabajo|Ruta propuesta|Disparador/limitación|
|---|---|---|
|Extracción textual, entidades candidatas, fechas, referencias, hashes, dedupe|Determinístico reutilizable|OCR dudoso o fechas contradictorias quedan señaladas; regex no decide efectos jurídicos.|
|Noticia simple con evidencia suficiente|Luna actual o Terra si evaluación autorizada mejora coste por salida aceptada|Una redacción integrada; detección de paráfrasis en misma salida no equivale a revisión independiente.|
|Norma con varios recursos/actos, conflicto documental, fundamentos extensos|Astra o mayor capacidad autorizada|Ejemplo IF10670: separar peticiones, fundamentos y parte resolutiva. Escalar por complejidad, no por longitud sola.|
|Revisión final alto impacto, Insight y Global|Revisor independiente con fuentes completas; especialista si hace falta|Sesión/rol separado, sin recibir veredicto del autor como verdad. Mismo modelo puede repetir sesgos: originales y fixtures adversariales obligatorios.|
|Evidencia ausente, acceso bloqueado, presupuesto agotado|HOLD/manual|Un modelo potente no sustituye original ni permiso de gasto.|

Evaluación futura controlada, sólo con autorización pipeline: conjunto fijo de12 ejemplos existentes (4noticias,4normas,4datos/Global; incluir IF10670,534 y Reuters). Mismo paquete fuente, misma versión de prompt, evaluación ciega del texto completo. Medir errores factuales/jurídicos críticos, soporte por claim, ganancia por párrafo, omisiones materiales, fechas/denominadores, coste por candidato aceptado y latencia; registrar tokens/coste observado, no precios supuestos. Gate crítico0errores y100%claims materiales sustentados; rúbrica utilidad0–2 por caso, mínimo2 para promover portada. Elegir ruta de menor coste que supera gates; no declarar superioridad con esta muestra pequeña. Evaluación pagada queda posterior y no consume presupuesto por defecto.

Escalar sólo si complejidad normativa identificada, evidencia conflictiva legible o borrador falla por síntesis/interpretación reparable; falta de fuente no escala. Máximo una reparación y una escalada por candidato si autorizadas dentro del límite vigente; después HOLD, sin bucles. Conservar `allow_call`, ledger mensual, attempted/success/failed, `record_response`, response_id, modelo exacto, input/output hashes y lineage. Cache key incluye fuente+prompt+schema+modelo. Ningún cambio de modelo reinicia contadores. Los defaults del módulo (deep5/60, fast40/400) NO son necesariamente presupuesto operativo: daily-radar configura deep15/run180/mes y fast120/run1500/mes. Leer límites efectivos del workflow antes de cualquier llamada; nunca elevarlos. Como límites por número de llamadas no garantizan dólares al cambiar modelo, Astra requiere además reserva de coste/tokens dentro del presupuesto monetario autorizado; si no está definido, HOLD. Este documento autoriza0 llamadas del pipeline.

## V2.3 Global: corrección focal de IA y codificación

Pieza actual `global-ai-coding-payer-cost-2026`, en `web/data/global_themes.json` y copia `data/global/themes.json`: titular afirma que IA puede inflar gasto; cuerpo redondea a US$1.000m; referencia interna atribuye US$942m a BCBSA vía Reuters24-sep. Why, recurring_pattern, decision_use y chile_watch repiten posibles efectos/recomendaciones sin nueva medición. Scores comerciales98/99 no prueban calidad.

Comprobación nueva: [comunicado primario BCBSA](https://www.bcbs.com/about-us/association-news/bcbsa-analysis-ai-coding-tools-affects-healthcare-costs) indexado confirma estimación942m para BCBS entre2023–2025; GET oficial devolvió502, no se leyó informe técnico. [Reuters registrado](https://www.reuters.com/legal/litigation/ai-tools-generated-nearly-1-billion-extra-costs-blue-cross-insurers-say-2026-09-24/) no accesible en esta revisión: no certificar nueva lectura de su artículo. [Respuesta primaria AHA5-oct](https://www.aha.org/news/blog/2026-10-05-better-information-better-care-how-coding-supports-todays-complex-patients) sí leída: cuestiona que se revisaran historias clínicas o identificaran reclamaciones con IA; indica total acumulado de dos años y falta de denominador del gasto total. AHA es contraparte interesada, no árbitro neutral. Su respuesta posterior añade evidencia que la ficha actual no contiene.

**Borrador condicionado, no publicación:** «BCBSA estima US$942 millones adicionales por cambios de codificación; hospitales cuestionan su atribución a IA». Ficha: «La estimación corresponde a planes de Blue Cross Blue Shield, no al gasto sanitario mundial. AHA objeta que el análisis no acredita diagnósticos sin respaldo clínico ni distingue reclamaciones procesadas con IA. Es una controversia sobre documentación y reembolso; no una medición causal del efecto de la IA clínica en Chile». El título conserva atribución y desacuerdo; ficha añade universo y límites de identificación. La réplica AHA se atribuye expresamente.

Eliminar recomendaciones genéricas de qué debe hacer cada institución y Chile-watch vacío. Conservar magnitud exacta, autor, período y límites en una sola exposición. Antes de aprobar el overlay, recuperar por vía permitida el original técnico BCBSA para verificar muestra, período analizado frente a ventana de coste, base2023, contrafactual y denominador. No incorporar37→40%,55.000casos ni653m sólo desde reproducciones secundarias. Si el informe no está accesible, no activar «Cómo se estimó» y conservar ficha corta atribuida con carencia explícita. Estado del overlay HOLD_SOURCE_METHOD, sin nueva publicación; no bloquea especificación Work6. No declarar fraude, causalidad ni efecto en primas comprobado por esta ficha.

## V2.4 UX transversal adicional

Se preservan exactamente componente de sobres, `piece_id`, IndexedDB/migración atómica/tombstones, sincronización y persistencia aprobados en §3. Sobre cerrado=no leído; abierto=leído. Misma pieza en Radar/Ponte/Global, misma ficha; piezas editoriales distintas no comparten lectura por mera URL.

- Navegación principal: «Radar · Chile» y «Global · Evidencia internacional»; texto breve en cabecera explica alcance, no otra capa. Radar cubre hechos del sector chileno; Global evidencia internacional seleccionada con límites de transferencia. `aria-current=page`, estado activo además de color. El teaser Global en Radar conserva procedencia y abre la ficha Global canónica.
- «Volver arriba»: una única acción flotante del viewport, fuera de articles y dialogs, aparece al salir de vista cabecera/controles (IntersectionObserver, sin polling). Respeta safe-area, no cubre CTA/foco, se oculta con modal abierto; vuelve a cabecera y deja foco en destino lógico. Con reduced-motion no animar scroll. No repetirla dentro de cada ficha.
- Filtros: `+` inmediatamente al lado del texto «Filtrar u ordenar», dentro del mismo activador de expansión con área44px mínima; cambia a menos al expandir, estado accesible via details/summary o aria-expanded. No crear dos targets que hacen lo mismo. «Fuentes» conserva enlace/acción propia al catálogo y no se convierte en filtro: la confusión visual actual no autoriza cambiar semántica.
- Fuentes: página pública agrupada por organismos/reguladores, prestadores/industria, gremios/innovación/investigación y evidencia internacional/medios, con nombre enlazado y descripción breve de alcance. Reutilizar datos y acceso desde Fuentes; URL estable de catálogo, sin exigir nuevo framework. Elegibilidad por superficie operativa: ACTIVA + evidencia de acceso/captura válida vigente conforme política de esa fuente. Un estado histórico, HTTP200 sin parsing o señal antigua no acredita cobertura actual. Excluir PAUSED/BLOCKED/unknown. Parcial sólo si superficie concreta verificada y nombrada; no listar institución completa por un producto que funciona. Cero novedades con captura válida puede seguir activa. Si ninguna elegible, estado vacío honesto.
- `web/app.js` hoy filtra catálogo sólo por nombre y expone checked_at/última detección/selección. Nueva proyección pública por allowlist: nombre, URL oficial, grupo y alcance. Diagnósticos, polling, errores y motivos permanecen administración; no borrarlos de history ni source_health, ni enviarlos ocultos en DOM público. Deshabilitar una fuente no borra noticias históricas ni sus atribuciones.

QA futuro delta: desktop1440×900, móvil390×844,320px y zoom200%; teclado/lector de pantalla, foco de retorno, Esc y scroll modal; título largo íntegro,44px, contraste4,5:1. Verificar + al lado del texto en ambos anchos y que Fuentes no altere filtros. Scroll muestra una sola acción flotante sin solapar banners/CTA. Fixtures catálogo ACTIVEvalid/ACTIVEstale/PAUSED/BLOCKED/unknown/parcial/valid-empty y caída de carga; ningún interno se filtra a payload/DOM público. Dos pestañas, bfcache y reversión siguen QA §3; no repetir pruebas históricas del comportamiento viejo. Esto es contrato, no QA visual acreditado de una implementación inexistente.


## V2.5 Ficha corregida IF/N°10670: texto concreto y ganancia por nivel

**Título propuesto:** Resolución Exenta IF/N°10670: Superintendencia rechaza reposiciones de cinco isapres contra el cambio del informe EMP.

**Fecha:** emitida10-sep-2026. **Fuente:** Superintendencia de Salud. No rejuvenecer al12-oct por esta revisión.

**Primera vista de ficha (borrador):**

La Circular IF/N°531 trasladó el informe parcial que la Superintendencia entrega a las isapres: se elaborará una vez concluido octubre, evaluando enero–octubre, en lugar del primer semestre. Cambia la oportunidad de esa comunicación; no agrega metas ni nuevas cargas de reporte a las isapres. La circular rige desde su notificación. [C,III–IV,p2; R,considerando12,p7]

Esencial y Consalud también pidieron suspender la circular. La Intendencia rechazó esa petición porque no fundamentaron ni acreditaron el daño irreparable o la imposibilidad de ejecutar una eventual decisión favorable exigidos por el artículo57. [R,considerando7,p4]

Los recursos jerárquicos subsidiarios se remitieron al Superintendente para decisión. Esta resolución no los resuelve. Su desenlace posterior no fue verificado al12-oct; por eso la ficha describe lo decidido el10-sep y no afirma pendencia actual. [R,resuelvo1–3,p8]

Fuentes al pie: «Resolución IF10670 · decisión sobre recursos» y «Circular IF531 · modificación impugnada», con enlaces oficiales del expediente siguiente. No otro resumen de estos párrafos.

**Bajo demanda: «Qué solicitaron y por qué se rechazó»**

|Recurrente|Petición y argumentos que recoge la resolución|Localizador|
|---|---|---|
|Nueva Masvida|Dejar sin efecto531; subsidiariamente conservar revisiones de junio y octubre. Alega pérdida de margen correctivo, utilidad del seguimiento para metas vinculadas a adecuación de precios, retroactividad y confianza legítima por aplicación al ejercicio2026 ya iniciado. Señala contraste con archivos del10nov y notificación31jul como parte de su alegación.|R,c3,pp1–2|
|Cruz Blanca|Dejar sin efecto531; recurso jerárquico subsidiario. Sostiene que noviembre/diciembre no bastan para movilizar beneficiarios hacia EMP y que falta motivación suficiente conforme art11 de Ley19.880: un informe parcial no exige esperar evaluación más completa.|R,c4,pp2–3|
|Colmena Golden Cross|Dejar sin efecto531 y mantener oportunidad anterior; recurso jerárquico subsidiario. Invoca utilidad de comunicaciones2023–2025 para acciones correctivas y pérdida de meses de gestión.|R,c5,p3|
|Consalud|Dejar sin efecto o corregir531 manteniendo también informe del primer semestre. Alega menor tiempo correctivo, riesgo para cumplimiento habilitante de adecuación del precio base y utilidad de validaciones junio/octubre por medición de embarazadas en segundo semestre. También pide suspensión.|R,c6–7,pp3–4|
|Esencial|Reposición, jerárquico subsidiario y suspensión constan; los considerandos no individualizan sus argumentos de fondo. No atribuirle los de otras recurrentes.|R,c2,p1;c7,p4;resuelvo,p8|

Las posiciones anteriores son las recogidas por el regulador; no se obtuvieron los escritos completos de las isapres. Las alegaciones no son hechos jurídicos confirmados por Alicanto.

**Fundamentos de fondo adicionales:**

- El regulador considera que las isapres tienen metodología e información propia para seguimiento permanente; el informe parcial es una verificación metodológica, no sustituto de su gestión ni garantía de cumplimiento. [R,c9,pp4–5]
- El corte octubre permite observar mejor embarazadas, recién nacidos y reliquidaciones. El Manual2026, aprobado mediante Resolución5143 de11mayo, ya contenía ventanas de identificación anteriores a531. No se introducen esas ventanas mediante10670. [R,c10,pp5–6]
- Frente a falta de motivación, explica que no pretende equiparar informe parcial y final: busca datos observables que en junio estaban incompletos. [R,c11,pp6–7]
- Frente a retroactividad, razona que cambiar la comunicación no altera derechos/cargas ni efectos de actuaciones anteriores; las acciones para cumplir metas permanecen. Frente a doble validación, considera suficientes metodología y proyecciones propias y aplica eficiencia a la verificación del organismo. [R,c12–13,p7]

**Calendario y efecto exacto (no nuevos plazos inventados):**31jul2026 fecha de531; vigencia desde notificación, no desde su carpeta web/agosto. Nueva Masvida relata notificación31jul; no consta aquí prueba individual para todas las isapres.10sep2026 firma10670; no se acredita fecha individual de notificación. Corte enero–octubre e informe una vez cumplido décimo mes, sin día de emisión señalado.10nov aparece en argumento de recurrente sobre archivos y10ene2027 en fundamento sobre carga final de reliquidaciones; no son fechas nuevas creadas por la resolución. El acto rechaza reposición y suspensión, remite los jerárquicos sobre531, y no sanciona ni determina por sí mismo cumplimiento de metas o autorización de alzas. No presupone que esas materias ya estén definitivamente resueltas.

|Bloque propuesto|Información nueva frente al nivel anterior|Qué deja de repetirse|
|---|---|---|
|Título|Acto, emisor, decisión y sujetos/circular impugnada|No necesita explicación del informe completo.|
|Ficha párrafo1|Quién informa a quién; período anterior/nuevo; límite de efectos; regla de vigencia|No vuelve a listar el rechazo.|
|Ficha párrafo2|Petición cautelar separada, dos solicitantes y estándar art57 aplicado|No llama a todo «recursos rechazados».|
|Ficha párrafo3|Remisión jerárquica y límite temporal del conocimiento|No presenta rechazo como cierre definitivo.|
|Tabla bajo demanda|Peticiones y argumentos diferenciados de cada recurrente, carenciaEsencial|No resume nuevamente la parte resolutiva.|
|Fundamentos bajo demanda|Respuesta técnica/jurídica a objeciones y relación Manual5143→531→10670|No repite «deben cumplir» como conclusión empresarial.|
|Calendario bajo demanda|Distingue corte/emisión/notificación y procedencia de otras fechas|No promete informe durante octubre ni renueva fecha del acto.|

La tabla de ganancia es un control interno del handoff, no una sección que debe renderizarse al usuario. La ficha compacta admite estos tres párrafos porque cada uno añade una dimensión distinta. Los módulos profundos pueden fusionarse si el diseño conserva sus afirmaciones y locators.
### Expediente de comparación con la ficha actual IF10670

Corte de investigación: 12 octubre 2026. Delta respecto de V1. Auditoría de originales descargados y ficha congelada en staging ef8cbe39; no implementación. Se aplicó skill PDF para lectura y comprobación visual de disposiciones; no API de IA pagada.

## Respuestas a las siete preguntas

1. **¿Quiénes recurrieron?** Nueva Masvida, Cruz Blanca, Colmena, Esencial y Consalud. [R, considerando2, p1; resuelvo1, p8]
2. **¿Qué pidieron?** Nueva Masvida: anular o conservar junio/octubre; Cruz Blanca: anular; Colmena: restituir oportunidad previa; Consalud: anular o corregir. Esencial: reposición registrada, sin motivos individualizados. [R, considerandos3–6, pp1–3]
3. **¿Qué argumentos?** Menor tiempo correctivo; Nueva Masvida: retroactividad/confianza legítima; Cruz Blanca: motivación insuficiente; Colmena: utilidad histórica; Consalud: riesgo para adecuación tarifaria y doble validación. [R, considerandos3–6, pp1–3]
4. **¿Por qué rechazar reposiciones?** Seguimiento autónomo; mejor observación de embarazadas, recién nacidos y reliquidaciones; motivación técnica; sin nuevas cargas ni retroactividad; innecesaria doble validación. [R, considerandos9–13, pp4–7]
5. **¿Por qué rechazar suspensión?** Esencial/Consalud no acreditaron daño irreparable ni imposibilidad de ejecutar una eventual decisión favorable, exigidos por artículo57. [R, considerando7, p4; resuelvo2, p8]
6. **¿Qué quedó pendiente?** Jerárquicos remitidos al Superintendente, no resueltos aquí. Notificación31-julio alegada por Nueva Masvida; fecha efectiva de notificación de esta resolución no consta. [R, considerando3,p2; resuelvo3,p8]
7. **¿Qué cambia y desde cuándo?** Circular fechada31-julio: vigencia desde notificación. Cambia informe de Superintendencia, antes posterior al primer semestre; ahora posterior al décimo mes, evaluando enero–octubre. No fija día de emisión. [C, numeralesIII–IV,p2]

## Evidencia y trazabilidad

Páginas anteriores en numeración humana (1–8 / 1–2). Texto completo revisado; verificación visual adicional de p8 de R y p2 de C para separar resuelvo, vigencia y fecha de corte.

| Clave | Original oficial | Archivo local de evidencia | Bytes | SHA256 |
|---|---|---|---:|---|
| R | https://www.superdesalud.gob.cl/app/uploads/2026/09/res-exenta-if-n10670-2026.pdf | v2-if10670.pdf | 2772571 | 33b264702a6cd5209eac7e64aab27d4f9876510b8b665f1062bdd616b52e2509 |
| C | https://www.superdesalud.gob.cl/app/uploads/2026/08/circular-if-n-531-2026.pdf | v2-if531.pdf | 511935 | e4908364b387a2db27ec9e6685ca6971012eeafa8ba504ad1619de07989f47b5 |

Fichas oficiales: https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n10670/ y https://www.superdesalud.gob.cl/normativa/circular-if-n531/ . La fecha estampada de R es10-septiembre, no el1-septiembre que devolvió un metadato de buscador. No deducir la fecha jurídica desde /08/ del alojamiento de C.

## Comparación de backend: problemas demostrados

`web/data/radar_today.json` contiene un registro coincidente por source_url. Huella canónica del registro (JSON UTF8, sort_keys, ensure_ascii=False, separadores coma/dos puntos): `9a0dafd63485fa8dac09d7a18d2ef568e8cf31c0193cdc070226c70b3120c074`.

`data/history/superintendencia_signals.json` contiene un registro de misma URL con hash `260e2f6146469de8cef6623efb219fd26a84bc0e595c049d7e05607d44904b0d`. Sus estructuras no son idénticas: no hacer reemplazo ciego ni suponer que cualquier discrepancia es error.

| Campo actual exportado | Diagnóstico y cambio requerido |
|---|---|
| `title` sólo número de resolución | Identidad jurídica sin hecho explicativo. Conservar como identidad; mostrar título factual. |
| `display_title` extenso, referencia a “junio a octubre” | Precisar corte, no fecha garantizada de comunicación. |
| `why_it_matters` / `required_change`: “se emitirá en octubre” | Error temporal frente a C, numeralIII. Sustituir por corte a octubre y emisión posterior al cierre de ese mes. |
| `related_context[0].summary` | Ya contiene correctamente “una vez cumplido el décimo mes”. La información existe, pero otra capa la degrada. |
| `key_facts[0]` idéntico a `what_happened` | Duplicación exacta; no es profundidad adicional. |
| `normative_editorial.business_subject` idéntico a `legal_action` | Campos distintos almacenan la misma explicación. No tratarlos como dos aportes. |
| `editorial_committee.public_title` | Texto truncado/agramatical: “Las isapres recurrentes deben operar bajo la mientras se resuelven”. Rechazar aun si otra capa muestra un título correcto. |
| `normative_context`: “siguen pendientes” | Estado actual no acreditado por una resolución histórica. Formular “remitidos en esta resolución; desenlace posterior no verificado”. |
| `effective_date_or_status=null`, `validity_text=null` | Contradice la seguridad aparente del texto vigente; exigir estado fechado y evidencia. |
| `publication_ready_score=100`, comité PASS, `critical_objections=[]` | Falso positivo de calidad: no detecta contradicción temporal, mala sintaxis ni repetición entre campos. |
| `source_documents` sólo R | Incorporar C como original de la modificación; URL de una norma relacionada no reemplaza fragmento verificable. |

### Autoridad de la corrección

El único texto propuesto para la ficha es la primera vista de V2.5 y sus módulos. Este expediente documenta el diagnóstico y no introduce una segunda ficha ni otro título. Mantener identidad y lectura; contrastar huella vigente antes de preparar overlay. Esta propuesta no autoriza publicación ni actualización automática de fecha.

## Límites y comprobaciones pendientes

- Se buscaron resoluciones posteriores por combinación de531, jerárquicos y Esencial en sitio oficial; no se localizó un desenlace posterior. Ausencia de resultado de búsqueda no certifica pendencia actual. No afirmar cierre definitivo de vía administrativa.
- Los escritos originales de cada isapre no fueron obtenidos: las posiciones están resumidas por la autoridad. Diferenciar “la resolución recoge” de “la isapre escribió”, y citar considerarandos, no presumir acceso al expediente.
- No convertir la fecha de firma de R en fecha probada de notificación. Para calendarios exigibles individualmente se necesita constancia de notificación.
- No verificado en esta revisión el Manual5143 completo ni cada tabla del Compendio vigente. C acredita su modificación histórica; una afirmación consolidada a hoy requiere cotejo actualizado del Compendio y decisiones posteriores.
- La ficha no debe extraer nuevas metas cuantitativas, aranceles, sanciones o permisos de adecuación desde este acto. Separar decisión del recurso, regla original, calendario y efectos de seguimiento.

## QA mínimo V2

1. Fallar si una superficie dice emisión “en octubre” y otra “una vez cumplido octubre”.
2. Fallar si suspensión y reposición comparten una razón genérica sin diferenciar sus fundamentos.
3. Fallar si Esencial recibe argumentos individualizados no encontrados en el original.
4. Fallar si remisión histórica se convierte en estado procesal actual sin `verified_at` y evidencia posterior.
5. Fallar si cualquier título canónico/exportado queda agramatical, aunque el componente principal utilice otro campo.
6. Pasar sólo con mapa afirmación→documento→página/considerando y revisión editorial independiente de la nueva síntesis.
## V2.6 Circular 534 y contrato temporal normativo

Revisión focal 12-oct-2026. HEAD observado al cierre: `860d95baf3b7db3e8c28493a0edfd2ffe371ab60` (árbol compartido actualizado desde la revisión UX anterior). No modificación de código ni llamadas pagadas. Evidencia externa original abierta nuevamente; conclusiones UI de este addendum son derivadas del código, no nueva sesión browser.

## Circular 534: sí está en backend y feed

|Etapa|Prueba y dictamen|
|---|---|
|Original|PDF oficial de cuatro páginas, Circular IF/N°534, fecha de emisión 14-sep-2026. Página normativa oficial muestra 14-sep-2026.|
|Discovery|No se identificó en esta revisión un evento histórico individual de discovery con timestamp. Eso no prueba ausencia de captura: seen/history la acreditan. `detected_at=null` impide afirmar detección LIVE.|
|Seen|`data/state/superintendencia_normativa_seen.json` incluye SHA256 `929d164f2e1f889bb2c7a79f5d65c8654cca4e21a0d2ebd86a652f0e752bedd3`, calculado mediante la función real `scouts._fingerprint`: slug + URL + título Circular IF/N°534. No buscar URL literal dentro de un archivo de hashes.|
|Queue|No hay entrada exacta de su URL en `data/state/pending_queue.json`; no es una señal pendiente actual. No inferir fallo.|
|History|Presente en `data/history/superintendencia_signals.json`, con what, why, tres key_points, PDF, vigencia y antecedentes. Título histórico opaco; existe recuración posterior.|
|Decisión|Feed: `editorial_decision=accept`, `publication_ready_score=100`, `feed_visibility=true`, comité PASS. Acredita dictamen persistido; no demuestra por sí solo revisión humana independiente. `config/df_integration_controls.json` conserva DF1-oct como corroboración duplicada del evento oficial14-sep.|
|Feed|Presente en `web/data/radar_today.json` con display_title explicativo y contexto normativo. `distribution=archive` no significa excluida: `individualCardAllowed` no consulta ese campo.|
|UI|`triageTitle` prioriza display_title. `visible` exige filtros+periodo+contrato. A 12-oct, 14-sep tiene28d: elegible30/60d; no14d. Si leída, desaparece solo de inbox y permanece feed. Filtros scope/type también pueden ocultarla. No hay evidencia para diagnosticar «colector no la capturó».|

Originales:
- https://www.superdesalud.gob.cl/app/uploads/2026/09/circular-if-n-534-2026.pdf (páginas1–4).
- https://www.superdesalud.gob.cl/normativa/circular-if-n534/ (fecha visible y PDF).

## Delta sustantivo verificado y propuesta editorial

**Título:** Circular IF/N°534: isapres deberán emitir bonos con cédula si fallan la huella y la validación auxiliar.

**Ficha propuesta:** Rige desde el 1 de diciembre de 2026. Complementa la Circular476 y modifica el Compendio de Beneficios. Las regularizaciones deben realizarse después de la atención. Exige registro de los casos, protocolo interno disponible para fiscalización y comunicación escrita de las decisiones sobre regularización. Si el impedimento es permanente, las medidas también deben ser permanentes. La isapre mantiene responsabilidad sobre protección de datos cuando usa proveedores tecnológicos.

**Evidencia:** PDF p1 antecedentes; p2 contingencia; p3 registro, protocolo y comunicaciones; p4 vigencia y proveedores. **Omitir:** extrapolaciones de ahorro, tasas de rechazo o sanciones que el documento no cuantifica. No confundir vigencia futura con obligación ya exigible al12-oct. Esta ficha aporta detalle real sobre el título; no requiere un bloque fijo de «importancia».

## Contradicciones y oportunidades temporales verificables en stock 30/60d

1. **IP7462:** feed `event_date=emission_date=2026-09-23`, `publication_date=null`, observación de listado `2025-09-23`, hecho `2023-05-02`. La reconciliación primaria ya existe (`verified_primary_emission`): no deshacerla ni declarar el año2025 válido. `sourceTiming` distingue emisión/publicación desconocida en ficha, pero la fila de Ponte usa únicamente `event_date`, sin etiqueta de base. Dos fechas diferentes no son automáticamente contradicción: hecho2023 y acto2026 son dimensiones distintas. Debe mostrarse «Emitida23sep» y, en profundidad, hecho2023; no «fiscalización reciente» por inferencia.
2. **IF9774:** emisión/publicación20-ago-2026, `fact_period` identifica fiscalización enero2025 y recurso contra acto julio2025. Está dentro de60d al12-oct (53d), fuera de30. No equivale a infracción ocurrida en agosto2026. La ficha renderiza sourceTiming, pero no tiene render específico para fact_period: dato capturado puede quedar invisible.
3. **Pulso Prestadores30d:** tres publicaciones15-sep, actos emitidos3/8sep. Su agrupación por publicación está declarada y puede ser válida, aunque los actos por emisión estén fuera de30d. No mezclar denominadores «actos emitidos» y «publicaciones». Al12-oct todavía cumplen30d por publicación; deben migrar/expirar al avanzar reloj. Exigir fecha de corte visible para que «últimos30d» no envejezca en un snapshot.
4. **Pulso Prestadores31–90d:** seis publicaciones, cuatro21-ago y dos5-ago; en una vista60d la tarjeta agregada entra por21-ago, pero dos componentes5-ago quedan fuera60d. El filtro evalúa únicamente fecha máxima de tarjeta, no miembros. Solución de bajo esfuerzo: rotular siempre ventana propia del agregado y corte; no presentar el número como resultado del filtro60d. Alternativa posterior: recalcular miembros y denominador según filtro. Nunca sumar UF y UTM sin conversión fechada.
5. **Reloj:** `ageDays` usa díaUTC para fechas puras mientras weekly freshness usa America/Santiago. Entre medianocheUTC y medianocheChile puede cambiar la pertenencia30/60d antes del cambio local. No se afirma fallo visual observado; se acredita divergencia en implementación. Unificar calendarioChile y documentar límites inclusivos (`<=30` actualmente permite31 fechas calendario si se incluye hoy).
6. **Fuente primaria oculta:** Circular534 conserva PDF en source_documents, pero detailHtml no itera ese array; presenta source_url de landing y related_context sin links verificados. El documento original existe y puede ser expuesto como «Circular original · PDF», evitando clic adicional y sin fabricar enlaces.

## Contrato normativo y de sanciones V2

Separar siempre: `issued_on` (acto), `published_on` (publicación comprobada), `fact_period` (hecho fiscalizado), `inspection_period` (fiscalización), `effective_from/until` (vigencia), `detected_at` (sistema). No completar unas a partir de otras. Mantener `event_date` por compatibilidad pero exigir `event_date_basis` y evidencia por fecha. Lo desconocido permanece null. `observed_listing_date` conflictivo se conserva como observación, no fecha canónica.

Título: acto+identidad+actor+sujeto+cambio. Ficha: cambio frente a antecedente, sujetos obligados, alcance, vigencia/plazo, obligaciones verificadas y enlaces primarios; separar resolución de recurso del acto original y no hacer que la resolución parezca creadora de una obligación preexistente. Hechos y sanción no son equivalentes a firmeza: estado procesal se conserva y no se inventa.

**Regla vinculante de sanciones:** `issued_on`, verificado contra resolución original, determina `event_date`, orden y frescura del acontecimiento sancionatorio. No hacer fallback a inspección, período, publicación ni first_seen. Si falta emisión, evento queda sin fecha verificada y fuera del ranking de sanciones recientes; puede mostrarse publicación reciente en una vista separada, rotulada como tal, sin llamar nueva a la sanción. Resolver contradicción índice/PDF a favor del original legible y conservar ambos valores y fundamento; ambigüedad no resuelta queda HOLD_DATE. Recaptura nunca cambia emisión. Los agregados históricos por publicación se conservan como «publicaciones oficiales», con ventana propia; no cuentan como sanciones emitidas dentro del filtro30/60d. El caso PulsoPrestadores30d descrito arriba es diagnóstico del agrupamiento heredado, no excepción a esta regla. Separar además `inspection_date` cuando haya día exacto y `inspection_period` si es intervalo; ambos distintos de período de hechos fiscalizados.

Para agregados: `window_start`, `window_end`, `window_basis`, `generated_at`, lista de IDs de miembros, unidades y `count_basis`; mostrar corte real. El usuario debe distinguir publicación reciente de acto reciente y de hecho reciente. Tests focales: IF534 incluida30d/no14d; IP7462 conserva publicaciónnull; IF9774 fiscalización2025 visible; agregado31–90 en filtro60 no se presenta como60; borde medianocheChile; clicPDF válido. No repetir backfill ni recaptura masiva.

## V2.7 Backlog focal y prompt sustituto de Codex H

Se conserva techo propuesto20h, sin sumar silenciosamente nuevas obligaciones. Reordenar antes que ampliar: núcleo editorial/normativo/UX consume prioridad; pilotos nuevos de fuentes se difieren si no caben. CENS/iHEALTH conservan prioridad estratégica y contrato, no promesa de ejecución este sprint.

|Tarea independiente|Tope|Dependencia / salida|
|---|---|---|
|H0 conciliación SHA/queue/PMO/contratos y alcance|0,5h|Work6 aceptado + autorización Dirección; sin eso no ejecutar.|
|H1 ficha canónica, eliminación resumen duplicado y etiquetas, navegación/+/flotante|3h|Reutilizar renderer; pruebas rutas/accesibilidad.|
|H2 sobres/store/migración aprobados|3h|No simplificar a Set obsoleto; evidencia concurrencia.|
|H3 esquema v3, proyección legacy y gate receipt, contrato flexible Global|4h|No implementar evaluador semántico universal; fixtures con PASS/REVISE.|
|H4 overlays/fixtures IF10670,534,Global y tres casos originales|2h|Sólo documentos/fixtures; respetar HOLD de fuente, no publicar.|
|H5 fechas sanción/reconciliación focal, trazabilidad534|2h|Sin backfill90d ni regeneración pagada; conflictos quedan auditados.|
|H6 catálogo público allowlist + alcance FONASA/ISP|2h|No falsificar actividad; conciliar PR29; administración conserva diagnóstico.|
|H7 QA focal y reviewer del SHA|2,5h|Evidencia desktop/mobile y contratos; riesgo abierto explícito.|
|H8 reserva para defectos críticos|1h|No consumir en nueva fuente mientras haya fallo P0.|

Suma20h. Recuperación Clínicas y spikes CENS/iHEALTH del backlog original conservados en cola siguiente, o sólo con capacidad liberada verificable y autorización de alcance por Commander; no nuevas horas implícitas. Mejoras posteriores: benchmark pagado autorizado de modelos, instrumentación coste monetario si faltante, relectura semántica progresiva del stock, fuentes adicionales. Al vencer timebox cerrar con artefacto y bloqueo, no rebajar gates.

```text
CODEX H ÚNICO · EJECUCIÓN CONDICIONADA
Antes de actuar: exigir receipt Work6 sobre versión final de PR32 y aceptación
explícita de Dirección. READY_FOR_WORK6 no es autorización. Si faltan: STOP.
Base staging fresca; rama aislada; Work3 único integrador. Lee este handoff V2,
issue5 últimas decisiones y Work6. Precedencia V2 sobre §7 y anexos antiguos.
No tocar main/prod ni fusionar staging. No publicar señales, ejecutar modelos
pagados, capturas masivas, backfill90d ni repetir auditorías acreditadas.
H0: concilia HEAD/queue/PMO/contratos; preserva cambios ajenos con guard.
H1–H2: implementa ficha única y UX V2.4, lectura exacta §3; no cambies identidad
por copy ni publiques una migración parcial Home/Global.
H3: esquema compatible y receipt semántico final, claims/módulos opcionales;
no mínimos de palabras/campos públicos redundantes. Normas mantienen identidad,
organismo, sujeto, objetivo, cambio, efecto/vigencia; art57 no igual recurso
jerárquico. Raw outputs/receipts históricos inmutables.
H4: fixtures/overlays revisables basados en originales y delta por párrafo;
no escribir history/feed/latest/approved para publicar. Global pendiente de
metodología queda HOLD_SOURCE_METHOD. No inventes motivo individual Esencial.
H5: audita captura534 sin duplicar; separa emisión sanción/publicación/inspección/
período/first_seen; recaptura no rejuvenece. Conflicto PDF/índice se registra.
H6: catálogo sólo superficies activas verificadas; sin técnicos en público.
FONASA noticiasP0; ISP vigilanciaP0. Sin bypass/relajarTLS ni rescatar todoP1.
H7: tests adversariales de delta y QA desktop/mobile; revisor independiente
sobre diff final y evidencia original. Recibos con hashes, consumo0 pipeline.
Respeta timeboxes20h; nuevos colectores/benchmarks se difieren, no absorben P0.
Entrega un PR revisable por tareas, SHA y riesgos a Work3. No merge/publicación.
```


# COMPLEMENTO FINAL · Estadísticas · 12 octubre 2026

## E1. Autoridad y revisión focal

Mandato: [Dirección, PR32 comentario6121104768](https://github.com/cftorre1/Radar-salud/pull/32#issuecomment-6121104768). Base aprobada `ef41c9fd3b8fa4724a3b2273d94f40e638c2e813`; staging reconsultado `ef8cbe3938623d493872ff5f3e717153f176d1be`. Este complemento añade un contrato especializado de datos a v3 y una tarea estadística a Codex H. Preserva íntegros V1/V2, evidencias, hallazgos abiertos y gates; no repite auditorías de normativa, noticias ni Global. No se modifica código ni contenido publicado.

Caso inspeccionado: `Pulso Isapre · datos a 2026-07` en `web/data/radar_today.json`, `data/excel/validated_series.json`, `isapre_pulse.py`, `isapre_insights.py`, `scripts/validate_isapre_workbooks.py` y proyección `web/app.js`. Diagnóstico focal: `build_pulse` escribe los mismos hechos en what/why, tabla, data_insights y data_insight_evidence. El renderer ofrece fórmulas en primera vista salvo flag de metodología; el registro no tiene `methodology_visibility=collapsed` ni `statistical_value_level=deep_analysis`. Por eso no basta renombrar Ver resumen. La columna «Lectura» vuelve a explicar lo que los indicadores ya dicen. Truncamiento mobile reportado por Dirección; esta revisión no afirma haber ejecutado nuevo browser QA.

## E2. Evidencia original y comparabilidad comprobada

Se descargaron por HTTPS los tres XLSX oficiales referenciados por el pulso, en lectura exclusiva. Sus bytes coinciden con hashes anteriores; no se ejecutó pipeline/publicador ni IA pagada. Validación determinística de totales enero–julio reutiliza funciones read-only del validador existente; además se extrajeron filas por código de isapre, se contrastaron extremos y se verificaron sumas. Leer hojas Notas permitió confirmar provisionalidad, definiciones y límites de movilidad.

|Serie y original|SHA256|Localizadores del caso|
|---|---|---|
|[Cartera2026](https://www.superdesalud.gob.cl/app/uploads/2026/08/estadistica-mensual-de-cartera-de-beneficiarios-2026.xlsx)|`bff79f5f67785da49e1e899d0a2f8c91479a1a14a33f205e4d9d0f0fddd1dbec`|Hojas Enero…Julio: A4 período; A6:E6 encabezados; A8:E14 abiertas; A16:E18 cerradas; C20:E20 sistema. Notas2–6.|
|[Suscripciones/desahucios2026](https://www.superdesalud.gob.cl/app/uploads/2026/08/estadistica-mensual-suscripcion-y-desahucios-2026.xlsx)|`dbffd33734c67d1272e76fab6423a5f0372cf81f5715801acb725f0cf56d27f6`|Julio, C20/D20 totales suscritos/voluntarios; Notas1–5 explican movimientos contractuales y otras causales.|
|[Movilidadjulio2025–julio2026](https://www.superdesalud.gob.cl/app/uploads/2026/08/estadistica-mensual-de-movilidad-de-cotizantes-202607.xlsx)|`851222149779fb792b699b5c47ed36b0ec0e413214f10c0d3d63d1c6fa23f0e7`|Nacional A3 cortes; D19 salidas, D31 entradas, D43 diferencia; Notas1–8.|

Notas comunes: información provisional, proveniente de archivos maestros enviados por isapres, susceptible de revisión posterior. Cartera mide cotizantes/cargas con beneficios vigentes. Movilidad compara presencia entre dos cortes: no cuenta todos los movimientos ocurridos durante doce meses; entradas y salidas del sistema no equivalen a cambios entre isapres, y no acreditan destino Fonasa. La ficha no debe transformar inferencias de destino en hechos observados.

La [landing actual de cartera](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) declara actualización a agosto2026 y publicación2-oct. Se preserva la versión julio del caso y su fecha de publicación7-sep registrada en evidencia previa; esa fecha histórica no queda nuevamente probada por una landing mutable. No llamarla «últimos datos» ni reemplazar archivo, fecha, hash o receipt silenciosamente. La actualización a agosto se deriva al pipeline normal, fuera de este complemento, sin nuevo backfill. Hojas futuras vacías no acreditan serie completa por existir su nombre.

## E3. Contrato editorial estadístico: mostrar relaciones, no repetir frases

El contrato de claims v3 se aplica a números y representaciones. Cada métrica tiene un único cálculo y origen, compartido por KPI, gráfico, tabla accesible y metodología. Repetir un valor para orientación/accesibilidad es necesario; repetir la conclusión en cinco párrafos no añade conocimiento.

|Nivel|Diseño y aporte exigido|
|---|---|
|Bandeja|Título factual con período y un hallazgo material. Sin un deck que lo parafrasee. Fecha de publicación separada del período de datos.|
|Ficha inicial|Representación elegida según hallazgo. Para este Pulso:2–4 KPI coherentes de una misma familia/período, sin rellenar hasta cuatro. En cualquier otra pieza puede bastar un indicador, tabla, anotación/texto o ninguna tarjeta. Gráfico de evolución únicamente con serie completa verificada; tabla alternativa sólo si aporta valor. Valores, unidad, universo y referencia temporal visibles.|
|Comparación institucional|Tabla/ranking por entidad cuando existan datos comparables y verificados, total sistema separado y cobertura declarada. Añade heterogeneidad que el promedio agregado oculta. No ranking a partir de participaciones supuestas.|
|Otras familias|Vistas separadas, cada una con período, población/unidad y límite visible propio. Nada de eje común para stocks, contratos y movilidad.|
|Metodología y fuentes|Panel secundario con fórmulas, celdas, fuente original, hash/versiones, bases, validaciones y definiciones. Cerrado inicialmente, accesible por teclado. Sin volver a narrar cada indicador.|

Eliminar «Hallazgos», «Cálculos» e «Implicancias» como bloques simultáneos que repiten tabla/KPI. Una interpretación sólo permanece si aporta otra comparación o conclusión sustentada, con premisas y límite; no recomendaciones evidentes de seguir datos. Quitar «base de ingresos» inferida desde cotizantes/cargas: esa composición no mide ingreso ni causalidad.

### Regla adaptativa para toda inteligencia estadística

Conciliación focal con [precisión posterior de Dirección6121281277](https://github.com/cftorre1/Radar-salud/pull/32#issuecomment-6121281277), detectada durante Reviewer. Pulso es un caso de prueba, **no plantilla universal de KPI+línea+ranking**. Aplica también a FEFI, licencias, estados financieros, epidemiología, listas de espera y presupuestos; no requiere investigar esas fuentes ahora.

Flujo editorial de Datos/BI/estadística/economía sanitaria, como responsabilidades concretas del editor y revisor existentes:

1. Perfilar fuente, cobertura, periodicidad, unidad, universo, denominador, definición y revisiones. Clasificar stock/flujo/tasa/proporción y cambios metodológicos; conservar nulos y calidad.
2. Explorar determinísticamente candidatos: tendencias, cambios, brechas por entidad/territorio, composición, anomalías, concentración, ciclos y contradicciones. Cada candidato conserva inputs/fórmula y limitaciones. No automatizar búsqueda irrestricta de patrones ni llamar significativa una anomalía por umbral sin tamaño muestral/metodología. Ciclos requieren historia suficiente; concentración exige universo íntegro; tasa exige denominador válido. Un cambio puede ser revisión administrativa.
3. Seleccionar por novedad frente a piezas anteriores, materialidad/magnitud, robustez y utilidad concreta. Sin cuota de hallazgos; si ninguno pasa, no publicar tarjeta. Separar observación de interpretación, sin fabricar causas.
4. Elegir representación después: KPI para magnitud puntual; línea para evolución comparable; barras para brechas; distribución para dispersión con datos individuales/agrupados suficientes; tabla para comparación exacta; anotación o texto para un cambio metodológico. No forzar gráficos, ranking ni2–4KPI en el contrato general. Cero visualizaciones es válido.
5. Redactar sólo lo que la representación no comunica, separar metodología reproducible y pasar revisión independiente del conjunto.

Agregar `finding_candidates[]` con tipo, input_refs, robustez, materialidad, novelty_refs, selección/motivo; `chosen_representation` opcional con razón de ajuste al hallazgo. Estos campos son internos y no nuevas secciones públicas. El renderer acepta módulos opcionales, no espera siempre KPI/chart/entity_table. Parsers y cálculos determinísticos; Terra/modelo económico sólo síntesis propuesta si disponible y autorizado; Astra sólo complejidad/contradicción/alto impacto conforme V2.2, conservando receipts y presupuesto. Cero llamadas nuevas autorizadas.

Prueba anti-sobreajuste adicional: existen referencias FEFI en history (marzo2026 y períodos2025), pero no se acreditó aquí una serie numérica FEFI verificada; no fabricar gráfico financiero. Usar como segundo fixture estructural el dataset existente `data/epidemiology/respiratory_pressure_2026.json`, SE37: contiene una contradicción documental registrada de positividad53,7% frente a56,7%, además de porcentajes con universos distintos. Resultado esperado del nuevo contrato: HOLD de ese indicador mientras no se resuelva la contradicción, ningún rankingisapres, ningún gráfico longitudinal inventado, ninguna suma de porcentajes heterogéneos. Es prueba negativa de compatibilidad con evidencia histórica, no revalidación del PDF ni nuevo hallazgo publicable. Work6/Builder debe además aplicar el selector a una familia distinta con evidencia aprobada (preferir FEFI si se acredita serie) y registrar representación elegida y razón; si falta evidencia, HOLD y prueba de vacío, no PASS de cobertura FEFI.

### Ejemplo factual de primera vista, sin publicar

**Título:** «Beneficiarios de isapres disminuyen en cada mes de febrero a julio de 2026».

**Etiqueta:** Sistema Isapre · datos provisionales · enero–julio2026. Fuente: Superintendencia de Salud. No lleva párrafo de resumen repetido.

|KPI|Valor|Referencia visible|
|---|---:|---|
|Beneficiarios|2.487.497|Julio2026; personas con beneficios vigentes|
|Cambio desde enero|−26.541|Enero→julio2026; diferencia de stock|
|Variación desde enero|−1,06%|Base enero2026:2.514.038|

Gráfico de línea «Beneficiarios · enero–julio2026», siete puntos oficiales: enero2.514.038; febrero2.510.385; marzo2.504.837; abril2.498.649; mayo2.493.684; junio2.489.258; julio2.487.497. En esta versión sí hay serie completa verificada; seis comparaciones mensuales negativas no significan siete caídas. EjeY con unidad «personas» o «millones de personas» claramente indicada, ticks y límites visibles; si rango acotado, declarar «eje no inicia en cero», sin exageración gráfica. Sin suavizado, proyección ni doble eje. Leyenda «Beneficiarios»; texto alternativo describe evolución y referencia a tabla accesible de siete observaciones. La tabla equivalente puede estar bajo «Ver datos del gráfico», sin ser otro bloque de conclusiones.

El título comunica continuidad de caída; KPI aportan tamaño/base; el gráfico aporta trayectoria y ritmo; el desglose siguiente añade diferencias institucionales. No volver a escribir esos cuatro aportes en «Por qué importa».

### Desglose verificado: decisión IMPLEMENTABLE, con grupos explícitos

Hay diez códigos coincidentes entre enero y julio: siete abiertas y tres cerradas. Sus conteos reconcilian con totales; no hay filas ausentes en este ejemplo. Comparabilidad contable de stocks sí; equivalencia de mercados/clientelas o calidad de gestión no. Presentar grupos separados, sin ranking competitivo conjunto de abiertas y cerradas. No omitir Isalud ni otras instituciones pequeñas. Mantener todas las filas accesibles sin cuotas editoriales.

Tabla de especificación desktop; no reproducir esta anchura sin adaptación mobile. Δ es beneficiarios julio menos enero; porcentaje usa base de cada entidad en enero, no total sistema.

|Isapre (código)|Cotizantes jul|Cargas jul|Beneficiarios jul|Δ ene→jul|Δ %|
|---|---:|---:|---:|---:|---:|
|**Abiertas**||||||
|Colmena Golden Cross (67)|363.526|201.038|564.564|−9.033|−1,57%|
|Cruz Blanca (78)|223.084|131.318|354.402|−6.241|−1,73%|
|Vida Tres (80)|80.285|59.557|139.842|−933|−0,66%|
|Nueva Masvida (81)|193.635|104.073|297.708|+3.740|+1,27%|
|Banmédica (99)|322.333|224.599|546.932|−18.549|−3,28%|
|Consalud (107)|295.872|162.679|458.551|−20|−0,0044%¹|
|Esencial (108)|34.857|23.728|58.585|+5.712|+10,80%|
|**Cerradas**||||||
|Isalud (63)|19.800|19.779|39.579|−911|−2,25%|
|Fundación (76)|15.970|10.297|26.267|−255|−0,96%|
|Cruz del Norte (94)|511|556|1.067|−51|−4,56%|
|**Total sistema**|**1.549.873**|**937.624**|**2.487.497**|**−26.541**|**−1,06%**|

¹ Mayor precisión excepcional para no presentar caída como0,00%. En UI puede rotularse «caída<0,01%» con valor preciso accesible; nunca «sin cambio». Orden inicial por beneficiarios descendente dentro de cada grupo; controles para Δpersonas y Δ%, asc/desc con `aria-sort`. Ordenar por valores crudos, no texto redondeado. Total no participa del ranking, permanece identificado como sistema completo aunque usuario filtre un grupo. Si se muestra subtotal de filtro, nombrarlo explícitamente.

Esta tabla sí añade conocimiento: el descenso agregado no implica descenso en cada institución; Nueva Masvida y Esencial aumentan en esos cortes. No inferir transferencias entre ellas, causalidad comercial, mejores prestaciones, rentabilidad ni flujo de caja. Porcentajes de bases muy distintas no son ranking de desempeño. No sumar porcentajes individuales ni promediar sin ponderación para obtener sistema.

### Vistas adicionales, nunca mezcladas con cartera

- **«Contratos · julio2026»**:19.716 suscripciones y15.172 desahucios voluntarios. Tabla simple indicador/contratos; advertencia visible «Desahucios voluntarios no incluyen todas las terminaciones». La resta+4.544, si se consulta, se llama brecha parcial, nunca saldo neto de cartera. No convertir contratos en personas; no mostrar+19.100 acumulado enero–julio dentro de esta vista mensual.
- **«Movilidad · cortes julio2025 y julio2026»**:91.963 cotizantes presentes sólo en corte final;109.663 presentes sólo en inicial; diferencia−17.700. Advertencia visible «Comparación entre cortes; no variación mensual ni conteo de todos los movimientos intermedios». No sumar este saldo a cambio enero–julio de beneficiarios. El workbook inspeccionado desagrega por edad/sexo/región, no ofrece ranking por isapre en este cuadro nacional: no fabricarlo.
- **«Metodología y fuentes»**: definición de stock/flujos/comparación entre cortes, notas provisionales, originales y celdas; cálculos auditables determinísticos. Las limitaciones necesarias para entender una cifra permanecen junto a ella; sólo detalle técnico va al panel.

## E4. Contrato técnico mínimo, sin implementación en este PR

Extensión opcional `statistical_view` de esquema v3 para piezas de Datos, sin cambiar normas/noticias/Global ni derivar tipo desde presencia de tabla:

- `dataset_version`, `family`, `metric_id`, `measure_kind` (`stock`, `flow`, `rate`, `proportion`, `contract_events`, `between_cuts`), `unit`, `population`, `period_start/end`, `comparison_base`, `provisional`, `evidence_refs`.
- `observations[]`: valor numérico o null, período, código oficial entidad, grupo, localizador hoja/celda y hash de fuente. `system_total` distinto de filas institucionales y subtotales; nunca sumar los tres.
- `derived_metrics[]`: identificador, fórmula determinística registrada, input_ids, valor sin redondear, display_precision y denominador explícito. Diferencia absoluta y variación relativa sujetas al dominio, comparabilidad y política explícita de E4.P1; no existe fórmula porcentual universal. Cuota de sistema sólo con universo exhaustivo y mismo corte; tasas requieren denominador elegible, no población conveniente.
- `comparability`: mismos períodos, definiciones, unidad, cobertura, código/identidad, cambios/fusiones revisados, revisión del original, missing_entity_ids, reconciled_totals y reason_codes. El validador actual verifica entidades pero exporta agregados: reutilizar extracción conservando filas y provenance, no lanzar LLM para leer/calc cifras ni inferir filas desde total.
- `presentation`: KPI references, chart reference, entity table reference, metodología references. No duplicar textos de insight en cada representación; `incremental_review` incluye cada bloque visual y su propósito, exime equivalentes accesibles de duplicación vacía.

Gate institucional: sólo habilitar comparación aprobada tras verificar extremos por código, todas las sumas y notas. Una entidad faltante queda visible como «sin dato» si universo conocido; null no es0. No redistribuir residual entre entidades. Si no hay filas verificadas, suprimir ranking y decir «desglose no verificado»; mantener agregado verificado. Si cobertura parcial, rotularla y no denominarla ranking completo ni suma sistema. Fusiones/cambio de definición rompen comparación hasta armonización documentada. Cifras revisadas crean versión nueva y receipt, no sobrescriben evidencia histórica. Una contradicción en totales bloquea esa comparación, no obliga a rellenarla con estimaciones.

No se exige gráfico adicional por isapre: tabla sortable aporta valor a menor esfuerzo. Gráfico de barras opcional posterior sólo con base cero; línea histórica no une huecos ni interpola datos ausentes. Si falla JS/gráfico, tabla semántica sigue disponible. No dependencia gráfica nueva obligatoria ni imagen raster de tabla.


### E4.P1 — Dominio de variaciones y cambios de signo (sustituye la fórmula general)

Corrección exclusiva **W6-01** del [dictamen Work6, commit469b491c](https://github.com/cftorre1/Radar-salud/blob/469b491caba94b281f4ab31844d4e8eb827ff594/docs/handoffs/WORK6_PRODUCT_AUDIT_2026_10_12.md), siguiendo [comentario6123589624](https://github.com/cftorre1/Radar-salud/pull/32#issuecomment-6123589624). La aprobación scoped previa se conserva como historial, no como cierre del REVISE posterior. Esta corrección solicita **READY_FOR_WORK6_RECHECK**, no autorización de Codex H. Los P2 de Work6 no se declaran corregidos en este delta; restantes decisiones, presupuestos y HOLD permanecen.

**Regla:** la fórmula ordinaria `100×(fin−inicio)/inicio` sólo se permite si `inicio>0`, la métrica admite interpretación proporcional, ambos valores cumplen su dominio y son comparables, y no existe transición financiera de utilidad a pérdida. Positividad del denominador es necesaria, no suficiente. Prohibido aplicar `abs(inicio)` como arreglo universal. Un porcentaje publicado por la fuente tampoco elude el gate; se conserva como dato de origen con advertencia si su interpretación es improcedente.

Antes de cualquier cálculo comprobar unidad/escala, períodos de igual alcance, universo, definición y versión compatible. Datos faltantes, S/I, no finitos, denominadores fuente inválidos y revisiones no conciliadas producen null con motivo; no cero. Si falla comparabilidad, **también** se bloquea delta absoluto, aunque pueda restarse numéricamente. `raw_arithmetic` aislado de auditoría nunca habilita salida editorial.

Registrar por métrica `value_domain` (no negativo o con signo), `comparison_policy` (proporcional, resultado financiero con signo, tasa, proporción, margen), `proportional_change_allowed`, `unit/scale`, períodos, versión de cada extremo, denominadores fuente si corresponde y su dominio. Salida determinística: `absolute_delta`, `relative_pct` nullable, `point_delta` nullable, `transition`, `reason_code`, `comparison_status`, `publication_status`, `base_version_used`. No usar signo porcentual para decidir «mejora»: `direction` numérica y `favorability` son distintas; favorable/desfavorable requiere semántica y evidencia, no colores automáticos.

|Dominio y transición|Salida pública permitida si comparable|Porcentaje ordinario|
|---|---|---|
|Resultado negativo→positivo|«Pasa de pérdida a utilidad», ambos importes/períodos y delta monetario positivo|N/A `loss_to_profit`|
|Resultado positivo→negativo|«Pasa de utilidad a pérdida», extremos y delta monetario negativo|N/A `profit_to_loss`, aunque base sea positiva|
|Negativo→negativo, fin menos negativo|«Pérdida menor», reducción absoluta de pérdida o delta firmado con unidades|N/A `negative_base`; no llamar caída al resultado por el signo del cociente|
|Negativo→negativo, fin más negativo|«Pérdida mayor», aumento absoluto de pérdida o delta firmado|N/A `negative_base`|
|Negativo→mismo negativo|«Pérdida sin cambio», delta0|N/A `negative_base`, no0% calculado|
|Negativo→cero|«Pasa de pérdida a resultado cero», delta positivo|N/A `negative_base`|
|Cero→positivo/negativo|«De resultado cero a utilidad/pérdida»; delta con unidades|N/A `zero_base`, ni infinito ni100%|
|Cero→cero|«Sin cambio, ambos valores cero»|N/A `zero_base`, no confundir con observación faltante|
|Positivo→cero|«Llega a cero», delta=−inicio|−100% si política proporcional válida; no afirmar mejora automáticamente|
|Positivo→positivo|Niveles, delta y porcentaje con base explícita|Permitido bajo gate|
|Conteo no negativo con extremo negativo|Valor fuera del dominio, HOLD|N/A `invalid_domain`; no etiquetar pérdida/utilidad|

No se calcula por defecto «reducción porcentual de la pérdida». Puede diseñarse posteriormente una métrica explícita de magnitud de pérdida con definición, nombre, unidad y aprobación propios; no reutilizar silenciosamente el porcentaje de resultados ni levantar gates mediante cambio de signo.

**Tasas, proporciones y márgenes mantienen su semántica:**

- Proporción0,20→0,30 equivale a20%→30%: cambio **+10 puntos porcentuales**, variación relativa **+50%** sólo si se justifica, etiquetada como relativa y con poblaciones/definiciones comparables. No+10%. Con base0 sólo cambio en puntos; relativa N/A. Numerador/denominador y escala declarados; proporciones fuera[0,1] o denominador fuente≤0 son inválidos.
- Margen−5%→+3%: **+8 puntos porcentuales**, «margen pasa de negativo a positivo»; relativa N/A. Margen+5%→−3%:−8pp, relativa N/A. Margen−5%→−2%:+3pp, relativa N/A. No aplicar dominio[0,1] a todo margen financiero: su dominio con signo debe estar definido y su denominador económico ser válido. Márgenes positivos comparables pueden admitir relativa, pero puntos son presentación primaria.
- Tasa10→15 por100.000: **+5 por100.000**; relativa+50% si misma definición, exposición y estandarización comparables. No5pp. Cambiar unidad por1.000/por100.000 exige conversión trazable antes de comparar; tasa con población expuesta0 no se convierte en cero. Un conteo puede ser0 aunque su tasa no sea calculable.
- Umbrales, índices con origen arbitrario, razones con signo o medidas sin interpretación proporcional: sólo cambio en su unidad cuando tenga sentido; no autorizar relativos porque la base sea positiva. Una disminución de tasa puede ser favorable o desfavorable según qué mide; no se deduce de la aritmética.

**Bases revisadas:** conservar versión original y revisada, fecha/motivo/fuente y revisar compatibilidad de ambos extremos. Comparación temporal usa par armonizado y `base_version_used`; revisión de un mismo período es otro delta, no crecimiento. Ejemplo de prueba: base publicada100, base revisada120 y fin150 comparables→delta temporal+30/+25%; revisión de base+20 separada. Nunca publicar+50% mezclando versión antigua. Si no hay puente/versiones compatibles, `HOLD_REVISED_BASE` para delta y porcentaje, mostrando sólo niveles claramente separados. Si revisión cambia base a0/negativa, reevaluar el dominio; un PASS anterior no se conserva. No usar último hash sin comprobar que ambas columnas fueron armonizadas.

**FEFI genuino, prueba matemática con HOLD editorial:** [XLS oficial v2](https://www.superdesalud.gob.cl/app/uploads/2026/07/finan_ifrs_mar_2026_web_v2.xls), SHA256 `e3c4f7b3cfee9a6e4a3122aef4d0c65a26d41630e482c16ec4345b8a804db065`, leído nuevamente con xlrd. `Result. Financieros comparados`: A4 enero–marzo; B5/D5 años2025/2026; A8 millones de pesos; B16−273,285, D16+34.090,653; F16+34.363,938. Oráculo correcto: «De pérdida de273,285 millones en enero–marzo2025 a utilidad de34.090,653 millones en enero–marzo2026; diferencia+34.363,938 millones». Porcentaje **N/A, transición pérdida→utilidad**. La fórmula anterior arroja−12.574,395960…%, que nunca debe renderizarse como caída ni entrar a rankings/colores/alt-text.

Este texto es **fixture, no ficha aprobada**: `Notas Explicativas!A18` contradice la cobertura Esencial de las filas institucionales; continúa HOLD de cobertura/comparaciones afectadas, incluidos agregados dependientes. `calculation_policy_pass` no implica `publication_pass`. Se retienen los floats originales; para reproducir estos importes se usan los literales decimales anteriores y se registra normalización a0,001millones sólo en el fixture, sin inventar una tolerancia general ni cerrar W6-02.

**Otra familia real:** stock de beneficiarios, [Cartera2026](https://www.superdesalud.gob.cl/app/uploads/2026/08/estadistica-mensual-de-cartera-de-beneficiarios-2026.xlsx), SHA `bff79f5f67785da49e1e899d0a2f8c91479a1a14a33f205e4d9d0f0fddd1dbec`, Enero!E20=2.514.038, Julio!E20=2.487.497. Conserva delta−26.541personas y relativa−1,055711966…% (display−1,06%). No nuevo backfill ni reauditoría de instituciones.

### E5.P1 — Fixtures determinísticos obligatorios y salida esperada

Los casos reales F1/C1 conservan URL, hash, celdas, períodos y unidades. Los restantes son **sintéticos**, exclusivamente pruebas de dominio: no cifras atribuidas a FEFI, entidades o fuentes sanitarias. Ningún LLM calcula ni decide habilitación porcentual.

|ID|Entrada y política|Delta esperado|Relativa esperada / estado|
|---|---|---:|---|
|F1|FEFI real−273,285→34.090,653millones|+34.363,938|N/A pérdida→utilidad; publicación HOLD|
|F2|Resultado−100→−40|+60|N/A pérdida menor|
|F3|Resultado−100→−160|−60|N/A pérdida mayor|
|F4|Resultado−100→−100|0|N/A pérdida sin cambio|
|F5|Resultado−100→0|+100|N/A pérdida→cero|
|F6|Resultado0→40|+40|N/A cero→utilidad|
|F7|Resultado0→−40|−40|N/A cero→pérdida|
|F8|Resultado0→0|0|N/A base cero|
|F9|Resultado100→−20|−120|N/A utilidad→pérdida|
|F10|Resultado100→0|−100|−100%, política proporcional habilitada|
|F11|Resultado100→150|+50|+50%, misma política|
|C1|Cartera real2.514.038→2.487.497personas|−26.541|−1,055711966…%|
|C2|Conteo100→−1|null|HOLD dominio inválido|
|M1|Faltante/S/I/NA/no finito en cualquiera de los extremos|null|N/A missing_or_invalid; no cero|
|R1|Base100revisada120, fin150 armonizado|+30|+25%; revisión+20 separada|
|R2|Base revisada pero versión fin no conciliada|null|HOLD_REVISED_BASE|
|R3|Base revisada de100 a−20, fin40; resultado armonizado|+60|N/A pérdida→utilidad; no reaplicar+50%|
|P1|Proporción0,20→0,30|+0,10; +10pp|+50% relativa permitida|
|P2|Proporción0→0,30|+0,30; +30pp|N/A base cero|
|P3|Proporción con denominador fuente0, o valor1,20|null|HOLD denominador/dominio|
|G1|Margen−0,05→0,03|+0,08; +8pp|N/A cambio de signo|
|G2|Margen0,05→−0,03|−0,08; −8pp|N/A cambio de signo|
|G3|Margen−0,05→−0,02|+0,03; +3pp|N/A base negativa|
|T1|Tasa10→15 por100.000|+5 por100.000|+50%; no pp|
|T2|Tasa con denominador fuente0|null|HOLD, no tasa0|
|U1|Unidades/períodos/universos incompatibles|null|HOLD comparabilidad|
|I1|Índice100→120, proporcional no autorizada|+20puntos de índice|N/A política no proporcional|

Además: ensayo negativo de mutación aplica fórmula antigua aF1 y debe fallar; aplicar valor absoluto a su base también debe fallar porque sigue exponiendo un porcentaje improcedente. Cambiar denominador de Pulso a valor final debe fallar contra C1. Orden porcentual excluye N/A del ranking numérico, conserva fila con motivo y permite ordenar por cambio absoluto sólo entre medidas/unidades comparables; null no se ordena como0. No calcular dirección/favorabilidad desde string de display.

QA mobile del delta:390px/320px/zoom200%, mostrar transición, extremos con períodos/unidades, delta y «No aplica: cambio de signo/base cero/base negativa» sin recortes ni tooltip exclusivo. N/A no oculta la pieza ni convierte valor en cero; razón accesible para lector de pantalla. Fórmulas/normalización/versiones permanecen bajo Metodología; información esencial de transición está visible. Este es criterio futuro de implementación, no QA visual ejecutado.

## E5. QA de aceptación y Reviewer estadístico

|Área|Prueba concreta y salida exigida|
|---|---|
|Aritmética y reconciliación|Cotizantes+cargas=beneficiarios por fila y sistema; suma diez instituciones=total sin subtotales duplicados; sumasΔ=−26.541; baseenero2.514.038 produce−1,06%; seis comparaciones negativas verificadas con siete puntos.|
|Períodos/unidades|Fixtures con contratosjulio, stockene→julio y movilidadjulio2025→julio2026 no comparten saldo/eje. Negativo: rechazar «+4.544 nuevos beneficiarios» y «−17.700 en julio».|
|Comparabilidad|Fila/código duplicado, entidad faltante, fusión, corte distinto, redefinición, total inconciliable, denominador0, S/I y vacío fallan de manera explícita. No ranking cuando hay sólo totales. Datos provisionales siempre identificados.|
|Gráficos|Mes omitido/desordenado/hueco impide gráfico de serie completa; no unir puntos ausentes. Unidad, período, leyenda, fuente y límites visibles; barra cero, línea con rango explícito. Tooltip no es único acceso al valor.|
|Redondeo|Consalud−20 no aparece como estabilidad; porcentajes derivados de valores crudos; diferencia porcentual no se llama puntos porcentuales. Orden no usa cadenas formateadas.|
|Mobile|390×844,320px y zoom200%: ninguna columna esencial recortada ni overflow horizontal de página/ficha. KPI2×2 o columna según espacio; nombres completos con wrap. Tabla se convierte en filas/tarjetas: nombre+beneficiarios+Δabsoluta/% visibles; cotizantes/cargas y baseenero en expansión con etiqueta/período. Todo accesible sin arrastre horizontal; no reducir letra para hacer caber6columnas.|
|Accesibilidad|Table caption/th/scope o equivalencia semántica; expansión button/aria-expanded; orden con nombre y aria-sort; foco estable al ordenar/expandir; targets44px; contraste texto4,5:1/gráfico3:1; signo y texto además de color. Texto alternativo y tabla exacta disponibles a lector de pantalla sin leer duplicados decorativos.|
|Valor incremental|Comparar captura vieja y propuesta: cada bloque explica su dato/comparación nuevos. Ausencia de resumen+hallazgos+implicancias+fórmulas repetidos. Equivalente accesible y evidencia no se penalizan por repetir cifras exactas.|
|Comprensión ejecutiva|En prueba breve sin guía, identificar período/universo y magnitud en≤20s; distinguir stock de contratos/movilidad y sistema de entidad en≤60s. Umbral propuesto, no medición realizada. Error causal o de período bloquea aunque cumpla tiempo. Registrar participantes, respuestas y tiempo; no inventar mejora porcentual.|
|Regresión focal|Normativa mantiene identificador/emisor/sujeto/efecto/vigencia; noticias conservan hechos incrementales; Global conserva límites/metodología y HOLD. Renderer especializado no aplica por accidente a tablas normativas. Probar fixtures existentes, sin reauditar originales ya aprobados.|

Reviewer independiente sólo evalúa este delta: originales+valores vs propuesta, comparabilidad/negativos, utilidad frente a ficha vieja y compatibilidad contractual con normativa/noticias/Global. QA visual futuro pertenece al SHA de implementación, no queda acreditado por esta especificación.

## E6. Delta mínimo del backlog y prompt Codex H

Añadir **H-Datos P0** con tope3h dentro de las20h aprobadas: reasignar1h de reservaH8 y diferir2h de H4 overlays históricos ya especificados (sin eliminarlos del backlog ni publicarlos). H4 no ejecutado queda explícitamente posterior, sujeto a priorización Work6/Dirección. H-Datos reutiliza H3 (modelo/refs/gates), H1 (ficha) y H7 (QA); no suma doble presupuesto. H5 normativo y H6catálogo conservan sus topes. H-Datos cubre proyección KPI+serie verificada+tabla institucional+metodología y fixtures; si excede3h, entregar delta y bloqueo preciso, nunca omitir accesibilidad/comparabilidad para declarar DONE. Puede separarse en commits sin crear otro Builder. Benchmark pagado sigue fuera y pipelinecalls=0.

Insertar después de H3 en prompt V2.7, preservando sus prohibiciones y autorización:

```text
H-Datos P0: aplicar E1–E5 a Pulso Isapre datosjulio2026. Reutilizar originales
por hash y cálculo determinístico; verificar códigos/definiciones/fechas antes
de habilitar tabla por isapre. No tratar la landing actualagosto como evidencia
de publicaciónjulio ni actualizar el pulso por este trabajo.
Ficha: título+un hallazgo; 2–4KPI coherentes; serie sólo si completa; tabla de
entidades verificadas separando abiertas/cerradas y total sistema. Enmobile,
filas responsivas sin recortar columnas esenciales. Métodos/fórmulas en panel
secundario accesible. Sin reexplicar indicadores en resumen/hallazgos/implicancias.
Stockene–julio, contratosjulio y movilidadentre cortesjulio2025–2026 se separan.
No causalidad/ingresos desde composición; no ranking sin datos; null no es0.
W6-01: implementar dominio determinístico E4.P1 y fixtures E5.P1. Porcentaje
sólo con base positiva y política interpretable; pérdidas/utilidades/cruces,
basecero/negativa y revisiones incompatibles usan N/A con motivo. No abs(base).
Conservar pp/tasas/márgenes y sus denominadores; distinguir cálculo y publicación.
FEFI real debe dar+34.363,938millones y N/A, manteniendo HOLD coberturaEsencial;
Cartera real mantiene−26.541 y−1,055711966…%. Adjuntar resultados del delta.
Work6 recheck focal del nuevo SHA y aceptación Dirección obligatorios antesH.
Antes de renderizar, perfila/explora/selecciona hallazgo y elige visual según E3;
Pulso no es plantilla general. Prueba segunda familia (FEFI sólo si verificada;
fixture respiratorio contradictorio exige HOLD del indicador), sin inventar series.
Tests E5+regresión focal normativa/noticias/Global. Datos originales/receipts
inmutables; ningún cambio a history/feed/latest/approved para publicar.
Tope H-Datos3h financiado por reserva1h+H4diferido2h, total sigue20h.
Work6 debe auditar el candidato final incluidas estadísticas; sólo tras su
aceptación y autorización Dirección ejecutar CodexH en rama aislada.
```

## E7. Instrucción precisa para Work6

Audita de forma integral e independiente el **SHA final de PR32 comunicado en el cierre de este complemento**, leyendo handoff, evidence y receipts. No uses `ef41c9fd` como candidato final: es la base V2. Confirma HEAD actual y detén aprobación si difiere del candidato revisado hasta conciliar delta. No construyas, publiques ni fusiones.

1. **Normativa:** contrasta IF10670/531, separación reposición/suspensión/jerárquicos y corteoctubre; IF534 captura real/vigencia; títulos especiales y emisión como fecha sancionatoria. Preserva límites de estado posterior no verificado.
2. **Noticias:** intenta refutar información incremental y atribuciones de las tres correcciones aprobadas; distingue propuesta editorial de publicación, evita párrafos que sólo parafrasean título. Reutiliza evidencias previas y reabre sólo contradicción concreta.
3. **Global:** comprueba contrato sin secciones obligadas, atribución frente a causalidad, fuentes/metodología, ausencia de extrapolación automática a Chile y mantenimiento de HOLD_SOURCE_METHOD de BCBSA.
4. **Estadísticas:** contrasta este caso contra XLSX por hash/celda, métricas y tabla diezisapres, totales/grupos/denominadores, períodos separados, provisionalidad, diseño responsivo y negativos E5. Desafía explícitamente sobreajuste a Pulso: una segunda familia debe poder escoger otra representación o HOLD sin exigir KPI+línea+ranking; FEFI sólo con serie acreditada. No certifiques QA visual sin ejecutarlo sobre una implementación; evalúa especificación y exige prueba al futuro Builder.
5. Cruza los cuatro tipos con navegación directa, sobres/identidad/persistencia, accesibilidad, catálogo activo y presupuesto. Evalúa al lector: qué aprende en cada clic. El Reviewer focal estadístico no sustituye tu auditoría integral.

Entrega PASS/REVISE con P0/P1/P2, evidencia por hallazgo, SHA exacto, pruebas realmente ejecutadas y riesgos abiertos. Sólo después de aceptación de Dirección se habilita Codex H. No cerrar HOLD externos con una nota genérica de PASS.
