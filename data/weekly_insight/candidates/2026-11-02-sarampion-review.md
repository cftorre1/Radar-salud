# Insight del lunes 2-nov-2026: sarampión (rezago infantil × brote regional × Presupuesto 2027)

Candidato: `2026-11-02-sarampion.json` (formato A, `anchor_kind: monday`, ancla 2026-11-02, vence 2026-11-09). Publicado en `editorial_approved.json`; el insight anterior (licencias, 23-oct) quedó en `archive/2026-10-23.json`.
Redactor: Claude (corrida programada del domingo 1-nov). Revisión independiente: subagente verificador, PASS_WITH_CORRECTIONS (6 correcciones aplicadas, sección 5).

## 1. Regla del tema y por qué no se usó el candidato "wow" del 27-oct

La regla de Dirección del 28-oct exige que la noticia gatillante sea de los 7 días previos al lunes (`MONDAY_EVIDENCE_DAYS = 7`). El candidato `2026-11-02-wow.json` (cáncer GES) tiene `event_date` 2026-10-21, 12 días antes del ancla, y por eso queda fuera. El borrador de cuidados (`2026-11-02-draft.json`, 23-oct) tampoco cumple.

## 2. Tesis evaluadas (noticias del 26-oct al 1-nov)

| # | Tesis | Noticia gatillante | Cruces | Respaldo | Resultado |
|---|---|---|---|---|---|
| 1 | **Sarampión: 44.386 vacunados y el rezago casi no baja, en el peor año regional; el Presupuesto 2027 recorta el PNI** | Minsal, 28-oct | OPS 1-jul (rezago de julio), OPS informe de situación 22-oct (casos por país), OPS 9-oct (riesgo en eventos masivos), prensa sobre el recorte de 5,3% real al PNI | Alto: 4 fuentes primarias (Minsal y OPS) + 2 de prensa declaradas | **Elegida** |
| 2 | Venta de Empresas Banmédica a Patria: Colombia frena por Aliansalud y el grupo tiene 28% de los beneficiarios de isapres abiertas | DF, 28-oct | Cartera SIS (repo), FNE 15-abr, UnitedHealth | Medio-bajo: DF es de pago (`config/paywalled_press.json`: solo título y bajada); monto, plazo del 19-nov y peso de Aliansalud vienen del cuerpo de DF | Descartada; candidata para cuando haya resolución de Supersalud Colombia |
| 3 | Boletines de la Intendencia de Prestadores (acreditación, reclamos, mediación, RNPI, ene–sep) | Superintendencia de Salud, 29-oct | GES garantía de calidad | Bajo: los PDF no se pudieron leer desde la sesión | Descartada |
| 4 | Ley Sanna: nueva contingencia + permiso para acompañar a NNA hospitalizados por salud mental | Cámara, 27 y 28-oct | Licencias por salud mental (DF 28-oct) | Bajo: proyectos recién ingresados y sin cifras; se cruza con el tema de licencias de la semana anterior | Descartada |
| 5 | Personas mayores: autenticación biométrica + sistema de cuidados | Cámara, 28-oct | Borrador de cuidados del 27-oct | Bajo: el gatillante es menor y las cifras de cuidados son de percepción | Descartada |
| 6 | Licencias por salud mental se desploman | DF, 28-oct | — | — | Repite el tema del insight anterior |

Temas de las últimas 4 semanas: licencias médicas (23-oct), UC Christus (10-oct) y Cenabast (candidato del 7-oct). El sarampión no se repite.

Por qué la 1: cruza el dato operativo de la semana (vacunados frente a rezago) con la situación regional, el riesgo de la gira del Papa (6 al 17-nov, dentro de la vigencia) y la decisión presupuestaria. Además, deja una lectura no obvia: el rezago casi no baja y el grupo sin ninguna dosis no muestra una baja.

## 3. Cifras con su cita (lectura del 1-nov-2026)

