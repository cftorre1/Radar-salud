# Discovery oficial de Global Intelligence

Rama `codex/global-intelligence-recurrent-20261011`, basada en staging `4ff51cf`.
Calificación aislada; ninguna integración, merge, publicación ni despliegue en staging,
main o producción. Los 14 temas curados y su exportación permanecen intactos.

## Resultado y reconciliación

Ventanas de días calendario inclusivas, con corte local Chile 2026-10-11:
30 días = 2026-09-12–2026-10-11; 90 días = 2026-07-14–2026-10-11.
El día 31/91 no se incluye. Captura, evento, vigencia, período del informe y
publicación son campos distintos.

| Fuente | Detalles verificados 30 / 90 | Control nativo observado 90 | Resultado |
| --- | --- | --- | --- |
| WHO | 84 / 241 | 241 URLs, 241 detectadas, 0 omitidas | READY_FOR_INTEGRATION, cadencia pendiente |
| PAHO | 139 / 172 contenidos únicos | 206 URLs de idioma, 206 detectadas, 0 omitidas | IMPLEMENTED_WITH_DECLARED_COVERAGE_GAPS |
| Reuters | No medible sin ruta autorizada | 8 referencias preexistentes curadas; no universo periodístico | EXTERNAL_BLOCKER_PROVEN por acceso/derechos |

