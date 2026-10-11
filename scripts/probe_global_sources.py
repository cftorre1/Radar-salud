"""Bounded official-surface probes; never retrieves Reuters journalism."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from html import unescape
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from radar_salud.global_discovery_common import USER_AGENT

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
def run(output: Path, extended: bool = False) -> dict:
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
    targets = [target for target in TARGETS if target[0] != "reuters_terms"]
    if extended:
        targets = [("who_robots", "https://www.who.int/robots.txt"), ("paho_robots", "https://www.paho.org/robots.txt")]
        prior = Path("data/audits/global_source_recovery_2026_10_11/probes/38141320771")
        for name in ("who_news", "who_publications", "who_emergencies"):
            text = (prior / (name + ".body")).read_text()
            match = re.search(r'hubsfiltering\([^,]+,\s*"[^"]+",\s*"([^"]+)"', text)
            if not match:
                raise ValueError("official API link not found")
            targets.append((name + "_api", urljoin("https://www.who.int", match[1]) + "&$skip=0&$top=50"))
        targets += [
            ("who_detail", "https://www.who.int/news/item/09-10-2026-who-urges-shift-from-institutional-to-community-based-mental-health-care"),
            ("paho_rss", "https://www.paho.org/en/rss.xml"),
            ("paho_chile_filter", "https://www.paho.org/en/news?c%5B%5D=65"),
            ("paho_terms", "https://www.paho.org/en/terms-and-conditions-use-site"),
            ("reuters_service_license", "https://reutersagency.com/license-reuters-content/"),
            ("reuters_service_api", "https://www.reutersagency.com/content-delivery-platforms/api-integrations/"),
        ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(probe, targets))
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "run_id": os.environ.get("GITHUB_RUN_ID"), "head_sha": os.environ.get("GITHUB_SHA"),
              "reuters_journalism_requested": False, "records": records}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    durable = Path("data/audits/global_source_recovery_2026_10_11/probes") / str(report["run_id"] or "local")
    durable.mkdir(parents=True, exist_ok=True)
    (durable / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for record in records:
        body = output / record["body_file"]
        if not body.exists():
            continue
        if record["key"].startswith("reuters") and not record["key"].endswith("robots"):
            # Only policy/service discovery metadata, never archive Reuters HTML.
            text = unescape(re.sub(r"<[^>]+>", " ", body.read_text(errors="replace")))
            text = " ".join(text.split())
            policy = [text[max(0, m.start()-120):m.end()+500]
                      for m in re.finditer(r"(?i)automat|licens|reproduc|syndicat|terms of use|Reuters Connect|API|copyright", text)]
            links = re.findall(r'''(?i)href=["']([^"']+)["']''', body.read_text(errors="replace"))
            links = sorted({url for url in links if any(term in url.lower() for term in ("terms", "license", "licens", "connect", "api", "copyright", "platform"))})
            (durable / (record["key"] + ".metadata.json")).write_text(json.dumps({"policy_fragments":policy[:20], "service_policy_links":links}, ensure_ascii=False, indent=2)+"\n")
        else:
            (durable / record["body_file"]).write_bytes(body.read_bytes())
    print(json.dumps({"run_id": report["run_id"], "results": [{"key": x["key"], "http": x["http_status"], "exit": x["returncode"]} for x in records]}))
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("work/global-surface-probes"))
    parser.add_argument("--extended", action="store_true")
    args = parser.parse_args()
    run(args.output, args.extended)
