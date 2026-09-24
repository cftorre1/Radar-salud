"""Anonymous source suggestions with durable, PII-minimized storage.

The public site is static, so this module deliberately does not pretend that a
browser submission was stored.  A hosting provider can expose the small API
adapter in ``scripts/source_suggestions_api.py`` once storage and SMTP settings
are approved.  Until then the browser stays fail-closed.
"""

from __future__ import annotations

import os
import smtplib
import sqlite3
import ssl
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Mapping, Protocol
from urllib.parse import urlparse


class SuggestionError(ValueError):
    """A safe validation error that may be returned to the client."""


class SuggestionThrottled(SuggestionError):
    """The anonymous global rate gate rejected the submission."""


def _text(value: object, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SuggestionError("Los campos deben enviarse como texto.")
    value = " ".join(value.strip().split())
    if len(value) > limit:
        raise SuggestionError("Uno de los campos supera el largo permitido.")
    return value


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise SuggestionError("No pudimos validar el tiempo del formulario.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SuggestionError("No pudimos validar el tiempo del formulario.") from exc
    if parsed.tzinfo is None:
        raise SuggestionError("No pudimos validar el tiempo del formulario.")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Suggestion:
    id: str
    created_at: str
    source_name: str
    source_url: str
    comment: str
    status: str = "received"
    notification_status: str = "pending"


class SuggestionStore(Protocol):
    def save(self, suggestion: Suggestion) -> None: ...

    def set_notification(self, suggestion_id: str, status: str, error: str = "") -> None: ...


class SuggestionNotifier(Protocol):
    def send(self, suggestion: Suggestion) -> None: ...


class GlobalRateGate:
    """Bound bursts without creating or retaining a user identifier."""

    def __init__(self, limit: int = 20, window_seconds: int = 60):
        self.limit = limit
        self.window = timedelta(seconds=window_seconds)
        self._events: deque[datetime] = deque()
        self._lock = threading.Lock()

    def admit(self, now: datetime) -> None:
        with self._lock:
            cutoff = now - self.window
            while self._events and self._events[0] <= cutoff:
                self._events.popleft()
            if len(self._events) >= self.limit:
                raise SuggestionThrottled("Hay demasiados envíos en este momento. Inténtalo más tarde.")
            self._events.append(now)


class SqliteSuggestionStore:
    """Durable own storage; intentionally contains no IP, email or user agent."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS source_suggestions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('received','reviewing','accepted','rejected')),
                    notification_status TEXT NOT NULL CHECK(notification_status IN ('pending','sent')),
                    notification_error TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def save(self, suggestion: Suggestion) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_suggestions
                    (id, created_at, source_name, source_url, comment, status, notification_status)
                VALUES (:id, :created_at, :source_name, :source_url, :comment, :status, :notification_status)
                """,
                asdict(suggestion),
            )

    def set_notification(self, suggestion_id: str, status: str, error: str = "") -> None:
        if status not in {"pending", "sent"}:
            raise ValueError("invalid notification status")
        with self._connect() as connection:
            connection.execute(
                """UPDATE source_suggestions
                   SET notification_status = ?, notification_error = ?
                   WHERE id = ?""",
                (status, error, suggestion_id),
            )

    def list(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM source_suggestions ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def set_status(self, suggestion_id: str, status: str) -> bool:
        if status not in {"received", "reviewing", "accepted", "rejected"}:
            raise ValueError("invalid suggestion status")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE source_suggestions SET status = ? WHERE id = ?",
                (status, suggestion_id),
            )
        return cursor.rowcount == 1


class SmtpSuggestionNotifier:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        recipient: str,
        username: str = "",
        password: str = "",
    ):
        self.host = host
        self.port = port
        self.sender = sender
        self.recipient = recipient
        self.username = username
        self.password = password

    def send(self, suggestion: Suggestion) -> None:
        message = EmailMessage()
        message["Subject"] = f"Nueva sugerencia de fuente · {suggestion.id}"
        message["From"] = self.sender
        message["To"] = self.recipient
        message.set_content(
            "\n".join(
                [
                    f"ID: {suggestion.id}",
                    f"Fecha UTC: {suggestion.created_at}",
                    f"Fuente: {suggestion.source_name or 'No indicada'}",
                    f"URL: {suggestion.source_url or 'No indicada'}",
                    f"Comentario: {suggestion.comment or 'Sin comentario'}",
                    "Estado inicial: received",
                ]
            )
        )
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=10) as smtp:
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> SmtpSuggestionNotifier | None:
        if env.get("SOURCE_SUGGESTIONS_SMTP_ENABLED", "").lower() != "true":
            return None
        required = ["SMTP_HOST", "SMTP_FROM", "SOURCE_SUGGESTIONS_NOTIFY_TO"]
        missing = [key for key in required if not env.get(key)]
        if missing:
            raise RuntimeError("SMTP de sugerencias habilitado sin configuración completa")
        return cls(
            host=env["SMTP_HOST"],
            port=int(env.get("SMTP_PORT", "465")),
            sender=env["SMTP_FROM"],
            recipient=env["SOURCE_SUGGESTIONS_NOTIFY_TO"],
            username=env.get("SMTP_USERNAME", ""),
            password=env.get("SMTP_PASSWORD", ""),
        )


class SourceSuggestionService:
    def __init__(
        self,
        store: SuggestionStore,
        notifier: SuggestionNotifier | None = None,
        *,
        now: Callable[[], datetime] | None = None,
        gate: GlobalRateGate | None = None,
    ):
        self.store = store
        self.notifier = notifier
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.gate = gate or GlobalRateGate()

    def submit(self, payload: Mapping[str, object]) -> Suggestion:
        current = self.now().astimezone(timezone.utc)
        if _text(payload.get("website"), 120):
            raise SuggestionThrottled("No pudimos procesar el envío.")
        started = _parse_time(payload.get("started_at"))
        elapsed = current - started
        if elapsed < timedelta(seconds=2) or elapsed > timedelta(hours=1):
            raise SuggestionThrottled("No pudimos validar el envío. Recarga el formulario.")
        self.gate.admit(current)

        source_name = _text(payload.get("source_name"), 160)
        source_url = _text(payload.get("source_url"), 500)
        comment = _text(payload.get("comment"), 800)
        if not source_name and not source_url:
            raise SuggestionError("Indica el nombre de la fuente o su URL.")
        if source_url:
            parsed = urlparse(source_url)
            if parsed.scheme != "https" or not parsed.hostname:
                raise SuggestionError("La URL debe ser un enlace HTTPS válido.")

        suggestion = Suggestion(
            id=f"src_{uuid.uuid4().hex}",
            created_at=current.isoformat().replace("+00:00", "Z"),
            source_name=source_name,
            source_url=source_url,
            comment=comment,
        )
        self.store.save(suggestion)
        if self.notifier is not None:
            try:
                self.notifier.send(suggestion)
            except Exception:
                self.store.set_notification(suggestion.id, "pending", "notification_failed")
            else:
                self.store.set_notification(suggestion.id, "sent")
                suggestion = Suggestion(**{**asdict(suggestion), "notification_status": "sent"})
        return suggestion


def service_from_env(env: Mapping[str, str] = os.environ) -> SourceSuggestionService:
    path = Path(env.get("SOURCE_SUGGESTIONS_DB_PATH", "data/source_suggestions.sqlite3"))
    return SourceSuggestionService(
        SqliteSuggestionStore(path),
        SmtpSuggestionNotifier.from_env(env),
    )
