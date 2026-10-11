# Diario Financiero · continuidad verificable

Worker: Codex A. Rama: `codex/df-end-to-end-20261011`. PR: [#11](https://github.com/cftorre1/Radar-salud/pull/11), base staging. Issue maestro: [#5](https://github.com/cftorre1/Radar-salud/issues/5); hallazgos DF: #6. Main/producción no se modifican.

## Completado con evidencia

- Baseline: 214 capturas de 181 URLs en la cola DF, todas sin fecha; 44 pending BACKFILL y170 rechazos genéricos. History y cola no tienen la misma naturaleza. Hay33 capturas duplicadas por título/bajada.
- Parser DF consume cXense y JSON-LD `datePublished`, conserva procedencia y fechas contradictorias y usa día Chile. No usa `dateModified`, fecha de captura ni una fecha incidental del cuerpo como publicación.
- Recuperación por URL preserva fingerprint, primera captura, intentos, motivo original y observaciones anteriores. Seen no bloquea rehidratación; decisiones editoriales precisas no se reabren. URLs ya en history no se vuelven a procesar.
- El core DF aplica el mínimo72 ya aprobado del Media Early Signal Gate. Fallos de captura, fecha, lectura o evaluación son retry, con causa específica; rechazo editorial conserva evaluación/score/umbral.
- Replay con publisher/model simulados prueba scout/parser/queue/processor reales hasta history/feed y segunda corrida idempotente. También verifica que DF-only no archive ni procese filas de otras fuentes ni renueve sus timestamps.
- Runtime real [38111768459](https://github.com/cftorre1/Radar-salud/actions/runs/38111768459) capturó214 originales, tuvo1 fallo, recuperó163 registros y realizó14 evaluaciones IA exitosas. Produjo2 filas DF. Los originales están en artefacto11691902368, ZIP SHA256 `9ca3cae1a230aeabd7a7cf8eb922d9201acde5c4b3adc13e4e4ebe4f6b9ae022`.
- La noticia de [Clínica San Carlos](https://www.df.cl/economia-y-politica/actualidad/aluvion-en-las-condes-obliga-a-cerrar-por-semanas-la-clinica-san-carlos) conservó captura10-oct22:23Z, publicación10-oct y quedó **LIVE** en history; score real72. No se inventó una fecha del incidente para lograr LIVE.
- El primer checkpoint falló por `git add data/telemetry` inexistente. La segunda corrida restauró las2 publicaciones desde sus evaluaciones pagadas y preservó el agregado fast31→45 sin repetirlas. Conserva la limitación de que el JSONL de uso por respuesta no estaba incluido en aquel artefacto.
- Ricarte Soto tiene timestamp cXense/JSON-LD7-oct frente a publicación visible8-oct04:00. `config/df_date_provenance.json` resuelve únicamente ese caso verificado usando la fecha visible, retiene ambos timestamps y no inventa la causa de la discrepancia. El cierre aún requiere revisión independiente.

## Abierto; no declarar DF cerrado

1. El texto extraído contiene recomendaciones, footer y plantillas después del artículo. Aislar el contenedor original y probar con markup real antes de aceptar nuevas decisiones. La fila general sobre catástrofe/Fiscalía debe reevaluarse: score72 pero explicación IA reconoce que no aporta una consecuencia sanitaria concreta. No fabricar diversidad con esa fila.
2. Ejecutar y revisar las últimas corridas aisladas. Las capturas tienen hora/hash originales; un replay del HTML no es un nuevo polling. Verificar publicación/rechazo de Ricarte y biometría y el resto de omisiones relevantes.
3. Reconciliación30/90 sigue parcial; seguir paginación observable hasta demostrar límites de inventario y documentar superficies no enumerables. No presentar stock interno o muestras Work3 como cobertura completa de df.cl.
4. QA general falla fuera de DF: `tests/test_web_snapshot.py:289` exige>=12 normativas y obtiene11. El mismo fallo existe en la base. No añadir tarjetas por cuota ni debilitar el test para cerrar DF.
5. Reviewer determinístico sobre snapshot recurado marca8 defectos estadísticos del boletín SIS junio2026. Data/editorial/UX pasan, estadísticas no; no equivale a Reviewer PASS.
6. QA browser local no se ejecutó: falta Chromium; los mirrors devuelven403 `Domain forbidden` de la política cloud. Los46 fallos fueron de lanzamiento, no46 regresiones de producto.
7. Gate maestro de issue5 exige merge seguro a staging, QA + Reviewer y runtime **posterior al merge**. Runtime en la rama aislada no cumple ese último gate. Mantener PR borrador e issues abiertas hasta obtener evidencia.

## Próxima acción exacta

Finalizar el checkpoint remoto en curso, hacer fetch/merge de su rama remota a la rama aislada (sin descartar estados), capturar los4 fixtures de markup real con el workflow DF y reparar el límite del cuerpo. Reutilizar evaluaciones pagadas sólo cuando el artículo y la decisión sean verificables; cualquier cambio de evidencia requiere nueva evaluación dentro de los guardrails existentes. Revisar cada resultado en `data/audits/df_reconciliation_2026_10_11.json`, actualizar queue/issue5 y volver a gates. El workflow Daily Radar original escribe staging; para este frente aislado usar exclusivamente `df-isolated-audit.yml`.

El proxy cloud bloquea df.cl y la descarga File Service; Actions sí logró acceder a originales y usar la credencial IA del repositorio. No solicitar otra credencial ni declarar que DF está externamente inaccesible en todos los entornos.
