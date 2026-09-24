# Sugerencias anónimas de fuentes

La portada incluye el CTA y el formulario, pero GitHub Pages no ejecuta el
endpoint de persistencia. El navegador usa `POST /api/source-suggestions` y,
si no recibe confirmación `201`, informa que el envío no está habilitado y no
simula almacenamiento.

## Datos almacenados

El servicio guarda solo `id`, timestamp UTC, nombre/URL de la fuente,
comentario, estado de gestión y estado de notificación. No guarda nombre de
persona, correo, IP, user-agent, cookie ni referrer.

## Activación pendiente de autorización

El adaptador puede arrancarse con:

```bash
SOURCE_SUGGESTIONS_ENABLED=true \
SOURCE_SUGGESTIONS_DB_PATH=/ruta/durable/suggestions.sqlite3 \
python scripts/source_suggestions_api.py
```

La notificación interna queda provider-ready y apagada por defecto. Requiere
una decisión de hosting, destinatario interno y credenciales SMTP:

```text
SOURCE_SUGGESTIONS_SMTP_ENABLED=true
SMTP_HOST
SMTP_PORT
SMTP_FROM
SMTP_USERNAME
SMTP_PASSWORD
SOURCE_SUGGESTIONS_NOTIFY_TO
```

No se agrega ningún secreto al repositorio. El equipo puede listar o cambiar
el estado de gestión directamente sobre el almacenamiento autorizado con
`scripts/source_suggestions_admin.py`.
