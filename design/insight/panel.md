# Panel de diseño: presentación del Insight semanal

Insight evaluado: `weekly-insight:2026-10-23:licencias-control-y-costo` (`data/weekly_insight/editorial_approved.json`).
Versión actual: `web/app.js` → `renderWeeklyDetail` + `insightChart`; estilos en `web/home-inbox.css`.
Capturas de la versión actual: `current-390.png`, `current-1280.png` (solo la parte visible del diálogo).

**Diagnóstico de la versión actual:** unas 730 palabras de cuerpo (más las fuentes) en 1 resumen + 7 listas con encabezado (Cifras y alcance, Actores, Lectura Alicanto, Decisiones que cambia, Qué observar, Límites de la evidencia, Fuentes). Los gráficos aparecen recién después de 6 viñetas de cifras que repiten sus mismos números. Lectura estimada: 3,5–4 min.

---

## 1. Críticas de cada experto a la versión actual

### Experto editorial en salud
- El foco (las licencias bajan, pero la caída se modera) está en el título, pero luego se diluye en 7 bloques. El lector tiene que reconstruir la tesis.
- "Lectura Alicanto" mezcla viñetas "Hecho:" e "Inferencia Alicanto:". Un hecho no es una lectura nuestra; ese rótulo confunde la separación que pretende hacer.
- Las mismas cifras aparecen hasta tres veces: en el resumen, en "Cifras y alcance" y en el gráfico (−12,3%, −14%, −13,4%, −12,2%).
- "Límites de la evidencia" está separado de las afirmaciones a las que se refiere. El lector no sabe que el ≈ −22% es la estimación frágil hasta llegar al final.
- "Qué observar" usa IDs normativos (Circular 3926, art. 30 del DS 3) sin explicarlos. Un no especialista no puede actuar con eso.

### Experto en negocios de salud (Isapres, Fonasa, prestadores, mutualidades)
- Lo esencial para un pagador es una sola idea: el costo se mueve por días (≈ −22%) y el ahorro se está moderando. Esa idea está enterrada en la viñeta 2 de "Cifras".
- "Decisiones que cambia" dice cosas que un ejecutivo del sector infiere solo ("modelar SIL por días", "ajustar procesos COMPIN"). Agrega largo, pero no información nueva.
- "Actores" es una lista descriptiva (quién paga, quién emite) que el público objetivo ya conoce.
- Falta jerarquía: el techo de $85 mil millones y los 5.646 funcionarios pesan visualmente lo mismo que la tesis principal.
- Las mutualidades no aparecen. Es correcto, porque el dato es de licencias de origen común, y no conviene forzarlas.

### Experto en storytelling
- No hay arco: es un inventario de fragmentos. Cada sección intenta ser mínima y el conjunto termina siendo tedioso.
- La tensión narrativa (cae, pero se frena: ¿qué pasa en 2027?) es buena, pero nunca se cuenta en prosa.
- Los gráficos, que son lo más claro, llegan tarde y sin un titular que diga qué mirar ("variación acumulada de licencias emitidas" describe, no afirma).
- El texto en gris claro y el cuerpo de las viñetas en otro tamaño rompen la lectura.

### Experto en presentación ejecutiva
- La regla de los 5 segundos no se cumple: después del título viene un párrafo de 90 palabras en gris, no el gráfico.
- El gráfico 1 usa 6 barras sueltas (Total/Fonasa/Isapres × 2 períodos). El par ago→sep no se lee como comparación; el "se modera" hay que buscarlo.
- El gráfico 2 está bien resuelto (octubre parcial distinguido), pero le falta un titular afirmativo y la nota de cobertura.
- Los números deben ir en el gráfico y la interpretación en el texto. Hoy ambos dicen lo mismo.
- En móvil el diálogo mide unos 4.700 px: demasiado scroll para un producto premium.

---

## 2. Las tres propuestas

