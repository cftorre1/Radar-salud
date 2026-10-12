# Reviewer independiente · cierre Codex H

**PASS_SCOPED técnico y editorial. P0 abiertos: ninguno. P1 abiertos: ninguno en el alcance revisado.** Los P2 y límites siguientes permanecen expresos. No es READY global, aprobación beta, publicación, merge ni despliegue.

Código revisado: `8f6039dca843fda5903e5e0684ce524e0146bebe`. Rama `codex/h-product-editorial-20261012`; staging base `ef8cbe3938623d493872ff5f3e717153f176d1be`. Contrato aprobado PR32 `a3e254d9ada6d2750787b416d7a9ee2253c08334`. Se cerró delta `5bf2e651c8062c387b576edd127a24308854b098..8f6039dca843fda5903e5e0684ce524e0146bebe`, además de revisión adversarial previa del candidato mutable. Cambios documentales posteriores requieren conciliar sólo su delta; no transfieren este PASS a código distinto.

## Alcance independiente

Leí contratos Work5_0/Work5_1 y paquetes de persistencia/UX, catálogo, esquema/gate/export editorial, fechas normativas, cálculos/selector estadístico y renderer. Reviewer no implementó cambios ni editó repositorio del Builder, main/staging/prod o datos vivos. Sólo informes/probes propios bajo reviewer; cero llamadas pagadas del pipeline. Servidor localhost de sólo lectura y rutas de fixtures para preview de candidatos.

**PASS técnico** acredita los checks focales y cierres reproducidos. **PASS editorial** acredita los cinco textos/metadatos finales frente a evidencia aprobada reutilizada; no declara que este Reviewer volvió a abrir originales. Claims/paragraphs/modules conservan receipt independiente final. Contrato de revisión humana no se sustituye por similitud léxica ni asserts del Builder.

## Hallazgos cerrados

