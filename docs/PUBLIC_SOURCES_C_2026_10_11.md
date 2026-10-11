# Fuentes públicas C — FONASA, ISP y DEIS

Rama aislada: `codex/c-public-sources-20261011`. Base exacta de `staging`:
`cadb6c2d1f3c286a0dbeea3d236f6f10d47df2bb`. Sin promoción a staging, main o producción.

La ingeniería y la revisión independiente están terminadas. **Ninguna de las cinco fuentes se declara operativa**: la captura directa del motor queda bloqueada por el proxy de este entorno. El replay actual registra `Tunnel connection failed: 403 Forbidden`, antes de negociar TLS con el origen. Los probes HTTP registran `envoy / Domain forbidden`. No se atribuyen estos códigos al servidor sanitario, su certificado, su WAF ni un cambio de HTML.

## Estado por fuente

| Fuente | Captura directa actual | Alternativa oficial evaluada | Fecha y cobertura |
|---|---|---|---|
| FONASA newsroom | CONNECT 403; sin HTML primario | fonasa.cl, nuevo.fonasa.gob.cl/news, feeds/API/sitemap y rutas de documentos | Navegación también bloqueada; no fecha ni formato live verificados. Un listing vacío es error, nunca éxito implícito. |
| FONASA Datos Abiertos | CONNECT 403 en los cuatro hubs | Noticias, Biblioteca/Cuenta Pública, boletines y análisis; PDFs FONASA/fonasaweb; BGI DIPRES | DIPRES muestra material histórico 2021, sin fecha de publicación actual verificable. No se promueve a señal reciente. Fallos de cualquier hub quedan explícitos; períodos, filenames y títulos no fijan fecha. |
| ISP / ANAMED | CONNECT 403 en www.ispch.cl e ispch.cl | Dominio vigente .cl, tablas y documentos oficiales; .gob.cl, RSS/API/sitemap contrastados | El índice oficial muestra etiquetas «Alerta» y «Nota informativa», además de «Publicación ISP». El parser exige columna «Fecha Publicación», no cualquier fecha de una fila. HTML primario actual pendiente. |
| ISP Surveillance | CONNECT 403 en laboratorios y archivo respiratorio | /boletin/, /virusrespiratorios/, archivo explícito del año vigente, /documento/ y PDFs | Para semana 39, el detalle oficial indexado fecha publicación 7 octubre 2026; filename PDF contiene 06-10-2026. Se conserva la fecha del detalle. Un listing histórico del navegador no acredita captura actual. |
| DEIS | CONNECT 403 en /centrofic/ | Portal, Datos Abiertos, publicaciones, feed, Centro FIC y repositoriodeis.minsal.cl | Navegación verifica PDFs de orientaciones CIE-10: publicación 25/06/2026, aunque portada diga mayo 2026 y ruta uploads 2021/03. La actualización ENO 31/08/2026 es editorial y se excluye. Catálogos estadísticos sin fecha explícita mantienen el gap. |

Los resultados de navegación están separados de los probes de transporte. Una búsqueda indexada, un resultado cacheado o un error del gateway del navegador **no** prueba respuesta HTTP, headers, redirects o TLS del origen. Las fixtures HTML de regresión son sintéticas y se identifican como tales; no se afirma conocer el markup vivo que el proxy impidió capturar.

## Controles implementados

- Scouts estrictos conectados al Daily Radar: FONASA, ISP y `DeisDocumentScout`.
- Fecha explícita de publicación ligada al detalle, columna del listing o documento. Validación calendárica y límite de fecha con calendario de Chile; conflicto, período de datos, fecha de modificación, año de archivo o nombre del PDF no habilitan publicación.
- HTTPS y hosts oficiales permitidos; cada redirect se valida antes de solicitar su destino y se vuelve a validar la URL final. Proxy, confianza CA y verificación TLS se conservan.
- Para PDFs: descarga primaria, firma PDF, lectura, límite de tamaño, SHA256 y fecha de captura. El vínculo detalle → PDF también queda trazado.
- Los procesadores requieren evidencia y evaluación editorial. Una fecha desconocida, un PDF ilegible o una evaluación pendiente no fabrican una señal.
- `source_health` conserva causas exactas, diagnóstico por subfrente, cobertura parcial, evidencia pendiente y fecha del último motor diario separada del replay de diagnóstico. Una señal histórica no oculta una captura actual sin fechas verificables.
- El replay de diagnóstico no altera cola, seen, watermarks, historial o gasto IA. El estado backend y web se actualiza sólo para las cinco fuentes autorizadas.

## Checkpoints y QA

| Checkpoint | Commit | Evidencia |
|---|---|---|
| ISP ANAMED | `7c81a2e` | `isp_anamed_checkpoint.json` |
| FONASA newsroom | `98fcdb6` | `fonasa_newsroom_checkpoint.json` |
| DEIS | `fbc9e5e` | `deis_checkpoint.json` |
| FONASA Datos Abiertos | `03d1bd1` | `fonasa_data_checkpoint.json` |
| Fechas y transporte común | `9e1701a` | `integrity_checkpoint.json` |
| ISP vigilancia y corrección de columna ANAMED | `b61dcab` | `isp_surveillance_checkpoint.json` |

Los artefactos están en `data/audits/public_sources_c_20261011/`, con respuestas de navegación, matrices de UA/método/TLS/host y scripts de replay. El commit de integración completa las dependencias comunes y conserva cada subfrente retomable.

QA final: **112 tests dirigidos aprobados**, replay controlado del motor aprobado y Node aprobado. Suite completa: **364 aprobados, 1 omitido, 1 fallo preexistente**. El fallo `test_normative_v2_recurates_all_visible_acts_and_routes_opaque_titles_to_review` exige al menos 12 actos pero el snapshot de staging contiene 11; se reprodujo sin cambios en worktree de la base exacta. No se modificó ese contenido ajeno al alcance ni se relajó el test. El Reviewer independiente verificó ese mismo fallo y dejó ingeniería PASS con blockers externos; no certifica captura operativa ni publicación live.

## Retomar sin reconstruir contexto

1. Leer `runtime_capture.json`, `reviewer.json` y el checkpoint de la fuente.
2. Habilitar el egreso oficial mediante la configuración soportada del entorno. Hosts necesarios: `www.fonasa.gob.cl`, `fonasa.gob.cl`, `www.fonasa.cl`, `fonasa.cl`, `datosabiertos.fonasa.cl`, `www.datosabiertos.fonasa.cl`, `www.ispch.cl`, `ispch.cl`, `www.ispch.gob.cl`, `ispch.gob.cl`, `deis.minsal.cl`, `repositoriodeis.minsal.cl`. Las rutas adicionales evaluadas están en los probes por fuente.
3. Ejecutar `python scripts/check_public_sources.py --record-health`. Salida 2 significa que alguna fuente no supera captura/fecha/evidencia; no convertirla en exit 0 ni en fuente sana.
4. Capturar HTML/PDF primarios, headers y redirects desde egreso autorizado. Sustituir las fixtures sintéticas por extractos verificables donde cambie el contrato real. Para Datos Abiertos, ligar explícitamente la fecha de publicación a cada archivo antes de habilitarlo.
5. Repetir tests dirigidos y Reviewer. Usar el motor diario con su estado persistente para ingesta; el replay de diagnóstico no publica ni avanza watermarks.

El único siguiente paso externo es habilitar egreso. Este trabajo no modifica la política de red ni inicia una promoción de release.
