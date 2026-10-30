# Playbook de fichas estadísticas

Lo aprendido con F1 Cartera, F4 GES y F6 Boletín IP (28–29 oct 2026), para reutilizarlo en F2 FEFI y en las próximas
estadísticas. Orden acordado: Cartera → Financieras (FEFI) → GES/Licencias. La política de publicación está en
[POLICY.md](POLICY.md). Este documento dice **cómo** construir una ficha y **dónde se hace cumplir** cada regla.

Convención: `sf` = `src/radar_salud/stats_fichas.py`; `js` = `web/stats-ficha.js`; `cfg` = `config/stats_fichas_v1.json`.
"(#N)" significa que la regla vive en un PR abierto y aún no está en `staging`.

## 1. Producto y diseño (Dirección, 28–29 oct)

| Regla | Dónde se cumple |
|---|---|
| Una ficha viva por familia. La anterior va a `archive/`. | `sf.publish`, `sf.live_fichas` |
| Cada actualización es un Insight: una tarjeta del feed que reemplaza las tarjetas sueltas que cubre. | `sf.ficha_card`, `sf.apply_to_snapshot`, `sf.ficha_covers`; disparadores en `sf.evaluate_triggers` |
| Índice → tema. Cada fila de tema tiene etiqueta, línea índice y sparkline, sin números bajo la sparkline. | `sf.topic_fields` (la sparkline replica el gráfico principal del tema), `js` `spark()`, `.sf-row` |
| En modo tema va primero el gráfico principal, con el selector fijo "Ver: tema n/N" y "← Todos los temas" arriba. | `js` `render`/`mount` (`.sf-sticky`, `.sf-pick`); `web/stats-ficha.css` |
| Arriba: ícono de compartir. Al pie: "Fuente original" y "Marcar leída". Kicker más dos líneas meta cortas. Sin "Seguir entidad". | (#113) `js` `shareButton()`, `metaLines()`, `#detailFoot` |
| A 390×844 las primeras filas del índice quedan sobre el pliegue. | (#113) `tests/browser/stats-ficha*.spec.cjs` |
| Texto o tarjeta KPI solo si agrega algo que el gráfico no muestra. `dek: None` significa sin texto. | `sf.topic_fields`; `sf.lens_checks` (`repeated_sentence`); dek incremental de F2 (`stats_ficha_f2.compose`) |
| Sin leyendas de "cómo leer" ni notas de método en el cuerpo. Solo se admiten las claves necesarias para leer el gráfico (p. ej. "punto = agosto, aro = enero") y la procedencia. El método va a Notas. | F1 `f1-share` subtitle; nota `n3b` de F1 (movida desde el texto del tema) |
| Ningún número bajo un gráfico que se pueda malinterpretar (mes vs. año). | sparklines sin ejes ni rótulos (`js` `spark()`) |
| Primero la serie de stock y después las diferencias mensuales. | F1 tema `total`: `[f1-stock, f1-mm]`; F2: niveles t−12 y t, y el cambio en la tabla |
| "Ver datos del gráfico" muestra el desglose útil (por Isapre, cotizantes vs. cargas). | `js` `chart()` → `<details class="sf-data">`; tablas de `f1-isapres` y `f2-resultado-isapres` |
| La Lectura Alicanto puede llevar cifras, pero trazables y no redundantes. | `sf.verify_lectura` + `src/radar_salud/lectura_verifier.py` (`restates_shown_text`, Jaccard ≥ 0,5) |
| "Corregido el xx" es la práctica estándar para corregir. El texto retirado se conserva. | `sf.correction_record`, `sf.sanitize_ges_signal`, `js` `correctionTag()` |

## 2. Reglas de verdad

| Regla | Dónde se cumple |
|---|---|
| Toda cifra traza a un valor de evidencia con locator (hoja!celda o páginas) y sha256. | `sf.value(locator=…)`, `sf.source_ref`; `sf.verify_ficha`: `number_not_in_evidence`, `source_without_hash`, `source_not_captured`, `chart_row_not_in_evidence` |
| Las líneas índice, los deks de tema y las KPI citan sus refs, según la unidad ("77%" solo calza con un valor %). | `sf.line_ref_errors`, `topic_kpi_number_not_in_refs`, `lens_checks` `kpi_ref_missing` |
| Las afirmaciones derivadas ("menor baja del año", "suben por segundo mes") se recalculan con la serie. | `sf.derived_claim_errors` |
| Las descomposiciones suman (cotizantes + cargas = cambio; privadas + públicas = trámite; Isapres = total sistema). Si no, HOLD. | F1 `table_cot_plus_cargas` y reconciliación; F6 `privadas_mas_publicas_distinto_de_tramite`; F2 `stats_capture_fefi.apply_table` `sum_mismatch` |
| Denominadores explícitos (en notas, fuente del gráfico y pool de la Lectura). | `lens_checks` `denominator_not_stated`; `sf.pool_entry` `share_or_rate_without_base`; `lectura_verifier.BASES` |
| Redacción según el signo: se escribe "3,2% menos", nunca "−3,2% menos". | `sf.SIGNED_WITH_WORD` en `verify_ficha` (`signed_figure_with_direction_word`); F6 `rec_clause`; F2 `result_phrase` |
| De pérdida a utilidad (o al revés): delta absoluto y variación % N/A. Nunca un % sobre base negativa. | `stats_ficha_f2.change` (`pct=None`), `pct_cell` → "N/A"; contexto en `docs/CLAUDE_PROJECT_CONTEXT_2026_10_24.md` |
| Los umbrales se evalúan sobre el valor redondeado que se muestra. | F4 `ges.p.*.yoy_pct` (redondeo a 1 decimal antes del 15%); F1 `mezcla.delta_shown`; F2 siniestralidad 90/95 |
| Los conteos van atados a su afirmación ("tres crecen", "9 de 10 con utilidad"). | `sf.COUNT_CLAIM`, `chart_headline_count_not_in_evidence`, `count_phrase`; F2 `conteo.*` citados en `index_refs` |
| Un stock nunca se suma entre cortes, y un flujo se rotula con su período. | `lens_checks` `stock_rule_not_stated`; F6 n1; F2 n1 |

## 3. Documentos (PDF / xls / xlsx)

1. **Captura.** Se hace con `stats_capture.SisFetcher`: allowlist SIS, robots.txt (falla cerrado), tope de 25 MB,
   30 s por pedido y 8 min por paso. Se guardan solo el hash y los valores, nunca el binario.
   F2 reutiliza el mismo fetcher en `stats_capture_fefi.capture_fefi`.
2. **No se aceptan heurísticas genéricas de texto** para "encontrar" cifras: dos revisiones independientes las
   rompieron (negación, subordinadas, bordes de tabla). En su lugar se usan **plantillas ancladas por cifra** en `cfg`.
   - Se aplican sobre texto normalizado (`figure_templates.normalize_text`), en las páginas citadas o en las filas de
     una hoja.
   - Cada patrón debe calzar **exactamente una vez** (`figure_templates.match_once`).
   - `reviewed_by`/`reviewed_at` los pone una persona, después de leer el texto real que imprimen las anotaciones de CI.
   - Un marcador `<<…>>` o una plantilla sin revisar significa HOLD (`figure_templates.review_state`).
   - Usa tokens `{t_year}`, `{t1_year}` y `{t_month}` en vez de fechas literales (`figure_templates.period_subs`).
   - Dónde viven: F6 checker v2 (#112); F2 `families.F2.parser_template`.
3. **Re-chequeo.** Cada parse registra `checker_version` y el hash de la plantilla. Si cambia cualquiera de los dos,
   el documento se vuelve a leer una vez.
   - Un sha distinto significa HOLD (`hash_mismatch`); nunca se re-captura en silencio.
   - Se conserva `previous_parse`.
   - Dónde: F6 en `stats_capture._recheck_doc` (#112); F2 en `stats_capture_fefi._recheck_doc`.
4. **Este sandbox no llega a `superdesalud.gob.cl`.** Los archivos reales se ven en CI o en la corrida diaria, mediante
   anotaciones `::notice`.
   - Límites: como máximo 9 por test, unos 3.000 caracteres cada una, escapadas, escritas con `capsys.disabled()`.
   - Tests: F6 `tests/test_stats_fichas_f6_real_pdf.py` (#112); F2 `tests/test_stats_ficha_f2_real_xls.py`.
   - Un solo test con anotaciones por PR: GitHub muestra unas 10 por paso.
5. Una hoja o unidad que no se puede leer, un `.xls` sin `xlrd`, una fila sin listar o una suma que no calza
   significan HOLD con la razón registrada (`stats_capture_fefi.parse_fefi_workbook`).

## 4. Tests

- **Fuente de CI.** CI usa DejaVu Sans. Los rótulos dentro del viewBox se prueban con DejaVu forzado
  (`tests/browser/stats-ficha.spec.cjs`, "fits … px with DejaVu Sans").
- **Medir posiciones** en un solo frame, cuando el scroll terminó (`page.evaluate` tras asentarse; commit `122394a8`).
- **Los tests nunca ven la clave de IA del runner** (`tests/conftest.py` `_no_provider_key`). Los ledgers van aislados
  con `RADAR_ROOT` en `tmp_path`.
- **Afirmar reglas, no conteos.** Un test atado al ledger vivo o a conteos de datos se rompe cuando los datos crecen.
  Ejemplos: "el total es un piso" (`a872833d`), "sigue la activación registrada" (`3898ac97`). El test CI de F2 afirma
  la regla de plantilla, no cuántas hojas hay.
- **Fixtures sintéticos** marcados como tales (`tests/stats_ficha_fixtures.py`; planillas generadas en memoria en
  `tests/test_stats_ficha_f2.py`). Cada KPI se recalcula en el test, independiente del builder.
- **Cada familia prueba** HOLD por plantilla sin revisar, suma que no calza, sha distinto, redacción según el signo y
  ausencia de llamadas al modelo.

## 5. Proceso

- **Revisión adversarial independiente** para todo lo que toque cifras o títulos. Antecedentes: tercera revisión del
  28 oct (POLICY.md, Lectura) y 62 sondas de #112.
- **"En staging"** significa verificado en la página desplegada, no en el código (CLAUDE.md regla 5). Rama ≠ merge ≠
  deploy ≠ salud recurrente.
- **Conflictos de datos:** se toman los datos de `staging` y se regenera offline
  (`scripts/run_stats_fichas.py --no-capture --no-llm`, `python tests/stats_ficha_fixtures.py`). Las salidas pagadas se
  preservan: `run_family` nunca vuelve a pagar una Lectura para el mismo `release_key`.
- **Una familia nueva queda `planned`** hasta tener builder, tests y PR a `staging`. Activarla (`status: active`) es una
  decisión aparte (POLICY.md).

## 6. Receta para una familia nueva

1. **Registro.** En `cfg`: `kpis` con fórmula, denominador, `period_rule`, umbral y `pitfalls`; además `calendar`,
   `templates`, `cadence_phrase` y `lectura_enabled: false`.
2. **Captura.** Fetcher SIS (u otro con allowlist, robots, tope y deadline propios), hash y valores, y re-chequeo por
   versión y plantilla.
3. **Plantilla.** Con marcadores `<<…>>` y `reviewed_by: "pendiente"`. Agregar el test CI de anotaciones.
4. **Builder.** `stats_ficha_<fam>.py` con `build_package` (reconciliación → HOLD), `compose` (temas adaptativos:
   solo los que los datos verificados sostienen) y `run` (`sf.run_family`).
5. **Tests.** Fixtures sintéticos, los HOLD, los recálculos independientes y la redacción.
6. **PR a `staging`.** Revisión independiente. Una persona llena y revisa la plantilla con el texto de CI.
   Dirección activa la familia.

## 7. F2 FEFI (estado al 30 oct)

**Qué hace.**
- `stats_capture_fefi`: lista las publicaciones FEFI desde `data/history/superintendencia_signals.json`, captura la
  planilla (xls o xlsx, con hash) y la lee **solo** con `families.F2.parser_template`.
  - Por tabla: una hoja, una fila de encabezado, una columna por (ítem, período) y una fila por Isapre.
  - La unidad queda anclada.
  - En cada columna las Isapres suman el "Total sistema".
- `stats_ficha_f2`: elige los temas que los datos verificados sostienen, de una lista cerrada:
  - resultados, ingresos y costos, siniestralidad, patrimonio;
  - un tema sin sus columnas no aparece;
  - con menos de tres temas, HOLD.
- Aplica las reglas de pérdida a utilidad, redacción según el signo, umbral redondeado y denominador explícito.
- La Lectura está apagada (`lectura_enabled: false`), así que no hay llamadas pagadas.
- F2 sigue `planned`: la corrida diaria no la ejecuta ni descarga nada. Solo corre con `--family F2`.

**Qué queda en HOLD y por qué.**
1. `parser_template_placeholder`: la plantilla tiene marcadores `<<…>>` y `reviewed_by: "pendiente"`. Hoja, columnas y
   filas no están verificadas contra el archivo real.
2. `HOLD_COVERAGE_ESENCIAL` (`config/editorial_rules_v3.json` → `holds.fefi_2026_03`): la nota A18 contradice las filas
   institucionales de Esencial.
   - Mientras siga activo, los agregados del sistema y los rankings entre Isapres **no se calculan**.
   - La ficha no se publica (POLICY.md: F2 sin auto-publicación).

**Pasos humanos para levantar el HOLD.**
1. Mergear este PR. CI (job `tests`) corre `tests/test_stats_ficha_f2_real_xls.py` y publica como anotaciones:
   - el formato, el sha256 y las hojas;
   - las primeras filas de hasta 7 hojas;
   - la nota de Esencial.

   Si el archivo es `.xls`, CI lo lee con `xlrd` (dependencia nueva en `pyproject.toml`).
2. Con ese texto, una persona reemplaza cada `<<…>>` de `families.F2.parser_template` por el patrón real:
   - hoja y fila de encabezado;
   - columnas (`item`/`period`, y `sign: -1` si los costos vienen negativos);
   - filas de las 10 Isapres y "Total sistema";
   - unidad (`to_mm_clp`) y nota de cobertura.

   Borra las columnas que no existan, y pone `reviewed_by` y `reviewed_at`. Va en un PR a `staging`, con revisión
   independiente.
3. En ese PR, el test CI debe pasar con `verified`: plantilla revisada ⇒ el parse real calza exactamente una vez y
   suma el total.
4. Dirección lee la nota A18 en la anotación y decide sobre Esencial.
   - Si la aclara, retira `holds.fefi_2026_03` de `config/editorial_rules_v3.json`, con fecha y razón (se conserva la
     historia).
   - Si no, la ficha sigue en HOLD.
5. Dirección decide activar F2 (`status: "active"`) y, por separado, la Lectura (`lectura_enabled`).
   - Primera corrida: `scripts/run_stats_fichas.py --family F2` captura una vez y re-chequea con la plantilla revisada.
   - Se publica solo si la reconciliación y `verify_ficha` dan PASS.
6. "En staging" se afirma solo después de ver la ficha en la página desplegada.

**Pendiente conocido.**
- Montos nominales: el valor real (UF) requiere capturar la serie UF.
- `margen_beneficiario` (registro) necesita el promedio de cartera F1.
- F6 adopta `figure_templates` cuando se mergee #112 (misma semántica).

## 8. Licencias (SUSESO/SIS) y otras: qué haría falta (no construido)

**F3 Licencias médicas y SIL.**
- **Fuentes.** SIS "Estadística Anual de Licencias Médicas y SIL del Sistema Isapre" (xlsx anual) y SUSESO
  "Estadísticas consolidadas de licencias médicas curativas y SIL – FONASA e ISAPRES" (anual). Los comunicados LME de
  SUSESO son texto, sin dataset: se conservan con su hash. Las sanciones a emisores salen de las páginas de
  fiscalización SUSESO (`suseso_fiscalizacion.py`).
- **Captura.** Fetcher con allowlist `www.suseso.gob.cl` además de la SIS, con robots, tope y deadline. Es el mismo
  patrón que `SisFetcher`, generalizando el host. Los comunicados entran como texto + hash, sin cifras derivadas.
- **Plantillas.** Una por planilla: hoja, encabezado, columnas `emitidas`/`autorizadas`/`rechazadas`/`dias_autorizados`
  por pagador (Isapre/COMPIN), con `{t_year}`. Se revisan con anotaciones CI, como F2.
- **Temas candidatos.** Emitidas vs. autorizadas (denominadores distintos), días por licencia autorizada, tasa de
  rechazo por pagador (sin comparar criterios Isapre vs. COMPIN) y sanciones a emisores (ventana de 90 días; sin
  nombrar profesionales sin resolución firme).
- **Período.** YTD a/a; el año en curso se rotula "parcial".

**F5 Reclamos/fiscalización, F7 Financiamiento público, F8 Presión asistencial.** Siguen la receta del §6.
- Antes de proponer temas, verificar la fuente: FONASA responde HTTP 403 e ISP falla en TLS (bloqueos externos).
- No inventar series: un tema existe solo si una columna revisada lo sostiene.
