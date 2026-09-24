# Alicanto Salud · baseline Beta del viernes

Versión: `beta-friday-2026-09-25`. Fuente estructurada: `config/pmo_baseline.json`. El baseline aprobado por el usuario tiene prioridad sobre documentos antiguos y el README. El objetivo es una Beta verificable en staging; `main` y producción requieren una decisión explícita de release.

## Regla de avance

`Aprobado` describe una decisión funcional aceptada. `Implementado` describe código existente sin prueba completa. `Validado` exige evidencia exitosa de tests, QA desktop y mobile, Reviewer independiente y URL de staging para el commit candidato. `Bloqueado` requiere una dependencia humana o externa concreta; `Pendiente` identifica trabajo por hacer; `Fuera de alcance` excluye pagos, precio definitivo y funciones no aprobadas. La existencia de un archivo o un test unitario aislado no certifica Beta.

El panel calcula el readiness desde el estado de cada bloque y conserva un enlace a la evidencia. No se reemplazan mediciones ausentes por cero. Tras cada ciclo se actualizan estados, fallos, cambios, desviaciones y siguiente acción en la fuente estructurada y el panel.

## Alcance comprometido

1. PMO versionado y panel de operación/readiness trazable.
2. Signal Density: 14 días, más recientes, nuevo/no leído, preferencias de ocultación, dos pulsos de sanciones móviles a 30 días, histórico íntegro, consolidación rutinaria, DF compacto, guard editorial, recuración y ruido SuperSalud.
3. Excel real de movilidad, cartera y suscripciones/desahucios con esquema validado, series, métricas, diagnóstico y Pulso Isapre solo con insights comprobados.
4. Chile: FONASA directo, ISP/ANAMED, DEIS y newsrooms prioritarios con monitoreo de fuente.
5. Global Intelligence Lite: Reuters, CB Insights, McKinsey, Deloitte, PwC, WHO, PAHO y BCG cuando aporten research material; hechos globales separados de hipótesis y señales chilenas.
6. Cobertura: fuentes activas y funnel LIVE auditable; detectada ≠ evaluada ≠ seleccionada; backfill separado y límites declarados.
7. Suscripción consentida y digest semanal FREE resumido, con envío real solo si existe material relevante; preparar PREMIUM sin pagos.
8. Analytics de visitas, recurrencia, lecturas, interacciones y conversión con minimización de datos.
9. FREE te mantiene al día. PREMIUM te ayuda a entender, conectar y anticipar. El detalle completo de cada nivel está en JSON; no existe precio definitivo ni checkout.
10. Presencia: preparación técnica de dominio, SSL, favicon, metadata, correo, DNS y páginas institucionales; compra, cuentas y textos legales definitivos requieren intervención humana.

## Evidencia inicial y límites

### Aislamiento staging / producción · 24 septiembre