Minsal, 28-oct (https://www.minsal.cl/minsal-busco-y-vacuno-a-mas-de-44-mil-ninos-y-ninas-contra-el-sarampion-y-llama-a-vacunar-a-mas-de-140-mil-con-su-esquema-pendiente/)
- 44.386: "permitió inmunizar a 44.386 niños y niñas de hasta 6 años desde julio, quienes tenían solo una dosis o ninguna"
- Más de 140 mil / 62 mil: "Quedan más de 140 mil niños y niñas con su esquema de vacunación incompleto y casi 62 mil de ellos" "vive en la Región Metropolitana."
- 7 de cada 10 / 27% / 6%: "Cerca de 7 de cada 10 son mayores de 3 años a quienes solo les falta la segunda dosis;" "un 27% requiere ambas dosis y un 6% son menores de 3 años sin su primera dosis."
- 22 años (afirmación del Minsal, que atribuye a la OPS): "Según la OPS, el número de contagios en la región de las Américas en 2026 es el peor en 22 años."
- 1993 / 460 / tres: "no haya transmisión comunitaria de sarampión desde 1993"; "este año Chile ha monitoreado 460 casos sospechosos de sarampión"; "se han confirmado solo tres casos importados"
- Gira del Papa: "La OPS también calificó de 'muy alto' el riesgo de contagio en los eventos masivos asociados a la visita del Papa León XIV […] a Argentina, Perú y Uruguay entre el 6 y el 17 de noviembre"

OPS, 1-jul (https://www.paho.org/es/noticias/1-7-2026-chile-sale-busqueda-mas-143-mil-ninas-ninos-con-vacunacion-incompleta-contra)
- "más de 143 mil niños y niñas" con esquema incompleto; "alrededor de 43 mil no han recibido la primera dosis"; "cerca de 100 mil tienen pendiente la segunda dosis"
- "22.324 casos confirmados de sarampión y 38 fallecimientos en las Américas" al 18 de junio

OPS, informe de situación n.º 14, 22-oct (https://www.paho.org/sites/default/files/2026/10/ops-sarampion-sitrep14-es.pdf), SE 1–41 (4-ene a 17-oct)
- 56.753 casos confirmados; 81 muertes; Perú 2.698; Bolivia 120; "un aumento de 4,8 veces" frente al mismo período de 2025

OPS, 9-oct (https://www.paho.org/es/noticias/9-10-2026-ops-evalua-como-muy-alto-riesgo-propagacion-sarampion-ante-proximos-eventos)
- "el riesgo de propagación del sarampión en la región se mantiene muy alto" ante "varios eventos religiosos masivos en América del Sur" (la nota no nombra al Papa; ese vínculo lo hace el Minsal)

Prensa, Presupuesto 2027 (proyecto, no ley)
- Radio U. de Chile, 19-oct: "El presupuesto del Programa Nacional de Inmunizaciones también registra una reducción, de 9.696 millones de pesos." No dice si es real o nominal. Subsecretaria Pizarro: "no le va a faltar vacuna a nadie".
- Diario Estrategia, 20-oct, citando a la Subsecretaría de Salud Pública: "un recorte del 5,3% real, unos 9 mil millones de pesos destinados al Programa Nacional de Inmunizaciones (PNI)". No informa el resultado de la votación.

## 4. Estimaciones (deterministas)

| id | Fórmula | Valor | Uso |
|---|---|---|---|
| crecimiento_casos | 56753 / 22324 | 2,54 | "se multiplicaron por 2,5" (gráfico 2); n4 |
| sin_dosis_pct | 27 + 6 | 33 | insumo |
| sin_dosis | 140 * (27 + 6) / 100 | 46,2 | "unos 46 mil en octubre" frente a "alrededor de 43 mil" en julio; n2 |

Las categorías coinciden: "sin primera dosis" en julio equivale, en octubre, al 27% que "requiere ambas" más el 6% de "menores de 3 sin primera dosis". Con los porcentajes redondeados y 140 mil como mínimo, el rango es de unos 45–48 mil. Por eso el texto dice "no muestran una baja", no "aumentaron".

## 5. Revisión independiente (subagente): PASS_WITH_CORRECTIONS, todas aplicadas

1. n3: se eliminó "aprobado en subcomisión" (la fuente no informa el resultado de la votación) y "nota del Senado" (es una nota de Diario Estrategia que cita a la Subsecretaría).
2. Real o nominal: el 5,3% real ("unos $9 mil millones", según la Subsecretaría) quedó separado de los $9.696 millones de Radio U. de Chile, que no dice si son reales o nominales (ensayo, key_figures y n3).
3. n1: la comparación entre julio y octubre es aproximada, porque ninguna fuente da la fecha de corte ni el rango de edad.
4. Titular y teaser: se cambió "Falta encontrarlos" por "El desafío parece ser encontrarlos", porque es una inferencia.
5. "No disminuyeron" pasó a "no muestran una baja".
6. Riesgo de la gira del Papa: en el ensayo ahora dice "Según el Minsal, la OPS…". En "qué mirar" se cita la evaluación de la OPS sobre eventos religiosos masivos en Sudamérica.
Opcionales aplicados: n4 (subregistro), atribución de "22 años" al Minsal en key_figures, "podría significar" en la lectura y "en 2026" para las muertes.

## 6. Verificación determinista

`verify_candidate` con un paquete de evidencia armado con las citas de arriba (34 cifras y 6 URL permitidas): **PASS**, 0 errores y 0 advertencias. `presentation_a_errors`: `[]`. Titular de 129 caracteres, dek de 30 palabras y ensayo de 250 palabras. `freshness_gate`: no elegible el 1-nov, elegible del 2 al 8-nov y no elegible el 9-nov.

`free_value.json` se regeneró con `scripts/product_report.py` y con `weekly_freshness.chile_today` fijado al 2026-11-02. Si se corre el domingo 1-nov, la regla del lunes (ancla ≤ hoy) oculta el insight, y ningún job de staging regenera `free_value` el lunes. El frontend (`weeklyFresh`) aplica la misma regla, así que el sitio no lo muestra antes del lunes 2-nov. Estado: `published_editorial_reviewed`; `weekly_presentation.errors = []`.

Tests: `tests/test_weekly*.py` y `tests/test_free_value*.py` pasan (67). `node --test tests/web.test.cjs` pasa (78). Los tests usaban `editorial_approved.json` como fixture del insight de licencias (barras pareadas, mes parcial), así que ahora leen `archive/2026-10-23.json`, que es idéntico. Se agregó un test de render para el insight vigente.
