# Radar Salud — Backfill 80/20

## Principio
Radar no busca cargar toda la historia desde el día uno. El objetivo es cargar primero el 20% de las fuentes y series que explican cerca del 80% del valor de DISCOVER, CONNECT, TREND y BENCHMARK.

## Regla financiera
- Presupuesto acumulado máximo antes de demostrar valor: CLP 100.000.
- Fase 1: CLP 0–20.000.
- Fase 2: acumulado <= CLP 50.000.
- Fase 3: acumulado <= CLP 100.000.
- Toda nueva carga histórica debe responder: “¿qué funcionalidad mejora con este gasto?”.

## Dos modos
- LIVE: solo novedades desde la última corrida; alimenta DISCOVER y, más adelante, WhatsApp.
- BACKFILL: carga histórica una vez por fuente/periodo. Nunca debe aparecer como noticia nueva del día.

## Orden de precarga
1. Datos estructurados oficiales: 3–5 años inicialmente; ampliar historia después si es barato y consistente.
2. Regulación oficial reciente: 12–24 meses.
3. Noticias/corporate: desde 2025, con filtros duros.
4. Talento/startups: después de validar el motor.
5. Legal/judicial histórico: solo cuando demuestre utilidad; Legal Watch puede comenzar LIVE.

## Optimización de costo
1. Hash y deduplicación antes de IA.
2. Reglas/keywords antes de IA.
3. Modelo barato para clasificación y extracción.
4. Modelos más costosos solo para señales de alto valor.
5. No generar narrativas históricas hasta que un usuario las abra o ASK las necesite.
6. Embeddings y conexiones se generan una vez y se reutilizan.
7. TREND se actualiza incrementalmente, no recalculando todo el histórico.

## Campos críticos
- event_date: cuándo ocurrió realmente.
- detected_at: cuándo Radar lo descubrió.
- ingestion_mode: LIVE o BACKFILL.

TREND usa event_date, no detected_at.
