# Comité Editorial Senior — 11 octubre 2026

Dictamen: **stock requiere correcciones; nuevo Insight aprobado con límites explícitos**. Base `9826b3b727cd7d9f504148072385d4cd37405895`; sólo staging.

## Alcance verificable

Revisión de los 182 registros fechados entre 2026-07-14 y 2026-10-11 dentro de un histórico de 733, más 2 agregados exclusivos del snapshot: **184 unidades iniciales**, más **1 evento recuperado tardíamente** desde Work3 y verificado contra DF, La Tercera y UC CHRISTUS: **185 en ese corte**, más7 originales del suplemento `ce3c624`: **192 unidades documentales revisadas al cierre**. Se revisaron materialidad, integridad, duplicación, cifras, actores, contexto y utilidad en cada fila. Un registro sin fecha queda HOLD adicional. Matriz: `data/audits/editorial_stock_90d_2026_10_11.json`.

Esto cubre el stock recuperado, no la reconciliación externa27/27. La cola bruta de 9,59MB no pudo leerse: fetch_blob cerró transporte y raw fetch rechazó tamaño/formato; no se certifican todos los pendientes/rechazos. Health y stock tienen cortes distintos y sus contadores no son intercambiables.

## Resultados

{"GROUP": 47, "HOLD": 89, "PASS": 15, "REVISE": 23, "CONTEXT": 12, "REJECT": 5, "GLOBAL_CONTEXT": 1}

Siete emisores en el histórico de90d; DF aporta14 registros, Bupa1 y RedSalud1. No hay señales recuperadas bajo FONASA, ISP, DEIS, Pulso ni emisores mutuales en ese histórico. Las sanciones sí incluyen mutuales/prestadores como actores afectados: eso no constituye diversidad de emisores. La ausencia en stock no prueba ausencia de publicaciones originales.

- Diario Oficial: 80 registros. Hay títulos de sumarios mezclados y PDF decodificado como texto. HOLD salvo tareas REVISE identificadas; no descartar por poca materialidad lo que no pudo leerse.
- Cadena TEA: IF11156 e IF11168 comparten resumen; verificar acto/PDF antes de fusionar. IP4972 contiene texto que identifica IP6640.
- APS: MINSAL omite cifras que aparecen en decreto del stock; el registro vecino mezcla título APS y contenido ISP sobre anticoagulantes. Resolver identidad primero.
- Licencias: consolidar antecedentes, caída de emisiones y estimación de gasto sin atribución causal automática. Mantener Plan Enlace como mecanismo separado.
- Isapres: actualizar pulso con nueva serie regional de agosto. No confundir cotizantes con beneficiarios ni comparar meses distintos para contradecir DF.
- Inversiones: combinar mapa territorial de Bupa/Andes/RedSalud/Sudmédica; separar anuncio, apertura, capacidad y producción, sin sumar CLP con USD.
- Sanciones: conservar resoluciones, conducta, emisión y publicación; UF/UTM separadas. Un pulso no demuestra una tendencia con captura parcial.
- COMPIN: la fuente contiene cifras y medidas omitidas por el resumen. Se solicita enriquecimiento, no clasificación prematura como anuncio vacío.

## Ranking y selección

1. UC CHRISTUS San Carlos: **89.8** — seleccionado tras evidencia nueva de Work3.
2. Cenabast/Ahumada: **85,9** — candidato fuerte, conservado como alternativa.
3. COMPIN/discapacidad: **82,7** — alternativa estratégica actual.

Se conservaron once propuestas con puntuación y causas de exclusión. La recuperación tardía de DF cambió el ganador antes de publicar: confirma suspensión por semanas y traslado de pacientes, con decisiones inmediatas para continuidad de red. No se certifica con esto la reparación del collector ni la cola: el evento sólo se publica en el Insight revisado, con trazabilidad a la auditoría y páginas originales.

La noticia del presupuesto2027 reexplica anuncio1-oct; créditos9-oct deriva de norma2-oct; estudio educativo está catalogado septiembre sin día verificado. No rejuvenecerlos por difusión.

La auditoría Work3 además obliga a revisar Bupa: La Dehesa y Huinganal ya estaban ejecutados según original, Mindplace futuro. El dictamen final de esa fila pasa de PASS provisional a REVISE. No se modificó el artículo sin resolver esa evidencia con el equipo reparador.

## Freshness gate

Siete fechas calendario en America/Santiago, edad0–6. La fecha de generación, captura o republicación no reinicia vigencia. Se exige ancla del cambio sustantivo y aprobación editorial de negocio. La ausencia de candidato o de revisión suficiente mantiene el módulo vacío. El Insight14-sep se conserva en archivo y su señal original no se borra.

La nueva pieza tiene ancla10-oct (anuncio de suspensión por semanas/traslados concluidos) y vence al comenzar **17-oct en Chile**, salvo reemplazo por evidencia superior. El aluvión ocurrió8-oct. DF y La Tercera recogen el mismo comunicado y UC CHRISTUS confirma el estado operativo: no se cuentan como tres evidencias independientes de daño. No se inventan pacientes, camas, pérdidas ni fecha de reapertura. Trazabilidad del análisis real: sesión Work2; no ejecución TERRA ni segundo revisor fingido.

Se corrige selección, construcción FREE y presentación. Un JSON válido o un resumen con key_points deja de bastar como PASS editorial. El modelo puede producir borrador, pero necesita revisión explícita antes de sustituir la pieza aprobada. La ficha muestra cifras, actores, decisiones, seguimiento, límites y fuentes.

## Prioridades para equipos reparadores

P0 identidad/extracción DO e IP4972; P0 recuperar contenidos/fechas de fuentes críticas y analizar nuevas señales; P1 series agosto y capacidad territorial; P1 reemplazar resúmenes genéricos por evidencia completa. No reducir umbrales para compensar falta de diversidad. Mantener issue5 abierta; QA técnico y Reviewer adicional no se presumen.

## Segundo control de entradas antes de cerrar

El suplemento Work3 `ce3c624` añadió siete originales: DF Ricarte Soto y bonos; Andes/MetLife; INDISA/Esencial; ACHS; RedSalud50 cirugías; Pulso residencias. Todos se abrieron y revisaron. La matriz conserva límites por fila y el ranking agrega tres propuestas actuales. Top3 elegible sin cambios. Ricarte Soto requiere contrastar presupuesto; Pulso exige resolver novedad sustantiva y denominadores; RedSalud necesita resultados y período para sostener una tesis superior. Las alianzas y ACHS enriquecen contexto de90 días sin rejuvenecer septiembre/agosto. No se declaran recuperados por el pipeline sólo por haber sido verificados editorialmente.

Se preserva la revisión independiente concurrente de la cola y sus enlaces a issues6–9. El suplemento confirma que telemetría pública y runtime no coinciden; esa reparación y la validación integral de cobertura siguen abiertas.
