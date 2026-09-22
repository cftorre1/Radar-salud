# Radar Salud V2

**Core:** DISCOVER · WATCH · CONNECT · TREND · BENCHMARK · ASK

Radar Salud V2 is a market-intelligence engine: it observes public signals, structures them, connects related events and detects emerging patterns before they become obvious.

See `docs/PRODUCT_SCOPE_V2.md`, `docs/SERVICES_V2_DRAFT.md` and `docs/SOURCES_V2_DRAFT.md`.

---

Motor mínimo para convertir fuentes públicas en `Signals`, asignar relevancia/confianza y decidir distribución.

## Decisiones de producto ya incorporadas

- Web = base de conocimiento y archivo.
- WhatsApp = canal de consumo.
- FREE: resumen semanal.
- PRO: resumen diario, una sola entrega normal por día.
- WATCH: puede romper la regla y enviar una alerta inmediata solo si el usuario sigue explícitamente ese tema.
- Futuro: contribuciones de usuarios estilo Waze, con reputación + verificación antes de publicar.
- Categorías V1 incluyen salud laboral, mutualidades/SUSESO/COMPIN e Innovación & Startups.

## Estructura

- `sql/001_schema.sql`: esquema PostgreSQL/Supabase.
- `src/radar_salud/models.py`: modelo Signal.
- `src/radar_salud/scoring.py`: Radar Score y confidence gates.
- `src/radar_salud/distribution.py`: reglas Free/Pro/Watch.
- `src/radar_salud/sources.py`: carga del registry de fuentes.
- `src/radar_salud/pipeline.py`: pipeline RawItem -> Signal.
- `src/radar_salud/cli.py`: demo local.
- `config/sources.json`: registry inicial.
- `data/sample_raw_items.json`: fixtures sintéticos para probar el motor.
- `tests/test_scoring.py`: pruebas básicas.

## Ejecutar demo

Desde la carpeta del proyecto:

```bash
python -m src.radar_salud.cli
```

## Qué hace hoy

1. Lee ítems crudos de ejemplo.
2. Los normaliza.
3. Calcula relevancia y confianza.
4. Decide si van a archivo, web, Radar diario/semanal o Watch inmediato.
5. Imprime el resultado.

## Qué NO hace todavía

- scraping real;
- llamadas a LLM;
- persistencia en Supabase;
- envío real por WhatsApp;
- RAG/ASK;
- autenticación/pagos.

Eso es deliberado: primero probamos el núcleo de decisión.

## Próximo milestone

`The Machine Works`:

- 5 fuentes reales;
- detección automática;
- deduplicación;
- extracción estructurada;
- scoring;
- 1 corrida diaria;
- salida lista para WhatsApp.


## Scout #1 — Superintendencia de Salud

Se agregó un scout real para vigilar la página pública de estadísticas de la Superintendencia.

Ejecutar:

```bash
python -m src.radar_salud.scout_cli
```

El scout:
1. descarga el listado público;
2. descubre publicaciones;
3. deduplica con huella SHA-256;
4. guarda solo ítems nuevos en `data/inbox/superintendencia_new.json`;
5. mantiene estado local en `data/state/superintendencia_seen.json`.

En producción el estado pasará a PostgreSQL/Supabase.

## Circuito completo V0 — Superintendencia

El primer pipeline real ya está separado en cuatro etapas:

1. `Scout`: descubre publicaciones nuevas y deduplica.
2. `Extractor`: entra al detalle y extrae título, fecha, período actualizado, adjuntos, números y evidencia textual.
3. `Validator`: mide **confianza/evidencia**, no relevancia.
4. `Analyst`: agrega tags, audiencia, interpretación acotada y dimensiones de scoring.
5. `Signal`: calcula Radar Score y queda listo para distribución.

Archivos principales:

- `src/radar_salud/extraction.py`
- `src/radar_salud/validation.py`
- `src/radar_salud/analysis.py`
- `src/radar_salud/superintendencia_pipeline.py`
- `src/radar_salud/engine_cli.py`

