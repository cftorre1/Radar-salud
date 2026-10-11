# Prestadores, gremio y farma · checkpoint Codex F

PR draft [#14](https://github.com/cftorre1/Radar-salud/pull/14), rama
`codex/f-prestadores-gremio-2026-10-11`, basada en `staging`. Base inicial
`cadb6c2`; incorporada gobernanza de `staging` hasta `73aff5c` mediante merge.
No se modificó ni desplegó `main`/producción. La aceptación permanece pendiente.

## Resultado verificable

Ocho fuentes originales observadas y auditadas. De doce candidatos recuperados,
cinco pasaron sus procesadores, tres fueron rechazados y cuatro siguen retenidos.
Todos son BACKFILL; los publicados son salidas de la rama aislada. Dos fechas
históricas de PDFs quedaron en cuarentena y siete registros de navegación del
gremio se archivaron conservando el estado anterior. Hay una entidad visible por
institución, incluyendo Clínicas Achs Salud separada de Achs Seguro Laboral.

Las ventanas incluyen edades 0–30/90 días al 11 de octubre de 2026. Se usa fecha
de publicación original verificada; ausencia de fecha es `null`. Los conteos son
límites inferiores cuando falta inventario, nunca prueba de cero omisiones.

| Fuente | Candidatos verificados 30/90 | Resultado de recuperación | Blocker vigente |
|---|---:|---|---|
| RedSalud | 1/2 | TMO retenido; Masvida ya existente | Listado 27-08 vs `datePublished` 04-09; inventario remoto completo sin persistir |
| Bupa Chile | 0/2 | Genomas recuperado; dos anuncios sin fecha retenidos | 51 tarjetas sin fecha de listado; inversión y BancoEstado sin publicación verificable |
| Clínica INDISA | 1/1 | Convenio Esencial retenido | Actions HTTP403; páginas 2–4 sin reconciliar; gate `pending_90_day_audit` |
| Red Dávila | 0/2 | Firma y ejecución Enlace rechazadas | Límite 90 días sin paginación verificada; tarjeta cáncer sin sello; submotivos de rechazo no persistidos |
| Andes Salud | 1/3 | Talca, MetLife y Puerto Varas recuperados | Primera página observada; frontera completa de 90 días no verificada |
| Clínicas de Chile A.G. | 1/1 | Jornada CENS recuperada | Noticias alcanzó frontera 90 días; 33 documentos sin fecha de publicación |
| Pfizer Chile | 0/0 | Sin omisión fechada de 2026 acreditada | Newsroom reciente sólo hasta junio 2023; tarjeta healthtech enlaza otro artículo |
| Clínicas Achs Salud | 0/1 | SAFED rechazado | Frontera 90 días incompleta; una URL Unicode y otro HTTPError; submotivo editorial no persistido |

Para el gremio se recorrieron Noticias y las 3/3/4 páginas de Memorias, Estudios
y análisis y Documentos: 39 items únicos, seis noticias fechadas y 33 documentos.
Actions resolvió los fallos de paginación del lector web. El año de datos, una
cita legal o el directorio de una URL no acreditan publicación.

Clínica Las Condes e Interclínicas conservan la disposición registrada
`pass_secondary`; no se activó otro newsroom ni se afirmó cobertura original
completa. Memorias/subcanales de Interclínicas mantienen su task Work4.
`prestadores_data` es un carril estadístico oficial, con sus blockers de fecha y
QA estadística registrados; no representa otra entidad institucional.

## Gates y gasto

Umbrales intactos: corporativo 78, prestador 75, noticias gremio 70 y documentos
gremio 75. Se exige H1, cuerpo legible y fecha verificada. Gates de fuente
pendientes bloquean antes de fetch y AI. Se preservan las diferencias entre
marketing, capacidad, convenio, inversión, aseguradores y relación público-privada.
Farmacia/laboratorio intrahospitalarios se clasifican como capacidad clínica;
convenios con laboratorios farmacéuticos nombrados conservan Farma. Puerto Varas
se expresa como proyecto; los $10.000 millones corresponden al plan regional.

Ocho llamadas fast nuevas en total; cero deep y cero reevaluaciones pagadas.
Ledger octubre fast 31→39. Los receipts inhiben ambos pases pagados en pushes
posteriores. `python scripts/export_provider_checkpoint.py --durable` verifica
los cinco outputs desde archivos versionados, sin descarga de artifacts ni AI.
Los checkpoints originales permanecen intactos; la curación posterior está
documentada en la auditoría de Andes Salud.

## QA y Reviewer

43 tests focalizados PASS; Python completo: 291 PASS, 1 FAIL preexistente
(11 actos normativos visibles frente al mínimo de 12), 1 skip. Node PASS.
Browser desktop/mobile: 44 PASS y 6 FAIL; los seis están presentes en la base.
El subconjunto de prestadores pasa 4/4 y verifica identidad, fechas, BACKFILL,
contrato editorial y cuarentena. Reviewer determinístico: data/editorial/UX
PASS, ocho críticos estadísticos iguales a la base. Estos gates no se redujeron.
La revisión independiente y sus condiciones están en el paquete QA.

Evidencia durable:

- `data/audits/provider_reconciliation_2026_10_11.json`: aceptación, ledger y continuidad.
- `data/audits/providers_2026_10_11/*.json`: URL/fecha/materialidad, cola/history/feed, blockers y commit por fuente.
- `data/audits/provider_qa_2026_10_11/`: resultados, comparación con la base, Reviewer y capturas.
- Checkpoints LIVE y repair, con receipts de runs originales y posteriores sin gasto.

## Continuidad desde un checkout limpio

```bash
mkdir -p work
python3 -m venv work/venv
work/venv/bin/python -m pip install -e . pytest
work/venv/bin/python scripts/reconcile_providers.py
work/venv/bin/python scripts/export_provider_checkpoint.py --durable
work/venv/bin/python -m pytest -q tests/test_provider_audit_intake.py tests/test_provider_newsroom_repairs.py tests/test_clinicas_chile_reconciliation.py tests/test_provider_runtime_reconciliation.py tests/test_corporate_newsrooms.py tests/test_beta_source_package.py
npm ci
npm test
npx playwright install chromium
npx playwright test tests/browser/providers.spec.cjs
```

El primer comando de reconciliación sólo lee. `--apply` ingresa evidencia
auditada; `--live` pasa sólo pendientes/retries por los procesadores y presupuestos
vigentes. No repetir evaluaciones terminales para obtener un submotivo no guardado.
En el entorno local se usó Chromium nativo porque la descarga de Playwright y
los hosts originales estaban restringidos; ese bloqueo local se distingue de
los resultados de fetch de Actions.

Siguiente trabajo: completar inventarios y fechas originales declarados; resolver
el conflicto RedSalud y el acceso/gate INDISA. Los owners de normativa/datos deben
resolver el QA global. Mantener PR draft y issue #5/recovery gate abiertos hasta
merge permitido a `staging`, QA + Reviewer y captura recurrente verificable.
