"""Daily First snapshot age checks; never updates captures or proves operation."""
from datetime import datetime, timedelta, timezone


def assess_snapshot(health: dict, now: datetime) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("observation time requires a timezone")
    result = {
        "observed_at": now.astimezone(timezone.utc).isoformat(),
        "checked_at": health.get("checked_at"),
        "age_seconds": None,
        "alert_at": None,
        "degrade_at": None,
        "evidence_freshness": "unverified_timestamp",
        "content_publication_dates_changed": False,
        "operation_proven_by_this_check": False,
        "cadence_proven_by_this_check": False,
        "existing_cadence_receipt": health.get("recurrent_operation_proven", False),
        "publication_authority": False,
    }
    try:
        checked = datetime.fromisoformat(str(health.get("checked_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return result
    if checked.tzinfo is None or checked.utcoffset() is None:
        return result
    age = (now - checked).total_seconds()
    if age < 0:
        result["evidence_freshness"] = "future_timestamp_hold"
        return result
    result.update(
        age_seconds=age,
        alert_at=(checked + timedelta(hours=24)).isoformat(),
        degrade_at=(checked + timedelta(hours=48)).isoformat(),
    )
    # A recent HTTP response cannot turn an incomplete or failed source into success.
    if (health.get("technical_status") != "ok"
            or health.get("coverage_completeness") != "complete"
            or health.get("pending_date_items", 0)
            or health.get("technical_failures")):
        result["evidence_freshness"] = "verification_hold"
    elif age >= 48 * 3600:
        result["evidence_freshness"] = "degraded_48h"
    elif age >= 24 * 3600:
        result["evidence_freshness"] = "alert_24h"
    else:
        result["evidence_freshness"] = "qualified_snapshot_within_24h"
    return result
