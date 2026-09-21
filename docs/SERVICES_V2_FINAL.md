# Radar Salud V2 — servicios y taxonomía final

## Principio de producto
Radar Salud no es una colección de “radars” separados. Es un único sistema de inteligencia de mercado con seis servicios sobre la misma base de Signals:

1. **DISCOVER** — qué pasó.
2. **WATCH** — qué no quiero perderme.
3. **CONNECT** — qué señales separadas están relacionadas.
4. **TREND** — qué patrón está apareciendo y con qué fuerza.
5. **BENCHMARK** — cómo se compara la actividad pública observable entre actores o grupos.
6. **ASK** — pregúntale al mercado observado por Radar.

Todos los servicios reutilizan el mismo modelo de datos. Las “subcategorías” son filtros/tags, no productos independientes.

---

## 1. DISCOVER
### Objetivo
Detectar hechos nuevos, verificables y potencialmente relevantes.

### Familias de señal
- **REGULACION_Y_POLITICA** — circulares, oficios, resoluciones, leyes, instrucciones, fiscalización, cambios de cobertura/reglas.
- **LEGAL_Y_JUDICIAL** — causas, recursos, reclamaciones, fallos, medidas cautelares, litigios con potencial impacto de mercado.
- **MERCADO_Y_CORPORATIVO** — inversiones, M&A, alianzas, resultados, nuevos negocios, expansión geográfica, propiedad.
- **PRESTADORES_Y_CAPACIDAD** — aperturas, cierres, nuevas camas/boxes/equipamiento, nuevos servicios, capacidad clínica.
- **ASEGURAMIENTO_Y_FINANCIAMIENTO** — Isapres, Fonasa, cartera, movilidad, FEFI, costos, precios, cobertura, financiamiento.
- **SALUD_LABORAL_Y_SEGURIDAD_SOCIAL** — mutualidades, SUSESO, ISL, COMPIN, licencias, accidentabilidad, enfermedades profesionales.
- **OPORTUNIDADES_Y_COMPRAS** — licitaciones, adjudicaciones, compras públicas y señales de demanda institucional.
- **INNOVACION_Y_STARTUPS** — healthtech, biotech, medtech, rondas, pilotos, startups, nuevas tecnologías/modelos.
- **TALENTO_Y_CAPACIDADES** — vacantes, clusters de contratación, ejecutivos, nuevas áreas/capacidades organizacionales.
- **DATOS_Y_EVIDENCIA** — estadísticas, encuestas, estudios, releases de datos, publicaciones académicas relevantes.
- **RADAR_MUNDO** — señales internacionales con posible implicancia para Chile/LatAm; siempre presentadas en español.

### Regla editorial mínima de una Signal
Toda Signal publicada debe responder:
- **Qué pasó**
- **Dato(s) clave(s)**
- **Por qué importa**
- **Para quién importa**
- **Fuente y enlace original**
- **Fecha**
- **Nivel de confianza**

---

## 2. WATCH
### Objetivo
Personalizar DISCOVER sin crear “radars” separados.

Un Watch es una combinación de filtros:
- entidad/institución
- tipo de institución
- evento
- tema estratégico
- tópico clínico/negocio
- geografía
- objeto regulatorio/legal
- país

### Regla de notificación
- Free: resumen semanal.
- Pro: resumen diario.
- **Solo WATCH puede generar una alerta intradía**, y solo si la Signal supera umbrales de relevancia y confianza.

---

## 3. CONNECT
### Objetivo
Transformar hechos aislados en contexto estratégico.

### Tipos de relación iniciales
- SAME_ENTITY — misma entidad.
- SAME_THEME — mismo tema estratégico.
- SAME_MARKET_MOVEMENT — señales diferentes que apuntan al mismo movimiento.
- SEQUENCE — una señal parece anteceder a otra en una secuencia temporal.
- SUPPORTS — una señal refuerza otra interpretación.
- CONTRADICTS — señales públicas que apuntan en direcciones opuestas.
- OWNERSHIP_OR_CONTROL — relación societaria/propiedad.
- SUPPLIER_CUSTOMER — relación comprador/proveedor cuando exista evidencia.
- TALENT_PLUS_TECH — contratación + inversión/adopción tecnológica.
- TENDER_PLUS_INVESTMENT — compra/licitación + inversión/capacidad.
- LEGAL_PLUS_REGULATORY — causa/fallo conectado con norma/instrucción.
- EXECUTIVE_PLUS_STRATEGY — movimiento ejecutivo conectado con nueva dirección estratégica.

