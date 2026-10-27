# Portada y Fuentes: propuesta de rediseño (27 oct 2026)

Responde al feedback del director: Insight y Global quedan como acordeones con marca de leído y el feed ocupa ≥50 % del primer viewport. Además se compactan "Tu bandeja" y los filtros, se proponen intereses nuevos y la vista Fuentes pasa a ser minimalista.

Entregables (todos en `design/home/`):

| Archivo | Qué es |
|---|---|
| `home-a.html` | Propuesta A: evolución conservadora de la estructura actual |
| `home-b.html` | Propuesta B (**recomendada**): header fijo compacto, acordeones finos, barra de bandeja en una línea con chips de intereses y feed denso. En desktop, rail lateral de intereses |
| `sources.html` | Fuentes minimalista. Sirve tanto para el diálogo `#sourcesDialog` como para `web/sources.html` |
| `mock-data.js` | Snapshot real generado desde `web/data` (radar_today 27-oct, free_value, public_sources, source_health). Las tres maquetas lo leen; abren con `file://` y no necesitan servidor |
| `current-*.png` | Estado actual: home, diálogo Fuentes y `sources.html`, a 390×844 y 1440×900 (más `-full` de página completa) |
| `proposal-*.png` | Propuestas a ambos tamaños, más estados: `proposal-b-intereses-mobile` (hoja de intereses), `proposal-b-insight-open-mobile` (acordeón abierto), `proposal-b-filtered-desktop` (Isapres+Fonasa), `proposal-a-filtrar-mobile`, `proposal-sources-*` |

Parámetros de URL de las maquetas: `?sheet=1` abre la hoja, `?open=weekly` abre el insight, `?i=isapres,fonasa` preselecciona intereses, `?wr=1` muestra el insight leído y `?gr=0` muestra Global sin leer.

---

## 1. Medición: cuánto del primer viewport ocupa el feed

Método (Playwright, Chromium, DPR 1, tras `networkidle`):

* **Cuota del feed** = unión vertical de los rectángulos de las tarjetas del feed (`#local article.signal` en la app actual, `.feed-card` en las maquetas) dentro del viewport, dividida por el alto del viewport.
* No cuentan los encabezados de grupo ("Hoy y ayer"), los acordeones ni las barras.
* Estado por defecto: perfil nuevo, 30 días, Pendientes, orden "Más recientes", 79 señales.
* En las maquetas, el Insight está sin leer y Global está leído, para mostrar ambos estados.

| | 390×844 cuota feed | 390×844 1.ª tarjeta (top) | 1440×900 cuota feed | 1440×900 1.ª tarjeta (top) |
|---|---|---|---|---|
| **Actual** | **0 %** | 1080 px (128 % del viewport) | **0 %** | 946 px (105 %) |
| **A** (conservadora) | **50,8 %** (5 tarjetas, 4 completas) | 391 px | **58,6 %** (8 / 7) | 294 px |
| **B** (recomendada) | **60,0 %** (7 tarjetas, 6 completas) | 310 px | **65,3 %** (8 / 7) | 283 px |

En la home actual a 390 px, el espacio se reparte así: brandbar 150 px, hero + newsletter 152 px, Insight + Global abiertos 485 px y bandeja oscura 205 px. A 1440 px: brandbar 133, hero 182, especiales 325 y bandeja 211. Hoy ninguna noticia aparece en el primer viewport en ninguno de los dos tamaños. Eso confirma la observación del director de que "¾ es logo, título y filtros".

**Fuentes, estado actual:** el diálogo mide 1941 px en mobile y 1700 px en desktop para solo 12 fuentes, unos 160 px por fuente. Cada fuente es una tarjeta con borde, el título de grupo va en versales serif de 26 px y el enlace va subrayado. **Propuesta:** filas de 34 px de una línea. El catálogo completo, con leyenda y CTA de sugerencia, cabe en una sola pantalla: panel de 794 px en desktop y 844 px en mobile, sin scroll horizontal.

## 2. Qué cambia en cada propuesta

### Común a A y B

* **Insight semanal y Global son siempre acordeones**: no desaparecen al leerse, como ocurre hoy en `#bigThings`.
  * Sin leer: punto acento relleno, pastilla **NUEVO** y fondo tintado.
  * Leído: anillo vacío, etiqueta "Leído", fondo blanco y título en tinta 68 %. El acordeón queda **colapsado**.
  * Al abrirse muestra resumen, fuente, fecha, la CTA "Ver análisis →" o "Explorar Global →" y "Marcar leído / no leído".
