"""Probe of the SIS open data files (Dirección 4-nov-2026: 'eso es oro').

Reads the SIS 'Datos abiertos de Isapres' page, lists every file link on datos.superdesalud.gob.cl, and for each
dataset downloads ONE recent file (bounded bytes) to record: URL, HTTP status, size, SHA-256, the ZIP members and
the header line (column names) of each member. robots.txt is honoured on both hosts (fail closed on errors other than
404). Nothing is published; the report is the receipt the data pipeline will build on.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import time
import urllib.robotparser
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

PAGE = "https://www.superdesalud.gob.cl/tax-biblioteca-digital/datos-abiertos-de-isapres-6988/"
FILE_HOST = "datos.superdesalud.gob.cl"
UA = "AlicantoSaludBot/1.0 (+https://alicantosalud.cl; datos abiertos SIS, lectura acotada)"
MAX_BYTES = 120 * 1024 * 1024
ROBOTS: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def get(url: str, limit: int = MAX_BYTES, timeout: int = 120) -> tuple[int, bytes, dict]:
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=timeout) as r:
            data = r.read(limit + 1)
            if len(data) > limit:
                raise ValueError(f"over_limit:{limit}")
            return r.status, data, dict(r.headers)
    except HTTPError as e:
        return e.code, b"", dict(e.headers or {})


def allowed(url: str) -> tuple[bool, str]:
    host = urlparse(url).netloc
    if host not in ROBOTS:
        try:
            status, body, _ = get(f"https://{host}/robots.txt", limit=512 * 1024, timeout=30)
        except (URLError, OSError, ValueError) as e:
            ROBOTS[host] = None
            return False, f"robots_unreachable:{type(e).__name__}"
        if status == 404:
            ROBOTS[host] = urllib.robotparser.RobotFileParser()
            ROBOTS[host].parse([])
        elif status != 200:
            ROBOTS[host] = None
            return False, f"robots_status:{status}"
        else:
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(body.decode("utf-8", "replace").splitlines())
            ROBOTS[host] = rp
    rp = ROBOTS[host]
    if rp is None:
        return False, "robots_unavailable"
    return rp.can_fetch(UA, url), "robots_ok" if rp.can_fetch(UA, url) else "robots_disallow"


def dataset_of(url: str) -> str:
    parts = unquote(urlparse(url).path).split("/")
    return parts[2] if len(parts) > 2 and parts[1] == "archivos" else "otro"


def period_key(url: str) -> str:
    m = re.findall(r"(\d{4}(?:t\d|\d{2})?)", unquote(url.rsplit("/", 1)[-1]).lower())
    return m[-1] if m else ""


def members(blob: bytes) -> list[dict]:
    out = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return [{"error": "bad_zip"}]
    for info in zf.infolist()[:20]:
        row = {"name": info.filename, "size": info.file_size}
        if not info.is_dir() and info.file_size:
            with zf.open(info) as f:
                head = f.read(4096)
            text = head.decode("utf-8", "replace") if b"\x00" not in head else ""
            first = text.splitlines()[0] if text else ""
            row["header"] = first[:600]
            row["delimiter"] = max([";", ",", "|", "\t"], key=first.count) if first else None
            row["encoding_guess"] = "utf-8" if head.decode("utf-8", "ignore") == head.decode("utf-8", "replace") else "latin-1?"
        out.append(row)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--per-dataset", type=int, default=1)
    a = ap.parse_args()
    report = {"page": PAGE, "user_agent": UA, "started_at": datetime.now(timezone.utc).isoformat(), "datasets": {}}
    ok, why = allowed(PAGE)
    report["page_robots"] = why
    if not ok:
        Path(a.output).write_text(json.dumps(report, ensure_ascii=False, indent=1))
        return
    status, body, _ = get(PAGE, limit=8 * 1024 * 1024, timeout=60)
    report["page_status"] = status
    links = sorted({html.unescape(m) for m in re.findall(r'href=["\']([^"\']+)["\']', body.decode("utf-8", "replace"))})
    files = [urljoin(PAGE, u) for u in links if urlparse(urljoin(PAGE, u)).netloc == FILE_HOST]
    dicts = [urljoin(PAGE, u) for u in links if "Diccionario" in u]
    report["dictionaries"] = dicts
    by: dict[str, list[str]] = {}
    for u in files:
        by.setdefault(dataset_of(u), []).append(u)
    for ds, urls in sorted(by.items()):
        urls.sort(key=period_key)
        entry = {"files_listed": len(urls), "first": urls[0], "last": urls[-1], "probed": []}
        for u in urls[-a.per_dataset:]:
            ok, why = allowed(u)
            row = {"url": u, "robots": why}
            if ok:
                t0 = time.time()
                try:
                    st, blob, hdr = get(u)
                    row.update(status=st, bytes=len(blob), seconds=round(time.time() - t0, 1),
                               sha256=hashlib.sha256(blob).hexdigest() if blob else None,
                               content_type=hdr.get("Content-Type"), last_modified=hdr.get("Last-Modified"))
                    if blob:
                        row["members"] = members(blob)
                except (URLError, OSError, ValueError) as e:
                    row["error"] = f"{type(e).__name__}:{e}"[:200]
            entry["probed"].append(row)
            time.sleep(2)
        report["datasets"][ds] = entry
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: {"listed": v["files_listed"], "last": v["last"].rsplit("/", 1)[-1],
                          "probe": [(p.get("status"), p.get("bytes"), p.get("robots")) for p in v["probed"]]}
                      for k, v in report["datasets"].items()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
