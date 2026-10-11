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


def test_sitemap_primary_urls_exclude_images_and_keep_news_publication_evidence():
    xml = b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
      xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"
      xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
      <url><loc>https://www.latercera.com/nacional/noticia/clinica/</loc>
      <lastmod>2026-10-11T08:00:00Z</lastmod>
      <news:news><news:publication_date>2026-10-10T10:00:00-03:00</news:publication_date>
      <news:title>Clinica title</news:title><news:keywords>salud, prestadores</news:keywords></news:news>
      <image:image><image:loc>https://www.latercera.com/resizer/image.jpg</image:loc></image:image>
      </url></urlset>'''
    observed = probe.describe(xml, probe.BASE, "application/xml")
    assert observed["xml_location_count"] == 1
    assert observed["xml_locations"] == [probe.BASE + "/nacional/noticia/clinica/"]
    assert observed["xml_entries"] == [{
        "url": probe.BASE + "/nacional/noticia/clinica/",
        "lastmod": "2026-10-11T08:00:00Z",
        "publication_date": "2026-10-10T10:00:00-03:00",
        "title": "Clinica title", "keywords": "salud, prestadores"}]


def test_empty_archive_page_is_observed_without_inventing_article_entries():
    observed = probe.describe(
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>',
        probe.EXTENDED_BOUNDARIES[0], "application/xml")
    assert observed["xml_root"] == "urlset"
    assert observed["xml_location_count"] == 0
    assert observed["xml_locations"] == observed["xml_entries"] == []


def test_rss_enumerates_all_primary_articles_with_date_and_body_provenance():
    xml = b'''<rss xmlns:content="http://purl.org/rss/1.0/modules/content/" version="2.0"><channel>
      <item><title>Untitled strategic signal</title><link>https://www.latercera.com/pulso/noticia/one/</link>
      <guid>https://www.latercera.com/pulso/noticia/one/</guid><pubDate>Sat, 10 Oct 2026 23:35:58 +0000</pubDate>
      <category>Pulso</category><description>Issuer debt restructuring</description>
      <content:encoded><![CDATA[<p>Full primary article body about hospital financing.</p>]]></content:encoded></item>
      <item><title>Second signal</title><link>https://www.latercera.com/nacional/noticia/two/</link>
      <pubDate>Fri, 09 Oct 2026 12:00:00 +0000</pubDate><category>Nacional</category>
      <content:encoded><![CDATA[<p>Second primary body</p>]]></content:encoded></item>
      <item><link>https://evil.test/article/</link></item></channel></rss>'''
    observed = probe.describe(xml, probe.BASE, "application/xml")
    assert observed["xml_root"] == "rss"
    assert observed["xml_location_count"] == 2
    entries = observed["xml_entries"]
    assert entries[0]["pubDate"] == "Sat, 10 Oct 2026 23:35:58 +0000"
    assert entries[0]["category"] == ["Pulso"]
    body = "<p>Full primary article body about hospital financing.</p>"
    assert entries[0]["content_encoded_excerpt"] == body
    assert entries[0]["content_encoded_characters"] == len(body)
    assert entries[0]["content_encoded_sha256"] == hashlib.sha256(body.encode()).hexdigest()
    assert "publication_date" not in entries[0]
