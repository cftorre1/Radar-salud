# Alicanto Autopilot V0.9.0 — candidato local

Estado al 23 de septiembre de 2026: implementación parcial, sin despliegue. Base auditada: `6a7f0edec3666e663ff05641f2f0a030160a3a27`.

## Resultado de la auditoría

Producción usa GitHub Pages y publica `web/`. Solo existía `main`, sin protección, y el workflow de publicación no ejecutaba tests. La corrida diaria escribía directamente en producción. El snapshot contenía 64 señales; la UI omitía Fiscalización de filtros e intereses. El conjunto inicial tenía 41 tests aprobados y 3 fallidos por expectativas antiguas de textos y agrupación.

Se verificaron una colisión real en IDs de lectura truncados, un desplazamiento de fecha por zona horaria y una comparación incorrecta de novedades contra la fecha de publicación. La cola existente estaba distribuida por fuente y no conservaba todos los RawItems pendientes de modo independiente del descubrimiento siguiente. También confundía publicaciones recientes halladas en el primer barrido con novedades LIVE.

El conector de GitHub devolvió `403 Resource not accessible by integration` al crear ramas. El navegador mostró GitHub sin sesión. No se inició autenticación, no se cambiaron permisos ni secretos y no hubo escrituras remotas exitosas.

## Arquitectura preparada

- `staging`: candidato y datos del collector. QA sin claves OpenAI.
- `main`: código elegido para producción. Se exige preview remoto exitoso del mismo SHA antes de publicar.
- `production-stable`: archivos exactos de la última publicación aceptada. Backup previo a cada deploy, restauración con comparación de bytes.
- `autopilot-state`: ledger separado. Reserva antes de ejecutar, máximo cinco intentos por día UTC; fallos y reintentos cuentan.
- Staging previsto en `/staging/`. Comparte origen y publicación GitHub Pages; no es aislamiento de infraestructura. Cada preview conserva los archivos de producción desde `production-stable`.
- Builder determinístico → servidor temporal de staging → pruebas desktop/mobile → Reviewer de solo lectura → feedback consolidado → bloqueo o candidato elegible.
- Las únicas reparaciones automáticas habilitadas regeneran reportes derivados. No hay un agente autónomo modificando código.
- La promoción automática permanece sin implementar/activada: exige primero aceptación remota y cierre del contrato funcional. El despliegue preparado desde `main` tiene gates, pero no se ha ejecutado.

## Funcionalidad incorporada localmente

Cola global persistente, deduplicación, prioridad LIVE, reintentos con espera, estados terminales, checkpoints atómicos por ítem, límites AI compartidos y corte al agotar ambos presupuestos. La primera exploración exitosa de cada fuente es BACKFILL; un marcador de exploración permite clasificar novedades LIVE desde la siguiente corrida. Fechas desconocidas se clasifican conservadoramente como BACKFILL: no se presentan como novedades LIVE. El descubrimiento de cada scout conserva su alcance existente; no se afirma cobertura exhaustiva de todo el sitio del proveedor.

Interfaz: siete días y orden reciente por defecto, cuatro señales no leídas en el resumen sin penalización por repetir fuente/tipo, ocultar tipos/ámbitos, Fiscalización, lectura sin salto, IDs completos, migración de IDs antiguos solo si no hay ambigüedad, calendario correcto en Chile, tolerancia a preferencias corruptas, foco y controles táctiles. Se añadió una sección pública sobre cobertura medida, selección y pendientes, con invitación a sugerir una fuente mediante GitHub Issues (requiere cuenta GitHub).

Dashboard de solo lectura en `web/admin/product.html`: señales, pendientes LIVE/BACKFILL, fuentes, iteraciones, tokens y diagnóstico Excel. Los datos desconocidos se muestran como no medidos. No hay autenticación administrativa ni controles de escritura en esta página pública.

Uso OpenAI: respuestas y tokens reales, caché, modelo e ID de respuesta, sin prompts ni claves. Históricos de tokens no recuperables. Costos USD nulos hasta aprobar tarifas; no se cambia pricing. Se desactivaron reintentos invisibles del SDK para respetar el contador de intentos. Un ledger de gasto corrupto bloquea llamadas.

