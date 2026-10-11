"""Capture selected original details for date and full-body diagnosis only.

No discovery inventory, queue, engine, AI, history or publishing is invoked.
Original bytes are retained before any parser runs, including HTTP error HTML.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from radar_salud.pulso_source import _Article, _nodes, _visible_byline_day, article_url, extract_article, health_anchor

ROOT = Path(__file__).resolve().parents[1]
CONTROL_URLS = (
    "https://www.latercera.com/nacional/noticia/kast-anuncia-uso-de-inteligencia-artificial-en-salud-para-priorizar-atencion-de-pacientes-de-mayor-gravedad/",
    "https://www.latercera.com/pulso/noticia/licencias-medicas-anotan-en-agosto-su-mayor-alza-en-ano-y-medio-debido-a-baja-base-de-comparacion/",
)
RSS_URL = "https://www.latercera.com/nacional/noticia/mas-de-2000-viviendas-afectadas-las-condes-despliega-maquinaria-y-equipos-de-emergencia-para-retirar-barro-tras-aluvion/"
DIAGNOSTIC_URL = "https://www.latercera.com/branded/noticia/empresas-x-chile-el-movimiento-empresarial-que-busca-fomentar-el-empleo-juvenil-impulsando-practicas-tp/"
DIAGNOSTIC_RUN_ID = 38134030226


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def original_article_url(url):
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.netloc == "www.latercera.com"
            and not parsed.query and not parsed.fragment and "/noticia/" in parsed.path)


def nested_rss_entry(value):
    if isinstance(value, dict):
        if value.get("url") == RSS_URL and value.get("pubDate"):
            return value
        for nested in value.values():
            if (entry := nested_rss_entry(nested)) is not None:
                return entry
    elif isinstance(value, list):
        for nested in value:
            if (entry := nested_rss_entry(nested)) is not None:
                return entry
    return None


def targets(control_path, rss_manifest):
    control = json.loads(control_path.read_bytes())
    indexed = {row["url"]: row for row in control["articles"]}
    if any(url not in indexed for url in CONTROL_URLS):
        raise ValueError("target_missing_from_frozen_control")
    rss = nested_rss_entry(json.loads(rss_manifest.read_bytes()))
    if rss is None:
        raise ValueError("target_missing_from_captured_official_rss")
    return [dict(url=url, title=indexed[url]["title"], expected_publication_date=indexed[url]["publication_date"],
                 target_reason="frozen_original_byline_vs_midnight_utc_chile_day", inventory_source="independent_frozen_control")
            for url in CONTROL_URLS] + [dict(url=RSS_URL, title=rss["title"],
                rss_publication_timestamp=rss["pubDate"], target_reason="full_primary_body_health_evidence_after_5500",
                inventory_source="captured_official_rss_not_final_date_evidence"),
                dict(url=DIAGNOSTIC_URL, target_reason="core_detail_error_incomplete_article_evidence",
                     inventory_source="core_diagnostic_not_frozen_control", source_run_id=DIAGNOSTIC_RUN_ID)]


def date_projection(kind, timestamp):
    result = {"source": kind, "timestamp": timestamp}
    try:
        stamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("timezone_missing")
        result.update(timestamp_calendar_day=stamp.date().isoformat(),
                      utc_day=stamp.astimezone(timezone.utc).date().isoformat(),
                      chile_day=stamp.astimezone(ZoneInfo("America/Santiago")).date().isoformat())
    except (ValueError, TypeError, AttributeError) as error:
        result["error"] = str(error)
    return result


def inspect_primary(html, url, expected=None):
    parser = _Article()
    parser.feed(html)
    dates = []
    bodies = []
    for script in parser.scripts:
        try:
            for node in _nodes(json.loads(script)):
                link = node.get("url") or node.get("mainEntityOfPage") or node.get("@id")
                if isinstance(link, dict):
                    link = link.get("@id")
                if article_url(link, url) != url:
                    continue
                if node.get("datePublished"):
                    dates.append(date_projection("url_bound_json_ld_datePublished", node["datePublished"]))
                if isinstance(node.get("articleBody"), str):
                    bodies.append(" ".join(node["articleBody"].split()))
        except (ValueError, TypeError):
            continue
    if parser.metas.get("article:published_time"):
        dates.append(date_projection("article_published_time", parser.metas["article:published_time"]))
    dates.extend(date_projection("article_time", value) for value in parser.times)
    try:
        byline = _visible_byline_day(parser.byline_dates)
        byline_error = None
    except ValueError as error:
        byline, byline_error = None, str(error)
    observed = {"canonical": parser.canonical, "visible_byline_text": " ".join(parser.byline_dates),
                "visible_byline_day": byline, "visible_byline_error": byline_error,
                "publication_timestamps": dates, "expected_frozen_byline_day": expected,
                "visible_matches_frozen_control": byline == expected if expected and byline else None,
                "chile_day_disagrees_with_visible_byline": bool(byline and any(
                    row.get("chile_day") != byline for row in dates if row.get("chile_day")))}
    if bodies:
        body = max(bodies, key=len)
        observed.update(primary_body_chars=len(body), primary_body_sha256=digest(body.encode()),
                        body_after_5500_chars=max(0, len(body)-5500), body_after_5500_text=body[5500:7500],
                        health_anchor_full_body=health_anchor(body), health_anchor_first_5500=health_anchor(body[:5500]))
    try:
        title, body, metadata = extract_article(html, url)
        observed["current_parser"] = {"status": "verified", "title": title, "body_chars": len(body), "metadata": metadata}
    except Exception as error:
        observed["current_parser"] = {"status": "error", "error_type": type(error).__name__, "reason": str(error)}
    return observed


def capture_target(target, output, opener=urlopen):
    url = target["url"]
    if not original_article_url(url):
        raise ValueError("unexpected_original_article_host_or_path")
    record = dict(target, requested_at=datetime.now(timezone.utc).isoformat())
    try:
        request = Request(url, headers={"User-Agent": "RadarSaludBot/0.1 (+public-source-monitor)"})
        try:
            response = opener(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            payload = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            record.update(status=response.status, final_url=response.geturl(), charset=charset,
                          content_type=response.headers.get("Content-Type", ""))
        compressed = gzip.compress(payload, mtime=0)
        relative = digest(payload) + ".html.gz"
        output.mkdir(parents=True, exist_ok=True)
        (output / relative).write_bytes(compressed)
        record.update(captured_at=datetime.now(timezone.utc).isoformat(), bytes=len(payload), sha256=digest(payload),
                      gzip_file=relative, gzip_sha256=digest(compressed), original_bytes_retained=True)
        # Saving the raw response precedes both diagnostic and production parsers.
        text = payload.decode(charset, errors="replace")
        record["returned_text_utf8_sha256"] = digest(text.encode())
        try:
            record["primary_date_and_body_audit"] = inspect_primary(text, url, target.get("expected_publication_date"))
        except Exception as error:
            record["audit_error"] = {"error_type": type(error).__name__, "reason": str(error)}
    except Exception as error:
        record.update(status=record.get("status", "error"), error_type=type(error).__name__, error=str(error))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, default=ROOT / "data/audits/pulso_external_control_2026_10_11.json")
    parser.add_argument("--rss-manifest", type=Path, default=ROOT / "data/audits/pulso_capture/manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "tests/fixtures/pulso_targeted_primary_real")
    parser.add_argument("--audit", type=Path, default=ROOT / "data/audits/pulso_targeted_primary_date_audit_2026_10_11.json")
    args = parser.parse_args()
    rows = [capture_target(target, args.output) for target in targets(args.control, args.rss_manifest)]
    report = {"schema_version": "1.0", "source": "pulso_latercera", "mode": "original_detail_capture_without_analysis_discovery_queue_or_publishing",
              "captured_at": datetime.now(timezone.utc).isoformat(), "ai_calls": 0,
              "control_sha256": digest(args.control.read_bytes()), "rss_manifest_sha256": digest(args.rss_manifest.read_bytes()),
              "target_count": len(rows),
              "captured_response_count": sum(bool(row.get("original_bytes_retained")) for row in rows),
              "status": "ORIGINAL_RESPONSES_CAPTURED_NOT_SOURCE_ACCEPTANCE" if all(
                  row.get("status") == 200 and row.get("original_bytes_retained") for row in rows) else "TARGETED_CAPTURE_PARTIAL",
              "requests": rows, "acceptance_note": "Capture retains original bytes even if the current parser rejects them; RSS dates remain provisional."}
    args.output.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (args.output / "manifest.json").write_text(serialized)
    args.audit.write_text(serialized)
    print(json.dumps({"status": report["status"], "http_statuses": [row["status"] for row in rows], "ai_calls": 0}))


if __name__ == "__main__":
    main()
