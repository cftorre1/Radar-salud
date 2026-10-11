# Recuperación efectiva de fuentes públicas C

PR existente: [#13](https://github.com/cftorre1/Radar-salud/pull/13), rama `codex/c-public-sources-20261011`, destino futuro `staging`. Se retoma `0fdb2e7`, con baseline QA `cadb6c2`. La rama incorpora el seguimiento de staging `c481984` conservando los hallazgos y tareas de otros frentes. Esta recuperación no está mergeada ni desplegada.

**DEIS está operativa con degradación comprobada. FONASA Noticias, FONASA Datos Abiertos, ISP ANAMED e ISP Surveillance tienen blockers externos probados desde Codex y GitHub Actions.** El antiguo resultado 0/5 basado sólo en CONNECT403 queda histórico en `data/audits/public_sources_c_20261011/recovery/history/`.

## Resultado por fuente

| Fuente | Outcome | Acceso real y cobertura |
|---|---|---|
| FONASA Noticias | `EXTERNAL_BLOCKER_PROVEN` | Codex rechaza CONNECT antes de TLS. GitHub conecta y verifica TLS; el frontal AWS ALB devuelve HTTP403, también con UA navegador. Raíz oficial, rutas históricas, feeds, API y dominio nuevo evaluados. El cuerpo del listing actual es inaccesible: el inventario 30/90 es desconocido. |
| FONASA Datos Abiertos | `EXTERNAL_BLOCKER_PROVEN` | Hub, cuatro subcanales y documentos fonasaweb devuelven HTTP403 desde GitHub. Alternativa oficial `datos.gob.cl`: inventario completo de 14 registros del publicador FONASA; todos tienen metadatos de 2015. Referencias GRD de DIPRES y MINSAL capturadas y legibles, conservando sus publicadores. Ninguna sustituye un canal FONASA recurrente actual. |
| ISP ANAMED | `EXTERNAL_BLOCKER_PROVEN` | Los cuatro aliases `.cl`/`.gob.cl` resuelven DNS; TCP443 expira antes de TLS en GitHub. Listing, raíz ANAMED, feeds/API y aliases probados. La alerta 31/26 del 29/09 está indexada en la superficie oficial, pero su PDF/fecha primarios no se capturaron: omisión trazada, sin publicación. |
| ISP Surveillance | `EXTERNAL_BLOCKER_PROVEN` | Mismo fallo TCP443 para boletines, archivo respiratorio del año actual y detalle oficial de semana 39. La fecha indexada 07/10 no se sustituye por la semana epidemiológica ni el nombre PDF 06/10. Inventario completo 30/90 desconocido; candidato omitido por captura bloqueada. |
| DEIS | `OPERATIVE_DEGRADED` | Centro FIC: 12 publicaciones explícitas; 10 PDF capturados y legibles, 2 volúmenes históricos superan el límite nativo de 20 MiB. Cinco catálogos vivos: 572 recursos con propósito, sin fecha editorial inventada. Catálogo nacional Ministerio de Salud/DEIS y muestra CSV reciente accesibles. Cobertura de catálogo y documentos, sin afirmar descarga universal o indicadores calculados. |

El componente que devuelve el 403 FONASA es observable por `Server: awselb/2.0`; la regla concreta y su dueño interno no son observables. No se identifica un challenge WAF. Para ISP se observa silencio del destino/ruta TCP443: no se atribuye a un firewall, certificado, cambio de HTML o regla específica sin evidencia.

La identidad de las superficies ISP se contrasta con sus páginas oficiales indexadas. La oficialidad FONASA se contrasta con ChileAtiende y el registro de publicador del catálogo nacional. Una identidad oficial comprobada no acredita que una ruta histórica siga funcionando. Los checkpoints indican expresamente dónde falta el cuerpo vivo.

## Recuperaciones y reconciliación

- DEIS usaba rutas supuestas `/datos-abiertos/` y `/publicaciones/` que responden 404: los cinco canales actuales están en tablas públicas Ninja Tables de la portada. El scout obtiene las URLs declaradas por el publicador, verifica identidad de tabla y parsea el envelope real `value`; no adivina rutas de datos.
- Se reparan espacios y Unicode de URLs PDF codificándolos una sola vez. La publicación CIE-10 más reciente comprobada es **25/06/2026**, aunque su portada sea mayo y su ruta contenga `uploads/2021/03`.
- Catálogos: Estadísticas 330 (`indicator`), Datos Abiertos 83 (`trend_benchmark_dataset`), Publicaciones/Infografías 54 (`report_reference`), Estándares/Normativas 62 (`normative_reference`), Tableros 43 (`indicator_dashboard`). Cada recurso conserva `publication_date=null` y `feed_eligible=false` cuando no hay publicación editorial verificable.
- El catálogo nacional filtra publicador Ministerio de Salud y atribución DEIS. Conserva las fechas de actualización de recurso/metadato como tales; no las convierte en fecha editorial. `data/state/deis_catalog.json` permite retomar datos para Trend/Benchmark. No hay indicadores nuevos calculados ni tarjetas creadas por cuota.
- El motor diario conserva el catálogo aparte de la cola editorial. Cada tabla se captura de forma independiente: el fallo de una tabla conserva las demás. La captura de documentos y catálogo también conserva resultados independientes.
- El parser ISP excluía un alias oficial `.gob.cl`. Ahora admite las cuatro autoridades exactas y mantiene controles de fechas, PDFs y redirects. La reparación de autoridad no elimina el timeout externo ni certifica markup vivo.

El inventario **editorial Centro FIC PDF** tiene 0 publicaciones materiales verificadas en 30 y 90 días; el dato sólo aplica a esa superficie. La última publicación es anterior al horizonte. Las referencias XLS/XLSX quedan trazadas aparte, incluyendo ENO y GES; no se afirma que una actualización sin cambio sustantivo sea una noticia. `deis-excluded-documents.json` contiene URLs y motivos de exclusión, con avisos originales. El hash de texto decodificado se distingue del hash de bytes primarios del transporte.

Las 12 filas reales del replay de cola quedan `archived / outside_90_day_backfill`, con fecha, URL y observación originales. El baseline tenía 2.913 filas; las 2.925 actuales conservan todas las originales. **0 publicaciones nuevas, 0 llamadas IA, historial/feed/watermarks sin cambios.** El inventario de otras fuentes bloqueadas es desconocido; sus ceros de Alicanto no se presentan como ausencia de noticias. La reconciliación usa fuente/URL exactas y no certifica equivalencia semántica de eventos publicados por terceros.

Las muestras de datos comprobadas incluyen un XLSX hospitalario con 14.641 filas en su primera hoja, el CSV de establecimientos con 5.782 filas y el CSV de indicadores hospitalarios con 168.474 filas. El último se descarga completo (27.248.718 bytes) con límite explícito de 32 MiB; ambos CSV pasan validación estructural. Cuatro datasets nacionales tienen actualización de recurso en 30/90 días; esas actualizaciones no son publicaciones editoriales ni acreditan por sí solas cambio material.

## Evidencia y QA

Confirmación final: [38117670184](https://github.com/cftorre1/Radar-salud/actions/runs/38117670184), SHA de código `55e31b1`, cinco scouts ejecutados en paralelo con archivos de salud aislados. El paquete íntegro `recovery/runs/38117670184/full-primary-evidence.zip` tiene SHA256 `a0a887a425ea0c4dacfa122ac809327ee811e644fb5f30c772a80ddba1225658`, incluyendo todas las capturas originales.

Ruta durable: `data/audits/public_sources_c_20261011/recovery/`. Los artefactos de Actions duran 14 días; capturas relevantes, hashes, inventarios y resultados se guardan también en git.

- Runtime inicial [38114731188](https://github.com/cftorre1/Radar-salud/actions/runs/38114731188); recuperación PDF [38115202557](https://github.com/cftorre1/Radar-salud/actions/runs/38115202557); diagnóstico TCP/TLS/aliases [38115282340](https://github.com/cftorre1/Radar-salud/actions/runs/38115282340); cinco catálogos [38115490854](https://github.com/cftorre1/Radar-salud/actions/runs/38115490854); integración nativa [38116537392](https://github.com/cftorre1/Radar-salud/actions/runs/38116537392).
- Alternativas GRD [38117181340](https://github.com/cftorre1/Radar-salud/actions/runs/38117181340); catálogo nacional y muestra reciente [38117463026](https://github.com/cftorre1/Radar-salud/actions/runs/38117463026); inventario completo del publicador FONASA [38117618594](https://github.com/cftorre1/Radar-salud/actions/runs/38117618594).
- Checkpoints separados por fuente: `fonasa-checkpoint.json`, `fonasa_datos_abiertos-checkpoint.json`, `isp_anamed-checkpoint.json`, `isp_surveillance-checkpoint.json`, `deis-checkpoint.json`. Cada uno registra endpoint, intentos, outcome, limitación y responsable/siguiente acción.
- **137 tests dirigidos PASS; suite completa 389 PASS, 1 SKIP, 1 fallo heredado**, reproducido en baseline. Exige 12 actos normativos y el snapshot contiene 11; no se relaja el test. QA remoto reproduce ese mismo fallo.
- **Node 41 PASS** mediante ejecución directa del archivo de tests. Desktop/mobile: 32 PASS y 14 FAIL tanto en candidato como en baseline, con idénticos títulos/proyectos de fallo y 0 regresiones nuevas.
- Reviewer determinista ejecutado en proceso independiente contra candidato y baseline: datos/editorial/UX PASS; estadísticas conserva los mismos ocho hallazgos heredados. No se afirma PASS global ni certificación semántica/médico-legal. El Reviewer remoto queda skipped por la dependencia de QA normativo.

`qa/manifest.json`, logs y reportes JSON muestran los alcances exactos. La revisión independiente histórica anterior se conserva como historia; no se reutiliza como certificación de la captura nueva.

## Handoff exacto

1. Responsable de integración/Reviewer: revisar PR #13 y sus checkpoints. El gate `source_recovery_reconciliation_gate_2026_10_11` sigue abierto: exige merge seguro a staging, QA/Reviewer y runtime real **posterior al merge**. El frente recuperado en esta rama no certifica release ni cierre de issue #5.
2. Administrador web FONASA: revisar rechazo del ALB para GET público desde GitHub, habilitar acceso autorizado de monitoreo o entregar export oficial actual con fecha editorial verificable. Confirmar las rutas canónicas de noticias y los cuatro canales del hub. El catálogo 2015 no sustituye esta acción.
3. Operador ISP red/hosting: verificar listener y ruta TCP443 de los cuatro aliases frente al egreso GitHub, restablecer HTTPS público o entregar export/feed oficial accesible. No se requiere desactivar TLS ni suponer una regla WAF.
4. DEIS: después del merge, repetir captura de las superficies con la misma política de fechas; usar catálogo para datos/referencias. Los dos volúmenes históricos grandes siguen fuera de la captura PDF de 20 MiB. Evaluar cambios reales entre snapshots antes de promover un dataset a señal periódica.
5. Ejecución reproducible: `python scripts/recover_public_sources_runtime.py --output work/public-source-recovery`; diagnóstico de fuentes `python scripts/check_public_sources.py --record-health`. Su salida 2 indica que no todas pasan validación completa, incluyendo degradaciones; no convertir ese resultado en PASS.

Los workflows aislados tienen permisos `contents: read`, guard de rama, checkout del SHA exacto y almacenamiento en artefactos. El scout/checker no publica, no usa credenciales IA y no escribe staging/main/producción. La cola del replay se copia antes de ejecutarse. Las únicas filas agregadas al estado de esta rama son los doce archivos DEIS comprobados y archivados.
