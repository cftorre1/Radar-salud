# DF · READY_FOR_INTEGRATION · PR #11

**Verdict: READY_FOR_INTEGRATION.** Frente DF técnicamente integrable; no equivale a DONE, candidate global PASS o runtime post-merge. Issues #5/#6 abiertas. No se hizo merge ni se escribió staging/main/producción.

## Paquete exacto

- Rama: `codex/df-end-to-end-20261011`; [PR #11](https://github.com/cftorre1/Radar-salud/pull/11), base `staging`.
- Base revisada: `fe3a4f779f43edfdea8edc9df2f2641dd96056c2`.
- Implementación y estados completos: `f3ad5f08a23360ab2df131d0ce80d55b5e9bf2f6`; el commit posterior de handoff sólo añade documentación/queue/PMO/evidencia.
- **Integrar el PR completo hasta su HEAD final**, incluida la implementación anterior y el handoff. No seleccionar cherry-picks aislados: código, fixtures, rehidratación, decisiones retiradas, dedupe, history/seen/cola y evidencia deben permanecer coherentes. El rango es `fe3a4f779f43edfdea8edc9df2f2641dd96056c2..HEAD` de esta rama. Si staging avanzó, Commander debe contrastar sus nuevos estados y resolver conflictos sin reemplazar registros ajenos a DF.
- Historia no reescrita. Pruebas de diff: registros no DF de queue/history/health/feed idénticos a staging; sólo plumbing compartido necesario para `--source`, motivos de defer y publicación durable.
- Se redujeron más de 31 mil líneas de template en fixtures, preservando exactamente cuerpo/fechas/cards y hashes de los originales. Matrices referencian una única copia de evidencia por URL. `work/` no se versiona. Estados voluminosos conservan los snapshots requeridos para explicar/retirar decisiones contaminadas; no son snapshots accidentales de otras fuentes.

## Resultado y evidencia

[Runtime real 38119095016](https://github.com/cftorre1/Radar-salud/actions/runs/38119095016), código `0afe39ee0ea9e603a253f8dfc7a4a9adbb93835c`: 41 candidatos, 41 fechas verificadas, 0 errores de detalle, 1 Fast exitosa, 0 Deep. **Iquique CESFAM 72 BACKFILL** se publicó como licitación aún no adjudicada, después de corregir la omisión de CESFAM en taxonomía sanitaria. El [runtime anterior](https://github.com/cftorre1/Radar-salud/actions/runs/38118591782) recuperó Congreso/medicamentos-pañales 84 y otras cuatro publicaciones desde la etiqueta oficial Medicamentos.

San Carlos LIVE 82, Ricarte Soto LIVE 82 y Empresas SB LIVE 86 permanecen aceptadas. Son días de publicación DF en calendario Chile; no fechas del incidente ni reloj de crawl. **26 publicaciones aceptadas en cola, 37 URLs DF en el feed** (incluye stock previo); 73 señales totales. Umbral 72 intacto. No se volvió a ejecutar el inventario completo.

| Revisión | Resultado | Evidencia durable |
|---|---|---|
| 21 publicaciones originales | 21/21 originales verificadas, más 5 aceptadas posteriores; 26/26 cuerpo, fecha, headline principal y fila única de history comprobados | `data/audits/df_publications_review_2026_10_11.json` |
| 40 retries originales | 18 RESOLVED_IRRELEVANT, 3 RESOLVED_DUPLICATE, 19 DEFERRED_MULTIMEDIA; cero retries genéricos/pending DF | `data/audits/df_retry_resolution_2026_10_11.json` |
| 13 URLs originales sin día | 4 fechas recuperadas con header/identidad principal; 9 PDF o listados no periodísticos excluidos, sin fecha inventada | `data/audits/df_undated_resolution_2026_10_11.json` |
| Control independiente | 12 controles de search externo en originales DF, robots y 3 sitemaps oficiales, archivo Medicamentos | `data/audits/df_independent_controls_2026_10_11.json` |
| 30 días | 191 URLs fechadas, 12-sep–11-oct; disposiciones individuales | `data/audits/df_reconciliation_2026_10_11.json` |
| 90 días | 228 URLs fechadas, 14-jul–11-oct; 24 páginas de archivo ya revisadas | mismo archivo |
| Readiness/gates/provenance | PASS DF, límites y blockers heredados separados | `data/audits/df_integration_readiness_2026_10_11.json` |

441 originales capturados sin fallos; incluye superficies auxiliares excluidas del denominador de noticias. La reconciliación sigue **parcial**: controles diversos y límites observados no prueban recall absoluto de df.cl. Fecha de nueva revisión no renueva timestamps del inventario original. Los replays offline conservan la revisión fuerte de HTML sólo si hash, cuerpo, fecha e identidad permanecen iguales.

## Editorial, duplicación y formatos

No hay falsas positivas por recomendaciones, titular ajeno o metadata de otra nota en las 26 aceptadas revisadas. Cada fila conserva score, categoría, razón/materialidad, lane, defecto anterior, presencia previa en staging/history/feed y original. El título DF de Antofagasta menciona 2025: el cuerpo separa la nueva transición de Portada del cierre de Cumbres en 2025; la señal describe capacidad actual, no inventa un evento pasado nuevo.

DF sobre biometría/bonos corrobora IF534: el feed prioriza la fuente oficial SIS y conserva ambos originales en history. Los dos reportes MELI–Cruz Verde del 28-ago describen la misma alianza/13 locales; la nota de lanzamiento lidera y el contexto permanece en history. El convenio Caja Los Andes del 14-ago es distinto del acuerdo SUSESO del 23-sep con otras tres cajas. VIGÍA/21-ago y presentaciones posteriores SUSESO son hitos diferentes. Tres multimedia (PDG, Ricarte, Caja Los Andes) ya están representados por sus textos canónicos.

El resultado exploratorio de envejecimiento en 42 pacientes, antes 72, se retiró por la evaluación registrada que explícitamente no acreditaba cambio material; no se modifica el umbral. Las decisiones/snapshots anteriores se conservan. MEDS–UDP 74 e Iquique 72 son acuerdos/capacidad concretos de alcance acotado: la falta de alcance nacional no equivale a falta de materialidad.

Los 19 diferidos son **18 audio/video sin transcripción oficial verificable en las superficies observadas + 1 nota con 5 PNG que requiere OCR verificado**. Cada uno tiene URL, fecha, assets/iframe, hash, texto descriptivo disponible, equivalente cuando existe y siguiente acción. No se inventó transcripción ni se sustituyó cuerpo con recomendaciones. No se afirma inexistencia universal de una transcripción fuera del control realizado. Las descripciones de 18 contenidos no sanitarios permiten una resolución de alcance, sin pretender que se transcribió todo el audio.

`deferred` sale de la cola automática y puede volver a `pending` cuando discovery obtiene fecha y texto principal verificables. No es rechazo editorial ni nueva aceptación en seen. Captura textual verificada, capability multimedia limitada y cobertura parcial están separadas en source_health. Frescura real: polling 06:52:30Z, última señal aceptada 10-oct; 1 publicación en esa corrida, 26 en stock, 19 formatos diferidos. No se renovaron timestamps de otras fuentes.

## READY_FOR_INTEGRATION CHECKLIST

- [x] Código DF focal PASS: 58 tests locales; 57 en el último Actions (el test adicional protege preservación offline).
- [x] Runtime real PASS; originales, model calls y history/feed trazables.
- [x] Reconciliación 30d y 90d, parcial y con límites explícitos.
- [x] 21 publicaciones originales auditadas; las 26 actuales verificadas.
- [x] 40 retries, 13 URLs sin fecha y multimedia clasificados individualmente.
- [x] Dedupe por evento revisado; registros de fuentes conservados.
- [x] Sin regresión DF; mínimo 72 y presupuestos intactos.
- [x] Rango/commits exactos a integrar: implementación `f3ad5f08a23360ab2df131d0ce80d55b5e9bf2f6` + commit final de handoff, mediante merge del PR completo.
- [x] Blockers heredados separados: normativa `11 >= 12` y 8 hallazgos SIS.
- [ ] Runtime **posterior al merge** y candidate global QA/Reviewer/browser todavía requeridos.

Suite ampliada: 304 PASS, 1 FAIL heredado, 1 skipped; live beta excluida por red local. Staging:264 PASS,2 FAIL,1 skipped, incluido el defecto de fecha DF ya reparado. Node PASS. Reviewer determinístico data/editorial/UX PASS; sus ocho hallazgos estadísticos son idénticos a staging. No se certifica revisión semántica independiente ni browser local: Chromium ausente, cero ejecuciones de producto. Esos límites no se presentan como regresiones DF.

## Siguiente acción exacta del Integration Commander

1. Revisar HEAD actual de staging y el PR final, preservar cambios concurrentes/no DF y efectuar merge seguro a **staging solamente**.
2. Ejecutar QA global, Reviewer y browser desktop/mobile tras resolver los gates normativo/SIS por sus frentes correspondientes. No fabricar tarjetas por cuota.
3. Ejecutar Daily fresco después del merge; verificar fecha publisher/LIVE, procesamiento de una nueva publicación elegible, dedupe/idempotencia y que los 19 formatos no vuelvan a retry genérico. Verificar counters y freshness sin tocar otras fuentes.
4. Guardar SHA de merge/run y outcome en issue5/6, queue y PMO. Sólo entonces considerar cierre. Main/producción requieren su propia autorización y no forman parte de este paquete.

Artefacto del runtime final:11694895241, digest `sha256:580f9cbe4262ee0f94bd58ccf30b2b4b5a9f44d0a3cdecfff77909942c7b72f2`; originales completos en Actions y fixtures/receipts/textos en git. Uso Fast acumulado172 (base31;141 llamadas de este frente), Deep14 sin llamadas nuevas. La antigua matriz capture-only no es la receipt del último engine: usar readiness/run logs para esa ejecución.