|ID|Problema|Resolución/corroboración|
|---|---|---|
|P1-UX-01|Migración por alias/pieza|Corregir fecha o incorporar pieza adopta alias conocido; no depende de un marcador global. Evidencia: `ux-probe-results-final-8f6039dc.json`.|
|P1-UX-02|Foco tras sobre de Ponte|Espera persistencia; mantiene foco en siguiente control visible tras retirar la fila. Evidencia: `ux-probe-results-final-8f6039dc.json`.|
|P1-UX-03|Noticia base y weekly pendientes|Ambas piezas permanecen elegibles aunque compartan URL; IDs separados. Evidencia: `ux-probe-results-final-8f6039dc.json`.|
|P1-UX-04|Edición weekly nueva|Una lectura v3 de la base no marca una nueva edición leída; importación compartida sólo legacy inicial. Evidencia: `state-probe-results-final-8f6039dc.json`.|
|P1-UX-05|Cerrar ficha y restaurar foco|Escape desde fila retirada enfoca siguiente pendiente o destino focusable. Evidencia: `ux-probe-results-final-8f6039dc.json`.|
|P1-UX-06|Filas recortadas y scroll interno|1440/390/320 muestran filas completas, expansión conserva elegibles y foco. Evidencia: `state-probe-results-final-8f6039dc.json; focus-expanded-final-8f6039dc.json`.|
|P1-UX-07|Tombstone revivido por alias corregido|Legacy título true + ID estable false + nuevo ID con alias explícito conserva false. Evidencia: `alias-tombstone-final-8f6039dc.json`.|
|P1-CAT-01|Diagnóstico administrativo en catálogo|UI carga public_sources.json; payload público tiene sólo id/name/group/url/description. Evidencia: `ux-probe-results-final-8f6039dc.json`.|
|P1-CAT-02|Consulta inválida o futura|Elegibilidad rechaza fecha inválida, sin zona o futura; sin inventar TTL contractual. Evidencia: `src/radar_salud/public_source_catalog.py; tests/test_product_editorial_v3.py`.|
|P1-ED-01|Claims/evidencia malformados|Texto vacío, URL sin host, locator vacío y fecha inválida producen rechazo. Evidencia: `gate-probe-results-final-8f6039dc.json`.|
|P1-ED-02|Módulos y receipts malformados|Referencias inexistentes, módulo escalar y veredictos mal tipados fallan cerrado. Evidencia: `gate-probe-results-final-8f6039dc.json`.|
|P1-ED-03|Contenido público fuera de firma|Fechas legales/contexto público incluidos en hash; cambio posterior deja stale_review. Renderer v3 excluye complementos legacy. Evidencia: `gate-probe-results-final-8f6039dc.json; final-delta-results-final-8f6039dc.json`.|
|P1-ED-04|Conclusión con premisa circular|Hipótesis que se invoca a sí misma es unsupported_conclusion. Evidencia: `gate-probe-results-final-8f6039dc.json`.|
|P1-ED-05|Overlay altera trazas pagadas|Whitelist protege modelo/response_id/lineage; overlay no sustituye originales. Evidencia: `src/radar_salud/editorial_overlay.py; tests/test_product_editorial_v3.py`.|
|P1-ED-06|invalid_validity muta contenido firmado|publication_ready devuelve editorial_v3_invalid_validity sin cambiar deep-copy ni hash. Evidencia: `final-delta-gate-results.json; tests/test_product_editorial_v3.py`.|
|P1-ED-07|Duplicado legacy + misma pieza v3|Exporter prefiere versión v3 revisada de la misma pieza; mantiene análisis con ID separado. Evidencia: `scripts/export_web_snapshot.py; revisión focal previa`.|
|P1-STAT-01|Dominio/denominador inválido|Tasas/proporciones/márgenes exigen denominador; policy/domain incompatibles rechazan. Evidencia: `gate-probe-results-final-8f6039dc.json; python-final-results.txt`.|
|P1-STAT-02|HOLD retiene cálculo dependiente|Errores de escala/base original borran delta, porcentaje y transición; comparación HOLD. Evidencia: `gate-probe-results-final-8f6039dc.json`.|
|P1-STAT-03|Serie o provenance inválida produce línea|Selector rechaza fuente inválida y serie incompleta/incomparable; FEFI/epidemiología conflictiva mantienen HOLD. Evidencia: `gate-probe-results-final-8f6039dc.json; tests/test_product_editorial_v3.py`.|
|P1-STAT-04|Caption/contraste mobile|Caption a ancho completo; gráfico y valores legibles, KPI relativo -1,06%, Consalud conserva caída pequeña. Evidencia: `stats-ui-320-final-8f6039dc.png; stats-ui-results-final-8f6039dc.json`.|
|P1-STAT-05|Complementos con hashes ausentes/invalidos|Sólo tres kind/family admitidos, SHA64 válido coincidente, meta validated y HTTPS con host; HOLD excluye. Evidencia: `final-delta-results-final-8f6039dc.json`.|
|P1-STAT-06|Complemento no firmado aparece en v3|!v3 impide renderizar data_insight_evidence legacy fuera de PUBLIC_FIELDS; v3 mantiene contenido firmado. Evidencia: `final-delta-results-final-8f6039dc.json`.|
|P1-STAT-07|Otra familia etiquetada como beneficiarios|Adapter exige cartera; respiratory/fefi/familia ausente muestran límite + fuente, sin SVG/tabla/ranking. Evidencia: `unsupported-family-initial.json; unsupported-family-final-8f6039dc.json`.|
|P1-DATE-01|Emisión inválida acreditada|Fecha o hash primario inválidos producen HOLD_DATE; no rejuvenece por captura. Evidencia: `gate-probe-results-final-8f6039dc.json`.|
|P1-GL-01|BCBSA sin límite metodológico|Proyección corta atribuye US$942 millones según Reuters, método pendiente, sin efecto causal de IA/Chile. Evidencia: `final-state-results-final-8f6039dc.json`.|
|P1-GL-02|Home/aria revive título causal antiguo|Home, Global, detalle y aria-label tras sync conservan la misma atribución y límite. Evidencia: `final-state-results-final-8f6039dc.json`.|
|P1-A11Y-01|Contraste/estado leído accesible|Texto conserva contraste; aria-description expresa estado y cambia en Home/feed/Ponte/weekly/Global. Evidencia: `final-state-results-final-8f6039dc.json; ux-390-final-8f6039dc.png`.|
|P2-UX-01|Volver arriba y reduced-motion|IntersectionObserver observa salida de controles; sin umbral300; reduced-motion auto y foco main en Home/Global. Evidencia: `final-scroll-results-8f6039dc.json`.|
|P2-CAT-01|Alcances omitidos en mapping|DEIS, prestadores_data y ACHS seguro laboral incorporados; cada fila sigue su elegibilidad observada. Evidencia: `src/radar_salud/public_source_catalog.py`.|

