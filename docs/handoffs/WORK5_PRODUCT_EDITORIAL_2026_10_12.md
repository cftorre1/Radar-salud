# WORK 5 · Product & Editorial Director

Paquete v1.0 · 12 octubre 2026 · destino: Work 3, Integration Commander y un único Codex Builder.

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