* La **newsletter** sale del hero y pasa a una fila fina dentro del feed, tras la 6.ª o 7.ª tarjeta.
* **Filtros:** las categorías actuales (Tipo × Ámbito, 13 ámbitos con nombres internos) se reemplazan por **Intereses** (ver §3).

### A: evolución conservadora

* Mantiene el orden actual: logo → titular → esta semana → bandeja oscura → feed.
* Logo y nav en una sola fila de 52 px (hoy son 150 px).
* Hero en 2 líneas: H1 a 23 px y propósito.
* Acordeones: los no leídos muestran un título de 2 líneas y los leídos, 1 línea. En desktop van lado a lado.
* La bandeja oscura queda en una línea: "Tu bandeja · 79 pendientes · 30 días · [Filtrar]". Debajo va la fila de lanes con "Marcar leídas". En desktop, todo cabe en una sola barra de 52 px.
* Filtrar abre una hoja con chips de intereses, período segmentado y orden.
* Cumple el piso del 50 %, pero en mobile queda justo (50,8 %).

### B: recomendada

* **Header fijo de 52 px**: logo, "Chile · Global" y PREMIUM. En desktop se suman el tagline y "Fuentes".
* **"Esta semana"**: dos filas-acordeón de unos 50 px (kicker, título de 1 línea, estado y chevron). La hora de actualización va en la etiqueta del bloque.
* **Barra de bandeja fija** bajo el header, en una línea: `Tu bandeja · 79 pendientes ▾ · 30 días ▾ · ✓✓ · ⚙`.
  * "79 pendientes ▾" abre las lanes Pendientes/Leídas/Todas. En desktop son tabs visibles.
  * "✓✓" marca todo como leído y "⚙" abre la hoja de intereses.
  * Debajo hay **una sola fila de chips de intereses con conteo**, con scroll horizontal y alto fijo de 40 px. Nunca hace wrap, así que no empuja el feed.
* **Feed denso**:
  * Título de 15 px, semibold, limitado a 2 líneas.
  * Meta de 12 px: fuente · fecha · etiqueta de formato (solo Normativa, Fiscalización o Datos).
  * Iconos de fuente y compartir en la línea de meta.
  * Punto de no leído en el margen izquierdo y separadores de 1 px, sin tarjetas.
* **Desktop**: rail derecho fijo de 288 px con "Mis intereses" (checkbox con conteos, agrupados en Actores y Temas), Período/Orden, resumen de fuentes ("12 fuentes · 3 al día → Ver fuentes") y la suscripción. El feed recupera el ancho completo de la columna.

## 3. Intereses: categorías nuevas, implementables con los campos existentes

En `radar_today.json` hay 189 señales y todas pasan `individualCardAllowed`. Con 30 días quedan 79 visibles. Los campos de clasificación disponibles son:

* `scopes`: 13 valores, siempre presente.
* `signal_types`: Noticias 160, Normativa 17, Fiscalización 7, Datos 4, Acreditación 1.
* `topics`: 9 valores en 185 señales.
* `category`: 12 valores.

`institution_types` y `strategic_theme` están vacíos, y `who_cares` aparece en solo 5 señales.

Basé el mapeo en **`scopes` + `signal_types` + `topics`** y **no en `category`**, porque `category` es ruidoso. Por ejemplo, "Chile, país poco preparado para envejecer" tiene `category`=Regulación & Legal y "Aramco y Enex… ciberseguridad" tiene `category`=Prestadores. La regla de filtro es OR entre intereses, y "Todo" equivale a ninguno seleccionado.

| Interés | Grupo | Regla (sobre campos existentes) | Señales 30 d (de 79) | Señales total (de 189) |
|---|---|---|---|---|
| Isapres | Actor | `scopes` ∋ Isapres \| Agentes de ventas | 13 | 39 |
| Fonasa | Actor | `scopes` ∋ Fonasa | 9 | 21 |
| Prestadores | Actor | `scopes` ∋ Prestadores | 17 | 66 |
| Salud laboral | Actor | `scopes` ∋ Salud laboral \| Seguridad social \| COMPIN | 12 | 24 |
| Farma e ISP | Actor | `scopes` ∋ Farma / medicamentos | 13 | 23 |
| Salud pública | Actor | `scopes` ∋ Salud pública | 12 | 18 |
| Normativa y fiscalización | Tema | `signal_types` ∋ Normativa \| Fiscalización \| Acreditación | 7 | 25 |
| Mercado e inversiones | Tema | `topics` ∋ investment_ma \| competition | 21 | 46 |
| Política y presupuesto | Tema | `scopes` ∋ Política pública \| Financiamiento, **o** (`scopes` ∋ Sistema de salud **y** `topics` ∋ financing \| waiting_lists) | 10 | 18 |
| Datos y cifras | Tema | `signal_types` ∋ Datos, o `category` ∈ {Datos sectoriales, Epidemiología y presión asistencial} | 1 | 4 |
| Innovación y global | Tema | `scopes` ∋ Healthtech, o `category` ∈ {Innovación & Startups, Radar Mundo} | 2 | 8 |