Excel: se conserva metadata de validación del parser en Signal, se rechazan meses inválidos y encabezados con períodos duplicados; etiquetas de variaciones no afirman aumentos/caídas cuando el signo no lo respalda. Diagnóstico de metadatos descargable en CSV compatible con Excel. No equivale a una nueva revisión de los libros oficiales ni a un informe XLSX.

## Decisiones recuperadas de Signal Density

| Decisión | Estado |
| --- | --- |
| Prioridad LIVE sobre BACKFILL, conservar pendientes al faltar presupuesto | Implementada en cola local y tests |
| Límites globales existentes Luna 120/run y Terra 15/run | Conservados en workflow diario; no se aumentan presupuestos |
| Siete días y orden reciente | Implementado |
| Nuevas distintas de pendientes y BACKFILL nunca nuevo | Implementado para nuevas ingestas; histórico sin timestamp no se inventa |
| Resumen por relevancia/intereses, sin diversidad forzada | Implementado |
| Ocultar grupos desde intereses | Implementado |
| Fiscalización/SuperSalud, SUSESO estructurado, filtro DF | Conservados; Fiscalización incorporada a UI |
| Contexto relacionado separado de fuentes alternativas | Conservado |
| Lectura sin salto e intereses | Conservados y extendidos |
| Insights de movilidad/cartera/suscripciones sin adivinar esquema | Parser conservado con validaciones adicionales |
| Marca y eslogan «Encuentra lo que importa» | Conservados |
| Acuerdos completos exclusivos de V0.8.5.2 | No recuperados íntegramente; no se declara conformidad completa |

## QA realizado y pendiente

Resultado local al cierre de este bloque: **66 tests Python y 6 tests Node aprobados**. Los seis workflows pasaron parseo YAML y `git diff --check` no detectó errores de whitespace.

La revisión independiente del código detectó y permitió corregir accesos por rama incorrecta, rollback de preview, conservación exacta de archivos y discrepancias entre SHA revisado y persistencia del ledger. La publicación se empaqueta exclusivamente con los archivos que pasaron QA; se omitieron reintentos inútiles del mismo SHA tras una decisión del Reviewer. Tests locales cubren límite5 persistente, fallos, cambio de día, identidad del Reviewer, SHA, checks incompletos, consolidación, prioridad/recuperación de cola, consumo, metadata y frontend.

Las pruebas de navegador quedaron escritas para 1440×900 y 390×844. No se ejecutaron en staging remoto debido al bloqueo de escritura. Se inspeccionó la producción actual en navegador y se verificó su despliegue exitoso en GitHub; esa observación no acredita la versión candidata.

No se ejecutó rollback real, no se generaron llamadas OpenAI pagas y no se ejecutaron collectors contra todas las fuentes. La revisión editorial automatizada aplica gates existentes; no certifica exactitud semántica/legal de los documentos. Persisten riesgos previos que requieren revisión: deduplicación normativa por número sin organismo/año, pertinencia de algunas noticias DF y contenido genérico de algunos resúmenes. No se alteraron reglas editoriales estructurales para resolverlos.

## Próximos pasos cuando exista acceso

1. Habilitar escritura de Contents y Workflows para la integración sobre este repositorio, o autorizar una sesión GitHub del navegador. No compartir tokens en el chat.
2. La primera ejecución de staging crea `production-stable` y `autopilot-state` solo si la punta de `main` coincide con un despliegue exitoso. Verificar que Pages admite despliegues desde staging antes de usar el preview.
3. Publicar el candidato en `staging`; ejecutar QA y preview, examinar desktop/mobile y feedback, corregir y repetir dentro del límite.
4. Completar/reconciliar el acuerdo íntegro V0.8.5.2. Resolver hallazgos editoriales estructurales con el usuario.
5. Promover el SHA exacto de staging mediante fast-forward a main. Un squash/merge que produzca otro SHA exige revisar y previsualizar ese SHA antes de publicar.
6. Ejecutar y verificar el despliegue final y un ensayo de rollback en staging. Solo entonces evaluar habilitar la promoción autónoma.
7. Si se requiere Builder/Reviewer con IA autónomos, acordar modelo, presupuesto y autoridad de cambios antes de activar nuevas llamadas pagas.

No se deben subir archivos manualmente sobre `main` ni ejecutar reset-state. La infraestructura no está lista para activarse hasta resolver acceso, ejecutar las pruebas remotas y confirmar los gates descritos.
