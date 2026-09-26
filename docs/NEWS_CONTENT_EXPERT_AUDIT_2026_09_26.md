# Auditoría experta de contenido — Home V2

Fecha: 26 de septiembre de 2026  
Snapshot inicial: `web/data/radar_today.json` vigente en `staging` al iniciar el ciclo.

> Actualización de cierre: la observación inicial sobre 29 señales históricas no auditadas quedó superada por `data/editorial_audit_90d_2026_09_26.json`. Ese segundo control cubre las 43 señales del snapshot, está unido a su SHA-256 y conserva decisiones manuales `accept/degrade/group/reject`. Ya no corresponde tratar esas 29 piezas como pendientes de auditoría.

## Alcance y método

Se revisaron 16 piezas que estaban visibles al iniciar el ciclo: las 14 señales del período inicial de 14 días y dos piezas especiales. Después del control fail-closed, Insight semanal quedó oculto por evidencia insuficiente; Home muestra actualmente 15 piezas (14 señales y Global Intelligence). Las otras 29 señales del snapshot están fuera del período inicial y no se presentan como auditadas. La matriz estructurada y el copy actual/propuesto están en `data/editorial_audit_2026_09_26.json`.

Cada pieza se evaluó con tres lentes coordinados:

1. noticia: precisión, atribución, actor + acción + consecuencia y ausencia de vaguedad;
2. negocio/salud: materialidad, proceso afectado y utilidad para una decisión ejecutiva;
3. producto digital: triage comprensible, consistencia entre “Ponte al día” y card, y sentido completo sin truncamiento.

No se consultaron fuentes externas nuevas, no se modificó el feed y no se cambió selección, ranking, fuentes ni interfaz.

## Resultado ejecutivo

- 3 piezas se conservan sin cambios: TEA/resolución 11156, Bupa y RedSalud. Global Intelligence conserva su título, pero requiere ajustar el resumen.
- 10 necesitan un título más informativo: piloto Barros Luco, consejo de eficiencia, acreditación Biobío, Eleam, propuesta APS, plan de cuidados, circulares 535/534, CLC y rabia. Algunas piezas acumulan más de una acción, por eso los totales de acciones no equivalen al total de piezas.
- 1 requiere ajustar el resumen: Global Intelligence debe mantener visible su carácter multifuente.
- 1 requiere ajustar “por qué importa”: el pulso sancionatorio debe explicitar que sus tres casos son históricos/BACKFILL y no detecciones LIVE.
- 3 requieren evidencia adicional antes de presentarse como accionables: consejo de eficiencia, plan de cuidados para personas mayores y la lectura semanal basada en una sola señal.
- 0 piezas se descartan con la evidencia actual; las tres insuficientes deben permanecer cautelosas y no elevarse a insight.

## Hallazgos prioritarios

### P0 — evitar impacto aparente sin evidencia

Los anuncios del consejo de eficiencia y del plan de cuidados no incluyen medidas, metas, presupuesto, cobertura ni plazos. El triage debe decirlo desde el título. No deben presentarse como decisiones implementadas ni como insight.

### P0 — distinguir actualidad de archivo

El Pulso de sanciones muestra tres resoluciones incorporadas desde histórico y cero detecciones LIVE. La procedencia debe permanecer visible en “por qué importa” para no convertir backfill en alerta reciente.

### P1 — completar la traducción de rótulos normativos

Home ya convierte `Circular IF/N°535` y `Circular IF/N°534` en títulos descriptivos; la matriz propone refinamientos menores para hacer explícita la obligación. `Resolución IP/N°7458` todavía llega al triage como identificador opaco y sí requiere reemplazo por actor, resultado y causa.

### P1 — atribuir afirmaciones de parte

Las declaraciones sobre saneamiento de Clínica Las Condes, la primacía regional del logro de rabia y el alcance del convenio RedSalud deben conservar atribución. La matriz propone títulos que evitan convertir afirmaciones del emisor en corroboración independiente.

### P1 — preservar categorías

La lectura semanal anterior contenía una conexión ejecutiva trazable, pero nacía de una sola señal y no alcanzaba el umbral multiseñal aprobado; queda oculta en modo fail-closed. El generador de Insight semanal permanece deshabilitado hasta implementar y probar una ruta que verifique dos señales independientes o una señal más un indicador independiente. Global Intelligence es multifuente e internacional; cualquier implicancia chilena continúa siendo hipótesis. Las noticias comunes no se renombran como insight.

## Recomendación de implementación

Preparar los cambios P0/P1 como un lote editorial separado y revisable en `staging`, usando únicamente los campos `card_what`, `card_why` y títulos derivados ya respaldados por la señal. No promover el lote a producción ni modificar reglas de selección hasta una tarea explícita de implementación.