* **Cobertura:** 74 de las 79 señales visibles (94 %) caen en al menos un interés. Las 5 restantes tienen solo `scopes`=Sistema de salud, por ejemplo el balance Senapred y la nota sobre Rotter & Krauss. Siguen visibles en "Todo". En total quedan fuera 16 de 189.
* Los chips con 0 señales en el período se ocultan; hoy pasaría con Innovación y global a 7 días. "Datos y cifras" e "Innovación y global" tienen poco volumen. Conviene revisarlos en 4 semanas y fusionarlos si siguen por debajo de 3 al mes.
* **Por qué actores y temas:** la audiencia (gerencias de isapres, clínicas, mutuales, farma y consultoras) se identifica por *a quién le pega* la noticia, no por su formato. "Mercado e inversiones" (21) es el interés con más volumen y hoy no existe como filtro.

**Forma de selección (B):** chips segmentados en línea como superficie principal y una hoja "Intereses" como superficie secundaria.

* Los **chips** dan filtrado de 1 toque, muestran dónde está el volumen gracias a los conteos y tienen alto constante, porque hacen scroll en vez de wrap. Además, la selección activa siempre está a la vista, cosa que hoy se esconde dentro de `<details>`.
* La **hoja** concentra lo que se toca poco (período, orden, "Fuentes y cobertura") y muestra todos los intereses agrupados con objetivos táctiles de 44 px.
* El estado es el **mismo** en chips, hoja y rail de desktop: un solo `Set` persistido en `alicanto_filters`, así que no hay dos modelos de preferencia. Esto respeta el test "one persistent filter model".

A usa solo la hoja, porque es más conservadora y tiene un toque más de fricción.

## 4. Fuentes: rediseño minimalista

* **Título "Fuentes"** y una línea de contexto: "12 fuentes públicas verificadas · 3 al día · revisadas hoy 09:04". El dato sale de `max(checked_at)` en source_health: 12:04 UTC son las 09:04 en Chile.
* **Leyenda en una línea:**

  | Estado | Regla |
  |---|---|
  | ● Al día | `technical_status` ok y `content_freshness` = recent |
  | ● Activa | ok, pero con contenido antiguo o desconocido |
  | ● Parcial | `technical_status` = partial |
  | ○ En prueba | la descripción contiene "En prueba" |

  Todo sale de `source_health.json`. La fecha corresponde a `latest_original_at`, o a `last_signal_at` si la primera falta.
* **Grupos** con versalitas de 10,5 px y conteo.
* **Filas de 34 px** con punto de estado, nombre (enlace) · descripción breve en gris y fecha alineada a la derecha. La línea es única, con ellipsis.
* **Pie:** "¿Falta una fuente relevante? Sugerir fuente →".
* Se eliminan el texto de marketing, el enlace "Ver catálogo" (la lista ya es el catálogo) y las tarjetas con borde.
* El mismo componente sirve para `web/sources.html`.
* Observación de datos: DEIS sale "Activa" con contenido de **25 jun**, y Superintendencia · Prestadores y PAHO no tienen fecha (se muestra "—"). Se muestran tal cual, sin maquillar.

## 5. Recomendación

**Recomiendo implementar B.** Es la única que llega al rango objetivo en ambos tamaños (60 % / 65 %), deja 6–7 noticias completas en el primer viewport y resuelve los cinco puntos del director:

1. Acordeones permanentes con marca de leído.
2. Menos espacio blanco.
3. Bandeja en una línea.
4. Intereses visibles y atractivos.
5. Fuentes limpia.

A queda como alternativa de bajo riesgo si se quiere conservar la bandeja oscura como ancla visual, aunque en mobile apenas supera el 50 %.

## 6. Plan de implementación (B), en rama aislada con PR hacia `staging`

**`web/index.html`**