Todas usan solo cifras del JSON. Únicos cálculos deterministas: ≈ −22% (0,877 × 0,891, ya presente en el JSON) y la moderación en pp (−12,3 − (−14,0) = +1,7; Fonasa +1,0; Isapres +1,3), presentada como diferencia aritmética. Ninguna tiene "Decisiones que cambia". Los límites de la evidencia pasan a superíndices ¹–⁵ con notas al final. Los hechos van en sans sin rótulo de lectura; la interpretación va en serif con filete ocre y rótulo "Lectura Alicanto" / "Alicanto".

| | A · Titular, gráficos, ensayo | B · Panel ejecutivo | C · Memo narrativo |
|---|---|---|---|
| Archivo | `proposal-a.html` | `proposal-b.html` | `proposal-c.html` |
| Concepto | Lo que pidió el director, literal: titular que decide → 2 gráficos → ensayo corto en dos tiempos (Qué pasó / Lectura Alicanto) → 3 señales autoexplicativas | Lectura en 90 s: titular-pregunta → 3 KPI → 2 gráficos → dos columnas (datos / lectura) → "Por qué le importa" por actor | Pregunta y respuesta corta, luego prosa continua con los gráficos intercalados en el punto del relato donde prueban algo |
| Estructura | Kicker · H1 · bajada factual · gráficos lado a lado (apilados en móvil) · Qué pasó · Lectura Alicanto · Qué mirar (3) · Notas · Fuentes | Kicker · H1 · KPI ×3 · gráficos · Datos ‖ Lectura · 3 tarjetas por actor · Notas · Fuentes plegadas | Kicker · H1 pregunta · respuesta · ¶ hecho · gráfico 1 · ¶ Alicanto · ¶ hecho · gráfico 2 · ¶ Alicanto · Próxima señal · Notas · Fuentes |
| Gráfico 1 | Barras pareadas desde cero (ago gris / sep ocre) con la columna "+x pp": la opción más honesta | Dumbbell con eje ampliado (−15 a −11), declarado bajo el gráfico | Slope chart ago→sep con eje ampliado y Total resaltado |
| Gráfico 2 | Columnas; octubre rayado/punteado "parcial · al día 16"; nota ⁴ de ventana de 90 días | Igual | Igual |
| Palabras (sin notas ni fuentes) | ≈ 425 (ensayo ≈ 225) | ≈ 350 (ensayo ≈ 155) | ≈ 350 (prosa ≈ 250) |
| Notas + fuentes | ≈ 195 | ≈ 175 (fuentes plegadas) | ≈ 165 |
| Lectura | ≈ 2 min (lo esencial en 10 s: H1 + gráficos) | ≈ 90 s (esencial en 5 s: KPI) | ≈ 2 min (esencial en 10 s: pregunta + respuesta) |
| Alto móvil / desktop | 3.322 / 2.412 px | 2.981 / 1.729 px | 2.932 / 2.413 px |
| Riesgo | Más largo de las tres; "Qué mirar" debe mantenerse autoexplicativo | Los KPI repiten números del gráfico (redundancia que el director criticó); "Por qué le importa" se acerca a "Decisiones que cambia" | La prosa repite algunas cifras del gráfico para hilar el relato; los gráficos no quedan juntos arriba |

Capturas: `proposal-{a,b,c}-390.png` y `proposal-{a,b,c}-1280.png`. Ninguna tiene scroll horizontal a 390 px.

### Debate del panel (resumen)
- **Editorial:** prefiere A o C. Ambas separan hechos de lectura sin rotular hechos como lectura. B corta la lectura a 2 párrafos y pierde matiz (salud mental).
- **Negocio:** le atrae B ("Por qué le importa"). Acepta que las tarjetas son lo que el director llamó redundante y que el ejecutivo lo infiere del ensayo de A. Pide que el ≈ −22% (días) aparezca en el primer párrafo de la lectura. A lo cumple.
- **Storytelling:** prefiere C, el único con arco real. Reconoce que el director pidió explícitamente "título → gráficos → ensayo", y que A conserva un arco dentro del ensayo (dato → ahorro real → no es tendencia → cautela).
- **Presentación ejecutiva:** descarta C, porque los gráficos dispersos impiden captar todo en un vistazo. Descarta los KPI de B, porque son números que ya están en los gráficos. Apoya A con barras desde cero.

