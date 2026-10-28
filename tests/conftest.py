"""Test-wide setup.

Historical audits whose paywalled text was replaced by receipts (Dirección 28-oct-2026)
are re-verified from their exact pre-redaction git blobs (see
data/audits/rights_redacted_originals_2026_10_28.json); the runtime never does this.
"""
from pathlib import Path

from radar_salud.pinned_evidence import install_original_audit_reader

install_original_audit_reader(Path(__file__).resolve().parents[1])
