# Preflight Luna / Terra / Astra

Estado: listo para ejecución controlada, **sin llamadas ni gasto**.

La fuente de verdad es `config/model_quality_experiment_v1.json`. Congela siete casos permitidos y trazables, junto con el SHA-256 exacto de cada snapshot: informes multifuente complejos, un teaser monofuente, noticia oficial simple, lectura normativa, noticia de negocio y pulso histórico con guard LIVE. Los tres modelos reciben exactamente el mismo input, prompt y contrato JSON. Si cambia cualquiera de los hashes, el corpus debe recongelarse antes de ejecutar.

## Ejecución pendiente

1. Dirección autoriza un costo máximo total en USD y confirma los tres modelos disponibles.
2. `OPENAI_API_KEY` se entrega como secreto; nunca se registra en archivos ni artefactos.
3. Se generan tres outputs por caso y se aleatorizan como A/B/C antes de evaluar.
4. Dos evaluaciones ciegas puntúan la rúbrica; discrepancias mayores a 10 puntos se adjudican.
5. Solo después se revela el modelo y se completan tokens, costo, latencia, errores, omisiones, edición humana y publicable-sin-edición.

No hay outputs de muestra: producirlos sin API real falsearía calidad, costo y latencia.

## Regla de decisión

Un output con hecho material inventado, afirmación sin fuente o hipótesis global presentada como hecho chileno falla automáticamente. El umbral de publicación sin edición es 85/100; el caso de negocio compara calidad incremental, minutos de edición y costo por pieza publicable, no solo promedio de rúbrica.