---

## 3. Recomendación: Propuesta A

Por qué:
1. Sigue el orden que pidió el director: titular potente que toma posición → gráficos (lo que él valora) → ensayo breve.
2. El texto no repite el gráfico. "Qué pasó" no repite las cifras por seguro ni las de sanciones; solo agrega lo que el gráfico no muestra (días, salud mental, fiscalización, Circular 3931 en lenguaje llano).
3. Separa hechos de interpretación por tipografía y filete, sin llamar "lectura" a un hecho.
4. Los límites de la evidencia quedan como superíndices junto a cada afirmación, con notas al final.
5. "Qué mirar" se reduce a 3 señales, cada una con su porqué en una frase y sin IDs normativos sin explicar (la Circular 3931 se nombra después de describir la regla). Se eliminó la Circular 3926 / art. 30 DS 3, porque no se puede explicar en una línea.
6. El gráfico 1 cambia a barras pareadas desde cero con "+x pp". Es más honesto que un eje ampliado y la moderación se lee directamente.

Para incorporar de las otras propuestas:
- De C: la "Próxima señal" como una sola línea es una alternativa si el editor no logra 3 señales autoexplicativas. Si hay menos de 2 señales válidas, la sección se omite.
- De B: plegar las fuentes en `<details>` en móvil para acortar el scroll.

---

## 4. Cambios de esquema en `editorial_approved.json` (`weekly_insight`)

**Eliminar del render** (y del contrato editorial nuevo):
- `decision_use`: se elimina.
- `actors`: se elimina del render. Puede quedar como metadato interno de clasificación.
- `insight_reading`: lo reemplaza `essay` (ver abajo). Hoy mezcla "Hecho:" e "Inferencia Alicanto:" en un mismo arreglo.
- `uncertainties`: lo reemplaza `notes` con IDs referenciables.
- `key_figures`: no se renderiza. Se conserva para auditoría y validación de cifras, porque cada número del ensayo debe existir aquí o en `estimates`.
- `summary`: lo reemplaza `dek`. Se mantiene `insight_teaser` para la tarjeta del inbox.

**Agregar:**

