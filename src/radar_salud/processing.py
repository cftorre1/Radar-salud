from __future__ import annotations

class DeferredProcessing(Exception):
    """The item was discovered correctly but must be retried later."""
    pass

class OutsideBackfillHorizon(Exception):
    """A verified publication date is older than the supported 90-day intake."""
