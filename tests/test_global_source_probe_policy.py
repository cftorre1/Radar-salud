import importlib.util
from pathlib import Path
from urllib.parse import urlparse

spec = importlib.util.spec_from_file_location("global_probe", Path("scripts/probe_global_sources.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

def test_reuters_qualification_never_requests_journalism():
    targets = [(key, url) for key, url in probe.TARGETS if key.startswith("reuters")]
    assert len(targets) == 4
    for _, url in targets:
        assert urlparse(url).scheme == "https"
        assert urlparse(url).path in {"/robots.txt", "/info-pages/terms-of-use/", "/"}
        assert "/business/" not in url and "/legal/litigation/" not in url

def test_official_probe_domains_are_fixed_and_unique():
    assert len({key for key, _ in probe.TARGETS}) == len(probe.TARGETS)
    assert {urlparse(url).hostname for _, url in probe.TARGETS} == {
        "www.who.int", "www.paho.org", "www.reuters.com", "reutersagency.com"}
