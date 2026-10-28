# Insight del lunes 2-nov-2026: candidato "wow" y revisión

Candidato: `data/weekly_insight/candidates/2026-11-02-wow.json` (formato A, `anchor_kind: monday`, ancla 2026-11-02, vence 2026-11-09).
Redactor: Claude (sesión editorial, 27-oct). Esta revisión es una **autorrevisión escéptica**, no la revisión independiente que exige `POLICY.md` (condición 2). El coordinador o el revisor independiente deben confirmarla antes de reemplazar `editorial_approved.json`.

## 1. Elección de tesis

Ventana de evidencia: 19-oct a 2-nov (regla del lunes: noticia ancla a 14 días o menos del ancla). Noticia ancla del feed de Alicanto: **La Tercera, 21-oct**, estudio CIPS-UDD sobre el costo del cáncer GES (`event_date` 2026-10-21, 12 días antes del ancla).

| # | Tesis candidata | Datos cruzados | Novedad | Decisión | Verificable | Graficable | Resultado |
|---|---|---|---|---|---|---|---|
| 1 | **Cáncer GES: el costo unitario se dispara y 2027 paga más derivar que detectar** | Estudio CIPS-UDD con datos de Fonasa (2018–2024) × proyecto de Presupuesto 2027 (Minsal, 19 y 21 oct) × retrasos GES por cáncer (informe de listas de espera del Minsal, II trimestre 2026) | Alta: la intensidad por paciente casi no cambia (+3,8%) y la relación derivar/detectar (≈ 9,8 veces) no se ha publicado | Alta: Fonasa, hospitales (pago por actividad 58,7% → 81,9%), clínicas privadas (derivaciones), Isapres y laboratorios | Alta: 2 fuentes primarias Minsal + estudio con datos administrativos (vía prensa) | Alta: 2 series honestas desde cero | **Elegida** |
| 2 | Envejecimiento + red de cuidados + Ley 21.822 (borrador `2026-11-02-draft.json`) | Encuesta, Mideso, estudio UC | Media | Media (efecto en 2027–2028) | Baja: todo por prensa; cifras de percepción | Media | Descartada |
| 3 | Genérico de semaglutida + obesidad + mercado farmacéutico | DF 20-oct, La Tercera 22-oct | Alta | Alta para farma | Baja: precio del genérico no publicado ("menos de la mitad"); sin fuente primaria de precios | Baja | Descartada |
| 4 | Cartera Isapre que se reduce + movilidad interisapres | Cartera SIS ene–ago 2026 (repo), La Tercera 17-oct | Media | Media | Media: el estudio del gremio es exploratorio | Alta | Descartada: noticia fuera de la ventana de 14 días y sin hecho nuevo |
| 5 | Presupuesto 2027 "efectivo" (+2,4% según Sugg) + alcaldes + deuda hospitalaria | La Tercera 19-oct | Media | Alta | Baja: La Tercera no se pudo leer (robots), sin cifra primaria de deuda | Media | Absorbida en la tesis 1 solo con cifras primarias |
| 6 | Licencias médicas | SUSESO | — | — | — | — | Tema del insight anterior |

Por qué la 1: es la única que cruza tres fuentes independientes (estudio académico con datos de Fonasa, proyecto oficial de presupuesto, informe oficial trimestral) y produce dos cifras nuevas y deterministas para un ejecutivo: (a) el costo sube por precio unitario, no por más prestaciones por paciente; (b) el proyecto 2027 destina a derivaciones oncológicas adicionales ≈ 9,8 veces lo que asigna a detección precoz de los tres cánceres que más retrasos GES acumulan después del de mama.

## 2. Cifras con su cita (lectura del 27-oct-2026)

Las citas son textuales de la página indicada. Limitación: WebFetch entrega extractos (máximo unos 125 caracteres por cita), no la página completa. La Tercera (21-oct) bloquea la lectura automática (robots). Sus cifras se tomaron del registro del feed de Alicanto y se contrastaron, una a una, con G5noticias (24-oct), que publica el mismo estudio.