### Ejecutar contra la fuente real

```bash
python -m src.radar_salud.engine_cli --limit 5
```

Para una corrida limpia:

```bash
python -m src.radar_salud.engine_cli --limit 5 --reset-state
```

Salida:

- `data/inbox/superintendencia_new.json`: publicaciones nuevas detectadas.
- `data/outbox/superintendencia_signals.json`: Signals procesados + errores de lote.

> Nota: la máquina donde ejecutes el comando debe tener salida a internet. El entorno de desarrollo de esta entrega no permite conexiones directas desde Python, por lo que la lógica web real está cubierta por fixtures/tests y la estructura de la página oficial fue verificada externamente.

### Tests

```bash
pytest -q
```

Estado actual: **10 tests** cubren scoring, distribución, discovery/dedup del Scout, extracción, validación y pipeline completo de la Superintendencia.

## Próximo hito

Después de validar una corrida real del circuito completo, el siguiente conector será **SUSESO**. La arquitectura ya permite reutilizar `RawItem`, `Signal`, scoring y distribución; solo cambian el Scout/Extractor/Analyst específicos de la fuente.

## Estado actual — SUSESO + Radar Diario

Se agregó **Scout #2: SUSESO** y un pipeline específico para publicaciones públicas de SUSESO. El sistema:

- descubre páginas/artículos públicos de SUSESO;
- ignora sistemas restringidos con login;
- extrae fecha, evidencia, adjuntos y cifras visibles;
- clasifica subtemas como regulación, accidentabilidad, enfermedades profesionales y licencias/subsidios;
- mantiene la categoría principal `Salud Laboral & Seguridad Social` mediante una regla de dominio;
- convierte el contenido en `Signal` usando el mismo motor de scoring que Superintendencia de Salud.

También se agregó `digest.py`, que genera el **Radar Diario Pro** ordenando señales por relevancia y confianza. Este digest no envía alertas inmediatas: los únicos eventos que pueden romper la regla de una comunicación diaria son los `Watch` explícitos del usuario.

Ejemplo de uso desde Python:

```python
from src.radar_salud.digest import build_daily_digest

print(build_daily_digest(signals, "2026-09-21"))
```

### Próximo hito

Conectar una tercera fuente estructuralmente distinta: **Mercado Público**. Esto permitirá probar el motor con una API, en lugar de HTML, y luego combinar Superintendencia + SUSESO + Mercado Público en un primer Radar Diario automático real.

## Estado actual — Mercado Público + Personal Relevance

Se agregó **Scout/cliente #3: Mercado Público** mediante su API oficial. El módulo:

- consulta licitaciones por fecha o código usando un ticket externo;
- filtra oportunidades relacionadas con salud;
- preserva `Oportunidades & Licitaciones` como categoría principal aunque aparezcan palabras como hospital o clínica;
- clasifica especialidades iniciales (oncología, atención domiciliaria, telemedicina, imagenología, medicamentos, laboratorio);
- valida evidencia estructurada de la API oficial.

El ticket se entrega por variable/secret y nunca se guarda en el repositorio.

También se agregó **Personal Relevance**. `Radar Score` sigue midiendo importancia global; un segundo score ordena las señales según perfil y watch tags. Perfiles demo:

- `isapre`
- `mutualidad`
- `prestador`

Ejecutar un digest demo personalizado:

```bash
python -m src.radar_salud.demo_multisource_cli --profile isapre
python -m src.radar_salud.demo_multisource_cli --profile mutualidad
```

El objetivo es que una circular SUSESO suba al primer lugar para un ejecutivo de mutualidad, mientras que una publicación de cartera Isapre suba para un ejecutivo de Isapre.

## Scout #4 — MINSAL / COMPIN

Radar incluye un scout para la sección pública de noticias de MINSAL y un pipeline que clasifica la señal por su naturaleza, no solo por la fuente:

- COMPIN / licencias / fiscalización -> Regulación & Legal o Salud Laboral & Seguridad Social.
- Infraestructura hospitalaria -> Prestadores / Infraestructura.
- Transformación digital -> Mercado / Transformación digital.
- GES -> Regulación & Legal.

