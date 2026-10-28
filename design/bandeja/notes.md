# Tu bandeja · 3 propuestas de barra (Dirección 27-oct 22:44)

Maquetas autónomas con el CSS y el marcado reales del Home (copias en esta carpeta: `home-inbox.css`,
`bandeja.js` = copia de `web/app.js` del paso B) y datos reales (`data/radar_today.json`: snapshot del
27-oct-2026 recortado a 95 días, 181 señales). Abrir `header-a.html`, `header-b.html`, `header-c.html`.
Capturas: `header-X-390x844.png`, `header-X-1440x900.png` y `header-X-filtros-*.png` (desplegable abierto).

## Lo que comparten las tres (arreglos 1–5)

1. **Encabezado**: `Chile · Global · Newsletter · PREMIUM` en todos los anchos. *Newsletter* abre el diálogo
   existente de resumen semanal (que enlaza a `subscription.html`); sin JS va a `subscription.html`.
   No se habilita envío ni captura: `data/subscription.json` sigue con `capture_enabled:false`, `send_enabled:false`.
2. **Esta semana**: Insight en **plata mate** (gris frío #F1F2F3→#E8EAEC, borde #D5D9DD) y Global en **oro mate**
   (#F6EFDF→#EFE4CA, borde #E0CFA8). Bajo contraste, pero ya no se vuelven blancos al leerlos (antes el fondo
   leído era #fff, por eso se veían iguales al feed). La marca Nuevo/Leído y el punto toman el tono de su fila.
3. **Filtros = desplegable compacto multiselección** que flota sobre el feed (no lo empuja; la lista conserva su
   lugar). Casillas en 2 columnas: «Todos los temas» (= selección vacía), Actores, Temas, Formato, Orden,
   «Fuentes y cobertura», «Ver N señales». Alto máx. 440 px con scroll interno. Se cierra con clic fuera,
   Escape, «Ver N señales» o al cambiar el período. **Preparado para Entidades** (rama `claude/entity-watch-20261027`):
   el grupo «Entidades» con buscador entra como un grupo más dentro del mismo desplegable (en la maqueta se muestra
   como marcador desactivado).
4. **Período**: es su propio `<select>` nativo en la barra («30 días ▾»). Abre solo la lista corta de períodos
   (en el teléfono, el selector nativo del sistema); ya no abre el panel de preferencias.
5. **Estado de lectura**: control segmentado siempre visible `Pendientes · Leídas · Todas` (desaparece el menú
   «N pendientes ▾»). Temas: el filtro se llama «Todos los temas» cuando no hay selección; ya no existe el chip
   «Todo 76». Solo queda un «todos» por concepto: «Todas» (lectura) y «Todos los temas» (temas).

## Las tres propuestas (misma altura que hoy: 2 líneas en móvil, 1 en escritorio)

| | Móvil, línea 1 | Móvil, línea 2 | Escritorio (1 línea) |
|---|---|---|---|
| **A · Estado junto al título** | Tu bandeja · [Pendientes 76 \| Leídas \| Todas] | [30 días ▾] [☰ Todos los temas ▾] … ✓✓ | título · segmentado con cifras · período · temas … ✓✓ |
| **B · Pestañas + chips de temas** | Tu bandeja · pestañas subrayadas Pendientes 76 · Leídas · Todas … ✓✓ | [30 días ▾] chips desplazables «Todos los temas», Isapres 15, … [⚙] | título · pestañas · período · ⚙ … ✓✓ (los temas viven en el riel) |
| **C · Herramientas arriba, estado a lo ancho** | Tu bandeja · [30 días ▾] [Todos los temas ▾] ✓✓ | segmentado a todo el ancho: Pendientes 76 \| Leídas 0 \| Todas 76 | título · período · temas … segmentado · ✓✓ |

- **A**: la más limpia; un solo lugar para temas (el desplegable). En móvil la cifra se muestra solo en el segmento activo (las otras quedan para lector de pantalla).
- **B**: conserva el cambio rápido de tema con un toque (chips), ahora multiselección y con «Todos los temas» explícito; ⚙ queda para formato/orden/fuentes.
- **C**: la más convencional (estilo iOS); el estado de lectura es lo más visible y muestra las tres cifras.

## Medición: parte del primer viewport ocupada por el feed

Medido con Playwright (Chromium) sobre estas maquetas: (alto del viewport − borde superior de la primera fila del feed) / alto del viewport.

| | 390×844 (mín. 55 %) | 1440×900 (mín. 60 %) | Alto de la barra móvil |
|---|---|---|---|
| Home actual (staging 10d504db) | 62,7 % | 70,6 % | 97 px |
| A | **62,9 %** | **71,0 %** | 95 px |
| B | **62,9 %** | **71,0 %** | 95 px |
| C | **63,6 %** | **71,0 %** | 89 px |

Sin desborde horizontal en ningún caso; sin errores de consola.

## Implementación (paso B)

Las piezas compartidas están en `web/` de la rama `claude/home-ux-round2-20261027`; la propuesta se elige con un
solo atributo: `<section class="radar-unit" data-bar="a|b|c">`. Tras la decisión se borra el CSS de las otras dos.
