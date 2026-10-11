"""Unconditional capture and diagnostic tests; no network or AI is used here."""
import gzip
import hashlib
import importlib.util
import io
import json
from email.message import Message
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("capture_pulso_targeted_primary", ROOT / "scripts/capture_pulso_targeted_primary.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def response(payload, url, status=200):
    class Response(io.BytesIO):
        headers = Message()
        headers["Content-Type"] = "text/html; charset=utf-8"
        def geturl(self):
            return url
    item = Response(payload)
    item.status = status
    return item


def test_original_bytes_are_saved_before_diagnostic_parser_can_fail(tmp_path, monkeypatch):
    fixture = next(row for row in json.loads((ROOT / "tests/fixtures/pulso_real/manifest.json").read_text())["fixtures"]
                   if "senior-housing" in row["url"])
    payload = gzip.decompress((ROOT / fixture["path"]).read_bytes())
    def reject(*args):
        raise ValueError("diagnosed_current_parser_rejection")
    monkeypatch.setattr(capture, "inspect_primary", reject)
    record = capture.capture_target({"url": fixture["url"]}, tmp_path,
                                   opener=lambda request, timeout: response(payload, fixture["url"]))
    assert record["status"] == 200 and record["original_bytes_retained"]
    compressed = (tmp_path / record["gzip_file"]).read_bytes()
    assert gzip.decompress(compressed) == payload
    assert record["sha256"] == hashlib.sha256(payload).hexdigest()
    assert record["gzip_sha256"] == hashlib.sha256(compressed).hexdigest()
    assert record["audit_error"]["reason"] == "diagnosed_current_parser_rejection"


def test_midnight_utc_and_chile_day_disagreement_is_observed_without_rewriting_byline():
    url = capture.CONTROL_URLS[0]
    body = "Texto sanitario de la clínica y la atención de pacientes. " * 140
    node = {"@type": "NewsArticle", "url": url, "datePublished": "2026-10-01T00:46:24.224Z",
            "headline": "Kast anuncia inteligencia artificial para atención de pacientes", "articleBody": body}
    # Synthetic unit case, never committed as a publisher original.
    html = (f'<link rel="canonical" href="{url}"><script type="application/ld+json">{json.dumps(node)}</script>'
            '<article><time class="byline-date">1 Octubre 2026</time></article>')
    audit = capture.inspect_primary(html, url, "2026-10-01")
    assert audit["visible_byline_day"] == "2026-10-01"
    assert audit["visible_matches_frozen_control"]
    assert audit["publication_timestamps"][0]["utc_day"] == "2026-10-01"
    assert audit["publication_timestamps"][0]["chile_day"] == "2026-09-30"
    assert audit["chile_day_disagrees_with_visible_byline"]
    assert audit["primary_body_chars"] > 5500
    assert audit["body_after_5500_chars"] > 0


@pytest.mark.parametrize("url", [
    "http://www.latercera.com/nacional/noticia/test/",
    "https://www.latercera.com.evil.test/nacional/noticia/test/",
    "https://user@www.latercera.com/nacional/noticia/test/",
    "https://www.latercera.com/nacional/",
    "https://www.latercera.com/nacional/noticia/test/?q=health",
])
def test_capture_rejects_foreign_hosts_and_unexpected_paths_before_network(tmp_path, url):
    def no_network(*args, **kwargs):
        raise AssertionError("Unexpected request")
    with pytest.raises(ValueError, match="unexpected_original_article_host_or_path"):
        capture.capture_target({"url": url}, tmp_path, opener=no_network)
    assert not list(tmp_path.iterdir())


def test_http_error_body_is_preserved_instead_of_becoming_missing_bytes(tmp_path):
    url = capture.CONTROL_URLS[0]
    payload = b"<html>Publisher temporary error</html>"
    record = capture.capture_target({"url": url}, tmp_path, opener=lambda request, timeout: response(payload, url, 503))
    assert record["status"] == 503
    assert record["original_bytes_retained"]
    assert gzip.decompress((tmp_path / record["gzip_file"]).read_bytes()) == payload


def test_targets_bind_two_frozen_controls_and_one_actual_rss_inventory_entry():
    selected = capture.targets(ROOT / "data/audits/pulso_external_control_2026_10_11.json",
                               ROOT / "data/audits/pulso_capture/manifest.json")
    assert [row["url"] for row in selected] == list(capture.CONTROL_URLS) + [capture.RSS_URL]
    assert [row["expected_publication_date"] for row in selected[:2]] == ["2026-10-01", "2026-10-09"]
    assert selected[2]["rss_publication_timestamp"] == "Fri, 09 Oct 2026 12:32:14 +0000"
    assert "expected_publication_date" not in selected[2]
