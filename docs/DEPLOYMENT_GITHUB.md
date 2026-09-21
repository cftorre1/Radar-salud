# Subida inicial a GitHub

Repositorio esperado: cftorre1/Radar-salud

## Opción web de GitHub
1. Descomprimir el ZIP localmente.
2. Abrir el repositorio Radar-salud.
3. Add file > Upload files.
4. Arrastrar TODOS los archivos y carpetas que están dentro de `radar-salud-github-upload` (no subir el ZIP ni una carpeta contenedora adicional).
5. Commit directly to `main` con mensaje: `Initial Radar Salud V2 pilot`.

## Verificación inmediata
- Deben verse en la raíz: `.github`, `config`, `docs`, `scripts`, `sql`, `src`, `tests`, `web`, `README.md`, `pyproject.toml`.
- Ir a Actions y confirmar que el workflow `daily-radar` aparece.
- La primera prioridad es que los tests pasen antes de activar fuentes reales.

## GitHub Pages
La web estática vive en `/web`. La publicación en Pages se configura después de validar el workflow y la generación de `web/data/radar_today.json`.

## Secretos futuros
No subir claves al repositorio. Tickets/API keys se guardan en Settings > Secrets and variables > Actions.
Ejemplo futuro: `MERCADO_PUBLICO_TICKET`.
