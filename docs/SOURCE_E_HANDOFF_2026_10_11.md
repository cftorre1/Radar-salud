Codex E dejó las reparaciones en `codex/e-salud-laboral-20261011`, basada en staging `cadb6c2d1f3c286a0dbeea3d236f6f10d47df2bb` e integrada con staging `fe3a4f779f43edfdea8edc9df2f2641dd96056c2`. El candidato de código y tests verificado es `f050ce6c96d2ebb1c6606aaafbcbbba4e41275c5`. Los commits posteriores de evidencia no cambian el código. [PR draft #12](https://github.com/cftorre1/Radar-salud/pull/12).

El frente queda implementado con blockers externos exactos, sin certificar operación LIVE, inventario completo de 90 días ni release. Se publicaron **0 señales** y se hicieron **0 llamadas de análisis pagado**. Las muestras materiales son candidatos pendientes de evaluación, no publicaciones.

| Fuente | Causa y reparación | Evidencia original reconciliada | Blocker / siguiente paso |
|---|---|---|---|
| Clínicas Achs Salud | El newsroom compartido no distingue por sí solo el prestador del seguro. Se exige atribución dentro del artículo a la red de clínicas o clínica identificada; se excluyen centros sin cambio clínico y menciones incidentales. El límite de cinco enlaces ya no oculta la muestra clínica antes del filtro. | SAFED/Clínica Atacama: publicación **28-08-2026**, dentro de 90 días y fuera de 30. La cifra de 4.200 horas pertenece al esfuerzo conjunto de prestadores, no a la clínica. Master Plan del **19-08-2026** corresponde a centros y se rechaza de esta lane. | Proxy del executor niega `www.achs.cl` y `www.achssalud.cl` en CONNECT: `403 Forbidden`. Configurar acceso y reproducir contra HTML original. No se verificó una muestra clínica de los últimos 30 días; no equivale a ausencia comprobada de noticias. |
| Achs Seguro Laboral | Se extraen H1, fecha de publicación y cuerpo del artículo, sin avisos, scripts, footer o últimas publicaciones. Los errores de detalle conservan URL y tipo; los candidatos se filtran por cambio concreto. | Guía de tratamiento/reintegro: **24-09-2026**. Datos de scooters: **15-09-2026**, con período enero-junio separado de la fecha de publicación. Ambas muestras dentro de 30/90 días. | Proxy del executor niega `www.achs.cl` en CONNECT. Validar HTML real, paginar hasta **13-07-2026** y completar revisión editorial. |
| Mutual de Seguridad | La respuesta original es un iframe de **Incapsula** hacia `/_Incapsula_Resource`, no un listado. Se devuelve `external_waf_challenge` con URL exacta. No se inventan rutas ni selectores alternativos; la estructura real permanece sin certificar. | Sin muestra fechada accesible. | Resolver acceso autorizado al newsroom/feed con el dueño de la fuente; adicionalmente configurar `www.mutual.cl` en el executor. Mantener el blocker y continuar otras fuentes. |
| IST | La regex de un segmento aceptaba navegación/historia, y el fallback leía fechas de toda la página. Se seleccionan enlaces de titulares H2/H3, se usa la fecha del detalle y se conserva/rechaza la fecha histórica fuera de 90 días. | Actividad de bienestar **07-10-2026** y feria **17-09-2026**: rechazadas. MK Recursos Humanos **29-07-2026**: candidato por incorporar más de 700 trabajadores. Byline y fecha visible coinciden en el texto del dominio original. | Proxy del executor niega `ist.cl`; el lector web directo además presenta timeouts. Las muestras IST proceden del texto indexado del dominio original: no se presenta como replay de HTML capturado. Validar selectores y paginación actuales. |

Las URLs exactas, motivos, fechas, ventanas y límites están en `data/audits/source_e/{clinicas_achs_salud,achs_seguro_laboral,mutual_seguridad,ist}.json`. La ventana usada es **11-09-2026 a 11-10-2026** para 30 días y **13-07-2026 a 11-10-2026** para 90 días, calendario de Chile. Hay siete muestras fechadas y una referencia histórica MCC sin fecha exacta reconciliada. Ninguna se redató con publicaciones relacionadas.

La colección diaria ahora incluye las cuatro fuentes en `config/sources.json` y `engine_cli.py`. Los resultados pasan por la cola durable existente; rechazos guardan motivo y fallos de acceso guardan código/URL en health y `data/state/occupational_source_discovery.json`. La marca `audit_pending_90_day` mantiene BACKFILL aun cuando existe un watermark reciente. El validator rápido sólo acredita discovery acotado; no acredita publicación ni inventario. La evaluación diferida de IA permanece pendiente y no se cuenta como rechazo editorial.

| Checkpoint | Commit |
|---|---|
| Extracción y materialidad de ACHS | `9805542` |
| Separación de Clínicas Achs Salud | `ca49a26` |
| Selectores y fechas históricas de IST | `cbdd89c` |
| Blocker Incapsula de Mutual | `a91339a` |
| Integración de cola y errores por fuente | `eec77a8` |
| Pendientes de análisis y auditor reproducible | `2acbb62` |
| Integración del staging concurrente | `e0bf6f4` |
| Calendario determinístico de los fixtures | `f050ce6` |

La validación está en `data/audits/source_e/validation.json`, con hashes de código/config/tests y evidencias durables. Las **37 pruebas del frente pasan**; las **41 pruebas Node pasan**. La suite Python da **292 PASS, 1 FAIL, 1 SKIP**. El fallo exige al menos 12 actos normativos y observa 11; se reprodujo en la base `cadb6c2` sin estas reparaciones. No se debilitó ese test ni se añadió una publicación para cumplir una cuota.

QA desktop **1440×900** y mobile **390×844**, usando Chromium instalado y Playwright 1.56.1: **32 PASS, 14 FAIL**. Los fallos conciernen al stock/export de fuentes, panel operativo, estado leído Global, GES y normativa 529. Los archivos de `web/` y los tests browser son idénticos a `cadb6c2`; la herencia se sustenta en identidad de bytes, no en una segunda corrida browser. Se conservan nombres y mensajes en `browser-summary.json`.

El Reviewer determinístico existente aprobó data/editorial/UX y rechazó statistics con **ocho findings idénticos a la base**, conservados en `reviewer-global.json` y `reviewer-baseline.json`. La precisión sustantiva independiente no está certificada. [QA remoto del candidato f050ce6](https://github.com/cftorre1/Radar-salud/actions/runs/38111947869) terminó FAIL por el mismo test normativo (**292 PASS, 1 FAIL, 1 SKIP**); staging y Reviewer remoto quedaron skipped. El Reviewer indicado arriba es local. El PR continúa draft.

Para retomar después de resolver la red:

```bash
git checkout codex/e-salud-laboral-20261011
python -m pip install -e . pytest
python -m pytest -q tests/test_occupational_sources.py tests/test_beta_source_package.py tests/test_live_evidence_replay.py
python scripts/audit_occupational_sources.py --output data/audits/source_e/runtime.json
```

El auditor es de sólo lectura: recorre las cuatro fuentes independientemente, no llama IA ni publica, y devuelve la evidencia de cada blocker aunque otra fuente falle. No usar `beta_source_engine_fast` como prueba de publicación. Antes de integrar, verificar HTML original y URLs canónicas, completar inventario/paginación de 90 días, revisar los candidatos materiales y sus fechas, ejecutar QA/Reviewer sobre el SHA integrado y resolver los gates globales abiertos. Hasta entonces, conservar BACKFILL y el estado operacional bloqueado. No hay bloqueo de este frente sobre los recolectores independientes.
