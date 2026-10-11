"""Bindings between observed documents and dated, captured ACHS articles."""
from datetime import date
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from radar_salud.beta_sources import _Links
from radar_salud.occupational_sources import Article


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/audits/source_e_recovery/achs_document_routes.json"


def test_document_routes_are_observed_on_the_bound_live_publisher_article():
    manifest = json.loads(MANIFEST.read_text())
    assert len(manifest["documents"]) == 3
    for document in manifest["documents"]:
        evidence = document["link_observation_capture"]
        content = (ROOT / evidence["artifact"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == evidence["sha256"]
        assert evidence["http_status"] == 200 and evidence["tls_verified"]
        parser = _Links()
        parser.feed(content.decode("utf-8"))
        url = document["associated_article_url"]
        assert (document["document_url"], document["link_label"]) in [
            (urljoin(url, href), label) for href, label in parser.links
        ]
        article = Article(url)
        article.feed(content.decode("utf-8"))
        assert article.publication_evidence(today=date(2026, 10, 11)) == document["associated_article_publication_evidence"]
        assert article.result(today=date(2026, 10, 11))[1] == document["associated_article_publication_date"]
        # A dated linking article does not establish a separate PDF/PPTX date.
        assert document["document_publication_date"] is None


def test_capture_targets_preserve_exact_official_urls_and_do_not_claim_binary_access():
    manifest = json.loads(MANIFEST.read_text())
    targets = {url for _, _, url in manifest["capture_targets"]}
    assert targets == {document["document_url"] for document in manifest["documents"]}
    assert manifest["paid_api_calls"] == 0 and not manifest["canonical_state_changed"]
    assert manifest["editorial_threshold"] == 75
    assert manifest["browser_attempt"]["origin_http_status_observed"] is None
    for document in manifest["documents"]:
        url = urlsplit(document["document_url"])
        assert url.scheme == "https" and url.hostname == "www.achs.cl"
        assert url.port in (None, 443) and not url.username and not url.password and not url.fragment
        assert url.path.startswith("/docs/librariesprovider2/")
        assert url.path.endswith((".pdf", ".pptx"))
        assert document["capture_state"] == "pending_verified_binary_capture"
