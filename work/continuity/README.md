# Continuidad de autonomía — 11 de octubre de 2026

**Infraestructura publicada y activa. Aceptación de cuatro horas: NO DEMOSTRADA.**
La excepción del owner autoriza este paquete de autonomía en `main`; no autoriza
producto, promoción desde staging, QA debilitado, nuevos secretos ni gasto.
El código verificado es `720af52a7e652adcd34afabb43dd609d154f5ca2`: 361 tests
PASS y actionlint 1.7.7 PASS sobre los cinco workflows. El primer pickup durable
ocurrió el `2026-10-11T05:29:46.231497Z`; publicar una corrección no reinicia
ese reloj ni convierte el tiempo transcurrido en progreso útil. El evaluador
conserva toda la historia y comprueba la última ventana real de cuatro horas;
exige trabajo, cobertura y todos los gates dentro de esa misma ventana.

La autoridad ejecutable es `autopilot-state:data/autopilot/control_v2.json`.
La queue aprobada y sus dependencias provienen de staging. El observer publica
proyecciones de queue/PMO y conserva referencias y evidencias inmutables.
Los datos de este directorio son snapshots verificables; no sustituyen esa
autoridad ni conceden aceptación. El commit que contiene este README es el
checkpoint documental; el checkpoint de código citado arriba ya fue publicado.

El último plan de la octava publicación, `6ba8a53b`, conservó 63 eventos raw y
26 pickups, y corrigió el crédito del retry QA equivalente: 55 efectivos, ocho
correcciones y doce transiciones. El observer `0e1cd350` retuvo el mismo control.
Las quince referencias inmutables fueron verificadas; ningún evento anterior al
primer pickup ni cada evento histórico efectivo se certifica automáticamente
como progreso útil. La reconciliación v2 de queue/PMO/ledger quedó en staging
`4ff51cfe`, mediante CAS sobre el parent fresco `eb7e0463`, preservando cambios
concurrentes, 82 tareas ajenas, Work3, gates, producto y evidencia anterior.

El snapshot de la octava publicación ya contiene un gap material de 7.641
segundos, superior al máximo de treinta minutos.
Haber pasado cuatro horas desde el pickup no satisface la aceptación. El snapshot
completo de Actions a las 09:15:32Z no observa entregas del controller nuevo por
schedule; la causa sigue indeterminada. No existe un canal completo confiable de
eventos del owner en las herramientas disponibles, por lo que el conteo permanece
desconocido. Los blockers y la intervención mínima exacta están en la verificación
JSON y en las instrucciones de continuidad siguientes.

Después de la reconciliación v2, preview `38128983053` retuvo `11 >= 12`.
Recovery `38129022561` despachó worker `38129027112`, cuyo resultado inmutable
fue BLOCKED, sin mutación ni candidato. El presupuesto lógico compartido pasó
de dos a tres intentos; no se reinició por el nuevo run ID. Controller
`38129022812` terminó a las 09:40:31Z. El estado posterior `695a7d67` conserva
raw63/efectivos55/correcciones8/transiciones12, con 27 pickups y cero leases
activos. No agregó eventos materiales ni crédito de blocker/transición. Este
resultado posterior está separado del snapshot inmutable de la octava publicación.
El snapshot final leído a las 09:46:17.848619Z es `641a8963`: incorpora metadata
posterior con esa misma proyección. Conserva los pending transitions, los relojes
materiales previos de cada familia, toda la historia y los bindings. Los hashes
del reporte del worker y del delta posterior están incorporados en hosted-evidence.

## Evidencia y límites

- `hosted-evidence.json`: ejecuciones reales, tareas, leases, heartbeats,
  transiciones y corrección append-only del crédito material duplicado.
- `recovery-before-after.json`: recovery anterior con diff corrupto y carrera
  de estado frente a dispatch por familia, reproducción y escalamiento acotado.
  Incluye reparación real del transporte que truncaba JSON de SUSESO.
- `canary-proof.json`: STALLED, nueva generación y rechazo del worker vencido
  tras 183.402066 segundos reales. Es fault injection separado; no cuenta como
  trabajo útil, fuente LIVE, cierre de producto ni aceptación de cuatro horas.
- `learning-ledger-receipt.json`: aprendizaje durable por CAS; no cuenta como
  progreso material. `artifact-manifest.json` permite verificar hashes y tamaños.
- `docs/AUTONOMY_VERIFICATION_2026_10_11.json` conserva las validaciones iniciales
  de 193 tests, las revisiones intermedias de 244, 259, 316, 330, 336 y 338,
  el candidato de 351 cuya publicación se retuvo por un defecto independiente,
  y la validación final de 361.

Los hashes de tokens permiten comparar owners sin publicar capacidades de lease.
La historia raw permanece intacta. Sólo una corrección válida, ligada por hashes
a los eventos originales y al problema/producto demostrados, retira un crédito
duplicado de la proyección efectiva. SUCCESS, dispatch, pickup aislado, heartbeat,
generación de un plan, reporte del observer y este checkpoint no son progreso material.
La prueba histórica de producto sólo se importa verificando commits, parent,
eventos y resultados inmutables reales. El importer no supone que el producto
actual fue el de un evento antiguo; tampoco modifica leases o la historia raw.