* `header.brandbar`: logo a 32 px (38 en desktop) y nav en una fila. Se mueve a `position:sticky`. Se agrega el botón "Fuentes" solo en desktop, con `data-open-sources` y sin id.
* `.hero`:
  * se elimina el bloque visual.
  * `.hero-purpose` se conserva como tagline del header, con el texto exacto, oculto en mobile.
  * `#meta` pasa a la etiqueta "Esta semana" y conserva el prefijo "Última actualización:".
  * `h1` "Encuentra lo que importa": ver riesgos.
* `.newsletter-strip` (con `#newsletterOpen` y el copy exacto) se saca del hero y se inserta en el feed desde app.js tras la 7.ª tarjeta. En desktop se repite en el rail.
* `#bigThings` pasa a ser el contenedor "Esta semana", siempre visible si hay especiales. Se conserva `#valueHighlights` (hidden).
* `.radar-unit`:
  * `.radar-head` contiene `h2#radarTitle` "Tu bandeja", `#radarMetrics` (pasa a ser el botón de lanes en mobile), la pastilla de período (proxy del `<select id="period">`), `#markAllRead` como icono y `summary` como botón ⚙.
  * **No** se pone `id="period"` dentro de `.radar-head`.
* `details#filterDetails` se conserva como hoja/popover: `<summary>` es el botón ⚙ y `.filter-body` es la hoja.
  * Contiene `#period`, `#sort`, `#resetFilters`, el texto "Tus filtros se guardan automáticamente…" y un nuevo `#interestFilters`.
  * `#typeFilters` se conserva como fila "Formato".
  * `#scopeFilters` se reemplaza por `#interestFilters`.
* Nuevo `div#interestChips` bajo `.radar-head` para los chips en línea, y `aside.rail` para desktop.
* `#sourcesOpen` se mueve al pie del feed (`.feed-end`). La hoja y el rail usan `data-open-sources`.
* `#lanes` se conserva con `[data-lane]`: en desktop son tabs y en mobile un menú.
* `#sourcesDialog`: se quitan `.conversion-lead` y el enlace "Ver catálogo". Se agrega la leyenda y la línea de contexto. Se conservan `#sourcesList`, `#source-suggestion` y `#sourceSuggestionOpen`.
* Se eliminan los bloques `<style>` inline acumulados de `.hero`, `.big-feature`, `.briefrow`, `.radar-unit .brief-list` y similares. Se consolidan en `home-inbox.css`.

**`web/app.js`**

* `brief()`: se renderizan **todos** los especiales en `#bigThings` como acordeones (`.big-feature.weekly/.global` + `.read`) y ya no se filtra `!specialRead(x)`.
  * El punto `[data-special-read]` es un botón propio de 44×44 px, separado del toggle de expandir.
  * Abrir el acordeón no marca leído; sí lo marca la CTA "Ver análisis".
* `draw()`: se elimina `readSpecials`/`groups.unshift(['Ediciones de la semana',…])` y `specialRow()`, que queda sin uso.
* `INTERESTS`: nuevo arreglo con las reglas de §3. `visible()` agrega el filtro `activeInterests` (OR) y `renderFilters()` dibuja chips, hoja y rail desde la misma fuente, con conteos sobre `inPeriod`.
* `persistFilters()`: agrega `interests:[...]`. Migración: un `scope` guardado se traduce a su interés equivalente (por ejemplo, Isapres → `isapres`) y "Todos" se traduce a `[]`.
* `card()`: título limitado a 2 líneas por CSS y la etiqueta de formato (`.tag`) solo para Normativa, Fiscalización o Datos. `rowMeta` no cambia.
* `updateMetrics()`: además actualiza el texto del botón de lanes en mobile.

**`web/public-sources.js`**

* `render()`: filas `.source-row` con `.d.<estado>`, nombre, descripción y fecha. Recibe `health` como segundo parámetro opcional.
* Se conserva el nombre oficial completo en el texto de la fila, porque los tests filtran `.source-row` por `health.sources[id].name`.
* Opcional: `short_name` en `public_sources.json`, mostrado con el nombre completo en un `sr-only`. Hay que verificar que `hasText` lo siga encontrando.

**CSS**

* `home-inbox.css` recibe los tokens (`--ink`, `--ivory`, `--accent`) y los estilos de header, acordeón, barra, chips, feed denso y rail.
* `product-ui.css` recibe el componente Fuentes.
* Fuera del header, la página no debe tener scroll horizontal a 390 px; los chips solo hacen scroll dentro de su contenedor.

## 7. Riesgos sobre tests existentes (selectores e IDs a preservar o actualizar)

