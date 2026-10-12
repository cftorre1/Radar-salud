# WORK 6 — Auditoría independiente de producto y contenido
Fecha: 12 de octubre de 2026. Repositorio: cftorre1/Radar-salud.

**DICTAMEN: REVISE. Devolver a Work 5 antes de autorizar Codex H.**

Candidato auditado: PR #32, SHA **4bb075eda97413d0c4423848c2ad8f7d8f0ceb91**.
Referencia staging comprobada al cierre: **ef8cbe3938623d493872ff5f3e717153f176d1be**.
PR abierto, sin fusionar. Auditoría documental, de originales, código existente y preview; no certificación de una implementación futura.

## 1. Resumen ejecutivo independiente

El contrato mejora sustancialmente navegación, lectura persistente, trazabilidad y profundidad editorial. Sus secciones finales V2 y E1–E7 prevalecen sobre propuestas anteriores. No corresponde reabrir como bloqueos resueltos la identidad semanal, los tombstones de lectura o la separación entre hecho e interpretación: están especificados, aunque aún no implementados.

Sin embargo, **E4 prescribe una variación porcentual general cuya única excepción es base cero**. FEFI contiene resultados negativos: aplicar literalmente esa fórmula a una pérdida que pasa a utilidad da una variación negativa de cinco dígitos. Es un contraejemplo real al supuesto de generalización desde Pulso. No basta confiar en que un revisor detectará el error después: el dominio permitido de cada cálculo debe ser determinístico y explícito. Hay un P1 del diseño propuesto; no detecté P0 en el alcance examinado.

La lectura independiente de FEFI encontró además una contradicción entre notas y cifras de Esencial. No autoriza una nueva ficha financiera ni un ranking: demuestra por qué deben conservarse los HOLD y verificarse notas, no sólo sumas. Es evidencia externa conflictiva, no un segundo defecto demostrado del contrato, que ya exige revisar notas.

La limpieza de Global es pertinente si conserva conflictos entre fuentes, metodología, límites y atribución. Retirar rótulos repetitivos no autoriza suprimir esa información. Los formatos normativos validados deben mantenerse. La reducción de llamadas/roles IA propuesta es razonable; no se ejecutaron llamadas pagadas del pipeline.

## 2. Método y separación de estados

Se leyeron PR #32, diff y conversación; handoff, Reviewer y manifiesto Work 5; issue #5 y decisiones recientes; reglas editoriales vigentes, comité, prompts/gates, frontend y datos de las cuatro familias. Los hashes del handoff y Reviewer coinciden con el manifiesto: respectivamente 9ba5c848d8aa4416b38e5ab07d29a2c8610eb6c6fdd727c8e5858fcd6cc4870f y 02ceee1dc247cd7d0f97af9e23e627ce18fb837ecf8eff736146d1adbc1b5a33. No se confunde el PASS_SCOPED del Reviewer con este dictamen.

PR #32 cambia solamente tres documentos Work 5. **IndexedDB v3, el nuevo detalle canónico, statistical_view, receipts semánticos y el catálogo público depurado son propuestas.** No existen por el hecho de describirse en el PR.

Se inspeccionó el preview https://alicantosalud.cl/staging/ y Global. El run de referencia [38208484632](https://github.com/cftorre1/Radar-salud/actions/runs/38208484632) muestra jobs de tests, staging, Reviewer y preview exitosos. Esto es evidencia histórica del pipeline, no ejecución nueva de esas suites por Work 6. El build incluye recuración/exportación: el contenido servido no se presume idéntico byte a byte al JSON del commit; la UI mostraba actualización 12-oct 03:05.

Se ejecutaron cálculos focales sobre cuatro archivos oficiales descargados, lectura de originales normativos/noticiosos y una reproducción aislada de pérdida de lectura usando las funciones reales del frontend. No hubo backfill, auditoría de fuentes de 90 días, suites grandes, recuración, publicación ni modificación funcional.

## 3. Hallazgos del contrato propuesto

### W6-01 — P1 — Dominio de variación porcentual incompleto; bloquea autorización

