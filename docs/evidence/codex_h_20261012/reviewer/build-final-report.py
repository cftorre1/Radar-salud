import json,hashlib,pathlib,datetime
D=pathlib.Path('/workspace/work/codex-h/reviewer');R=pathlib.Path('/workspace/work/codex-h/implementation')
sha='8f6039dca843fda5903e5e0684ce524e0146bebe'
closed=[
('P1-UX-01','Migración por alias/pieza','Corregir fecha o incorporar pieza adopta alias conocido; no depende de un marcador global.','ux-probe-results-final-8f6039dc.json'),
('P1-UX-02','Foco tras sobre de Ponte','Espera persistencia; mantiene foco en siguiente control visible tras retirar la fila.','ux-probe-results-final-8f6039dc.json'),
('P1-UX-03','Noticia base y weekly pendientes','Ambas piezas permanecen elegibles aunque compartan URL; IDs separados.','ux-probe-results-final-8f6039dc.json'),
('P1-UX-04','Edición weekly nueva','Una lectura v3 de la base no marca una nueva edición leída; importación compartida sólo legacy inicial.','state-probe-results-final-8f6039dc.json'),
('P1-UX-05','Cerrar ficha y restaurar foco','Escape desde fila retirada enfoca siguiente pendiente o destino focusable.','ux-probe-results-final-8f6039dc.json'),
('P1-UX-06','Filas recortadas y scroll interno','1440/390/320 muestran filas completas, expansión conserva elegibles y foco.','state-probe-results-final-8f6039dc.json; focus-expanded-final-8f6039dc.json'),
('P1-UX-07','Tombstone revivido por alias corregido','Legacy título true + ID estable false + nuevo ID con alias explícito conserva false.','alias-tombstone-final-8f6039dc.json'),
('P1-CAT-01','Diagnóstico administrativo en catálogo','UI carga public_sources.json; payload público tiene sólo id/name/group/url/description.','ux-probe-results-final-8f6039dc.json'),
('P1-CAT-02','Consulta inválida o futura','Elegibilidad rechaza fecha inválida, sin zona o futura; sin inventar TTL contractual.','src/radar_salud/public_source_catalog.py; tests/test_product_editorial_v3.py'),
('P1-ED-01','Claims/evidencia malformados','Texto vacío, URL sin host, locator vacío y fecha inválida producen rechazo.','gate-probe-results-final-8f6039dc.json'),
('P1-ED-02','Módulos y receipts malformados','Referencias inexistentes, módulo escalar y veredictos mal tipados fallan cerrado.','gate-probe-results-final-8f6039dc.json'),
('P1-ED-03','Contenido público fuera de firma','Fechas legales/contexto público incluidos en hash; cambio posterior deja stale_review. Renderer v3 excluye complementos legacy.','gate-probe-results-final-8f6039dc.json; final-delta-results-final-8f6039dc.json'),
('P1-ED-04','Conclusión con premisa circular','Hipótesis que se invoca a sí misma es unsupported_conclusion.','gate-probe-results-final-8f6039dc.json'),
('P1-ED-05','Overlay altera trazas pagadas','Whitelist protege modelo/response_id/lineage; overlay no sustituye originales.','src/radar_salud/editorial_overlay.py; tests/test_product_editorial_v3.py'),
('P1-ED-06','invalid_validity muta contenido firmado','publication_ready devuelve editorial_v3_invalid_validity sin cambiar deep-copy ni hash.','final-delta-gate-results.json; tests/test_product_editorial_v3.py'),
('P1-ED-07','Duplicado legacy + misma pieza v3','Exporter prefiere versión v3 revisada de la misma pieza; mantiene análisis con ID separado.','scripts/export_web_snapshot.py; revisión focal previa'),
('P1-STAT-01','Dominio/denominador inválido','Tasas/proporciones/márgenes exigen denominador; policy/domain incompatibles rechazan.','gate-probe-results-final-8f6039dc.json; python-final-results.txt'),
('P1-STAT-02','HOLD retiene cálculo dependiente','Errores de escala/base original borran delta, porcentaje y transición; comparación HOLD.','gate-probe-results-final-8f6039dc.json'),
('P1-STAT-03','Serie o provenance inválida produce línea','Selector rechaza fuente inválida y serie incompleta/incomparable; FEFI/epidemiología conflictiva mantienen HOLD.','gate-probe-results-final-8f6039dc.json; tests/test_product_editorial_v3.py'),
('P1-STAT-04','Caption/contraste mobile','Caption a ancho completo; gráfico y valores legibles, KPI relativo -1,06%, Consalud conserva caída pequeña.','stats-ui-320-final-8f6039dc.png; stats-ui-results-final-8f6039dc.json'),
('P1-STAT-05','Complementos con hashes ausentes/invalidos','Sólo tres kind/family admitidos, SHA64 válido coincidente, meta validated y HTTPS con host; HOLD excluye.','final-delta-results-final-8f6039dc.json'),
('P1-STAT-06','Complemento no firmado aparece en v3','!v3 impide renderizar data_insight_evidence legacy fuera de PUBLIC_FIELDS; v3 mantiene contenido firmado.','final-delta-results-final-8f6039dc.json'),
('P1-STAT-07','Otra familia etiquetada como beneficiarios','Adapter exige cartera; respiratory/fefi/familia ausente muestran límite + fuente, sin SVG/tabla/ranking.','unsupported-family-initial.json; unsupported-family-final-8f6039dc.json'),
('P1-DATE-01','Emisión inválida acreditada','Fecha o hash primario inválidos producen HOLD_DATE; no rejuvenece por captura.','gate-probe-results-final-8f6039dc.json'),
('P1-GL-01','BCBSA sin límite metodológico','Proyección corta atribuye US$942 millones según Reuters, método pendiente, sin efecto causal de IA/Chile.','final-state-results-final-8f6039dc.json'),
('P1-GL-02','Home/aria revive título causal antiguo','Home, Global, detalle y aria-label tras sync conservan la misma atribución y límite.','final-state-results-final-8f6039dc.json'),
('P1-A11Y-01','Contraste/estado leído accesible','Texto conserva contraste; aria-description expresa estado y cambia en Home/feed/Ponte/weekly/Global.','final-state-results-final-8f6039dc.json; ux-390-final-8f6039dc.png'),
('P2-UX-01','Volver arriba y reduced-motion','IntersectionObserver observa salida de controles; sin umbral300; reduced-motion auto y foco main en Home/Global.','final-scroll-results-8f6039dc.json'),
('P2-CAT-01','Alcances omitidos en mapping','DEIS, prestadores_data y ACHS seguro laboral incorporados; cada fila sigue su elegibilidad observada.','src/radar_salud/public_source_catalog.py')]
open_p2=[
{'id':'P2-STAT-ADAPTER','status':'OPEN_SCOPED_LIMIT','description':'Frontend especializado en cartera y sus vistas separadas contratos/movilidad. No certifica representación pública genérica de FEFI/epidemiología/distribuciones; familias no soportadas quedan con límite explícito. Selector general probado, no cuota obligatoria.'},
{'id':'P2-QA-AT','status':'OPEN_EVIDENCE_LIMIT','description':'No sesión independiente con lector de pantalla real, zoom nativo200% ni estudio humano de comprensión ejecutiva. Se verificó DOM/ARIA, teclado/foco y viewports1440/390/320. Builder reporta195px como prueba de reflow, que no sustituye zoom nativo.'},
{'id':'P2-W6-TOLERANCE','status':'CARRIED_FORWARD','description':'Políticas generales de precisión/tolerancia por familia de Work6 no quedan cerradas normalizando el fixture financiero decimal. No se afirma PASS universal de parsers o cobertura monetaria.'}]
checks=json.load(open(D/'editorial-final-receipt-checks-8f6039dc.json'))
# Preserve historical receipt; final receipt extends its representation check.
s=json.load(open(D/'statistical-final-receipt.json'));s['visual_evidence']='stats-ui-results-final-8f6039dc.json and corresponding1440/390/320 screenshots; final family cartera representation independently rechecked.';(D/'statistical-final-receipt.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
artifacts=['ux-probe-results-final-8f6039dc.json','state-probe-results-final-8f6039dc.json','alias-tombstone-final-8f6039dc.json','focus-expanded-final-8f6039dc.json','gate-probe-results-final-8f6039dc.json','stats-ui-results-final-8f6039dc.json','final-delta-results-final-8f6039dc.json','final-state-results-final-8f6039dc.json','final-scroll-results-8f6039dc.json','unsupported-family-final-8f6039dc.json','editorial-final-receipt-checks-8f6039dc.json','statistical-final-receipt.json','node-final-8f6039dc-results.txt','python-final-results.txt','final-delta-gate-results.json']
limits=[
'Originales no releídos: revisión del contenido final contra evidencia previamente aprobada de Work5/Work5_1. No nueva captura, fecha de observación o cobertura externa acreditada por este Reviewer.',
'Los cinco receipts PASS son de candidatos/preview, no publicación. Fixture bytes cambia al incorporar receipts; content_version final de cada pieza sigue coincidiendo con receipt independiente.',
'HOLD_SOURCE_METHOD BCBSA, cobertura Esencial/FEFI y positividad respiratoria conflictiva permanecen; no DIPRES o destino Fonasa inferidos.',
'No certificación global READY, beta, merge, despliegue, activación de fuentes o gasto. Cero llamadas IA pagadas del pipeline.',
'Probes de persistencia prueban navegador actual y dos pestañas; no prometen convivencia con bundles antiguos ni sincronización entre dispositivos.',
'QA integral del Builder se atribuye al Builder: no se reejecutó la suite completa independiente. Fallos iniciales más rechecks focales no se presentan como una única corrida integral limpia.',
'No se afirma verificación independiente de manifest de 5.671 archivos/refs productivos; es evidencia de Builder para conciliación final. Reviewer sólo escribió en su directorio propio.'
]
obj={'verdict':'PASS_SCOPED_TECHNICAL_EDITORIAL','technical_verdict':'PASS_SCOPED','editorial_verdict':'PASS_SCOPED_REUSED_APPROVED_EVIDENCE','reviewer':'CodexH-IndependentReviewer','date':'2026-10-12','code_sha':sha,'branch':'codex/h-product-editorial-20261012','base_staging_sha':'ef8cbe3938623d493872ff5f3e717153f176d1be','approved_contract_sha':'a3e254d9ada6d2750787b416d7a9ee2253c08334','final_delta_from':'5bf2e651c8062c387b576edd127a24308854b098','open_p0':[],'open_p1':[],'open_p2':open_p2,'closed_findings':[{'id':i,'title':t,'resolution':r,'evidence':e,'status':'CLOSED'} for i,t,r,e in closed],'editorial_final_receipts':checks['items'],'independent_validation':{'node':{'passed':49,'file':'node-final-8f6039dc-results.txt'},'python':{'passed':58,'scope':['tests/test_product_editorial_v3.py','tests/test_statistics_reviewer.py','tests/test_ist_full_pdf_review.py'],'file':'python-final-results.txt','checkpoint':'4de1dbd7; final8f delta changes no Python implementation/tests'},'browser':'Own Chromium localhost read-only probes rerun on final8f; fixture routes, two tabs, keyboard/focus, ARIA,1440/390/320, screenshots; scroll reduced-motion and unsupported families corroborated.','receipts':'5 final content_version hashes and embedded reviews match, validate_depth all ok; independent integer/Decimal oracle10entities+7months+initial bases.'},'builder_validation_reported':{'python_focal':75,'python_wide_initial':'3885 PASS,2 IST failures,1 skip; pypdf6.20.0 and3 IST targeted PASS resolve reported failures','browser_initial':'84/94 PASS;10 initial failures recovered in focal rechecks; final12 focused PASS reported','preview':'165 signals deterministic preview no findings reported','protected_manifest':'5671 files unchanged reported'},'limitations':limits,'evidence':{f:hashlib.sha256((D/f).read_bytes()).hexdigest() for f in artifacts}}
(D/'REVIEW_FINAL_CODEX_H_2026_10_12.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
md=f'''# Reviewer independiente · cierre Codex H

**PASS_SCOPED técnico y editorial. P0 abiertos: ninguno. P1 abiertos: ninguno en el alcance revisado.** Los P2 y límites siguientes permanecen expresos. No es READY global, aprobación beta, publicación, merge ni despliegue.

Código revisado: `{sha}`. Rama `codex/h-product-editorial-20261012`; staging base `ef8cbe3938623d493872ff5f3e717153f176d1be`. Contrato aprobado PR32 `{obj['approved_contract_sha']}`. Se cerró delta `{obj['final_delta_from']}..{sha}`, además de revisión adversarial previa del candidato mutable. Cambios documentales posteriores requieren conciliar sólo su delta; no transfieren este PASS a código distinto.

## Alcance independiente

Leí contratos Work5_0/Work5_1 y paquetes de persistencia/UX, catálogo, esquema/gate/export editorial, fechas normativas, cálculos/selector estadístico y renderer. Reviewer no implementó cambios ni editó repositorio del Builder, main/staging/prod o datos vivos. Sólo informes/probes propios bajo reviewer; cero llamadas pagadas del pipeline. Servidor localhost de sólo lectura y rutas de fixtures para preview de candidatos.

**PASS técnico** acredita los checks focales y cierres reproducidos. **PASS editorial** acredita los cinco textos/metadatos finales frente a evidencia aprobada reutilizada; no declara que este Reviewer volvió a abrir originales. Claims/paragraphs/modules conservan receipt independiente final. Contrato de revisión humana no se sustituye por similitud léxica ni asserts del Builder.

## Hallazgos cerrados

|ID|Problema|Resolución/corroboración|
|---|---|---|
'''
for i,t,r,e in closed:md+=f'|{i}|{t}|{r} Evidencia: `{e}`.|\n'
md+='''
El P1 complementario se encontró en `1d9fcaa1`: ausencias `undefined===undefined` y hashes inválidos mostraban «verificados»; payload podía añadirse fuera del hash v3. Evidencia inicial en `final-delta-results.json` y `final-delta-gate-results.json`. El cierre no modifica la firma: el renderer final excluye dichos campos legacy de v3, valida hashes/allowlist/URL para legacy y omite todo bajo HOLD. Por tanto la igualdad de hash de los campos ahora no renderizados no se afirma resuelta mediante extensión de PUBLIC_FIELDS.

El P1 de otra familia se encontró después: fixture respiratory_positivity de tres puntos se dibujaba como beneficiarios/millones de personas. `unsupported-family-final-8f6039dc.json` confirma límite explícito, documento original y ausencia de gráfico/tabla/ranking para respiratory, FEFI y familia ausente. Adapter de cartera permanece, sin prometer un renderer general nuevo.

`invalid_validity` devuelve `(False, editorial_v3_invalid_validity, 0)` sin mutar deep-copy ni content_version. Estado de lectura accesible se comprueba antes/después y sincronización Home→Global; título y aria-label atribuidos BCBSA no vuelven al copy causal antiguo. Los tres complementos históricos son mezcla, brecha contractual y movilidad, con hashes por familia; no repiten stock/streak ni aparecen bajo HOLD o en v3.

## P2 abiertos y límites de producto

'''
for p in open_p2:md+=f"- **{p['id']} · {p['status']}**: {p['description']}\n"
md+='''
## Receipts editoriales finales

Todos coinciden con `content_version()` final y con el receipt adjunto; `validate_depth()` devuelve ok en las cinco piezas. `editorial-case-receipts.json` conserva claim_verdicts, paragraph_verdicts y los dos module_verdicts de IF10670. No se activan/publican candidatos.

|Caso|Hash final firmado|Qué añade / límite|
|---|---|---|
'''
reasons={'felix_bulnes':'Técnica/primera experiencia; ocurrido30-sep, publicación7-oct; no beneficio clínico medido.','presupuesto_2027':'Tres bases y procedencia sectorial4,7% separadas de $18,4billones según Pulso; propuesta, no validación nueva DIPRES.','san_carlos':'Servicios/recintos/reagendamiento; consulta12-oct no renueva anuncio10-oct; reapertura exacta desconocida.','circular_if534':'Vigencia1-dic y deberes operativos; emisión/publicación14-sep separadas; no obligación exclusiva IMED.','resolucion_if10670':'Reposición/suspensión/remisión separadas, informe tras octubre, publicación/notificación desconocidas; sin pendencia actual ni argumentos inventados Esencial; dos módulos nuevos.'}
for x in checks['items']:md+=f"|{x['id']}|`{x['content_version']}`|{reasons[x['id']]}|\n"
md+=f'''
Fixture editorial byte SHA256 actual `{checks['fixture_file_sha256']}` tras adjuntar receipts. El byte hash original de `editorial-case-receipts.json` documenta su snapshot anterior; no se confunde con hash semántico de cada candidato. Fixture estadístico SHA256 `{s['fixture_sha256']}`. Oracle independiente usa valores/celdas de Work5 aprobados:10 instituciones, siete meses, tres sumas y Δtotal−26.541; porcentajes por base inicial, sistema−1,055711966…%. FEFI firmado−273,285→34.090,653 produce+34.363,938millones y relativa N/A; PASS aritmético no levanta HOLD de cobertura Esencial.

## Validación ejecutada y atribución

- **Reviewer:** Node directo49 PASS en SHA final (`node-final-8f6039dc-results.txt`). Python58 PASS focal en checkpoint4de1dbd7 (product_editorial_v3, statistics_reviewer, IST); delta final8f no cambia Python. Suite completa no repetida.
- **Reviewer:** probes Chromium propios en SHA final: alias/tombstones/migración concurrente, dos escrituras distintas, reload, nueva weekly independiente, lectura sólo tras apertura exitosa, foco tras sobre/cierre/expansión, catálogo sanitizado, estado ARIA/sync, complementos válidos/negativos, 1440/390/320 sin clipping/overflow, orden numérico/aria-sort, capturas y reduced-motion Home/Global. Tres filas adicionales conservadas y límites de contratos/movilidad visibles.
- **Reviewer:** hashes de los cinco candidatos revalidados; cálculos enteros/Decimal independientes y validadores adversariales. Las imágenes finales320/390 fueron inspeccionadas visualmente. `statistical-final-receipt.json` amplía el receipt previo a representación del SHA final.
- **Builder, informado:**75 Python focal; suite amplia3885 PASS/2 fallos IST/1skip y después pypdf6.20.0+3 IST PASS; navegador integral84/94 PASS y diez fallos recuperados en rechecks, último12 focal PASS; preview determinístico165 señales; manifest de 5.671 archivos protegidos idénticos y refs main/staging/prod sin cambio. Esta revisión no convierte rechecks en una sola pasada integral limpia ni afirma ejecutar su manifest.

## Evidencia y límites de cierre

'''
for l in limits:md+=f'- {l}\n'
md+='''
Probes/resultados/screenshots finales llevan sufijo `final-8f6039dc` salvo los probes explícitos scroll/unsupported/receipt. JSON final enumera archivos y SHA256 de evidencia. Informes parciales e iniciales se conservan como historial; snapshots sin sufijo de fase pudieron ser reemplazados durante rechecks y no sirven para atribuir una imagen a un fallo inicial. Los repro negativos originales con JSON y tool transcript se distinguen de los resultados finales.

Salida de este receipt: candidato técnico/editorial revisable para handoff, con cero P0/P1 abiertos en este scope y P2/límites expresos. La decisión de integración corresponde al integrador/owner autorizado.
'''
(D/'REVIEW_FINAL_CODEX_H_2026_10_12.md').write_text(md)
print(json.dumps({'sha':sha,'closed_findings':len(closed),'open_p0':0,'open_p1':0,'open_p2':len(open_p2),'report':str(D/'REVIEW_FINAL_CODEX_H_2026_10_12.md'),'json':str(D/'REVIEW_FINAL_CODEX_H_2026_10_12.json')},ensure_ascii=False))
