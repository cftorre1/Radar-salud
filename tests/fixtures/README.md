# Fixtures de prueba

## Prensa con muro de pago: contenido [Sintético]

Dirección decidió el 28-oct-2026 tratar como prensa con muro de pago a Diario
Financiero (df.cl) y a La Tercera (todas sus secciones). Las fixtures de esas
fuentes (`pulso_*`, `df_*`, `product_editorial_v3_cases.json`) son
**[Sintético]**: el cuerpo, los pies de foto, las etiquetas y los módulos de la
página no son texto publicado. Los historiales de git no se reescribieron, así
que esta limpieza afecta solo al árbol de trabajo.

### Qué se conserva

- Lo que la política de derechos (`config/paywalled_press.json`) declara
  público: título, URL y bajada pública del editor (`og:description`, meta
  `description`, `description` de JSON-LD). Son además las identidades con las
  que `data/` registra cada pieza.
- La estructura que ejercitan los parsers: etiquetas, clases, atributos,
  bloques JSON-LD y `<script>`, la API Arc (`content_elements`), campos
  `meta`/`og:*` y los marcadores de bloqueo y muro de pago (`#articleLock`,
  `isAccessibleForFree`, `content_tier`).
- Las fechas, las horas, los números, las entidades HTML, los escapes `\uXXXX`
  y los espacios.
- Las palabras a las que reacciona el código: palabras clave de las
  expresiones regulares y literales de `src/`, nombres de sección y meses, y
  las palabras funcionales del castellano.
- Los nombres de archivo direccionados por contenido, que siguen siendo el
  sha256 de la captura original.

Cada otra palabra es una pseudo-palabra de la misma longitud, con el mismo
patrón de mayúsculas y tildes. Se reemplaza siempre igual en todas las
fixtures, así que las citas de las salidas pagadas siguen coincidiendo con el
cuerpo. La clave de la sustitución no está en el repositorio.

### Procedencia mediante recibos

`SYNTHETIC_PAYWALLED_FIXTURES.json` contiene dos tablas:

- `files`: por archivo, el sha256 de los bytes sintéticos (`synthetic_sha256`)
  y el de la captura original (`original_sha256`).
- `receipts`: sha256(valor sintético) → sha256(valor original), para cada valor
  cuyo hash original está fijado en el repositorio. Cubre los bytes, la página
  descomprimida, el cuerpo y el título analizados, y los objetos y textos JSON
  canónicos.

`tests/synthetic_receipts.py` (instalado desde `tests/conftest.py`) hace que,
solo en los tests, `hashlib.sha256` devuelva para un valor sintético registrado
el hash de la captura original que representa. Cualquier otro valor conserva su
hash real, así que un archivo alterado sigue fallando. Las pruebas de
procedencia verifican entonces que el archivo sea el sustituto sintético
registrado de la captura X. El runtime nunca importa este módulo.

`tests/test_synthetic_paywalled_fixtures.py` falla en estos casos:

- una fixture menciona un host con muro de pago y no está registrada;
- un archivo cambia de bytes;
- un recibo es inconsistente;
- queda una oración de las huellas de redacción
  (`data/audits/paywalled_body_fingerprints_*.json`).

### Agregar fixtures nuevas

Nunca se debe commitear una captura real de df.cl o latercera.com. Una
fixture nueva debe ser sintética desde el origen y debe registrarse con sus
recibos.