**Evidencia reproducible.** Handoff E4, derived_metrics: Δ%=100×(end−start)/start y excepción start0→N/A. E5 prueba cero, pero no bases negativas ni cruces de signo. En el XLS oficial FEFI v2, hoja `Result. Financieros comparados`, B16=-273,285 y D16=34.090,653, millones de pesos, enero–marzo 2025 y 2026. F16=34.363,938. Aplicación literal: **−12.574,395960261229%**. Es cálculo de auditoría sobre celdas, no indicador aprobado para publicación. El conflicto de notas descrito más abajo impide elevar ese conjunto a ficha validada; el contraejemplo matemático conserva su validez.

**Causa probable.** Regla derivada de stocks positivos de Pulso extendida a magnitudes financieras con signo. Identificar stock/flow/rate no define por sí solo el dominio de una fórmula.

**Riesgo.** Presentar recuperación como caída, ordenar entidades por un porcentaje sin interpretación económica o dejar que un modelo “corrija” signos arbitrariamente.

**Corrección precisa.** Añadir dominio y política de comparación por métrica/fórmula registrada. Para variación porcentual ordinaria, exigir base estrictamente positiva y una magnitud con interpretación proporcional aprobada. Si base≤0, o si un resultado financiero cruza entre pérdida y utilidad, mostrar cambio absoluto y transición pérdida/utilidad, con motivo explícito de N/A. No sustituir silenciosamente la base por su valor absoluto. Una fórmula financiera alternativa requiere nombre, definición y aprobación específica. Diferenciar signo numérico de favorable/desfavorable; un aumento de gasto no es automáticamente favorable.

**Aceptación objetiva.** Fixtures determinísticos: pérdida→utilidad, pérdida→pérdida menor, pérdida→pérdida mayor, cero→positivo, positivo→cero, positivo→negativo y stock positivo ordinario. Para B16/D16 debe producir cambio absoluto +34.363,938 millones y porcentaje no aplicable, nunca “caída de 12.574%”. Las tres variantes con base negativa y cero→positivo deben devolver N/A porcentual; positivo→cero admite −100% si la métrica permite comparación proporcional; positivo→negativo financiero devuelve N/A y transición a pérdida. Para Pulso debe conservar −26.541 y −1,055711966…%. Ningún modelo calcula o decide la validez aritmética. Actualizar E4, E5 y prompt final, y recibir revisión focal antes de Dirección.

### W6-02 — P2 — Precisión y reconciliación necesitan tolerancia explícita

**Evidencia.** FEFI contiene decimales y lecturas binarias como −273.28500000000076; E4 exige sumas verificadas y valores crudos, pero no define precisión/tolerancia por unidad. Pulso cuenta personas enteras y no revela este problema.

**Causa/riesgo.** Extrapolar igualdad exacta de conteos a cifras monetarias puede producir HOLD falso; una tolerancia improvisada puede ocultar diferencias reales.

**Corrección.** Definir precisión de origen, unidad de cálculo y tolerancia de reconciliación registrada. Decimal/normalización controlada para magnitudes monetarias; exactitud entera para personas. Nunca repartir residuos ni tolerar contradicciones de notas.

**Aceptación.** Error de representación binaria no bloquea una suma válida; diferencia superior a la tolerancia documentada sí; una unidad faltante en conteos falla. Registrar residual observado y umbral. No altera el P1 ni habilita FEFI.

### W6-03 — P2 — Aclarar fixtures mínimos al diferir H4

**Evidencia.** E6 difiere dos horas de overlays históricos H4 para H-Datos y preserva H7. Es defendible, pero “H4 diferido” puede interpretarse como diferir también muestras de regresión necesarias para el nuevo renderer/gate.

**Causa/riesgo.** Confusión entre curación del stock y pruebas de compatibilidad; una ficha normativa o legacy válida podría desaparecer.

**Corrección.** Explicitar que se difiere producción de overlays históricos, no los fixtures mínimos de normativa, noticias, Global HOLD, datos y detalle legacy limitado. Mantener los mismos topes; si no cabe, informar bloqueo sin declarar DONE.

**Aceptación.** H7 contiene esas cinco rutas y fallos de carga, verificadas sobre el SHA de implementación. Ningún fixture obliga a publicar ni regenerar datos.

### W6-04 — P2 — Ampliar fixture sancionatorio a decisiones mixtas y sustituciones

**Evidencia.** IF/N°7312 sanciona ISALUD con 400 UF y absuelve el segundo cargo; IF/N°11076 sustituye una multa previa por cancelación del registro del agente. No toda decisión es sanción acumulable.

