import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from radar_salud.source_suggestions import (
    GlobalRateGate,
    SourceSuggestionService,
    SqliteSuggestionStore,
    SuggestionError,
    SuggestionThrottled,
)


NOW = datetime(2026, 9, 24, 23, 40, tzinfo=timezone.utc)


def payload(**changes):
    base = {
        "source_name": "Observatorio de Salud",
        "source_url": "https://example.org/publicaciones",
        "comment": "Revisar sus informes trimestrales.",
        "website": "",
        "started_at": (NOW - timedelta(seconds=4)).isoformat(),
    }
    base.update(changes)
    return base


class RecordingNotifier:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    def send(self, suggestion):
        if self.fail:
            raise RuntimeError("provider down")
        self.sent.append(suggestion)


def service(tmp_path, notifier=None, gate=None):
    store = SqliteSuggestionStore(tmp_path / "suggestions.sqlite3")
    return SourceSuggestionService(store, notifier, now=lambda: NOW, gate=gate), store


def test_anonymous_submission_is_traceable_and_notified_without_pii(tmp_path):
    notifier = RecordingNotifier()
    target, store = service(tmp_path, notifier)

    created = target.submit(payload())
    rows = store.list()

    assert created.id.startswith("src_")
    assert created.notification_status == "sent"
    assert len(rows) == 1
    assert rows[0]["status"] == "received"
    assert rows[0]["notification_status"] == "sent"
    assert rows[0]["source_url"] == "https://example.org/publicaciones"
    assert set(rows[0]) == {
        "id",
        "created_at",
        "source_name",
        "source_url",
        "comment",
        "status",
        "notification_status",
        "notification_error",
    }
    assert notifier.sent[0].id == created.id


def test_name_or_https_url_is_required_and_identity_fields_are_not_stored(tmp_path):
    target, store = service(tmp_path)
    with pytest.raises(SuggestionError, match="nombre de la fuente o su URL"):
        target.submit(payload(source_name="", source_url=""))
    with pytest.raises(SuggestionError, match="HTTPS"):
        target.submit(payload(source_name="", source_url="http://example.org"))

    target.submit({**payload(source_url=""), "email": "should-not-be-stored@example.org", "name": "Persona"})
    row = store.list()[0]
    assert "email" not in row
    assert "name" not in row
    assert "Persona" not in str(row)


def test_honeypot_fill_time_and_global_rate_gate_reject_abuse(tmp_path):
    target, _ = service(tmp_path, gate=GlobalRateGate(limit=1, window_seconds=60))
    with pytest.raises(SuggestionThrottled):
        target.submit(payload(website="spam"))
    with pytest.raises(SuggestionThrottled):
        target.submit(payload(started_at=(NOW - timedelta(milliseconds=100)).isoformat()))

    target.submit(payload())
    with pytest.raises(SuggestionThrottled, match="demasiados"):
        target.submit(payload(source_name="Otra fuente"))


def test_notification_failure_keeps_durable_record_pending(tmp_path):
    target, store = service(tmp_path, RecordingNotifier(fail=True))
    created = target.submit(payload())
    row = store.list()[0]
    assert created.status == "received"
    assert row["notification_status"] == "pending"
    assert row["notification_error"] == "notification_failed"


def test_internal_status_workflow_is_separate_from_editorial_publication(tmp_path):
    target, store = service(tmp_path)
    created = target.submit(payload())
    assert store.set_status(created.id, "reviewing") is True
    assert store.set_status(created.id, "accepted") is True
    assert store.list()[0]["status"] == "accepted"
    with pytest.raises(ValueError):
        store.set_status(created.id, "published")


def test_sqlite_schema_has_no_deliberate_identity_or_request_metadata(tmp_path):
    _, store = service(tmp_path)
    with sqlite3.connect(store.path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(source_suggestions)")}
    assert not columns.intersection({"email", "name", "ip", "user_agent", "cookie", "referrer"})
