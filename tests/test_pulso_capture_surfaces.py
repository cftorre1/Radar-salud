"""Verify capture provenance and robots without making live network requests."""
import gzip
import hashlib
import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location("capture_pulso_surfaces", Path(__file__).parents[1] / "scripts/capture_pulso_surfaces.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_capture_storage_preserves_original_bytes_and_is_deterministic(tmp_path):
    payload = b"<html>Original publisher evidence</html>"
    first = probe.save_response(tmp_path, payload)
    second = probe.save_response(tmp_path, payload)
    assert first == second
    assert gzip.decompress((tmp_path / first["gzip_file"]).read_bytes()) == payload
    assert first["sha256"] == hashlib.sha256(payload).hexdigest()


def test_official_routing_and_observed_sitemap_children():
    assert probe.official_url("/etiqueta/salud/") == probe.BASE + "/etiqueta/salud/"
    for url in ("http://www.latercera.com/a", "https://www.latercera.com.evil.test/a",
                "https://user@www.latercera.com/a", "https://www.latercera.com:443/a"):
        assert probe.official_url(url) is None
    xml = b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://www.latercera.com/arc/outboundfeeds/sitemap/?from=100</loc></sitemap><sitemap><loc>https://evil.test/other</loc></sitemap></sitemapindex>'
    observed = probe.describe(xml, probe.BASE, "application/xml")
    assert observed["xml_root"] == "sitemapindex"
    assert observed["xml_locations"] == [probe.BASE + "/arc/outboundfeeds/sitemap/?from=100"]


def test_robots_disallow_search_without_fetching(tmp_path):
    class NoNetwork:
        def open(self, request, timeout):
            raise AssertionError("robots-disallowed endpoint must never be requested")
    original = probe.SEEDS
    probe.SEEDS = ((probe.BASE + "/search/?q=salud", "search", "excluded"),)
    try:
        report = probe.capture(tmp_path, opener=NoNetwork())
    finally:
        probe.SEEDS = original
    assert report["responses"][0]["status"] == "skipped"
    assert report["responses"][0]["reason"] == "publisher_robots_disallow"
    assert report["coverage_complete_90_days"] is False
    assert report["ai_calls"] == 0


def test_declared_wildcard_query_exclusions_are_enforced():
    assert probe.publisher_excluded(probe.BASE + "/search/?q=salud")
    assert probe.publisher_excluded(probe.BASE + "/pf/api/v3/content/fetch")
    assert not probe.publisher_excluded(probe.BASE + "/arc/outboundfeeds/rss/?outputType=xml")
