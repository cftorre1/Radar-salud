# Discovery oficial de Global Intelligence

Rama `codex/global-intelligence-recurrent-20261011`, basada originalmente en staging `4ff51cf` e integrada con `bc723e0` en la rama aislada.
Calificación aislada. Sin merge, activación, publicación o despliegue en staging,
main o producción. Los 14 temas curados y su exportación permanecen idénticos en bytes.

## Resultado y reconciliación

Corte Chile 2026-10-11, ventanas de días calendario inclusivas:
30 días = 2026-09-12–2026-10-11; 90 días = 2026-07-14–2026-10-11.
Fecha de publicación, captura, evento, vigencia y período estadístico son campos distintos.

| Fuente | Detalles únicos verificados 30 / 90 | Control nativo observado 90 | Outcome |
| --- | --- | --- | --- |
| WHO | 84 / 241 | 241 URLs, 241 detectadas, 0 omitidas | READY_FOR_INTEGRATION |
| PAHO | 185 / 530 | 673 URLs, 673 detectadas, 0 omitidas | READY_FOR_INTEGRATION |
| Reuters | No medible sin ruta autorizada | 8 referencias curadas preexistentes; no universo periodístico | EXTERNAL_BLOCKER_PROVEN por permiso/licencia |

Evidencia de corte: [runtime 38153425336](https://github.com/cftorre1/Radar-salud/actions/runs/38153425336),
`data/audits/global_source_recovery_2026_10_11/runs/38153425336/inventory.json` y capture_manifest originales. La metadata final está en
`data/audits/global_source_recovery_2026_10_11/runs/38153425336/coverage_requalification/38156977778/inventory.json` y `data/audits/global_source_recovery_2026_10_11/runs/38153425336/coverage_requalification/38156977778/inventory.csv`; conserva el origen de cada campo. Cada fila conserva URL, título,
fecha original, sección, tipo/materialidad candidata, estado, motivo, entidades y receipts.
WHO indexado 30/90: 84/241 identidades; PAHO indexado: 185/530 identidades tras unir traducciones.
WHO candidatos materiales verificados en 90 días: 148, rechazado 4, diferido 237;
PAHO candidatos materiales verificados en 90 días: 229, rechazado 14, diferido 516.
Los conteos verificados excluyen detalles inaccesibles y fechas no acreditadas.

El baseline tenía WHO dos referencias de junio fuera de 90 días, PAHO cero y Reuters
ocho. La recuperación de PAHO frente al archivo sin filtro añadió 358 identidades,
46 dentro de 30 días y 152 potencialmente materiales. WHO recuperó la verificación
de 63 detalles que habían recibido 429; las identidades ya estaban indexadas.

El baseline no tenía discovery recurrente para estas fuentes. Se recupera descubrimiento
de candidatos, sin atribuirles publicación o impacto empresarial probado. `new` mide
identidades ausentes del inventario anterior; no implica una señal LIVE chilena.

El denominador de recall viene de un segundo lector independiente de los índices
oficiales, antes de unir idiomas. Se mide recall de superficies declaradas/capturadas,
no toda la producción del publisher. Un recall observado de 1.0 no resuelve un archivo
truncado, una fecha contradictoria o un detalle bloqueado. Ambas ventanas quedan completas para las superficies declaradas WHO y PAHO.

## WHO

Noticias, publicaciones y Disease Outbreak News, con APIs Sitefinity públicas
derivadas del HTML oficial vigente. Paginación `$top`/`$skip` hasta límites anteriores
a 90 días. No API key/login. El candidato RSS `/rss-feeds` respondió 404.
PublicationDateAndTime y FormatedDate/FormattedDate deben concordar. DON619 publicado
08/10 conserva el inicio de evento 14/05 separado. DON620 tiene URL/canonical/fecha
10/10 concordantes; sólo se admite la variación del artículo inglés en el sufijo
"the Russian Federation", sin relajar equivalencia general de titulares.

El runtime 38145510005 recibió 63 respuestas 429 en detalles. El primer Retry-After
3600, observado 2026-10-11T14:02:51.835710Z, impuso cooldown hasta 15:02:51.835710Z.
Ese collector anterior continuó solicitudes: se corrigió con bloqueo serial,
circuito persistente por origen y pruebas de cola/redirect. El collector vigente
se detiene en el primer 429, conserva su evidencia y continúa otro publisher.
No rota identidad/IP, no reintenta dentro del plazo y no evade WAF. El resultado
actual conserva 0 fallos técnicos y checked_at
`2026-10-11T16:07:31.827873+00:00`; la salud no borra una degradación por haber respondido el índice.

WHO/PAHO comparten `WHO_UN_SYSTEM`: no son corroboración independiente entre sí.
La licencia WHO CC BY-NC-SA 3.0 IGO requiere permiso para reproducción comercial.
Sólo metadata/enlaces en el producto; derechos/editorial son gates previos a cualquier publicación.
Los fixtures públicos de detalle contienen sólo H1/fecha/canonical. Cuerpos originales
son evidencia de runtime, sin reproducción en el producto.

## PAHO

Seis superficies: noticias regionales EN/ES, Chile EN/ES `c[]=65`, alertas
epidemiológicas y documentos técnicos ES. La ficha influenza semana 37 publicada
25/09 conserva el período separado y no infiere año del período a partir de captura.
El filtro Chile es ámbito taxonómico, sin inventar consecuencia local.
Traducciones sólo se unen mediante enlaces recíprocos oficiales; conservan todos
los títulos, URLs, fechas y receipts. Conflictos de fechas quedan pendientes.
Las reglas de ruido/materialidad normalizan español con acentos; prioridad de
discovery no equivale a score editorial ni aprobación de publicación. La selección
bilingüe usa la prioridad máxima de títulos oficiales verificados, conserva la
clasificación de cada miembro y deja conflictos candidate/routine pendientes.
Los miembros sin detalle o con fechas conflictivas no elevan prioridad.

El archivo sin filtro anuncia page8, devuelve filas distintas en page9 y repite
page9 en page10 antes de alcanzar julio. No acredita cobertura 30/90.
Se encontró el formulario GET público `date[min]`/`date[max]`, comprobado vivo en
diagnóstico 38146631942. El collector recorre intervalos de siete días, verifica
el eco del formulario y fechas editoriales de cada fila, solapa un día para límites
de medianoche y divide intervalos saturados. Prueba el parámetro de página observado
más allá del fin nativo observado. El cierre exige vista/formulario cerrados,
fechas comprobadas y un probe vacío posterior. Para paginadores numerados exige
nav/ul/li anidados, páginas contiguas, único activo con aria-current, todos los enlaces
ligados al mismo origen/path/rango y último índice menor que ocho; el cap en cualquier
página anterior fuerza subdivisión. Una repetición permanece incompleta.
La captura fresca retuvo el paginador terminal en la página posterior vacía:
23 particiones quedaron sin calificar en el inventario original. El HTML real
usa h4.visually-hidden#pagination-heading; fixtures EN/ES conservan su árbol
y los hashes originales. La calificación
separada exige GET n+1, finalURL idéntica, paginador íntegro/clamped n<8 idéntico
al anterior positivo, mismo rango/formulario, cero tarjetas/fechas/metadatos de
publicación, ningún otro paginador/control y texto sólo de formulario/nav.
El auditor independiente verifica cada condición sobre bytes guardados.
Preserva recibos y fechas de todas las observaciones; cualquier
contradicción deja fecha pendiente. Particiones sin visitar o que alcanzan el límite
de páginas quedan explícitamente incompletas. Nunca toma el rango solicitado como
fecha de publicación ni considera cero contenidos cuando no hay evidencia.

Los 403 históricos de Work4/executor no sustentan un blocker HTTP del publisher:
Actions recibió contenido real con TLS verificado. Fallbacks evaluados: RSS oficial
de diez entradas recientes insuficiente para 90 días; once sitemaps con 20.013 URLs
principalmente antiguas y sin indicios periodísticos actuales; `lastmod` no es fecha
de publicación. El footer enlaza el repositorio oficial `iris.paho.org`, HTTP200,
sin API/fechas de noticias en su landing; no reemplaza la reconciliación del newsroom.
La búsqueda está excluida por robots y no se solicita.

## Reuters y fallback editorial

Robots HTTP200 prohíbe colección automatizada de contenido, datos o información
sin consentimiento escrito previo de Reuters; wildcard `Disallow: /`. Abarca títulos
y metadata. No se consultaron periodismo, archivos, feeds ni sitemaps Reuters.
El CONNECT403 del executor no fundamenta el bloqueo. Las páginas oficiales Reuters
Agency/Connect/API describen contratación/licencia; no conceden ruta abierta para
Alicanto. Los términos del portal respondieron 401, como evidencia adicional.
No hay entitlement/ruta configurada o documentada en repo/entorno; no se afirma
ausencia de contratos fuera de estos registros. Desbloqueo: acreditar servicio,
consentimiento y alcance comercial; credenciales por canal seguro, nunca en logs.

Fallback editorial: un editor aporta manualmente enlace y descripción original
apoyada por fuentes primarias independientes verificadas. Sin fetch de Reuters ni
extracción automática de títulos, metadata, cuerpo o citas. Revisión de derechos
y editorial obligatoria. Las ocho referencias curadas no son un inventario ni recall.
`data/audits/w4_reuters_2026_10_11.json` contiene policy y rutas evaluadas.

## Frecuencia e integración

El hook candidato Global corre después de core, con `always`, límite de 50 minutos y sin
clave AI; checkpoint incluso si core falla. Sólo actualiza sus tres filas de source health,
sin alterar cobertura LIVE Chile. El job permite 95 minutos; la frecuencia existente es
días hábiles a las 09:30 UTC. Este hook no se ejecutó en staging y no activa fuentes en producción.
La calificación aislada tiene ramas de escritura restringidas y cero modelos pagados.

Cadencia probada requiere dos capturas live **completas y frescas**, IDs distintos,
contrato idéntico y al menos 86.400 segundos. Ledger registra modo/reutilización;
legacy sin esos campos, resume de campaña y replay no prueban cadencia. Reutilizar
bytes exige identidad/hash/TLS/UA y edad máxima de una hora al cargar y usar contenido.
Los timestamps originales se conservan; una ejecución nueva no rejuvenece la evidencia.
WHO/PAHO recurrent_operation_proven siguen falsos hasta satisfacer esa prueba.
WHO conserva su anchor fresco bajo contrato 2. PAHO cambió a contrato 4: la proyección
no cuenta como primera captura fresca completa. Requiere una primera live completa
bajo contrato 4 y después otra distinta al menos 24 h más tarde; el timestamp next_cadence
no garantiza aceptación. Las dependencias core recuperación/balance continúan
preservadas y no aceptadas aquí.

Default de 30 días, máximo 10 temas por materialidad, sin cuota. Cero nuevas tarjetas:
discovery no incluye análisis sustantivo aprobado; todos los candidatos requieren
consecuencia empresarial acreditada, corroboración independiente, derechos y aprobación
editorial. El exporter sólo exporta la colección aprobada. Hipótesis Chile permanece
separada de hechos globales y de señales chilenas.

## QA y evidencia durable

Manifest: URL inicial/final, redirects, HTTP, headers seguros, hash/bytes, UA y TLS.
Cada redirect verifica robots/cooldown del destino. No cookies, Authorization,
credenciales o cuerpos periodísticos Reuters. Fechas inválidas, futuras, contradictorias
o desconocidas quedan pendientes; `dateModified` no rejuvenece publicación.

QA dirigida 184 PASS + 94 subcasos; Python determinístico
1178 PASS y 0 fallos en Actions sobre el candidato integrado con `bc723e08200ada1cfb0146c6ce6da0d6f1ad11af`;
Node 43 PASS; Global desktop/mobile
12 PASS. La suite excluye el runtime vivo beta ajeno.
El fallo histórico de Normativa fue corregido upstream. Los dos fallos locales de hashes del PDF de IST se reprodujeron aisladamente con
test/audit/PDF idénticos a bc723e0 y pypdf6.10. En Actions la suite completa pasa;
no se afirman fallos allí. No hay regresiones de Global ni cambios a ese frente.
Los cuatro fallos browser del baseline incluyen el supuesto de inclusión en el
teaser de diez temas y encabezados research ausentes del renderer Lite intacto.
Se verifica el comportamiento real de lectura/filtros/fuentes/hechos/hipótesis y el
grupo Global separado de cobertura Chile. No se certifica una UI research más amplia.

Replay PASS, cero red/AI/publicaciones y diez hashes canónicos intactos;
auditor independiente de bytes PASS, sin imports
del collector ni red, verifica índice/control, detalles, alias, fechas, particiones,
HTTP/TLS/robots/redirect/hash. Reviewer: `PASS_SCOPED_WITH_OPERATIONAL_HOLDS` con límites operacionales
explícitos. Evidencia `data/audits/global_source_recovery_2026_10_11/runs/38153425336/` y `reviewer_final.json`; outcomes por fuente en
`data/audits/w4_who_2026_10_11.json`, `w4_paho_2026_10_11.json`, `w4_reuters_2026_10_11.json`.
La recalificación posterior usa cero red, modo `projection_replay`,
inventario original y ledger intactos, y reporte before/after en
`data/audits/global_source_recovery_2026_10_11/runs/38153425336/metadata_requalification/38155456354/inventory.json`. La calificación
final de cobertura está en `data/audits/global_source_recovery_2026_10_11/runs/38153425336/coverage_requalification/38156977778/inventory.json`
y su report.json, sin cambiar identidades/fechas/counts; preserva también la QA
de metadata en `data/audits/global_source_recovery_2026_10_11/runs/38153425336/metadata_qa/38155456354/`. No prueba otra
captura ni cadencia. QA final: [run 38156977778](https://github.com/cftorre1/Radar-salud/actions/runs/38156977778);
la calificación fresca original conserva sus cuatro reportes en `data/audits/global_source_recovery_2026_10_11/runs/38153425336/fresh_qa/`.
Queue sólo actualiza esas tres tareas. PMO conserva Global Implementado, sin promoción.
