# Analytics beta · instrumentación preparada, no activada

`web/data/analytics.json` mantiene `enabled=false`, `privacy_approved=false` y la clave pública de proyecto vacía. El código no asigna identificadores, no guarda eventos, no llama al proveedor y no recoge correos hasta que Dirección apruebe proveedor y tratamiento de datos y se configure la integración. Un identificador nuevo por evento evita un perfil persistente cuando se autorice; la recurrencia es un booleano calculado de la preferencia de visita que la web ya conserva localmente. No transmite URL, título, ID de card, email, valores libres ni intereses individuales.

| Evento preparado | Activación del evento | Propiedades permitidas |
| --- | --- | --- |
| `visit` | página cargada | `returning` (booleano local) |
| `brief_open`, `brief_mark_read` | bandeja de 30 segundos | ninguna |
| `card_open`, `card_read_toggle` | card | ninguna |
| `source_click` | enlace de fuente | ninguna; no URL de destino |
| `facet_change`, `period_change`, `sort_change` | filtro de Explorar | ninguna |
| `preferences_open`, `preference_change` | personalización | solo `dimension` (tipo/ámbito) y `hidden` booleano |
| `email_signup_intent` | envío del formulario | ninguna; no acredita conversión confirmada |
| `premium_cta` | botón PREMIUM o «acceso anticipado» | ninguna |
| `newsletter_open` | enlace Newsletter | ninguna |
| `datos_ficha_open` | fila de ficha en Datos | ninguna; no el id de la ficha |
| `datos_serie_change` | selector de la serie 1990–2025 en Datos | ninguna; no la serie elegida |

**Propuesta 10-nov-2026 (no activada): proveedor `goatcounter`.** Sin cookies ni identificadores. `analytics.json` trae `provider="goatcounter"` y `goatcounter_endpoint=""`, con ambas banderas en `false`. Sólo se carga `https://gc.zgo.at/count.js` si `enabled` y `privacy_approved` son `true` y el endpoint es `https://<código>.goatcounter.com/count`. La página vista se cuenta con `location.pathname`, sin query ni `#`. Los eventos se envían como `evento/<nombre>`, sin propiedades. El proveedor `posthog` sigue disponible con sus mismas reglas.

Para medir conversión confirmada y gestión de suscriptores se necesitará evidencia del proveedor después de la aprobación humana. Para activar recolección real se requieren proveedor, clave pública, acuerdo/aviso de privacidad y decisión explícita de Dirección; ningún valor debe activarse como consecuencia automática del deploy.
