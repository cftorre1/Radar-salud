"""Replay the DEIS transport checkpoint without changing TLS verification."""
import json
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


URLS = [
    "https://deis.minsal.cl/",
    "http://deis.minsal.cl/",
    "https://deis.minsal.cl/centrofic/",
    "https://deis.minsal.cl/feed/",
    "https://deis.minsal.cl/wp-json/wp/v2/posts?per_page=5&_fields=id,date,modified,title,link",
    "https://repositoriodeis.minsal.cl/",
    "https://repositoriodeis.minsal.cl/ContenidoSitioWeb2020/uploads/2021/03/Orientaciones%20de%20codificaci%C3%B3n%20para%20el%20Cap%C3%ADtulo%20XXI%20junio2026.pdf",
]
USER_AGENTS = ["RadarSaludBot/0.1 (+public-source-monitor)", "Mozilla/5.0"]


def main():
    rows = []
    for url in URLS:
        for user_agent in USER_AGENTS:
            row = {
                "url": url, "user_agent": user_agent,
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                "tls_verification": "ssl.create_default_context(); verification enabled",
            }
            try:
                request = urllib.request.Request(url, headers={
                    "User-Agent": user_agent,
                    "Accept": "text/html,application/rss+xml,application/json,application/pdf;q=0.9,*/*;q=0.8",
                })
                with urllib.request.urlopen(request, timeout=15, context=ssl.create_default_context()) as response:
                    row.update(status=response.status, headers=dict(response.headers), final_url=response.url,
                               first_bytes=response.read(128).hex())
            except Exception as exc:
                row.update(error_type=type(exc).__name__, error=str(exc))
                if isinstance(exc, urllib.error.HTTPError):
                    row.update(status=exc.code, headers=dict(exc.headers),
                               response_body=exc.read(500).decode("utf-8", "replace"))
            rows.append(row)
    target = Path(__file__).with_name("deis_network_probe.json")
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(target), "attempts": len(rows), "completed": True}))


if __name__ == "__main__":
    main()
