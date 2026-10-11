"""Bounded public-origin probes. Never submit forms, cookies or WAF challenges."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

OFFICIAL_HOSTS = {
    "achs.cl", "www.achs.cl", "achssalud.cl", "www.achssalud.cl",
    "mutual.cl", "www.mutual.cl", "ww2.mutual.cl", "ist.cl", "www.ist.cl",
    "clinicasachssalud.cl", "www.clinicasachssalud.cl",
    "proceso-devolucion-masiva.mutual.cl",
    "www.clinicaportada.cl", "clinicaportada.cl", "clinicaatacama.cl", "www.clinicaatacama.cl",
    "clinicaloscoihues.cl", "www.clinicaloscoihues.cl", "www.clinicamaitenes.cl", "clinicamaitenes.cl",
    "www.clinicalircay.cl", "clinicalircay.cl", "clinicalosandes.cl", "www.clinicalosandes.cl",
    "www.clinicasur.cl", "clinicasur.cl", "www.clinicapuertomontt.cl", "clinicapuertomontt.cl",
    "www.clinica-curico.cl", "clinica-curico.cl",
}
SAFE_HEADERS = {
    "content-type", "content-length", "date", "last-modified", "etag", "location",
    "server", "strict-transport-security", "retry-after", "x-robots-tag",
    "x-iinfo", "x-cdn", "cf-ray", "cf-mitigated", "cache-control",
    "x-wp-total", "x-wp-totalpages", "link",
}
USER_AGENTS = {
    "identified": "AlicantoSaludSourceRecovery/1.0 (public-source audit; no challenge execution)",
    "browser_comparison": "Mozilla/5.0 (compatible; AlicantoSaludSourceRecovery/1.0)",
}
TARGETS = [
    ("achs", "robots", "https://www.achs.cl/robots.txt"),
    ("achs", "newsroom", "https://www.achs.cl/centro-de-noticias"),
    ("achs", "page_2", "https://www.achs.cl/centro-de-noticias/2"),
    ("achs", "sitemap", "https://www.achs.cl/sitemap.xml"),
    ("achs", "feed_candidate", "https://www.achs.cl/feed/"),
    ("achs_salud", "robots", "https://www.achssalud.cl/robots.txt"),
    ("achs_salud", "clinics", "https://www.achssalud.cl/areasdeatencion/clinicas"),
    ("achs_salud", "home", "https://www.achssalud.cl/"),
    ("achs_salud", "sitemap", "https://www.achssalud.cl/sitemap.xml"),
    ("achs_clinics", "robots", "https://www.clinicasachssalud.cl/robots.txt"),
    ("achs_clinics", "home", "https://www.clinicasachssalud.cl/"),
    ("achs_clinics", "sitemap", "https://www.clinicasachssalud.cl/sitemap.xml"),
    ("mutual", "robots", "https://www.mutual.cl/robots.txt"),
    ("mutual", "home", "https://www.mutual.cl/"),
    ("mutual", "newsroom", "https://www.mutual.cl/portal/publico/empresa/home/nuestra-mutual/noticias/"),
    ("mutual", "sitemap_candidate", "https://www.mutual.cl/sitemap.xml"),
    ("mutual", "feed_candidate", "https://www.mutual.cl/feed/"),
    ("mutual_legacy", "home", "https://ww2.mutual.cl/"),
    ("ist", "robots", "https://ist.cl/robots.txt"),
    ("ist", "newsroom", "https://ist.cl/noticias/"),
    ("ist", "page_2", "https://ist.cl/noticias/page/2/"),
    ("ist", "category_page_2", "https://ist.cl/category/noticias/page/2/"),
    ("ist", "category_page_3", "https://ist.cl/category/noticias/page/3/"),
    ("ist", "transparency", "https://ist.cl/transparencia/"),
    ("ist", "feed", "https://ist.cl/feed/"),
    ("ist", "sitemap_candidate", "https://ist.cl/wp-sitemap.xml"),
    ("ist", "api_candidate", "https://ist.cl/wp-json/wp/v2/posts?per_page=1"),
]


def official_url(url):
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname in OFFICIAL_HOSTS
            and parsed.port in (None, 443) and not parsed.username and not parsed.password)


def safe_headers(raw):
    # A proxy CONNECT and final response can share the dump; keep their blocks.
    blocks = []
    for block in re.split(r"\r?\n\r?\n", raw.strip()):
        lines = block.splitlines()
        if not lines or not lines[0].startswith("HTTP/"):
            continue
        selected = {"status_line": lines[0]}
        for line in lines[1:]:
            name, sep, value = line.partition(":")
            if sep and name.lower() in SAFE_HEADERS:
                selected[name.lower()] = value.strip()
        blocks.append(selected)
    return blocks


def waf_kind(body):
    text = body[:150000].decode("utf-8", errors="replace")
    if re.search(r"_Incapsula_Resource|Incapsula incident|Request unsuccessful.*Incapsula", text, re.I | re.S):
        return "incapsula_challenge"
    if re.search(r"cf-chl-|Just a moment\.\.\.|cf-turnstile", text, re.I):
        return "cloudflare_challenge"
    if len(body) < 15000 and re.search(r"verify you are human|access denied|request blocked", text, re.I):
        return "possible_access_challenge"
    return None


def capture(url, output, *, ua="identified", timeout=35):
    if not official_url(url):
        raise ValueError("Only configured public official HTTPS hosts may be requested")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256((url + "\n" + ua).encode()).hexdigest()[:20]
    record = {"url": url, "user_agent": ua, "captured_at": datetime.now(timezone.utc).isoformat(), "hops": []}
    current = url
    for hop in range(6):
        with tempfile.TemporaryDirectory() as temp:
            header_path, body_path = Path(temp) / "headers", Path(temp) / "body"
            max_bytes = "20000000" if urlsplit(current).path.casefold().endswith(".pdf") else "6000000"
            command = ["curl", "--silent", "--show-error", "--proto", "=https", "--connect-timeout", "12",
                       "--max-time", str(timeout), "--max-filesize", max_bytes, "--max-redirs", "0",
                       "--user-agent", USER_AGENTS[ua], "--dump-header", str(header_path),
                       "--output", str(body_path), "--write-out", "%{json}", current]
            process = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 10)
            try:
                info = json.loads(process.stdout)
            except (ValueError, TypeError):
                info = {}
            headers = safe_headers(header_path.read_text(errors="replace") if header_path.exists() else "")
            body = body_path.read_bytes() if body_path.exists() else b""
            status = int(info.get("response_code", info.get("http_code", 0)) or 0)
            connect_status = int(info.get("http_connect", 0) or 0)
            origin_tls = status > 0 and connect_status in (0, 200)
            details = {"url": current, "http_status": status, "proxy_connect_status": connect_status,
                       "curl_exit": process.returncode, "headers": headers,
                       "tls": {"origin_handshake_observed": origin_tls,
                               "certificate_verification_result": info.get("ssl_verify_result") if origin_tls else None,
                               "verified": origin_tls and info.get("ssl_verify_result") == 0},
                       "content_type": info.get("content_type"), "bytes": len(body),
                       "sha256": hashlib.sha256(body).hexdigest(), "waf": waf_kind(body),
                       "error": process.stderr.strip()[:1000] if process.returncode else None}
            name = f"{identity}-{hop}.body"
            (output / name).write_bytes(body)
            details["body_file"] = name
            record["hops"].append(details)
            if status in (301, 302, 303, 307, 308):
                location = next((b.get("location") for b in reversed(headers) if b.get("location")), None)
                if location:
                    destination = urljoin(current, location)
                    if not official_url(destination):
                        record["stop_reason"] = "redirect_outside_official_allowlist"
                        record["redirect_destination"] = destination
                        break
                    current = destination
                    continue
            if connect_status == 403:
                record["stop_reason"] = "proxy_connect_rejected"
            elif details["waf"]:
                record["stop_reason"] = details["waf"]
            else:
                record["stop_reason"] = "transport_error" if process.returncode else "response_captured"
            break
    else:
        record["stop_reason"] = "redirect_limit"
    record["final_url"] = current
    record["http_status"] = record["hops"][-1]["http_status"]
    record["waf"] = record["hops"][-1]["waf"]
    (output / f"{identity}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--environment", choices=["github_actions", "codex"], required=True)
    parser.add_argument("--targets-json", help="Additional confirmed official route triples")
    args = parser.parse_args()
    output = Path(args.output)
    targets = TARGETS + (json.loads(Path(args.targets_json).read_text()) if args.targets_json else [])
    records = []
    for source, surface, url in targets:
        agents = ["identified", "browser_comparison"] if surface in ("home", "newsroom") else ["identified"]
        for ua in agents:
            try:
                record = capture(url, output, ua=ua)
            except Exception as exc:
                record = {"url": url, "user_agent": ua, "stop_reason": "probe_exception", "error": str(exc)}
            record.update(source=source, surface=surface)
            records.append(record)
            print(json.dumps({k: record.get(k) for k in ("source", "surface", "url", "user_agent", "http_status", "waf", "stop_reason")}), flush=True)
            time.sleep(1)
    report = {"environment": args.environment, "run_id": os.environ.get("GITHUB_RUN_ID"),
              "candidate_sha": os.environ.get("GITHUB_SHA"), "captured_at": datetime.now(timezone.utc).isoformat(),
              "public_requests_only": True, "challenge_execution": False, "cookies_sent": False,
              "headers_allowlisted_no_cookies_or_authorization": True, "records": records}
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