**Causa/riesgo.** Una extracción centrada en “sanción+importe” puede omitir absolución o sumar multa sustituida y cancelación; el nombre de una isapre destinataria puede confundirse con sujeto sancionado.

**Corrección.** Incorporar esos dos controles al fixture normativo existente: actor, acto previo, relación sustituye, decisión por cargo y estado procedimental separados.

**Aceptación.** No sumar decisiones sustituidas; no atribuir la cancelación a Banmédica por figurar como destinataria; conservar absolución de ISALUD. Emisión del acto gobierna frescura, no fecha de fiscalización ni carga del PDF.

## 4. Defectos actuales: confirmados, pero ya abordados por Work 5

| ID / severidad | Evidencia y causa probable | Riesgo | Corrección prevista y aceptación |
|---|---|---|---|
| ACT-01 / P1 | Dos pestañas abiertas: marcar tema IA como leído en Global cambia 9→8 pendientes allí; Home conserva su acción “Marcar como leído”. app.js persistRead y global.js saveRead escriben el Set completo cargado al inicio. Harness con ambas funciones reproduce pérdida de una lectura al guardar otra pestaña. | Lecturas perdidas y reaparición de pendientes. | Store por pieza, transacción, tombstone y notificación definidos por V2. Probar cambios distintos simultáneos, mismo id en ambos órdenes, no leído persistente, migración, recarga y pageshow. Es deuda de implementación, no prueba de que V2 falla. |
| ACT-02 / P1 | Abrir Félix desde Ponte lleva a tarjeta y reduce pendientes antes de una profundización útil; abrir Ver resumen de Pulso muestra dialog sin marcarlo leído. | Misma intención produce estados diferentes; “leído” no equivale a haber visto detalle. | Un destino canónico y lectura tras render satisfactorio; fallo no altera estado, no leído revierte, foco vuelve al origen. V2 lo especifica. |
| ACT-03 / P1 | Detalle Pulso repite cartera/contratos/movilidad en tabla, hallazgos, fórmulas e implicancias; aún incluye “base de ingresos”. Global IA usa título causal fuerte con metodología no verificada. Gates actuales puntúan longitud y exigen what/why; comité devuelve PASS estructural sin demostrar delta semántico. | Confundir volumen con profundidad y asociación con causalidad. | Claims verificables, delta por bloque, revisión independiente y HOLD; v3/E3 lo cubren. La corrección visual sola no cierra el defecto. |
| ACT-04 / P2 | Fuentes presenta ISP/FONASA con error y Reuters pausada bajo “Fuentes que alimentan Alicanto”, junto con fechas técnicas. | Expectativa de cobertura que no existe. | Allowlist pública de fuentes activas verificadas y diagnóstico separado; ninguna bloqueada/desconocida/pausada aparece como operativa. Decisión de Dirección ya incorporada. |
| ACT-05 / P2 | “+” alejado visualmente del texto de filtro; Volver arriba aparece inline en fichas, no como control flotante global. | Interacción menos descubrible y regreso inconsistente. | Agrupar texto/+, estado expandido y teclado; control flotante sin tapar contenido ni foco, comportamiento coherente en ambas superficies. Pruebas responsive futuras obligatorias. |

## 5. Cobertura editorial independiente

### A. Normativa y fiscalización

- **Circular IF/N°534:** original de cuatro páginas y detalle staging contrastados. Conservar identidad, contingencia tras falla biométrica y auxiliar, regularización posterior, deberes de registro/protocolo y vigencia 1-dic-2026. No reducirla a un proveedor tecnológico. Su presencia en ventana de 30 días no implica que deba aparecer en 14 días.
- **Resolución IF/N°10670:** original de ocho páginas. Rechaza reposiciones de cinco isapres; rechazo de suspensión sólo para Esencial/Consalud; remite recursos jerárquicos. No es cierre definitivo de toda controversia. Conservar argumentos atribuidos y fundamentos del órgano sin inventar una argumentación individual para Esencial. IF/N°531 exige distinguir completar el décimo mes de afirmar una emisión durante octubre.
- **Prestadores, IP/N°7462:** lectura focal de decisión original confirma 400 UTM a Clínica Sanatorio Alemán; no inferir firmeza ni difundir datos de pacientes. El caso de fiscalización previo no debe reemplazar emisión como fecha de señal.
- **Isapres, IF/N°7312:** original confirma ISALUD, 400 UF, absolución parcial y recursos posibles. Se utilizó como control histórico negativo de fechas, no como novedad de octubre ni como inicio de auditoría de 90 días.
- **Agentes, IF/N°11076:** original confirma acto del 22-sep, multa previa y sustitución por cancelación ante falta de pago. Separar fechas de emisión, notificación, plazo y verificación. No confundir sujeto con entidad notificada.

