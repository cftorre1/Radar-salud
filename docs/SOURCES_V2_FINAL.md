# Radar Salud V2 — universo de fuentes y selección MVP

## Principio
El valor de Radar aumenta por **amplitud + estructura + memoria histórica + conexión entre señales**. No necesitamos activar todas las fuentes el día 1. Separamos: MVP operativo, ampliación dentro de 60 días y producto final.

---

## MVP — Día 1 a 14: núcleo mínimo
Objetivo: obtener señales diarias útiles y probar el pipeline end-to-end.

1. **Superintendencia de Salud**
   - Circulares, oficios, resoluciones, estadísticas, cartera, movilidad, FEFI, publicaciones.
   - Clave para regulación, aseguramiento y datos.

2. **MINSAL / COMPIN (publicaciones públicas)**
   - Política, infraestructura, fiscalización, licencias, transformación del sistema público.

3. **SUSESO**
   - Circulares, dictámenes, fiscalización, estadísticas de seguridad social y salud laboral.

4. **Mercado Público / ChileCompra**
   - Licitaciones, adjudicaciones y demanda institucional.
   - API/open data; ticket cuando corresponda.

5. **Diario Financiero**
   - Fuente chilena de alta confianza para señales corporativas, inversión, M&A y mercado.
   - No se penaliza por ausencia de segunda fuente; corroboración adicional mejora confianza pero no es obligatoria.

6. **Reuters**
   - Única fuente internacional del núcleo MVP.
   - Solo señales con potencial implicancia local/regional; presentación siempre en español con link original.

---

## MVP — Día 15 a 60: fuentes necesarias para probar CONNECT/TREND
Estas son parte del MVP de 60 días, aunque no del día 1.

7. **Poder Judicial**
   - Legal Watch: causas, reclamaciones, recursos y fallos públicos relevantes.

8. **BCN / LeyChile + Diario Oficial**
   - Texto normativo, versiones y publicaciones oficiales.

9. **FONASA**
   - Cobertura, compras/modelos, datos y cambios institucionales relevantes.

10. **DEIS / datos abiertos MINSAL**
   - Capacidad, establecimientos, utilización y datos sanitarios estructurados.

11. **CASEN / Observatorio Social + CEP**
   - Tendencias de percepción, acceso, protección financiera y contexto social.

12. **CMF**
   - Hechos esenciales, información financiera/corporativa de actores cuando aplique.

13. **Career pages / ATS públicos de 10–20 actores prioritarios**
   - Prestadores, Isapres, mutualidades, healthtechs y proveedores tecnológicos.
   - Fundamental para Talent Intelligence y TREND.

14. **Newsrooms corporativos de 10–20 actores prioritarios**
   - Inversiones, alianzas, aperturas, lanzamientos, ejecutivos.

15. **Start-Up Chile**
   - Innovación y startups chilenas relevantes.

---

## Producto final — Chile
### Regulación / Gobierno
- Superintendencia de Salud
- MINSAL
- FONASA
- SUSESO
- COMPIN (fuentes públicas)
- ISP
- DEIS
- INE
- BCN / LeyChile
- Diario Oficial
- CMF
- otros reguladores/organismos relevantes según tema

### Legal
- Poder Judicial
- Tribunal Constitucional cuando corresponda
- organismos administrativos con resoluciones/reclamaciones públicas

### Compras / oportunidades
- Mercado Público / ChileCompra
- compras y licitaciones sectoriales adicionales si existen fuentes públicas permitidas

### Datos / encuestas / evidencia
- CASEN / Observatorio Social
- CEP
- DEIS
- INE
- estadísticas sectoriales de Superintendencia/SUSESO/FONASA/MINSAL
- universidades y centros de investigación relevantes

### Empresas / actores
- sitios corporativos y newsrooms de Isapres
- prestadores públicos y privados
- mutualidades / ISL
- laboratorios, pharma, farmacias
- healthtech, biotech, medtech
- proveedores tecnológicos relevantes
- asociaciones gremiales

### Talento
- career pages / ATS públicos permitidos
- avisos corporativos directos
- portales públicos de empleo compatibles con automatización
- LinkedIn solo como complemento de distribución/descubrimiento; no depender de scraping

### Innovación / startups
- Start-Up Chile
- LAVCA
- LatamList
- Dealroom (según acceso/licencia)
- portfolios de VC/aceleradoras
- corporate venture / aceleradoras sectoriales

### Prensa Chile
- Diario Financiero como fuente principal
- expansión selectiva a otros medios confiables si agregan cobertura distinta

### Internacional
- Reuters como núcleo
- posteriormente fuentes especializadas de salud/negocios según valor (ej. STAT/Fierce/otros con acceso permitido)
- una fuente general adicional solo si aporta señales no cubiertas

---

## Expansión LatAm (6–8 meses)
No se hardcodean fuentes chilenas en la arquitectura. Cada source incluye country_code, source_type, access_method, trust y permisos.

Orden candidato de expansión:
1. Colombia o Perú (decidir por disponibilidad de datos y tamaño de mercado)
2. el segundo entre Colombia/Perú
3. Argentina o Uruguay
4. Brasil después, por idioma y complejidad adicional

Para cada país se replica el mismo mapa de familias:
- regulador sanitario / aseguramiento
- ministerio
- compras públicas
- justicia
- estadísticas oficiales
- prensa económica confiable
- corporate/newsrooms/careers
- startups/VC