Esto permite que una misma fuente alimente varias verticales sin perder urgencia ni contexto.

Ejecutar tests:

```bash
pytest -q
```

Estado actual: 23 tests.

## Radar Diario V0 (6 fuentes)

V0 contempla estas seis familias activas antes de expandir fuentes:

1. Superintendencia de Salud
2. SUSESO
3. Mercado Público
4. Minsal / COMPIN
5. Diario Financiero (`press_high_trust`, confianza base 93)
6. Reuters (`Radar Mundo`, confianza base 96)

Diario Financiero y Reuters no pierden confianza solo por no contar con una segunda fuente. La corroboración externa es un atributo separado (`corroboration_status`) que puede aumentar evidencia, pero no es requisito para tratar a prensa de alta confianza como utilizable.

### Regla de entrega

- Free: digest semanal.
- Pro: un digest diario.
- Watch: única excepción que puede generar una alerta durante el día.
- Digest diario: máximo 5 señales locales + 2 señales de `Radar Mundo`.

### Demo del mensaje diario

```bash
PYTHONPATH=src python -m radar_salud.demo_daily_v0
```

La salida de ejemplo también queda en `data/sample_daily_v0.txt`.


## Piloto web (nuevo)

La carpeta `web/` contiene una interfaz estática mínima que muestra para cada señal:

- título específico;
- `Qué pasó`;
- `Por qué importa`;
- fuente + confianza;
- enlace directo a la fuente original.

Para verla localmente:

```bash
cd web
python -m http.server 8000
```

Luego abre `http://localhost:8000`.

### Automatización diaria en la nube

`.github/workflows/daily-radar.yml` es un piloto de GitHub Actions que puede ejecutarse manualmente o de lunes a viernes. No requiere que un computador personal quede encendido.

**Importante:** hoy el workflow automatiza solamente el circuito real de Superintendencia. Las otras fuentes tienen parsers/componentes y pruebas, pero todavía no están todas conectadas a una corrida cloud real. No confundir tests locales con un servicio ya desplegado.

### Mercado Público

Para activar Mercado Público hay que solicitar el ticket oficial de API y guardarlo como secret (`MERCADO_PUBLICO_TICKET`) en el entorno cloud. El ticket no debe escribirse en el código ni compartirse públicamente.
## BENCHMARK V2 structured metrics
BENCHMARK now has its own structured-data layer instead of forcing statistics into `Signal`:

- `MetricDefinition`: canonical definition, unit, denominator, segments, comparability and caveats.
- `MetricObservation`: one sourced value for an entity, period, geography/population/segment and confidence.
- `Signal` remains the event layer; CONNECT/TREND provide context around metric changes.

See `config/benchmark_metrics_v1.json` and `docs/BENCHMARK_V2.md`.

## Editorial Quality V0.2

The public briefing is now curated rather than a raw dump of collected items:

- technical JSON-LD/schema.org contamination is cleaned and can trigger human review;
- repetitive monthly Isapre releases are grouped into one connected update on the homepage;
- stale items discovered during the first backfill are kept out of the daily front page;
- `what_happened` and `why_it_matters` are specific by release type (cartera, movilidad, FEFI/financial, GES, etc.);
- Radar Score is user-facing as `Esencial`, `Relevante` or `Contexto`;
- dates are humanized and empty Radar Mundo is hidden.

The next structured-data milestone is attachment ingestion into `MetricObservation` so BENCHMARK can say what changed, not only that a statistical release exists.

## V0.2.1 — historial persistente y rebuild editorial

- Las corridas LIVE guardan Signals en `data/history/superintendencia_signals.json`.
- La portada se reconstruye desde el historial persistente, no solo desde los ítems nuevos del día.
- Una corrida sin novedades ya no vacía la portada.
- El workflow manual incluye `rebuild=true` para reprocesar el historial visible después de cambios editoriales; las corridas programadas siguen siendo incrementales.
