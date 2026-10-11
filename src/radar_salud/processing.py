from __future__ import annotations

class DeferredProcessing(Exception):
    """The item was discovered correctly but must be retried later."""
    def __init__(self, message="Processing deferred", *, reason=None):
        super().__init__(message)
        self.reason = reason


class RejectedProcessing(Exception):
    """An evaluated candidate has a durable, document-specific rejection reason."""
    pass

class OutsideBackfillHorizon(Exception):
    """A verified publication date is older than the supported 90-day intake."""
