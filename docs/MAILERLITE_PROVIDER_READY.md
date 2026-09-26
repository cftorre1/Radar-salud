# MailerLite provider-ready — Alicanto Salud

Estado: preparado y **deshabilitado**. No se creó cuenta, no se guardaron secretos y no se activó captura ni envío.

## Separación de funnels

- `newsletter_weekly`: resumen semanal con consentimiento específico y doble opt-in.
- `early_access`: acceso anticipado, con grupo y consentimiento independientes.

Los identificadores de ambos grupos permanecen vacíos en `web/data/subscription.json`. No se reutiliza un consentimiento entre funnels.

## Activación mínima pendiente

1. Dirección crea o habilita la cuenta MailerLite y entrega por canal secreto `MAILERLITE_API_KEY`.
2. En MailerLite crea dos grupos separados y registra sus IDs en configuración segura.
3. Verifica `hola@alicantosalud.cl` como remitente y autentica `alicantosalud.cl` con los valores exactos entregados por MailerLite.
4. Dirección aprueba finalidad, retención, texto de consentimiento y doble opt-in.
5. Dirección confirma que el plan contratado permite `emails.*.content` por API. La documentación oficial limita esa capacidad al plan Advanced; no se debe contratar ni cambiar de plan sin autorización. Si el plan no la incluye, se debe elegir y probar un flujo oficial compatible antes de activar.
6. Solo entonces se cambian `capture_enabled`, `send_enabled`, `privacy_approved`, `sender.verified` y `api_html_content_supported` a `true`.

El sender crea una campaña regular para el grupo `newsletter_weekly` y luego solicita envío inmediato. Sin todos los gates —incluida la capacidad real del plan— ni siquiera intenta la red.

## DNS sin romper Google Workspace

- Mantener MX de Google, DKIM de Google y DMARC actuales.
- Publicar el CNAME DKIM y TXT de verificación **exactos** que muestre la cuenta MailerLite.
- Debe existir un solo TXT SPF en el apex. No agregar un segundo `v=spf1`: combinar el `include` exacto que entregue MailerLite con `include:_spf.google.com` en el registro existente y conservar un único `~all` final.
- No copiar valores genéricos de documentación a producción: registrar evidencia exacta desde la cuenta antes de modificar Cloudflare.

Referencias oficiales verificadas el 26-sep-2026:

- MailerLite API: `POST https://connect.mailerlite.com/api/campaigns` y `POST /api/campaigns/{id}/schedule`; `emails.*.content` requiere plan Advanced según la documentación vigente.
- MailerLite Subscribers: grupos distintos pueden asignarse al crear/actualizar suscriptores.
- MailerLite DNS: solo un registro SPF; si ya existe, debe combinarse en vez de duplicarse.
