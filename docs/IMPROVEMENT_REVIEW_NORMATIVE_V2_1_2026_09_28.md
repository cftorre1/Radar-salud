# Improvement Review — Normative Editorial V2.1
Fecha: 2026-09-28
Candidato revisado: `677702acda24c1a97ef114cb37b3f7fc835a5142`
Ámbito: backlog aprobado `normative_editorial_v2_2026_09_27`, staging únicamente.

## Resultado

**PASS para staging.** Los doce actos visibles tienen identidad del documento en el titular, materia comprensible y decisión/cambio explícito. En resoluciones, el titular separa el acto que decide, la norma afectada y el efecto de la resolución sobre esa norma. “Contexto de la señal” agrega vigencia, alcance o antecedente y no es necesario para identificar el acto.

La revisión legal editorial contrastó los doce casos con publicaciones de la Superintendencia de Salud, incluyendo sus fichas de [resoluciones](https://www.superdesalud.gob.cl/normativa/resoluciones/) y [circulares](https://www.superdesalud.gob.cl/normativa/circulares/). El Reviewer automatizado valida persistencia y estructura; no sustituye la confirmación jurídica humana.

## Antes / después del stock visible

| Acto | Titular previo | Titular V2.1 persistido | Fuente oficial |
|---|---|---|---|
| IF/N°11156 | Resolución Exenta IF/N°11156 sobre Circular IF/Nº528: Isapres: cobertura TEA sin tope anual y nuevo registro obligatorio · IF/N°11156 | Resolución Exenta IF/N°11156 · TEA: acoge parcialmente recursos contra Circular IF/N°528; mantiene cobertura sin tope anual y prohíbe exigir RND | https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n11156/ |
| IF/N°535 | Circular IF/N°535 · Isapres no podrán compensar reembolsos a empleadores públicos sin habilitación legal | Circular IF/N°535 · Reembolsos a empleadores públicos: prohíbe a las isapres compensarlos con otras deudas, salvo habilitación legal | https://www.superdesalud.gob.cl/normativa/circular-if-n535/ |
| IF/N°534 | Circular IF/N°534 · Isapres deberán emitir bonos con cédula cuando falle la validación biométrica | Circular IF/N°534 · Bonos electrónicos: si fallan biometría y validación auxiliar, las isapres deben aceptar la cédula | https://www.superdesalud.gob.cl/normativa/circular-if-n534/ |
| IF/N°10670 | Resolución Exenta IF/N°10670 sobre Circular IF/N°531: Las isapres recurrentes deben operar bajo la Circular IF/N°531 mientras se | Resolución Exenta IF/N°10670 · Metas EMP: rechaza recursos contra Circular IF/N°531, por lo que sigue vigente el cambio de junio a octubre en el informe parcial | https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n10670/ |
| IF/N°10615 | Resolución Exenta IF/N°10615 sobre Oficio Ord. IF/N°27.377: Isapre Nueva Masvida debe ajustar la documentación, nomenclatura y cálculo | Resolución Exenta IF/N°10615 · Plan MAS2026: acoge parcialmente el recurso contra Oficio IF/N°27.377; Nueva Masvida ajusta aporte, siniestralidad y mandato | https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n10615/ |
| IF/N°533 | Circular IF/N°533 sobre adecuar su reporte mensual del inventario utilizado para la devolución y pago de SIL del sector público y | Circular IF/N°533 · SIL: actualiza el inventario mensual con nuevos campos, formatos y validaciones | https://www.superdesalud.gob.cl/normativa/circular-if-n533/ |
| IF/N°9994 | Resolución Exenta IF/N°9994 sobre Circular IF/N°532: La Circular IF/N° 532 mantiene su ejecución pese a las impugnaciones | Resolución Exenta IF/N°9994 · Afiliación electrónica: rechaza suspender Circular IF/N°532; sus reglas entran en vigor en enero de 2027 | https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n9994/ |
| IF/N°532 | Circular IF/N°532 sobre las nuevas exigencias aumentan el nivel de evidencia verificable sobre la identidad, el consentimiento y | Circular IF/N°532 · Afiliación electrónica: refuerza controles de identidad, consentimiento y trazabilidad desde enero de 2027 | https://www.superdesalud.gob.cl/normativa/circular-if-n532/ |
| IF/N°531 | Circular IF/N°531 sobre el cambio modifica el momento y el período de referencia de la información con que se comunica el avance | Circular IF/N°531 · Metas EMP: traslada a octubre el informe de avance parcial sobre enero-octubre | https://www.superdesalud.gob.cl/normativa/circular-if-n531/ |
| IF/N°8760 | Resolución Exenta IF/N°8760 sobre Circular IF/N°529: Durante la suspensión, las instrucciones de la Circular IF/N°529 no producen | Resolución Exenta IF/N°8760 · CAEC: suspende Circular IF/N°529; pausa reglas de derivación urgente hasta resolver los recursos | https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n8760/ |
| IF/N°530 | Circular IF/N°530 sobre estandariza el canal y la oportunidad de entrega de información sobre profesionales que autorizan | Circular IF/N°530 · Contralores médicos: exige informar cambios cada mes, dentro de los primeros cinco días hábiles | https://www.superdesalud.gob.cl/normativa/circular-if-n530/ |
| IF/N°529 | Circular IF/N°529 sobre la modificación vincula el incumplimiento del plazo de derivación con el otorgamiento de la cobertura | Circular IF/N°529 · CAEC en urgencias: vincula la derivación tardía con la cobertura en el prestador que atendió | https://www.superdesalud.gob.cl/normativa/circular-if-n529/ |

## Revisión de calidad

| Dimensión | Evaluación |
|---|---|
| Coherencia estratégica | La jerarquía comunica inteligencia regulatoria: primero el acto jurídico, enseguida el asunto y la consecuencia operacional. |
| Claridad editorial | Títulos leíbles para equipos de salud/seguros. En IF/N°10670, 10615, 9994, 8760 y 11156 quedan separados decisión, acto recurrido y efecto; se acepta mayor longitud en móvil para conservar precisión. |
| Densidad informativa | El título lleva identidad + materia + acción. El contexto añade fecha de vigencia, excepción, alcance o procedimiento; no duplica el título. |
| Integridad de datos | La exportación final conserva `display_title`, subtítulo/identidad legal y `normative_context` para las 12 URLs. El gate y el Reviewer usan identidad estable y comprueban sujeto/acción y relaciones de resolución. |
| UX responsive | Browser desktop/mobile: 46/46 casos aprobados, incluido el corpus V2.1 y navegación a contexto. Fechas sin hora se comparan como días calendario y la prueba fija el reloj completo a las 23:59 UTC. |
| Mantenibilidad | V2.1 vive en `config/normative_editorial_v2.json`, persiste en snapshot final y lo auditan gate, tests Python/Node, browser QA y Reviewer. La fuente canónica de recencia está en `app.js`; el asset web se genera desde ella. |
| Regresión / incertidumbre | Dos intentos de recuperación mostraron el límite de 14 días y una expresión regular mal escapada. Se corrigieron y comprobaron sobre el SHA final; no se promocionó main/producción. El Reviewer determinístico no sustituye el juicio legal. |

## QA y revisión independiente

- Python: **237 passed**.
- Node: **39 passed**.
- Playwright: **46 passed** en Chromium desktop y mobile, incluidos 12 titulares V2.1 y fecha calendario.
- Reviewer: **PASS**, `findings: []`; checks de datos, editorial y UX.
- Preview staging: **PASS**; rollback omitido porque no hubo fallo en el candidato final.
- Evidencia: [GitHub Actions #602](https://github.com/cftorre1/Radar-salud/actions/runs/36421011711), SHA `677702acda24c1a97ef114cb37b3f7fc835a5142`; evidencia browser y Reviewer adjunta a la ejecución.

## Aprendizaje y controles

- Persistir la transformación editorial en el snapshot final y comprobar el snapshot, no solo un estado transitorio del pipeline.
- Identidad de acto en titular: contrato semántico documento + materia + acción; no imponer límite rígido de longitud.
- Para `YYYY-MM-DD`, aplicar ventana de días calendario y probar con reloj fijo, congelando constructor `Date` y `Date.now()`.
- Editar `app.js`, fuente canónica; validar el asset generado y el resultado móvil/desktop.
- Deduplicar Insight semanal y señal base solo si ambas corresponden al mismo acto y están dentro del período.

## Decisión

Marcar V2.1 como validado en staging y continuar con la siguiente tarea crítica aprobada: `signal_simplification_statistics_v2_2026_09_27`. Sin cambios en `main` ni producción.
