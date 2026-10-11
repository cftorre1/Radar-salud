"""Reproducible ISP transport probe. Preserves proxy settings and TLS verification."""
import concurrent.futures
import datetime
import json
import subprocess
from pathlib import Path
import sys

CHANNELS = {
    "anamed": [
        "https://www.ispch.gob.cl/categorias-alertas/anamed/",
        "https://www.ispch.cl/categorias-alertas/anamed/",
        "https://ispch.cl/categorias-alertas/anamed/",
        "http://www.ispch.cl/categorias-alertas/anamed/",
        "https://www.ispch.cl/anamed/",
        "https://www.ispch.cl/categorias-alertas/anamed/feed/",
        "https://www.ispch.cl/wp-json/wp/v2/",
    ],
    "surveillance": [
        "https://www.ispch.gob.cl/boletin/",
        "https://www.ispch.cl/boletin/",
        "https://ispch.cl/boletin/",
        "http://www.ispch.cl/boletin/",
        "https://www.ispch.cl/boletines-de-vigilancia-y-laboratorio-al-dia/",
        "https://ispch.cl/boletin/informe-de-laboratorio-biomedico-vigilancia-de-rabia-animal-2025/",
        "https://ispch.cl/wp-content/uploads/2026/06/VB-Informe-anual-rabia-animal-2025.pdf",
        "https://www.ispch.cl/virusrespiratorios/",
        "https://ispch.cl/virusrespiratorios/",
        "https://ispch.cl/biomedico/vigilancia-de-laboratorio/ambitos-de-vigilancia/vigilancia-virus-respiratorios/informes-virus-respiratorios/?y=2026",
        "https://www.ispch.cl/documento/semana-39-2026/",
        "https://www.ispch.cl/wp-content/uploads/2026/09/Informe-circulacion-virus-respiratorios-SE36-15-09-2026.pdf",
        "https://www.ispch.cl/boletin/feed/",
        "https://www.ispch.cl/virusrespiratorios/feed/",
    ],
}
UAS = ["RadarSaludBot/0.1 (+public-source-monitor)",
       "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"]


def probe(task):
    url, ua, method = task
    command = ["curl", "--silent", "--show-error", "--location", "--max-time", "20",
               "--max-redirs", "5", "--user-agent", ua,
               "--write-out", "\nCURL_OBSERVATION:%{json}"]
    if method == "HEAD":
        command.append("--head")
    else:
        command.extend(["--dump-header", "-", "--output", "/dev/null"])
    command.append(url)
    before = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    headers, marker, metrics = result.stdout.partition("\nCURL_OBSERVATION:")
    parsed = json.loads(metrics) if marker else {}
    # The complete curl object can contain machine paths. Retain transport facts only.
    facts = {key: parsed.get(key) for key in ["response_code", "http_connect", "num_redirects",
                                             "url_effective", "ssl_verify_result", "exitcode"]}
    connect_denied = facts.get("http_connect") == 403
    proxy_http_denied = (not connect_denied and facts.get("response_code") == 403
                         and "server: envoy" in headers.lower())
    environment_denied = connect_denied or proxy_http_denied
    return {"attempted_at_utc": before, "url": url, "method": method, "user_agent": ua,
            "curl_exit_code": result.returncode, "headers": headers,
            "stderr": result.stderr.strip(), "metrics": facts,
            "origin_http_status": None if environment_denied else facts.get("response_code"),
            "origin_tls_verified": None if environment_denied or result.returncode or not url.startswith("https:") else True,
            "blocker_layer": ("environment_proxy_connect" if connect_denied else
                              "environment_proxy_http" if proxy_http_denied else "unclassified")}


channel = sys.argv[1]
tasks = [(url, ua, method) for url in CHANNELS[channel] for ua in UAS for method in ["HEAD", "GET"]]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    rows = list(pool.map(probe, tasks))
target = Path(f"data/audits/public_sources_c_20261011/isp_{channel}_transport.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({"tls_verification_disabled": False, "proxy_bypassed": False,
                              "channel": channel, "attempts": rows}, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"path": str(target), "attempts": len(rows),
                  "proxy_connect_denied": sum(row["blocker_layer"] == "environment_proxy_connect" for row in rows)}))
