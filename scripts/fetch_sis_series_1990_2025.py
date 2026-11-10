"""Descarga las "Series estadísticas del sistema Isapre 1990-2025" (Superintendencia de Salud) con recibos.

Fuente única: la página de la biblioteca digital SIS ``SERIES_PAGE``. Se descarga la página (robots.txt honrado con el
User-Agent del bot, falla cerrada) y luego cada archivo .xlsx/.xls/.pdf enlazado desde ella en el host de la SIS; no se
infiere ninguna URL. Cada archivo queda con URL, estado HTTP, bytes, SHA-256 y Last-Modified en ``receipts.json``.
Se ejecuta en GitHub Actions (el sandbox no alcanza superdesalud.gob.cl).
"""
from __future__ import annotations

import hashlib
import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_sis_open_data as base  # noqa: E402

SERIES_PAGE = "https://www.superdesalud.gob.cl/biblioteca-digital/series-estadisticas-del-sistema-isapre-1990-2025/"
HOST = "www.superdesalud.gob.cl"
OUT = Path(__file__).resolve().parents[1] / "data" / "reference" / "sis_series_1990_2025"
LIMIT = 40 * 1024 * 1024
EXT = (".xlsx", ".xls", ".pdf", ".csv")


def links(page_html: str) -> list[str]:
    seen, out = set(), []
    for m in re.findall(r'href=["\']([^"\']+)["\']', page_html):
        u = urljoin(SERIES_PAGE, html.unescape(m)).split("#")[0]
        p = urlparse(u)
        if p.netloc == HOST and p.path.lower().endswith(EXT) and "/app/uploads/" in p.path and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def safe_name(url: str) -> str:
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ok, why = base.allowed(SERIES_PAGE)
    page = {"url": SERIES_PAGE, "robots": why}
    files = []
    if ok:
        status, body, headers = base.get(SERIES_PAGE, limit=8 * 1024 * 1024, timeout=60)
        page.update(status=status, bytes=len(body), sha256=hashlib.sha256(body).hexdigest(),
                    last_modified=headers.get("Last-Modified"))
        if status == 200:
            (OUT / "pagina_series.html").write_bytes(body)
            page["archivo"] = "pagina_series.html"
            for url in links(body.decode("utf-8", "replace")):
                dest = OUT / safe_name(url)
                rec = {"archivo": dest.name, **base.download(url, dest, LIMIT)}
                if "error" in rec and dest.exists():
                    dest.unlink()
                files.append(rec)
                print({k: rec.get(k) for k in ("archivo", "status", "bytes", "robots", "error")}, flush=True)
        else:
            page["error"] = f"http_{status}"
    else:
        page["error"] = "robots_blocked"
    base.write_json(OUT / "receipts.json", {
        "fuente": "Superintendencia de Salud, biblioteca digital: Series estadísticas del sistema Isapre 1990-2025",
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "user_agent": base.UA,
        "requested_by": "Plan comercial (Datos: series históricas 1990-2025)",
        "pagina": page, "archivos": files})
    print({"pagina": {k: page.get(k) for k in ("status", "robots", "error")}, "archivos": len(files),
           "errores": sum("error" in f for f in files)})
    return 0 if ok and page.get("status") == 200 and files else 1


if __name__ == "__main__":
    raise SystemExit(main())
