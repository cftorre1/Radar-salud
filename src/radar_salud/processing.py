from __future__ import annotations

class DeferredProcessing(Exception):
    """The item was discovered correctly but must be retried later."""
    pass
