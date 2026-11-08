# Insight del lunes 9-nov-2026: residencias para mayores × hospitalización social × Ley 21.822

Candidato: `2026-11-09-residencias.json` (formato A, `anchor_kind: monday`, ancla 2026-11-09, vence 2026-11-16). Publicado en `editorial_approved.json`; el insight anterior (sarampión, 2-nov) quedó en `archive/2026-11-02.json`.
Redactor: Claude (corrida programada del domingo 8-nov). Revisión independiente: subagente verificador, PASS_WITH_CORRECTIONS (8 correcciones aplicadas, sección 5).

## 1. Ancla estadística (F4 GES) y por qué no se usó

`run_weekly_insight_a.py --offline --as-of 2026-11-09` seleccionó la ficha F4 GES (período 2026-06) y escribió `2026-11-09-stats-brief.json`. No se usó:

- La regla de Dirección del 28-oct exige que la noticia gatillante sea de los 7 días previos al lunes. La SIS publicó la planilla el 14-oct (26 días antes). Lo único que ocurrió en la semana fue la primera verificación de Alicanto (5-nov). `verify_candidate` comprueba `event_date` (ventana `MONDAY_EVIDENCE_DAYS = 7`) y, con la fecha de la SIS, un borrador anclado falla. Tomar la fecha de verificación interna como `event_date` habría sido forzar la regla.
- Las cifras ancla permitidas pesan poco: el −7,0% y el −54,1% de Isapres los explica un T2 2025 atípico en los datos SIS, como dice la propia ficha. Además, el cáncer GES fue el candidato "wow" del 2-nov.
- Se aplica la decisión 2 de POLICY.md: tema normal, sin `stats_anchor` y sin registro de contrato. `check_weekly_insight_contract.py --gate` da PASS.

Conflicto a resolver por Dirección/coordinación: la regla de selección por ancla estadística (primera verificación ≤ 7 días, publicación SIS ≤ 30 días) y la verificación de `event_date` (≤ 7 días) no son compatibles. Un insight anclado en una ficha cuya publicación SIS tenga más de 7 días nunca pasa `verify_candidate`.

## 2. Tesis evaluadas (noticias del 2 al 8-nov)

| # | Tesis | Gatillante (≤ 7 días) | Cruces | Respaldo | Resultado |
|---|---|---|---|---|---|
| 1 | **Entra capital privado a las residencias para mayores, pero el déficit de cuidados ya se paga en camas de hospital** | FNE, 2-nov (aprobación pura y simple SalfaCorp–Angelini–Villa Soleares–Vivendi) | Estudio de la Superintendencia de Salud sobre hospitalización social (1% de egresos, 15,3% de días-cama de personas de 60+), 1.056 pacientes con alta en camas (subsecretario de Redes), red Senama (23 Eleam, 1.318 cupos), catastro 2021 (993/505), Censo 2024 INE (593.010 de 80+, 54% con discapacidad), Ley 21.822 (Política Nacional de Envejecimiento en 6 meses), plan Minsal post-Pitrufquén | Alto: 5 fuentes oficiales (FNE, SIS, INE, Minsal, Diario Oficial) + 4 de prensa declaradas | **Elegida** |
| 2 | Ley Corta: a dos años, isapres han devuelto cerca del 30% de la deuda; prepagos (Nueva Masvida terminó) | DF, 2 y 5-nov | Pauta 20-ago (21%), cartera SIS, FEFI | Medio-bajo: DF es de pago (solo título y bajada); sin informe oficial de avance a la vista | Descartada; candidata cuando la SIS publique el avance |
| 3 | Ley Ricarte Soto: decreto de prestadores aprobados + fiscalización LRS + recorte en Presupuesto 2027 | Diario Oficial, 5-nov | Fiscalización SIS 28-oct, prensa sobre Presupuesto | Medio: el decreto es un listado sin cifras de impacto | Descartada |
| 4 | Presupuesto de la Superintendencia de Salud ($21.033 millones) y fiscalización GES | SIS, 2-nov | Partida 16 | Medio: anuncio institucional, poco cruce nuevo | Descartada |
| 5 | Circulares IF 538–541 (terapia ocupacional en planes, deducible CAEC, plazos GES de urgencia) | SIS, 5-nov | — | Bajo: cambios técnicos sin cifras | Descartada |
| 6 | F4 GES (ancla estadística) | SIS, 14-oct | brief | Ver sección 1 | Descartada |

Temas de las últimas 4 semanas: sarampión (2-nov), licencias médicas (23-oct) y UC Christus (10-oct). Las residencias para mayores no se repiten. El borrador de cuidados del 2-nov (`2026-11-02-draft.json`, no publicado) usaba encuestas de percepción por prensa. Este insight parte de un hecho nuevo (la decisión de la FNE) y lo cruza con fuentes oficiales.