Conclusión: arquitectura normativa propuesta suficiente con W6-04 como mejora P2. No sustituir formatos jurídicos por la ficha genérica de noticias.

### B. Noticias

- **Félix Bulnes:** la comunicación oficial del Hospital Barros Luco confirma el hecho quirúrgico y participación de su especialista. El original MINSAL no fue recuperable en esta sesión; no certifico independientemente fecha operatoria, plataforma ni todos los detalles adicionales que Work 5 obtuvo. El frontend existente muestra repetición y contexto genérico. Retener sólo afirmaciones enlazadas a original recuperado/receipt existente, sin completar secciones vacías.
- **Presupuesto 2027:** lectura de Pulso confirma bases distintas para 1,5%, 2,7% y 3,5%; no son tres crecimientos sanitarios comparables. El 4,7% sectorial exige su propia base y atribución. Propuesta presupuestaria no equivale a ejecución. La corrección Work 5 aporta información real.
- **San Carlos de Apoquindo:** La Tercera describe término del traslado; página oficial UC CHRISTUS informa cierres/servicios y continuidad de otras instalaciones. Es fuente dinámica, observada el 12-oct, sin inventar fecha editorial ni reapertura. Separar hecho de recomendación operativa; no deducir saturación de la red.

Conclusión: eliminar repetición mejora la ficha sólo si el detalle agrega datos, contexto o límites comprobados. No exigir implicancias universales.

### C. Global Intelligence

Se revisó feed y UI con diez temas, contrato, caso IA-codificación y réplica primaria AHA. Suprimir bloques interpretativos obligatorios evita prosa genérica; deben sobrevivir el desacuerdo entre actores, universo, período, metodología disponible y sus límites. La AHA es parte interesada, no verificador neutral.

No se recuperó el original técnico BCBSA y no se verificó el método subyacente; Reuters conserva restricción. **HOLD_SOURCE_METHOD permanece**. La crítica AHA no valida ni invalida por sí sola una estimación causal. No convertir la síntesis propuesta en aprobación de publicación ni conservar titular causal por inercia. No se certifican independientemente todos los temas ni se activa fuente alguna.

### D. Estadísticas e inteligencia de negocios

**Pulso, positivos reproducidos en XLSX originales:** julio 2.487.497 beneficiarios = 1.549.873 cotizantes + 937.624 cargas. Diez entidades reconcilian con el total; enero 2.514.038 y delta −26.541, −1,055711966…%. Los siete cortes muestran seis bajas consecutivas. Julio contratos 19.716−15.172=4.544 eventos, no nuevos beneficiarios. Movilidad entre julio 2025 y julio 2026: 91.963−109.663=−17.700, no cambio mensual. Archivos y celdas en manifiesto adjunto.

KPI, serie y tabla de entidades tienen utilidad distinta si no reiteran una narrativa idéntica. Cotizantes/cargas no prueban ingresos; la contribución aritmética de cargas no es causa. La alternativa accesible de un gráfico no cuenta como redundancia vacía.

**FEFI, segunda familia oficial:** landing de marzo 2026 y XLS v2 examinados con xlrd, metodología IFRS, notas, comparativos y resultados institucionales. Se encontró el contraejemplo con signo W6-01. También `Notas Explicativas!A18` declara ausencia de información de Esencial por revisión, mientras `E. Resultados comparado por Isa!A13:B13,Q13:R13` contiene código108 y resultados −1.488,57/−29,705. Se necesita aclaración/versionado oficial antes de aprobar cobertura institucional completa o agregado que dependa de esa inclusión. No resolver usando una nota de prensa, cero, exclusión silenciosa o estimación.

