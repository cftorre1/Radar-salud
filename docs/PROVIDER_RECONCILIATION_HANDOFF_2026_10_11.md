# Prestadores, gremio y farma · handoff de Codex F

Estado del frente: **EXTERNAL_BLOCKER_PROVEN**. [PR #14](https://github.com/cftorre1/Radar-salud/pull/14) permanece draft en `codex/f-prestadores-gremio-2026-10-11`; no está READY_FOR_INTEGRATION. Rama reconciliada con `staging` **c4819844e413d31ede792521a2c137392c4ae104**, merge `96ad6f6`, preservando Work2/3/4 y gobernanza. No hubo merge directo, despliegue ni modificación de main/producción.

## Cobertura demostrada y límites

Se conciliaron **1.066 registros de URL** contra pending queue, seen ledger, history, feed y source health. Cada pieza tiene título, institución/canal, publicación verificada o null, fecha del hecho/período/vigencia separadas, clasificación, motivo, aliases/relaciones y evidencia original. Los registros incluyen navegación y documentos; no equivalen a 1.066 noticias sanitarias recientes.

Ventanas inclusivas 0–30/90 días al 2026-10-11, con corte de 90 días el 2026-07-13. En inventarios incompletos los números son **límites inferiores verificados**; los totales relevantes/publicables son null. Cero piezas verificadas no demuestra cero actividad. `omitted_material=0` significa que los candidatos observados están ingresados o relacionados con una señal existente; no certifica los originales inaccesibles.

| Institución | Publicaciones verificadas 30/90 | Candidatos relevantes 30/90 | Publicados / rechazados / retenidos | Outcome |
|---|---:|---:|---:|---|
| RedSalud | 8 / 30 | 2 / 9 | 2 / 7 / 0 | OPERATIVE_DEGRADED |
| Bupa Chile | 0 / 7 | 0 / 2, más 2 sin fecha | 2 / 1 / 1 | EXTERNAL_BLOCKER_PROVEN |
| Clínica INDISA | 1 / 1 previamente verificadas | 1 / 1, más 1 sin fecha | 0 / 0 / 2 | EXTERNAL_BLOCKER_PROVEN |
| Red Dávila | 3 / 13 | 1 / 6 | 0 / 6 / 0 | OPERATIVE_DEGRADED |
| Andes Salud | 11 / 26 | 1 / 4 | 3 / 1 / 0 | OPERATIVE_VALIDATED |
| Clínicas de Chile A.G. | 1 / 3 | 1 / 1 | 1 / 0 / 0 | OPERATIVE_DEGRADED |
| Pfizer Chile | 0 / 0 verificadas | 0 / 0 verificadas | 0 / 0 / 0 | OPERATIVE_DEGRADED |
| Clínicas Achs Salud | 10 / 25 en archivo del grupo | 0 / 1 de la filial, más 1 sin fecha | 0 / 1 / 1 | OPERATIVE_DEGRADED |

Los ocho publicados incluyen dos señales anteriores a esta recuperación: SAFED de Bupa y convenio RedSalud/Masvida. **Se recuperaron seis**. Los rechazos incluyen decisiones actuales no pagadas sobre eventos relacionados; no todos representan una evaluación nueva del modelo.

- **RedSalud:** nueve páginas, Observatorio y sitemap, 94 URL. Cuatro discrepancias de teaser se resuelven sólo mediante canonical propia, JSON-LD propio y sello visible dedicado concordantes. TMO se publicó el 04-09, no el teaser 27-08 ni `dateModified` 07-10. Dos originales del sitemap siguen sin contenido/fecha verificables; alternativa histórica de tele­trombólisis también 403 y Chrome devuelve DOM sin artículo. Microscopio KINEVO900 conserva su carácter operacional y el diagnóstico histórico desconocido; no se inventó score ni se repagó un rechazo para rellenarlo.
- **Bupa:** 51 tarjetas, 53 URL y cinco scripts públicos, sitemap oficial, raíces, feeds y CMS. Las raíces más nuevas carecen de publicación editorial verificable. Inversión US$15m es el evento ya publicado por DF el 21-09, score88: su fecha no se presta a Bupa. BancoEstado es continuidad de campaña desde2024, sin expansión estructural. Conecta introduce atención del asegurador para más de14mil asegurados65+; se retiene por fecha original ausente, con score null y sin AI.
- **INDISA:** listado, detalles, archivos, búsqueda, CMS/feeds y aliases oficiales; HTTP403 en Actions. Chrome normal muestra la misma PÁGINA EN MANTENCIÓN, no el artículo. Esencial conserva la publicación11-09 previamente verificada, que no acredita cobertura actual; FundaElbo sigue sin fecha. Mantener `pending_90_day_audit`: restaurar publisher y conciliar archivo antes de evaluar.
- **Dávila:** **640 originales del sitemap visitados**, 411 fechados por HTTP. Se navegaron además **los228 originales HTTP403 con Chrome normal**:37 HTTP200 fechados,191 aún HTTP403 con igual hash de DOM. La combinación HTTP/Chrome dejó448 fechados,13 recientes90 y3 recientes30; el lector original completa después las191 fechas históricas restantes hasta639 noticias fechadas. Medicina Deportiva1-08 se recuperó por esa vía y evaluó una vez58<75. No se interpretó como simple consejo de bienestar. Los191 originales restantes fueron abiertos uno a uno en el lector público original: todos tienen sello juntoalH1 anterioral13-07 (máximo29-06), con antigüedad de caché registrada. Así queda conciliada la cronología del corpus conocido:639 noticias fechadas ycsr de navegación. Las191 rutas siguen403 actuales; no se declara HTTP200 ni parser vivo a partir del lector. RSS/CMS/paginación alternativos devuelven HTML de fallback. Hay seis candidatos explicados, no publicación forzada para compensar published=0.
- **Andes:** CMS completo de26 publicaciones90,11 en30;24 noticias y dos campañas exactas revisadas. Cuatro candidatos: Talca, MetLife, Puerto Varas publicados; Frutillar70<75 rechazado. Las20 restantes son educación clínica. Fechas CMS cotejadas con encabezado propio. Las dos campañas con título/URL/fecha esperados se excluyen; otro path, título o fecha sigue fallando cerrado.
- **Gremio:** Noticias, Memorias, Estudios y análisis y Documentos; paginación3/3/4 de biblioteca,129 entradas sitemap,33 documentos. CENS70 publicado; opinión que reutiliza OCDE2025 y reunión de sostenibilidad sin compromiso operacional no crean otras señales. El RSS de biblioteca más nuevo es16-03-2026, anterior al corte; la fecha de entrada **no fecha cada PDF o versión**. Se requiere publicación editorial/versionado para33 PDFs y una pieza de biblioteca. Dos fechas falsas de PDFs permanecen en cuarentena; siete registros de navegación archivados.
- **Pfizer:** 17 URL oficiales,16 detalles legibles y encabezados de componentes; última publicación verificada22-01-2023. Los links healthtech/Covax apuntan a otros contenidos y no prestan su fecha al H1 recibido. Cinco originales quedan sin cronología verificable. Requiere newsroom actual o reparación de links/fechas del publisher.
- **Clínicas Achs Salud:** 160 URL del archivo central,25 recientes90, con filtro de pertenencia a la filial; mutualidad conserva su otra entidad. Sitio propio enlazado oficialmente, ocho alternativas, CMS de90 vacío y RSS sin entradas. SAFED es el programa ya cubierto por Bupa; volumen conjunto4299 no se atribuye a Achs. Formulario de precalificación del Master Plan La Serena carece de publicación, adjudicación, monto/capacidad/inicio: retenido, sin AI ni nueva entidad. El error Unicode fue corregido y probado en runtime real.

Cada fuente tiene propietario y acción exacta en `data/audits/provider_piece_reconciliation_2026_10_11.json`. En las dependencias de publisher, Source Engineering debe volver a conciliar cuando haya acceso o evidencia editorial nueva. Integration Commander no puede convertir esos null en cobertura completa por aprobar este PR.

Clínica Las Condes e Interclínicas mantienen su disposición registrada `pass_secondary`; no se activó otro newsroom. Subcanales de Interclínicas pertenecen a Work4. `prestadores_data` conserva su lane estadístico y blockers/QA propios.

## Seis outputs reales y decisiones editoriales

`data/audits/provider_recovered_outputs_2026_10_11.json` prueba salida de procesadores, fecha, score/gate, código de recuperación, lane, materialidad, queue key, seen, unicidad history/feed y contrato editorial. Los checkpoints originales y de reparación permanecen intactos. Las738 filas history y59 publicaciones de cola previas siguen iguales como objetos JSON; sólo se añade TMO a esas738 filas. Feed visible55, cada recuperada exactamente una vez.

| Recuperada | Publicación | Score / gate | Contenido y límite factual |
|---|---|---:|---|
| Andes Talca | 08-09 | 86 / 75 | US$45m,94 camas/18 críticas; farmacia/laboratorio intrahospitalarios son capacidad clínica, sin Farma |
| Andes–MetLife | 23-09 | 82 / 75 | Renovación cinco años;150mil asegurados2031 es meta |
| Andes Puerto Varas | 24-08 | 82 / 75 | Séptimo centro planificado;1000m²,17 consultas y5 muestras;CLP10bn es plan regional fase1, no monto del centro solo |
| Bupa Genomas | 13-08 | 78 / 78 | Programa1000 genomas2026–2030; base anunciada, no completada |
| Clínicas de Chile–CENS | 02-10 | 70 / 70 | Jornada1-10 sobre implementación digital; no nueva ley ni implementación propia |
| RedSalud TMO | 04-09 | 84 / 78 | Unidad1233m²/seis salas protegidas;40–50 trasplantes/año declarado/proyectado, CAR-T2028 planificado |

Todos son BACKFILL y pasan comité/feed. Los umbrales corporativo78/prestador75/noticias gremio70/documentos75 siguen intactos. No se añadió impacto nacional como gate.

Las tres rechazadas iniciales tienen razones actuales específicas: firma Enlace relacionada con ejecución74<75; ejecución Enlace reconsiderada **una vez** con anuncio oficial adicional y hechos de30 cirugías, frente a500 pacientes planificados; SAFED Achs relacionado con programa existente sin incremento propio. Donde faltaba diagnóstico histórico se conserva esa ausencia separada de la revisión actual.

Las cuatro retenidas iniciales se resolvieron así: TMO publicado; inversión Bupa relacionada con DF; BancoEstado excluida como continuidad promocional; Esencial bloqueada por mantenimiento/gate. Retenidas actuales: Conecta, Esencial, FundaElbo y formulario LaSerena, con dependencia concreta y sin scores inventados.

Doce llamadas fast adicionales en la conciliación ampliada: dos follow-up, nueve completion y una Medicina Deportiva. Ledgerfast31→39 en primera recuperación,39→51 ahora;deep14 intacto. Cero repeticiones pagadas de terminales sin evidencia nueva. Los receipts inhiben todos los workflows pagados posteriores. La única reevaluación documentada usa evidencia oficial adicional Enlace, no búsqueda de score.

## Runtime y validación

Las ocho fuentes permanecen registradas en el motor que usa Daily Radar. `provider_recurrent_checkpoint_2026_10_11.json` registra dos ejecuciones reales de `engine_cli --discovery-only --source …` con persistencia: segunda0 nuevas, mismos terminales publicados, history/ledger/unrelatedqueue intactos y watermark del publisher fallido preservado. Ambos polls sobre la cola ya consolidada ingresaron0 piezas nuevas. Cada poll verifica siete fuentes accesibles y el HTTPError original INDISA. Discovery recurrente no equivale a evaluación editorial. Última ejecución completada: [38120892476](https://github.com/cftorre1/Radar-salud/actions/runs/38120892476), checkout `affa53d`; el receipt final de CI prueba seis outputs durables y cero reanálisis pagados.

No se ejecutó el scheduler de staging ni se promovió esta rama. Daily Radar ejecuta tests core antes de recoger: el fallo normativo heredado detiene ese paso; owner normativa/datos debe resolverlo antes de certificar operación periódica tras integración. Las pruebas de runtime aislado usan el motor real, no fixtures.

QA final: código/health de datos `8c7b246f034bb52bb7fdb540308aaf47e8fa8e1a`, browser completo en `9a077a9b5458b573698adb37aebcf8b62a2debd4` y subconjunto prestadores repetido contra el health definitivo:

- Frente:75 PASS,1 skip de prueba live opt-in; Node PASS.
- Python completo:321 PASS,1 FAIL heredado,1 skip. El FAIL requiere12 actos Normativa visibles y encuentra11.
- Browser desktop/mobile:44 PASS,6 FAIL heredados; prestadores4/4 PASS, unicidad, fuentes/fechas, BACKFILL, contrato y health honesto.
- Reviewer determinístico: data/editorial/UX PASS, estadísticas FAIL con los mismos ocho códigos críticos de la base; sin nuevos críticos.
- Baseline inicial y `staging` actual tienen árboles `web`, `src` y `tests` idénticos por SHA; los cambios intermedios son governance/audits. Se preserva evidencia de14 fallos browser iniciales y los seis comunes actuales, sin rebajar tests.
- Reviewer independiente revisó código/datos, detectó un P2 del lector de Chrome ya corregido y verificó las guardas y pruebas: exige canonical y Article propios y bloquea challenge/identidad ajena antes de AI. Dictamen final: **PASS scoped sobre `affa53d`**, sin hallazgos abiertos. Evidencia y pruebas propias en `provider_qa_2026_10_11/independent-reviewer.json`; no convierte los gates compartidos a PASS.

## Continuidad desde checkout limpio

```bash
mkdir -p work
python3 -m venv work/venv
work/venv/bin/python -m pip install -e . pytest
work/venv/bin/python scripts/export_provider_checkpoint.py --durable
work/venv/bin/python scripts/provider_piece_reconciliation.py
work/venv/bin/python -m pytest -q tests/test_provider_inventory.py tests/test_provider_piece_reconciliation.py tests/test_provider_audit_intake.py tests/test_provider_original_reader.py tests/test_provider_newsroom_repairs.py tests/test_provider_runtime_reconciliation.py tests/test_provider_url_transport.py tests/test_andes_archive.py tests/test_source_health_facets.py tests/test_beta_source_package.py tests/test_clinicas_chile_reconciliation.py tests/test_corporate_newsrooms.py
npm ci
npm test
npx playwright install chromium
npx playwright test tests/browser/providers.spec.cjs
```

`export_provider_checkpoint --durable` comprueba seis outputs sin AI ni artifact temporal. `provider_piece_reconciliation.py` reutiliza decisiones explícitas versionadas, no evalúa ni cambia queue/history: actualiza sólo matrices de auditoría y facetas health. Los snapshots/feed se regeneran con `export_web_snapshot.py --offline`; no asumir que regeneration es promoción.

Evidencia durable: master `provider_reconciliation_2026_10_11.json`, ocho audits e inventarios, ledger por pieza, outputs verificados, snapshots reales follow-up/completion/nueva pieza Dávila, metadata/Chrome con receipts y paquete QA. Los workflows aislados tienen permisos contents:read y jamás escriben staging. El Chrome normal verifica TLS, no resuelve desafíos ni cambia identidad; dumpDOM no observa HTTP/finalURL y lo declara; la captura Playwright228 sí observa ambos.

Integration Commander: conservar PRdraft e issue5 abierta. Resolver QA global con owners existentes, evaluar las dependencias editoriales de publisher según gobernanza, revisar el merge permitido y verificar Daily Radar después. Cualquier nueva evidencia de contenido, fecha o magnitud entra por gates normales; ninguna de estas tarjetas se publica de nuevo para obtener verde.
