# Decisiones de producto · 25-oct-2026

Fuente: auditoría con cuatro perspectivas expertas (editorial, negocios digitales, negocios de salud, UX/UI) y decisión de Dirección. Documento vivo de decisión: Claude Docs "Alicanto · Decisiones de producto tras la auditoría experta".

## Diagnóstico compartido
- Sin captura diaria no hay producto: primero contenido fresco y aviso público de frescura.
- El insight vigente es "noticia de la semana con comentario", no inteligencia: 0 de 165 señales tienen `connection_keys`/`trend_keys`; 0 temas Global ligados a señales locales; 163 señales con corroboración "unknown".
- `radar_score` no discrimina (59 de 67 señales de 30 días ≥ 65) y deja sin `editorial_relevance` a 25 de 34 señales SIS/SUSESO, mientras toda la prensa (107) tiene puntaje.

## Decisiones
| # | Tema | Decisión |
|---|---|---|
| 1 | Big things leídas | Salen de la portada (sin anclas); quedan en "Leídas" y en un archivo de ediciones anteriores |
| 2 | Insight | Semanal. Se parte de las 1-3 noticias más relevantes y se investiga información adicional (datos, historial, fuentes primarias, Global) hasta formar una tesis con evidencia cruzada. Requiere cobertura de fuentes suficiente |
| 3 | Estado leído | Punto solo en no leídas; no leída en negrita; leída sin marca; "Marcar no leída" como texto en la ficha |
| 4 | Vista por defecto | Pendientes con tope 30 días y separador "Nuevas desde tu última visita"; período y orden dentro de Filtrar |
| 5 | Relevancia | El puntaje no se muestra; se usa para filtrar lo que no interesa. Personalización por intereses con cuentas/PREMIUM |
| 6 | Probadita Global | Cada semana debe haber una pieza valiosa: ampliar cobertura de fuentes globales |
| 7 | Íconos por fila | Visibles, sutiles, minimalistas y autoexplicativos (fuente ↗, compartir) |
| 8 | FREE / PREMIUM | Insight gratis en beta (vitrina); PREMIUM = Watch por actor, series de datos, archivo y exportación |
| 9 | Validación | 4 semanas con ~15 ejecutivos: correo semanal manual con consentimiento; medir retorno y reenvíos; entrevistar precio y quién paga. Envío sujeto a lista aprobada por Dirección |

## Formato del insight estratégico
Tesis en una frase · 3-4 evidencias rotuladas (dato / hecho / inferencia) · qué la contradice · qué decisión cambia y para quién (aseguradora, prestador, farma, inversionista) · indicador a vigilar con fecha. Mínimo: tres hechos independientes de al menos dos emisores + una serie de datos o un tema Global; sin dato, se rotula hipótesis.

## Mitigaciones aceptadas
- Derechos de prensa: priorizar fuentes primarias; para prensa, titular + enlace + dato incremental propio; revisión legal antes de cobrar.
- Datos personales: publicar sanciones a nivel institucional o con resolución firme; no nombrar profesionales sin respaldo firme.
- Exactitud normativa: ficha con ID, vigencia y enlace oficial; sin parafrasear obligaciones.
- Deduplicar por hecho ("+N fuentes").
- Lectura por dispositivo aceptada en beta; sincronización con cuentas.
- "Abrir no es leer": "Marcar no leída" a un toque en la ficha.
- Afirmar menos con más fuerza, separando dato, hecho e inferencia.

## Plan
1. Captura diaria desde `staging` + franja pública de frescura.
2. Ajustes de inicio (decisiones 1, 3, 4, 7) y merge del PR #39.
3. Deduplicación por hecho + etiqueta de segmento.
4. Relevancia por segmento (filtro interno).
5. Conexiones entre señales + Global ligado a señales locales + ampliar fuentes globales.
6. Insight v2 semanal: borrador cruzado automático, revisor independiente, aprobación de Dirección.
7. Validación con ejecutivos.