### Estudio CIPS-UDD (prensa) — G5noticias, 24-oct
URL: https://g5noticias.cl/2026/10/24/evolucion-del-gasto-ges-cancer-recursos-aumentaron-89-pero-las-prestaciones-crecieron-menos-de-la-mitad-entre-2018-y-2024/

| Cifra usada | Cita |
|---|---|
| $185.472 → $350.778 millones (2018 → 2024) | "el financiamiento GES-Cáncer pasó de $185.472 millones en 2018 a $350.778 millones en 2024" |
| pesos de 2026 | "expresados en pesos constantes de 2026" |
| +89,1% | "Entre 2018 y 2024, Chile incrementó en 89,1% los recursos destinados al financiamiento" |
| presupuesto Minsal +42,3% | "al aumento de 42,3% registrado por el presupuesto ajustado del Ministerio de Salud durante el mismo período." |
| prestaciones +37,7%; personas +32,9% | "el número de prestaciones realizadas aumentó en 37,7%, mientras que las personas atendidas crecieron 32,9%." |
| 1.135.798 → 1.564.084 | "Las prestaciones oncológicas pasaron de 1.135.798 a 1.564.084," |
| 717.432 → 953.422 | "las personas atendidas aumentaron de 717.432 a 953.422." |
| $163.000 → $224.000; ≈ 37% | "pasó de aproximadamente $163.000 en 2018 a $224.000 en 2024," / "lo que representa un incremento cercano al 37%." |
| 1,58 → 1,64 prestaciones por persona | "pasando de 1,58 a 1,64 durante el período analizado." (según el texto, es el promedio de prestaciones por paciente) |
| diagnóstico +109,6% | "los recursos destinados a diagnóstico, confirmación y etapificación aumentaron 109,6%," |
| tratamiento +85,4%; seguimiento +80,2% | "En tanto, el financiamiento para tratamiento creció 85,4% y el destinado a seguimiento aumentó 80,2%." |
| tratamiento 80–83% del total | "representando entre el 80% y el 83% del financiamiento GES-Cáncer durante los años analizados." |
| 16 patologías | "en 16 patologías oncológicas GES entre 2018 y 2024." |
| fuente de datos | el artículo dice que los datos provienen de registros obtenidos de Fonasa por Transparencia (paráfrasis del extracto) |

Comprobación aritmética: 350.778 / 185.472 = 1,891 (+89,1% ✓). 1.564.084 / 1.135.798 = 1,377 (+37,7% ✓). 953.422 / 717.432 = 1,329 (+32,9% ✓). 1.135.798 / 717.432 = 1,583 y 1.564.084 / 953.422 = 1,641 (✓ 1,58 y 1,64 son prestaciones por persona). 185.472 millones / 1.135.798 = $163.297 y 350.778 millones / 1.564.084 = $224.270 (✓ $163.000 y $224.000; +37,3%).

### Noticia ancla — La Tercera, 21-oct (feed de Alicanto)
URL: https://www.latercera.com/nacional/noticia/estudio-revela-que-el-costo-real-por-prestacion-oncologica-ges-aumento-37-entre-2018-y-2024/
Registro del feed: "el financiamiento de las prestaciones GES oncológicas pasó de $185.472 millones en 2018 a $350.778 millones en 2024, un crecimiento de 89,1%, mientras las prestaciones aumentaron 37,7%, de 1.135.798 a 1.564.084 […] el costo real promedio por prestación subió aproximadamente 37%, de cerca de $163 mil a $224 mil, expresados en pesos de 2026." Coincide con G5noticias.

### Minsal, 19-oct — presentación de la Partida 16 (fuente primaria)
URL: https://www.minsal.cl/ministra-chomali-y-presupuesto-2027-este-es-el-primer-paso-para-la-sostenibilidad-financiera-del-sistema/ (leída como https://www.minsal.cl/?p=159708, mismo título y fecha)

