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
def _no_provider_key(monkeypatch):
    """Tests never see the runner's real AI key (daily run 29-oct: with the key present, export tests made real
    translation calls and Pulso replays reached the model branch). A test that needs a key sets it itself."""
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _fresh_paywall_run_counter():
    """Each test is its own run for the per-run teaser re-analysis cap."""
    from radar_salud import pulso_paywall
    pulso_paywall.reset_run_counter()
    yield
    pulso_paywall.reset_run_counter()


# --- Rights policy version under test -------------------------------------------------
# Dirección 28-oct-2026 (policy 1.3.0): every latercera.com section, metered ones
# included, is paid (title + public lead + date + link + receipt). The pinned Pulso
# replay/regression tests below exercise pipeline logic (liveblog dates, paid
# revalidation chains, materiality...) on real La Tercera pieces that were OPEN under
# policy 1.2.0 (premium prefixes/sections/article flag only). They keep running against
# that historical scope (and with per-article flags recorded as evidence only, as those
# captures were taken) so the code paths stay covered; they do not describe production.
# Rights tests (CURRENT_POLICY_MODULES or ``@pytest.mark.current_rights_policy``) and
# tests/test_paywall_metered_20261028.py assert the current, host-wide policy.
CURRENT_POLICY_MODULES = {"test_paywall_rights_v2_20261028", "test_paywall_rights_v3_20261028",
                          "test_paywall_rights_v4_20261028", "test_paywall_rights_v5_20261028",
                          "test_paywall_metered_20261028",
                          "test_source_links_paywall_20261028", "test_web_snapshot"}


def pytest_configure(config):
    config.addinivalue_line("markers", "current_rights_policy: run against config/paywalled_press.json as is")


@pytest.fixture(autouse=True)
def _rights_policy_scope(request, monkeypatch):
    module = request.module.__name__.rsplit(".", 1)[-1]
    if module in CURRENT_POLICY_MODULES or request.node.get_closest_marker("current_rights_policy"):
        yield
        return
    from radar_salud import source_rights
    for rule in source_rights.load_policy()["sources"]:
        if rule.get("metered_sections_paywalled"):
            monkeypatch.setitem(rule, "scope", "path_prefix_section_or_article_flag")
            monkeypatch.setitem(rule, "metered_sections_paywalled", False)
    # Those pinned captures predate per-article flag capture (review 3): replay them as
    # captured then -- the access record is kept as evidence, the flags do not decide.
    original_flags = source_rights.publisher_access_flags

    def evidence_only(*args, **kwargs):
        out = original_flags(*args, **kwargs)
        for key in ("isAccessibleForFree", "publisher_paywall", "content_tier"):
            out.pop(key, None)
        return out

    monkeypatch.setattr(source_rights, "publisher_access_flags", evidence_only)
    # ... and the sentence-overlap rule: since policy 1.3.0 every La Tercera body is
    # fingerprinted, so each replayed piece would match its own sentences.
    monkeypatch.setattr(source_rights, "_runtime_fingerprints", lambda: frozenset())
    yield
