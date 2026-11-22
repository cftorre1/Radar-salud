# Insight del lunes 23-nov-2026: trasplantes × donación × comparación con España

Publicado en `editorial_approved.json` (formato v2, ancla 2026-11-23, vence 2026-11-30). El insight del 16-nov (partos y natalidad) quedó en `archive/2026-11-16.json`; el del 9-nov sigue como ejemplo de referencia de los tests.
Redactor: Claude (corrida programada del domingo 22-nov). Revisión independiente: subagente revisor, 3 rondas (PASS final en la ronda 3).

## Ancla estadística
`run_weekly_insight_a.py --offline --as-of 2026-11-23`: `no_stats_new_period_in_week`. Tema normal, sin `stats_anchor`.

## Tesis evaluadas (noticias del 16 al 22-nov)

| # | Tesis | Gatillante | Cruces | Resultado |
|---|---|---|---|---|
| 1 | **El récord de trasplantes que anuncia el Minsal convive con una donación baja y sin programa de donación en asistolia para órganos** | Minsal, 20-nov (602 trasplantes, 205 donantes, 2.177 en espera) | Minsal 2019 (645 trasplantes, 300 donantes), ISP vía 24horas (2.097 en espera renal y 307 trasplantados en 2025), negativa familiar 59% (Minsal vía 24horas), 11 donantes por millón (Colegio Médico vía BioBioChile), España 2025 (51,9 p.m.p., 1.416 de 2.547 en asistolia), preguntas frecuentes del Minsal (consentimiento presunto, familia, córneas) | **Elegida** |
| 2 | Centros médicos crecen 37% en 4 años | Diario Financiero, 19-nov (primer puntaje del radar) | — | Descartada: prensa de pago; solo título y bajada públicos, sin cifras abiertas para cruzar esta semana |
| 3 | Autotoma de VPH en 100 comunas desde 2027 | Minsal, 17-nov | Mortalidad por cáncer cervicouterino (Minsal) | Descartada: sin tiempo para reunir cobertura de PAP y vacunación verificables; queda como candidata |
| 4 | Trabajo pesado y minería: 2 circulares de SUSESO en consulta | SUSESO, 17 y 19-nov | — | Descartada: cambio regulatorio sin datos de impacto |
| 5 | Partida 16 y hormonización cruzada | Senado 18-nov, Minsal 22-nov | — | Descartada: debate valórico sin cifras de mercado ni presupuesto atribuibles |

Temas de las últimas 4 semanas: natalidad (16-nov), residencias (9-nov), sarampión (2-nov), licencias (23-oct). Trasplantes no se repite.

Por qué la 1: es un hecho oficial de la semana con lectura no obvia. El récord que anuncia el Minsal no se concilia con los 645 trasplantes que el mismo ministerio informó para 2019; la lista sigue en 2.177 personas; y la diferencia con España no es solo de tasa (11 contra 51,9 por millón) sino de vía: en España el 55,6% de los donantes fallecidos de 2025 fue en asistolia, y en Chile esa vía solo existe para córneas.

## Titular (3 candidatos, revisor ciego)
Pares puntuados por precisión, claridad, novedad y largo: corto con contraste 15/20; hecho + tensión 12/20; consecuencia de negocio 12/20 (causalidad no probada en «la donación pone el techo»). Ganó el corto con contraste, con el récord atribuido al Minsal.

## Verificación
`verify_candidate(weekly, candidates/2026-11-23-trasplantes-evidence.json, 2026-11-23)`: PASS sin errores ni advertencias. Ensayo de 773 palabras; bajada de una oración (27 palabras); titular de 77 caracteres. Revisión de pantalla 390×844: el primer párrafo empieza en y≈417 px.

## Revisión independiente
- Ronda 1 (FAIL): el «récord desde 2000» choca con los 645 trasplantes de 2019 del propio Minsal; «el ritmo se sostuvo», «por más pabellones» y «la espera más larga está en el riñón» sin fuente; la cifra de la lista atribuida a la ministra; bajada sin el medio. Todo corregido; se agregó la página de 2019 como fuente 6.
- Ronda 2 (PASS_WITH_CORRECTIONS): orden de la frase de 2019; salvedad sobre donantes vivos; «cambio estructural»; año no informado en la bajada; párrafo de negocio sin el récord discutido. Corregido.
- Ronda 3: PASS (detalle opcional «en la historia del país», aplicado).

## Límites conocidos
- Extractos leídos con WebFetch (el proxy bloquea curl a minsal.cl); cada extracto tiene 125 caracteres o menos.
- No se pudieron leer las fichas del Senado y la Cámara sobre proyectos de institucionalidad de trasplantes, ni la Ley 20.413 en bcn.cl (carga dinámica).
- `insights.json` y la página para compartir del 23-nov no se incluyen: los genera la exportación diaria cuando el insight entra en vigencia.
