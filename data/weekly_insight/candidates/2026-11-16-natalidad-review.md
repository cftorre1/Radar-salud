# Insight del lunes 16-nov-2026: partos en clínicas × natalidad × fertilidad asistida

Publicado en `editorial_approved.json` (formato v2, ancla 2026-11-16, vence 2026-11-23). El insight del 9-nov (residencias) quedó en `archive/2026-11-09.json` y sigue siendo el ejemplo de referencia de los tests.
Redactor: Claude (corrida programada del domingo 15-nov). Revisión independiente: subagente revisor, 5 rondas (PASS final en la ronda 5).

**Reescritura por política de prensa de pago (CI del PR #211).** La primera versión usaba el cuerpo de la nota de Diario Financiero (67.530 → 26.217, 61,2%, RedSalud, Indisa, Alemana, cita de Santa María). `test_paywall_rights_v2_20261028` la rechazó: según `config/paywalled_press.json` (Dirección, 28-oct), de df.cl solo se usan el título y la bajada públicos. El texto final usa solo la bajada («más de un 60%» en la última década) y el título/bajada de la nota de Antofagasta; el `source_url` del insight es el INE.

## Ancla estadística
`run_weekly_insight_a.py --offline --as-of 2026-11-16`: `no_stats_new_period_in_week` (ninguna ficha nueva verificada en la semana). Tema normal, sin `stats_anchor`; `check_weekly_insight_contract.py --gate` PASS.

## Tesis evaluadas (noticias del 9 al 15-nov)

| # | Tesis | Gatillante | Cruces | Resultado |
|---|---|---|---|---|
| 1 | **Los partos en clínicas caen más rápido que los nacimientos; las clínicas giran a fertilidad, que el Estado casi no financia** | Diario Financiero, 12-nov (cifras de Clínicas de Chile) | INE estadísticas vitales 2025 (146.446, TGF 0,99), Anuario INE 2015 (244.670), series Isapre SIS (3.410.487 → 2.517.305), CIPER (10.500 ciclos, 15 prestadores PAD en 5 regiones), Comisión de Salud del Senado (580 de 9.000 ciclos con financiamiento estatal), Plan Chile Renace (eje salud reproductiva, propuesta a comienzos de 2027), cierre de maternidad en Antofagasta | **Elegida** |
| 2 | Isapres rechazan 46,4% de licencias de salud mental | Ficha Alicanto, 10-nov | SUSESO (modelo de detección presentado al BID, 10-nov) | Descartada: licencias fue el tema del 23-oct |
| 3 | Compensación por pañales y medicamentos (Boletín 18255-31) | Informe de comisión, 11-nov | Residencias / personas mayores | Descartada: personas mayores fue el tema del 9-nov; sin cifras de costo fiscal a la vista |
| 4 | Circular IF/539 (plazo para informar urgencias GES y Ley Ricarte Soto) | Diario Oficial, 11-nov | — | Descartada: cambio técnico sin cifras |
| 5 | Protocolo de columna lumbar e incidentes peligrosos (SUSESO) | SUSESO, 11 y 13-nov | — | Descartada: sin datos de impacto |

Temas de las últimas 4 semanas: residencias (9-nov), sarampión (2-nov), licencias (23-oct), UC Christus (10-oct). Natalidad/partos no se repite.

Por qué la 1: cruza un movimiento de mercado (cierres y reconversión de maternidades) con estadística oficial y política pública, y su lectura no es obvia: la caída de los partos en prestadores privados (más de 60% según DF) supera la de los nacimientos (40,1% entre 2015 y 2025), y la demanda hacia la que giran las clínicas tiene financiamiento público mínimo (580 de unos 9.000 ciclos).

## Verificación
`verify_candidate(weekly, candidates/2026-11-16-natalidad-evidence.json, 2026-11-16)`: PASS sin errores ni advertencias. Ensayo de 688 palabras; bajada de una oración (28 palabras); titular de 77 caracteres.

## Revisión independiente
- Ronda 1 (PASS_WITH_CORRECTIONS): bajada encadenaba dos noticias y mostraba una estimación sin nota; 10.500 y 20.000 son ambos de Zegers (CIPER); Diario Constitucional no identifica al expositor; cifras de Indisa/Alemana y del cierre sin medio en la frase; «Tampoco basta la salida de afiliados» y «porción cada vez menor» eran inferencias no sostenidas; «En junio» sin fecha verificable. Todo corregido; barra de isapres retirada del gráfico.
- Ronda 2 (PASS_WITH_CORRECTIONS): «egresos obstétricos» → «egresos hospitalarios por parto». Corregido.
- Ronda 3: PASS (versión retirada por la política de prensa de pago).
- Ronda 4 (PASS_WITH_CORRECTIONS), sobre la reescritura: la bajada atribuye el >60% a Diario Financiero; «otra clínica… la segunda desde 2025»; «sin precisar años ni fuente». Corregido.
- Ronda 5: PASS.

## Límites conocidos
- Los extractos se leyeron con WebFetch (el proxy bloquea curl a ine.gob.cl y df.cl); el extracto de Santa María y el título de la nota de Antofagasta se confirmaron por esa vía.
- La cifra de partos privados (>60%) es solo la bajada pública de DF, sin años ni fuente; el período no coincide exactamente con 2015–2025.
- `tests/test_normativa_index.py::test_published_index_is_built_from_the_registry_and_review` falla también en `staging` (7b8db82d); no es de este PR.
