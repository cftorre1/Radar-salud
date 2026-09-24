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
