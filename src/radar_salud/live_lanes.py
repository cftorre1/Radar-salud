"""When the 27-oct-2026 network lanes (datos.gob.cl, CMF/SIS, Prestadores) run.

They run inside the real engine and never inside the test suite: a per-lane
variable (``1``/``0``) forces the choice; otherwise they run when the workflow
enables evidence capture (the daily and hourly jobs set
``RADAR_CAPTURE_EVIDENCE=1``) and no pytest test is executing. This needs no
workflow change on ``main``.
"""
from __future__ import annotations

import os


def enabled(flag, env=None):
    env = os.environ if env is None else env
    forced = env.get(flag)
    if forced in ("0", "1"):
        return forced == "1"
    return env.get("RADAR_CAPTURE_EVIDENCE") == "1" and "PYTEST_CURRENT_TEST" not in env