FEFI puede requerir tabla comparativa/puente entre dos períodos y cambios absolutos; dos cortes no justifican línea mensual. Ratios de liquidez en veces, proporciones almacenadas como fracciones y montos no comparten escala. Esto refuta que la receta Pulso sea universal. No se crea un producto FEFI ni se acredita comparabilidad integral.

**Respiratorio:** se inspeccionó fixture existente con inconsistencia 53,7/56,7; no se releyó su PDF. Es prueba negativa heredada, no validación independiente de epidemiología. HOLD del indicador y ausencia de gráfico inventado siguen siendo la respuesta correcta.

## 6. UX desktop/mobile y accesibilidad

Desktop observado a 1348×927: Home, Ponte, filtros, Radar, fichas IF534/Pulso, Global, acciones de lectura y Fuentes. Filtro se expande; cambiar 30→60 días permite ver Pulso; se restauró 30 días. Se restauraron los cambios de lectura de prueba: Home 69 tarjetas/67 pendientes; Global 10 temas/9 pendientes. Se confirmó la diferencia entre título/entrada Ponte y botón Ver resumen. El botón llamado “Más info” en la solicitud corresponde aquí a “Ver resumen”; no se presume que todos los títulos abran detalle.

Fuentes es hoy un diálogo, no una página pública nueva implementada. Navegación principal Home→Global existe. El diseño deberá conservar retorno, filtros, anchors, fuentes originales, compartir y acceso al contenido leído; quitar una tarjeta de pendientes no debe eliminarla del feed. La identidad semanal no debe depender del enlace compartido.

Mobile: inspección estática de media queries, expansión de lista y controles; hay alturas y overflow oculto con regla de expansión, por lo que no se declara pérdida inevitable de contenido sólo por leer CSS. **No se ejecutó viewport 390×844/320 ni zoom200%, lector de pantalla o medición de contraste en esta sesión.** No se hereda un PASS visual de los 68 tests históricos. La herramienta de navegador disponible no expuso ajuste de viewport; se aplica stop-loss y se mantiene el gate de pruebas de implementación.

E5 establece criterios adecuados: nombres completos, orden numérico, tabla semántica, alternativa accesible, foco, targets44px y contraste. Verificar además foco al desaparecer pendientes, Escape/cierre del diálogo, no duplicar lectura accesible de gráfico+tabla, y botón flotante sin obstrucción. No aprobar responsive mediante screenshots desktop.

## 7. Arquitectura editorial e IA

Código existente: `llm_analysis.py` requiere what_happened/why_it_matters; `editorial_gate.py` usa también longitud; `editorial_committee.py` asigna panel y verdict estructural. Eso no equivale a un comité independiente que haya contrastado originales. Los nombres de roles no acreditan llamadas ni deliberación.

v3 propone claims, localizadores, hashes, versiones y receipt de revisión semántica independiente. Es implementable y mejor que contar párrafos. Aceptación: una paráfrasis no agrega profundidad; una nueva fecha/sujeto/limitación sí sólo con evidencia. Conservar negaciones y operadores jurídicos. Un cambio de fuente o contenido invalida el receipt asociado; no reusar PASS de otra versión.

Selección por mérito y bloques opcionales son decisiones correctas: cero hallazgos es resultado válido. Ninguna cuota de roles, gráficos o secciones debe producir texto de relleno. IA puede ayudar con síntesis y objeciones; cálculos, fechas extraíbles, referencias y hashes requieren verificación determinística.

Terra/Astra deben seguir condicionados a disponibilidad real, benchmark controlado, beneficio medido y autorización de coste; no se da por probado un modelo por su nombre configurado. Preservar editor principal, especialista selectivo y revisión focal con tope de reparación. No crear ocho revisores permanentes ni gastar para sumar celdas. Cero llamadas pagadas del pipeline en esta auditoría.

## 8. Backlog corregido y decisiones pendientes

