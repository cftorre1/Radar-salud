# BENCHMARK V2 — alcance funcional

## Qué es
BENCHMARK no es un ranking de noticias. Es la capa analítica de Radar Salud que combina:

1. **Datos públicos estructurados** (`MetricObservation`).
2. **Definiciones comparables y trazables** (`MetricDefinition`).
3. **Signals** para actividad estratégica observable.
4. **CONNECT/TREND** para explicar el contexto de los cambios.

## Preguntas que debe poder responder
- ¿Cómo se compara una Isapre con sus pares en cartera, gasto, cobertura, SIL, GES y finanzas?
- ¿Cómo evoluciona una mutualidad en cobertura, siniestralidad, enfermedad profesional, gasto y prevención?
- ¿Qué prestadores muestran mayor expansión, capacidad, inversión, precios públicos o actividad digital observable?
- ¿Dónde están las brechas territoriales de oferta/cobertura?
- ¿Qué actor está cambiando más rápido y qué señales públicas podrían explicarlo?

## Cinco dimensiones obligatorias
- **ENTITY** — institución, cohorte, región o sistema.
- **METRIC** — definición exacta del indicador.
- **TIME** — período comparable.
- **COHORT** — pares relevantes.
- **CONTEXT** — Signals/Connections/Trends que ayudan a interpretar.

## Macrocatálogo
### Isapres
Cartera/demografía; ingresos/primas; prestaciones/uso; cobertura financiera; SIL; GES; finanzas; planes/precios; género/equidad; prevención/acceso; judicial/regulatorio; actividad estratégica.

### Mutualidades
Cobertura; siniestralidad; enfermedad profesional; prevención; prestaciones médicas; prestaciones económicas; finanzas; eficiencia; judicial/regulatorio; actividad estratégica.

### Prestadores privados
Precios/tarifas públicas; capacidad e infraestructura; oferta clínica; actividad/volumen cuando sea pública; finanzas públicas; expansión/mercado; talento; compras/tecnología; legal/regulatorio; innovación.

### Prestadores públicos / territorio
Capacidad; acceso/producción; compras; calidad/resultados disponibles; red/territorio; brechas regionales.

## Reglas de calidad
- No comparar métricas de distinta definición bajo el mismo nombre.
- Un valor per cápita debe identificar denominador.
- Precios publicados != tarifas negociadas.
- Missing data se muestra como missing.
- Toda observación conserva fuente, período, segmento/población y confianza.
- Signals de actividad son evidencia de movimiento, no una medida automática de calidad.