**Se preservan tal cual:**

* `#radarTitle` (texto exacto "Tu bandeja", con el `<h2 id="radarTitle">Tu bandeja</h2>` literal que busca `web.test.cjs`).
* `#radarMetrics` (texto `N pendientes|Estás al día`, nunca "período" ni "30 días"; el período va en su propia pastilla).
* `#filterDetails` (cerrado por defecto; `summary` con `justify-content:flex-start`).
* `#period` y `#sort` dentro de `#filterDetails` (`#sort` por defecto es `date` y `#period` es `30`).
* `#resetFilters`, `#markAllRead`, `#lanes` con `[data-lane=p|l|t]` y `aria-pressed`, `#undoBar` y `#undoRead`.
* `#local article[data-card]`, `.title-open`, `[data-read]` y `[data-share]`.
* `#bigThings .big-feature.weekly/.global`, con `[data-special-read]` ≥44 px y `.card-meta` dentro del cuerpo.
* `#weeklyInsightDialog` (contiene "Lectura Alicanto:").
* `#sourcesOpen`, `#sourcesDialog`, `#sourcesList .source-row` (con `link` https), `#source-suggestion` y `#earlyAccessOpen`/`button.premium-access` ("Acceso PREMIUM"; en B el texto visible es "PREMIUM", así que hay que conservar el texto completo o actualizar el test).
* `#newsletterOpen` dentro de `.newsletter-strip`, con su copy exacto.
* `#valueHighlights`, `#backTop`, "Volver arriba" y `#meta` ("Última actualización:").

**Tests que cambian por decisión de diseño (requieren aprobación del director y actualizarse en el mismo PR):**

1. `product.spec.cjs` ~176–182 y 227–229: hoy esperan que el especial leído **desaparezca** de `#bigThings` (`toHaveCount(0)`, `#bigThings` hidden) y reaparezca en `#local .special-row` bajo "Ediciones de la semana". Con acordeones permanentes, el especial sigue en `#bigThings` con clase `.read` y no se duplica en `#local`. Hay que reescribirlos para comprobar `.read`, el estado colapsado y la persistencia tras recargar. También cambia que el foco vaya a `.lane.on` después de marcar.
2. `product.spec.cjs` 30–31: el H1 "Encuentra lo que importa" visible y en una línea. B lo retira de la vista. Hay dos caminos: actualizar el test, o conservar el H1 como `sr-only`, aunque así deja de ser "visible" y el test falla igual.
3. `product.spec.cjs` 506–513 (mobile): exigen `#radarMetrics.y > #radarTitle.y` y `#sourcesOpen.y > #radarMetrics.y`.
   * Con título y conteo en la misma línea, el primero depende de la alineación. Usar `align-items:baseline` hace que el texto pequeño quede más abajo, pero conviene relajar el test a "misma línea o debajo".
   * El segundo se cumple si `#sourcesOpen` va al pie del feed.
4. `product.spec.cjs` 90–97: hacen clic en `#typeFilters` → "Fiscalización" dentro del `<details>`. Se conserva `#typeFilters` (fila "Formato" de la hoja) y no cambian. Los tests sobre `#scopeFilters` (si los hay en specs nuevos) pasan a `#interestFilters`.
5. Fuentes (`product.spec.cjs` 553–558, `occupational-recovery`, `providers`, `pulso-source-registry`):
   * `#sourcesList` debe seguir conteniendo los nombres de grupo "Organismos públicos y reguladores" y "Noticias y mercado".
   * **No** debe contener `Última consulta|Última señal detectada|Última seleccionada|Reuters|FONASA`. Por eso la leyenda usa "Fecha = contenido más reciente capturado".
   * Las filas deben conservar el nombre oficial (`hasText`).
6. `web.test.cjs` "Home inbox keeps actions in the gutter": `specialCard()` debe seguir conteniendo `class="dotbtn`, `data-special-read`, `data-share` dentro de `.card-meta`, y el texto "Insight de la semana · N fuentes". La maqueta B abrevia el kicker a "Insight · 6 fuentes", así que conviene mantener el texto largo o ajustar el test.

## 8. Notas

* Las maquetas no modifican `web/` ni ningún otro archivo del repo; todo está en `design/home/`.
* El teaser del insight contiene "~-22%" (copy de `free_value.json`). Es un detalle editorial menor.
* Ninguna propuesta activa newsletter, pagos ni gasto de IA: los botones de suscripción siguen siendo los existentes, que hoy están deshabilitados.
