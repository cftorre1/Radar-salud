# Alicanto Salud · Servicios y cuentas

Inventario permanente. **Nunca** registrar contraseñas, tokens ni API keys aquí: solo nombres de variables. Credenciales en gestor de contraseñas y GitHub Secrets.
Estados: OPERATIVO VERIFICADO / CUENTA EXISTE (declarada por Dirección) / CONFIGURADO SIN PROBAR / PLANEADO / DESHABILITADO.
Actualizado: 2026-10-24 (Claude). Titular, facturación y recuperación deben completarse por Dirección.

| Servicio | Finalidad | Estado | Variable / secreto | Titular admin | Costo mensual | Facturación | Recuperación | Notas |
|---|---|---|---|---|---|---|---|---|
| GitHub (`cftorre1/Radar-salud`) | Código, Actions, Pages | OPERATIVO VERIFICADO | `GITHUB_TOKEN` (automático) | cftorre1 | Plan Free | — | — | Repo público. Ramas sin protección (24-oct). Cron de main desactivados manualmente el 24-oct |
| GitHub Pages | Hosting del sitio y `/staging/` | OPERATIVO VERIFICADO | — | cftorre1 | Gratis (repo público) | — | — | Último preview exitoso 12-oct |
| alicantosalud.cl | Dominio y sitio | OPERATIVO (sitio responde, 24-oct) | — | por completar | — | — | — | Sin `CNAME` versionado en el repo; verificar en Pages/Cloudflare |
| NIC Chile | Registro del dominio | CUENTA EXISTE | — | por completar | Anual | — | — | Verificar fecha de renovación |
| Cloudflare | DNS del dominio | CUENTA EXISTE | — | por completar | — | — | — | Verificar registros, SPF/DKIM/DMARC |
| Google Workspace | Correo `hola@alicantosalud.cl` | CUENTA EXISTE | — | por completar | — | — | — | Remitente previsto del newsletter, no verificado |
| OpenAI API | Análisis FAST (gpt-5.6-luna) y DEEP (gpt-5.6-terra) | CONFIGURADO; última llamada registrada 12-oct | `OPENAI_API_KEY` | por completar | ~USD 2 histórico; tope declarado USD 10/semana | — | — | HOLD sin cambios hasta benchmark ciego vs Claude |
| Anthropic (Claude, Claude Code) | Orquestación, desarrollo, revisión | CUENTA EXISTE; GitHub conectado 24-oct | API no configurada | cftorre1 | Plan de suscripción | — | — | API solo tras aprobación y benchmark |
| Buttondown | Envío semanal (código en `main`) | DESCONOCIDO | `BUTTONDOWN_API_KEY` | por completar | — | — | — | `weekly-digest.yml` de main publicaba directo; desactivado el 24-oct. Confirmar si la cuenta existe |
| MailerLite | Suscripciones y resumen semanal | DESHABILITADO | `MAILERLITE_API_KEY` | — | — | — | — | `web/data/subscription.json`: captura y envío en false, sin grupos ni remitente verificado |
| PostHog | Analítica | CONFIGURADO SIN KEY | project key | — | — | — | — | Requiere revisión de privacidad/consentimiento |
| Supabase / PostgreSQL | Persistencia, usuarios, autenticación | PLANEADO | — | — | — | — | — | Solo `sql/001_schema.sql` |
| WhatsApp Business API | Alertas | DESHABILITADO | — | — | — | — | — | Fuera del MVP |
| Mercado Público API | Licitaciones | PLANEADO | ticket no verificado | — | — | — | — | Integración futura |
| Pagos / facturación | Planes FREE/PREMIUM | PLANEADO | — | — | — | — | — | Requiere decisión de proveedor y precios |
