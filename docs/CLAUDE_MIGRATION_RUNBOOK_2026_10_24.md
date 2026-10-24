# Claude Ecosystem Migration Runbook — 24-oct-2026

## Principio
**No migrar código fuera de GitHub.** Claude debe conectarse a `cftorre1/Radar-salud` y trabajar por ramas/PR. Lo que falta traspasar es orientación estratégica, permisos/autenticación externos, secretos en gestor seguro, herramientas locales y autonomía de agentes, no copiar millones de bytes manualmente.

## Inventario que SÍ migra y que NO
| Recurso | Dónde está | Acción |
|---|---|---|
| Código Python/JS, HTML, tests, workflows, fixtures, history, receipts, config, handoffs | GitHub repo | Clonar completo; preservar git history y archivos grandes. No exportar a chats. |
| Concepto, tesis, MVP, roadmap, decisiones y pendientes | `docs/CLAUDE_PROJECT_CONTEXT_2026_10_24.md`, issue #5 | Leer y mantener actualizado con PR documental. |
| Contexto exclusivo de chats Work/Codex, prioridades comerciales recientes no registradas | Conversaciones ChatGPT | Ya sintetizado parcialmente en contexto maestro; verificar decisiones faltantes contra usuario y registrar en PR, no asumir acceso automático de Claude. |
| GitHub App/OAuth, permisos de cuenta, repos privados, herramientas | Entorno ChatGPT | Reconectar GitHub en Claude/Claude Code con permisos mínimos; no transferibles por Git. |
| OpenAI/Anthropic/API keys, MailerLite, PostHog, dominio/DNS y otros tokens | Proveedor/secret store, si existen | Inventariar nombres, scopes, rotación y owner de credenciales; insertar valores únicamente en GitHub Secrets/gestor del nuevo entorno con aprobación. **Nunca copiar valores en prompts/repos/issues.** |
| Workflows cron/Actions, Pages/entornos | GitHub | Persisten en GitHub pero confirmar permisos, triggers, environments y schedule real; no activarlos sin gate. |
| Estado de agentes Work/Codex, tareas ChatGPT | Plataformas originales | No se migra ejecución/recursos ni sesiones. Reconstruir backlog operativo desde queue, PMO, issue y PR. |
| Archivos grandes `web/data/product.json` (~37.5 MB según bloqueo Codex I) | GitHub | Clonar vía Git funcional/runner autorizado; evitar conector de lectura individual. Verificar hash de blobs y que checkout esté completo. |
| Dominio/branding/copy/legal/imagen logo original | Parte en web y repositorio, parte decisiones de chat | Comprobar que assets originales y derechos están en repo; si faltan, documentar y subir assets propios sin secretos. |

## Preflight en entorno Claude
1. Conectar GitHub y conceder acceso sólo al repo; confirmar permiso para PR, lectura issue5/Actions. Registrar quién puede mergear.
2. `git clone --no-single-branch https://github.com/cftorre1/Radar-salud.git`; `git fetch origin`; `git switch --track origin/staging`. Verificar `git status --short`, `git rev-parse HEAD`, archivos grandes y hashes Git, ausencia de LFS/submodules inesperados; NO degradar TLS/proxy.
3. Leer `docs/CLAUDE_PROJECT_CONTEXT_2026_10_24.md`, este runbook, `docs/PRODUCT_SCOPE_V2.md`, `docs/SERVICES_V2_FINAL.md`, `docs/PMO_BASELINE.md`, `config/orchestrator_queue.json`, `config/pmo_baseline.json`, `data/source_health.json`, `docs/handoffs/`, issue #5 y PR #29/#32/#33/#34.
4. Ejecutar baseline offline reproducible: Python tests, Node tests, Playwright desktop/mobile, Reviewer; confirmar herramientas de sistema y paquetes por lockfiles; las fuentes en LIVE requieren permisos/red y no deben ser ejecutadas indiscriminadamente.
5. Distinguir branch/code/CI vs staging HEAD/runtime y Pages desplegado, reportando cinco SHAs si difieren.
6. Listar workflows `.github/workflows/`, GitHub Actions Secrets **por nombre, no valor**, variables, branches rules, Pages environments y dominio; categorizar cada integración: OPERATIVA COMPROBADA / CONFIGURADA SIN PROBAR / PLANEADA / BLOQUEADA / FUERA DE ALCANCE.
7. Poner gastos, modelos, mails y automatización en HOLD hasta disponer de cuentas y autorizaciones. Para migración de OpenAI a Claude, conservar interfaces y fixtures y ejecutar benchmark ciego con evidencia, sin reemplazar el routing global por mera renombrada.
8. Crear issue y backlog de 2 semanas prioritario con owner y gates, basándose en hechos, no estimaciones inventadas.