### Resultado
CONNECT no afirma causalidad sin evidencia. Produce “clusters de señales” con racional y fuerza de relación.

---

## 4. TREND
### Objetivo
Detectar patrones antes de que sean obvios en el mercado.

### Estados
- **Emerging** — patrón incipiente.
- **Accelerating** — intensidad claramente creciente.
- **Established** — patrón robusto y transversal.
- **Cooling** — actividad descendente.

### Gate inicial de activación
Un candidato TREND se crea cuando, como mínimo:
- >= 5 Signals relacionadas
- >= 3 entidades distintas
- confianza media suficiente
- ventana actual significativamente distinta de la ventana previa

Estos umbrales son calibrables por familia de señal; no deben ser reglas eternas.

### Dimensiones de agregación
TREND puede detectar patrones por:
- institución específica
- tipo de institución (ej. prestadores privados)
- subsector
- región/país
- strategic theme
- event type
- combinación de los anteriores

### Prospección responsable
TREND puede generar **Prospective Signals** cuando existe un cluster consistente de evidencia, pero debe expresarlo como evidencia prospectiva, no como predicción cierta.

Ejemplo válido:
> “Se observan 5 señales consistentes con una posible expansión en oncología; aún no existe anuncio oficial.”

### Uso externo
Algunas tendencias pueden ser **TREND PUBLIC** para LinkedIn/adquisición. El detalle, evidencia, entidades y evolución queda en **TREND PRO**.

---

## 5. BENCHMARK
### Objetivo
Comparar instituciones, cohortes, territorios y períodos usando **datos públicos estructurados + Signals observables**, con definiciones métricas explícitas y trazabilidad. BENCHMARK no se limita a noticias ni emite rankings subjetivos de calidad.

### Capas
- **MetricDefinition**: define exactamente qué significa el indicador, unidad, denominador, granularidad, segmentos y caveats.
- **MetricObservation**: guarda cada valor por entidad/período/geografía/segmento/fuente.
- **Signal activity**: complementa los datos duros con inversión, expansión, talento, innovación, licitaciones y actividad legal/regulatoria.
- **CONNECT/TREND context**: ayuda a explicar por qué un indicador o actor está cambiando.

### Familias macro
- Isapres: cartera/demografía; ingresos/primas; prestaciones/uso; cobertura; SIL; GES; finanzas; planes/precios; género/equidad; prevención; judicial/regulatorio; actividad estratégica.
- Mutualidades: cobertura; siniestralidad; enfermedades profesionales; prevención; prestaciones; finanzas; eficiencia; judicial/regulatorio; actividad estratégica.
- Prestadores: precios/tarifas públicas; capacidad; oferta clínica; actividad pública; finanzas cuando existan; expansión; talento; compras/tecnología; legal/regulatorio; innovación.
- Sistema/territorio: cobertura poblacional; oferta; gasto/financiamiento; acceso; brechas; inversión y tendencias.

### Modos de comparación
- entidad vs entidad
- entidad vs cohorte
- entidad a través del tiempo
- cohorte vs cohorte
- región vs región
- país vs país (fase LatAm)

Ver `docs/BENCHMARK_V2.md` y `config/benchmark_metrics_v1.json`.

---

## 6. ASK
### Objetivo
Interrogar el conocimiento acumulado de Radar, no ofrecer un chatbot genérico.

ASK consulta:
- Signals
- Connections
- Trends
- Benchmarks
- Entities
- fuentes
- ventanas temporales
- tipos de institución
- países

### Reglas
- respuesta trazable a fuentes
- separar hechos de interpretación Radar
- reconocer ausencia de evidencia
- permitir preguntas comparativas y retrospectivas

---

## Jerarquía de inteligencia
1. **Signal** — un hecho.
2. **Connected Signal / Cluster** — dos o más hechos relacionados.
3. **Trend** — patrón multi-señal/multi-entidad.
4. **Strategic Theme** — tendencia persistente de más largo plazo.
5. **Prospective Signal** — evidencia consistente con un movimiento futuro posible.
