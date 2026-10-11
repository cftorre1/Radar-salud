# Work 4 — Universo de fuentes faltantes y expansión

Alicanto Salud · staging · corte 2026-10-11 · issue [#5](https://github.com/cftorre1/Radar-salud/issues/5).

**Resultado:** 75 filas de evaluación, 10 Isapres, 15 paquetes ejecutables (3 P0 y 12 P1). Ninguna fuente activada ni cambio a producción. La matriz distingue propuesta, prueba pública y operación real.

Producto revisado: `9826b3b727cd7d9f504148072385d4cd37405895`. Integración de documentación sobre `cadb6c2d1f3c286a0dbeea3d236f6f10d47df2bb`; incorpora las auditorías Work 3 publicadas durante este trabajo. Fuentes de roadmap: `SOURCES_V2_FINAL.md`, `SERVICES_V2_FINAL.md`, PMO y cola; no hay un archivo llamado `ROADMAP.md` en este corte.

## Decisión ejecutiva

- P0: cohorte comparable de las diez Isapres, hechos esenciales/finanzas CMF y presupuesto/ejecución DIPRES. Cierran brechas de competencia y financiamiento con datos primarios.
- P1: FNE y CENABAST; OMS; factibilidad Reuters/OPS/Mercado Público/PJUD y resolver BCN; pilotos prestadores, memorias/regiones, INE/CASEN, ISL/COMPIN y tecnología UDD/CENS.
- Mantener fuentes empresariales/promocionales como secundarias salvo evento material. Start-Up Chile/ATS/VC especializado quedan diferidos expresamente: eran compromisos del roadmap, no se dan por cumplidos.
- FNE y CENABAST se agregan por evidencia concreta de M&A, distribución y adopción tecnológica. No se añade un conector por cada actor.

Disposiciones: 34 “activar ahora”, 32 secundarias, 7 post-MVP y 2 descartes de ingesta. Las 34 propuestas se consolidan en 15 paquetes; varias son extensiones de fuentes existentes o el mismo adapter para distintas entidades.

**“Activar ahora” significa prioridad de incorporación/calificación en staging, no que la fuente esté activa o sana.** Si hay bloqueo, la primera acción es una prueba acotada de acceso. No se promociona ninguna sin el quality gate, evidencia temporal y reconciliación runtime. Las prioridades son internas a expansión y no desplazan la recuperación crítica del issue #5.

## Reuters, WHO y PAHO: veredicto de recurrencia

| Publisher | Referencias únicas curadas | Última publicación curada | Recolector periódico / health propio | Conclusión |
| --- | --- | --- | --- | --- |
| Reuters | 8 | 2026-10-08 | No encontrado | curated_only_no_periodic_operation_proven |
| WHO | 2 | 2026-06-22 | No encontrado | curated_only_no_periodic_operation_proven |
| PAHO | 0 | — | No encontrado | not_present_in_curated_dataset_or_runtime |

`data/global/themes.json` declara generación 2026-10-08T23:55:00Z: 14 temas y 17 referencias únicas. La colección fue actualizada recientemente; no es sólo material de ejemplo antiguo. Su exportación en QA no consulta Reuters, WHO ni PAHO.

`press_pipeline.py` contiene normalizadores Reuters usados en pruebas/demo. `global_intelligence.py` valida/carga contenidos y reconoce publishers. El workflow diario llama a `engine_cli`; no enruta recolectores para estos tres. No aparecen como fuentes con health propio en los artefactos revisados. Un cron general tampoco demuestra ejecución de una fuente ausente.

Mercado Público presenta un caso similar: cliente API y pruebas existen, pero falta la ruta periódica y el cliente no resuelve aún la semántica de publicación/adjudicación. CMF no puede contarse como respaldo operativo de CLC hasta integrar y probar ese circuito; un PDF DIPRES fijo no constituye seguimiento recurrente de FONASA.

## Método y límites

Se contrastaron issue #5, documentación de servicios/fuentes, configs, workflow/código, salud/descubrimiento y auditorías. Ventanas: 30 días desde 11/09 y 90 días desde 13/07. Se verificaron superficies públicas y muestras dirigidas; **no es una certificación exhaustiva de cada archivo de 90 días ni una ejecución de los conectores**. Un buscador puede localizar evidencia sin que el servidor permita extracción directa.

Cada fila incluye propósito, módulo, URL primaria, frecuencia, disponibilidad, fechas/evidencia, prueba reciente o ausencia explícita, valor, ruido y decisión. La matriz JSON conserva datos estructurados, hashes del corte, mapeo de brechas, referencias y tareas. Fechas desconocidas quedan nulas. La fecha de captura nunca sustituye publicación, vigencia, evento o período.

Work 3 registra fallos aún abiertos de cobertura y autonomía; por ejemplo, Andes no agota el listado y DF tiene problemas de fecha/cola. Las tareas de expansión preservan esas dependencias. No se relabelan como saludables los 27 conectores existentes ni se infiere salud de una salida vacía.

Se incorporó el cierre editorial Work 2 antes de integrar. La [página de contingencias UC CHRISTUS](https://www.ucchristus.cl/contingencias) se abrió directamente: aporta suspensión de atención y cambios de capacidad, pero carece de fecha editorial. Se debe versionar y conciliar el estado de hospitalización con los comunicados fechados. Su presencia y el Insight curado no prueban un collector periódico. El anuncio presupuestario difundido el 05/10 también requiere separar publicación de la novedad sustantiva anterior.

## Cobertura de compromisos

| Familia solicitada | Filas de matriz |
| --- | --- |
| Reuters recurrente | reuters |
| OMS/WHO | who |
| OPS/PAHO | paho |
| Mercado Público/ChileCompra | procurement |
| Poder Judicial | pjud |
| BCN/LeyChile | bcn |
| CMF | cmf |
| DIPRES | dipres |
| INE | ine |
| CASEN | casen |
| CEP | cep |
| ISL | isl |
| COMPIN | compin |
| universo completo Isapres | sis_cohort, isapre_banmedica, isapre_colmena, isapre_consalud, isapre_cruzblanca, isapre_nuevamasvida, isapre_vidatres, isapre_esencial, isapre_isalud, isapre_fundacion, isapre_cruzdelnorte |
| Clínica Alemana | alemana |
| UC CHRISTUS | uc_christus |
| Clínica Las Condes | clc |
| Interclínicas | interclinica |
| otras redes prestadoras | falp, uandes_clinic, meds, andes_regional, existing_networks, other_providers, public_providers |
| universidades y centros de estudios | udd, uchile, uc_policy, clapes |
| Start-Up Chile | startup_chile |
| ecosistema healthtech | cens, prosalud, healthtech, lavca, vc_maps |
| laboratorios | pharma_primary, roche, megalabs, saval, pharma_associations, pfizer_existing |
| farmacias | ahumada, salcobrand, cruzverde, independent_pharmacies |
| medtech | ge, siemens, medtronic, adimech |

Otros compromisos del roadmap también quedan resueltos en la matriz: ATS/careers, LinkedIn, TC/TDLC, VC/aceleradoras, biotech, prensa internacional especializada y expansión LatAm. Los mínimos del usuario no se usan como límite artificial del universo.

## Matriz completa

Las dos tablas de cada familia se unen por ID. La primera cubre propósito, destino, superficie y cadencia; la segunda cubre viabilidad, evidencia, señal, valor/ruido y decisión. “Primaria indexada” significa localizada en fuente oficial mediante búsqueda; “abierta” significa que se leyó el contenido. Ninguna equivale a prueba runtime.

### Internacional

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| reuters · Reuters recurrente | M&A, capital, tecnología y regulación internacional con posible transferencia a Chile | Global Intelligence, Discovery | [Fuente](https://www.reuters.com/business/healthcare-pharmaceuticals/) | Diaria hábil; alertas materiales, no cuota |
| who · OMS / WHO | Epidemiología, guías y cambios de sistemas sanitarios | Global Intelligence, Trend | [Fuente](https://www.who.int/news-room) | 2 veces por semana; alertas urgentes diarias |
| paho · OPS / PAHO | Vigilancia epidemiológica regional y políticas comparables | Global Intelligence, Trend | [Fuente](https://www.paho.org/es/informes-tecnicos) | Semanal por boletín; diario sólo alertas |
| oecd · OECD salud | Comparación de sistemas, gasto y adopción tecnológica | Global Intelligence, Benchmark | [Fuente](https://www.oecd.org/en/topics/health.html) | Mensual y por publicación |
| consulting · Deloitte, McKinsey y PwC | Tesis estratégicas y cambio de modelos de negocio | Global Intelligence | [Fuente](https://www.deloitte.com/us/en/industries/life-sciences-health-care.html) | Mensual |
| restricted_global · BCG / CB Insights | Tesis de mercado y mapas de innovación | Global Intelligence | [Fuente](https://www.cbinsights.com/research/) | Trimestral si existe acceso autorizado |
| specialist_media · STAT / Fierce Healthcare | Profundidad sectorial internacional complementaria | Global Intelligence | [Fuente](https://www.statnews.com/) | Semanal si se habilita |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| reuters | Normalizadores en press_pipeline.py; sin fetcher/ruta periódica. Acceso automatizado y derechos no acreditados. | Fecha editorial y URL disponibles en referencias; falta validar captura íntegra permitida y actualizaciones. | [2026-10-05](https://www.reuters.com/legal/transactional/ge-healthcare-buy-sofie-biosciences-945-million-strengthen-radiopharma-business-2026-10-05/) · GE HealthCare anuncia compra de SOFIE; contrastable con emisor. Muestra indexada, no prueba de conector. (primary_indexed) | Alto: operaciones que los reguladores chilenos no cubren. Ruido: Medio: litigios sin pertinencia, duplicados y foco EE.UU. | activar ahora · P1 · w4_reuters_2026_10_11 |
| who | Listado y detalle HTML públicos abiertos en esta auditoría; falta parser/routing periódico. | Fecha explícita en detalle; distinguir versión de guía, período de datos y noticia. | [2026-10-09](https://www.who.int/news/item/09-10-2026-who-urges-shift-from-institutional-to-community-based-mental-health-care) · Orientación hacia atención comunitaria de salud mental; detalle primario accesible. (primary_opened) | Alto: evidencia internacional de política y demanda. Ruido: Medio: nombramientos, campañas y efemérides. | activar ahora · P1 · w4_who_2026_10_11 |
| paho | Contenido oficial indexado; listado y PDF devolvieron 403. Ruta alternativa pública pendiente. | Lista presenta publicación y semana epidemiológica; PDF completo sin verificar en este entorno. | [2026-09-25](https://www.paho.org/es/informes-tecnicos) · Informe regional influenza semana 37, publicación listada 25/09; señal indexada y acceso directo bloqueado. (primary_indexed_blocked) | Alto: contexto LatAm y riesgo sanitario. Ruido: Bajo-medio: mezclar países o revisiones. | activar ahora · P1 · w4_paho_2026_10_11 |
| oecd | URL primaria presente en colección curada; no se verificó canal recurrente en este trabajo. | Datos y fecha de informe deben separarse; metodología internacional no idéntica a Chile. | [2026-10-07](https://www.oecd.org/en/publications/proceeding-report-from-madrid-conference-on-the-responsible-scale-of-ai-in-healthcare_cf9439c3-en.html) · Informe Madrid sobre escala responsable de IA, según themes.json; no recapturado aquí. (repository_curated_only) | Medio-alto para Benchmark y tesis Global. Ruido: Bajo; riesgo de atribuir cifras internacionales a Chile. | secundaria · Sin incorporación priorizada |
| consulting | Enlaces de informes curados; automatización/reutilización y fechas deben calificarse por editor. | Fecha en themes.json no sustituye chequeo del original; distinguir proyección de resultado. | [2026-09-18](https://www.deloittedigital.com/us/en/insights/perspective/genai-greenlight-health-care.html) · Referencia GenAI en themes.json; revisión directa pendiente. (repository_curated_only) | Medio: insumo interpretativo con corroboración primaria. Ruido: Alto: marketing, encuestas no comparables y contenido repetido. | secundaria · Sin incorporación priorizada |
| restricted_global | Auditorías previas registran 403/acceso y restricciones de reutilización comercial; no demostrada licencia aplicable. | No se validó una muestra reciente reutilizable. | Sin prueba reciente permitida; restricciones/acceso descritos en PMO_BASELINE. No se infiere una prohibición universal. (repository_audit_only) | Medio; alto solapamiento con fuentes primarias. Ruido: Alto: gated marketing y coste de derechos. | post-MVP · Sin incorporación priorizada |
| specialist_media | Roadmap posterior; superficies/acceso no calificados aquí. | Sin detalle reciente validado; exigir fecha editorial y derechos. | No se invierte en validar nuevas suscripciones antes de resolver Reuters/WHO. (primary_indexed) | Medio incremental. Ruido: Medio-alto: redundancia y geografía EE.UU. | post-MVP · Sin incorporación priorizada |

### Isapres

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| sis_cohort · SIS: registro y datos de las 10 Isapres | Denominador completo de competencia, beneficiarios, finanzas y redes | Benchmark, Trend, Watch | [Fuente](https://www.superdesalud.gob.cl/registro/isapres/) | Registro mensual; datos por release mensual/trimestral; cambios materiales diarios |
| isapre_banmedica · Banmédica | Cuota, cartera, resultados, precios regulados, redes/convenios y cambios de control; comparar dentro de su tipo. | Benchmark, Watch, Trend | [Fuente](https://www.banmedica.cl/) | SIS mensual/trimestral; canal corporativo semanal selectivo |
| isapre_colmena · Colmena Golden Cross | Cuota, cartera, resultados, precios regulados, redes/convenios y cambios de control; comparar dentro de su tipo. | Benchmark, Watch, Trend | [Fuente](https://www.colmena.cl/) | SIS mensual/trimestral; canal corporativo semanal selectivo |
| isapre_consalud · Consalud | Cuota, cartera, resultados, precios regulados, redes/convenios y cambios de control; comparar dentro de su tipo. | Benchmark, Watch, Trend | [Fuente](https://www.consalud.cl/) | SIS mensual/trimestral; canal corporativo semanal selectivo |
| isapre_cruzblanca · Cruz Blanca | Cuota, cartera, resultados, precios regulados, redes/convenios y cambios de control; comparar dentro de su tipo. | Benchmark, Watch, Trend | [Fuente](https://www.cruzblanca.cl/) | SIS mensual/trimestral; canal corporativo semanal selectivo |
| isapre_nuevamasvida · Nueva Masvida | Cuota, cartera, resultados, precios regulados, redes/convenios y cambios de control; comparar dentro de su tipo. | Benchmark, Watch, Trend | [Fuente](https://www.nuevamasvida.cl/) | SIS mensual/trimestral; canal corporativo semanal selectivo |
| isapre_vidatres · Vida Tres | Cuota, cartera, resultados, precios regulados, redes/convenios y cambios de control; comparar dentro de su tipo. | Benchmark, Watch, Trend | [Fuente](https://www.vidatres.cl/) | SIS mensual/trimestral; canal corporativo semanal selectivo |
| isapre_esencial · Esencial | Cuota, cartera, resultados, precios regulados, redes/convenios y cambios de control; comparar dentro de su tipo. | Benchmark, Watch, Trend | [Fuente](https://www.somosesencial.cl/) | SIS mensual/trimestral; canal corporativo semanal selectivo |
| isapre_isalud · Isalud (registro SIS: Isalud Ltda.) | Cuota, cartera, resultados, precios regulados, redes/convenios y cambios de control; comparar dentro de su tipo. | Benchmark, Watch, Trend | [Fuente](https://www.isapredecodelco.cl/) | SIS mensual/trimestral; canal corporativo mensual |
| isapre_fundacion · Fundación | Cuota, cartera, resultados, precios regulados, redes/convenios y cambios de control; comparar dentro de su tipo. | Benchmark, Watch, Trend | [Fuente](https://www.isaprefundacion.cl/) | SIS mensual/trimestral; canal corporativo mensual |
| isapre_cruzdelnorte · Cruz del Norte | Cuota, cartera, resultados, precios regulados, redes/convenios y cambios de control; comparar dentro de su tipo. | Benchmark, Watch, Trend | [Fuente](https://www.isaprecruzdelnorte.cl/) | SIS mensual/trimestral; canal corporativo mensual |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| sis_cohort | Registro HTML y publicación con adjuntos; aprovechar conector SIS existente. | Publicación explícita 02/10/2026, datos agosto 2026; no medir cobertura por nombre de conector. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Nueva publicación mensual de cartera del sistema; validar archivo por código antes de computar participación. (primary_opened) | Muy alto: cierra comparación completa con baja fragmentación. Ruido: Bajo si normaliza períodos, universos y tipos de Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |
| isapre_banmedica | Timeout en apertura; no prueba inaccesibilidad permanente. El adapter compartido SIS cubre la entidad sin conector diario propio. | Alta en publicación SIS agregada; corporativa todavía no calificada. Sin muestra corporativa reciente fechada verificada. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Prueba compartida: SIS publica cartera de agosto el 02/10. No es prueba de publicación nativa de Banmédica. (primary_opened_shared_dataset) | Alto en cohorte competitiva completa; valor incremental de newsroom por demostrar. Ruido: Medio-alto: descuentos, beneficios y banners sin fecha; holding no equivale a Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |
| isapre_colmena | Home abierta, alianzas y memoria enlazadas. El adapter compartido SIS cubre la entidad sin conector diario propio. | Alta en publicación SIS agregada; corporativa todavía no calificada. Alianzas INDISA/UC/Salcobrand visibles pero sin fecha de novedad verificada. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Prueba compartida: SIS publica cartera de agosto el 02/10. No es prueba de publicación nativa de Colmena Golden Cross. (primary_opened_shared_dataset) | Alto en cohorte competitiva completa; valor incremental de newsroom por demostrar. Ruido: Medio-alto: descuentos, beneficios y banners sin fecha; holding no equivale a Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |
| isapre_consalud | Home abierta; gobierno corporativo, estudios y vínculo a ILC. El adapter compartido SIS cubre la entidad sin conector diario propio. | Alta en publicación SIS agregada; corporativa todavía no calificada. Beneficios preventivos visibles sin fecha; no convertir promoción en cambio de cobertura. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Prueba compartida: SIS publica cartera de agosto el 02/10. No es prueba de publicación nativa de Consalud. (primary_opened_shared_dataset) | Alto en cohorte competitiva completa; valor incremental de newsroom por demostrar. Ruido: Medio-alto: descuentos, beneficios y banners sin fecha; holding no equivale a Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |
| isapre_cruzblanca | Home abierta, redes y tablas públicas; grupo Bupa exige separar negocios. El adapter compartido SIS cubre la entidad sin conector diario propio. | Alta en publicación SIS agregada; corporativa todavía no calificada. Banner de precios 2026/27 indica vigencia, no fecha de noticia. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Prueba compartida: SIS publica cartera de agosto el 02/10. No es prueba de publicación nativa de Cruz Blanca. (primary_opened_shared_dataset) | Alto en cohorte competitiva completa; valor incremental de newsroom por demostrar. Ruido: Medio-alto: descuentos, beneficios y banners sin fecha; holding no equivale a Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |
| isapre_nuevamasvida | Home abierta; noticias/convenios por calificar. El adapter compartido SIS cubre la entidad sin conector diario propio. | Alta en publicación SIS agregada; corporativa todavía no calificada. Convenio Examedi localizado es de 2025; no muestra reciente validada. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Prueba compartida: SIS publica cartera de agosto el 02/10. No es prueba de publicación nativa de Nueva Masvida. (primary_opened_shared_dataset) | Alto en cohorte competitiva completa; valor incremental de newsroom por demostrar. Ruido: Medio-alto: descuentos, beneficios y banners sin fecha; holding no equivale a Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |
| isapre_vidatres | Home y novedades públicas abiertas. El adapter compartido SIS cubre la entidad sin conector diario propio. | Alta en publicación SIS agregada; corporativa todavía no calificada. Indicadores al 31/08/2026 son período de cifras, no publicación ni cambio contractual. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Prueba compartida: SIS publica cartera de agosto el 02/10. No es prueba de publicación nativa de Vida Tres. (primary_opened_shared_dataset) | Alto en cohorte competitiva completa; valor incremental de newsroom por demostrar. Ruido: Medio-alto: descuentos, beneficios y banners sin fecha; holding no equivale a Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |
| isapre_esencial | Home abierta, redes/beneficios; noticia de tercero no equivale a canal propio. El adapter compartido SIS cubre la entidad sin conector diario propio. | Alta en publicación SIS agregada; corporativa todavía no calificada. Redes INDISA/Andes visibles sin fecha corporativa verificada; cobertura INDISA existente debe cruzarse. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Prueba compartida: SIS publica cartera de agosto el 02/10. No es prueba de publicación nativa de Esencial. (primary_opened_shared_dataset) | Alto en cohorte competitiva completa; valor incremental de newsroom por demostrar. Ruido: Medio-alto: descuentos, beneficios y banners sin fecha; holding no equivale a Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |
| isapre_isalud | Home falló en una apertura; novedades y aviso de adecuación indexados. El adapter compartido SIS cubre la entidad sin conector diario propio. | Alta en publicación SIS agregada; corporativa todavía no calificada. Adecuación 2026 con vigencia junio y resolución marzo: histórica, no nueva en octubre. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Prueba compartida: SIS publica cartera de agosto el 02/10. No es prueba de publicación nativa de Isalud (registro SIS: Isalud Ltda.). (primary_opened_shared_dataset) | Alto en cohorte competitiva completa; valor incremental de newsroom por demostrar. Ruido: Medio-alto: descuentos, beneficios y banners sin fecha; holding no equivale a Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |
| isapre_fundacion | Home y noticias públicas; alto componente de beneficios. El adapter compartido SIS cubre la entidad sin conector diario propio. | Alta en publicación SIS agregada; corporativa todavía no calificada. Aviso sin aumento base 2026 indexado sin publicación inequívoca. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Prueba compartida: SIS publica cartera de agosto el 02/10. No es prueba de publicación nativa de Fundación. (primary_opened_shared_dataset) | Alto en cohorte competitiva completa; valor incremental de newsroom por demostrar. Ruido: Medio-alto: descuentos, beneficios y banners sin fecha; holding no equivale a Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |
| isapre_cruzdelnorte | Home pública abierta; no novedad fechada localizada. El adapter compartido SIS cubre la entidad sin conector diario propio. | Alta en publicación SIS agregada; corporativa todavía no calificada. Ausencia de muestra nativa reciente no se trata como cero cambios. | [2026-10-02](https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/) · Prueba compartida: SIS publica cartera de agosto el 02/10. No es prueba de publicación nativa de Cruz del Norte. (primary_opened_shared_dataset) | Alto en cohorte competitiva completa; valor incremental de newsroom por demostrar. Ruido: Medio-alto: descuentos, beneficios y banners sin fecha; holding no equivale a Isapre. | activar ahora · P0 · w4_isapres_2026_10_11 |

### Compras publicas

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| procurement · Mercado Público / ChileCompra | Demanda, inversión, proveedores ganadores y contratos sanitarios | Discovery, Watch, Benchmark | [Fuente](https://api.mercadopublico.cl/) | Diaria hábil incremental; adjudicaciones y cambios de etapa |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| procurement | Cliente API implementado, sin ruta periódica. API exige ticket; alternativa datos abiertos por validar. | Cliente actual conserva cierre, no evidencia suficiente de publicación/adjudicación. Cada campo requiere semántica propia. | [2026-10-02](https://www.chilecompra.cl/category/centro-de-documentacion/normativa/salud/) · Categoría oficial Salud con aviso 02/10; no se validó todavía licitación/adjudicación reciente a nivel transacción. (primary_indexed_not_transaction) | Muy alto: brecha de compras, medtech, laboratorios y financiamiento. Ruido: Alto si usa sólo palabra laboratorio o montos estimados. | activar ahora · P1 · w4_procurement_2026_10_11 |

### Judicializacion

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| pjud · Poder Judicial | Precios, coberturas, prestaciones y conflictos judiciales materiales | Watch, Discovery | [Fuente](https://www.pjud.cl/prensa-y-comunicaciones/noticias-del-poder-judicial) | Diaria hábil una vez calificado |
| tc_tdlc · Tribunal Constitucional / TDLC | Conflictos constitucionales y competencia sanitaria relevantes | Watch | [Fuente](https://www.tribunalconstitucional.cl/) | Semanal por roles sanitarios |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| pjud | Acceso observado exige JavaScript/CAPTCHA; sin detalle primario reciente capturado. | Requiere fecha de fallo y publicación, rol, instancia y efecto; titulares secundarios no bastan. | [Fecha no verificada](https://www.pjud.cl/prensa-y-comunicaciones/noticias-del-poder-judicial) · Bloqueo de verificación en prensa PJUD; no hay fallo reciente primario validado. (blocked) | Alto: brecha de judicialización. Ruido: Alto: casos individuales, reiteración y datos sensibles. | activar ahora · P1 · w4_legal_2026_10_11 |
| tc_tdlc | Superficies institucionales candidatas; no probadas en esta revisión. | Exigir rol, resolución, fecha y alcance; no detalle reciente validado. | No se obtuvo muestra primaria sanitaria reciente; no activar por completar lista. (primary_indexed) | Medio y episódico; complemento a PJUD/FNE. Ruido: Medio-alto: procedimientos sin efecto y doble cobertura. | secundaria · Sin incorporación priorizada |

### Regulacion

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| bcn · BCN / LeyChile | Texto consolidado, vigencia y cambios normativos | Watch, Benchmark | [Fuente](https://www.bcn.cl/leychile/) | Diaria para cambios detectados; snapshot de versión |
| compin · COMPIN | Licencias, discapacidad, cambios de gestión y capacidad | Watch, Trend | [Fuente](https://www.milicenciamedica.cl/) | Semanal por MINSAL/SUSESO; alertas institucionales |
| congress · Congreso: comisiones y tramitación sanitaria | Anticipar cambios legales antes de publicación en DO | Watch | [Fuente](https://www.senado.cl/actividad-legislativa/comisiones/) | Semanal; por hitos |
| contraloria · Contraloría: fiscalización sanitaria | Uso de fondos, licencias y fallas institucionales | Watch | [Fuente](https://siad.contraloria.cl/ca/recursos-digitales) | Mensual o por informe material |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| bcn | Normas indexadas y PDFs; calificar resolver canónico/versiones. Complementar DO/SIS. | Alta autoridad; alto riesgo de confundir fecha de generación PDF con norma/publicación/vigencia. | [2026-03-31](https://www.bcn.cl/leychile/navegar?idNorma=1222748) · Resolución de adecuación ISALUD publicada 31/03; prueba histórica, no novedad reciente. (primary_indexed) | Alto como referencia verificable; bajo como feed duplicado. Ruido: Bajo si actúa como resolver, alto con PDFs rejuvenecidos. | activar ahora · P1 · w4_legal_2026_10_11 |
| compin | Portal de trámites no es feed; usar noticias/normativa pública MINSAL/SUSESO existentes. Sin login. | Alta para anuncio oficial fechado, baja para banners de trámites sin año. | [2026-10-06](https://www.minsal.cl/presidente-kast-minsal-y-desarrollo-social-lanzan-plan-que-moderniza-y-agiliza-certificacion-de-discapacidad/) · Anuncio MINSAL sobre modernización de certificación de discapacidad. (primary_indexed) | Alto por cambios sistémicos; no requiere datos individuales. Ruido: Medio: instrucciones de uso repetidas y promesas sin resultados. | activar ahora · P1 · w4_occupational_2026_10_11 |
| congress | Agenda, sesiones y tramitación públicas; video/transcripción no constituyen norma aprobada. | Fecha de sesión, ingreso, votación y promulgación diferentes. | [2026-10-06](https://tv.senado.cl/tvsenado/comisiones/permanentes/salud/comision-de-salud/2026-10-05/120031.html) · Sesión de comisión de Salud sobre glosas presupuestarias; página fechada 06/10. (primary_indexed) | Medio-alto como alerta temprana. Ruido: Alto si cada sesión se publica o confunde propuesta con ley. | secundaria · Sin incorporación priorizada |
| contraloria | Índice público de reportes; seleccionar salud antes de profundizar. | Fecha de informe/período auditado distintas; última muestra específica de licencias localizada es histórica. | [Fecha no verificada](https://siad.contraloria.cl/ca/recursos-digitales) · Catálogo CIC; no se validó informe sanitario material dentro de 90 días. (primary_indexed_no_recent_health) | Medio como corroboración de MINSAL/SUSESO. Ruido: Alto si incorpora toda fiscalización pública. | secundaria · Sin incorporación priorizada |

### Financiamiento

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| cmf · CMF | Capital, deuda, propiedad, resultados y hechos esenciales | Discovery, Watch, Benchmark | [Fuente](https://www.cmfchile.cl/institucional/mercados/entidad.php?control=svs&grupo=&mercado=V&pestania=101&row=&rut=93930000&tipoentidad=RVEMI&vig=VI) | Diaria hábil hechos; trimestral EEFF |
| dipres · DIPRES | Presupuesto, ejecución y programas de Salud/FONASA | Benchmark, Trend, Watch | [Fuente](https://www.dipres.gob.cl/597/w3-multipropertyvalues-14626-38403.html) | Mensual ejecución; semanal durante discusión presupuestaria |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| cmf | Ficha de emisor/índices públicos; acceso/descarga dinámica y parser canónico pendientes. | Distinguir aviso, período financiero y calendario de entrega. PDF del emisor puede estar replicado en Bolsa. | [2026-08-05](https://cibe.bolsadesantiago.com/Documentos/Noticias/Hechos%20Esenciales/hes_2026080512549.pdf) · Aviso de CLC del 05/08 sobre cierre de aumento de capital; documento del emisor alojado en Bolsa, original CMF por resolver. (issuer_pdf_indexed) | Muy alto: respaldo hoy supuesto pero no conectado. Ruido: Bajo-medio: perímetros de holding y avisos administrativos. | activar ahora · P0 · w4_cmf_2026_10_11 |
| dipres | Índice público abierto; documentos/carga dinámica requieren resolver enlaces estables. | Proyecto, ley y ejecución diferentes; año fiscal no es fecha de publicación. | [2026-10-05](https://www.minsal.cl/salud-aumentara-su-presupuesto-en-47-para-2027-ministra-chomali-destaca-foco-en-gestion-eficiencia-y-reduccion-de-listas-de-espera/) · MINSAL anuncia aumento del presupuesto 2027 el 05/10; índice DIPRES del proyecto abierto. Falta normalizar tablas originales. (primary_indexed_context_only) | Muy alto: financiamiento público y capacidad futura. Ruido: Medio: anuncios agregados y dobles conteos entre transferencias. | activar ahora · P0 · w4_dipres_2026_10_11 |

### Datos demanda

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| ine · INE | Inflación de salud, demografía y denominadores territoriales | Benchmark, Trend | [Fuente](https://www.ine.gob.cl/estadisticas-por-tema/precios-e-inflacion/indice-de-precios-al-consumidor) | Mensual según calendario; demografía por versión |
| casen · CASEN / Observatorio Social | Previsión, acceso, gasto y segmentación socioeconómica | Benchmark, Trend | [Fuente](https://observatorio.ministeriodesarrollosocial.gob.cl/encuesta-casen-2024) | Chequeo mensual; carga sólo nueva versión/encuesta |
| cep · CEP | Prioridad social y percepción sobre salud | Trend | [Fuente](https://www.cepchile.cl/opinion-publica/encuesta-cep/) | Por publicación; control trimestral |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| ine | Tablas/boletines oficiales; descarga y normalización de división Salud pendientes. | Alta con base, división, unidad, territorio y mes de referencia. | [2026-10-08](https://www.ine.gob.cl/sala-de-prensa/prensa/general/noticia/2026/10/08/%C3%ADndice-de-precios-al-consumidor-%28ipc%29-de-septiembre-present%C3%B3-una-variaci%C3%B3n-mensual-de-0-4) · IPC de septiembre divulgado 08/10; dato general no puede sustituir componente Salud. (primary_indexed) | Alto para contexto y comparación real de gasto/demanda. Ruido: Bajo; riesgo de extrapolar IPC a costos clínicos específicos. | activar ahora · P1 · w4_socioeconomic_2026_10_11 |
| casen | Resultados y archivos oficiales de encuesta 2024; microdatos/metodología requieren adapter. | Separar levantamiento, difusión y revisión; pesos y cambios metodológicos obligatorios. | [Fecha no verificada](https://bidat.gob.cl/details/ficha/dataset/estadisticas-casen-2024) · Dataset CASEN 2024 difundido en enero 2026, fuera de ventana reciente; insumo estructural, no noticia fresca. (primary_indexed_historical) | Alto para segmentación; menor valor en Discovery. Ruido: Bajo si respeta error muestral y comparabilidad. | activar ahora · P1 · w4_socioeconomic_2026_10_11 |
| cep | Serie y PDFs públicos indexados; sin adapter justificado para MVP. | Fecha de encuesta/campo distinta de difusión; opinión no equivale a demanda observada. | [2026-06-10](https://www.cepchile.cl/opinion-publica/encuesta-cep/) · Encuesta N°96 difundida 10/06, campo abril-mayo; muestra disponible fuera de 90 días. (primary_indexed) | Medio contextual; menor urgencia que INE/CASEN. Ruido: Medio: coyuntura política y lectura causal incorrecta. | secundaria · Sin incorporación priorizada |

### Salud laboral

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| isl · ISL | Cobertura laboral pública, siniestralidad y compras/redes | Benchmark, Trend, Watch | [Fuente](https://www.isl.gob.cl/centro_estadisticas/) | Mensual datos; semanal convenios materiales |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| isl | Centro de estadísticas y noticias oficiales; parsear PDFs y períodos. | Infografía agosto 2026 identificada; día de publicación no confirmado. | [Fecha no verificada](https://www.isl.gob.cl/centro_estadisticas/) · Centro estadístico incluye agosto 2026; no fecha editorial exacta. Convenio RedSalud de marzo es sólo fixture histórico. (primary_indexed_period_only) | Alto para completar ACHS/Mutual/IST con asegurador público. Ruido: Medio-alto en noticias de talleres y ceremonias. | activar ahora · P1 · w4_occupational_2026_10_11 |

### Competencia

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| fne · FNE: operaciones de concentración | M&A de prestadores, farmacias y suministros | Discovery, Watch | [Fuente](https://www.fne.gob.cl/) | Diaria hábil |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| fne | Noticia primaria abierta, resoluciones/versiones públicas enlazables; algunas pendientes de publicación. | Fecha clara; aprobación, inicio de investigación y cierre son etapas diferentes. | [2026-09-23](https://www.fne.gob.cl/fne-aprueba-adquisicion-de-rotter-krauss-por-parte-de-salcobrand/) · Aprobación de adquisición de Rotter & Krauss por Salcobrand. (primary_opened) | Muy alto: M&A verificable transversal, más preciso que noticias promocionales. Ruido: Bajo con filtro sectorial y entidades. | activar ahora · P1 · w4_fne_2026_10_11 |

### Suministro

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| cenabast · CENABAST | Contratación, dispensación, farmacias y adopción digital | Discovery, Watch, Benchmark | [Fuente](https://www.cenabast.cl/category/noticias/) | 2 veces por semana; datos por release |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| cenabast | Listado/detalle HTML abierto con fecha, tablas y actores. | Alta fecha; claims/ahorros requieren contexto. Discrepancia 25/26 productos en noticia Ahumada debe preservarse. | [2026-10-07](https://www.cenabast.cl/421-locales-de-farmacias-ahumada-se-adhieren-a-la-ley-cenabast-para-fortalecer-la-cobertura-de-remedios-mas-baratos/) · Adhesión de 421 locales Ahumada; segunda muestra: piloto Barros Luco/Yapp publicado 24/09. (primary_opened) | Muy alto: un canal cubre farmacias, laboratorios, compras e innovación. Ruido: Medio: ceremonias y metas no ejecutadas. | activar ahora · P1 · w4_cenabast_2026_10_11 |

### Prestadores

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| alemana · Clínica Alemana | Capacidad, inversión, alianzas clínicas y tecnología | Discovery, Watch | [Fuente](https://www.clinicaalemana.cl/articulos/todas-las-noticias/novedades-alemana) | Semanal; aumentar sólo si densidad material lo justifica |
| uc_christus · UC CHRISTUS | Red, inversión, acceso y acuerdos asistenciales | Discovery, Watch | [Fuente](https://www.ucchristus.cl/blog-salud-uc/articulos) | Semanal |
| clc · Clínica Las Condes | Capital, estructura financiera, control e inversiones | Discovery, Watch, Benchmark | [Fuente](https://www.cmfchile.cl/institucional/mercados/entidad.php?control=svs&grupo=&mercado=V&pestania=101&row=&rut=93930000&tipoentidad=RVEMI&vig=VI) | Diaria hábil CMF; trimestral estados |
| interclinica · Interclínica / Interclínicas | Red regional, adquisiciones, capacidad y resultados | Benchmark, Watch | [Fuente](https://www.interclinica.cl/memorias-anuales) | Anual memorias con chequeo mensual; eventos por FNE/prensa |
| falp · FALP | Capacidad oncológica, diagnóstico, investigación y alianzas | Watch, Discovery | [Fuente](https://www.falp.org/noticia/falp-y-cchen-exploran-nuevas-oportunidades-de-colaboracion-para-la-investigacion-en-cancer/?cat=fundacion) | Semanal |
| uandes_clinic · Clínica Universidad de los Andes | Capacidad y competencia de alta complejidad | Watch | [Fuente](https://www.clinicauandes.cl/noticia) | Quincenal dirigida |
| meds · MEDS | Centros ambulatorios, alianzas y expansión | Watch | [Fuente](https://www.meds.cl/) | Quincenal dirigida |
| andes_regional · Andes Salud: Puerto Montt y Talca | Expansión regional y capacidad efectiva por sede | Discovery, Watch | [Fuente](https://www.andessaludpuertomontt.cl/noticias/andes-salud-puerto-montt-presenta-plan-2030/) | Semanal en conector existente |
| existing_networks · RedSalud, Bupa/IntegraMédica, INDISA, Dávila y ACHS Salud | Cobertura material de redes y filiales de conectores existentes | Discovery, Watch, Benchmark | [Fuente](https://www.redsalud.cl/) | Cadencia de conector existente; auditoría de sedes mensual |
| other_providers · Otros prestadores regionales, diagnóstico, diálisis y odontología | Detectar consolidación y capacidad fuera de las grandes redes | Watch, Benchmark | [Fuente](https://www.superdesalud.gob.cl/registro/) | Registro mensual; señales por FNE/CMF/prensa |
| public_providers · Servicios de Salud y hospitales públicos | Infraestructura, compras, productividad y alianzas público-privadas | Watch, Benchmark | [Fuente](https://www.minsal.cl/) | Semanal por proyectos; datos por release |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| alemana | Dominio antiguo redirige a clinicaalemana.cl; listado/detalle con fecha abiertos. | Fecha editorial verificable; evento y publicación no siempre coinciden. | [2026-09-25](https://www.clinicaalemana.cl/articulos/detalle/2026/llevamos-atencion-especializada-a-cauquenes-con-200-prestaciones-de-salud?itm_campaign=marca&itm_medium=web&itm_source=vitrina_cas) · Operativo en Cauquenes con prestaciones; útil para parser, no prueba de expansión permanente. (primary_opened) | Alto como actor, materialidad de muestra reciente insuficiente para aprobar feed. Ruido: Alto: educación, campañas, premios y operativos. | activar ahora · P1 · w4_providers_2026_10_11 |
| uc_christus | Listado y detalles públicos con fechas verificables. Contingencias es segunda superficie material, abierta pero sin fecha editorial. | Distinguir operativo 26–27/09 de noticia 01/10 y personas de prestaciones. La página contingencias requiere snapshot/versionado y corroboración temporal; no extraer todo como noticia nueva. | [2026-10-01](https://www.ucchristus.cl/blog-salud-uc/articulos/2026/operativo-en-la-region-de-antofagasta-concreto-427-consultas-y-36-cirugias-oftalmologicas) · Operativo oftalmológico en Antofagasta; prueba de fecha, no inversión permanente. (primary_opened) | Alto: hay evidencia de interrupción de capacidad en página de contingencia; falta asegurar fecha/versión para ingestión. Ruido: Alto: educación y difusión de atención comunitaria. | activar ahora · P1 · w4_providers_2026_10_11 |
| clc | Priorizar ficha de emisor CMF y documentos de inversionistas; newsroom no necesario para primera cobertura. | Aviso fechado; validar URL original CMF y no confundir calendario de EEFF. | [2026-08-05](https://cibe.bolsadesantiago.com/Documentos/Noticias/Hechos%20Esenciales/hes_2026080512549.pdf) · Aviso del emisor sobre cierre del aumento de capital, replicado por Bolsa. (issuer_pdf_indexed) | Muy alto en finanzas; alto ruido en contenido clínico corporativo. Ruido: Bajo en hechos esenciales; alto en noticias clínicas generales. | activar ahora · P0 · w4_cmf_2026_10_11 |
| interclinica | Memorias 2025/2024/2023 enlazadas y accesibles en índice; extracción PDF pendiente. | Año de ejercicio visible, fecha de publicación no demostrada. | [Fecha no verificada](https://www.interclinica.cl/memorias-anuales) · Índice oficial de memorias incluye 2025; no prueba de publicación reciente. (primary_opened_period_only) | Alto para mapa de red; newsrooms diarios aportarían poco. Ruido: Bajo en memorias con perímetro; medio en prensa. | activar ahora · P1 · w4_provider_data_2026_10_11, w4_fne_2026_10_11 |
| falp | Artículos oficiales indexados con fecha; listado canónico por resolver en piloto. | Buena fecha; visita exploratoria no demuestra acuerdo firmado ni inversión. | [2026-09-07](https://www.falp.org/noticia/falp-y-cchen-exploran-nuevas-oportunidades-de-colaboracion-para-la-investigacion-en-cancer/?cat=fundacion) · Exploración de colaboración FALP/CCHEN en investigación oncológica. (primary_indexed) | Alto para oncología y tecnología especializada. Ruido: Medio-alto: educación y exploración sin compromiso. | activar ahora · P1 · w4_providers_2026_10_11 |
| uandes_clinic | Noticias públicas indexadas; muestra material reciente no validada. | No usar avance de infraestructura universitaria como obra clínica sin identificación. | [Fecha no verificada](https://www.clinicauandes.cl/noticia) · Newsroom localizado; predominan premios y comunicaciones, sin inversión reciente confirmada. (primary_indexed_no_material_sample) | Medio incremental tras Alemana/UC/FALP. Ruido: Alto: premios, educación y confusión universidad/clínica. | secundaria · Sin incorporación priorizada |
| meds | Web corporativa indexada; señal de alianza reciente localizada en prensa, no confirmada en original. | Fecha de DF verificable por índice; falta detalle primario corporativo. | [2026-09-01](https://www.df.cl/empresas/salud/clinica-meds-y-universidad-diego-portales-sellan-alianza-que-creara-centro) · DF informa alianza MEDS–UDP para centro; lead secundario que requiere corroboración. (secondary_indexed) | Medio para ambulatorio; hoy puede cubrirlo DF. Ruido: Alto en deporte, marcas personales y promociones. | secundaria · Sin incorporación priorizada |
| andes_regional | Subdominios/sitios regionales con artículos fechados; ampliar frontier del actor ya conectado. | Fecha editorial y apertura/plan separadas; plan 2030 no implica capacidad instalada hoy. | [2026-09-09](https://www.andessaludpuertomontt.cl/noticias/andes-salud-puerto-montt-presenta-plan-2030/) · Puerto Montt presenta plan 2030 el 09/09; Talca publica apertura 08/09. (primary_indexed) | Alto: resuelve sesgo Santiago y límites del hub. Ruido: Medio: republicaciones de matriz y sedes. | activar ahora · P1 · w4_provider_data_2026_10_11 |
| existing_networks | Conectores ya declarados; issue #5 mantiene recuperación/balance. No certificarlos sanos por esta matriz. | Usar auditorías existentes por actor y ledger real; no se recapturó toda la ventana en Work 4. | Hay fuentes implementadas y auditorías de cobertura; ausencia de una sede en el ledger sigue siendo brecha. (repository_audit_only) | Alto en expansión de frontera; cero valor en duplicar conectores ya existentes. Ruido: Medio: duplicación matriz/filial y actividad promocional. | activar ahora · P1 · w4_provider_data_2026_10_11 |
| other_providers | Registro de prestadores ya conectado como familia; inventario de actores/propiedad debe validar sede y razón social. | No se calificaron todos los newsrooms independientes ni se obtuvo muestra primaria común. | Cobertura por intermediarios primarios y registro; no prometer censo exhaustivo de sitios privados. (primary_indexed) | Medio incremental; foco en operaciones concretas y concentración regional. Ruido: Alto si se rastrea cada clínica sin materialidad. | secundaria · Sin incorporación priorizada |
| public_providers | Cubrir prioritariamente MINSAL, DIPRES, ChileCompra y CENABAST; portales hospitalarios sólo para corroborar. | Distinguir licitación, construcción, recepción e inicio de operación. | [2026-09-24](https://www.cenabast.cl/cenabast-hospital-barros-luco-trudeau-y-yapp-inician-piloto-para-el-retiro-de-medicamentos-gratuitos-en-farmacias-privadas/) · Barros Luco participa en piloto de dispensación con Yapp. (primary_opened) | Alto con canales comunes; bajo retorno de cientos de newsrooms. Ruido: Alto en ceremonias y operativos. | secundaria · Sin incorporación priorizada |

### Universidades

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| udd · UDD / DHTAC y evaluación tecnológica | Tecnología clínica, evidencia de adopción y evaluación | Trend, Watch | [Fuente](https://medicina.udd.cl/dhtac/) | Quincenal |
| uchile · Universidad de Chile: Escuela de Salud Pública / RCSP | Epidemiología, sistemas y políticas sanitarias | Trend, Global Intelligence | [Fuente](https://saludpublica.uchile.cl/) | Mensual por investigación |
| uc_policy · UC: Centro de Políticas Públicas | Propuestas de sistema y ensayos clínicos | Trend, Watch | [Fuente](https://politicaspublicas.uc.cl/publicaciones/) | Mensual |
| clapes · CLAPES UC y otros centros de estudios | Economía de salud, datos y propuestas sectoriales | Trend | [Fuente](https://clapesuc.cl/investigacion/) | Mensual dirigida |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| udd | Noticia oficial fechada y duplicado institucional; calificar índice estable. | Fecha precisa; separar prototipo/plataforma de resultado clínico demostrado. | [2026-07-14](https://medicina.udd.cl/dhtac/2026/07/14/clinica-alemana-y-udd-impulsan-plataforma-digital-para-apoyar-la-toma-de-decisiones-clinicas-basada-en-evidencia/) · UDD y Alemana impulsan plataforma de apoyo a decisiones clínicas. (primary_indexed) | Alto para innovación con actor clínico identificable. Ruido: Medio-alto: seminarios, aspiraciones y publicaciones duplicadas. | activar ahora · P1 · w4_innovation_2026_10_11 |
| uchile | Registro de prensa y revista públicos indexados; registro de prensa es secundario, no estudio original. | Requiere fecha, método, DOI/URL de estudio y período; abstracts no equivalen a resultados definitivos. | [Fecha no verificada](https://saludpublica.uchile.cl/noticias-esp/registro-de-prensa/2026-registro-de-prensa/septiembre) · Registro de prensa septiembre 2026; se localizó superficie, no estudio original reciente calificado. (primary_indexed_period_only) | Medio-alto contextual. Ruido: Medio: opinión, prensa republicada y congresos. | secundaria · Sin incorporación priorizada |
| uc_policy | Publicaciones y PDFs públicos; filtro sanitario necesario. | Alta trazabilidad de autor/documento; propuesta no es política vigente. | [Fecha no verificada](https://politicaspublicas.uc.cl/web/content/uploads/2026/04/CAP7-Propuesta-para-Chile25.pdf) · Capítulo de propuestas sobre ensayos clínicos publicado en abril; fuera de 90 días. (primary_indexed_historical) | Medio, principalmente escenarios. Ruido: Medio: opinión/política no aplicada. | secundaria · Sin incorporación priorizada |
| clapes | Informes indexados; cada centro adicional requiere evaluar metodología y financiamiento. | Fecha verificable en informe; mantener atribución y sesgo de origen. | [2026-04-24](https://clapesuc.cl/investigacion/informe-el-desafio-de-generar-politicas-publicas-con-el-uso-de-datos-de-salud-agregados-en-el-tiempo) · Informe sobre políticas con datos agregados de salud, 24/04; histórico. (primary_indexed) | Medio; aporta interpretación, no reemplaza INE/CASEN. Ruido: Medio-alto: advocacy, columnas y métodos heterogéneos. | secundaria · Sin incorporación priorizada |

### Innovacion

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| startup_chile · Start-Up Chile / CORFO | Descubrir empresas, cohortes y financiamiento temprano sanitario | Watch, Benchmark | [Fuente](https://startupchile.org/portafolio/) | Trimestral por cohorte |
| cens · CENS | Interoperabilidad, evaluación y adopción de salud digital | Trend, Watch | [Fuente](https://cens.cl/makecens/) | Quincenal |
| prosalud · Pro Salud Chile / Transforma Salud | Mapa de actores y alianzas de salud digital | Watch | [Fuente](https://prosaludchile.cl/noticias/noticias-de-salud/) | Mensual dirigida |
| healthtech · Healthtech: Healthatom, Examedi, Yapp, I-MED y cartera abierta | Rondas, contratos, despliegue y cambios de modelo | Watch, Discovery | [Fuente](https://www.healthatom.com/prensa) | Quincenal dirigida por empresa; eventos en fuentes primarias comunes |
| nonhealth_biotech · Biotech no sanitaria / ChileBio agrícola | Control negativo de clasificación por sector | Discovery | [Fuente](https://www.chilebio.cl/) | No recolectar para este universo |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| startup_chile | Portafolio/blog públicos indexados; clasificación healthtech, datos por empresa y ronda deben corroborarse. | Cohorte/selección no prueba inversión privada, ingresos o eficacia. | [2026-09-21](https://www.economia.gob.cl/2026/09/21/nueva-generacion-de-start-up-chile-comienza-proceso-de-aceleracion-en-nido-lucia.htm) · Ministerio informa inicio cohorte BIG 12 el 21/09; no señal healthtech específica. (primary_indexed) | Medio como seed de entidades; bajo como feed de salud hoy. Ruido: Alto: emprendimientos no sanitarios y eventos. | post-MVP · Sin incorporación priorizada |
| cens | Listado/detalle HTML público abierto; bienes públicos requieren extraer versión/autor. | Fecha clara de noticia; webinar no prueba compra ni contratación. | [2026-09-10](https://cens.cl/compras-publicas-de-innovacion-nuevas-herramientas-para-abordar-desafios-de-salud/) · Webinar sobre compras públicas de innovación; negativo editorial útil salvo documento técnico nuevo. (primary_opened) | Alto potencial técnico, valor real condicionado a documentos y adopciones. Ruido: Alto: cursos, agenda, certificaciones y promoción. | activar ahora · P1 · w4_innovation_2026_10_11 |
| prosalud | Noticias institucionales indexadas; predominan encuentros y comités. | No detalle reciente de financiamiento/adopción validado. | [Fecha no verificada](https://prosaludchile.cl/noticias/noticias-de-salud/) · Actividades/estrategia 2026–27 y ferias; no operación material reciente probada. (primary_indexed_no_material_sample) | Medio para descubrir actores. Ruido: Alto: eventos y declaraciones gremiales. | secundaria · Sin incorporación priorizada |
| healthtech | Healthatom sin novedad reciente validada; Examedi blog, Yapp vía contraparte CENABAST, I-MED vía SIS. | Fecha/counterparty/etapa obligatorias; premio o API administrativa no prueba adopción clínica. | [2026-09-24](https://www.cenabast.cl/cenabast-hospital-barros-luco-trudeau-y-yapp-inician-piloto-para-el-retiro-de-medicamentos-gratuitos-en-farmacias-privadas/) · Piloto Yapp/Barros Luco documentado por contraparte pública; no despliegue nacional. (primary_opened) | Alto cuando hay contrato/ronda; bajo para blogs generales. Ruido: Alto: promoción, premios y claims clínicos. | secundaria · Sin incorporación priorizada |
| nonhealth_biotech | Sitio relacionado con biotecnología agrícola; nombre no prueba pertinencia sanitaria. | No hay señal sanitaria material reciente validada. | La palabra biotech por sí sola no habilita el dominio. (primary_indexed) | Bajo para Alicanto Salud. Ruido: Muy alto: falso positivo semántico. | descartar · Sin incorporación priorizada |

### Capital innovacion

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| lavca · LAVCA | Capital privado y venture capital latinoamericano | Global Intelligence, Benchmark | [Fuente](https://www.lavca.org/research/) | Semestral/release |
| vc_maps · LatamList, Dealroom y portafolios VC | Descubrir rondas y entidades que luego requieren confirmación | Watch, Global Intelligence | [Fuente](https://latamlist.com/) | Quincenal dirigida tras MVP |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| lavca | Investigación pública indexada; bases detalladas reservadas a miembros. | Período semestral y publicación diferentes; cifra LatAm no es Chile/salud. | [Fecha no verificada](https://www.lavca.org/research/) · Reporte Mid-Year 2026 localizado, sin transacción reciente sanitaria chilena validada. (primary_indexed_period_only) | Medio para contexto de inversión. Ruido: Medio: geografía/sector amplios y cobertura parcial de deals. | post-MVP · Sin incorporación priorizada |
| vc_maps | Roadmap contempla fuentes públicas/permitidas; APIs/licencia y portafolios no calificados aquí. | Sin ronda reciente primaria validada. Anuncio, cierre y monto revelado deben distinguirse. | No hay muestra reciente comprobada de Chile/salud; corroborar en startup/inversor y transacción. (primary_indexed) | Medio potencial; menor que FNE/CMF para etapa actual. Ruido: Alto: rondas repetidas, estimaciones y cobertura selectiva. | post-MVP · Sin incorporación priorizada |

### Laboratorios

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| pharma_primary · Laboratorios: ISP + compras como canal común | Registro sanitario, seguridad, oferta, demanda y adjudicaciones | Watch, Benchmark | [Fuente](https://www.ispch.cl/anamed/) | Cadencia ISP existente; compras diaria cuando calificada |
| roche · Roche Chile / Roche global | Inversión, diagnóstico, acceso y pipeline | Watch, Global Intelligence | [Fuente](https://www.roche.cl/media) | Mensual local; global por hito |
| megalabs · Megalabs Chile y laboratorios nacionales | Capacidad, inversiones, compras y cambios de suministro | Watch | [Fuente](https://www.megalabschile.cl/noticias/) | Mensual dirigida |
| saval · SAVAL / SAVALnet | Innovación y educación profesional como contexto | Trend | [Fuente](https://www.savalnet.cl/mundo-medico/noticias/) | Mensual dirigida |
| pharma_associations · CIF y asociaciones de laboratorios | Posiciones sectoriales, ensayos e inversión | Watch, Trend | [Fuente](https://www.cifchile.cl/noticias/) | Mensual dirigida |
| pfizer_existing · Pfizer Chile y otros emisores internacionales | Inversión, alianzas y acceso de actores específicos | Watch, Global Intelligence | [Fuente](https://www.pfizer.cl/) | Cadencia existente Pfizer; otros sólo por evento |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| pharma_primary | ISP ANAMED/surveillance ya declarados; issue #5 mantiene verificación de recuperación. ChileCompra/CENABAST amplían mercado. | Separar fecha de alerta, lote/evento, resolución y cierre del retiro. | Revisiones existentes de ISP; este trabajo no certifica ejecución ni recaptura toda su ventana. (repository_audit_only) | Muy alto transversal; no requiere un feed por laboratorio. Ruido: Bajo en actos regulatorios, medio si duplica alerta/noticia. | secundaria · Sin incorporación priorizada |
| roche | Media local indexado con contenido antiguo; comunicados globales fechados disponibles. | Regulador, país y etapa obligatorios; prioridad FDA no equivale a registro ISP. | [2026-09-10](https://www.roche.com/media/releases/med-cor-2026-09-10) · Comunicado global de revisión prioritaria FDA para Enspyng; no demuestra autorización chilena. (primary_indexed) | Medio como corroboración tecnológica. Ruido: Alto en productos/claims y falta de aplicabilidad local. | secundaria · Sin incorporación priorizada |
| megalabs | Noticias corporativas indexadas; sin detalle reciente material validado. | No inferir fecha desde recrawl ni nombre de ruta de PDF de alerta. | [Fecha no verificada](https://www.megalabschile.cl/noticias/) · Superficie localizada; no señal corporativa reciente calificada. (primary_indexed_no_material_sample) | Medio si aparece inversión o contrato; cobertura común más eficiente. Ruido: Alto en campañas, formación y lanzamientos no materiales. | secundaria · Sin incorporación priorizada |
| saval | Noticias fechadas indexadas; mucho contenido educativo. | Fecha editorial disponible, novedad de app no implica adopción o beneficio clínico. | [2026-10-09](https://www.savalnet.cl/mundo-medico/noticias/presentan-aplicacion-movil-centro-saval-en-congreso-de-medicina-interna.html) · Lanzamiento de aplicación Centro SAVAL en congreso; señal reciente de bajo valor estratégico. (primary_indexed) | Bajo-medio incremental. Ruido: Alto: congresos, opinión y educación médica. | secundaria · Sin incorporación priorizada |
| pharma_associations | Noticias gremiales públicas indexadas; otras asociaciones (p. ej., ASILFA) necesitan calificación de superficie. | Atribuir afirmaciones al gremio; sin detalle reciente material verificado. | [Fecha no verificada](https://www.cifchile.cl/noticias/) · Seminarios/actividad de ensayos 2026; no contrato, inversión ni cambio regulatorio reciente demostrado. (primary_indexed_no_material_sample) | Medio contextual; no sustituye regulador o estudios. Ruido: Alto: advocacy y eventos. | secundaria · Sin incorporación priorizada |
| pfizer_existing | Pfizer tiene conector; no se recertifica en esta revisión. Resto por fuente primaria del evento. | No confundir fecha global con disponibilidad Chile; fuente corporativa exige atribución. | Conector Pfizer en universo issue #5; no demuestra cobertura de la familia pharma. (repository_audit_only) | Medio incremental; alta cobertura por ISP/CENABAST/Reuters. Ruido: Alto en campaña y marca. | secundaria · Sin incorporación priorizada |

### Farmacias

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| ahumada · Farmacias Ahumada | Red de dispensación, precios y acuerdos público-privados | Watch, Benchmark | [Fuente](https://www.farmaciasahumada.cl/) | Por evento; canal primario CENABAST semanal |
| salcobrand · Salcobrand / Empresas SB | M&A, integración de canales y alianzas | Watch, Discovery | [Fuente](https://salcobrand.cl/) | Por evento FNE/CENABAST; revisión corporativa mensual |
| cruzverde · Cruz Verde / Socofar | Red, propiedad, abastecimiento y acuerdos | Watch, Benchmark | [Fuente](https://www.cruzverde.cl/) | Mensual dirigida por actor |
| independent_pharmacies · Farmacias independientes y comunales | Cobertura territorial y acceso a medicamentos | Benchmark, Trend | [Fuente](https://www.cenabast.cl/) | Mensual datos; hitos por publicación |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| ahumada | Retail no recomendado como feed; contraparte CENABAST dispone de comunicado y tabla públicos. | Publicación clara en contraparte; precios y ahorro con fecha y comparador, no serie homogénea. | [2026-10-07](https://www.cenabast.cl/421-locales-de-farmacias-ahumada-se-adhieren-a-la-ley-cenabast-para-fortalecer-la-cobertura-de-remedios-mas-baratos/) · Adhesión Ley CENABAST de 421 locales documentada el 07/10. (primary_opened) | Alto sobre estructura/acceso, bajo en ofertas diarias. Ruido: Alto si se usa ecommerce como noticia. | secundaria · Sin incorporación priorizada |
| salcobrand | Priorizar FNE y contraparte pública; retail y programas de innovación sólo descubren leads. | Aprobación de compra identificable; cierre y perímetro requieren fuente adicional. | [2026-09-23](https://www.fne.gob.cl/fne-aprueba-adquisicion-de-rotter-krauss-por-parte-de-salcobrand/) · FNE aprueba compra Rotter & Krauss por Salcobrand el 23/09. (primary_opened) | Alto para concentración y expansión a óptica. Ruido: Alto en promociones; bajo en resolución FNE. | secundaria · Sin incorporación priorizada |
| cruzverde | Retail público; no se calificó newsroom corporativo. No usar páginas internas de empleados aunque aparezcan indexadas. | Sin muestra primaria material reciente validada; no inventar actividad por completar tres cadenas. | Ninguna señal reciente pública material verificada en este trabajo. (primary_indexed) | Medio-alto por tamaño del actor; recurrencia propia por demostrar. Ruido: Alto en promociones y contenidos no destinados al público. | secundaria · Sin incorporación priorizada |
| independent_pharmacies | Registro/canales CENABAST y municipalidad sólo con dato agregado público. | Direcciones/locales y fármacos cambian; conservar snapshot y fecha de actualización real. | [2026-09-24](https://www.cenabast.cl/cenabast-hospital-barros-luco-trudeau-y-yapp-inician-piloto-para-el-retiro-de-medicamentos-gratuitos-en-farmacias-privadas/) · Piloto Barros Luco/Yapp usa farmacias adheridas; no representa todas las independientes. (primary_opened) | Alto en mapa territorial; poco valor en noticias por farmacia. Ruido: Bajo-medio con filtro de cobertura. | secundaria · Sin incorporación priorizada |

### Medtech

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| ge · GE HealthCare | M&A, tecnologías diagnósticas y suministro | Global Intelligence, Watch | [Fuente](https://www.gehealthcare.com/en/about/newsroom/press-releases) | Semanal dirigida por eventos |
| siemens · Siemens Healthineers | Equipamiento, inversión hospitalaria y diagnóstico | Global Intelligence, Watch | [Fuente](https://www.siemens-healthineers.com/latam/news) | Mensual; hitos regionales |
| medtronic · Medtronic y fabricantes de dispositivos | Robótica, dispositivos, acuerdos y financiamiento | Global Intelligence, Watch | [Fuente](https://news.medtronic.com/press-releases?keywords=Innovative+Integrated+Health) | Mensual dirigida |
| adimech · ADIMECH | Estándares, regulación y ecosistema de dispositivos | Watch, Trend | [Fuente](https://adimech.org/) | Mensual dirigida |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| ge | Newsroom y comunicado primario indexados; acceso periódico aún no implementado. | Fecha de anuncio explícita; acuerdo de compra no equivale a cierre ni operación Chile. | [2026-10-05](https://www.gehealthcare.com/en-us/about/newsroom/press-releases/ge-healthcare-to-acquire-sofie-biosciences-establishing-a-final-mile-footprint-for-pet-radiopharmaceutical-supply-in-the-us) · Anuncio compra SOFIE para radiofármacos PET en EE.UU.; corrobora Reuters. (primary_indexed) | Alto en evento material; canal permanente incremental por probar. Ruido: Medio-alto: productos/claims y geografía externa. | secundaria · Sin incorporación priorizada |
| siemens | Portal regional de noticias/press releases indexado. | Separar país de instalación y fecha editorial; noticia regional no es inversión Chile. | [2026-07-29](https://www.siemens-healthineers.com/latam/news) · Instalación/tecnología en Hospital Italiano de Argentina el 29/07; señal regional. (primary_indexed) | Medio para transferencias tecnológicas. Ruido: Alto en novedades comerciales y adjudicaciones no confirmadas. | secundaria · Sin incorporación priorizada |
| medtronic | Portal global de comunicados indexado; no detalle reciente con fecha validado en esta auditoría. | Distinguir aprobación, indicación, jurisdicción y comercialización. | [Fecha no verificada](https://news.medtronic.com/press-releases?keywords=Innovative+Integrated+Health) · Índice de comunicados localizado; señal reciente material pendiente. (primary_indexed_no_material_sample) | Medio incremental tras Reuters/ISP/compras. Ruido: Alto en claims de producto. | secundaria · Sin incorporación priorizada |
| adimech | Sitio gremial público indexado; dominio verificado adimech.org. | Actividad de ciberseguridad/HIMSS localizada sin inversión reciente fechada calificada. | [Fecha no verificada](https://adimech.org/) · Noticias/eventos gremiales; no evento comercial material reciente confirmado. (primary_indexed_no_material_sample) | Medio como perspectiva sectorial. Ruido: Alto: agenda, advocacy y premios. | secundaria · Sin incorporación priorizada |

### Talento

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| careers · Career pages / ATS públicos de 10–20 actores | Cambios de capacidades, contratación y perfiles tecnológicos | Trend, Benchmark | [Fuente](https://www.redsalud.cl/) | Semanal si se aprueba cartera de ATS |
| linkedin · LinkedIn | Descubrimiento/distribución complementaria | Watch | [Fuente](https://www.linkedin.com/) | Manual dirigida |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| careers | Compromiso roadmap; endpoints públicos/condiciones por actor no calificados. No fingir universo de 20 cubierto. | Fecha original, republicación, ubicación e ID de vacante imprescindibles; sin muestra reciente verificada. | No se validó lote actual de ATS. Primero inventario público de Isapres/redes priorizadas, con dedup de vacantes. (primary_indexed) | Medio para Talent Intelligence, menor urgencia que finanzas/compras. Ruido: Alto: reposts, consultoras y vacantes permanentes. | post-MVP · Sin incorporación priorizada |
| linkedin | Roadmap excluye dependencia de scraping; no se presupone acceso automatizado. | Sin muestra pública material reciente calificada; posts no prueban contratos. | No se usa como fuente de ingesta recurrente. (primary_indexed) | Bajo como ingesta, medio como pista humana. Ruido: Alto: autopromoción, duplicados y permisos. | descartar · Sin incorporación priorizada |

### Latam

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| latam · Expansión Colombia/Perú → Argentina/Uruguay → Brasil | Replicar mapa de fuentes por país | Global Intelligence, Benchmark | [Fuente](https://www.paho.org/) | Diseño por país después de MVP; vigilancia regional OPS antes |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| latam | Roadmap 6–8 meses; reguladores/compras/justicia/corporate/VC de cada país todavía sin calificación. | Sin prueba por país en este trabajo; no prometer universo internacional implementado. | Se preserva expansión por familias y country_code, sin hardcodear Chile. (primary_indexed) | Alto posterior; dispersa foco actual. Ruido: Alto por legislación, idioma y comparabilidad. | post-MVP · Sin incorporación priorizada |

### Core existente

| ID / fuente | Propósito analítico | Módulo | Superficie primaria | Frecuencia |
| --- | --- | --- | --- | --- |
| core_official · MINSAL / FONASA / DEIS / SUSESO / Diario Oficial | Política, cobertura pública, epidemiología/utilización, seguridad social y actos normativos; completar operación antes de duplicar fuentes. | Discovery, Watch, Trend, Benchmark | [Fuente](https://www.minsal.cl/) | Diaria normativa/noticias; estadísticas por release |
| press_chile · Prensa Chile: DF / Pulso y medios secundarios | Inversión, M&A y señales empresariales tempranas | Discovery, Watch | [Fuente](https://www.df.cl/empresas/salud) | Cadencia existente diaria/múltiple diaria |
| mutualities_existing · ACHS Seguro Laboral / Mutual de Seguridad / IST | Competencia laboral, red prestadora, prevención y siniestralidad | Watch, Benchmark, Trend | [Fuente](https://www.achs.cl/centro-de-noticias) | Cadencia existente; estadísticas por release |

| ID | Disponibilidad técnica | Fechas y evidencia | Señal de prueba / nivel | Valor esperado / ruido | Decisión / backlog |
| --- | --- | --- | --- | --- | --- |
| core_official | Fuentes declaradas dentro de los 27; recuperación runtime/fechas/archivos sigue abierta bajo issue #5. No se propone otra copia de esos conectores. | Acto, publicación, vigencia y período son distintos. DEIS y FONASA requieren versiones y denominadores; faltantes no son ceros. | [2026-10-06](https://www.minsal.cl/presidente-kast-minsal-y-desarrollo-social-lanzan-plan-que-moderniza-y-agiliza-certificacion-de-discapacidad/) · Anuncio MINSAL COMPIN del 06/10; sólo muestra de la familia, no validación completa de FONASA/DEIS/SUSESO/DO. (primary_indexed) | Muy alto; expansión complementa sin sustituir recuperación. Ruido: Medio: actos administrativos, republicaciones y episodios sin cambio material. | secundaria · Sin incorporación priorizada |
| press_chile | DF y Pulso declarados; Work 3 acredita fallos pendientes de fecha/cola y falta de prueba posterior a reparación. Otros medios sólo si añaden cobertura. | Fecha editorial de origen y evento distintas; conservar procedencia de modificación. Alta confianza no elimina gate temporal. | [2026-09-01](https://www.df.cl/empresas/salud/clinica-meds-y-universidad-diego-portales-sellan-alianza-que-creara-centro) · DF informa alianza MEDS–UDP; ejemplo de coverage secundaria, no prueba de ingesta real. (secondary_indexed) | Alto con operación correcta; menor valor de duplicar medios generalistas. Ruido: Medio: columnas, paywalls, notas repetidas y titulares sin etapa de transacción. | secundaria · Sin incorporación priorizada |
| mutualities_existing | Conectores en issue #5; calificación/ejecución real aún a reconciliar. ISL se añade como contraparte pública. | Datos SUSESO pueden comparar actores con denominadores; newsrooms no sustituyen series. | Artefactos de auditoría existentes; sin nueva muestra primaria fechada propia en este trabajo. (repository_audit_only) | Alto como familia, incremento de valor depende de completar datos y operación. Ruido: Alto en talleres/campañas; bajo en estadísticas comparables. | secundaria · Sin incorporación priorizada |

## Backlog ejecutable

Fuente canónica: [paquetes JSON](../config/source_expansion_backlog_2026_10_11.json). Cada paquete define owner, primera acción, pasos, fixtures/negativos, archivos de entrada, criterios de aceptación, dependencias, bloqueos y salida de evidencia. Se enlaza también desde `orchestrator_queue.json`. No requiere buscar otra vez qué hacer.

| Prioridad / ID | Objetivo | Owner | Primera acción | Bloqueo externo |
| --- | --- | --- | --- | --- |
| P0 · w4_isapres_2026_10_11 | Cohorte competitiva completa de las 10 Isapres | Data Intelligence + Market Intelligence | Extraer registro oficial de Isapres y fijar códigos 63,67,76,78,80,81,94,99,107,108, tipo abierta/cerrada, alias, grupo y vigencia. | Ninguno acreditado; calidad pendiente |
| P0 · w4_cmf_2026_10_11 | Financiamiento y hechos esenciales CMF | Financial Intelligence + Source Engineering | Crear inventario de emisores/grupos con RUT verificado (comenzar CLC 93930000, ILC, grupos de prestadores e Isapres); documentar filiales fuera del perímetro reportante. | Ninguno acreditado; calidad pendiente |
| P0 · w4_dipres_2026_10_11 | Presupuesto y ejecución de salud DIPRES | Public Finance + Data Intelligence | Descubrir proyecto 2027 y series de ejecución por Partida/Capítulo/Programa de Salud y FONASA; extraer URL de cada archivo desde índice oficial. | Ninguno acreditado; calidad pendiente |
| P1 · w4_fne_2026_10_11 | M&A sanitario desde FNE | Competition Intelligence + Source Engineering | Descubrir noticias/operaciones de concentración FNE con filtros de actores sanitarios y enlaces a resoluciones públicas. | Ninguno acreditado; calidad pendiente |
| P1 · w4_cenabast_2026_10_11 | Acceso a medicamentos, canales y adopción tecnológica CENABAST | Supply Chain Intelligence + Source Engineering | Implementar listado/detalle de prensa CENABAST; conservar tablas y referencias de abastecimiento con extracción mínima. | Ninguno acreditado; calidad pendiente |
| P1 · w4_procurement_2026_10_11 | Licitaciones y adjudicaciones sanitarias trazables | Procurement Intelligence + Source Engineering | Revisar src/radar_salud/mercado_publico.py y documentación oficial ChileCompra; comprobar disponibilidad de ticket autorizado sin mostrar secretos. No usar ClaveÚnica ni ticket de terceros. | Ticket autorizado para API o ruta abierta equivalente por verificar. |
| P1 · w4_who_2026_10_11 | OMS recurrente con señales internacionales materiales | Global Intelligence + Source Engineering | Implementar discovery desde WHO news-room y detalle; priorizar guías, emergencias, epidemiología y cambios de política. | Ninguno acreditado; calidad pendiente |
| P1 · w4_reuters_2026_10_11 | Reuters: ruta recurrente permitida o hold explícito | Global Intelligence + Source Engineering | Auditar ruta pública/contratada permitida de Reuters; documentar condiciones de uso, estabilidad del índice y derechos de extracción/resumen antes de automatizar. | Acceso y derechos para automatización no acreditados en repositorio. |
| P1 · w4_paho_2026_10_11 | OPS: resolver acceso público a vigilancia regional | Epidemiology Intelligence + Source Engineering | Probar rutas oficiales públicas documentadas de informes técnicos/influenza y repositorio alternativo oficial; registrar HTTP, fecha y límites. | 403 en listado y PDF desde entorno de consulta. |
| P1 · w4_legal_2026_10_11 | BCN como resolver normativo y PJUD como factibilidad | Legal Intelligence + Source Engineering | BCN: enlazar normas originadas en DO/SIS con idNorma, fecha original, vigencia, versión y cambios; no crear una noticia por regeneración de PDF. | PJUD presenta verificación JavaScript/CAPTCHA; sin bypass. |
| P1 · w4_providers_2026_10_11 | Pilotos selectivos Alemana, UC CHRISTUS y FALP | Provider Intelligence + Source Engineering | Muestrear ventana completa 90 días por newsroom con paginación, fechas verificadas, motivos de rechazo y cobertura. | Ninguno acreditado; calidad pendiente |
| P1 · w4_provider_data_2026_10_11 | Memorias Interclínica y subcanales regionales de redes existentes | Provider Intelligence + Data Intelligence | Interclínica: extraer memorias 2025/2024/2023 por URL/hash, instalaciones, control y magnitudes comparables; guardar fecha de publicación desconocida cuando corresponda. | Ninguno acreditado; calidad pendiente |
| P1 · w4_socioeconomic_2026_10_11 | INE y CASEN como base comparable de mercado | Data Intelligence | INE: usar release calendar y archivo IPC para división Salud, además de población/proyecciones verificadas; conservar base, territorio y frecuencia. | Ninguno acreditado; calidad pendiente |
| P1 · w4_occupational_2026_10_11 | ISL agregado y COMPIN a través de canales oficiales existentes | Occupational Intelligence + Data Intelligence | ISL: detectar infografías/estadísticas mensuales y memorias, normalizar trabajadores/empleadores/atenciones por período y definición. | Ninguno acreditado; calidad pendiente |
| P1 · w4_innovation_2026_10_11 | UDD/DHTAC y CENS: tecnología con evidencia de adopción | Technology Intelligence + Source Engineering | Calificar publicaciones DHTAC/UDD y bienes públicos/noticias CENS; fijar entidades y tipos: investigación, piloto, evaluación, despliegue, financiamiento. | Ninguno acreditado; calidad pendiente |

Orden de preparación: Isapres → CMF → DIPRES. Después FNE/CENABAST/WHO y pilotos de alto valor. Factibilidades bloqueadas se ejecutan de forma acotada y se continúa otra tarea; no se repiten indefinidamente ni se deja todo esperando credenciales. Mantener las dependencias core antes de promover una fuente a activa.

**Cierre de cada incorporación:** quality gate completo, ventana 90 días reconciliada o límite explícito, fixture material y negativos, deduplicación, fechas separadas, ruta real y dos ejecuciones separadas según cadencia con ledger/health. Una prueba omitida no es PASS; una fuente aprobada no obliga a publicar una card.

La cola persistida no despierta por sí misma una sesión detenida. Este trabajo no crea automaciones, despacha recolecciones ni acredita que los paquetes hayan sido ejecutados.

## Trazabilidad y validación

- [Matriz canónica y evidencia](../data/audits/source_expansion_matrix_2026_10_11.json)
- [Backlog detallado](../config/source_expansion_backlog_2026_10_11.json)
- [Cola del proyecto](../config/orchestrator_queue.json) y [PMO](../config/pmo_baseline.json)
- [Auditoría Work 3](../data/audits/work3_adversarial_2026_10_11.json) y [suplemento](../data/audits/work3_adversarial_2026_10_11_supplement.json)

Comprobación local: JSON válidos; diez códigos Isapre únicos (7 abiertas, 3 cerradas); cobertura de todos los mínimos; todas las filas P0/P1 enlazan tareas; toda tarea tiene fuentes, primera acción y aceptación; dependencias sin ciclos; referencias/archivos existentes; diff sin espacios inválidos. Los 18 controles existentes de cola, PMO y catálogo pasaron mediante ejecución directa de sus funciones y temporales aislados: pytest no está instalado en este entorno. No equivale a CI completa ni validación de conectores. [Evidencia de validación](../data/audits/source_expansion_validation_2026_10_11.json).