| Cifra usada | Cita |
|---|---|
| 22,7% y +4,7% | "los recursos destinados a Salud representan el 22,7% del erario nacional, lo que significa un crecimiento de un 4,7%." |
| $52.846 millones para derivaciones | "contempla 52.846 millones de pesos adicionales para derivaciones oncológicas" |
| $5.387 millones para detección precoz | "5.387 millones de pesos para detectar a tiempo el cáncer cervicouterino, colorrectal y gástrico" |
| brecha gasto–presupuesto (contexto, sin cifra) | "la Partida 16 pretende disminuir progresivamente la brecha existente entre el gasto y el presupuesto." |

Nota de la revisión: la misma oración menciona "23.501 millones de pesos" para renovar equipos del Plan Nacional del Cáncer, mientras que la nota del 21-oct habla de "$22.843 millones para el Plan Nacional del Cáncer". Por esa inconsistencia, ninguna de las dos cifras se usa.

### Minsal, 21-oct — Tercera Subcomisión Mixta aprueba la partida (fuente primaria)
URL: https://www.minsal.cl/tercera-subcomision-mixta-de-presupuestos-aprueba-partida-del-ministerio-de-salud-para-2027-recursos-aumentan-47-y-superan-los-183-billones/ (leída como https://www.minsal.cl/?p=159780)

| Cifra usada | Cita |
|---|---|
| $829 mil millones adicionales | "El presupuesto contempla $829 mil millones adicionales para fortalecer la atención primaria, reducir los tiempos de espera," |
| 58,7% → 81,9% | "la proporción del financiamiento hospitalario vinculada a actividad asistencial valorizada" … "aumentará de 58,7% a 81,9%, fortaleciendo la relación entre los recursos asignados y las prestaciones realizadas." |
| aprobado en subcomisión | título: "Tercera Subcomisión Mixta de Presupuestos aprueba partida del Ministerio de Salud para 2027: recursos aumentan 4,7%…" |

### Minsal, informe de listas de espera No GES y garantías GES retrasadas (glosa 06), II trimestre 2026 (fuente primaria)
URL: https://www.minsal.cl/wp-content/uploads/2026/08/Glosa-06-LE-II-trimestre.pdf (corte al 30 de junio de 2026)

| Cifra usada | Cita |
|---|---|
| 68.878 garantías retrasadas | "se registraron 68.878 Garantías de Oportunidad GES retrasadas" |
| 2,83%, −0,21 pp (3,04% en 2025) | "La proporción de garantías retrasadas sobre el total alcanzó 2,83%, lo que representa una disminución de 0,21 puntos porcentuales" |
| Tabla 4, personas | "Cáncer colorrectal en personas de 15 años y más 4.151" · "Cáncer de mama en personas de 15 años y más 2.614" · "Cáncer cervicouterino 2.496" · "Cáncer gástrico 1.471" · "Cáncer de próstata en personas de 15 años y más 792" |
| "los tres que, junto al de mama, más retrasos acumulan entre los oncológicos" | Las demás filas oncológicas de la Tabla 4 son menores: pulmón 701, tiroides 451, linfomas 431, renal 321, ovario 149, testículo 143, leucemia 72, vesical 69, mieloma 29, menores de 15 años 19 y osteosarcoma 3. Tumores primarios del SNC (744, no se llaman "cáncer" en la tabla) también son menores que 1.471 |

Descartado tras la revisión: la comparación con el I trimestre (77.604 garantías retrasadas al 31 de marzo). Ese informe da una proporción de 6,50%, frente a 2,83% en el II trimestre, y sus tablas de personas y de garantías no cuadran entre sí (colorrectal: 5.448 frente a 5.483). La metodología no parece comparable, así que no se usa una serie trimestral.

## 3. Estimaciones (deterministas)

| id | Fórmula | Valor | Uso |
|---|---|---|---|
| veces_presupuesto | 89.1 / 42.3 | 2,11 | "el doble" (titular, gráfico 1); nota n2 |
| intensidad | ((1564084 / 953422) / (1135798 / 717432) − 1) × 100 | 3,62 | "+3,6% prestaciones por persona" (lectura); nota n3. Reemplaza la versión 1,64 / 1,58 (3,8%), que usaba promedios ya redondeados |
| derivar_detectar | 52846 / 5387 | 9,81 | "9,8 veces" (lectura); nota n4 |

