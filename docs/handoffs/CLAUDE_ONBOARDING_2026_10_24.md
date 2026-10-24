# Claude · Diagnóstico de onboarding — 24-oct-2026

Documento de auditoría. No autoriza merges, despliegues, gastos ni publicaciones.

## Base verificada
- Clon completo `cftorre1/radar-salud`, staging HEAD `d31314e5d25913f3bdb6eaabbf03858f4f3d3f2c` (merge PR #35), 2.034 commits.
- `web/data/product.json` (37.463.117 bytes) íntegro: blob `0253e5ad9443415a2457f529fae8527ed48337b7` igual al árbol. El bloqueo de checkout de Codex I ya no aplica.
- `main` = `54174c5d` (11-oct), 1.942 commits detrás de staging y 68 propios. `production-stable` = `06831243` (23-sep).
- Las tres ramas figuran `protected=false` vía API. Repositorio público.

## Hallazgos críticos
1. **Sin captura desde el 12-oct.** Último `checked_at` en `data/source_health.json` = 2026-10-12. Daily Radar: 10 corridas programadas seguidas en `failure` (12–23 oct), paso "Core deterministic tests before collection".
2. **Los `schedule` corren desde `main`** (rama por defecto), no desde staging. Cron activos en main: `autonomy-controller.yml` (*/10), `source-audit-executor.yml` (horario), `daily-radar.yml` (lun–vie 09:30 UTC), `weekly-digest.yml` (vie 12:00 UTC).
3. **`daily-radar.yml` en main ejecuta `git push origin HEAD:staging`** si sus tests pasan: riesgo de sobrescribir staging con salida de código antiguo.
4. **`weekly-digest.yml` en main publica directo vía Buttondown** (`scripts/send_weekly_digest.py`: crea email y llama `/publish`) si existe `BUTTONDOWN_API_KEY`. Corrió `success` 9, 16 y 23-oct. Existencia del secreto NO verificada (API de secretos bloqueada para esta sesión). Contradice "newsletter apagado" de staging.
5. **QA de staging rojo:** preview del merge PR #35 (run 40123646028) falla en `pytest`.

## QA local sobre `d31314e`
- Python: 3.870 passed, 4 failed, 1 skipped (3 módulos no recolectados por falta del SDK `openai` en este entorno; en CI sí corren).
  - `tests/test_reviewer.py::test_current_snapshot_passes_existing_editorial_gate` — `stale_source_check` (fuentes sin consulta en 7 días). Documentado.
  - `tests/test_web_snapshot.py::test_real_prestador_pulse_keeps_material_and_all_three_resolutions` — `sanction_count` 9 vs supuesto fijo 3. Documentado.
  - 2× `tests/test_ist_full_pdf_review.py` — requieren el PDF de IST, red bloqueada en este entorno; revalidar en CI.
- Node: 49/49 PASS. Playwright: no ejecutado (sin navegadores ni acceso a registros en este entorno).

## Integraciones (secretos referenciados en workflows, sin valores)
| Servicio | Estado | Variable |
|---|---|---|
| GitHub Actions/Pages | Operativo; cron desalineado | `GITHUB_TOKEN` |
| OpenAI | Usado hasta 12-oct; 556 respuestas, ~USD 1,8 estimados (534 luna, 22 terra) | `OPENAI_API_KEY` |
| Buttondown | Código de envío activo en main | `BUTTONDOWN_API_KEY` |
| MailerLite, PostHog, Supabase, WhatsApp | Diseño/configuración sin credencial en uso | — |
| Dominio `alicantosalud.cl` | Sin `CNAME` en repo; no verificado | — |

## PR abiertos
- #34: mergeable, limpio (base `74da1c6d`, 4 commits detrás de staging).
- #29: 17 detrás de staging; 2 defectos Daily First pendientes.
- #32: documental, 17 detrás; sus 3 archivos aún no están en staging.

## Orden recomendado (requiere Dirección)
0. Desactivar los cron de `main` (UI de Actions) y revisar la cuenta Buttondown.
1. PR: reparar los 2 tests vencidos sin relajar controles (regla relativa a la fecha del snapshot; sin número fijo de sanciones).
2. Proteger `main` y `production-stable`.
3. Diseño de ejecución diaria que corra código de staging, determinística, con alertas 24h/48h.
4. #34 → #29 (rebase + defectos) → #32. Luego prueba de recurrencia ≥24h y 7/7, Codex I, IF10670/FEFI.

OpenAI queda en HOLD sin cambios hasta un benchmark ciego contra fixtures editoriales.