El P1 complementario se encontró en `1d9fcaa1`: ausencias `undefined===undefined` y hashes inválidos mostraban «verificados»; payload podía añadirse fuera del hash v3. Evidencia inicial en `final-delta-results.json` y `final-delta-gate-results.json`. El cierre no modifica la firma: el renderer final excluye dichos campos legacy de v3, valida hashes/allowlist/URL para legacy y omite todo bajo HOLD. Por tanto la igualdad de hash de los campos ahora no renderizados no se afirma resuelta mediante extensión de PUBLIC_FIELDS.

El P1 de otra familia se encontró después: fixture respiratory_positivity de tres puntos se dibujaba como beneficiarios/millones de personas. `unsupported-family-final-8f6039dc.json` confirma límite explícito, documento original y ausencia de gráfico/tabla/ranking para respiratory, FEFI y familia ausente. Adapter de cartera permanece, sin prometer un renderer general nuevo.

`invalid_validity` devuelve `(False, editorial_v3_invalid_validity, 0)` sin mutar deep-copy ni content_version. Estado de lectura accesible se comprueba antes/después y sincronización Home→Global; título y aria-label atribuidos BCBSA no vuelven al copy causal antiguo. Los tres complementos históricos son mezcla, brecha contractual y movilidad, con hashes por familia; no repiten stock/streak ni aparecen bajo HOLD o en v3.

## P2 abiertos y límites de producto

- **P2-STAT-ADAPTER · OPEN_SCOPED_LIMIT**: Frontend especializado en cartera y sus vistas separadas contratos/movilidad. No certifica representación pública genérica de FEFI/epidemiología/distribuciones; familias no soportadas quedan con límite explícito. Selector general probado, no cuota obligatoria.
- **P2-QA-AT · OPEN_EVIDENCE_LIMIT**: No sesión independiente con lector de pantalla real, zoom nativo200% ni estudio humano de comprensión ejecutiva. Se verificó DOM/ARIA, teclado/foco y viewports1440/390/320. Builder reporta195px como prueba de reflow, que no sustituye zoom nativo.
- **P2-W6-TOLERANCE · CARRIED_FORWARD**: Políticas generales de precisión/tolerancia por familia de Work6 no quedan cerradas normalizando el fixture financiero decimal. No se afirma PASS universal de parsers o cobertura monetaria.

## Receipts editoriales finales

Todos coinciden con `content_version()` final y con el receipt adjunto; `validate_depth()` devuelve ok en las cinco piezas. `editorial-case-receipts.json` conserva claim_verdicts, paragraph_verdicts y los dos module_verdicts de IF10670. No se activan/publican candidatos.

|Caso|Hash final firmado|Qué añade / límite|
|---|---|---|
|felix_bulnes|`cdab9e14929a0a5c8b03d61ee6915e7330b721d9961d6fe90b833f1a8ea97f6d`|Técnica/primera experiencia; ocurrido30-sep, publicación7-oct; no beneficio clínico medido.|
|presupuesto_2027|`fdef5574f0bada517f2f04fc9cd2240ee628682c5396704ed667cc9830d3d842`|Tres bases y procedencia sectorial4,7% separadas de $18,4billones según Pulso; propuesta, no validación nueva DIPRES.|
|san_carlos|`b85c23e9ee942dde1e2f5768539f71a31a7d1535b83b8f4beb32388bbad738b0`|Servicios/recintos/reagendamiento; consulta12-oct no renueva anuncio10-oct; reapertura exacta desconocida.|
|circular_if534|`205328ba2974564be079ea8d96a904baeaedda7387776119b1926ce889caa62b`|Vigencia1-dic y deberes operativos; emisión/publicación14-sep separadas; no obligación exclusiva IMED.|
|resolucion_if10670|`bd283d2199b07cb4053277ab15e034bc1d8e28bbb142bb47f5eee0bbc38e7f05`|Reposición/suspensión/remisión separadas, informe tras octubre, publicación/notificación desconocidas; sin pendencia actual ni argumentos inventados Esencial; dos módulos nuevos.|