## 4. Revisión escéptica (segunda lectura): correcciones hechas

1. El titular decía "gasto GES en cáncer", pero el estudio cubre solo Fonasa. Ahora dice "gasto de Fonasa en cáncer GES … 89% real en seis años".
2. "El doble que el presupuesto": la prensa no dice si el 42,3% del Minsal está en pesos constantes. Si fuera nominal, la brecha real sería mayor, así que "el doble" es una cota prudente. Queda declarado en n2.
3. "9,8 veces más recursos nuevos": el Minsal solo llama "adicionales" a los $52.846 millones. Se cambió a "destina a derivaciones oncológicas adicionales 9,8 veces lo que asigna a detectar a tiempo…". La n4 aclara que se comparan solo dos líneas y que no se sabe a qué prestadores irán las derivaciones.
4. "En atención primaria" para la línea de detección venía de una paráfrasis, no de una cita. Se eliminó.
5. "Más retrasos GES acumulan" era ambiguo (¿entre todos los problemas GES?). Ahora dice "entre los oncológicos".
6. "Qué mirar" 2 afirmaba que la detección temprana era el cuello de botella, pero los retrasos GES pueden estar en tratamiento. Se reescribió como un hecho comprobable: son los mismos cánceres a los que apunta la línea de detección.
7. "Desplazando otras prestaciones o generando deuda" pasó a condicional ("Si sigue creciendo al doble…"), dentro de la lectura.
8. "Demanda concreta" para clínicas privadas pasó a "pueden ser". El Minsal no dice a qué prestadores irán las derivaciones (n4).
9. El teaser decía "el cáncer GES cuesta 89% más". Es el gasto total, no el costo, y se corrigió.
10. "Glosa 06" se quitó de los textos visibles: la regla 3 estricta lee "06" como cantidad.

Riesgos que quedan (para el revisor independiente):
- Las cifras del estudio CIPS-UDD vienen de prensa (dos medios coinciden). Nadie ha revisado el informe original (n1).
- La lectura "Isapres y laboratorios deberían leer la misma señal" es una inferencia sectorial. El estudio no incluye Isapres.
- El proyecto 2027 aún no es ley (n6).

## 5. Verificación determinista

Se importa `verify_candidate` (`src/radar_salud/weekly_insight_a.py`) con un paquete de evidencia armado con las citas de arriba (`numbers` = cifras de las citas; `allowed_urls` = las 5 fuentes), más `presentation_a_errors` y `freshness_gate` (`src/radar_salud/weekly_freshness.py`, versión del commit 7da148ea, que aplica la regla 3 estricta a todo texto visible).

```json
{
 "verification": {
  "verdict": "PASS",
  "errors": [],
  "warnings": []
 },
 "presentation_a_errors": [],
 "gate": true,
 "gate_nov8": true,
 "gate_nov9": false,
 "headline_chars": 138,
 "dek_words": 32,
 "essay_words_approx": 246,
 "reading_time_min": 2,
 "warnings": []
}
```

`verify_candidate`: **PASS**, 0 errores y 0 advertencias. `presentation_a_errors`: `[]`. Paquete de evidencia: 41 cifras y 5 URL permitidas. `freshness_gate` (anchor_kind monday): elegible el 2026-11-02 y el 2026-11-08, no elegible el 2026-11-09. `product_report.py` en la copia temporal, con la fecha del 2026-11-02: `weekly_insight_status = published_editorial_reviewed`, `weekly_presentation.errors = []`.

**Bloqueo detectado en el frontend (no corregido aquí):** `weeklyFresh()` en `web/app.js` (línea 51) exige que `event_date` tenga menos de 7 días respecto de hoy. La regla del lunes del backend (`monday_freshness_gate`) admite evidencia de hasta 14 días. Este candidato tiene `event_date` 2026-10-21, así que el 2-nov el sitio lo **ocultaría** aunque `free_value.json` lo publique (en el render: `weeklyFresh(w, 2026-11-02) = false`). Cualquier insight del lunes con noticia ancla de 7 a 14 días de antigüedad queda oculto. Corrección sugerida: que `weeklyFresh` replique `monday_freshness_gate` cuando `anchor_kind === 'monday'` (ancla ≤ hoy < expires_on; ancla − evento ≤ 14 días). Por eso las capturas se tomaron llamando directamente a `renderWeeklyDetail(freeValue.weekly_insight)` y `showModal()` en el sitio servido, no desde la tarjeta del home.