Los números corresponden al [runtime 2](https://github.com/cftorre1/Radar-salud/actions/runs/38144109753).
El JSON de cada ejecución es la autoridad del corte; contiene inventario, fechas
originales, secciones, clasificación, estado, motivos, entidades y procedencia.
El CSV es una proyección para revisión. El baseline tenía WHO 2 referencias de
junio fuera de 90 días, PAHO 0 y Reuters 8; no tenía recolector periódico ni health
de estas fuentes. El nuevo circuito recuperó discovery, no tarjetas publicadas.

Recall se mide con un segundo lector de los índices oficiales, independiente del
DOM del collector, comparando conjuntos de URLs antes de deduplicar idiomas.
Es recall de las superficies declaradas/capturadas, no de toda la producción del
publisher. El denominador de artículos históricos ausentes del índice es desconocido.
La salud distingue conteos indexados, detalles verificados, ventanas 30/90,
URLs por idioma, materialidad candidata, diferidos, rechazos, errores y páginas.
`new` es delta de identidades contra la ejecución anterior, sin inferir LIVE Chile.

## WHO

Tres superficies oficiales: noticias, publicaciones y Disease Outbreak News.
Las páginas oficiales declaran APIs Sitefinity públicas; el collector deriva esos
endpoints del HTML vigente y pagina con `$top`/`$skip` hasta superar la ventana.
Las siete páginas de runtime 2 alcanzaron límites ordenados anteriores a 90 días.
No se requiere API key ni login. El RSS candidato `/rss-feeds` devolvió 404 y no
se usa para fingir continuidad.

PublicationDateAndTime y FormatedDate/FormattedDate deben concordar. DON619
publicado 08/10 conserva inicio de evento 14/05 en otro campo. DON620 fue
rechazado en runtime 1 por título; el diagnóstico vivo corroboró misma URL,
canon y fecha 10/10, con la única variación del artículo inglés en “the Russian
Federation”. La compatibilidad se limita a ese sufijo de DON, sin equivalencia
general de titulares.

WHO/PAHO comparten grupo institucional `WHO_UN_SYSTEM`; dos referencias entre
ellas no prueban corroboración independiente. La política WHO CC BY-NC-SA 3.0 IGO
requiere permiso para reproducción comercial: este circuito conserva metadata
y enlaces y exige revisión de derechos antes de preparar material publicable.
El fixture público de detalle retiene sólo H1/fecha/canonical; los cuerpos originales
son capturas de QA, no contenido del producto.

## PAHO

Noticias regionales EN/ES, filtros oficiales Chile `c[]=65` EN/ES, alertas
epidemiológicas y documentos técnicos en español. La ficha técnica de influenza
de semana epidemiológica 37 tiene publicación 25/09: la semana no sustituye la
fecha y su año permanece desconocido cuando el título no lo acredita.

Las traducciones se unen sólo cuando ambas páginas declaran enlaces recíprocos
de idioma. Se conservan todos los títulos, URLs, fechas y capturas. Fechas
discordantes dejan el grupo pendiente. El filtro Chile es ámbito taxonómico,
sin inventar un efecto local. El idioma español tiene reglas propias de ruido y
materialidad; el rango numérico es prioridad de discovery, no score editorial.

La navegación anuncia page8 como última. Pruebas HTTP200 muestran page9 con
noticias distintas (CMS 01–09/09) y page10 repitiendo page9. El collector prueba
el parámetro público observado dentro del límite de páginas y declara brecha
cuando se repite antes de llegar a julio. Los archivos Chile, alertas y técnicos
sí alcanzan límites anteriores a 90 días. La ventana regional de 90 sigue siendo
un límite inferior; no se certifica completitud histórica.

Fallos históricos 403 de Work4 no se mantienen como blocker HTTP actual:
las seis superficies y los detalles respondieron en Actions con TLS verificado.
Fallbacks evaluados: RSS oficial devuelve diez entradas recientes (30/09–09/10),
insuficientes para 90 días; once sitemaps oficiales HTTP200 sin URLs periodísticas
con indicios de fechas de la ventana actual, con muestras antiguas 2014–2024.
`lastmod` del sitemap nunca se interpreta como publicación. La búsqueda pública
está excluida por robots y no se consulta. Estas rutas no resuelven el histórico
faltante. Siguiente acción: archivo/export oficial PAHO con fechas editoriales o
aclaración del proveedor sobre el truncamiento; no extrapolar cero contenidos.

## Reuters y fallback editorial

Robots HTTP200 dice: “Collection of content, data and/or information ... through
automated means is prohibited unless you have prior written consent from Reuters”.
El wildcard declara `Disallow: /`. Abarca títulos y metadata; un sitemap listado
no concede autorización. No se consultaron noticias, archivos ni sitemaps Reuters.
El bloqueo del executor no se usa como fundamento de este veredicto.

Las páginas de servicio/licencia Reuters Agency y entrega Reuters Connect/API
fueron evaluadas: presentan contratación y solicitud de licencia, sin una ruta
abierta que otorgue permiso de automatización para Alicanto. Los términos del
portal principal respondieron 401; ese resultado no reemplaza la política explícita.
No hay entitlement o ruta configurada/documentada en repo/entorno. No se afirma
que Alicanto carezca de todo contrato fuera de estos registros. Para desbloquear
se requiere acreditar servicio, autorización escrita y alcance de uso; las
credenciales se gestionan por canal seguro, sin incluirlas en evidencia o logs.

Fallback: un editor puede aportar manualmente un enlace y una descripción original
apoyada por fuentes primarias independientes verificadas. No fetch de Reuters,
extracción automática de título/metadata, cuerpo, citas o reproducción. La referencia
queda en revisión de derechos/editorial. Las ocho referencias curadas no son un
inventario real ni un denominador de recall y se conservan sin ampliarlas.

## Frecuencia, integración y publicación

El candidato agrega discovery independiente al workflow diario existente, antes
de tests core, con timeout de seis minutos y sin clave AI. Sus resultados se
checkpointan incluso si falla core; la salud Global se remira tras los exports
core. El piloto existente corre días hábiles a 09:30 UTC. Este hook está sólo en
la rama candidata y no se ejecutó sobre staging. El workflow aislado sólo puede
escribir esta rama, no despliega y no usa modelos de pago.

El ledger exige dos capturas live completas de IDs distintos y contrato de cobertura
idéntico, separadas al menos 86400 segundos para declarar cadencia probada. Los runs
de contratos anteriores no se reutilizan para certificar superficies nuevas. Ejecuciones contiguas y replay
no satisfacen ese criterio; las ejecuciones iniciales no permiten afirmar operación
diaria. El health declara checked_at real y el momento mínimo para la próxima
validación. Las dependencias de recuperación/balance core siguen preservadas y
la exposición/publicación permanece desactivada.

Se entregan hasta diez temas candidatos de 30 días ordenados por materialidad,
sin cuota. Todos requieren consecuencia empresarial verificada, corroboración
independiente, derechos y aprobación editorial. La aplicación conserva el default
30 y máximo 10. El exporter existente sólo exporta la colección aprobada, nunca
el inventario de discovery. Cero nuevas tarjetas es el resultado correcto de esta
calificación: aún no existen análisis sustantivos aprobados para estos candidatos.
Los temas globales y sus hipótesis Chile no se convierten en señales chilenas.

## Evidencia y QA

`data/audits/global_source_recovery_2026_10_11/` conserva baseline, probes HTTP/TLS,
políticas, diagnósticos de títulos/pagers/sitemaps y runs JSON/CSV/manifest/replay.
Los manifests contienen hash, bytes, URL inicial/final, redirects, headers seguros,
User-Agent y TLS; no cookies, Authorization, credenciales o cuerpos de Reuters.
Cada redirect verifica el robots de destino. Fechas futuras, inválidas, contradictorias
o desconocidas quedan pendientes; `dateModified` no rejuvenece una publicación.

El replay usa raíz temporal y verifica cero requests, cero AI/publicaciones,
igualdad de inventario/control/selección y hashes intactos de nueve proyecciones
canónicas. QA dirigida, determinística completa, Node y browser Global desktop/mobile
quedan en los checkpoints de ejecución. El único fallo heredado reproducido en
staging `4ff51cf` exige doce actos normativos visibles cuando el snapshot tiene once;
tests/exporter/snapshot de ese frente permanecen byteidénticos. No se altera el
stock normativo para hacer pasar esta misión Global.
