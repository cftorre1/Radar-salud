"""Read-only connectivity evidence for the nine configured clinical publishers."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from radar_salud.achs_clinics import CLINICS, NETWORK_IDENTITY_URL
try:
    from scripts.occupational_access_probe import capture, USER_AGENTS
except ModuleNotFoundError:
    from occupational_access_probe import capture, USER_AGENTS

REPRESENTATIVE_IDS = ("portada", "maitenes", "puerto_montt")
MAX_WORKERS = 2
CAPTURE_TIMEOUT = 35
REPO_ROOT = Path(__file__).resolve().parents[1]


def planned_phases():
    """Three regional representatives, then the remaining publishers and hub."""
    representatives = [clinic for identifier in REPRESENTATIVE_IDS for clinic in CLINICS if clinic["id"] == identifier]
    remaining = [clinic for clinic in CLINICS if clinic["id"] not in REPRESENTATIVE_IDS]
    hub = {"id": "clinical_network", "name": "Clínicas Achs Salud", "home": NETWORK_IDENTITY_URL, "news": None}
    return (("representatives", representatives), ("remaining_publishers_and_hub", remaining + [hub]))


def observe_dns(host):
    """Observe the OS resolver in a bounded child process; never select an IP."""
    command = [sys.executable, "-c", (
        "import json,socket,sys; "
        "a=socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM); "
        "print(json.dumps(sorted({(socket.AddressFamily(r[0]).name,r[4][0]) for r in a})))"
    ), host]
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8)
        values = json.loads(result.stdout) if result.returncode == 0 else []
        return {"host": host, "resolver": "normal_os_resolver", "elapsed_seconds": round(time.monotonic() - started, 3),
                "addresses_observed_only": values, "exit_code": result.returncode,
                "error": result.stderr.strip()[-1000:] if result.returncode else None}
    except (subprocess.TimeoutExpired, ValueError) as exc:
        return {"host": host, "resolver": "normal_os_resolver", "addresses_observed_only": [],
                "elapsed_seconds": round(time.monotonic() - started, 3), "error": type(exc).__name__}


def successful(record, statuses=(200,)):
    last = (record.get("hops") or [{}])[-1]
    return (record.get("stop_reason") == "response_captured" and record.get("http_status") in statuses
            and last.get("curl_exit") == 0 and last.get("tls", {}).get("verified") is True
            and not record.get("waf"))


def diagnose_publisher(publisher, output, *, probe=capture, dns_lookup=observe_dns):
    """Two home UAs only; robots/listing use the identified public audit UA."""
    started = time.monotonic()
    home = publisher["home"]
    parsed = urlsplit(home)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    records, skipped = [], []

    def request(surface, url, ua="identified"):
        try:
            record = probe(url, output, ua=ua, timeout=CAPTURE_TIMEOUT)
        except Exception as exc:
            record = {"url": url, "user_agent": ua, "http_status": 0, "hops": [],
                      "stop_reason": "probe_exception", "error": f"{type(exc).__name__}: {str(exc)[:1000]}"}
        record = dict(record, source=publisher["id"], surface=surface)
        records.append(record)
        return record

    try:
        dns = dns_lookup(parsed.hostname)
    except Exception as exc:
        dns = {"host": parsed.hostname, "error": f"{type(exc).__name__}: {str(exc)[:1000]}"}
    for ua in ("identified", "browser_comparison"):
        request("home", home, ua)
    robots = request("robots", robots_url)
    policy = None
    if successful(robots):
        policy = RobotFileParser()
        policy.parse((Path(output) / robots["hops"][-1]["body_file"]).read_text(errors="replace").splitlines())
    robots_available = policy is not None or successful(robots, statuses=(404,))
    news = publisher.get("news")
    if news:
        if any(record.get("waf") for record in records):
            skipped.append({"url": news, "reason": "publisher_challenge_observed_no_further_surface_probe"})
        elif not robots_available:
            skipped.append({"url": news, "reason": "robots_policy_unavailable", "robots_stop_reason": robots.get("stop_reason")})
        elif policy is not None and not policy.can_fetch(USER_AGENTS["identified"], news):
            skipped.append({"url": news, "reason": "robots_disallowed"})
        else:
            request("newsroom", news)
    return {"publisher_id": publisher["id"], "name": publisher["name"], "home": home, "newsroom": news,
            "dns": dns, "records": records, "skipped_surfaces": skipped,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def write_report(output, publishers, *, phase, started):
    records = [record for publisher in publishers for record in publisher["records"]]
    report = {"environment": "github_actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "codex", "run_id": os.environ.get("GITHUB_RUN_ID"),
              "candidate_sha": os.environ.get("CANDIDATE_SHA", os.environ.get("GITHUB_SHA")),
              "captured_at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": round(time.monotonic() - started, 3),
              "diagnostic_only": True, "state_mutation": False, "ai_calls": 0,
              "public_requests_only": True, "challenge_execution": False, "cookies_sent": False,
              "headers_allowlisted_no_cookies_or_authorization": True,
              "normal_dns_no_ip_selection": True, "concurrency_limit": MAX_WORKERS,
              "connect_timeout_seconds": 12, "request_timeout_seconds": CAPTURE_TIMEOUT,
              "phase": phase, "publishers_completed": len(publishers), "publishers_expected": 10,
              "summary": {"stop_reasons": dict(Counter(record.get("stop_reason") for record in records)),
                          "http_statuses": dict(Counter(str(record.get("http_status", 0)) for record in records)),
                          "successful_identified_newsrooms": sum(record.get("surface") == "newsroom" and successful(record) for record in records)},
              "publishers": publishers, "records": records}
    temporary = Path(output) / "report.json.tmp"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(Path(output) / "report.json")
    return report


def run_diagnostic(output, *, probe=capture, dns_lookup=observe_dns):
    output = Path(output).resolve()
    if not output.is_relative_to(REPO_ROOT.resolve() / "data/audits/source_e_recovery"):
        raise ValueError("Diagnostic output must stay under data/audits/source_e_recovery")
    output.mkdir(parents=True, exist_ok=True)
    publishers = []
    started = time.monotonic()
    write_report(output, publishers, phase="starting", started=started)
    for phase, group in planned_phases():
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(diagnose_publisher, publisher, output, probe=probe, dns_lookup=dns_lookup): publisher for publisher in group}
            for future in as_completed(futures):
                publisher = future.result()
                publisher["phase"] = phase
                publishers.append(publisher)
                write_report(output, publishers, phase=phase, started=started)
                print(json.dumps({"publisher": publisher["publisher_id"], "phase": phase,
                                  "stop_reasons": [record.get("stop_reason") for record in publisher["records"]]}), flush=True)
    return write_report(output, publishers, phase="completed", started=started)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run_diagnostic(args.output)


if __name__ == "__main__":
    main()