## 6. Render

Sitio real (`web/app.js`, `renderWeeklyDetail`) servido desde una copia temporal. Allí `editorial_approved.json` se reemplazó por este candidato y `free_value.json` se regeneró con `scripts/product_report.py`, con la fecha fijada al 2026-11-02 para el gate del lunes. El worktree no se tocó.
Capturas: `2026-11-02-wow-390.png` y `2026-11-02-wow-1280.png` (diálogo completo). Sin scroll horizontal a 390 px, 2 SVG y sin errores de página. A 1280 px se acortaron las etiquetas del gráfico 1 ("GES-Cáncer", "Minsal"), porque se superponían.

## 7. Revisión editorial independiente: PASS_WITH_CORRECTIONS (27-oct)

Se aplicaron las 6 correcciones pedidas:

1. Titular, `title` e `insight_title`: "… 2027 suma más a derivar que a detectar" (138 caracteres).
2. Lectura, primer párrafo: primera oración reemplazada ("dos vías de peso parecido: más personas atendidas (+32,9%) y un costo promedio por prestación cerca de 37% mayor … crecieron 3,6%").
3. Estimación `intensidad`: valor 3,62, display "≈ +3,6%", n3 con el texto indicado. Los 4 insumos (1.135.798, 1.564.084, 717.432, 953.422) ya estaban en `key_figures`.
4. Gráfico 1: rótulo "Minsal*" y el subtítulo indicado.
5. Lectura, segundo párrafo: "…9,8 veces lo que asigna, en un monto que el Minsal no califica como adicional, a detectar a tiempo…".
6. n4: se agregó la frase indicada. La cifra de $23.501 millones entró en `key_figures` y en las citas de la fuente del 19-oct ("23.501 millones de pesos para renovar equipos del Plan Nacional del Cáncer", releída el 27-oct). Advertencia: la nota del Minsal del 21-oct da "$22.843 millones para el Plan Nacional del Cáncer"; la n4 usa solo la cifra del 19-oct, que es la de equipos.

Opcionales:
- "deberían" pasó a "podrían" (Isapres y laboratorios).
- **Cabecera "21 OCT 2026": no se corrigió.** `renderWeeklyA` en `web/app.js` muestra `fmtDate(w.event_date)`. Cambiar `event_date` al 2-nov falsearía la fecha de la noticia, y la regla de 14 días la usa. Se corrige en `web/app.js` (mostrar `freshness_anchor_date` si `anchor_kind === 'monday'`), junto con el bloqueo de `weeklyFresh` de la sección 5. Eso queda fuera de este commit, que solo incluye candidatos.

Ajustes propios necesarios para volver a PASS, ambos sin cambiar el significado:
- **Fórmula:** se escribió como `((1564084 / 953422) / (1135798 / 717432) - 1) * 100`, en vez de `… * 100 - 100`. Son equivalentes (3,6226). La n3 muestra "− 1", y con la forma original la regla 3 marcaba `number_untraced:notes:1`, porque solo los operandos de la fórmula cuentan como origen.
- **Ensayo (257 palabras, límite 250):** se eliminó "Precio, tecnología y productividad pasan a ser las variables a gestionar, más que el volumen." Además, con la nueva lectura (la mitad del alza viene de más personas atendidas), "más que el volumen" ya no era correcto. Quedan 246 palabras.

Resultado: `verify_candidate` PASS (0 errores), `presentation_a_errors` vacío, gate del 2 al 8-nov elegible y del 9-nov no elegible, `product_report` con estado `published_editorial_reviewed`. Capturas a 390 y 1280 px rehechas: sin scroll horizontal, 2 SVG, sin errores. No se instaló en `editorial_approved.json`.
