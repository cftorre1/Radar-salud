# Veredicto final independiente · delta revisado

**PASS SCOPED — handoff documental.** Releí la sección final de persistencia/migración y la ficha Pulso modificada. Los tres hallazgos P1 iniciales quedan cerrados en especificación; no se acredita implementación ni ejecución de QA.

- IndexedDB transaccional sustituye la alternativa insegura de read-modify-write. El contrato define tombstones, marcador y datos en una transacción, precedencia v3, notificaciones y límite explícito para bundles antiguos. La sección final declara su autoridad sobre las alternativas del anexo.
- La separación weekly/base ahora adopta una decisión explícita de producto: preservar el estado visible anterior marcando ambas leídas cuando el legado era compartido, con provenance `legacy_shared_read`, sin asegurar que ambas se leyeron. Es una alternativa admisible a mi propuesta conservadora inicial; la ambigüedad queda reconocida, estados específicos prevalecen y mutaciones futuras son independientes.
- Pulso separa correctamente la procedencia del incremento sectorial y la asignación publicada en partidas de la Cámara.

Riesgos residuales no bloqueantes: el Builder debe demostrar la serialización, reversión durante migración, identidad estable dentro de edición y recepción de notificaciones; las estimaciones de tiempo no certifican viabilidad ya probada. Las antiguas opciones de persistencia del anexo son subordinadas, no otra implementación autorizada. Mantengo los límites de revisión del informe original: no QA browser ni auditoría independiente completa de nueve fuentes o de Félix Bulnes.

El PASS no autoriza publicación de señales, merge, activación recurrente de fuentes ni beta. El informe inicial siguiente se conserva como historial; su REVISE queda sustituido por este dictamen.

---

# Work5 · Revisión independiente adversarial

Dictamen: **REVISE acotado antes de entregar como contrato ejecutable**. No es rechazo de la dirección de producto ni evaluación de implementación. Revisé el handoff completo, rutas/identidad/estado de `web/app.js` y `web/global.js`, esquema y gates editoriales, y originales actuales UC CHRISTUS y Pulso. No ejecuté QA browser ni revalidé toda la matriz de nueve fuentes.

## Correcciones requeridas

1. **P1 · Estado compartido: eliminar alternativa insegura.** Anexo A permite read-modify-write del snapshot con eventos. localStorage no aporta transacción entre get/set: dos pestañas pueden leer el mismo snapshot y perder una actualización aun recargando antes de escribir. Elegir registro por identidad como contrato mínimo; guardar explícitamente false para reversión, con precedencia sobre legacy. Migración idempotente sólo cuando no existe valor v3, marca de completitud escrita después de importación. Tests de carrera controlada y refresh después de revertir. Definir si pestañas abiertas con bundle viejo requieren recarga; no prometer convivencia completa sin implementarla.

2. **P1 · Migración Insight/noticia tiene ambigüedad irreversible.** El código `specials()` comparte ID de primera noticia con igual URL para weekly. El nuevo contrato correctamente separa piezas, pero no define qué hacer con un read legacy compartido que no permite saber cuál se abrió. Declarar una política: conservar lectura de noticia y dejar Insight pendiente cuando no existe evidencia inequívoca de lectura propia; conservar legacy `weekly:<id>` cuando exista. No copiar automáticamente el bit a ambas piezas. Usar identidad explícita de weekly y relación de evento, nunca fecha o URL dinámica sola. Documentar que un Insight puede reaparecer una vez por separación auditada de identidad; no llamarlo pérdida de lectura por cambio de copy.

3. **P1 · Pulso: corregir atribución de $18,4 billones.** La ficha propuesta agrupa monto y 4,7% como si ambos procedieran de la minuta. El original atribuye monto a partidas en página de Cámara (párrafo bajo introducción) y variación a minuta (sección Las cifras de expansión). Cambiar a: “La minuta sitúa el aumento de Salud en 4,7% frente a esa última base. Pulso informa además una asignación de $18,4 billones, según las partidas publicadas por la Cámara.” Cifras y denominadores restantes sí coinciden con el cuerpo revisado; no acredité DIPRES independientemente.

## Mejoras no bloqueantes

- Hacer explícito que gates determinísticos no detectan semántica por sí solos: prueba de paráfrasis usa receipt de revisión/fixture etiquetado, no regex universal. B1 de 3–4h parece viable como contrato/compatibilidad/gating por receipt; no como sistema autónomo de juicio semántico. Si no cabe, entregar scaffold y HOLD, sin marcar gate semántico resuelto.
- El presupuesto suma hasta20h y está acotado. Los pilotos están sujetos a permisos y no hay cron autorizado: correcto. Evitar que “IMPLEMENTAR AHORA” se lea como conector recurrente activado; aclaración ya presente.
- Encabezado anexo A dice no QA browser, mientras cierre añade revisión raíz desktop. No es falsedad si se conserva atribución, pero puede simplificarse: “Análisis inicial estático; evidencia desktop adicional al final”.

## Evidencia y aspectos que pasan revisión de alcance

- UC CHRISTUS contingencias confirma cierre de San Carlos y El Alba, servicios afectados, reagendamiento y alternativas. Fuente dinámica sin fecha: handoff no inventa fecha editorial. https://www.ucchristus.cl/contingencias (leído12oct2026, sección Información importante para nuestros pacientes).
- Pulso original confirma las tres bases de comparación y diferencia entre gasto global y Salud. https://www.latercera.com/pulso/noticia/presupuesto-2027-minuta-politica-del-gobierno-reporta-alza-del-gasto-distinta-de-la-informada/ (leído12oct2026, publicado6oct2026, secciones introducción/Las cifras de expansión).
- No se certifica móvil, operación de nuevos colectores ni licencias comerciales desconocidas; no presenta checks históricos como ejecutados por Work5.
- No propone publicar señales ni merge; conserva separación documental, versión/evidencia y decisión Commander.
- Las tres correcciones propuestas incorporan información incremental. No repito validación completa Félix ni los nueve sitios: permanecen sustentados por investigación de sus autores, sin PASS independiente de esos originales en esta revisión.

Con los tres P1 corregidos: **PASS scoped del handoff documental**, sujeto a lectura del delta, sin aprobar implementación, publicación o beta.