Por qué la 1: es el ejemplo que pidió Dirección (adultos mayores × políticas públicas de cuidados / ley de vejez digna). Además, conecta un movimiento de mercado con el costo para el sistema de salud. Su lectura no es obvia: la hospitalización social es 1% de los egresos de las personas de 60+, pero 15% de sus días-cama, y las personas con alta que siguen hospitalizadas equivalen a ≈ 80% de los cupos públicos de Senama.

## 3. Cifras con su cita (lectura del 8-nov-2026)

- **FNE, comunicado del 2-nov.** Cita: "aprobó de manera pura y simple la asociación"; "no resulta apta para reducir sustancialmente la competencia en ninguno de los segmentos analizados"; "foco en proyectos de mayor tamaño". Partes: Rentas Inmobiliarias San Esteban (Villa Soleares) y Senior Care Services (Vivendi), que administrará las residencias. El comunicado no trae cifras; el informe se publicará en el buscador de fusiones.
- **CNN Chile.** Cita: "un tamaño objetivo de UF 1.500.000". Además: 148 habitaciones en La Reina (abril de 2027), ampliación de 52 a 102 en Ñuñoa, 250 habitaciones en total, "hasta 1.000 habitaciones en un horizonte de hasta 15 años" y aprobación de la FNE el 29-oct.
- **Emol, 14-sep, con datos de Senama.** Cita: "mantiene 23 Eleam públicos con cupo para 1.318 personas" (informe del I trimestre de 2026). Además: 900 hogares privados autorizados y 16 víctimas fatales en Pitrufquén, en un recinto sin resolución sanitaria.
- **La Tercera, septiembre.** Cita: "Ese catastro dio con 993 hogares autorizados y otros 505 sin resolución sanitaria". El último registro oficial es de 2021.
- **Minsal, 15-sep.** Cita: "cerca de 500 establecimientos sin autorización sanitaria". También anunció que publicará la oferta de Eleam con resolución sanitaria.
- **INE, 29-sep (Censo 2024).** Citas: "3.665.028 personas de 60 años o más, equivalentes al 19,8%"; "593.010 personas tienen 80 años o más"; "54,0%" en situación de discapacidad.
- **La Tercera, junio.** Citas: "cuando llegó al cargo en marzo, eran 996"; "Ahora, en junio, ese número subió a 1.056". Los dio el subsecretario Julio Montt en un conversatorio. Es un dato de todas las edades y la fuente lo atribuye a falta de redes. El "$94,5 mil millones anuales" del mismo artículo **no se usó**, porque no informa autor ni método.
- **Superintendencia de Salud, estudio de Olivares-Tirado (publicado en 2020, datos de 2017).** Definición: "estadía prolongada (60 o más días) con una baja necesidad de atención médica hospitalaria". Cifras: 1% de los egresos de las personas de 60+ y "15,3% del total de días-cama utilizados por las PM60+" (3.918.415). Los montos de gasto (MM$15.473 Fonasa y MM$20.146 Isapres, en pesos de 2019) **no se usaron**, para evitar comparar pesos de 2019 con cifras actuales.
- **Ley 21.822 (Diario Oficial, 1-jun; resumen de Actualidad Jurídica DOE).** Cita: "deberá dictarse dentro de seis meses desde la entrada en vigencia de la ley". La fecha de vigencia no está verificada, así que el texto no da plazo de vencimiento.

Estimaciones: 505 / (993 + 505) = 33,7% ("uno de cada tres") y 1.056 / 1.318 = 80,1% ("ocho de cada diez"). Ninguna cifra es monetaria, así que no hay mezcla de valores reales y nominales.

## 4. Verificación determinista

`verify_candidate`: PASS, sin errores ni advertencias. Ensayo de 249 palabras, bajada de 35 palabras y titular de 109 caracteres. Las 5 notas resuelven y todas tienen referencia. La Ley 21.822 se explica con "obliga a dictar". `reviewed_weekly` es válido del 9 al 15-nov y falla el 8-nov y el 16-nov.

## 5. Revisión independiente (subagente): PASS_WITH_CORRECTIONS

Corrección bloqueante:
1. El subtítulo del gráfico 2 decía "% del total de personas"; ahora dice "% de los egresos y de los días-cama".

Correcciones aplicadas:
2. Comparación 1.056 vs. cupos: el ensayo ahora dice "de todas las edades" y "cupos públicos".
3. Causalidad: las camas ocupadas se atribuyen a la "falta de redes", no a la falta de cupos. La nota n4 lo explica.
4. Partes: "sociedades ligadas a Villa Soleares y a Vivendi, que administrará las residencias".
5. Fechas: comunicado de la FNE del 2-nov y aprobación del 29-oct; CNN sin día.
6. Tono: "Ese costo queda fuera del debate" pasó a "rara vez se discute".
7. Qué mirar: el informe de la FNE y el registro del Minsal llevan "cuando se publique", porque no tienen fecha comprometida.
8. Ley 21.822: el plazo queda "desde que entra en vigencia", sin fecha inventada.

Sugerencia no aplicada: citar en el texto la fuente de cada cifra del párrafo 2 de "Qué pasó". El párrafo ya nombra el Censo 2024, y la nota n2 cubre los cupos de Senama.
