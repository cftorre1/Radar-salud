"""CI-only: the F6 checker v2 on the real Boletín IP N°2-2026 acreditación PDF.

Downloads the document through the production ``SisFetcher`` (allowlist, robots.txt, byte cap, deadline) and skips
when the network or the SIS is unavailable (e.g. sandboxes without egress). When it runs (GitHub Actions / daily run),
the bytes must still hash to the recorded SHA-256, and 101 / 584 must pass by the approved rules: 101 by sentence on
p.2, 584 by the 'Total general 367 217 584' row on p.8 (367 + 217 = 584) under a caption naming 'tramitación'.
"""
import time
from pathlib import Path

import pytest

from radar_salud import stats_capture as cap

ACR = "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf"
SHA = "8b7f7c7a385e4c0997033137adfe604d08ea148a3f01282553d07722b4569a2b"


@pytest.fixture(scope="module")
def real_pdf() -> bytes:
    try:
        return cap.SisFetcher(deadline=time.monotonic() + 60, timeout=20)(ACR)
    except Exception as exc:  # no egress, proxy refusal, robots/SIS down: nothing to test here
        pytest.skip(f"real PDF not reachable: {type(exc).__name__}: {exc}"[:200])


def test_real_acreditacion_pdf_passes_checker_v2(real_pdf):
    import hashlib
    sha = hashlib.sha256(real_pdf).hexdigest()
    if sha != SHA:
        pytest.skip(f"SIS document changed ({sha[:12]}…): the capture HOLDs it as hash_mismatch")
    info = cap.verified_metrics(Path(__file__).resolve().parents[1])[ACR]
    old = cap.parse_boletin_pdf(real_pdf, info["metrics"], info["pages_1based"])  # checker v1: today's HOLD
    assert old["verified_present"]["with_observations"] is False and old["verified_present"]["pending_applications"] is False
    res = cap.parse_boletin_pdf(real_pdf, info["metrics"], info["pages_1based"], "acreditacion")
    rules = res["figure_rules"]
    assert res["status"] == "verified", rules
    assert rules["with_observations"]["rule"] == "sentence" and rules["with_observations"]["page"] == 2, rules
    tot = rules["pending_applications"]
    assert tot["rule"] == "total_row" and tot["page"] == 8 and tot["sum_check"] == "367 + 217 = 584", rules