`main` pasó de `ea55bc7e` a `28be3108` modificando exclusivamente `daily-radar.yml` y `static.yml`: el piloto programado o manual consulta y escribe en `staging`; producción solo admite `workflow_dispatch` explícito sobre `main`. La configuración compatible llegó a staging en `7f1dd05c`. El [piloto #22](https://github.com/cftorre1/Radar-salud/actions/runs/36023129314), limitado a un elemento, pasó 102 tests y escribió `d698f725` solo en staging. `main` permaneció en `28be3108` y el último deploy de producción continuó siendo [#90](https://github.com/cftorre1/Radar-salud/actions/runs/36018933311); no hubo #91.

El primer preview falló porque el bootstrap exigía que el nuevo HEAD de `main` ya estuviera desplegado. El fix `1d1f1d3f` admite las ramas auxiliares existentes sin modificarlas y conserva la exigencia de deploy aceptado si falta alguna. [Preview #59](https://github.com/cftorre1/Radar-salud/actions/runs/36023632007): bootstrap, 104 tests Python, 16 Node, QA browser desktop 1440×900 y mobile 390×844, Reviewer y deploy staging PASS. Generó artefacto de rollback; la restauración real ya se [ensayó en #7](https://github.com/cftorre1/Radar-salud/actions/runs/35939432026) y no se provocó de nuevo un fallo de staging en este ciclo. Capturas en el artefacto `staging-evidence-1d1f1d3` del run #59.

Work consulta la cola y el PMO al iniciar y cerrar cada ciclo activo. Una vigilancia horaria de Work quedó habilitada para retomar tareas `approved` después de inactividad; el disparador GitHub disponible no admite push a un JSON (solo eventos de pull request). Falta observar la primera ejecución automática para marcar validada esa mejora. Las tareas no aprobadas y cualquier cambio de producción fuera de una excepción explícita permanecen excluidos.

### Intelligence Inbox / Cards V2.2 · 24 septiembre

La portada de staging `ea7e5d9f` dispone cobertura → Explorar compacto → bandeja 30 segundos → feed. La bandeja incluye todas las señales no leídas del período y respeta las preferencias; se puede marcar Leído sin retirar la card, con persistencia, navegación de ida/vuelta y foco de teclado. La card incluye fecha/fuente con períodos de datos rotulados como datos, y la segunda capa adelanta referencias y respaldo antes de detalles largos. El primer candidato `ea2dffa` recibió FAIL independiente por fecha sintética presentada como publicación y pérdidas de foco/scroll; se corrigió. [Preview #63](https://github.com/cftorre1/Radar-salud/actions/runs/36025340784): tests, QA browser 1440×900 y 390×844, Reviewer y despliegue PASS. Las capturas están en `staging-evidence-ea7e5d9` de ese run. El ajuste factual `49d1d8d9` pasó [preview #64](https://github.com/cftorre1/Radar-salud/actions/runs/36025870200), con 104 Python, 17 Node, ocho pruebas browser, Reviewer y preview. La tarea queda Validada dentro de su alcance; los restantes requisitos Beta conservan sus estados independientes.

- Preview final [run #8](https://github.com/cftorre1/Radar-salud/actions/runs/35939727172) para `62111e3`: bootstrap, tests, QA 1440×900/390×844, Reviewer y deploy pasaron.
- Ensayo [run #7](https://github.com/cftorre1/Radar-salud/actions/runs/35939432026): fallo deliberado del preview, rollback con comparación de bytes y job de restauración exitoso.
- LIVE/BACKFILL globales aún carecen de primera medición. Los 2.515 pendientes legados no se reclasifican artificialmente. Excel legado figura como `not_recorded_legacy`; ninguna validación nueva puede inferirse de esos registros.
- El despliegue de staging comparte el sitio GitHub Pages, pero empaqueta la raíz desde `production-stable`. `github-pages` admite solo `main`; `staging-pages` solo `staging`.

## Registro y bloqueos

El JSON registra por bloque estado, evidencia, dependencias y lo que falta; además enumera bloqueos humanos con acción, proveedor, datos, tiempo estimado e impacto. No se activan AI Builder, pagos ni promoción automática. Un ciclo se detiene ante un bloqueo sensible real, tres ciclos consecutivos sin progreso medible o una corrección que reduciría protecciones/evidencia. No se impone un límite rígido de cinco iteraciones.

## Addendum aprobado · Cards V2 / Progressive Disclosure

**Estado:** Aprobado. **Horizonte:** MVP viernes. **Prioridad:** Alta. **Principio:** Barrido → Entiendo → Profundizo. No se declara Validado antes de QA desktop y mobile, Reviewer independiente y evidencia remota de staging.

La tarjeta conserva título, tipo/ámbito, síntesis breve, una línea de por qué importa, acceso a resumen cuando la evidencia ofrece profundidad y fuente original. La segunda capa contiene solamente los campos respaldados por la fuente: resumen ejecutivo, hallazgos, cifras, actores, vigencia, puntos clave, aspectos a revisar, contexto y fuentes. Si el material es limitado se ofrece «Ver contexto disponible» o solo la fuente original; nunca se inventa profundidad.

Home muestra transparencia compacta antes de Explorar: «Miramos mucho para mostrarte poco» con fuentes activas y señales detectadas, evaluadas y seleccionadas LIVE derivadas de medición real. Si no hay medición, lo declara. La explicación, cobertura, límites, LIVE/BACKFILL, fuentes monitoreadas y sugerencia de nuevas fuentes pasan a la vista secundaria.

### Complemento de Dirección · criterio de experiencia

La tarjeta responde en 5–10 segundos de qué trata, qué cambió, por qué importa y si merece profundidad. Jerarquía: título → síntesis → por qué importa → acciones. Solo se agrega una cifra excepcional si determina la relevancia. La segunda capa debe aportar comprensión ejecutiva sustentada en evidencia: hechos, hallazgos, cifras, actores, implicancias, vigencia, atención y contexto útil; no basta con duplicar la tarjeta. Si solo hay título o metadata, se ofrece la fuente original. «Ver contexto disponible» exige contenido adicional real. El QA verifica altura y barrido de varias señales mobile, ausencia de duplicados, valor incremental y métricas compactas.

**Evidencia Cards V2:** [run #21](https://github.com/cftorre1/Radar-salud/actions/runs/35988742995), commit `292d3318f550e56d62109b192442b87da5c65567`: tests, QA desktop/mobile, Reviewer y preview PASS. Addendum implementado y validado con alcance de muestra; el bloque Signal Density completo sigue Implementado.

## Live Evidence Integrity · primer run real

[Daily Radar pilot #17](https://github.com/cftorre1/Radar-salud/actions/runs/35989996109) sobre `staging`: siete fuentes consultadas, 2.533 ítems BACKFILL, 2.515 archivados fuera del horizonte de 90 días, 6 pendientes, 11 rechazados y 1 publicado. LIVE cero es el resultado honesto de la primera pasada sin watermark previo; no prueba aún discovery incremental. Una respuesta deep midió 9.268 tokens de entrada y 923 de salida. [Preview #25](https://github.com/cftorre1/Radar-salud/actions/runs/35990231987) falló QA por una aserción que esperaba ausencia de medición y no desplegó. La corrección requiere su propia evidencia.

La investigación de los 42 fallos fast históricos identificó 40 errores HTTP 429 `insufficient_quota` / `credit_balance_exhausted` en los logs del Daily Radar #13. Las causas de dos fallos permanecen desconocidas. La disponibilidad fast actual no fue probada; no se modificaron billing ni presupuestos.

[Run #26](https://github.com/cftorre1/Radar-salud/actions/runs/35990692761) validó la primera evidencia de cola y cobertura en staging: siete fuentes técnicas, LIVE 0/0/0, BACKFILL separado y admin móvil de 390 px. [Segundo discovery #18](https://github.com/cftorre1/Radar-salud/actions/runs/35991071881): siete consultas sin nuevas publicaciones, LIVE cero, 5 BACKFILL pendientes; ningún llamado OpenAI. No se puede certificar un evento LIVE genuino hasta que una fuente publique uno.

[Preview #28](https://github.com/cftorre1/Radar-salud/actions/runs/35991606685) pasó tests, QA desktop/mobile, Reviewer y smoke para la recuración: 38 → 36 señales en portada; las resoluciones IP/N°5024 e IP/N°4417 permanecen entre los 678 registros históricos. Las circulares estratégicas IF/N°530–535 permanecen visibles. Reviewer independiente confirmó estas diferencias. El Pulso Isapre factual `7fbf5c7` usa exclusivamente las tres familias Excel canónicas, hashes de workbooks cotejados y totales reconciliados. [Preview #29](https://github.com/cftorre1/Radar-salud/actions/runs/35992139203) pasó tests, QA desktop/mobile, Reviewer, despliegue y smoke; el Reviewer independiente verificó tarjeta, datos y HTML de resumen, con límite de no haber interactuado manualmente con ese modal. El período 2026-07 no se presenta como fecha de publicación; no se infieren causas ni tendencia. La Beta completa sigue pendiente.

## QA de Dirección · Cards V2 pendiente

El PASS #21 cubrió una muestra previa; Dirección detectó cuatro gaps efectivos: modelo duplicado de intereses/ocultación, truncamiento semántico Bupa, pulso Prestadores sin materia por resolución y relación IF/N°535→77 sin URL validada. [Preview #32](https://github.com/cftorre1/Radar-salud/actions/runs/35996846040) falló QA desktop/mobile y no desplegó: selector antiguo y tarjeta de 458 px. Estado del addendum: **Implementado**, hasta PASS específico de QA desktop/mobile, Reviewer independiente y staging en el candidato corregido. No interpretar el antiguo PASS como validación de estos gaps.

Deuda de infraestructura prioritaria, posterior al MVP viernes: handoff automático Dirección → baseline/PMO → Work para registrar decisiones aprobadas y eliminar retransmisión manual. Debe conservar revisión y evidencia; no automatiza aprobación editorial, privacidad ni cambios sensibles.

### Cierre verificado de los cuatro gaps

[Preview #33](https://github.com/cftorre1/Radar-salud/actions/runs/35997649138) pasó tests, QA desktop/mobile, Reviewer, preview y smoke; Reviewer independiente comprobó preferencias persistidas, Bupa y otras muestras semánticas, tres resoluciones Prestadores (70, 50 y 200 UF) y relación IF/N°535→77 sin URL inventada. [Preview #34](https://github.com/cftorre1/Radar-salud/actions/runs/35998052315) pasó todos los checks y abrió explícitamente “Normativa relacionada” en browser QA para exigir IF/N°77 visible. El staging interactivo confirmó la referencia y el aviso de enlace pendiente. Cards V2, como addendum, queda **Validado** con este alcance de muestra; Signal Density global y Beta completa siguen Implementado/no listos. La deuda de handoff queda Pendiente fuera del MVP viernes.

## Live Evidence Integrity · tercera captura incremental

[Daily Radar pilot #19](https://github.com/cftorre1/Radar-salud/actions/runs/35998824088) consultó siete fuentes exitosamente. Encontró un enlace nuevo de DF sobre minería sin fecha verificable; se clasificó BACKFILL pendiente y no entró a LIVE ni al feed. La cola quedó con 5 BACKFILL pendientes, 13 rechazados y 1 publicado. LIVE permanece 0/0/0. [Preview #36](https://github.com/cftorre1/Radar-salud/actions/runs/35999033456) pasó tests, QA desktop/mobile, Reviewer y smoke de estos datos. La validación de una publicación LIVE genuina depende de que una fuente activa publique un ítem nuevo, pertinente y fechado; no se genera evidencia artificial.

## Regla de avance revisada · replay y observación externa

El recorrido discovery → LIVE → cola → histórico/feed → cobertura se prueba con fixtures controlados, incluido un evento fechado, uno histórico y otro sin fecha, repetición idempotente y un ataque de mezcla BACKFILL/LIVE. Esta prueba certifica la **capacidad técnica**, nunca la observación de una noticia real. El primer evento LIVE genuino queda en un registro independiente «Pendiente de observación externa» y se seguirá buscando en capturas incrementales; su espera no bloquea otros bloques del MVP.

El indicador `0/10` conserva su significado estricto: bloques críticos completamente Validados. El panel agrega requisitos explícitos por bloque y porcentaje de requisitos respaldados por evidencias de tests, desktop, mobile, Reviewer y preview. Un requisito sin evidencia completa se degrada a Implementado; el porcentaje no estima calidad editorial ni equivale a autorización de release. Los bloqueos humanos y las observaciones externas se muestran por separado.

[Preview #39](https://github.com/cftorre1/Radar-salud/actions/runs/36016370144) validó técnicamente el replay (tests, QA desktop/mobile, Reviewer y despliegue); la observación LIVE real sigue pendiente. El guard PMO exige SHA, run GitHub y asociación expresa de cada requisito con la evidencia. La captura incremental permanece activa.

## Fuentes Chile · primer conector

La ruta oficial de noticias FONASA `https://www.fonasa.gob.cl/noticias/` está identificada. El scout consulta detalles y toma la fecha únicamente de metadata publicada; un elemento sin fecha queda BACKFILL y el procesador lo descarta. El análisis ausente queda diferido, sin resumen inventado. Su sitio respondió 403 desde este entorno, por lo que el conector está **Implementado**, pendiente prueba de discovery real en staging y revisión editorial. ISP/ANAMED presentó un error de certificado y DEIS expiró en esta inspección; ninguno se presenta como fuente validada.

Reviewer del conector FONASA detectó que un timeout de detalle no debía parecer una publicación sin fecha. La ronda ahora registra fallo técnico y no mueve watermark; un error posterior de enriquecimiento deja el ítem pendiente de reintento. Continúa pendiente comprobar acceso efectivo desde Actions.


## Addendum aprobado — Cards V2.1 / Intelligence Inbox

**Estado:** Aprobado · **Horizonte:** MVP viernes · **Prioridad:** Alta

**Principio:** **Descarto → Selecciono → Entiendo → Profundizo**

Objetivo: convertir “Qué debes saber en 30 segundos” en la bandeja principal de triage diario, para barrer señales con scroll mínimo, marcar descartes como leídos y profundizar solo cuando algo interese.

Alcance aprobado:
- Orden de home: Header → “Miramos mucho para mostrarte poco” → Explorar compacto → “Qué debes saber en 30 segundos” → feed.
- Explorar debe reducir materialmente su altura, especialmente en mobile.
- “30 segundos” muestra de forma compacta las señales no leídas del período, incluyendo normativa, legal, fiscalización, datos, noticias y pulsos.
- Cada fila permite **Marcar leído** sin ir a la card; al hacerlo desaparece de la bandeja, pero permanece en el feed como leído.
- Cada fila permite **Ver** y navegar a la card correspondiente.
- Desde la card debe existir una acción clara **Volver a 30 segundos** para continuar el barrido.
- Estado leído/no leído sincronizado entre bandeja y card, con persistencia.
- Jerarquía de profundidad: **30 segundos → card → Ver resumen/Ver contexto → Fuente original**.
- No reabrir Cards V2 ya validadas salvo regresión.

Validación requerida: QA desktop/mobile, Reviewer, evidencia en staging, persistencia leído/no leído, navegación ida/vuelta, sincronización de estados y comprobación de barrido con scroll mínimo.

## Hallazgo crítico de aislamiento · 24 septiembre

[Daily Radar pilot #21](https://github.com/cftorre1/Radar-salud/actions/runs/36018677014), ejecutado en staging con límite de un elemento, consultó siete fuentes existentes y registró FONASA `HTTPError` (0 descubrimientos, salud técnica `error`, resultado editorial `not_evaluated`). LIVE sigue 0/0/0; BACKFILL pending pasó a 15 por descubrimientos DF sin fecha verificable. No hubo llamadas OpenAI en este piloto. FONASA continúa **Implementado**, no Validado. El preview automático de la captura quedó cancelado; los nuevos datos requieren QA separado.

El workflow heredado de `main` (`static.yml`) escucha la finalización de cualquier `Daily Radar pilot`; [producción #90](https://github.com/cftorre1/Radar-salud/actions/runs/36018933311) se ejecutó por `workflow_run` al terminar #21 y desplegó un checkout de `main` en `ea55bc7`, no el código de staging. El cron heredado de `main` también escribe en `main` (último commit `ea55bc7`, creado antes de este ciclo). **No se ejecutarán más pilotos** mientras este disparador exista. Se requiere autorización explícita para corregir solo dos workflows de `main`: hacer que el cron escriba a staging y eliminar el despliegue por finalización de piloto. No se promovió código MVP a main ni se modificaron esos workflows en este ciclo.


## Addenda aprobados — cierre MVP

### Cards V2.2 / metadata compacta y fuentes en resumen
**Estado:** Aprobado · **Horizonte:** MVP viernes · **Prioridad:** Alta

- Card: fecha de publicación + fuente en línea compacta al pie.
- Acciones: **Fuente original ↗** siempre que exista URL verificada; **Ver resumen →** solo con profundidad sustentada; **Ver contexto disponible →** cuando corresponda.
- La segunda capa concentra contexto y evidencia. **Fuentes y referencias** deben aparecer arriba, después del resumen ejecutivo/qué ocurrió y antes de bloques extensos, no escondidas al final.
- Mantener cards compactas sin perder frescura, credibilidad ni contexto mínimo.

### Insights Excel V1
**Estado:** Aprobado · **Horizonte:** MVP viernes · **Prioridad:** Crítica

Principio: **Dato → Insight determinístico → Señal**, con comportamiento fail-closed.

- Cartera: variaciones mensuales/acumuladas, rachas/anomalías y desagregación solo con esquema/denominador validados.
- Suscripciones/desahucios: saldo, cambios mensuales/acumulados y anomalías cuando sean comparables.
- Movilidad: solo comparaciones compatibles con el intervalo validado disponible.
- Cada insight debe exponer período, evidencia/fórmula y fuente.
- El LLM no inventa el hallazgo estadístico; puede explicar implicancias una vez validado el insight.
- Pulso Isapre puede incorporar únicamente insights validados y comparables.

El preview [#48](https://github.com/cftorre1/Radar-salud/actions/runs/36019691556) confirmó QA desktop/mobile, Reviewer y publicación del diagnóstico. Referencias del panel: staging `8db66b6`, producción observada [#90](https://github.com/cftorre1/Radar-salud/actions/runs/36018933311) desde main `ea55bc7`. Son mediciones distintas; no hubo promoción del candidato.
