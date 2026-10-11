"""Bounded official-surface probes; never retrieves Reuters journalism."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

TARGETS = [
    ("who_robots", "https://www.who.int/robots.txt"),
    ("who_news", "https://www.who.int/news"),
    ("who_emergencies", "https://www.who.int/emergencies/disease-outbreak-news"),
    ("who_publications", "https://www.who.int/publications/i"),
    ("who_rss", "https://www.who.int/rss-feeds"),
    ("who_copyright", "https://www.who.int/about/policies/publishing/copyright"),
    ("paho_robots", "https://www.paho.org/robots.txt"),
    ("paho_news", "https://www.paho.org/en/news"),
    ("paho_alerts", "https://www.paho.org/en/epidemiological-alerts-and-updates"),
    ("paho_reports", "https://www.paho.org/es/informes-tecnicos"),
    ("paho_chile", "https://www.paho.org/es/chile/noticias"),
    ("paho_copyright", "https://www.paho.org/en/copyright"),
    ("reuters_robots", "https://www.reuters.com/robots.txt"),
    ("reuters_terms", "https://www.reuters.com/info-pages/terms-of-use/"),
    ("reuters_service_robots", "https://reutersagency.com/robots.txt"),
    ("reuters_service", "https://reutersagency.com/"),
]
USER_AGENT = "AlicantoHealthDiscovery/1.0 (+https://github.com/cftorre1/Radar-salud; metadata research)"

def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    def probe(target):
        key, url = target
        body, headers = output / f"{key}.body", output / f"{key}.headers.tmp"
        started = datetime.now(timezone.utc).isoformat()
        result = subprocess.run([
            "curl", "--silent", "--show-error", "--location", "--max-redirs", "4",
            "--proto", "=https", "--proto-redir", "=https", "--connect-timeout", "12",
            "--max-time", "40", "--max-filesize", "5000000", "--user-agent", USER_AGENT,
            "--dump-header", str(headers), "--output", str(body), "--write-out", "%{json}", url,
        ], capture_output=True, text=True, timeout=45)
        try:
            transport = json.loads(result.stdout)
        except ValueError:
            transport = {}
        raw = body.read_bytes() if body.exists() else b""
        allowed = {"location", "content-type", "last-modified", "date", "server", "x-cdn", "retry-after"}
        safe_headers = [line for line in (headers.read_text(errors="replace") if headers.exists() else "").splitlines()
                        if line.startswith("HTTP/") or line.partition(":")[0].lower() in allowed]
        headers.unlink(missing_ok=True)
        return {"key": key, "requested_url": url, "fetched_at": started,
                "returncode": result.returncode, "http_status": transport.get("http_code", 0),
                "final_url": transport.get("url_effective"), "redirects": transport.get("num_redirects"),
                "ssl_verify_result": transport.get("ssl_verify_result"), "safe_headers": safe_headers,
                "error": result.stderr[:500], "body_sha256": hashlib.sha256(raw).hexdigest(),
                "body_bytes": len(raw), "body_file": body.name, "user_agent": USER_AGENT}
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(probe, TARGETS))
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "run_id": os.environ.get("GITHUB_RUN_ID"), "head_sha": os.environ.get("GITHUB_SHA"),
              "reuters_journalism_requested": False, "records": records}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"run_id": report["run_id"], "results": [{"key": x["key"], "http": x["http_status"], "exit": x["returncode"]} for x in records]}))
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("work/global-surface-probes"))
    run(parser.parse_args().output)
