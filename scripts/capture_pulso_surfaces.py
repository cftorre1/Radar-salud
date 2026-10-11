"""Capture public La Tercera surfaces from an isolated, permitted runner.

This probe establishes routing and markup, not 30/90-day coverage. Responses are
saved unchanged, hashed and compressed; article dates remain publisher evidence
for the production parser to verify. No model calls or publishing occur here.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urldefrag
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET


BASE = "https://www.latercera.com"
HOSTS = {"www.latercera.com", "latercera.com"}
USER_AGENT = "RadarSaludBot/0.1 (+public-source-monitor)"
SITEMAPS = (
    BASE + "/arc/outboundfeeds/sitemap-index/?outputType=xml",
    BASE + "/arc/outboundfeeds/news-sitemap-index/?outputType=xml",
    BASE + "/arc/outboundfeeds/sitemap/?outputType=xml",
)
ARTICLE_FIXTURES = (
    BASE + "/pulso/noticia/senior-housing-los-grupos-que-dominan-el-negocio-de-las-residencias-para-adultos-mayores/",
    BASE + "/nacional/noticia/clinica-uc-christus-de-san-carlos-de-apoquindo-termina-traslado-de-pacientes-ante-suspension-de-operaciones-por-aluvion/",
)
SEEDS = (
    (BASE + "/robots.txt", "robots", "publisher_declaration"),
    *((url, "sitemap", "robots_declaration_verified_independently") for url in SITEMAPS),
    *((BASE + path, "listing", "configured_or_known_taxonomy") for path in (
        "/canal/pulso/", "/canal/nacional/", "/etiqueta/salud/",
        "/etiqueta/isapres/", "/etiqueta/fonasa/", "/etiqueta/clinicas/",
        "/etiqueta/hospitales/", "/etiqueta/listas-de-espera/",
    )),
    (BASE + "/arc/outboundfeeds/rss/?outputType=xml", "feed", "endpoint_hypothesis"),
    (BASE + "/feed/", "feed", "endpoint_hypothesis"),
    *((url, "article", "independent_known_article") for url in ARTICLE_FIXTURES),
    (BASE + "/etiqueta/salud/2/", "pagination", "route_hypothesis"),
    (BASE + "/etiqueta/isapres/2/", "pagination", "route_hypothesis"),
    (BASE + "/canal/pulso/2/", "pagination", "route_hypothesis"),
    (BASE + "/search/?q=salud", "search", "robots_exclusion_probe_no_request"),
)


def official_url(url: str, base: str = BASE) -> str | None:
    target = urldefrag(urljoin(base, url))[0]
    parsed = urlsplit(target)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS
            or parsed.username or parsed.password or parsed.port):
        return None
    return target


def publisher_excluded(url: str) -> bool:
    # RobotFileParser does not implement Google's wildcard query matching.
    # Preserve the publisher's explicit exclusions even after parsing robots.
    parsed = urlsplit(url)
    return parsed.path.startswith("/pf/api/v3/") or (
        parsed.path == "/search/" and any(part.startswith("q=") for part in parsed.query.split("&")))


class OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official_url(newurl, req.full_url):
            raise URLError("redirect_outside_official_publisher")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.meta = {}
        self.canonical = None
        self.scripts = []
        self.json_ld = []
        self._script_type = None
        self._script_parts = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])
        elif tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            if key and attributes.get("content"):
                self.meta.setdefault(key, []).append(attributes["content"])
        elif tag == "link" and "canonical" in attributes.get("rel", "").split():
            self.canonical = attributes.get("href")
        elif tag == "script":
            self._script_type = attributes.get("type", "")
            self._script_parts = []
            if attributes.get("src"):
                self.scripts.append(attributes["src"])

    def handle_data(self, data):
        if self._script_type is not None:
            self._script_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script_type is not None:
            if self._script_type == "application/ld+json":
                try:
                    self.json_ld.append(json.loads("".join(self._script_parts)))
                except ValueError:
                    self.json_ld.append({"parse_error": True})
            self._script_type = None
            self._script_parts = []


def describe(payload: bytes, url: str, content_type: str) -> dict:
    """Describe observed evidence without assigning an editorial date or verdict."""
    text = payload.decode("utf-8", errors="replace")
    parser = Markup()
    parser.feed(text)
    links = list(dict.fromkeys(u for link in parser.links if (u := official_url(link, url))))
    locations = []
    root_type = None
    try:
        root = ET.fromstring(payload)
        root_type = root.tag.rsplit("}", 1)[-1]
        locations = list(dict.fromkeys(
            u for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "loc"
            and node.text and (u := official_url(node.text.strip(), url))))
    except (ET.ParseError, ValueError):
        pass
    observed_endpoints = list(dict.fromkeys(
        u for match in re.findall(r'["\'](/(?:pf/api|arc/outboundfeeds)/[^"\'\s<>]+)', text)
        if (u := official_url(match.replace("\\u0026", "&"), url))))
    return {
        "canonical": parser.canonical,
        "metadata": {k: v for k, v in parser.meta.items() if k in (
            "article:published_time", "article:modified_time", "og:url",
            "og:title", "article:section", "description", "cXenseParse:recs:publishtime")},
        "json_ld": parser.json_ld,
        "fusion_properties": sorted(set(re.findall(r"Fusion\.([A-Za-z_$][\w$]*)", text))),
        "official_script_urls": [u for path in parser.scripts if (u := official_url(path, url))],
        "observed_public_endpoint_candidates": observed_endpoints,
        "article_links": [link for link in links if "/noticia/" in urlsplit(link).path],
        "pagination_links": [link for link in links if re.search(
            r"/(?:page|pagina|p)/\d+/?$|/\d+/?$|[?&](?:page|offset|from|p)=", link)],
        "taxonomy_links": [link for link in links if re.search(r"/(?:etiqueta|canal)/", link)],
        "xml_root": root_type,
        "xml_location_count": len(locations),
        "xml_locations": locations,
        "content_type": content_type,
    }


def save_response(output: Path, payload: bytes) -> dict:
    digest = hashlib.sha256(payload).hexdigest()
    relative = Path("responses") / f"{digest}.gz"
    path = output / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(payload, mtime=0))
    return {"sha256": digest, "bytes": len(payload), "gzip_file": str(relative),
            "gzip_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def capture(output: Path, *, maximum: int = 45, seconds: int = 600,
            fixture_dir: Path | None = None, opener=None) -> dict:
    opener = opener or build_opener(OfficialRedirects())
    report = {"schema_version": "1.0", "source": "pulso_latercera",
              "started_at": datetime.now(timezone.utc).isoformat(),
              "verdict": "SURFACE_PROBE_NOT_COVERAGE_ACCEPTANCE", "ai_calls": 0,
              "coverage_complete_30_days": False, "coverage_complete_90_days": False,
              "robots_enforced": True, "responses": [], "fixtures": []}
    queue = list(SEEDS)
    visited = set()
    robots = RobotFileParser()
    robots.parse(["User-agent: *", "Disallow: /pf/api/v3/", "Disallow: /search/?q="])
    deadline = time.monotonic() + seconds
    while queue and len(visited) < maximum and time.monotonic() < deadline:
        url, kind, provenance = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        record = {"url": url, "kind": kind, "provenance": provenance,
                  "captured_at": datetime.now(timezone.utc).isoformat()}
        report["responses"].append(record)
        if not official_url(url):
            record.update(status="skipped", reason="outside_official_publisher")
        elif url != BASE + "/robots.txt" and (publisher_excluded(url) or not robots.can_fetch(USER_AGENT, url)):
            record.update(status="skipped", reason="publisher_robots_disallow")
        else:
            try:
                request = Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept-Encoding": "identity"})
                try:
                    response = opener.open(request, timeout=25)
                except HTTPError as error:
                    response = error
                with response:
                    payload = response.read(8_000_001)
                    record.update(status=response.status, final_url=response.geturl(),
                                  content_type=response.headers.get("Content-Type", ""))
                record.update(save_response(output, payload))
                if len(payload) > 8_000_000:
                    record.update(truncated=True, reason="response_exceeded_8mb_bound")
                if record["status"] == 200 and not record.get("truncated"):
                    record["observed"] = describe(payload, record["final_url"], record["content_type"])
                    if kind == "robots":
                        text = payload.decode("utf-8", errors="replace")
                        robots.parse(text.splitlines())
                        declared = [u for value in re.findall(r"^Sitemap:\s*(\S+)", text, re.M | re.I)
                                    if (u := official_url(value))]
                        record["declared_sitemaps"] = declared
                        queue.extend((u, "sitemap", "observed_robots_declaration") for u in declared)
                    if record["observed"]["xml_root"] == "sitemapindex":
                        queue.extend((u, "sitemap_child", "observed_sitemap_index")
                                     for u in record["observed"]["xml_locations"][:2])
                    if kind in {"listing", "pagination"}:
                        queue.extend((u, "pagination", "observed_archive_link")
                                     for u in record["observed"]["pagination_links"][:2])
                    if fixture_dir and url in {BASE + "/etiqueta/salud/", BASE + "/canal/pulso/", *ARTICLE_FIXTURES}:
                        fixture_dir.mkdir(parents=True, exist_ok=True)
                        name = "pulso_listing" if url == BASE + "/canal/pulso/" else (
                            "salud_listing" if "/etiqueta/" in url else (
                                "senior_housing" if "/pulso/" in url else "uc_christus"))
                        fixture_path = fixture_dir / f"{name}.html.gz"
                        fixture_path.write_bytes(gzip.compress(payload, mtime=0))
                        report["fixtures"].append({"path": str(fixture_path), "url": url,
                            "captured_at": record["captured_at"], "sha256": record["sha256"],
                            "gzip_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                            "transformation": "gzip storage only; original response bytes unchanged"})
            except Exception as error:
                record.update(status="error", error_type=type(error).__name__, error=str(error)[:250])
        write_json(output / "manifest.json", report)
    report.update(finished_at=datetime.now(timezone.utc).isoformat(),
                  remaining_probe_urls=len(queue), attempted_urls=len(visited))
    write_json(output / "manifest.json", report)
    if fixture_dir:
        write_json(fixture_dir / "manifest.json", {"source": report["source"],
                   "verdict": report["verdict"], "fixtures": report["fixtures"]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/audits/pulso_capture"))
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures/pulso_real"))
    parser.add_argument("--max-urls", type=int, default=45)
    parser.add_argument("--seconds", type=int, default=600)
    args = parser.parse_args()
    report = capture(args.output, maximum=args.max_urls, seconds=args.seconds, fixture_dir=args.fixtures)
    print(json.dumps({"verdict": report["verdict"], "attempted": report["attempted_urls"],
                      "successful": sum(r["status"] == 200 for r in report["responses"]),
                      "fixtures": len(report["fixtures"]), "manifest": str(args.output / "manifest.json")}))


if __name__ == "__main__":
    main()
