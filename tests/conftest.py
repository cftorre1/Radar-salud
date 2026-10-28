"""Test-wide setup.

Historical audits whose paywalled text was replaced by receipts (Dirección 28-oct-2026)
are re-verified from their exact pre-redaction git blobs (see
data/audits/rights_redacted_originals_2026_10_28.json); the runtime never does this.
"""
from pathlib import Path

import pytest

from radar_salud.pinned_evidence import install_original_audit_reader

install_original_audit_reader(Path(__file__).resolve().parents[1])


@pytest.fixture(autouse=True)
def _fresh_paywall_run_counter():
    """Each test is its own run for the per-run teaser re-analysis cap."""
    from radar_salud import pulso_paywall
    pulso_paywall.reset_run_counter()
    yield
    pulso_paywall.reset_run_counter()