Fixture editorial byte SHA256 actual `03c7fae1cff4367cee10da056bc61ced87357192e232e438b5ea10efda2e50be` tras adjuntar receipts. El byte hash original de `editorial-case-receipts.json` documenta su snapshot anterior; no se confunde con hash semántico de cada candidato. Fixture estadístico SHA256 `4c3d78dc7f621ea8f1dd5053baeb1cae5b585d03bdd6715adb3490439a82d5da`. Oracle independiente usa valores/celdas de Work5 aprobados:10 instituciones, siete meses, tres sumas y Δtotal−26.541; porcentajes por base inicial, sistema−1,055711966…%. FEFI firmado−273,285→34.090,653 produce+34.363,938millones y relativa N/A; PASS aritmético no levanta HOLD de cobertura Esencial.

## Validación ejecutada y atribución

- **Reviewer:** Node directo49 PASS en SHA final (`node-final-8f6039dc-results.txt`). Python58 PASS focal en checkpoint4de1dbd7 (product_editorial_v3, statistics_reviewer, IST); delta final8f no cambia Python. Suite completa no repetida.
- **Reviewer:** probes Chromium propios en SHA final: alias/tombstones/migración concurrente, dos escrituras distintas, reload, nueva weekly independiente, lectura sólo tras apertura exitosa, foco tras sobre/cierre/expansión, catálogo sanitizado, estado ARIA/sync, complementos válidos/negativos, 1440/390/320 sin clipping/overflow, orden numérico/aria-sort, capturas y reduced-motion Home/Global. Tres filas adicionales conservadas y límites de contratos/movilidad visibles.
- **Reviewer:** hashes de los cinco candidatos revalidados; cálculos enteros/Decimal independientes y validadores adversariales. Las imágenes finales320/390 fueron inspeccionadas visualmente. `statistical-final-receipt.json` amplía el receipt previo a representación del SHA final.
- **Builder, informado:**75 Python focal; suite amplia3885 PASS/2 fallos IST/1skip y después pypdf6.20.0+3 IST PASS; navegador integral84/94 PASS y diez fallos recuperados en rechecks, último12 focal PASS; preview determinístico165 señales; manifest de 5.671 archivos protegidos idénticos y refs main/staging/prod sin cambio. Esta revisión no convierte rechecks en una sola pasada integral limpia ni afirma ejecutar su manifest.

## Evidencia y límites de cierre

- Originales no releídos: revisión del contenido final contra evidencia previamente aprobada de Work5/Work5_1. No nueva captura, fecha de observación o cobertura externa acreditada por este Reviewer.
- Los cinco receipts PASS son de candidatos/preview, no publicación. Fixture bytes cambia al incorporar receipts; content_version final de cada pieza sigue coincidiendo con receipt independiente.
- HOLD_SOURCE_METHOD BCBSA, cobertura Esencial/FEFI y positividad respiratoria conflictiva permanecen; no DIPRES o destino Fonasa inferidos.
- No certificación global READY, beta, merge, despliegue, activación de fuentes o gasto. Cero llamadas IA pagadas del pipeline.
- Probes de persistencia prueban navegador actual y dos pestañas; no prometen convivencia con bundles antiguos ni sincronización entre dispositivos.
- QA integral del Builder se atribuye al Builder: no se reejecutó la suite completa independiente. Fallos iniciales más rechecks focales no se presentan como una única corrida integral limpia.
- No se afirma verificación independiente de manifest de 5.671 archivos/refs productivos; es evidencia de Builder para conciliación final. Reviewer sólo escribió en su directorio propio.

Probes/resultados/screenshots finales llevan sufijo `final-8f6039dc` salvo los probes explícitos scroll/unsupported/receipt. JSON final enumera archivos y SHA256 de evidencia. Informes parciales e iniciales se conservan como historial; snapshots sin sufijo de fase pudieron ser reemplazados durante rechecks y no sirven para atribuir una imagen a un fallo inicial. Los repro negativos originales con JSON y tool transcript se distinguen de los resultados finales.

Salida de este receipt: candidato técnico/editorial revisable para handoff, con cero P0/P1 abiertos en este scope y P2/límites expresos. La decisión de integración corresponde al integrador/owner autorizado.
