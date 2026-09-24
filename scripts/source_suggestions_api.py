#!/usr/bin/env python3
"""Minimal same-origin adapter for the anonymous source suggestion service.

It is disabled unless explicitly enabled and is not started by the static Pages
workflow.  This keeps staging fail-closed until durable hosting and SMTP settings
are approved.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from radar_salud.source_suggestions import (
    SuggestionError,
    SuggestionThrottled,
    service_from_env,
)


MAX_BODY = 4096


class Handler(BaseHTTPRequestHandler):
    service = None

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/source-suggestions":
            self._json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._json(413, {"error": "invalid_body"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError
            suggestion = self.service.submit(payload)
        except SuggestionThrottled as exc:
            self._json(429, {"error": "throttled", "message": str(exc)})
        except SuggestionError as exc:
            self._json(422, {"error": "invalid", "message": str(exc)})
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self._json(400, {"error": "invalid_json"})
        except Exception:
            self._json(503, {"error": "unavailable", "message": "No pudimos guardar la sugerencia."})
        else:
            self._json(
                201,
                {
                    "id": suggestion.id,
                    "created_at": suggestion.created_at,
                    "status": suggestion.status,
                    "message": "Gracias. Guardamos tu sugerencia para revisión.",
                },
            )

    def log_message(self, fmt: str, *args: object) -> None:
        # Do not persist IP addresses or user agents in application logs.
        return


def main() -> None:
    if os.environ.get("SOURCE_SUGGESTIONS_ENABLED", "").lower() != "true":
        raise SystemExit("Source suggestions API is disabled")
    Handler.service = service_from_env()
    host = os.environ.get("SOURCE_SUGGESTIONS_HOST", "127.0.0.1")
    port = int(os.environ.get("SOURCE_SUGGESTIONS_PORT", "8080"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