| Orden | Responsable | Entrega / salida |
|---|---|---|
| Antes de H | Work 5 | Cerrar W6-01 en E4/E5/prompt y aportar fixtures/resultados del dominio numérico. Puede añadir W6-02 a la misma revisión. |
| Revisión focal | Work 6 / revisor independiente | Verificar exclusivamente delta y contraejemplos; no repetir auditoría histórica ni suites grandes. Dictamen nuevo ligado al SHA revisado. |
| Autorización | Dirección | Aceptar contrato corregido y alcance/timeboxes; sólo después puede comenzar Codex H. Este informe no sustituye esa aceptación. |
| H1/H2/H3 | Builder futuro | Detalle canónico, store transaccional y contrato editorial; preservar compatibilidad legacy, tombstones y evidencia. |
| H-Datos | Builder futuro | Mantener tope3h y total20h, incorporando W6-01, precisión y HOLD. Si excede, declarar bloqueo; no sacrificar accesibilidad ni ampliar horas tácitamente. |
| H5/H6/H7 | Builder futuro | Preservación normativa, catálogo permitido y regresiones focales incluidas W6-03/W6-04, desktop/mobile/a11y sobre SHA implementado. |
| Posterior | Dirección | Overlays históricos H4, nuevas fuentes o FEFI publicable sólo con priorización y evidencia; no habilitados por esta auditoría. |

Pendientes editoriales concretos: política de porcentajes financieros; aclaración oficial sobre cobertura FEFI/Esencial; metodología primaria BCBSA y restricciones Reuters; evidencia recuperable de los detalles MINSAL no revalidados. No se pide a Dirección resolver aritmética: Work 5 debe entregar la regla correcta. Las decisiones previas de emisión sancionatoria, catálogo público y preservación normativa no necesitan reabrirse.

## 9. Evidencia, límites y reproducción

Manifiesto compañero: `WORK6_PRODUCT_AUDIT_EVIDENCE_2026_10_12.json`. Incluye URLs, hashes de originales, celdas, resultados y límites. Para reproducir, descargar exactamente esas versiones, verificar SHA256, leer valores numéricos con openpyxl(data_only=True)/xlrd y aplicar fórmulas indicadas. No usar una landing de otro mes para atribuir publicación.

Fuentes primarias y noticias revisadas:
- [IF534](https://www.superdesalud.gob.cl/app/uploads/2026/09/circular-if-n-534-2026.pdf), [IF10670](https://www.superdesalud.gob.cl/app/uploads/2026/09/res-exenta-if-n10670-2026.pdf), [IF531](https://www.superdesalud.gob.cl/app/uploads/2026/08/circular-if-n-531-2026.pdf).
- [IP7462](https://www.superdesalud.gob.cl/app/uploads/2026/09/res-exenta-ip-n-7462-clinica-sanatorio-aleman-pas-n-5008485-2023_0001.pdf), [IF7312](https://www.superdesalud.gob.cl/app/uploads/2026/07/res-exenta-if-7312-i-9-2025.pdf), [IF11076](https://www.superdesalud.gob.cl/app/uploads/2026/10/res-exenta-if-11076-a-55-2026_censurado.pdf).
- [Hospital Barros Luco](https://www.hospitalbarrosluco.gob.cl/jefe-de-patologia-mamaria-del-hospital-barros-luco-participa-en-historica-cirugia-robotica-de-cancer-de-mama/), [Presupuesto/Pulso](https://www.latercera.com/pulso/noticia/presupuesto-2027-minuta-politica-del-gobierno-reporta-alza-del-gasto-distinta-de-la-informada/), [San Carlos/La Tercera](https://www.latercera.com/nacional/noticia/clinica-uc-christus-de-san-carlos-de-apoquindo-termina-traslado-de-pacientes-ante-suspension-de-operaciones-por-aluvion/), [UC CHRISTUS](https://www.ucchristus.cl/contingencias).
- [AHA](https://www.aha.org/news/blog/2026-10-05-better-information-better-care-how-coding-supports-todays-complex-patients), [landing FEFI marzo](https://www.superdesalud.gob.cl/biblioteca-digital/estadisticas-financieras-del-sistema-isapre-a-marzo-2026/).

Stop-loss: fallo de acceso al original MINSAL/BCBSA no se convirtió en verificación; no se intentó evadir licencias o barreras. Sin reproducción completa del repositorio ni suites de integración nuevas. Las pruebas aisladas no demuestran comportamiento del futuro store IndexedDB.

## 10. Recomendación de cierre

**REVISE — devolver a Work 5 por W6-01.** Los P2 quedan documentados y no serían por sí solos impedimento para PASS. No autorizar Codex H hasta corrección focal, dictamen actualizado y aceptación explícita de Dirección. No fusionar PR #32; no modificar main, producción, datos publicados ni originales Work 5.
