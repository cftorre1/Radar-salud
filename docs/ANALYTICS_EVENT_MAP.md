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

Para medir conversión confirmada y gestión de suscriptores se necesitará evidencia del proveedor después de la aprobación humana. Para activar recolección real se requieren proveedor, clave pública, acuerdo/aviso de privacidad y decisión explícita de Dirección; ningún valor debe activarse como consecuencia automática del deploy.