## Dependencias/credenciales a inspeccionar, jamás afirmar existentes sin prueba
- `OPENAI_API_KEY` (experimento/routing de modelo); claves Anthropic si se decide usar Claude API. `config/model_routing_v1.json` es configuración heredada, no credencial.
- `MAILERLITE_API_KEY`, grupos newsletter/early access, dominios DKIM/SPF/DMARC, sender, consentimiento y flags. Por ahora newsletter apagado según repo.
- `POSTHOG` project key y host, seguimiento de uso; key pública no es necesariamente secreta, pero privacidad y consentimiento se deben evaluar.
- Token de Mercado Público (documentación antigua), proveedores externos/data; inspeccionar workflows para descubrir exactamente cuáles se invocan y sus condiciones de ejecución.
- GitHub token / app installation para clone, branches, checks, PR, issues, workflow_dispatch, Pages; permisos mínimos y scopes exactos.
- Cloudflare/DNS `alicantosalud.cl`, Google Workspace, HTTPS/SSL, proveedor de dominio; **verificar propiedad/configuración** en la cuenta correspondiente.
- Supabase/Postgres/WhatsApp son arquitectura prevista; NO asumir instancias activas. Verificar por telemetría/variables si alguna fue habilitada.
- OpenAI modelo Terra/Astra/Luna y sus rutas, presupuesto configurado; no exportar conversaciones privadas ni API keys.

## Herramientas y arquitectura
- `python -m pytest` / revisar `pyproject.toml` para comandos exactos.
- `npm ci && npm test`; `npx playwright test` con browsers disponibles; comandos de Actions son la referencia para CI.
- GitHub Pages despliega `web/` a staging/publicación; confirmar URL real/branch/paths.
- `src/radar_salud/` pipeline, `scripts/`, `config/` y `data/`; cuidar snapshots y generadores determinísticos. Ver `README.md` sólo como documentación histórica.
- `sql/` contiene esquema inicial pero requiere auditoría de despliegue antes de confiar en persistencia fuera de Git.
- No exponer material de usuarios/conversaciones, recibos pagados o documentos con copyright fuera de lo permitido.

## Riesgos que el nuevo ejecutor debe aceptar explícitamente
1. Daily First y autonomía semanal/día nunca se acreditan por un run único exitoso; dos ejecuciones válidas separadas >=24h y observación 7/7.
2. PR #29 no fusionado y dos defectos diarios precisos; no duplicar publicaciones pagadas.
3. Fuente bloqueada NO significa cero novedades; no sortear CloudFront/ALB, TLS o copyright.
4. IF10670 texto heredado REVISE; FEFI HOLD; modelos/metodología BCBSA Global HOLD.
5. Suscripción y pagos NO están habilitados; evitar CTA que prometa servicio inexistente.
6. El proyecto de Codex I no contiene trabajo de implementación en la rama inicial; no perseguir un PR inexistente. Si ya existe un PR nuevo al retomar, revalidar.
7. Preparar beta comercial requiere seguridad/privacidad/QA editorial operativo y autorización humana, nunca publicación implícita.

## Definition of Done del traspaso
- Claude puede explicar tesis, 6 servicios, MVP, plan comercial y roadmap sin consultar chats de ChatGPT.
- Clone completo y hash verificado, tests baseline, GitHub issue/PR/Actions visible.
- Matriz APIs/servicios y propietarios, secretos **sin valores**, owners y estados probados; plan para conectar faltantes.
- Distinción de staging/main/producción, pipeline editorial, derechos, QA/Reviewer y presupuestos vigente.
- Backlog priorizado de bloqueos reales con evidencia actual y responsables.
- Una primera PR documental o de bug pequeño creada desde Claude, revisada e integrada exclusivamente bajo autorización. No activar APIs ni despliegues de producción en la prueba.
