"""Read-only real transport + native scout replay, confined to artifact output.

No API keys, AI calls, queue/seen/history/feed mutations or git pushes. The
workflow is branch-only and has read permissions. A completed diagnostic is
not an operational PASS: every source's actual discovery outcome is recorded.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import shutil
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from radar_salud.public_source_evidence import HOSTS, failure_details


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_HOSTS = set().union(*HOSTS.values()) | {"nuevo.fonasa.gob.cl"}
HEADERS = {"User-Agent": "RadarSaludBot/0.3 (+public-source-monitor)",
           "Accept": "text/html,application/pdf,application/xml,application/json;q=0.9,*/*;q=0.5"}


def now():
    return datetime.now(timezone.utc).isoformat()


def allowed(url):
    p = urlsplit(url)
    return (p.scheme == "https" and p.hostname in OFFICIAL_HOSTS
            and p.port in (None, 443) and not p.username and not p.password)


class TraceRedirects(HTTPRedirectHandler):
    def __init__(self, rows):
        super().__init__()
        self.rows = rows

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.rows.append({"from": req.full_url, "status": code, "to": newurl})
        if not allowed(newurl):
            raise ValueError("Redirect left the official HTTPS hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def error_stage(exc):
    reason = exc.reason if isinstance(exc, URLError) else exc
    message = str(reason)
    if "Tunnel connection failed" in message:
        return "proxy_connect"
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, HTTPError):
        return "http"
    return "transport_or_parser"


def probe(slug, url, output, timeout=18):
    row = {"source": slug, "url": url, "host": urlsplit(url).hostname,
           "captured_at": now(), "method": "GET", "redirects": [],
           "http_status": None, "origin_tls_observed": False}
    try:
        if not allowed(url):
            raise ValueError("Probe URL is outside official HTTPS hosts")
        row["dns"] = {"addresses": sorted({v[4][0] for v in socket.getaddrinfo(row["host"], 443)})}
    except socket.gaierror as exc:
        row["dns"] = {"error": str(exc)}
    try:
        request = Request(url, headers=HEADERS)
        try:
            response = build_opener(TraceRedirects(row["redirects"])).open(request, timeout=timeout)
        except HTTPError as exc:
            response = exc
        with response:
            row.update(http_status=response.code, final_url=response.geturl(), origin_tls_observed=True,
                       headers={k: v for k, v in response.headers.items() if k.lower() in {
                           "content-type", "server", "date", "location", "last-modified", "etag",
                           "content-length", "retry-after"}})
            body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise ValueError("Capture exceeded 8 MiB")
            digest = hashlib.sha256(body).hexdigest()
            suffix = ".pdf" if body.startswith(b"%PDF-") else ".html"
            path = output / "captures" / (digest + suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            row.update(sha256=digest, bytes=len(body), body_path=str(path.relative_to(output)))
            text = body[:300000].decode("utf-8", errors="replace").lower()
            waf = any(x in text for x in ("_incapsula_resource", "cf-chl-", "request unsuccessful. incapsula",
                                          "access denied | akamai", "captcha-delivery.com"))
            row["waf_challenge"] = waf
            row["outcome"] = "waf" if waf else "http" if response.code >= 400 else "captured"
    except Exception as exc:
        row.update(outcome=error_stage(exc), error_type=type(exc).__name__, error=str(exc))
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "work/public-source-recovery")
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    endpoints = json.loads((ROOT / "config/public_source_runtime_endpoints.json").read_text())
    tasks = [(slug, url) for slug, urls in endpoints.items() for url in urls]
    with ThreadPoolExecutor(max_workers=6) as executor:
        probes = list(executor.map(lambda pair: probe(*pair, args.output), tasks))
    result = {"captured_at": now(), "runtime": "github_actions" if os.getenv("GITHUB_ACTIONS") else "codex",
              "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "run_id": os.getenv("GITHUB_RUN_ID"), "probes": probes,
              "ai_calls": 0, "ingestion_state_mutated": False}
    (args.output / "transport.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if not args.probe_only:
        from check_public_sources import check
        from radar_salud import public_source_transport
        from radar_salud.deis_sources import DeisCatalogScout
        native_captures = []
        original_download = public_source_transport.download_official
        def capture_download(url, slug, **kwargs):
            metadata = kwargs.get("capture_metadata")
            capture = metadata if metadata is not None else {}
            kwargs["capture_metadata"] = capture
            body, headers = original_download(url, slug, **kwargs)
            path = args.output / "captures" / (capture["sha256"] + (".pdf" if body.startswith(b"%PDF-") else ".html"))
            path.write_bytes(body)
            native_captures.append({"source": slug, **capture, "body_path": str(path.relative_to(args.output))})
            return body, headers
        public_source_transport.download_official = capture_download
        # The native scouts use the actual configured HTTPS transport. Their
        # diagnostic runner cannot publish and does not call paid processing.
        isolated_root = args.output / "isolated"
        (isolated_root / "data").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "data/source_health.json", isolated_root / "data/source_health.json")
        runtime = check(isolated_root, record_health=True)
        (args.output / "native_discovery.json").write_text(json.dumps(runtime, ensure_ascii=False, indent=2) + "\n")
        result["native_operational_sources"] = runtime["operational_sources"]
        try:
            catalog = DeisCatalogScout().discover()
        except Exception as exc:
            catalog = {"source": "deis", "error": str(exc), "error_details": failure_details(exc)}
        (args.output / "deis_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
        (args.output / "native_captures.json").write_text(json.dumps(native_captures, ensure_ascii=False, indent=2) + "\n")
        # Replay the real durable queue contract against a copy of the existing
        # stock. This records horizon rejections without inventing paid analysis.
        from radar_salud.pending_queue import PendingQueue
        from radar_salud.models import RawItem
        queue_path = isolated_root / "data/state/pending_queue.json"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "data/state/pending_queue.json", queue_path)
        queue = PendingQueue(queue_path)
        queue_result = {"mode": "isolated_real_queue_discovery_without_paid_processing",
                        "main_staging_production_mutated": False, "sources": {}}
        for slug, row in runtime["sources"].items():
            items = [RawItem(**item) for item in row["items"]]
            for item in items:
                item.metadata["source_quality_gate"] = "audit_pending_90_day"
            added = queue.discover(slug, items)
            rows = [{"key": key, **value} for key, value in queue.items.items() if value["source"] == slug]
            queue_result["sources"][slug] = {"added": added, "counts": queue.counts(slug), "records": rows}
        (args.output / "isolated_queue_replay.json").write_text(json.dumps(queue_result, ensure_ascii=False, indent=2) + "\n")
    summary = {"runtime": result["runtime"], "commit": result["commit"],
               "transport_outcomes": {slug: [
                   {"url": row["url"], "outcome": row["outcome"], "http_status": row["http_status"]}
                   for row in probes if row["source"] == slug] for slug in endpoints},
               "native_operational_sources": result.get("native_operational_sources"),
               "diagnostic_only": True}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