La evidencia conserva el fallo real `assert 11 >= 12`. No existe aquí una mutación
de producto ni un cierre de fuente verificado. Los bloqueos permiten continuar
otras familias; los mismos inputs no abren un loop de auditorías idénticas.
El nuevo intento hosted ACHS corrigió la URI dentro del candidato, pero el gate
LIVE siguió fallando: ambos intentos hicieron rollback, sin changed_paths ni
crédito de mutación. La fiscalización y medios terminaron sin crédito repetido
mientras public data y QA conservaron sus ejecuciones independientes.
Los dos créditos posteriores de diagnóstico UNSUPPORTED se identificaron como
inválidos. La quinta observación los retiró por corrección append-only: raw62 intactos,
55 efectivos y siete correcciones en el primer plan hosted `a703892e`, verificado
con sus ocho referencias inmutables. El observer `a7495354` conservó el control;
repair y candidate quedaron SKIPPED sin nuevos claims porque los inputs seguían
iguales. Estos números pertenecen a esa observación histórica. Los 30 eventos anteriores al primer pickup no se convierten en
progreso de la ventana observada. Las doce transiciones y la evidencia real ACHS
permanecen. La autoridad material es la identidad canónica del engine; el hash
diagnóstico del producer no puede esconder una aserción nueva.
Una última reproducción encontró además que la clasificación INCOMPLETE omitía
todo recovery. `fc03cfb` restringe esa omisión al diagnóstico redundante exacto:
aserciones, contexto, baseline, gates o ejecución adicionales siguen siendo
evidencia. El replay conserva los mismos eventos y las siete correcciones.
`15416d1` exige además que la comparación use evidencia principal independiente:
un recovery no puede corroborarse con sus propios datos anidados. Cambiar esos
datos y regenerar sus hashes sigue siendo una diferencia significativa.

## Continuar exactamente

1. Leer el head fresco de `autopilot-state`, no un remote-tracking ref antiguo.
   Comparar `material_events` raw con `effective_material_events` y sus
   `material_event_corrections`. Consultar queue/PMO/ledger en el mismo SHA.
2. Las tareas ya aprobadas autorizan trabajo reversible de fuente. El executor
   intenta primero la estrategia determinística de URI reconocida, sin patch
   previamente suministrado ni modelo pago. Un plan generado no es evidencia de
   reparación; exige preimagen, branch aislado y todos los gates existentes.
   `ai_builder_enabled=false` sigue vigente. El límite de 24 requests pertenece
   a nuestra instrumentación: agotarlo es cobertura INCOMPLETE/UNVERIFIED, no un
   fallo verificado del publisher/parser, ni evidencia de LIVE PASS.

   Para fallos que la estrategia no reconoce, el blocker es
   `executor_capability_missing`, no una supuesta falta de autorización de Toba.
   El frente responsable puede añadir una estrategia segura o aportar un plan
   exacto dentro de la tarea ya aprobada. No fabricar contenido para QA verde.
   El esquema mantiene máximo tres archivos y 24 KB de texto combinado:

   ```json
   {"schema_version":1,"replacements":[{"path":"ruta-aprobada","sha256":"hash-preimagen","old":"texto-único-existente","new":"reparación-justificada"}]}
   ```

   El runner exige una coincidencia única y todos los gates. La ausencia de
   `acceptance_artifact` impide cerrar la tarea, no comenzar una reparación
   aprobada. El artefacto se declara como
   `{"path":"ruta-relativa","sha256":"hash-del-archivo"}` y debe contener
   evidencia real ligada a task/candidate SHA, verdict PASS y requisitos completos
   de fuente, ventana 30/90, publicación/rechazo/ausencia, QA y Reviewer.
   Una eventual integración de producto en staging corresponde al frente dueño y
   a su autoridad existente; este runtime no promueve producto a main/producción.
3. Commit de esos inputs relevantes en la autoridad aprobada: schedule y triggers
   existentes reabren sólo la familia afectada. No hace falta reiniciar el owner;
   cambiar un timestamp, doc, SHA no relacionado o heartbeat no habilita retry.
   El cron declarado de diez minutos no prueba entrega real: el snapshot de runs
   `event=schedule` conservado en hosted-evidence no registra un controller nuevo
   después de publicar. Sí verifica el dispatch por push y por completion.
   La causa de entrega no está determinada; revisar GitHub si siguen faltando
   ticks. No contar la declaración ni reiniciar manualmente como prueba de pickup.
4. Proveer un export confiable e inmutable de `owner_prompt_events`, con watermark
   de completitud para la misma ventana observada y cobertura de Actions. Verificar
   origen y hashes mediante un producer conectado al observer antes de incorporar
   la observación por CAS. `autonomy_observation.build_mutation` conserva
   `NOT_PROVEN` mientras ese canal falta: una atestación escrita en control no
   conecta el canal ni valida aceptación. GitHub no ve el chat;
   arrays vacíos o `verified=true` escrito manualmente no prueban cero intervención.
5. Observar cuatro horas reales útiles, sin gaps sobre el límite de la política,
   y registrar UTC, tasks, lanes, evidence/commits, stalls, recovery y transiciones.
   Hasta entonces mantener `NOT_PROVEN`. El contrato legado Stage A conserva además
   mutación durable y reparación de fuente verificadas; escalamiento correcto es
   evidencia operacional útil y no satisface por sí solo ese contrato estricto.

Si aparece otro defecto reparable de infraestructura: reproducir, reparar dentro
del alcance, prueba dirigida, commit aislado, push fast-forward y verificar hosted.
No forzar refs, no reescribir historia, no relajar gates. La hipótesis siguiente es
que nuevos inputs reales abran sólo la familia correspondiente y produzcan una
mutación validada y transición sin prompts, conservando las demás tareas.

El bundle incremental original de 17 commits y los bundles de 35, 46, 49, 50 y 51 checkpoints
históricos y el paquete final de 54 commits fueron restaurados desde el main base con árbol exacto. Permanecen en la
continuidad local; los bundles, logs completos y capturas raw no se publican en main.
La continuidad final agrega un bundle privado completo del checkpoint documental.