```jsonc
{
  "headline": "Las licencias médicas caen 12,3%, pero la caída ya se frena: 2027 no debería presupuestarse con el ahorro de 2026",
  "dek": "Entre enero y septiembre se emitieron 5.155.495 licencias médicas electrónicas, 12,3% menos que en 2025. Un mes antes, la baja acumulada era de 14%.",   // solo hechos, ≤ 40 palabras
  "estimates": [                                   // cálculos deterministas, no LLM
    {"id": "dias_reposo", "label": "días totales de reposo", "value": -21.9, "display": "≈ −22%",
     "formula": "0.877 * 0.891 - 1", "inputs": ["licencias -12,3%", "días promedio 12,8→11,4"], "note_ref": "n1"},
    {"id": "moderacion_total", "value": 1.7, "unit": "pp", "formula": "-12.3 - (-14.0)"}
  ],
  "charts": [
    {
      "id": "moderacion",
      "form": "paired_bars",                       // paired_bars | columns
      "headline": "La caída se achica en todos los seguros",   // titular afirmativo
      "subtitle": "Variación interanual acumulada de licencias emitidas",
      "unit": "%",
      "series": [{"key": "ago", "label": "ene–ago", "emphasis": false}, {"key": "sep", "label": "ene–sep", "emphasis": true}],
      "rows": [
        {"label": "Total",   "values": {"ago": -14.0, "sep": -12.3}, "strong": true},
        {"label": "Fonasa",  "values": {"ago": -14.4, "sep": -13.4}},
        {"label": "Isapres", "values": {"ago": -13.5, "sep": -12.2}}
      ],
      "delta": {"from": "ago", "to": "sep", "unit": "pp", "label": "se modera"},   // calculado por el renderer
      "source": "SUSESO (ene–sep, 23 oct) y datos SUSESO citados por Pulso (ene–ago, 9 oct)",
      "note_refs": []
    },
    {
      "id": "sanciones",
      "form": "columns",
      "headline": "Más de 30 sanciones a emisores al mes",
      "subtitle": "Oficios de sanción a emisores de licencias, por mes",
      "unit": "oficios",
      "rows": [{"label": "Ago", "value": 36}, {"label": "Sep", "value": 32},
               {"label": "Oct", "value": 15, "style": "partial", "partial_label": "parcial · al día 16"}],
      "source": "Registro de sanciones SUSESO capturado por Alicanto",
      "note_refs": ["n4"]
    }
  ],
  "essay": {
    "facts":   {"heading": "Qué pasó", "paragraphs": ["La baja es pareja entre seguros, sexo y sector. … techo bruto de más de $85 mil millones en subsidios,[^n5] …"]},
    "reading": {"heading": "Lectura Alicanto", "paragraphs": ["Para quien paga el subsidio, la cifra que importa son los días … en torno a 22%.[^n1]", "…", "…"]}
  },                                               // facts + reading: 150–250 palabras en total
  "watch": [                                       // opcional, 0–3; si hay menos de 2 válidos, no se muestra
    {"headline": "Cifras de licencias de octubre a diciembre.",
     "explanation": "Si vuelven a superar a las del mismo mes de 2025, el efecto del control habría tocado piso y el ahorro de 2026 no se repetiría."}
  ],
  "notes": [
    {"id": "n1", "kind": "estimate",   "text": "Estimación Alicanto: 0,877 × 0,891 ≈ 0,78. …"},
    {"id": "n2", "kind": "causality",  "text": "La coincidencia entre fiscalización y menor emisión es temporal; …"},
    {"id": "n3", "kind": "press",      "text": "El vínculo entre gasto en licencias y precio de planes proviene de prensa, …"},
    {"id": "n4", "kind": "coverage",   "text": "El registro es una ventana móvil de 90 días. …"},
    {"id": "n5", "kind": "non_final",  "text": "Las licencias observadas por fiscalización no son resoluciones firmes; …"}
  ],
  "reading_time_min": 2                            // calculado: palabras / 200
}
```

`sources[]` se mantiene; se puede agregar `sources[].short_role` (≤ 6 palabras) para la lista compacta.

**Reglas nuevas para el validador / gate editorial** (`editorial_approved` → PASS solo si):
1. `essay.facts` no contiene marcadores de inferencia ("sugiere", "podría", "estimamos", "Alicanto"); `essay.reading` no contiene el prefijo "Hecho:".
2. Todo `[^nX]` del ensayo, de `charts[].note_refs` y de `estimates[].note_ref` existe en `notes`, y toda nota se usa al menos una vez.
3. Cada número del ensayo existe en `key_figures`, en `charts[].rows` o en `estimates` (trazabilidad). Además, se emite una advertencia (no un bloqueo) si un número de `charts[].rows` se repite en `essay.facts` (redundancia con el gráfico).
4. El conteo de palabras de `essay` está entre 150 y 250; `dek` ≤ 40; `headline` ≤ 140 caracteres.
5. `watch[].explanation` es obligatorio (≥ 12 palabras), y un ID normativo (Circular, DS, art.) solo se acepta si la misma explicación describe la regla en lenguaje llano.
6. Las filas `style: "partial"` requieren `partial_label`.

**Cambio de render** (fuera de este folder, para el PR de implementación): `renderWeeklyDetail` debe renderizar `headline → dek → charts (grid 2 col ≥ 820 px) → essay.facts → essay.reading → watch → notes → sources`. `insightChart` gana el modo `paired_bars` con columna delta y titular/subtítulo. Para la transición conviene mantener un fallback al esquema actual.
